"""Factor group 2 — Valuation: Value + Quality (ACTIVE).

Data source: yfinance fundamentals. Cross-sectional by construction —
these functions take the whole universe's metrics on one date.

Value composite (rank-normalized, higher = cheaper):
    earnings yield (1/PE), book yield (1/PB), EBITDA yield (1/EV_EBITDA),
    FCF yield
Quality composite (rank-normalized, higher = better):
    ROE, ROIC, gross margin, earnings stability (3Y EPS std dev, inverted)

Combined (Novy-Marx 2013 Quality-Value): 0.5 * value_z + 0.5 * quality_z

Hard universe filters (spec Phase 2): negative ROE, negative FCF,
market cap < $1B. (Spec's 4th bullet — "P/E < 0 and not a recovery case" —
is subsumed by the negative-ROE filter: persistent negative earnings imply
negative ROE; recovery cases with positive ROE but negative trailing P/E
survive, which is the spec's stated intent.)
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from app.factors.cross_section import rank_normalize
from app.factors.factor_base import FactorBase, FactorStatus

MIN_MARKET_CAP = 1_000_000_000  # $1B


def _safe_inverse(values: pd.Series) -> pd.Series:
    """1/x preserving sign and NaN; 0 and inf -> NaN (yield form of a ratio)."""
    v = values.astype(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        inv = 1.0 / v
    return inv.replace([np.inf, -np.inf], np.nan)


def value_composite(metrics: pd.DataFrame) -> pd.Series:
    """Cross-sectional value score. Higher = cheaper.

    Required columns: pe_ratio, pb_ratio, ev_ebitda, fcf_yield.
    Ratios are converted to yields (1/x) before ranking so that ordering is
    monotone-in-cheapness even around negative values; each component is
    rank-normalized and components are averaged (NaN-tolerant).
    """
    components = pd.DataFrame(
        {
            "earnings_yield": rank_normalize(_safe_inverse(metrics["pe_ratio"])),
            "book_yield": rank_normalize(_safe_inverse(metrics["pb_ratio"])),
            "ebitda_yield": rank_normalize(_safe_inverse(metrics["ev_ebitda"])),
            "fcf_yield": rank_normalize(metrics["fcf_yield"]),
        }
    )
    return components.mean(axis=1, skipna=True)


def quality_composite(metrics: pd.DataFrame) -> pd.Series:
    """Cross-sectional quality score. Higher = better business.

    Required columns: roe, roic, gross_margin, eps_std_3y.
    eps_std_3y (3Y std dev of EPS) is inverted: stability is quality.
    """
    components = pd.DataFrame(
        {
            "roe": rank_normalize(metrics["roe"]),
            "roic": rank_normalize(metrics["roic"]),
            "gross_margin": rank_normalize(metrics["gross_margin"]),
            "earnings_stability": rank_normalize(
                metrics["eps_std_3y"], higher_is_better=False
            ),
        }
    )
    return components.mean(axis=1, skipna=True)


def quality_value_composite(value_z: pd.Series, quality_z: pd.Series) -> pd.Series:
    """Combined score per spec: 0.5 * value_z + 0.5 * quality_z."""
    return 0.5 * value_z + 0.5 * quality_z


def universe_filter_mask(metrics: pd.DataFrame) -> pd.Series:
    """True = keep. Applies the spec's hard filters.

    Required columns: roe, fcf_yield (sign proxies FCF sign), market_cap.
    Rows with NaN in a filter column are EXCLUDED (conservative: no data,
    no position).
    """
    roe_ok = metrics["roe"] > 0
    fcf_ok = metrics["fcf_yield"] > 0
    mcap_ok = metrics["market_cap"] >= MIN_MARKET_CAP
    return (roe_ok & fcf_ok & mcap_ok).fillna(False)


class ValuationFactor(FactorBase):
    """Registry-facing wrapper for the valuation group.

    Note: valuation is inherently cross-sectional (ranks across the
    universe), so per-ticker compute() requires a provider that returns the
    universe metrics table for the date; the ticker's row is then read off
    the ranked result. Wired in Step 6.
    """

    status = FactorStatus.ACTIVE
    name = "valuation"
    category = "fundamental"
    signals = ("value_composite", "quality_composite")

    def __init__(self, metrics_provider=None):
        """metrics_provider(as_of_date) -> DataFrame indexed by ticker with
        columns: pe_ratio, pb_ratio, ev_ebitda, fcf_yield, roe, roic,
        gross_margin, eps_std_3y, market_cap."""
        self._metrics = metrics_provider

    def compute(self, ticker: str, as_of_date: date) -> dict:
        if self._metrics is None:
            raise RuntimeError(
                "ValuationFactor needs a metrics_provider — wired in Step 6."
            )
        metrics = self._metrics(as_of_date)
        value = value_composite(metrics)
        quality = quality_composite(metrics)
        return {
            "value_composite": float(value.get(ticker, np.nan)),
            "quality_composite": float(quality.get(ticker, np.nan)),
        }
