"""Cross-sectional normalization helpers used by the active factors.

Both spec-mandated normalizations live here:
- z-score "across universe on the same date" (momentum composite)
- rank-normalization "across universe" (value/quality composites)

Rank-normalization maps percentile ranks through the inverse normal CDF
(van der Waerden scores), which makes rank-based and z-based composites
directly comparable and robust to outliers. Stdlib only — no scipy.
"""

from __future__ import annotations

from statistics import NormalDist

import numpy as np
import pandas as pd

_NORMAL = NormalDist()


def zscore(values: pd.Series) -> pd.Series:
    """Plain cross-sectional z-score. NaNs stay NaN; zero-variance -> 0."""
    v = values.astype(float)
    std = v.std(ddof=0)
    if not np.isfinite(std) or std == 0:
        return pd.Series(0.0, index=v.index).where(v.notna())
    return (v - v.mean()) / std


def robust_zscore(values: pd.Series) -> pd.Series:
    """Median/MAD z-score (docs/ROBUST_Z_PREREG.md, scheme S-ROBUST).

    (x - median) / (1.4826 * MAD). The 1.4826 constant makes MAD a
    consistent estimator of sigma for Gaussian data, so a +/-1.0 threshold
    keeps the meaning it has under the plain z-score — the scale simply
    stops being hostage to one extreme name.

    Degenerate MAD (>= half the names identical, e.g. a zero-inflated
    signal) falls back to the plain z-score rather than dividing by zero;
    NaNs stay NaN.
    """
    v = values.astype(float)
    med = v.median()
    mad = (v - med).abs().median()
    scale = 1.4826 * mad
    if not np.isfinite(scale) or scale == 0:
        return zscore(v)
    return (v - med) / scale


def rank_normalize(values: pd.Series, higher_is_better: bool = True) -> pd.Series:
    """Map values to N(0,1) scores via percentile ranks (outlier-robust).

    NaNs stay NaN and do not consume rank mass.
    """
    v = values.astype(float)
    if not higher_is_better:
        v = -v
    pct = v.rank(pct=True, method="average")  # NaN-safe: NaN ranks are NaN
    n = v.notna().sum()
    if n == 0:
        return pd.Series(np.nan, index=v.index)
    # shrink from {1/n..1} toward the open interval (0,1) for finite inv_cdf
    shrunk = (pct * n - 0.5) / n
    return shrunk.map(lambda p: _NORMAL.inv_cdf(p) if pd.notna(p) else np.nan)
