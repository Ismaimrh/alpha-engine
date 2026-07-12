"""SEC EDGAR Form 4 insider-transactions pipeline (spec Step 5.3 / Phase 1).

Flow (runnable entry: scripts/backfill_insider.py):
    1. load_ticker_cik_map()      — SEC's company_tickers.json (cached)
    2. list_form4_filings(cik)    — from data.sec.gov submissions JSON
    3. fetch + parse_form4(xml)   — nonDerivativeTable P/S transactions
    4. upsert into insider_transactions (dedup: accession_no + row_seq,
       migration 004)

SEC FAIR-ACCESS COMPLIANCE (https://www.sec.gov/os/accessing-edgar-data):
- Mandatory declarative User-Agent with contact info: we hard-fail if
  SEC_USER_AGENT is unset or still the .env.example placeholder.
- Max 10 requests/second allowed; we throttle to ~5/s (REQUEST_PAUSE).

Scope per spec: open-market purchases (code P) and sales (code S) from the
non-derivative table only. total_value = shares x price; rows with no
price (gifts, code-less legs) are skipped. Point-in-time key: filing_date
comes from the submissions index (when the market could see it), distinct
from transaction_date.

Known MVP limitation (documented): the submissions JSON "recent" block
covers an issuer's last ~1000 filings. For S&P 500 names, 2 years of Form
4s virtually always fits; if the window isn't fully covered we log a
data_quality 'partial' row rather than silently under-reporting.
"""

from __future__ import annotations

import json
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta

import requests

from app.config import RAW_DATA_DIR, SEC_USER_AGENT

CIK_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:0>10}.json"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc_nodash}/{doc}"

SEC_CACHE_DIR = RAW_DATA_DIR / "insider"
CHECKPOINT_FILE = SEC_CACHE_DIR / "backfill_checkpoint.json"
REQUEST_PAUSE = 0.2  # ~5 req/s, half the SEC ceiling
MAX_RETRIES = 3


# ----------------------------------------------------------------- checkpoint

def load_checkpoint() -> dict[str, str]:
    """{ticker: iso_date_completed} for tickers already fully processed."""
    if CHECKPOINT_FILE.exists():
        try:
            return json.loads(CHECKPOINT_FILE.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def save_checkpoint(done: dict[str, str]) -> None:
    """Atomic write (temp + rename) so a kill mid-write can't corrupt it."""
    CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CHECKPOINT_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(done, indent=0))
    tmp.replace(CHECKPOINT_FILE)


def _headers() -> dict:
    if not SEC_USER_AGENT or "your.email@example.com" in SEC_USER_AGENT.lower():
        raise RuntimeError(
            "SEC_USER_AGENT is unset or still the placeholder. SEC fair-access "
            "policy requires a real 'Name contact@email' User-Agent in .env "
            "before any EDGAR request."
        )
    return {"User-Agent": SEC_USER_AGENT, "Accept-Encoding": "gzip, deflate"}


def _get(url: str) -> requests.Response:
    """Throttled GET with retries and SEC-compliant headers."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, headers=_headers(), timeout=30)
            if resp.status_code == 429:
                time.sleep(2**attempt)
                continue
            resp.raise_for_status()
            time.sleep(REQUEST_PAUSE)
            return resp
        except requests.RequestException:
            if attempt == MAX_RETRIES:
                raise
            time.sleep(2**attempt)
    raise RuntimeError(f"unreachable: {url}")


# ------------------------------------------------------------- CIK mapping

def load_ticker_cik_map(refresh: bool = False) -> dict[str, int]:
    """ticker -> CIK from SEC's official mapping, cached to data/raw/insider/.

    SEC tickers use dashes for share classes (BRK-B), matching our
    canonical US form — no re-normalization needed.
    """
    cache = SEC_CACHE_DIR / "company_tickers.json"
    if cache.exists() and not refresh:
        raw = json.loads(cache.read_text())
    else:
        raw = _get(CIK_MAP_URL).json()
        SEC_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(raw))
    return {row["ticker"].upper(): int(row["cik_str"]) for row in raw.values()}


# ------------------------------------------------------- filings enumeration

def list_form4_filings(cik: int, since: date) -> tuple[list[dict], bool]:
    """(filings, window_fully_covered) for form type '4' since `since`.

    Each filing dict: {accession, filing_date, primary_doc}.
    window_fully_covered is False when the 'recent' block's oldest entry is
    newer than `since` (possible under-reporting; logged by the caller).
    """
    data = _get(SUBMISSIONS_URL.format(cik=cik)).json()
    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accessions = recent.get("accessionNumber", [])
    dates = recent.get("filingDate", [])
    docs = recent.get("primaryDocument", [])

    filings = []
    for form, acc, fdate, doc in zip(forms, accessions, dates, docs):
        if form != "4":
            continue
        filed = date.fromisoformat(fdate)
        if filed >= since:
            filings.append(
                {"accession": acc, "filing_date": filed, "primary_doc": doc}
            )
    oldest_listed = (
        date.fromisoformat(dates[-1]) if dates else date.today()
    )
    return filings, oldest_listed <= since


def fetch_form4_xml(cik: int, accession: str, primary_doc: str) -> str:
    """Fetch the primary Form 4 XML document for a filing."""
    acc_nodash = accession.replace("-", "")
    # primary_doc can carry an XSL-view prefix (xslF345X0x/); strip to raw XML
    doc = primary_doc.split("/")[-1]
    return _get(ARCHIVE_URL.format(cik=cik, acc_nodash=acc_nodash, doc=doc)).text


# ----------------------------------------------------------------- parsing

def _text(node, path: str) -> str | None:
    found = node.find(path)
    return found.text.strip() if found is not None and found.text else None


def _clean_date(raw: str | None) -> str | None:
    """Form 4 date values sometimes carry timezone suffixes
    ('2026-05-12-05:00') that Postgres rejects. Keep the ISO date part,
    validate it; None if unparseable."""
    if not raw:
        return None
    candidate = raw.strip()[:10]
    try:
        return date.fromisoformat(candidate).isoformat()
    except ValueError:
        return None


def parse_form4(xml_text: str) -> list[dict]:
    """Parse one ownershipDocument into P/S transaction dicts.

    Returns rows with: transaction_date, transaction_code, shares, price,
    total_value, insider_name, insider_title. Non-derivative table only;
    rows without a positive price are skipped (gifts, exercises).
    """
    root = ET.fromstring(xml_text)

    name = _text(root, ".//reportingOwner/reportingOwnerId/rptOwnerName")
    rel = root.find(".//reportingOwner/reportingOwnerRelationship")
    title = None
    if rel is not None:
        title = _text(rel, "officerTitle")
        if not title:
            flags = [
                ("isDirector", "Director"),
                ("isOfficer", "Officer"),
                ("isTenPercentOwner", "10% Owner"),
            ]
            title = next(
                (label for tag, label in flags if _text(rel, tag) in ("1", "true")),
                None,
            )

    rows = []
    for txn in root.findall(".//nonDerivativeTable/nonDerivativeTransaction"):
        code = _text(txn, "transactionCoding/transactionCode")
        if code not in ("P", "S"):
            continue
        tdate = _clean_date(_text(txn, "transactionDate/value"))
        shares = _text(txn, "transactionAmounts/transactionShares/value")
        price = _text(txn, "transactionAmounts/transactionPricePerShare/value")
        try:
            shares_f = float(shares)
            price_f = float(price)
        except (TypeError, ValueError):
            continue
        if not tdate or shares_f <= 0 or price_f <= 0:
            continue
        rows.append(
            {
                "transaction_date": tdate,
                "transaction_code": code,
                "shares": shares_f,
                "price": price_f,
                "total_value": round(shares_f * price_f, 2),
                "insider_name": name,
                "insider_title": title,
            }
        )
    return rows


# ------------------------------------------------------------------ backfill

def backfill_insider(
    tickers: list[str] | None = None, years: int = 2, restart: bool = False
) -> dict:
    """Full Step 5.3 flow. Upserts insider_transactions for the universe.

    Resume semantics: a ticker is checkpointed once fully processed; on
    re-run, checkpointed tickers whose completion date is today are skipped
    (no SEC re-downloads). `restart=True` ignores the checkpoint. Progress
    prints are flushed so `tail -f` works under nohup.
    """
    from app.data_pipeline.yfinance_loader import get_ticker_to_id, log_quality
    from app.utils.db import supabase

    mapping = get_ticker_to_id()
    universe = tickers if tickers is not None else sorted(mapping)
    universe = [t for t in universe if t in mapping]
    since = date.today() - timedelta(days=int(years * 365.25))
    cik_map = load_ticker_cik_map()

    done = {} if restart else load_checkpoint()
    today_iso = date.today().isoformat()
    skipped = [t for t in universe if done.get(t) == today_iso]
    todo = [t for t in universe if done.get(t) != today_iso]

    quality, rows_written, filings_seen = [], 0, 0
    started = datetime.now()
    print(
        f"Form 4 backfill: {len(todo)} tickers to do, {len(skipped)} "
        f"checkpointed (skipped), since {since} ...",
        flush=True,
    )
    for n, ticker in enumerate(todo, 1):
        cik = cik_map.get(ticker)
        if cik is None:
            quality.append(
                {"ticker": ticker, "status": "missing",
                 "details": "no CIK in SEC mapping"}
            )
            done[ticker] = today_iso
            save_checkpoint(done)
            continue
        try:
            filings, covered = list_form4_filings(cik, since)
            filings_seen += len(filings)
            records = []
            for filing in filings:
                xml_text = fetch_form4_xml(cik, filing["accession"], filing["primary_doc"])
                for seq, row in enumerate(parse_form4(xml_text)):
                    records.append(
                        {
                            "company_id": mapping[ticker],
                            "filing_date": filing["filing_date"].isoformat(),
                            "accession_no": filing["accession"],
                            "row_seq": seq,
                            "source": "SEC_EDGAR",
                            **row,
                        }
                    )
            for i in range(0, len(records), 500):
                supabase.table("insider_transactions").upsert(
                    records[i : i + 500], on_conflict="accession_no,row_seq"
                ).execute()
            rows_written += len(records)
            status = "success" if covered else "partial"
            quality.append(
                {"ticker": ticker, "status": status,
                 "details": f"{len(filings)} filings, {len(records)} P/S rows"
                 + ("" if covered else " (recent-block window not fully covered)")}
            )
            done[ticker] = today_iso  # checkpoint only after full success
            save_checkpoint(done)
        except Exception as exc:  # noqa: BLE001 — NOT checkpointed; retried on resume
            quality.append(
                {"ticker": ticker, "status": "error", "details": str(exc)[:300]}
            )
        if n % 10 == 0:
            elapsed = (datetime.now() - started).total_seconds()
            eta_min = (elapsed / n) * (len(todo) - n) / 60
            print(
                f"  {n}/{len(todo)} done ({rows_written} rows, "
                f"{filings_seen} filings, ETA ~{eta_min:.0f} min)",
                flush=True,
            )
    for q in quality:
        q["source"] = "sec_edgar"
    log_quality(quality)

    ok = sum(1 for q in quality if q["status"] in ("success", "partial"))
    return {
        "tickers_requested": len(universe),
        "tickers_skipped_checkpoint": len(skipped),
        "tickers_success": ok + len(skipped),
        "tickers_partial": sum(1 for q in quality if q["status"] == "partial"),
        "tickers_missing": sum(1 for q in quality if q["status"] == "missing"),
        "tickers_error": sum(1 for q in quality if q["status"] == "error"),
        "filings_processed": filings_seen,
        "rows_written": rows_written,
        "elapsed_s": round((datetime.now() - started).total_seconds(), 1),
    }
