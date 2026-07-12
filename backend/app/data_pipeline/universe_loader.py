"""S&P 500 universe loader (spec Step 3).

Flow:
    1. fetch_sp500_from_wikipedia()  -> DataFrame [ticker, name, sector, industry]
    2. save_universe_csv(df)         -> data/universe.csv  (frozen snapshot)
    3. upsert_companies(df)          -> Supabase `companies` table

Spec resolution (agreed with the human): Phase 1 says "hardcode the list,
refresh quarterly from Wikipedia"; Step 3 says "fetch from Wikipedia". We
fetch and cache to data/universe.csv; if Wikipedia is unreachable we fall
back to the cached CSV. Re-run quarterly to refresh.

Ticker normalization: Wikipedia uses dots for share classes (BRK.B, BF.B);
yfinance and most APIs use dashes (BRK-B). We store the dash form as the
canonical ticker everywhere in this project.
"""

from __future__ import annotations

import io
from datetime import date

import pandas as pd
import requests

from app.config import DATA_DIR

WIKIPEDIA_SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
UNIVERSE_CSV = DATA_DIR / "universe.csv"

# Wikipedia blocks generic bots; a descriptive UA is polite and reliable.
_HEADERS = {
    "User-Agent": (
        "AlphaEngineMVP/0.1 (S&P 500 constituent list fetch for research; "
        "contact: see repo)"
    )
}

# Wikipedia column -> our column
_COLUMN_MAP = {
    "Symbol": "ticker",
    "Security": "name",
    "GICS Sector": "sector",
    "GICS Sub-Industry": "industry",
}


def normalize_us_ticker(ticker: str) -> str:
    """US-source ticker canonicalization: uppercase, dots -> dashes.

    US sources (Wikipedia, SEC) write share classes with dots (BRK.B);
    yfinance wants dashes (BRK-B). APPLY ONLY TO US-SOURCED TICKERS:
    European yfinance tickers use dot-suffixes that must be preserved
    (MC.PA, SAP.DE, ASML.AS) — a global dot->dash rule would corrupt them.
    A future EU universe loader (Phase 6) needs its own normalizer.
    """
    return ticker.strip().upper().replace(".", "-")


# Backward-compatible alias (pre-v3.1 name); prefer normalize_us_ticker.
normalize_ticker = normalize_us_ticker


def parse_sp500_html(html: str) -> pd.DataFrame:
    """Parse the Wikipedia S&P 500 constituents table from raw HTML.

    Separated from fetching so it is unit-testable offline with a fixture.
    Returns a DataFrame with columns: ticker, name, sector, industry.
    """
    tables = pd.read_html(io.StringIO(html))
    constituents = None
    for table in tables:
        if {"Symbol", "Security"}.issubset(set(map(str, table.columns))):
            constituents = table
            break
    if constituents is None:
        raise ValueError(
            "Could not find the constituents table (columns Symbol/Security) "
            "in the Wikipedia page — the page layout may have changed."
        )

    df = constituents[list(_COLUMN_MAP)].rename(columns=_COLUMN_MAP).copy()
    df["ticker"] = df["ticker"].map(normalize_ticker)
    df = df.dropna(subset=["ticker", "name"]).drop_duplicates(subset=["ticker"])
    df = df.sort_values("ticker").reset_index(drop=True)

    n = len(df)
    if not 480 <= n <= 520:  # the index holds ~503 tickers (share classes)
        raise ValueError(
            f"Parsed {n} tickers — outside the sanity range [480, 520]. "
            f"Refusing to seed a suspicious universe."
        )
    return df


def fetch_sp500_from_wikipedia(timeout: int = 30) -> pd.DataFrame:
    """Fetch and parse the current S&P 500 constituent list."""
    resp = requests.get(WIKIPEDIA_SP500_URL, headers=_HEADERS, timeout=timeout)
    resp.raise_for_status()
    return parse_sp500_html(resp.text)


def save_universe_csv(df: pd.DataFrame) -> None:
    UNIVERSE_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(UNIVERSE_CSV, index=False)


def load_universe_csv() -> pd.DataFrame:
    if not UNIVERSE_CSV.exists():
        raise FileNotFoundError(
            f"{UNIVERSE_CSV} not found and Wikipedia fetch failed — "
            f"no universe available."
        )
    return pd.read_csv(UNIVERSE_CSV)


def get_universe(refresh: bool = True) -> pd.DataFrame:
    """Return the S&P 500 universe, preferring a fresh Wikipedia fetch.

    Falls back to the cached data/universe.csv if the fetch fails.
    """
    if refresh:
        try:
            df = fetch_sp500_from_wikipedia()
            save_universe_csv(df)
            return df
        except Exception as exc:  # noqa: BLE001 — degrade to cache, loudly
            print(f"WARN: Wikipedia fetch failed ({exc}); using cached CSV.")
    return load_universe_csv()


def upsert_companies(df: pd.DataFrame, batch_size: int = 500) -> int:
    """Upsert the universe into the Supabase `companies` table.

    Idempotent: conflict on the unique `ticker` column updates name/sector/
    industry in place. market_cap stays NULL until the yfinance pipeline
    (Step 5) fills it. Returns the number of rows sent.
    """
    from app.utils.db import supabase  # local import: keep module importable offline

    records = [
        {
            "ticker": row.ticker,
            "name": row.name_,
            "sector": row.sector if pd.notna(row.sector) else None,
            "industry": row.industry if pd.notna(row.industry) else None,
            "in_universe": True,
        }
        for row in df.rename(columns={"name": "name_"}).itertuples(index=False)
    ]
    sent = 0
    for i in range(0, len(records), batch_size):
        chunk = records[i : i + batch_size]
        supabase.table("companies").upsert(chunk, on_conflict="ticker").execute()
        sent += len(chunk)
    return sent


def seed(refresh: bool = True) -> dict:
    """Full Step 3 flow. Returns a summary dict."""
    df = get_universe(refresh=refresh)
    save_universe_csv(df)
    sent = upsert_companies(df)

    from app.utils.db import supabase

    count_resp = (
        supabase.table("companies").select("id", count="exact").limit(1).execute()
    )
    return {
        "date": date.today().isoformat(),
        "tickers_parsed": len(df),
        "rows_upserted": sent,
        "companies_in_db": count_resp.count,
        "csv": str(UNIVERSE_CSV),
    }
