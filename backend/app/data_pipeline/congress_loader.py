"""Congressional trading pipeline (spec Step 5.4 / Phase 1).

Primary free sources (Plan A): the Senate/House Stock Watcher aggregate
JSON dumps (community-maintained mirrors of efdsearch.senate.gov and
disclosures-clerk.house.gov). These have had maintenance gaps historically,
so this loader is deliberately source-agnostic:

    fetch (per-source URL) -> normalize_rows(raw, chamber) -> upsert

and it computes DATA STALENESS on every run: if the newest filing_date in
a source is older than STALE_AFTER_DAYS, the run logs a loud warning and a
'partial' quality row. If a source turns out dead, Plan B is direct
EFD/Clerk scraping (a separate loader behind the same normalize/upsert).

Normalization notes:
- transaction_type: purchase / sale (sale_full+sale_partial collapse) /
  exchange ('exchange' rows carry no direction; the factor ignores them).
- estimated_value: midpoint of the disclosed amount range; lower bound for
  open-ended ranges ("Over $50,000,000").
- Point-in-time: filing_date = disclosure_date (STOCK Act allows up to 45
  days' delay — the factor gates on this, never on transaction_date).
- Dedup: no stable row id exists in the dumps, so row_key = sha1 of the
  normalized identifying fields (migration 005).
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timedelta

import requests

from app.config import RAW_DATA_DIR

SENATE_URL = (
    "https://senate-stock-watcher-data.s3-us-west-2.amazonaws.com"
    "/aggregate/all_transactions.json"
)
HOUSE_URL = (
    "https://house-stock-watcher-data.s3-us-west-2.amazonaws.com"
    "/data/all_transactions.json"
)
CONGRESS_CACHE_DIR = RAW_DATA_DIR / "congress"
STALE_AFTER_DAYS = 60
_AMOUNT_RE = re.compile(r"\$?([\d,]+)")


# --------------------------------------------------------------- primitives

def parse_amount_range(amount: str | None) -> tuple[float | None, str | None]:
    """'$1,001 - $15,000' -> (8000.5, cleaned_range).

    Open-ended ('Over $50,000,000' / '$1,001 -') -> lower bound.
    Unparseable -> (None, original).
    """
    if not amount:
        return None, None
    numbers = [float(m.replace(",", "")) for m in _AMOUNT_RE.findall(amount)]
    if not numbers:
        return None, amount.strip()
    if len(numbers) == 1:
        return numbers[0], amount.strip()
    return (numbers[0] + numbers[1]) / 2, amount.strip()


def normalize_type(raw: str | None) -> str | None:
    """purchase / sale / exchange; None for unrecognized."""
    if not raw:
        return None
    low = raw.lower()
    if "purchase" in low:
        return "purchase"
    if "sale" in low:
        return "sale"
    if "exchange" in low:
        return "exchange"
    return None


def _parse_date(raw: str | None) -> date | None:
    """Handles both 'MM/DD/YYYY' (senate) and 'YYYY-MM-DD' (house)."""
    if not raw:
        return None
    raw = raw.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _normalize_us_ticker(ticker: str) -> str:
    return ticker.strip().upper().replace(".", "-")


def row_key(chamber: str, politician: str, ticker: str, tdate: str,
            ttype: str, amount_range: str | None, fdate: str) -> str:
    """Deterministic dedup key (migration 005)."""
    blob = "|".join([chamber, politician, ticker, tdate, ttype,
                     amount_range or "", fdate])
    return hashlib.sha1(blob.encode()).hexdigest()


def dedupe_row_keys(records: list[dict]) -> list[dict]:
    """Disambiguate records whose content-hash row_keys collide.

    A senator can file two GENUINELY IDENTICAL transactions (same ticker/
    day/type/amount range — e.g. two lots). Postgres rejects an upsert
    batch touching the same key twice ('cannot affect row a second time'),
    so the Nth duplicate gets '#N' folded into its hash. Deterministic
    across re-runs because within-PTR row order is stable (per-PTR cache),
    keeping upserts idempotent. Mutates and returns `records`.
    """
    seen: dict[str, int] = {}
    for r in records:
        key = r["row_key"]
        n = seen.get(key, 0)
        if n:
            r["row_key"] = hashlib.sha1(f"{key}#{n}".encode()).hexdigest()
        seen[key] = n + 1
    return records


# ------------------------------------------------------------ normalization

def normalize_rows(raw_rows: list[dict], chamber: str) -> list[dict]:
    """Stock-Watcher-shaped rows -> congress_transactions records
    (without company_id; keyed by 'ticker' for the caller to map).

    Rows are skipped when: no usable ticker ('--', empty), unrecognized
    type, or unparseable dates. Skips are counted by the caller via the
    length difference.
    """
    politician_field = "senator" if chamber == "Senate" else "representative"
    out = []
    for row in raw_rows:
        ticker = (row.get("ticker") or "").strip()
        if not ticker or ticker in ("--", "N/A"):
            continue
        ttype = normalize_type(row.get("type"))
        if ttype is None:
            continue
        tdate = _parse_date(row.get("transaction_date"))
        fdate = _parse_date(row.get("disclosure_date"))
        if tdate is None or fdate is None:
            continue
        politician = (row.get(politician_field) or "").strip()
        estimated, amount_range = parse_amount_range(row.get("amount"))
        ticker = _normalize_us_ticker(ticker)
        out.append(
            {
                "ticker": ticker,
                "transaction_date": tdate.isoformat(),
                "filing_date": fdate.isoformat(),
                "politician_name": politician,
                "chamber": chamber,
                "party": (row.get("party") or None),
                "transaction_type": ttype,
                "amount_range": amount_range,
                "estimated_value": estimated,
                "source": f"{chamber.lower()}_stock_watcher",
                "row_key": row_key(chamber, politician, ticker,
                                   tdate.isoformat(), ttype, amount_range,
                                   fdate.isoformat()),
            }
        )
    return out


def staleness(rows: list[dict], today: date | None = None) -> tuple[date | None, bool]:
    """(newest_filing_date, is_stale). Stale when newest filing is older
    than STALE_AFTER_DAYS — the loud signal that a source has died."""
    today = today or date.today()
    if not rows:
        return None, True
    newest = max(date.fromisoformat(r["filing_date"]) for r in rows)
    return newest, (today - newest).days > STALE_AFTER_DAYS


# ------------------------------------------------------------------ fetching

def fetch_source(url: str, cache_name: str, timeout: int = 120) -> list[dict]:
    """Download an aggregate dump (they are 10-50MB), cache to data/raw/."""
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    rows = resp.json()
    CONGRESS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CONGRESS_CACHE_DIR / cache_name).write_text(json.dumps(rows))
    return rows


# ------------------------------------------------------------------ backfill

def backfill_congress(years: int = 2) -> dict:
    """Full Step 5.4 flow: both chambers -> congress_transactions."""
    from app.data_pipeline.yfinance_loader import get_ticker_to_id, log_quality
    from app.utils.db import supabase

    mapping = get_ticker_to_id()
    since = date.today() - timedelta(days=int(years * 365.25))

    sources = [
        ("Senate", SENATE_URL, "senate_all_transactions.json"),
        ("House", HOUSE_URL, "house_all_transactions.json"),
    ]
    quality, written, summary_per_source = [], 0, {}
    for chamber, url, cache_name in sources:
        try:
            raw = fetch_source(url, cache_name)
            rows = normalize_rows(raw, chamber)
            newest, stale = staleness(rows)
            in_window = [
                r for r in rows
                if date.fromisoformat(r["transaction_date"]) >= since
            ]
            matched = [r for r in in_window if r["ticker"] in mapping]
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
            written += len(records)
            status = "partial" if stale else "success"
            details = (
                f"{len(raw)} raw, {len(in_window)} in window, "
                f"{len(records)} matched universe; newest filing {newest}"
            )
            if stale:
                details += f" — STALE (> {STALE_AFTER_DAYS}d old), source may be dead"
                print(f"WARN [{chamber}]: {details}")
            quality.append({"ticker": None, "status": status, "details": details})
            summary_per_source[chamber] = {
                "rows_written": len(records), "newest_filing": str(newest),
                "stale": stale,
            }
        except Exception as exc:  # noqa: BLE001
            quality.append(
                {"ticker": None, "status": "error", "details": f"{chamber}: {exc}"[:300]}
            )
            summary_per_source[chamber] = {"error": str(exc)[:120]}
    for q in quality:
        q["source"] = "congress"
    log_quality(quality)

    return {"rows_written": written, **summary_per_source}
