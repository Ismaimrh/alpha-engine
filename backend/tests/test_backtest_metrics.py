"""Offline tests for backtest metrics (Step 7.1)."""

import numpy as np
import pandas as pd
import pytest

from app.backtest.metrics import (
    daily_ic,
    decile_spread,
    forward_returns,
    ic_summary,
)

RNG = np.random.default_rng(11)
N_DATES, N_NAMES, H = 60, 50, 5


@pytest.fixture(scope="module")
def close_panel() -> pd.DataFrame:
    """Synthetic closes where a hidden 'alpha' ranks future returns."""
    dates = pd.bdate_range("2026-01-01", periods=N_DATES).date
    companies = [f"co-{i:02d}" for i in range(N_NAMES)]
    alpha = np.linspace(-0.002, 0.002, N_NAMES)  # co-49 drifts up most
    rows = []
    for ci, c in enumerate(companies):
        drift = alpha[ci]
        prices = 100 * np.exp(np.cumsum(RNG.normal(drift, 0.001, N_DATES)))
        rows.extend(
            {"date": d, "company_id": c, "close": p}
            for d, p in zip(dates, prices)
        )
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def fwd(close_panel) -> pd.DataFrame:
    return forward_returns(close_panel, horizon=H)


def _scores(close_panel, sign: float) -> pd.DataFrame:
    """Score = sign * alpha rank (perfectly (anti-)predictive of drift)."""
    companies = sorted(close_panel["company_id"].unique())
    score_map = {c: sign * i for i, c in enumerate(companies)}
    df = close_panel[["date", "company_id"]].copy()
    df["score"] = df["company_id"].map(score_map)
    return df


def test_forward_returns_shape_and_no_lookahead(close_panel, fwd):
    # Last H dates must be absent (no future to measure)
    dates = sorted(close_panel["date"].unique())
    assert max(fwd["date"]) == dates[-H - 1]
    # Spot-check one value against manual computation
    c = "co-25"
    series = close_panel.loc[close_panel["company_id"] == c].sort_values("date")
    manual = series["close"].iloc[H] / series["close"].iloc[0] - 1
    got = fwd.loc[(fwd["company_id"] == c) & (fwd["date"] == dates[0]),
                  "fwd_return"].iloc[0]
    assert got == pytest.approx(manual)


def test_predictive_factor_has_positive_ic(close_panel, fwd):
    ic = daily_ic(_scores(close_panel, +1.0), fwd, "score")
    summary = ic_summary(ic)
    assert summary["mean_ic"] > 0.15
    assert summary["t_stat"] > 2.0
    assert summary["hit_rate"] > 0.7


def test_anti_predictive_factor_has_negative_ic(close_panel, fwd):
    ic = daily_ic(_scores(close_panel, -1.0), fwd, "score")
    assert ic_summary(ic)["mean_ic"] < -0.15


def test_random_factor_ic_near_zero(close_panel, fwd):
    df = close_panel[["date", "company_id"]].copy()
    df["score"] = RNG.normal(size=len(df))
    summary = ic_summary(daily_ic(df, fwd, "score"))
    assert abs(summary["mean_ic"]) < 0.05


def test_decile_spread_positive_for_predictive(close_panel, fwd):
    spread = decile_spread(_scores(close_panel, +1.0), fwd, "score", horizon=H)
    assert spread["mean_spread_ann"] > 0
    assert spread["hit_rate"] > 0.7
    assert spread["n_days"] > 0


def test_small_cross_sections_skipped(fwd, close_panel):
    tiny = _scores(close_panel, +1.0).groupby("date").head(5)  # 5 names/day
    ic = daily_ic(tiny, fwd, "score")
    assert len(ic) == 0  # below MIN_NAMES_PER_DAY everywhere


def test_ic_summary_empty():
    s = ic_summary(pd.Series(dtype=float))
    assert s["n_days"] == 0 and np.isnan(s["mean_ic"])


def test_empty_overlap_factor_returns_empty_not_crash(close_panel, fwd):
    """Regression (valuation in production): scores existing only on dates
    with no forward returns must yield an empty IC series and NaN spread,
    not a TypeError from renaming an empty-groupby DataFrame."""
    last_date = max(close_panel["date"])  # beyond fwd's last date
    lonely = pd.DataFrame({
        "date": [last_date] * 40,
        "company_id": [f"co-{i:02d}" for i in range(40)],
        "score": np.arange(40, dtype=float),
    })
    ic = daily_ic(lonely, fwd, "score")
    assert len(ic) == 0 and ic.name == "ic_score"
    assert ic_summary(ic)["n_days"] == 0
    spread = decile_spread(lonely, fwd, "score")
    assert spread["n_days"] == 0 and np.isnan(spread["mean_spread_ann"])
