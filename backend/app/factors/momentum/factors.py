"""Factor group 1 — Momentum / Technical (ACTIVE).

Data source: yfinance OHLCV (daily closes). Signals:
    momentum_12_1  — 12-month return skipping the most recent month
                     (Jegadeesh-Titman 1993 skip-month momentum)
    rsi_14         — 14-day Relative Strength Index (0-100)
    macd_signal    — MACD line minus signal line (positive = bullish)

Composite: z-scored cross-sectionally on the same date, then weighted
0.5 / 0.2 / 0.3 per spec.

All functions are pure (Series in, float out) so they are unit-testable
without any data pipeline; DB wiring happens in Step 6.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import ta

from app.factors.cross_section import zscore
from app.factors.factor_base import FactorBase, FactorStatus

# Composite weights per spec
W_M12_1, W_RSI, W_MACD = 0.5, 0.2, 0.3


def _history(prices: pd.Series, as_of_date: date) -> pd.Series:
    """Point-in-time truncation: closes up to and including as_of_date."""
    return prices.loc[: pd.Timestamp(as_of_date)].dropna()


def compute_momentum_12_1(prices: pd.Series, as_of_date: date) -> float:
    """Return from t-12 months to t-1 month, expressed as decimal.

    Skips the most recent month to avoid mean-reversion noise.
    (Implementation verbatim from spec Phase 2.)
    """
    ts = pd.Timestamp(as_of_date)
    end = prices.asof(ts - pd.DateOffset(months=1))
    start = prices.asof(ts - pd.DateOffset(months=12))
    if pd.isna(end) or pd.isna(start) or start <= 0:
        return float(np.nan)
    return float(end / start) - 1.0


def compute_rsi_14(prices: pd.Series, as_of_date: date, period: int = 14) -> float:
    """Relative Strength Index at as_of_date. Range 0-100; NaN if <period+1 obs."""
    hist = _history(prices, as_of_date)
    if len(hist) < period + 1:
        return float(np.nan)
    rsi = ta.momentum.RSIIndicator(hist, window=period).rsi()
    return float(rsi.iloc[-1])


def compute_macd_signal(prices: pd.Series, as_of_date: date) -> float:
    """MACD line minus signal line at as_of_date. Positive = bullish.

    Uses ta defaults (12/26/9); needs ~35 observations to be defined.
    """
    hist = _history(prices, as_of_date)
    if len(hist) < 35:
        return float(np.nan)
    macd = ta.trend.MACD(hist)
    diff = macd.macd().iloc[-1] - macd.macd_signal().iloc[-1]
    return float(diff)


def momentum_composite(m12_1: float, rsi: float, macd: float) -> float:
    """Weighted average of ALREADY-Z-SCORED signal values for one ticker.

    Per spec: weights m12_1=0.5, rsi=0.2, macd=0.3, applied to values that
    were normalized to z-scores across the universe on the same date (see
    momentum_composite_cross_section). NaN inputs contribute 0 with their
    weight removed; returns NaN only if all three are NaN.
    """
    vals = np.array([m12_1, rsi, macd], dtype=float)
    weights = np.array([W_M12_1, W_RSI, W_MACD])
    mask = ~np.isnan(vals)
    if not mask.any():
        return float(np.nan)
    return float((vals[mask] * weights[mask]).sum() / weights[mask].sum())


def momentum_composite_cross_section(signals: pd.DataFrame) -> pd.Series:
    """Composite for the whole universe on one date.

    `signals` columns: momentum_12_1, rsi_14, macd_signal (index = ticker).
    Each column is z-scored cross-sectionally, then weighted per spec.
    """
    z = pd.DataFrame(
        {
            "momentum_12_1": zscore(signals["momentum_12_1"]),
            "rsi_14": zscore(signals["rsi_14"]),
            "macd_signal": zscore(signals["macd_signal"]),
        }
    )
    return z.apply(
        lambda row: momentum_composite(
            row["momentum_12_1"], row["rsi_14"], row["macd_signal"]
        ),
        axis=1,
    )


class MomentumFactor(FactorBase):
    """Registry-facing wrapper for the momentum group."""

    status = FactorStatus.ACTIVE
    name = "momentum"
    category = "price"
    signals = ("momentum_12_1", "rsi_14", "macd_signal")

    def __init__(self, price_provider=None):
        """price_provider(ticker, as_of_date) -> pd.Series of daily closes
        with a DatetimeIndex. Wired to the DB/parquet cache in Step 6."""
        self._prices = price_provider

    def compute(self, ticker: str, as_of_date: date) -> dict:
        if self._prices is None:
            raise RuntimeError(
                "MomentumFactor needs a price_provider — wired in Step 6 "
                "(run_daily_factors.py). The pure functions in this module "
                "are usable directly in the meantime."
            )
        prices = self._prices(ticker, as_of_date)
        return {
            "momentum_12_1": compute_momentum_12_1(prices, as_of_date),
            "rsi_14": compute_rsi_14(prices, as_of_date),
            "macd_signal": compute_macd_signal(prices, as_of_date),
        }
