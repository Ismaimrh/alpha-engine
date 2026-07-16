"""Offline tests for daily factor assembly (Step 6.1) — pure function only."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.factors.compute import assemble_factor_scores

AS_OF = date(2026, 7, 9)
IDS = ["co-momo", "co-value", "co-insider", "co-filtered"]


def _price_signals() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "momentum_12_1": [0.40, 0.05, 0.10, -0.05],
            "rsi_14": [72.0, 48.0, 55.0, 41.0],
            "macd_signal": [1.5, 0.1, 0.3, -0.4],
        },
        index=IDS,
    )


def _fundamentals() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "pe_ratio":     [45.0, 9.0, 20.0, 30.0],
            "pb_ratio":     [10.0, 1.1, 3.0, 4.0],
            "ev_ebitda":    [28.0, 6.0, 12.0, 15.0],
            "fcf_yield":    [0.015, 0.08, 0.04, -0.01],  # co-filtered: negative FCF
            "roe":          [0.25, 0.18, 0.15, 0.10],
            "roic":         [0.18, 0.14, 0.11, 0.07],
            "gross_margin": [0.60, 0.40, 0.35, 0.30],
            "eps_std_3y":   [0.5, 0.3, 0.6, 0.9],
        },
        index=IDS,
    )


def _mcaps() -> pd.Series:
    return pd.Series([500e9, 20e9, 10e9, 8e9], index=IDS)


def _insider() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "company_id": ["co-insider"] * 3,
            "transaction_date": ["2026-06-20", "2026-06-25", "2026-07-01"],
            "filing_date": ["2026-06-22", "2026-06-27", "2026-07-02"],
            "insider_name": ["CEO", "CFO", "COO"],  # cluster -> doubled
            "transaction_code": ["P", "P", "P"],
            "total_value": [1e6, 1e6, 1e6],
        }
    )


@pytest.fixture(scope="module")
def scores() -> pd.DataFrame:
    return assemble_factor_scores(
        AS_OF, _price_signals(), _fundamentals(), _mcaps(),
        _insider(), pd.DataFrame(),
    )


def test_shape_and_columns(scores):
    assert sorted(scores.index) == sorted(IDS)
    assert set(scores.columns) == {
        "momentum_composite", "valuation_composite",
        "quality_composite", "insider_congress_composite",
        "insider_v2",  # candidate column (research cycle 1)
    }


def test_momentum_ranks_the_trend_leader(scores):
    assert scores["momentum_composite"].idxmax() == "co-momo"


def test_valuation_ranks_the_cheap_quality_name(scores):
    assert scores["valuation_composite"].idxmax() == "co-value"


def test_hard_filtered_name_excluded_from_valuation_only(scores):
    assert np.isnan(scores.loc["co-filtered", "valuation_composite"])
    assert np.isnan(scores.loc["co-filtered", "quality_composite"])
    # ...but still ranked on momentum and insider
    assert not np.isnan(scores.loc["co-filtered", "momentum_composite"])
    assert not np.isnan(scores.loc["co-filtered", "insider_congress_composite"])


def test_insider_cluster_dominates_composite(scores):
    assert scores["insider_congress_composite"].idxmax() == "co-insider"


def test_no_congress_data_degrades_gracefully(scores):
    # congress_df empty -> composite = insider-only leg, still defined
    assert scores["insider_congress_composite"].notna().all()


def test_zero_activity_names_share_the_same_score(scores):
    quiet = scores.loc[["co-momo", "co-value", "co-filtered"],
                       "insider_congress_composite"]
    assert quiet.nunique() == 1  # all zero-activity -> identical z


def test_point_in_time_late_filing_excluded():
    """A buy filed after as_of must not move the composite."""
    late = _insider().copy()
    late.loc[3] = {
        "company_id": "co-momo", "transaction_date": "2026-07-05",
        "filing_date": "2026-07-15",  # filed AFTER as_of
        "insider_name": "CEO", "transaction_code": "P", "total_value": 5e7,
    }
    with_late = assemble_factor_scores(
        AS_OF, _price_signals(), _fundamentals(), _mcaps(), late, pd.DataFrame()
    )
    base = assemble_factor_scores(
        AS_OF, _price_signals(), _fundamentals(), _mcaps(), _insider(), pd.DataFrame()
    )
    pd.testing.assert_series_equal(
        with_late["insider_congress_composite"],
        base["insider_congress_composite"],
    )


def test_duplicated_mcap_index_does_not_crash():
    """Regression: offset pagination without total ordering produced
    duplicated company_ids; .get() then returned a Series and
    insider_buy_signal crashed on `market_cap <= 0`."""
    dup_mcaps = pd.Series(
        [500e9, 500e9, 20e9, 10e9, 8e9],
        index=["co-momo", "co-momo", "co-value", "co-insider", "co-filtered"],
    )
    dup_prices = pd.concat([_price_signals(), _price_signals().iloc[[0]]])
    result = assemble_factor_scores(
        AS_OF, dup_prices, _fundamentals(), dup_mcaps, _insider(), pd.DataFrame()
    )
    assert result.index.is_unique
    assert result["insider_congress_composite"].notna().all()


# ------------------------------------------------- insider v2 (candidate)

def _v2_txns(rows):
    return pd.DataFrame(rows, columns=["transaction_date", "filing_date",
                                       "insider_name", "transaction_code",
                                       "total_value"])


def test_v2_ignores_sells_entirely():
    from app.factors.insider_congressional.factors import insider_buy_signal_v2

    only_sells = _v2_txns([
        ("2026-06-01", "2026-06-03", "Alice CEO", "S", 50_000_000),
        ("2026-06-10", "2026-06-11", "Bob CFO", "S", 80_000_000),
    ])
    assert insider_buy_signal_v2(only_sells, AS_OF, 10e9) == 0.0

    with_buy = _v2_txns([
        ("2026-06-01", "2026-06-03", "Alice CEO", "S", 50_000_000),
        ("2026-06-10", "2026-06-11", "Bob CFO", "P", 1_000_000),
    ])
    assert insider_buy_signal_v2(with_buy, AS_OF, 10e9) > 0.0


def test_v2_breadth_beats_single_whale():
    from app.factors.insider_congressional.factors import insider_buy_signal_v2

    whale = _v2_txns([("2026-06-01", "2026-06-03", "Alice CEO", "P", 3_000_000)])
    trio = _v2_txns([
        ("2026-06-01", "2026-06-03", "Alice CEO", "P", 1_000_000),
        ("2026-06-05", "2026-06-07", "Bob CFO", "P", 1_000_000),
        ("2026-06-09", "2026-06-11", "Carol COO", "P", 1_000_000),
    ])
    # same total dollars, three distinct buyers > one whale
    assert (insider_buy_signal_v2(trio, AS_OF, 10e9)
            > insider_buy_signal_v2(whale, AS_OF, 10e9))


def test_v2_log_scaling_tames_outliers():
    from app.factors.insider_congressional.factors import insider_buy_signal_v2

    small = _v2_txns([("2026-06-01", "2026-06-03", "A", "P", 1_000_000)])
    huge = _v2_txns([("2026-06-01", "2026-06-03", "A", "P", 100_000_000)])
    s, h = (insider_buy_signal_v2(small, AS_OF, 10e9),
            insider_buy_signal_v2(huge, AS_OF, 10e9))
    assert h > s                      # monotonic
    assert h / s < 100                # but far sublinear (100x $ -> <100x signal)


def test_v2_respects_point_in_time_and_180d_window():
    from app.factors.insider_congressional.factors import insider_buy_signal_v2

    unfiled = _v2_txns([("2026-06-01", "2026-08-01", "A", "P", 1_000_000)])
    assert insider_buy_signal_v2(unfiled, AS_OF, 10e9) == 0.0  # filed in future

    old = _v2_txns([("2025-10-01", "2025-10-03", "A", "P", 1_000_000)])
    recent = _v2_txns([("2026-02-01", "2026-02-03", "A", "P", 1_000_000)])
    assert insider_buy_signal_v2(old, AS_OF, 10e9) == 0.0      # > 180d ago
    assert insider_buy_signal_v2(recent, AS_OF, 10e9) > 0.0    # inside 180d


def test_assemble_emits_insider_v2_column():
    result = assemble_factor_scores(
        AS_OF, _price_signals(), _fundamentals(), _mcaps(), _insider(),
        pd.DataFrame(),
    )
    assert "insider_v2" in result.columns
    assert result["insider_v2"].notna().any()
