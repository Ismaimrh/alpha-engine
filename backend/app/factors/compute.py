"""Daily factor computation (spec Step 6.1 / Phase 2).

Assembles the three active composites for one as-of date and writes
factor_scores. The assembly itself (assemble_factor_scores) is a PURE
function over DataFrames — offline-testable; the fetch_* functions wrap
Supabase queries.

Column mapping into factor_scores (schema note):
    momentum_composite         — z-weighted momentum per spec (0.5/0.2/0.3)
    valuation_composite        — combined Quality-Value: 0.5*value_z+0.5*quality_z
    quality_composite          — quality leg alone (column exists; filled for
                                 diagnostics/IC analysis)
    insider_congress_composite — smart-money composite (0.7 insider/0.3
                                 congress, renormalized if a leg is absent),
                                 z-scored cross-sectionally

Conventions:
- Names failing the hard universe filters (ROE<=0, FCF<=0, mcap<$1B, or
  missing filter data) get NaN valuation/quality composites: excluded from
  the valuation ranking, NOT from momentum/insider.
- Congress data absent (Gate 1 exception B) -> smart_money renormalizes to
  insider-only automatically; nothing special to configure.
- Point-in-time: price/fundamental rows are selected with date <= as_of;
  transactions are gated on filing_date <= as_of inside the factor
  functions themselves.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from app.factors.cross_section import zscore
from app.factors.insider_congressional.factors import (
    V2_LOOKBACK_DAYS,
    insider_buy_signal_v2,
    congress_buy_signal,
    insider_buy_signal,
    smart_money_composite,
)
from app.factors.momentum.factors import momentum_composite_cross_section
from app.factors.valuation.factors import (
    quality_composite,
    quality_value_composite,
    universe_filter_mask,
    value_composite,
)

LOOKBACK_DAYS = 90  # insider/congress signal window (spec)


# ------------------------------------------------------------------ fetching

def fetch_latest_trading_date(as_of: date) -> date | None:
    """Most recent price_features date <= as_of."""
    from app.utils.db import supabase

    resp = (
        supabase.table("price_features")
        .select("date")
        .lte("date", as_of.isoformat())
        .order("date", desc=True)
        .limit(1)
        .execute()
    )
    return date.fromisoformat(resp.data[0]["date"]) if resp.data else None


def fetch_price_signals(trading_date: date) -> pd.DataFrame:
    """One row per company: momentum_12_1, rsi_14, macd_signal (=hist)."""
    from app.utils.db import supabase

    rows, page = [], 0
    while True:
        resp = (
            supabase.table("price_features")
            .select("company_id,momentum_12_1,rsi_14,macd_hist")
            .eq("date", trading_date.isoformat())
            .order("company_id")
            .range(page * 1000, page * 1000 + 999)
            .execute()
        )
        rows.extend(resp.data)
        if len(resp.data) < 1000:
            break
        page += 1
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(
            columns=["momentum_12_1", "rsi_14", "macd_signal"]
        )
    df = df.rename(columns={"macd_hist": "macd_signal"}).set_index("company_id")
    df = df[~df.index.duplicated(keep="first")]
    return df[["momentum_12_1", "rsi_14", "macd_signal"]].astype(float)


def fetch_fundamental_metrics(as_of: date) -> pd.DataFrame:
    """Latest snapshot (as_of_date <= as_of), one row per company."""
    from app.utils.db import supabase

    latest = (
        supabase.table("fundamental_features")
        .select("as_of_date")
        .lte("as_of_date", as_of.isoformat())
        .order("as_of_date", desc=True)
        .limit(1)
        .execute()
    )
    if not latest.data:
        return pd.DataFrame()
    snap_date = latest.data[0]["as_of_date"]
    rows, page = [], 0
    while True:
        resp = (
            supabase.table("fundamental_features")
            .select(
                "company_id,pe_ratio,pb_ratio,ev_ebitda,fcf_yield,"
                "roe,roic,gross_margin,eps_std_3y"
            )
            .eq("as_of_date", snap_date)
            .order("company_id")
            .range(page * 1000, page * 1000 + 999)
            .execute()
        )
        rows.extend(resp.data)
        if len(resp.data) < 1000:
            break
        page += 1
    df = pd.DataFrame(rows).set_index("company_id").astype(float)
    return df[~df.index.duplicated(keep="first")]


def fetch_market_caps() -> pd.Series:
    from app.utils.db import supabase

    resp = (
        supabase.table("companies")
        .select("id,market_cap")
        .eq("in_universe", True)
        .execute()
    )
    df = pd.DataFrame(resp.data).set_index("id")
    return df["market_cap"].astype(float)


def _fetch_transactions(table: str, as_of: date, lookback: int) -> pd.DataFrame:
    """Window fetch: filing_date <= as_of, transaction_date in lookback."""
    from app.utils.db import supabase

    start = (as_of - timedelta(days=lookback)).isoformat()
    rows, page = [], 0
    while True:
        resp = (
            supabase.table(table)
            .select("*")
            .lte("filing_date", as_of.isoformat())
            .gt("transaction_date", start)
            .order("id")
            .range(page * 1000, page * 1000 + 999)
            .execute()
        )
        rows.extend(resp.data)
        if len(resp.data) < 1000:
            break
        page += 1
    df = pd.DataFrame(rows)
    return df.drop_duplicates(subset=["id"]) if not df.empty else df


# ------------------------------------------------------------ pure assembly

def assemble_factor_scores(
    as_of: date,
    price_signals: pd.DataFrame,
    fundamentals: pd.DataFrame,
    market_caps: pd.Series,
    insider_df: pd.DataFrame,
    congress_df: pd.DataFrame,
) -> pd.DataFrame:
    """Pure cross-sectional assembly. Index: company_id. Columns:
    momentum_composite, valuation_composite, quality_composite,
    insider_congress_composite."""
    # Defensive: duplicated indexes (e.g. from pagination bugs upstream)
    # would make .get() return a Series and corrupt cross-sections.
    market_caps = market_caps[~market_caps.index.duplicated(keep="first")]
    price_signals = price_signals[~price_signals.index.duplicated(keep="first")]
    if not fundamentals.empty:
        fundamentals = fundamentals[~fundamentals.index.duplicated(keep="first")]
    universe = price_signals.index.union(fundamentals.index).union(
        market_caps.index
    )
    out = pd.DataFrame(index=universe)

    # --- Momentum (z-weighted per spec)
    if not price_signals.empty:
        out["momentum_composite"] = momentum_composite_cross_section(
            price_signals.reindex(universe)
        )
    else:
        out["momentum_composite"] = np.nan

    # --- Valuation (hard filters -> NaN outside investable set)
    if not fundamentals.empty:
        metrics = fundamentals.reindex(universe)
        metrics["market_cap"] = market_caps.reindex(universe)
        keep = universe_filter_mask(metrics)
        investable = metrics.loc[keep]
        v = value_composite(investable)
        q = quality_composite(investable)
        out["quality_composite"] = q.reindex(universe)
        out["valuation_composite"] = quality_value_composite(v, q).reindex(universe)
    else:
        out["quality_composite"] = np.nan
        out["valuation_composite"] = np.nan

    # --- Insider + Congress (raw signals per company, then z)
    ins_by_co = (
        dict(tuple(insider_df.groupby("company_id")))
        if not insider_df.empty
        else {}
    )
    con_by_co = (
        dict(tuple(congress_df.groupby("company_id")))
        if not congress_df.empty
        else {}
    )
    empty_ins = pd.DataFrame(
        columns=["transaction_date", "filing_date", "insider_name",
                 "transaction_code", "total_value"]
    )
    empty_con = pd.DataFrame(
        columns=["transaction_date", "filing_date", "transaction_type",
                 "estimated_value"]
    )
    raw = {}
    raw_v2 = {}
    for cid in universe:
        mcap = market_caps.get(cid, np.nan)
        raw_v2[cid] = insider_buy_signal_v2(
            ins_by_co.get(cid, empty_ins), as_of, mcap,
            lookback_days=V2_LOOKBACK_DAYS)
        ins = insider_buy_signal(ins_by_co.get(cid, empty_ins), as_of, mcap,
                                 lookback_days=LOOKBACK_DAYS)
        con = congress_buy_signal(con_by_co.get(cid, empty_con), as_of, mcap,
                                  lookback_days=LOOKBACK_DAYS)
        raw[cid] = smart_money_composite(ins, con)
    out["insider_congress_composite"] = zscore(pd.Series(raw))
    out["insider_v2"] = zscore(pd.Series(raw_v2))  # candidate (Gate 2 pending)

    return out


# -------------------------------------------------------------------- write

def write_factor_scores(scores: pd.DataFrame, score_date: date) -> int:
    from app.utils.db import supabase

    df = scores.reset_index().rename(columns={"index": "company_id"})
    df = df.astype(object).where(pd.notna(df), None)
    records = [
        {"date": score_date.isoformat(), **row} for row in df.to_dict("records")
    ]
    sent = 0
    for i in range(0, len(records), 500):
        supabase.table("factor_scores").upsert(
            records[i : i + 500], on_conflict="company_id,date"
        ).execute()
        sent += len(records[i : i + 500])
    return sent


def run_daily_factors(as_of: date | None = None) -> dict:
    """Step 6.1 entry: compute + write factor_scores for one date."""
    as_of = as_of or date.today()
    trading_date = fetch_latest_trading_date(as_of)
    if trading_date is None:
        raise RuntimeError("no price data at or before as_of — run Step 5.1 first")

    prices = fetch_price_signals(trading_date)
    fundamentals = fetch_fundamental_metrics(as_of)
    mcaps = fetch_market_caps()
    # v2 needs the wider window; v1 re-filters to 90d internally
    insider = _fetch_transactions("insider_transactions", as_of,
                                  max(LOOKBACK_DAYS, V2_LOOKBACK_DAYS))
    congress = _fetch_transactions("congress_transactions", as_of, LOOKBACK_DAYS)

    scores = assemble_factor_scores(
        as_of, prices, fundamentals, mcaps, insider, congress
    )
    written = write_factor_scores(scores, trading_date)
    return {
        "as_of": as_of.isoformat(),
        "trading_date": trading_date.isoformat(),
        "companies_scored": len(scores),
        "momentum_nonnull": int(scores["momentum_composite"].notna().sum()),
        "valuation_nonnull": int(scores["valuation_composite"].notna().sum()),
        "insider_nonnull": int(scores["insider_congress_composite"].notna().sum()),
        "rows_written": written,
        "congress_rows_in_window": len(congress),
    }
