"""Unit tests for the momentum factor (co-located per spec structure)."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.factors.momentum.factors import (
    compute_macd_signal,
    compute_momentum_12_1,
    compute_rsi_14,
    momentum_composite,
    momentum_composite_cross_section,
)

AS_OF = date(2025, 12, 31)


def _daily_index(days: int = 420) -> pd.DatetimeIndex:
    return pd.bdate_range(end=pd.Timestamp(AS_OF), periods=days)


def test_momentum_12_1_known_answer():
    # Price doubles linearly over the window: p(t) grows 100 -> 200.
    idx = _daily_index()
    prices = pd.Series(np.linspace(100.0, 200.0, len(idx)), index=idx)
    m = compute_momentum_12_1(prices, AS_OF)
    # start ≈ price 12 months ago, end ≈ price 1 month ago
    start = prices.asof(pd.Timestamp(AS_OF) - pd.DateOffset(months=12))
    end = prices.asof(pd.Timestamp(AS_OF) - pd.DateOffset(months=1))
    assert m == pytest.approx(end / start - 1)
    # linear 100->200 over ~20 months => 12-1 window ≈ (195/140)-1 ≈ 0.39
    assert 0.3 < m < 0.5


def test_momentum_12_1_insufficient_history_is_nan():
    idx = pd.bdate_range(end=pd.Timestamp(AS_OF), periods=100)  # < 12 months
    prices = pd.Series(np.linspace(100, 110, len(idx)), index=idx)
    assert np.isnan(compute_momentum_12_1(prices, AS_OF))


def test_rsi_bounds_and_direction():
    idx = _daily_index(120)
    up = pd.Series(np.linspace(100, 150, len(idx)), index=idx)
    down = pd.Series(np.linspace(150, 100, len(idx)), index=idx)
    rsi_up = compute_rsi_14(up, AS_OF)
    rsi_down = compute_rsi_14(down, AS_OF)
    assert 0 <= rsi_down < 50 < rsi_up <= 100


def test_rsi_insufficient_history_is_nan():
    idx = pd.bdate_range(end=pd.Timestamp(AS_OF), periods=10)
    prices = pd.Series(np.linspace(100, 101, 10), index=idx)
    assert np.isnan(compute_rsi_14(prices, AS_OF))


def test_macd_sign_matches_recent_trend_change():
    """MACD-signal measures momentum CHANGE: test reversals, not steady
    trends (in a constant-rate trend the signal line converges to the MACD
    line and the diff tends to ~0)."""
    idx = _daily_index(150)
    n = len(idx)
    # Flat then rallies over the last 30 sessions -> bullish cross
    turn_up = pd.Series(
        np.concatenate([np.full(n - 30, 100.0), 100 * 1.01 ** np.arange(30)]),
        index=idx,
    )
    # Flat then sells off over the last 30 sessions -> bearish cross
    turn_down = pd.Series(
        np.concatenate([np.full(n - 30, 100.0), 100 * 0.99 ** np.arange(30)]),
        index=idx,
    )
    assert compute_macd_signal(turn_up, AS_OF) > 0
    assert compute_macd_signal(turn_down, AS_OF) < 0


def test_point_in_time_truncation():
    # Data AFTER as_of_date must not affect the signal.
    idx = _daily_index(200)
    prices = pd.Series(np.linspace(100, 130, len(idx)), index=idx)
    mid = idx[120].date()
    extended = prices.copy()
    truncated = prices.loc[: idx[120]]
    assert compute_rsi_14(extended, mid) == pytest.approx(
        compute_rsi_14(truncated, mid)
    )
    assert compute_macd_signal(extended, mid) == pytest.approx(
        compute_macd_signal(truncated, mid)
    )


def test_composite_weights_and_nan_handling():
    assert momentum_composite(1.0, 1.0, 1.0) == pytest.approx(1.0)
    assert momentum_composite(2.0, 0.0, 0.0) == pytest.approx(1.0)  # 0.5*2/1.0
    # NaN leg: weight renormalized over remaining legs
    assert momentum_composite(1.0, np.nan, 1.0) == pytest.approx(1.0)
    assert np.isnan(momentum_composite(np.nan, np.nan, np.nan))


def test_cross_section_zscoring():
    df = pd.DataFrame(
        {
            "momentum_12_1": [0.30, 0.10, -0.10],
            "rsi_14": [70.0, 50.0, 30.0],
            "macd_signal": [2.0, 0.0, -2.0],
        },
        index=["WIN", "MID", "LOSE"],
    )
    comp = momentum_composite_cross_section(df)
    assert comp["WIN"] > comp["MID"] > comp["LOSE"]
    assert comp["MID"] == pytest.approx(0.0, abs=1e-9)  # symmetric universe
