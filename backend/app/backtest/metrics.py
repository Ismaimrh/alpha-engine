"""Backtest metrics (spec Step 7 / Phase 3): forward returns, information
coefficients, decile spreads. Pure pandas — no I/O, fully offline-testable.

Definitions:
- forward return (horizon h): close[t+h]/close[t] - 1, computed per company
  on the TRADING-DATE grid (h = trading days). Aligned at t: the score
  known at t is evaluated against the return realized AFTER t — the
  correct, no-lookahead direction.
- IC (information coefficient): per-date cross-sectional Spearman rank
  correlation between factor score and forward return. Spearman (not
  Pearson) because factor scores are rankings by construction and robust
  to outliers.
- ICIR: mean(IC) / std(IC) — signal-to-noise of the IC series.
- t-stat: mean(IC) / (std(IC)/sqrt(n_days)) — significance of mean IC.
- decile spread: mean forward return of top-decile names minus bottom
  decile, per date, annualized by (252/h).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

MIN_NAMES_PER_DAY = 30  # cross-sections smaller than this are skipped


def forward_returns(panel: pd.DataFrame, horizon: int = 21) -> pd.DataFrame:
    """Forward h-trading-day returns from a close panel.

    `panel` columns: date, company_id, close. Returns columns:
    date, company_id, fwd_return. The last h dates have no forward
    return and are dropped.
    """
    wide = panel.pivot(index="date", columns="company_id", values="close")
    wide = wide.sort_index()
    fwd = wide.shift(-horizon) / wide - 1.0
    # pandas 3.0: stack() keeps NaNs (no dropna arg) — drop explicitly so
    # the last `horizon` dates (no future to measure) are truly absent.
    out = fwd.stack().dropna().rename("fwd_return").reset_index()
    return out


def daily_ic(
    scores: pd.DataFrame,
    fwd: pd.DataFrame,
    score_col: str,
    min_names: int = MIN_NAMES_PER_DAY,
) -> pd.Series:
    """Per-date Spearman IC between `score_col` and forward returns.

    `scores` columns: date, company_id, <score_col>; `fwd` columns:
    date, company_id, fwd_return. Dates with fewer than `min_names`
    joint observations are skipped.
    """
    merged = scores[["date", "company_id", score_col]].merge(
        fwd, on=["date", "company_id"], how="inner"
    ).dropna(subset=[score_col, "fwd_return"])
    name = f"ic_{score_col}"
    if merged.empty:
        # e.g. a factor whose scores exist only on dates with no forward
        # returns yet (valuation with snapshot-only fundamentals): pandas'
        # groupby().apply() on an empty frame returns a DataFrame, so
        # return the empty Series explicitly.
        return pd.Series(dtype=float, name=name)

    def _ic(group: pd.DataFrame) -> float:
        if len(group) < min_names:
            return np.nan
        return group[score_col].corr(group["fwd_return"], method="spearman")

    ic = merged.groupby("date").apply(_ic, include_groups=False)
    return ic.dropna().rename(name)


def ic_summary(ic: pd.Series) -> dict:
    """Mean IC, ICIR, t-stat, hit rate, n_days."""
    n = len(ic)
    if n == 0:
        return {"n_days": 0, "mean_ic": np.nan, "icir": np.nan,
                "t_stat": np.nan, "hit_rate": np.nan}
    mean, std = float(ic.mean()), float(ic.std(ddof=1))
    icir = mean / std if std > 0 else np.nan
    t_stat = mean / (std / np.sqrt(n)) if std > 0 else np.nan
    return {
        "n_days": n,
        "mean_ic": round(mean, 4),
        "icir": round(icir, 3),
        "t_stat": round(t_stat, 2),
        "hit_rate": round(float((ic > 0).mean()), 3),
    }


def decile_spread(
    scores: pd.DataFrame,
    fwd: pd.DataFrame,
    score_col: str,
    horizon: int = 21,
    n_deciles: int = 10,
    min_names: int = MIN_NAMES_PER_DAY,
) -> dict:
    """Top-minus-bottom decile forward return, annualized.

    Returns {mean_spread_ann, hit_rate, n_days}.
    """
    merged = scores[["date", "company_id", score_col]].merge(
        fwd, on=["date", "company_id"], how="inner"
    ).dropna(subset=[score_col, "fwd_return"])
    if merged.empty:
        return {"mean_spread_ann": np.nan, "hit_rate": np.nan, "n_days": 0}

    def _spread(group: pd.DataFrame) -> float:
        if len(group) < max(min_names, n_deciles * 2):
            return np.nan
        ranks = pd.qcut(group[score_col].rank(method="first"),
                        n_deciles, labels=False)
        top = group.loc[ranks == n_deciles - 1, "fwd_return"].mean()
        bottom = group.loc[ranks == 0, "fwd_return"].mean()
        return top - bottom

    spreads = merged.groupby("date").apply(_spread, include_groups=False).dropna()
    if spreads.empty:
        return {"mean_spread_ann": np.nan, "hit_rate": np.nan, "n_days": 0}
    ann = float(spreads.mean()) * (252 / horizon)
    return {
        "mean_spread_ann": round(ann, 4),
        "hit_rate": round(float((spreads > 0).mean()), 3),
        "n_days": len(spreads),
    }
