"""Offline tests for fundamentals transformations (Step 5.2)."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.data_pipeline.fundamentals_loader import (
    build_metrics,
    compute_eps_std_3y,
    compute_roic,
    safe_div,
)

AS_OF = date(2026, 7, 8)


def _income_stmt() -> pd.DataFrame:
    """yfinance-shaped annual income statement: rows = items, cols = years
    (newest first)."""
    cols = pd.to_datetime(["2025-12-31", "2024-12-31", "2023-12-31", "2022-12-31"])
    return pd.DataFrame(
        {
            cols[0]: {"Operating Income": 120e9, "Pretax Income": 118e9,
                      "Tax Provision": 20e9, "Net Income": 98e9,
                      "Diluted Average Shares": 15.5e9},
            cols[1]: {"Operating Income": 110e9, "Pretax Income": 109e9,
                      "Tax Provision": 17e9, "Net Income": 92e9,
                      "Diluted Average Shares": 15.8e9},
            cols[2]: {"Operating Income": 100e9, "Pretax Income": 99e9,
                      "Tax Provision": 16e9, "Net Income": 83e9,
                      "Diluted Average Shares": 16.2e9},
            cols[3]: {"Operating Income": 95e9, "Pretax Income": 96e9,
                      "Tax Provision": 15e9, "Net Income": 81e9,
                      "Diluted Average Shares": 16.5e9},
        }
    )


def _balance_sheet() -> pd.DataFrame:
    col = pd.to_datetime(["2025-12-31"])[0]
    return pd.DataFrame({col: {"Total Debt": 100e9, "Stockholders Equity": 80e9}})


def test_safe_div():
    assert safe_div(10, 4) == 2.5
    assert np.isnan(safe_div(10, 0))
    assert np.isnan(safe_div(None, 5))
    assert np.isnan(safe_div("x", 5))


def test_roic_known_answer():
    # tax = 20/118 ≈ 0.1695; roic = 120e9*(1-0.1695)/180e9 ≈ 0.5537
    roic = compute_roic(_income_stmt(), _balance_sheet())
    expected = 120e9 * (1 - 20e9 / 118e9) / 180e9
    assert roic == pytest.approx(expected, rel=1e-9)


def test_roic_missing_frames_is_nan():
    assert np.isnan(compute_roic(None, None))
    assert np.isnan(compute_roic(_income_stmt(), None))


def test_roic_fallback_tax_rate():
    stmt = _income_stmt().drop(index=["Tax Provision"])
    roic = compute_roic(stmt, _balance_sheet())
    assert roic == pytest.approx(120e9 * 0.79 / 180e9, rel=1e-9)


def test_eps_std_3y_known_answer():
    eps = pd.Series(
        [98e9 / 15.5e9, 92e9 / 15.8e9, 83e9 / 16.2e9, 81e9 / 16.5e9]
    )
    assert compute_eps_std_3y(_income_stmt()) == pytest.approx(
        eps.std(ddof=1), rel=1e-9
    )


def test_eps_std_needs_three_years():
    two_years = _income_stmt().iloc[:, :2]
    assert np.isnan(compute_eps_std_3y(two_years))


def test_build_metrics_full_record():
    info = {
        "marketCap": 3.0e12, "trailingPE": 30.0, "forwardPE": 27.0,
        "priceToBook": 12.0, "enterpriseToEbitda": 22.0,
        "freeCashflow": 90e9, "returnOnEquity": 1.2, "grossMargins": 0.45,
        "revenueGrowth": 0.08, "earningsGrowth": 0.10,
        "mostRecentQuarter": 1743379200,  # 2025-03-31 UTC
    }
    rec = build_metrics(info, _income_stmt(), _balance_sheet(), AS_OF)
    assert rec["as_of_date"] == "2026-07-08"
    assert rec["pe_ratio"] == 30.0
    assert rec["fcf_yield"] == pytest.approx(90e9 / 3.0e12)
    assert rec["roic"] == pytest.approx(120e9 * (1 - 20e9 / 118e9) / 180e9)
    assert rec["eps_std_3y"] is not None
    assert rec["_market_cap"] == 3.0e12
    assert rec["filing_date"] is not None and rec["filing_date"].startswith("2025-03")


def test_build_metrics_sparse_info_yields_nones_not_crashes():
    rec = build_metrics({"marketCap": 5e9}, None, None, AS_OF)
    assert rec["pe_ratio"] is None
    assert rec["roic"] is None
    assert rec["eps_std_3y"] is None
    assert rec["fcf_yield"] is None
    assert rec["_market_cap"] == 5e9
