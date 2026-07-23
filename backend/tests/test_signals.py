"""Offline tests for the Signal Phase S1 core (spec D1-D4)."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.signals.cards import (
    AVOID_THRESHOLD,
    BUY_THRESHOLD,
    HORIZON_DAYS,
    STOP_K,
    TARGET_K,
    build_cards,
    sigma_21_from_daily_vol,
)
from app.signals.resolve import resolve_card_path, wilson_ci

ISSUE = date(2026, 7, 17)
EXPIRES = date(2026, 8, 17)


def _inputs():
    alpha = pd.Series({"hi": 2.5, "mid": 0.3, "lo": -1.8, "nan": np.nan,
                       "novol": 3.0})
    closes = pd.Series({"hi": 100.0, "mid": 50.0, "lo": 80.0, "nan": 10.0,
                        "novol": 20.0})
    vol = pd.Series({"hi": 0.02, "mid": 0.01, "lo": 0.015,
                     "novol": np.nan})
    tickers = pd.Series({"hi": "HI", "mid": "MID", "lo": "LO",
                         "nan": "NAN", "novol": "NV"})
    return alpha, closes, vol, tickers


def test_d1_selection_and_d2_envelope():
    alpha, closes, vol, tickers = _inputs()
    cards = build_cards(ISSUE, alpha, closes, vol, tickers, EXPIRES, "champ")
    by = {c["ticker"]: c for c in cards}
    assert set(by) == {"HI", "LO"}          # mid below threshold; nan/novol skipped
    hi = by["HI"]
    assert hi["direction"] == "BUY"
    s21 = sigma_21_from_daily_vol(0.02)
    assert hi["target"] == pytest.approx(100 * (1 + TARGET_K * s21), rel=1e-6)
    assert hi["stop"] == pytest.approx(100 * (1 - STOP_K * s21), rel=1e-6)
    assert by["LO"]["direction"] == "AVOID"
    # thresholds are the registered constants
    assert BUY_THRESHOLD == 1.0 and AVOID_THRESHOLD == -1.0


def _path(vals, start="2026-07-20"):
    idx = list(pd.bdate_range(start, periods=len(vals)).date)
    return pd.Series(vals, index=idx, dtype=float)


def test_d3_buy_hit_before_stop():
    out = resolve_card_path("BUY", 100, 110, 95,
                            _path([102, 111, 94]), HORIZON_DAYS)
    assert out["status"] == "hit"
    assert out["realized_return"] == pytest.approx(0.11, rel=1e-6)


def test_d3_buy_stop_first_even_if_hit_later():
    out = resolve_card_path("BUY", 100, 110, 95,
                            _path([94, 120]), HORIZON_DAYS)
    assert out["status"] == "stop"
    assert out["realized_return"] == pytest.approx(-0.06, rel=1e-6)


def test_d3_avoid_mirrors_envelope():
    # AVOID: entry 100, buy-frame target 110/stop 95 -> falls to 90 = HIT
    out = resolve_card_path("AVOID", 100, 110, 95,
                            _path([98, 90]), HORIZON_DAYS)
    assert out["status"] == "hit"
    assert out["realized_return"] == pytest.approx(0.10, rel=1e-6)  # profit on fall
    # rises to 105 (= entry + (entry-stop)) = STOP for an AVOID
    out2 = resolve_card_path("AVOID", 100, 110, 95,
                             _path([101, 105]), HORIZON_DAYS)
    assert out2["status"] == "stop"
    assert out2["realized_return"] == pytest.approx(-0.05, rel=1e-6)


def test_d3_expiry_and_still_open():
    flat = [100.5] * HORIZON_DAYS
    out = resolve_card_path("BUY", 100, 110, 95, _path(flat), HORIZON_DAYS)
    assert out["status"] == "expired"
    assert out["realized_return"] == pytest.approx(0.005, rel=1e-4)
    still = resolve_card_path("BUY", 100, 110, 95, _path([101, 102]),
                              HORIZON_DAYS)
    assert still is None  # no event, horizon not elapsed -> stays open


def test_d4_wilson_ci():
    lo, hi = wilson_ci(18, 30)
    assert 0.40 < lo < 0.60 < hi < 0.78    # 60% on n=30: wide, honest
    assert wilson_ci(0, 0) == (0.0, 0.0)
    lo_big, hi_big = wilson_ci(600, 1000)
    assert hi_big - lo_big < 0.07          # tightens with N


def test_d3d_terminated_series_resolves_at_last_close():
    # bankruptcy-style slide: hits the stop on the way down (event wins)
    slide = _path([90, 60, 20])
    out = resolve_card_path("BUY", 100, 110, 95, slide, HORIZON_DAYS,
                            series_terminated=True)
    assert out["status"] == "stop"
    # terminated flat path, no event: expired at last available close
    stub = _path([101, 102])
    out2 = resolve_card_path("BUY", 100, 110, 95, stub, HORIZON_DAYS,
                             series_terminated=True)
    assert out2["status"] == "expired"
    assert out2["realized_return"] == pytest.approx(0.02, rel=1e-6)
    # same stub NOT terminated: stays open (regression guard)
    assert resolve_card_path("BUY", 100, 110, 95, stub, HORIZON_DAYS) is None


def test_63d_envelope_wider_than_21d():
    """S2: same name, same vol — the 63d envelope must be sqrt(3)x wider."""
    alpha = pd.Series({"hi": 2.5})
    closes = pd.Series({"hi": 100.0})
    vol = pd.Series({"hi": 0.02})
    tickers = pd.Series({"hi": "HI"})
    c21 = build_cards(ISSUE, alpha, closes, vol, tickers, EXPIRES, "m21",
                      horizon_days=21)[0]
    c63 = build_cards(ISSUE, alpha, closes, vol, tickers, EXPIRES, "m63",
                      horizon_days=63)[0]
    assert c63["horizon_days"] == 63
    width21 = c21["target"] - c21["stop"]
    width63 = c63["target"] - c63["stop"]
    assert width63 / width21 == pytest.approx(np.sqrt(3), rel=1e-3)


def test_horizon_by_model_map_resolves_differently():
    from app.backtest.outcomes import HORIZON_BY_MODEL, compute_outcomes

    assert HORIZON_BY_MODEL["cand-mom61-63d-v1"] == 63
    dates = list(pd.bdate_range("2026-01-01", periods=70).date)
    closes = pd.DataFrame([{"date": d, "company_id": "c1", "close": 100 + i}
                           for i, d in enumerate(dates)])
    preds = pd.DataFrame([{"date": dates[0], "company_id": "c1",
                           "model_version": "m", "alpha_score": 1.0,
                           "predicted_return_30d": 0.01}])
    out21 = compute_outcomes(preds, closes, horizon=21)
    out63 = compute_outcomes(preds, closes, horizon=63)
    assert out21.iloc[0]["resolved_date"] == dates[21]
    assert out63.iloc[0]["resolved_date"] == dates[63]
    assert out63.iloc[0]["realized_return"] > out21.iloc[0]["realized_return"]
