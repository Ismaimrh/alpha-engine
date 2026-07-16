"""Factor group 3 — Insider + Congressional Trading (ACTIVE).

Data sources: SEC EDGAR Form 4 (insider) + House/Senate disclosures
(congressional). Signals:

    insider_buy_signal  — (buy$ − 0.3·sell$) / market_cap over lookback,
                          doubled if 3+ distinct insiders buy within any
                          30-day window (cluster detection)
    congress_buy_signal — (buy$ − 0.5·sell$) / market_cap over lookback

Composite: 0.7 · insider + 0.3 · congress (insider is historically the
more reliable signal — Lakonishok-Lee 2001 vs Ziobrowski 2011/2014).

POINT-IN-TIME DISCIPLINE (Gate 1 requirement): a transaction only counts
if its *filing_date* ≤ as_of_date. Congress members have up to 45 days to
file (STOCK Act) and insiders 2 business days; using transaction_date for
visibility would leak future information into backtests.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from app.factors.factor_base import FactorBase, FactorStatus

SELL_DISCOUNT_INSIDER = 0.3
SELL_DISCOUNT_CONGRESS = 0.5
CLUSTER_MIN_INSIDERS = 3
CLUSTER_WINDOW_DAYS = 30
CLUSTER_MULTIPLIER = 2.0
W_INSIDER, W_CONGRESS = 0.7, 0.3


def _point_in_time_window(
    df: pd.DataFrame, as_of_date: date, lookback_days: int
) -> pd.DataFrame:
    """Rows visible on as_of_date with transaction inside the lookback.

    Visibility is gated on filing_date (point-in-time); the signal window
    is defined on transaction_date.
    """
    if df.empty:
        return df
    start = as_of_date - timedelta(days=lookback_days)
    filed = pd.to_datetime(df["filing_date"]).dt.date
    traded = pd.to_datetime(df["transaction_date"]).dt.date
    mask = (filed <= as_of_date) & (traded > start) & (traded <= as_of_date)
    return df.loc[mask]


def has_cluster_buy(
    transactions: pd.DataFrame,
    min_insiders: int = CLUSTER_MIN_INSIDERS,
    window_days: int = CLUSTER_WINDOW_DAYS,
) -> bool:
    """True if >= min_insiders DISTINCT insiders bought within any
    window_days-long window of the given (already point-in-time-filtered)
    transactions."""
    buys = transactions.loc[transactions["transaction_code"] == "P"]
    if buys["insider_name"].nunique() < min_insiders:
        return False
    dates = pd.to_datetime(buys["transaction_date"]).dt.date
    for anchor in dates.unique():
        in_window = (dates >= anchor) & (
            dates <= anchor + timedelta(days=window_days)
        )
        if buys.loc[in_window.values, "insider_name"].nunique() >= min_insiders:
            return True
    return False


def insider_buy_signal(
    transactions: pd.DataFrame,
    as_of_date: date,
    market_cap: float,
    lookback_days: int = 90,
) -> float:
    """Insider signal per spec.

    `transactions` columns (DB schema): transaction_date, filing_date,
    insider_name, transaction_code ('P' buy / 'S' sell), total_value.
    Returns 0.0 when there is simply no activity (absence of trades is
    informative neutrality, not missing data); NaN if market_cap invalid.
    """
    if not np.isfinite(market_cap) or market_cap <= 0:
        return float(np.nan)
    window = _point_in_time_window(transactions, as_of_date, lookback_days)
    if window.empty:
        return 0.0
    buys = window.loc[window["transaction_code"] == "P", "total_value"].sum()
    sells = window.loc[window["transaction_code"] == "S", "total_value"].sum()
    signal = (buys - SELL_DISCOUNT_INSIDER * sells) / market_cap
    if has_cluster_buy(window):
        signal *= CLUSTER_MULTIPLIER
    return float(signal)


def congress_buy_signal(
    transactions: pd.DataFrame,
    as_of_date: date,
    market_cap: float,
    lookback_days: int = 90,
) -> float:
    """Congressional signal per spec (House + Senate combined).

    `transactions` columns (DB schema): transaction_date, filing_date,
    transaction_type ('purchase'/'sale'/'exchange'), estimated_value.
    'exchange' rows are ignored (no directional information).
    """
    if not np.isfinite(market_cap) or market_cap <= 0:
        return float(np.nan)
    window = _point_in_time_window(transactions, as_of_date, lookback_days)
    if window.empty:
        return 0.0
    buys = window.loc[
        window["transaction_type"] == "purchase", "estimated_value"
    ].sum()
    sells = window.loc[window["transaction_type"] == "sale", "estimated_value"].sum()
    return float((buys - SELL_DISCOUNT_CONGRESS * sells) / market_cap)


def smart_money_composite(insider: float, congress: float) -> float:
    """0.7 · insider + 0.3 · congress. A NaN leg contributes 0 with its
    weight removed; NaN only if both legs are NaN."""
    vals = np.array([insider, congress], dtype=float)
    weights = np.array([W_INSIDER, W_CONGRESS])
    mask = ~np.isnan(vals)
    if not mask.any():
        return float(np.nan)
    return float((vals[mask] * weights[mask]).sum() / weights[mask].sum())


class InsiderCongressionalFactor(FactorBase):
    """Registry-facing wrapper for the insider + congressional group."""

    status = FactorStatus.ACTIVE
    name = "insider_congressional"
    category = "alternative"
    signals = ("insider_buy_signal", "congress_buy_signal")

    def __init__(self, transactions_provider=None):
        """transactions_provider(ticker, as_of_date) -> (insider_df,
        congress_df, market_cap). Wired to the DB in Step 6."""
        self._provider = transactions_provider

    def compute(self, ticker: str, as_of_date: date) -> dict:
        if self._provider is None:
            raise RuntimeError(
                "InsiderCongressionalFactor needs a transactions_provider — "
                "wired in Step 6."
            )
        insider_df, congress_df, market_cap = self._provider(ticker, as_of_date)
        return {
            "insider_buy_signal": insider_buy_signal(
                insider_df, as_of_date, market_cap
            ),
            "congress_buy_signal": congress_buy_signal(
                congress_df, as_of_date, market_cap
            ),
        }


# ------------------------------------------------------------- v2 (candidate)

V2_LOOKBACK_DAYS = 180


def insider_buy_signal_v2(
    transactions: pd.DataFrame,
    as_of_date: date,
    market_cap: float,
    lookback_days: int = V2_LOOKBACK_DAYS,
) -> float:
    """CANDIDATE signal (post-Gate-2 rework, 2026-07): purchases only.

    Gate 2 autopsy of v1 (IC -0.0039, t=-0.93): 50k sells drowned 3.5k
    buys; zero-inflation; 21d horizon mismatch. v2, literature-grounded
    (Lakonishok-Lee 2001; Cohen-Malloy-Pomorski 2012):

      - PURCHASES ONLY — sells are mostly comp/diversification noise.
      - log1p(buy$/mcap * 1e4) — log-tames whales; the 1e4 scaling puts
        typical buy intensities into log1p's responsive range.
      - x (1 + distinct_buyers/2) — conviction breadth: three insiders
        buying beats one big buy (continuous, not v1's binary x2).
      - 180d window — insider alpha plays out over months.

    Status: computed as a standalone candidate column; joins nothing until
    it passes Gate 2 IC on its own. Champion and composite are untouched.
    """
    if not np.isfinite(market_cap) or market_cap <= 0:
        return float(np.nan)
    window = _point_in_time_window(transactions, as_of_date, lookback_days)
    buys = window.loc[window["transaction_code"] == "P"]
    if buys.empty:
        return 0.0
    intensity = float(buys["total_value"].sum()) / market_cap
    breadth = 1.0 + buys["insider_name"].nunique() / 2.0
    return float(np.log1p(intensity * 1e4) * breadth)
