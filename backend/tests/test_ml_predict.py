"""Offline tests for champion/challenger prediction building (Step 8.2)."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.ml.predict import (
    CHAMPION_VERSION,
    build_prediction_rows,
    calibrate_slope,
    position_sizes,
    rank_confidence,
)

D = date(2026, 7, 8)


def test_calibrate_slope_recovers_linear_relation():
    rng = np.random.default_rng(5)
    x = rng.normal(size=5000)
    df = pd.DataFrame({"momentum_composite": x,
                       "target": 0.01 * x + rng.normal(0, 0.001, 5000)})
    assert calibrate_slope(df) == pytest.approx(0.01, rel=0.05)
    assert calibrate_slope(df.head(10)) == 0.0  # too little data -> neutral


def test_rank_confidence_extremes_highest():
    s = pd.Series({"big+": 3.0, "big-": -2.9, "mid": 0.5, "tiny": 0.01,
                   "gone": np.nan})
    c = rank_confidence(s)
    assert c["big+"] > c["mid"] > c["tiny"] >= 0.5
    assert c["big-"] > c["mid"]          # extremeness, not direction
    assert np.isnan(c["gone"])
    assert c.max() <= 0.99


def test_position_sizes_top_n_book():
    alpha = pd.Series({f"c{i}": float(i) for i in range(10)})
    pos = position_sizes(alpha, top_n=3)
    assert pos["c9"] == pos["c8"] == pos["c7"] == pytest.approx(1 / 3)
    assert pos["c0"] == 0.0
    assert pos.sum() == pytest.approx(1.0)


def test_build_rows_shape_and_nan_skipping():
    alpha = pd.Series({"a": 1.5, "b": -0.5, "c": np.nan})
    pred = pd.Series({"a": 0.02, "b": -0.01, "c": 0.0})
    rows = build_prediction_rows(D, alpha, pred, CHAMPION_VERSION, top_n=1)
    assert len(rows) == 2                      # NaN alpha skipped
    by_id = {r["company_id"]: r for r in rows}
    assert by_id["a"]["position_size"] == 1.0  # top-1 book
    assert by_id["b"]["position_size"] == 0.0
    assert by_id["a"]["model_version"] == CHAMPION_VERSION
    assert by_id["a"]["date"] == "2026-07-08"
    assert by_id["a"]["predicted_return_30d"] == 0.02


def test_sector_candidate_version_distinct():
    from app.ml.predict import (CHAMPION_VERSION, SECTOR_CANDIDATE_VERSION)
    from app.ml.train import MODEL_VERSION as CHALLENGER_VERSION

    versions = {CHAMPION_VERSION, SECTOR_CANDIDATE_VERSION, CHALLENGER_VERSION}
    assert len(versions) == 3  # three distinct tracked models


def test_calibrate_slope_works_on_alternate_score_col():
    rng = np.random.default_rng(9)
    x = rng.normal(size=3000)
    df = pd.DataFrame({"momentum_sector_rel": x,
                       "target": 0.008 * x + rng.normal(0, 0.001, 3000)})
    assert calibrate_slope(df, score_col="momentum_sector_rel") == pytest.approx(
        0.008, rel=0.05)
