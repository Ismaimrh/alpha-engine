"""Senate EFD direct loader (Plan B for Step 5.4).

The community Stock Watcher mirrors died (403, verified 2026-07-09), so we
go to the official source: efdsearch.senate.gov (Senate Office of Public
Records). Electronic PTRs (Periodic Transaction Reports) are HTML tables;
paper filings are scanned images and are SKIPPED (counted + logged).

Protocol (long-established EFD flow):
    1. GET  /search/home/  -> csrfmiddlewaretoken + session cookie
    2. POST /search/home/  with prohibition_agreement=1  (access agreement)
    3. POST /search/report/data/  (DataTables JSON) filtered to PTRs (type
       11) in a submitted-date window, paginated
    4. GET  each electronic PTR page /search/view/ptr/<uuid>/ and parse the
       transactions table

Output rows are shaped exactly like the old Stock Watcher rows, so the
whole normalize/dedup/upsert path in congress_loader is REUSED unchanged
(same row_key, same table, source='senate_efd').

House PTRs (PDF parsing) are deferred post-MVP — decision recorded in
CLAUDE.md; the smart-money composite renormalizes to the legs present.

Resumability: parsed PTRs are cached to data/raw/congress/efd/<uuid>.json;
re-runs skip cached filings (delete the dir or pass refresh=True to force).
"""

from __future__ import annotations

import json
import re
import time
from datetime import date, datetime, timedelta

import requests
from bs4 import BeautifulSoup

from app.config import RAW_DATA_DIR

BASE = "https://efdsearch.senate.gov"
HOME = f"{BASE}/search/home/"
SEARCH_DATA = f"{BASE}/search/report/data/"
EFD_CACHE_DIR = RAW_DATA_DIR / "congress" / "efd"

REQUEST_PAUSE = 0.5
PAGE_SIZE = 100
PTR_LINK_RE = re.compile(r"/search/view/(ptr|paper)/([0-9a-f-]+)/")

# Browser-realistic identity: EFD sits behind an anti-bot layer (403s
# obviously-scripted clients). Tier 1 = these headers; Tier 2 = Selenium.
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
BROWSER_HEADERS = {
    "User-Agent": BROWSER_UA,
    "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
               "image/avif,image/webp,*/*;q=0.8"),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
}


# ------------------------------------------------------------------ session

def open_session() -> requests.Session:
    """Tier 1 bootstrap: browser-realistic requests session."""
    s = requests.Session()
    s.headers.update(BROWSER_HEADERS)
    landing = s.get(HOME, timeout=30)
    if landing.status_code == 403:
        raise RuntimeError(
            "EFD returned 403 to the requests client (anti-bot layer). "
            "Use the Selenium engine: pip install selenium, ensure Chrome "
            "is installed, then run with --engine selenium."
        )
    landing.raise_for_status()
    token = extract_csrf(landing.text)
    s.headers["Referer"] = HOME
    resp = s.post(
        HOME,
        data={"csrfmiddlewaretoken": token, "prohibition_agreement": "1"},
        timeout=30,
    )
    resp.raise_for_status()
    time.sleep(REQUEST_PAUSE)
    return s


def open_session_selenium(headless: bool = False) -> requests.Session:
    """Tier 2 bootstrap: real Chrome passes the anti-bot check and the
    access agreement; its cookies + exact UA are transplanted into a
    requests.Session for the fast data endpoints.

    HEADED by default: Akamai commonly blocks headless Chrome but passes a
    visible one — a window will open for a few seconds during bootstrap.
    On failure, saves page HTML + screenshot to data/raw/congress/ for
    diagnosis and raises with pointers.
    """
    try:
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.support.ui import WebDriverWait
    except ImportError as exc:
        raise RuntimeError(
            "Selenium engine requested but not installed: pip install selenium"
        ) from exc

    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1280,900")
    # Standard stealth: hide the obvious automation tells Akamai checks.
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    driver = webdriver.Chrome(options=options)
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"},
    )
    try:
        driver.get(HOME)
        wait = WebDriverWait(driver, 30)
        try:
            checkbox = wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR,
                     "input[name='prohibition_agreement'], "
                     "input#agree_statement, input[type='checkbox']")
                )
            )
        except Exception as exc:  # noqa: BLE001 — dump diagnostics, then fail loud
            EFD_CACHE_DIR.parent.mkdir(parents=True, exist_ok=True)
            html_path = EFD_CACHE_DIR.parent / "efd_debug.html"
            png_path = EFD_CACHE_DIR.parent / "efd_debug.png"
            html_path.write_text(driver.page_source)
            driver.save_screenshot(str(png_path))
            raise RuntimeError(
                f"EFD agreement checkbox not found. url={driver.current_url!r} "
                f"title={driver.title!r}. Saved {html_path} and {png_path} — "
                f"send these for loader repair. If the page looks like an "
                f"'Access Denied' challenge, retry WITHOUT --headless, or from "
                f"a different network."
            ) from exc
        checkbox.click()
        for btn in driver.find_elements(By.CSS_SELECTOR, "button[type='submit']"):
            try:
                btn.click()
                break
            except Exception:  # noqa: BLE001
                pass
        wait.until(lambda d: "/search/" in d.current_url)
        ua = driver.execute_script("return navigator.userAgent")
        s = requests.Session()
        s.headers.update({**BROWSER_HEADERS, "User-Agent": ua, "Referer": HOME})
        for c in driver.get_cookies():
            s.cookies.set(c["name"], c["value"], domain=c.get("domain"))
        return s
    finally:
        driver.quit()


def get_session(engine: str = "auto") -> requests.Session:
    """engine: 'requests', 'selenium', or 'auto' (requests then selenium)."""
    if engine == "requests":
        return open_session()
    if engine == "selenium":
        return open_session_selenium()
    try:
        return open_session()
    except RuntimeError as exc:
        print(f"Tier 1 failed ({exc}); trying Selenium ...", flush=True)
        return open_session_selenium()


def extract_csrf(html: str) -> str:
    """csrfmiddlewaretoken from a form page (fixture-testable)."""
    soup = BeautifulSoup(html, "lxml")
    node = soup.find("input", attrs={"name": "csrfmiddlewaretoken"})
    if node is None or not node.get("value"):
        raise RuntimeError(
            "EFD landing page had no csrfmiddlewaretoken — site markup may "
            "have changed; paste the page HTML for loader repair."
        )
    return node["value"]


# ------------------------------------------------------------- PTR listing

def list_ptrs(session: requests.Session, start: date, end: date) -> tuple[list[dict], int]:
    """All PTR filings submitted in [start, end].

    Returns ([{uuid, url, senator, filed}], paper_count). Paper filings are
    counted but not returned.
    """
    csrf = session.cookies.get("csrftoken", "")
    filings, paper, offset = [], 0, 0
    while True:
        payload = {
            "start": str(offset),
            "length": str(PAGE_SIZE),
            "report_types": "[11]",  # 11 = Periodic Transaction Report
            "filer_types": "[]",
            "submitted_start_date": start.strftime("%m/%d/%Y 00:00:00"),
            "submitted_end_date": end.strftime("%m/%d/%Y 23:59:59"),
            "candidate_state": "",
            "senator_state": "",
            "office_id": "",
            "first_name": "",
            "last_name": "",
            "csrfmiddlewaretoken": csrf,
        }
        resp = session.post(SEARCH_DATA, data=payload, timeout=30)
        resp.raise_for_status()
        page = resp.json()
        rows = page.get("data", [])
        for row in rows:
            parsed = parse_listing_row(row)
            if parsed is None:
                continue
            if parsed["kind"] == "paper":
                paper += 1
            else:
                filings.append(parsed)
        offset += PAGE_SIZE
        if offset >= int(page.get("recordsTotal", 0)) or not rows:
            break
        time.sleep(REQUEST_PAUSE)
    return filings, paper


def parse_listing_row(row: list) -> dict | None:
    """One DataTables row -> {kind, uuid, url, senator, filed} or None.

    Row shape: [first_name, last_name, office_html, report_link_html,
    date_received]. (fixture-testable)
    """
    if len(row) < 5:
        return None
    first, last, _office, link_html, filed = row[0], row[1], row[2], row[3], row[4]
    m = PTR_LINK_RE.search(link_html or "")
    if m is None:
        return None
    kind, uuid = m.group(1), m.group(2)
    return {
        "kind": kind,
        "uuid": uuid,
        "url": f"{BASE}/search/view/{kind}/{uuid}/",
        "senator": f"{(first or '').strip().title()} {(last or '').strip().title()}".strip(),
        "filed": (filed or "").strip(),
    }


# --------------------------------------------------------------- PTR pages

def parse_ptr_html(html: str, senator: str, filed: str) -> list[dict]:
    """Transactions table of one electronic PTR -> Stock-Watcher-shaped rows.

    Expected cells per row: [#, transaction_date, owner, ticker, asset_name,
    asset_type, type, amount, comment]. Rows whose ticker cell is '--' pass
    through (normalize_rows skips them centrally). (fixture-testable)
    """
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table")
    if table is None:
        return []
    out = []
    for tr in table.find_all("tr"):
        cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        if len(cells) < 8:
            continue
        out.append(
            {
                "transaction_date": cells[1],
                "disclosure_date": filed,
                "ticker": cells[3],
                "type": cells[6],
                "amount": cells[7],
                "senator": senator,
            }
        )
    return out


def fetch_ptr_rows(session: requests.Session, filing: dict,
                   refresh: bool = False) -> list[dict]:
    """Fetch+parse one PTR, with a per-filing JSON cache for resumability."""
    EFD_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = EFD_CACHE_DIR / f"{filing['uuid']}.json"
    if cache.exists() and not refresh:
        return json.loads(cache.read_text())
    resp = session.get(filing["url"], timeout=30)
    resp.raise_for_status()
    rows = parse_ptr_html(resp.text, filing["senator"], filing["filed"])
    cache.write_text(json.dumps(rows))
    time.sleep(REQUEST_PAUSE)
    return rows


# ------------------------------------------------------------------ backfill

def backfill_senate_efd(years: int = 2, refresh: bool = False,
                        engine: str = "auto") -> dict:
    """Plan B Step 5.4 flow: Senate EFD -> congress_transactions."""
    from app.data_pipeline.congress_loader import (
        dedupe_row_keys,
        normalize_rows,
        staleness,
    )
    from app.data_pipeline.yfinance_loader import get_ticker_to_id, log_quality
    from app.utils.db import supabase

    mapping = get_ticker_to_id()
    end = date.today()
    start = end - timedelta(days=int(years * 365.25))

    started = datetime.now()
    session = get_session(engine)
    filings, paper = list_ptrs(session, start, end)
    print(f"EFD: {len(filings)} electronic PTRs, {paper} paper (skipped), "
          f"{start} -> {end}", flush=True)

    raw_rows: list[dict] = []
    for n, filing in enumerate(filings, 1):
        try:
            raw_rows.extend(fetch_ptr_rows(session, filing, refresh=refresh))
        except Exception as exc:  # noqa: BLE001 — one bad PTR must not kill the run
            print(f"WARN: PTR {filing['uuid']} failed: {exc}", flush=True)
        if n % 50 == 0:
            elapsed = (datetime.now() - started).total_seconds()
            eta_min = (elapsed / n) * (len(filings) - n) / 60
            print(f"  {n}/{len(filings)} PTRs ({len(raw_rows)} raw rows, "
                  f"ETA ~{eta_min:.0f} min)", flush=True)

    rows = normalize_rows(raw_rows, "Senate")
    for r in rows:
        r["source"] = "senate_efd"
    newest, stale = staleness(rows)
    matched = [r for r in rows if r["ticker"] in mapping]
    records = []
    for r in matched:
        r = dict(r)
        r["company_id"] = mapping[r.pop("ticker")]
        records.append(r)
    records = dedupe_row_keys(records)
    for i in range(0, len(records), 500):
        supabase.table("congress_transactions").upsert(
            records[i : i + 500], on_conflict="row_key"
        ).execute()

    status = "partial" if stale else "success"
    details = (f"EFD: {len(filings)} PTRs (+{paper} paper skipped), "
               f"{len(rows)} normalized, {len(records)} matched universe; "
               f"newest filing {newest}")
    log_quality([{"ticker": None, "status": status, "details": details,
                  "source": "congress"}])
    return {
        "electronic_ptrs": len(filings),
        "paper_ptrs_skipped": paper,
        "raw_rows": len(raw_rows),
        "normalized_rows": len(rows),
        "rows_written": len(records),
        "newest_filing": str(newest),
        "stale": stale,
        "elapsed_s": round((datetime.now() - started).total_seconds(), 1),
    }
