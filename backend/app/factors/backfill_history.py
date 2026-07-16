"""Historical factor backfill (spec Step 6.2 / Phase 2).

Computes factor_scores for EVERY trading date in the price history
(~504 dates x ~503 names) — the panel that Gate 2's IC analysis and the
Step 7 backtest consume. Reuses assemble_factor_scores per date, so the
daily job and the historical panel share ONE implementation (no
train/serve skew).

Honest data limitations, by factor:
- momentum: full history (price_features covers ~2y). Clean.
- insider:  full history (Form 4 backfill covers the window), filing-date
            gated per date — genuinely point-in-time.
- congress: senate leg history from EFD (filing-date gated).
- valuation: SNAPSHOT-ONLY — yfinance fundamentals cannot be
            reconstructed historically. valuation/quality composites are
            NaN before the first snapshot date and only fill as daily
            snapshots accumulate. Gate 2 IC for valuation will therefore
            be low-powered at first; momentum + insider carry the early
            backtest. (Documented since Step 5.2.)
- market caps: historical mcap approximated as
            mcap_today * close_t / close_today (constant-shares
            approximation) for the insider/congress denominators. Errors
            wash partially in the per-date cross-sectional z-score.

Resumable: dates already present in factor_scores are skipped unless
restart=True.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

from app.factors.compute import LOOKBACK_DAYS, assemble_factor_scores, write_factor_scores
from app.factors.insider_congressional.factors import V2_LOOKBACK_DAYS

# Prefilter window per date: wider than LOOKBACK_DAYS as a safety margin —
# assemble_factor_scores applies the exact point-in-time 90d window itself.
PREFILTER_DAYS = max(LOOKBACK_DAYS, V2_LOOKBACK_DAYS) + 30  # v2 needs 180d
# "Whole table" fetch horizon: 100 years (10**6 days overflows date range).
WHOLE_TABLE_DAYS = 36_500


# ------------------------------------------------------------------ fetching

def _fetch_all(table: str, columns: str, order: str) -> pd.DataFrame:
    """Full-table paginated fetch."""
    from app.utils.db import supabase

    rows, page = [], 0
    while True:
        resp = (
            supabase.table(table)
            .select(columns)
            .order(order)
            .range(page * 1000, page * 1000 + 999)
            .execute()
        )
        rows.extend(resp.data)
        if len(resp.data) < 1000:
            break
        page += 1
    return pd.DataFrame(rows)


def fetch_price_panel() -> pd.DataFrame:
    """date x company panel of momentum signals + close (for mcap approx)."""
    df = _fetch_all(
        "price_features",
        "date,company_id,momentum_12_1,rsi_14,macd_hist,close",
        "id",  # total order: unique key -> stable offset pagination
    )
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df = df.drop_duplicates(subset=["date", "company_id"])
    return df.rename(columns={"macd_hist": "macd_signal"})


def fetch_existing_score_dates() -> set[date]:
    from app.utils.db import supabase

    rows, page = [], 0
    while True:
        resp = (
            supabase.table("factor_scores")
            .select("date")
            .range(page * 1000, page * 1000 + 999)
            .execute()
        )
        rows.extend(resp.data)
        if len(resp.data) < 1000:
            break
        page += 1
    return {date.fromisoformat(r["date"]) for r in rows}


# --------------------------------------------------------------- pure pieces

def approx_historical_mcaps(
    closes_on_date: pd.Series, closes_latest: pd.Series, mcap_latest: pd.Series
) -> pd.Series:
    """mcap_t ≈ mcap_now * close_t / close_now (constant shares)."""
    ratio = closes_on_date / closes_latest
    return (mcap_latest * ratio).replace([np.inf, -np.inf], np.nan)


# ------------------------------------------------------------------ backfill

def backfill_factor_history(restart: bool = False,
                            start: date | None = None) -> dict:
    """Compute factor_scores for all trading dates in price history."""
    from app.factors.compute import (
        fetch_fundamental_metrics,
        fetch_market_caps,
    )
    from app.factors.compute import _fetch_transactions  # full-window variant below

    print("Loading price panel (paginated, ~260 requests) ...", flush=True)
    panel = fetch_price_panel()
    trading_dates = sorted(panel["date"].unique())
    if start:
        trading_dates = [d for d in trading_dates if d >= start]

    existing = set() if restart else fetch_existing_score_dates()
    todo = [d for d in trading_dates if d not in existing]
    print(f"{len(trading_dates)} trading dates, {len(todo)} to compute "
          f"({len(trading_dates) - len(todo)} already present)", flush=True)
    if not todo:
        return {"dates_total": len(trading_dates), "dates_computed": 0,
                "rows_written": 0}

    # One-time fetches
    insider_all = _fetch_transactions(
        "insider_transactions", todo[-1], lookback=WHOLE_TABLE_DAYS
    )
    congress_all = _fetch_transactions(
        "congress_transactions", todo[-1], lookback=WHOLE_TABLE_DAYS
    )
    for df in (insider_all, congress_all):
        if not df.empty:
            df["_filing"] = pd.to_datetime(df["filing_date"]).dt.date
            df["_trans"] = pd.to_datetime(df["transaction_date"]).dt.date
    fundamentals = fetch_fundamental_metrics(todo[-1])
    first_snapshot: date | None = None
    if not fundamentals.empty:
        from app.utils.db import supabase
        resp = (
            supabase.table("fundamental_features")
            .select("as_of_date").order("as_of_date").limit(1).execute()
        )
        first_snapshot = date.fromisoformat(resp.data[0]["as_of_date"])
    mcap_latest = fetch_market_caps()

    latest_date = trading_dates[-1]
    closes_latest = (
        panel.loc[panel["date"] == latest_date]
        .set_index("company_id")["close"].astype(float)
    )
    empty = pd.DataFrame()

    started, rows_written = datetime.now(), 0
    for n, d in enumerate(todo, 1):
        day = panel.loc[panel["date"] == d].set_index("company_id")
        signals = day[["momentum_12_1", "rsi_14", "macd_signal"]].astype(float)
        mcaps = approx_historical_mcaps(
            day["close"].astype(float), closes_latest, mcap_latest
        )
        ins = (
            insider_all.loc[
                (insider_all["_filing"] <= d)
                & (insider_all["_trans"] > d - timedelta(days=PREFILTER_DAYS))
            ]
            if not insider_all.empty else empty
        )
        con = (
            congress_all.loc[
                (congress_all["_filing"] <= d)
                & (congress_all["_trans"] > d - timedelta(days=PREFILTER_DAYS))
            ]
            if not congress_all.empty else empty
        )
        funds = fundamentals if (first_snapshot and d >= first_snapshot) else empty
        scores = assemble_factor_scores(d, signals, funds, mcaps, ins, con)
        rows_written += write_factor_scores(scores, d)
        if n % 20 == 0:
            elapsed = (datetime.now() - started).total_seconds()
            eta_min = (elapsed / n) * (len(todo) - n) / 60
            print(f"  {n}/{len(todo)} dates ({rows_written} rows, "
                  f"ETA ~{eta_min:.0f} min)", flush=True)

    return {
        "dates_total": len(trading_dates),
        "dates_computed": len(todo),
        "rows_written": rows_written,
        "valuation_from": str(first_snapshot),
        "elapsed_s": round((datetime.now() - started).total_seconds(), 1),
    }
