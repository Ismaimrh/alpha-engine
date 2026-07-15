"""Offline tests for paper-trading outcome resolution (Step 13)."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.backtest.outcomes import (
    compute_outcomes,
    promotion_verdict,
    realized_ic_by_day,
)

H = 5
DATES = list(pd.bdate_range("2026-06-01", periods=15).date)
NAMES = [f"co-{i:02d}" for i in range(40)]


@pytest.fixture(scope="module")
def closes():
    rows = []
    for ci, c in enumerate(NAMES):
        drift = 0.001 * (ci - 20)  # higher index -> higher drift
        prices = 100 * np.exp(np.cumsum(np.full(len(DATES), drift)))
        rows += [{"date": d, "company_id": c, "close": p}
                 for d, p in zip(DATES, prices)]
    return pd.DataFrame(rows)


def _preds(pdate, model="champ"):
    return pd.DataFrame([
        {"date": pdate, "company_id": c, "model_version": model,
         "alpha_score": float(i), "predicted_return_30d": 0.001 * i}
        for i, c in enumerate(NAMES)
    ])


def test_resolves_only_elapsed_horizons(closes):
    early = _preds(DATES[0])                    # resolves (0 + 5 < 15)
    late = _preds(DATES[-2])                    # cannot resolve yet
    out_early = compute_outcomes(early, closes, horizon=H)
    out_late = compute_outcomes(late, closes, horizon=H)
    assert len(out_early) == len(NAMES)
    assert out_late.empty and list(out_late.columns)  # empty WITH columns
    assert set(out_early["resolved_date"]) == {DATES[H]}


def test_realized_return_math(closes):
    out = compute_outcomes(_preds(DATES[0]), closes, horizon=H)
    row = out.loc[out["company_id"] == "co-30"].iloc[0]
    wide = closes.pivot(index="date", columns="company_id", values="close")
    manual = wide.loc[DATES[H], "co-30"] / wide.loc[DATES[0], "co-30"] - 1
    assert row["realized_return"] == pytest.approx(manual, rel=1e-6)
    # excess returns sum to ~0 across the cross-section (values are
    # stored rounded to 8dp, so allow rounding-scale drift)
    assert out["realized_excess_return"].mean() == pytest.approx(0, abs=1e-7)


def test_realized_ic_positive_when_alpha_ranks_drift(closes):
    out = compute_outcomes(_preds(DATES[0]), closes, horizon=H)
    ic = realized_ic_by_day(out)
    assert len(ic) == 1
    assert ic.iloc[0] > 0.9  # alpha == drift rank in this rigged world


def test_promotion_rule():
    days = pd.bdate_range("2026-01-01", periods=80).date
    champ = pd.Series(0.03, index=days)
    chall_better = pd.Series(0.05, index=days)
    chall_worse = pd.Series(0.01, index=days)

    v = promotion_verdict(champ, chall_better, min_days=60)
    assert v["decision"] == "promote_challenger"
    v2 = promotion_verdict(champ, chall_worse, min_days=60)
    assert v2["decision"] == "keep_champion"
    v3 = promotion_verdict(champ.head(10), chall_better.head(10), min_days=60)
    assert v3["decision"] == "keep_champion"
    assert "insufficient" in v3["reason"]


def test_empty_inputs():
    empty = compute_outcomes(pd.DataFrame(), pd.DataFrame())
    assert empty.empty
    assert realized_ic_by_day(empty).empty
