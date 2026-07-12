"""Offline tests for the purged walk-forward ensemble (Step 8.1)."""

import numpy as np
import pandas as pd
import pytest

from app.ml.train import (
    EMBARGO,
    FEATURES,
    HORIZON,
    build_dataset,
    feature_importances,
    train_final_model,
    walk_forward_predict,
)

RNG = np.random.default_rng(21)
N_DATES, N_NAMES = 320, 60


@pytest.fixture(scope="module")
def world():
    """Synthetic panel: a persistent per-company signal nonlinearly drives
    the company's drift; momentum_composite observes that signal (noisily).
    Other features are pure noise."""
    dates = list(pd.bdate_range("2025-01-01", periods=N_DATES).date)
    names = [f"co-{i:02d}" for i in range(N_NAMES)]
    feat_rows, price_rows = [], []
    for c in names:
        sig = float(RNG.normal())                  # persistent company alpha
        drift = 0.002 * np.tanh(2 * sig)           # nonlinear link
        prices = 100 * np.exp(np.cumsum(RNG.normal(drift, 0.002, N_DATES)))
        for i, d in enumerate(dates):
            price_rows.append({"date": d, "company_id": c, "close": prices[i]})
            feat_rows.append({
                "date": d, "company_id": c,
                "momentum_composite": sig + float(RNG.normal(0, 0.1)),
                "rsi_14": float(RNG.normal()),
                "macd_signal": float(RNG.normal()),
                "momentum_12_1": float(RNG.normal()),
                "valuation_composite": np.nan,     # like production
                "insider_congress_composite": float(RNG.normal()),
            })
    return pd.DataFrame(feat_rows), pd.DataFrame(price_rows)


@pytest.fixture(scope="module")
def dataset(world):
    features, closes = world
    return build_dataset(features, closes)


def test_dataset_shape_and_target(dataset):
    assert set(FEATURES).issubset(dataset.columns)
    assert "target" in dataset.columns
    # excess returns: cross-sectional mean ~0 each day
    daily_mean = dataset.groupby("date")["target"].mean()
    assert daily_mean.abs().max() < 1e-10
    # last HORIZON dates have no target rows
    assert dataset["date"].nunique() == N_DATES - HORIZON


def test_walk_forward_purge_is_respected(dataset):
    oos, folds = walk_forward_predict(dataset, min_train_days=100,
                                      retrain_every=42)
    assert len(folds) >= 2
    for fold in folds:
        assert fold["train_max_date"] < fold["test_start"]
        assert fold["purge_gap_days"] >= HORIZON + EMBARGO
    # OOS predictions cover only test dates, never train dates
    assert not oos.empty
    first_fold = folds[0]
    assert oos["date"].min() >= first_fold["test_start"]


def test_ensemble_learns_the_nonlinear_signal(dataset):
    oos, _ = walk_forward_predict(dataset, min_train_days=100,
                                  retrain_every=42)
    merged = oos.merge(dataset[["date", "company_id", "target"]],
                       on=["date", "company_id"])
    ic = merged.groupby("date").apply(
        lambda g: g["prediction"].corr(g["target"], method="spearman"),
        include_groups=False,
    ).dropna()
    assert ic.mean() > 0.05  # clearly positive OOS IC on rigged data


def test_final_model_importances_find_the_true_driver(dataset):
    model = train_final_model(dataset)
    imp = feature_importances(model)
    assert max(imp, key=imp.get) == "momentum_composite"
    assert imp["valuation_composite"] == 0.0  # all-NaN feature unused
    assert abs(sum(imp.values()) - 1.0) < 0.01


def test_all_nan_feature_column_tolerated(dataset):
    # valuation_composite is entirely NaN in the fixture — must not crash
    oos, folds = walk_forward_predict(dataset, min_train_days=100,
                                      retrain_every=84)
    assert not oos.empty and folds
