"""Offline tests for the yfinance pipeline's indicator math (Step 5.1).

No network: synthetic OHLCV in, indicator properties and cross-validation
against the `ta` library out.
"""

from datetime import date

import numpy as np
import pandas as pd
import pytest
import ta

from app.data_pipeline.yfinance_loader import (
    FEATURE_COLUMNS,
    _records,
    compute_price_features,
)


@pytest.fixture(scope="module")
def ohlcv() -> pd.DataFrame:
    """~400 sessions of realistic random-walk OHLCV."""
    rng = np.random.default_rng(7)
    idx = pd.bdate_range(end="2025-12-31", periods=400)
    close = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0004, 0.015, len(idx)))), index=idx)
    return pd.DataFrame(
        {
            "Open": close * (1 + rng.normal(0, 0.003, len(idx))),
            "High": close * (1 + abs(rng.normal(0, 0.006, len(idx)))),
            "Low": close * (1 - abs(rng.normal(0, 0.006, len(idx)))),
            "Close": close,
            "Volume": rng.integers(1e6, 5e7, len(idx)),
        }
    )


@pytest.fixture(scope="module")
def features(ohlcv) -> pd.DataFrame:
    return compute_price_features(ohlcv)


def test_schema_columns_exact(features):
    assert list(features.columns) == FEATURE_COLUMNS


def test_rsi_matches_ta_library(ohlcv, features):
    """Our pipeline RSI must match ta.momentum.RSIIndicator."""
    expected = ta.momentum.RSIIndicator(ohlcv["Close"], window=14).rsi()
    got = features["rsi_14"]
    got.index = ohlcv.index  # align (features index is date objects)
    both = pd.DataFrame({"ta": expected, "ours": got}).dropna()
    assert len(both) > 350
    assert np.allclose(both["ta"], both["ours"], atol=1e-8)


def test_macd_matches_ta_library(ohlcv, features):
    macd_ta = ta.trend.MACD(ohlcv["Close"])
    for ours_col, theirs in (
        ("macd", macd_ta.macd()),
        ("macd_signal", macd_ta.macd_signal()),
        ("macd_hist", macd_ta.macd_diff()),
    ):
        got = features[ours_col]
        got.index = ohlcv.index
        both = pd.DataFrame({"ta": theirs, "ours": got}).dropna()
        assert len(both) > 300, ours_col
        assert np.allclose(both["ta"], both["ours"], atol=1e-8), ours_col


def test_sma_known_answer(ohlcv, features):
    manual = ohlcv["Close"].rolling(20).mean()
    got = features["sma_20"]
    got.index = ohlcv.index
    both = pd.DataFrame({"m": manual, "g": got}).dropna()
    assert np.allclose(both["m"], both["g"])


def test_momentum_12_1_shift_convention(ohlcv, features):
    close = ohlcv["Close"]
    expected = close.shift(21) / close.shift(252) - 1
    got = features["momentum_12_1"]
    got.index = ohlcv.index
    both = pd.DataFrame({"e": expected, "g": got}).dropna()
    assert len(both) == len(close) - 252
    assert np.allclose(both["e"], both["g"])


def test_realized_vol_positive_and_annualized(ohlcv, features):
    vol = features["realized_vol_30d"].dropna()
    assert (vol > 0).all()
    # Generator daily sigma 0.015 -> annualized ≈ 0.238; loose sanity band
    assert 0.1 < vol.median() < 0.5


def test_warmup_rows_are_nan(features):
    assert np.isnan(features["sma_200"].iloc[100])
    assert np.isnan(features["momentum_12_1"].iloc[200])
    assert not np.isnan(features["sma_200"].iloc[-1])
    assert not np.isnan(features["momentum_12_1"].iloc[-1])


def test_point_in_time_no_lookahead(ohlcv):
    """Truncating the future must not change past feature values."""
    full = compute_price_features(ohlcv)
    truncated = compute_price_features(ohlcv.iloc[:300])
    check_day = truncated.index[-1]
    pd.testing.assert_series_equal(
        full.loc[check_day], truncated.loc[check_day], check_names=False
    )


def test_records_nan_to_none_and_types(features):
    records = _records("uuid-123", features)
    assert len(records) == len(features)
    first, last = records[0], records[-1]
    assert first["company_id"] == "uuid-123"
    assert isinstance(first["date"], str) and first["date"] == str(features.index[0])
    assert first["sma_200"] is None            # warm-up -> NULL
    assert isinstance(last["sma_200"], float)  # filled at the end
    assert isinstance(last["volume"], int)     # JSON-safe int, not np/Int64
