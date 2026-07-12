"""Unit tests for insider + congressional factor (co-located per spec)."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.factors.insider_congressional.factors import (
    congress_buy_signal,
    has_cluster_buy,
    insider_buy_signal,
    smart_money_composite,
)

AS_OF = date(2025, 6, 30)
MCAP = 1e10  # $10B


def _insider_df(rows) -> pd.DataFrame:
    return pd.DataFrame(
        rows,
        columns=[
            "transaction_date",
            "filing_date",
            "insider_name",
            "transaction_code",
            "total_value",
        ],
    )


def test_insider_buys_minus_discounted_sells():
    df = _insider_df(
        [
            ("2025-06-01", "2025-06-03", "CEO", "P", 2_000_000),
            ("2025-06-05", "2025-06-06", "CFO", "S", 1_000_000),
        ]
    )
    sig = insider_buy_signal(df, AS_OF, MCAP)
    assert sig == pytest.approx((2_000_000 - 0.3 * 1_000_000) / MCAP)


def test_point_in_time_filing_gate():
    """THE Gate 1 property: a trade filed after as_of_date is invisible.

    Transaction on 2025-06-20 but filed 2025-07-05 (congress can file up
    to 45 days late) must NOT appear in the 2025-06-30 signal.
    """
    df = _insider_df(
        [
            ("2025-06-20", "2025-07-05", "CEO", "P", 5_000_000),  # filed late
            ("2025-06-10", "2025-06-11", "VP", "P", 1_000_000),  # visible
        ]
    )
    sig = insider_buy_signal(df, AS_OF, MCAP)
    assert sig == pytest.approx(1_000_000 / MCAP)  # only the visible buy


def test_lookback_window_excludes_old_trades():
    df = _insider_df(
        [
            ("2025-01-15", "2025-01-16", "CEO", "P", 9_000_000),  # > 90d old
            ("2025-06-01", "2025-06-02", "CFO", "P", 1_000_000),
        ]
    )
    sig = insider_buy_signal(df, AS_OF, MCAP, lookback_days=90)
    assert sig == pytest.approx(1_000_000 / MCAP)


def test_cluster_doubles_signal():
    base_rows = [
        ("2025-06-01", "2025-06-02", "CEO", "P", 1_000_000),
        ("2025-06-10", "2025-06-11", "CFO", "P", 1_000_000),
    ]
    no_cluster = _insider_df(base_rows)
    cluster = _insider_df(
        base_rows + [("2025-06-20", "2025-06-21", "COO", "P", 1_000_000)]
    )
    assert not has_cluster_buy(no_cluster)
    assert has_cluster_buy(cluster)
    sig_2 = insider_buy_signal(no_cluster, AS_OF, MCAP)
    sig_3 = insider_buy_signal(cluster, AS_OF, MCAP)
    assert sig_3 == pytest.approx(2 * 3_000_000 / MCAP)  # doubled
    assert sig_2 == pytest.approx(2_000_000 / MCAP)  # not doubled


def test_cluster_requires_distinct_insiders_within_window():
    # Same insider buying 3 times is NOT a cluster.
    same = _insider_df(
        [
            ("2025-06-01", "2025-06-02", "CEO", "P", 1_000_000),
            ("2025-06-05", "2025-06-06", "CEO", "P", 1_000_000),
            ("2025-06-09", "2025-06-10", "CEO", "P", 1_000_000),
        ]
    )
    assert not has_cluster_buy(same)
    # 3 distinct insiders but spread > 30 days apart pairwise is NOT a cluster.
    spread = _insider_df(
        [
            ("2025-04-05", "2025-04-06", "CEO", "P", 1_000_000),
            ("2025-05-15", "2025-05-16", "CFO", "P", 1_000_000),
            ("2025-06-25", "2025-06-26", "COO", "P", 1_000_000),
        ]
    )
    assert not has_cluster_buy(spread)


def test_no_activity_is_zero_not_nan():
    empty = _insider_df([])
    assert insider_buy_signal(empty, AS_OF, MCAP) == 0.0


def test_invalid_market_cap_is_nan():
    df = _insider_df([("2025-06-01", "2025-06-02", "CEO", "P", 1_000_000)])
    assert np.isnan(insider_buy_signal(df, AS_OF, np.nan))
    assert np.isnan(insider_buy_signal(df, AS_OF, 0))


def _congress_df(rows) -> pd.DataFrame:
    return pd.DataFrame(
        rows,
        columns=[
            "transaction_date",
            "filing_date",
            "transaction_type",
            "estimated_value",
        ],
    )


def test_congress_signal_and_exchange_ignored():
    df = _congress_df(
        [
            ("2025-06-01", "2025-06-20", "purchase", 500_000),
            ("2025-06-05", "2025-06-25", "sale", 200_000),
            ("2025-06-07", "2025-06-26", "exchange", 900_000),  # ignored
        ]
    )
    sig = congress_buy_signal(df, AS_OF, MCAP)
    assert sig == pytest.approx((500_000 - 0.5 * 200_000) / MCAP)


def test_congress_late_filing_invisible():
    df = _congress_df([("2025-06-01", "2025-07-10", "purchase", 500_000)])
    assert congress_buy_signal(df, AS_OF, MCAP) == 0.0


def test_smart_money_composite():
    assert smart_money_composite(1.0, 1.0) == pytest.approx(1.0)
    assert smart_money_composite(1.0, 0.0) == pytest.approx(0.7)
    assert smart_money_composite(np.nan, 1.0) == pytest.approx(1.0)  # renorm
    assert np.isnan(smart_money_composite(np.nan, np.nan))
