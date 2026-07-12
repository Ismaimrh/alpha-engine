"""Offline tests for the walk-forward backtest engine (Step 7.2)."""

import numpy as np
import pandas as pd
import pytest

from app.backtest.engine import (
    perf_summary,
    run_backtest,
    select_top,
    to_wide_closes,
    turnover,
)

RNG = np.random.default_rng(3)
N_DATES, N_NAMES = 130, 40


@pytest.fixture(scope="module")
def world():
    """Synthetic world where high 'score' names deterministically drift up."""
    dates = list(pd.bdate_range("2026-01-01", periods=N_DATES).date)
    names = [f"co-{i:02d}" for i in range(N_NAMES)]
    drift = np.linspace(-0.003, 0.003, N_NAMES)  # score-aligned drift
    rows, score_rows = [], []
    for ci, c in enumerate(names):
        prices = 100 * np.exp(np.cumsum(np.full(N_DATES, drift[ci])))
        for d, p in zip(dates, prices):
            rows.append({"date": d, "company_id": c, "close": p})
            score_rows.append({"date": d, "company_id": c, "s": float(ci)})
    return (to_wide_closes(pd.DataFrame(rows)), pd.DataFrame(score_rows))


def test_turnover_math():
    assert turnover([], ["a", "b"]) == 1.0            # initial buy-in
    assert turnover(["a", "b"], ["a", "b"]) == 0.0    # unchanged
    assert turnover(["a", "b"], ["a", "c"]) == 0.5    # half replaced
    assert turnover(["a"], []) == 0.0


def test_select_top_excludes_nan():
    s = pd.Series({"a": 3.0, "b": np.nan, "c": 1.0, "d": 2.0})
    assert select_top(s, 2) == ["a", "d"]


def test_strategy_beats_benchmark_in_rigged_world(world):
    closes, scores = world
    result = run_backtest(closes, scores, "s", top_n=10, rebalance_every=21,
                          cost_bps=10)
    strat = perf_summary(result["daily_returns"])
    bench = perf_summary(result["benchmark_returns"])
    assert strat["ann_return"] > bench["ann_return"]  # selection skill shows
    assert strat["sharpe"] > 1.0                      # deterministic drift
    # Static ranking -> zero turnover after the initial buy-in
    assert result["avg_turnover"] < 0.15
    assert result["rebalances"] >= 5


def test_costs_hurt_monotonically(world):
    closes, scores = world
    r_free = run_backtest(closes, scores, "s", top_n=10, cost_bps=0)
    r_cheap = run_backtest(closes, scores, "s", top_n=10, cost_bps=10)
    r_dear = run_backtest(closes, scores, "s", top_n=10, cost_bps=100)
    tot = lambda r: perf_summary(r["daily_returns"])["total_return"]  # noqa: E731
    assert tot(r_free) > tot(r_cheap) > tot(r_dear)


def test_no_lookahead_scores_only_from_rebalance_date(world):
    """Scores on non-rebalance dates are never read: corrupting all of
    them must leave the backtest bit-identical."""
    closes, scores = world
    base = run_backtest(closes, scores, "s", top_n=10)
    reb_dates = {list(closes.index)[i] for i in range(0, len(closes.index), 21)}
    corrupted = scores.copy()
    mask = ~corrupted["date"].isin(reb_dates)
    corrupted.loc[mask, "s"] = RNG.normal(size=int(mask.sum()))
    same = run_backtest(closes, corrupted, "s", top_n=10)
    pd.testing.assert_series_equal(base["daily_returns"], same["daily_returns"])


def test_perf_summary_known_drawdown():
    daily = pd.Series([0.10, -0.50, 0.10])  # peak 1.10 -> trough 0.55
    s = perf_summary(daily)
    assert s["max_drawdown"] == pytest.approx(-0.50)
    assert s["total_return"] == pytest.approx(1.10 * 0.50 * 1.10 - 1)


def test_perf_summary_empty():
    s = perf_summary(pd.Series(dtype=float))
    assert s["n_days"] == 0 and np.isnan(s["sharpe"])
