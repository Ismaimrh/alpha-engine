"""yfinance fundamentals pipeline (spec Step 5.2 / Phase 1).

Fills fundamental_features (one snapshot row per company per as_of_date)
and refreshes companies.market_cap.

POINT-IN-TIME REALITY (documented MVP limitation): yfinance `.info` is a
CURRENT snapshot — historical ratio series cannot be reconstructed from it.
So as_of_date = run date, and history accumulates as the daily pipeline
runs. Consequence for Gate 2/3: the valuation factor's backtestable history
starts when snapshots start; the momentum factor carries early backtests.
This is the standard $0-budget tradeoff and is logged here explicitly.

Derived metrics (not directly in .info):
- roic       = EBIT * (1 - effective tax rate) / (total debt + equity),
               from the annual income statement + balance sheet
- eps_std_3y = std dev of the last 3-4 annual EPS values
               (net income / shares outstanding), for the quality composite
- fcf_yield  = freeCashflow / marketCap

Pure transformation functions are separated from fetching so they are
unit-testable offline with synthetic statement frames.
"""

from __future__ import annotations

import time
from datetime import date, datetime

import numpy as np
import pandas as pd
import yfinance as yf

PAUSE_SECONDS = 0.4  # per-ticker politeness
MAX_RETRIES = 2


# ------------------------------------------------------- pure transformations

def safe_div(num, den) -> float:
    """num/den with None/NaN/0-denominator -> NaN."""
    try:
        num = float(num)
        den = float(den)
    except (TypeError, ValueError):
        return float(np.nan)
    if not np.isfinite(num) or not np.isfinite(den) or den == 0:
        return float(np.nan)
    return num / den


def _stmt_value(frame: pd.DataFrame | None, row: str, col_idx: int = 0) -> float:
    """Read frame.loc[row].iloc[col_idx] defensively (yfinance statements
    are row-labeled, newest column first). NaN if absent."""
    if frame is None or frame.empty or row not in frame.index:
        return float(np.nan)
    try:
        return float(frame.loc[row].iloc[col_idx])
    except (IndexError, TypeError, ValueError):
        return float(np.nan)


def compute_roic(income_stmt: pd.DataFrame | None, balance_sheet: pd.DataFrame | None) -> float:
    """ROIC = EBIT * (1 - effective tax rate) / (total debt + equity).

    Effective tax rate = Tax Provision / Pretax Income, clipped to [0, 0.5];
    falls back to 21% if unavailable. NaN if EBIT or invested capital missing.
    """
    ebit = _stmt_value(income_stmt, "Operating Income")
    if np.isnan(ebit):
        ebit = _stmt_value(income_stmt, "EBIT")
    tax = safe_div(
        _stmt_value(income_stmt, "Tax Provision"),
        _stmt_value(income_stmt, "Pretax Income"),
    )
    tax = 0.21 if np.isnan(tax) else float(np.clip(tax, 0.0, 0.5))
    debt = _stmt_value(balance_sheet, "Total Debt")
    equity = _stmt_value(balance_sheet, "Stockholders Equity")
    if np.isnan(equity):
        equity = _stmt_value(balance_sheet, "Common Stock Equity")
    debt = 0.0 if np.isnan(debt) else debt
    invested = debt + equity
    if np.isnan(ebit) or np.isnan(invested) or invested <= 0:
        return float(np.nan)
    return ebit * (1 - tax) / invested


def compute_eps_std_3y(income_stmt: pd.DataFrame | None) -> float:
    """Std dev of the last up-to-4 annual EPS values (>=3 required).

    EPS_year = Net Income / Diluted Average Shares (per year column).
    """
    if income_stmt is None or income_stmt.empty:
        return float(np.nan)
    ni_row = "Net Income"
    sh_row = "Diluted Average Shares"
    if ni_row not in income_stmt.index or sh_row not in income_stmt.index:
        return float(np.nan)
    ni = pd.to_numeric(income_stmt.loc[ni_row], errors="coerce")
    sh = pd.to_numeric(income_stmt.loc[sh_row], errors="coerce")
    eps = (ni / sh).dropna()
    if len(eps) < 3:
        return float(np.nan)
    return float(eps.iloc[:4].std(ddof=1))


def build_metrics(
    info: dict,
    income_stmt: pd.DataFrame | None,
    balance_sheet: pd.DataFrame | None,
    as_of: date,
) -> dict:
    """Assemble one fundamental_features record (without company_id)."""
    mcap = info.get("marketCap")
    filing_ts = info.get("mostRecentQuarter")
    filing_date = (
        datetime.fromtimestamp(filing_ts).date().isoformat()
        if isinstance(filing_ts, (int, float)) and filing_ts > 0
        else None
    )

    def _f(key) -> float | None:
        v = info.get(key)
        try:
            v = float(v)
            return v if np.isfinite(v) else None
        except (TypeError, ValueError):
            return None

    def _nan_to_none(v: float) -> float | None:
        return None if v is None or (isinstance(v, float) and np.isnan(v)) else v

    return {
        "as_of_date": as_of.isoformat(),
        "filing_date": filing_date,
        "pe_ratio": _f("trailingPE"),
        "forward_pe": _f("forwardPE"),
        "pb_ratio": _f("priceToBook"),
        "ev_ebitda": _f("enterpriseToEbitda"),
        "fcf_yield": _nan_to_none(safe_div(info.get("freeCashflow"), mcap)),
        "roe": _f("returnOnEquity"),
        "roic": _nan_to_none(compute_roic(income_stmt, balance_sheet)),
        "gross_margin": _f("grossMargins"),
        "revenue_growth_yoy": _f("revenueGrowth"),
        "eps_growth_yoy": _f("earningsGrowth"),
        "eps_std_3y": _nan_to_none(compute_eps_std_3y(income_stmt)),
        "_market_cap": _f("marketCap"),  # side-channel for companies table
    }


# ------------------------------------------------------------------ fetching

def fetch_ticker_fundamentals(ticker: str, as_of: date) -> dict | None:
    """Fetch one ticker's snapshot; None if info is empty/unusable."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            t = yf.Ticker(ticker)
            info = t.info or {}
            if not info.get("marketCap") and not info.get("trailingPE"):
                return None
            try:
                income = t.income_stmt
            except Exception:  # noqa: BLE001
                income = None
            try:
                balance = t.balance_sheet
            except Exception:  # noqa: BLE001
                balance = None
            return build_metrics(info, income, balance, as_of)
        except Exception:  # noqa: BLE001
            if attempt == MAX_RETRIES:
                raise
            time.sleep(2**attempt)
    return None


# -------------------------------------------------------------------- writes

def backfill_fundamentals(tickers: list[str] | None = None) -> dict:
    """Full Step 5.2 flow: snapshot every universe ticker into
    fundamental_features and refresh companies.market_cap."""
    from app.data_pipeline.yfinance_loader import get_ticker_to_id, log_quality
    from app.utils.db import supabase

    mapping = get_ticker_to_id()
    universe = tickers if tickers is not None else sorted(mapping)
    universe = [t for t in universe if t in mapping]
    as_of = date.today()

    quality, written = [], 0
    started = datetime.now()
    print(f"Fundamentals snapshot for {len(universe)} tickers, as_of {as_of} ...")
    for n, ticker in enumerate(universe, 1):
        try:
            metrics = fetch_ticker_fundamentals(ticker, as_of)
            if metrics is None:
                quality.append(
                    {"ticker": ticker, "status": "missing",
                     "details": "empty info snapshot"}
                )
                continue
            mcap = metrics.pop("_market_cap")
            record = {"company_id": mapping[ticker], **metrics}
            supabase.table("fundamental_features").upsert(
                record, on_conflict="company_id,as_of_date"
            ).execute()
            if mcap:
                supabase.table("companies").update({"market_cap": mcap}).eq(
                    "id", mapping[ticker]
                ).execute()
            written += 1
            filled = sum(v is not None for v in record.values())
            quality.append(
                {"ticker": ticker, "status": "success",
                 "details": f"{filled}/{len(record)} fields"}
            )
        except Exception as exc:  # noqa: BLE001
            quality.append(
                {"ticker": ticker, "status": "error", "details": str(exc)[:300]}
            )
        if n % 50 == 0:
            print(f"  {n}/{len(universe)} done ({written} written)")
        time.sleep(PAUSE_SECONDS)

    for q in quality:
        q["source"] = "yfinance_fundamentals"  # overrides log_quality default
    log_quality(quality)

    ok = sum(1 for q in quality if q["status"] == "success")
    return {
        "tickers_requested": len(universe),
        "tickers_success": ok,
        "tickers_missing": sum(1 for q in quality if q["status"] == "missing"),
        "tickers_error": sum(1 for q in quality if q["status"] == "error"),
        "rows_written": written,
        "elapsed_s": round((datetime.now() - started).total_seconds(), 1),
    }
