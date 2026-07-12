"""Offline tests for the historical factor backfill (Step 6.2)."""

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from app.factors.backfill_history import (
    PREFILTER_DAYS,
    WHOLE_TABLE_DAYS,
    approx_historical_mcaps,
)
from app.factors.compute import LOOKBACK_DAYS


def test_mcap_approximation_scales_with_price():
    closes_then = pd.Series({"A": 50.0, "B": 200.0})
    closes_now = pd.Series({"A": 100.0, "B": 100.0})
    mcap_now = pd.Series({"A": 10e9, "B": 5e9})
    approx = approx_historical_mcaps(closes_then, closes_now, mcap_now)
    assert approx["A"] == pytest.approx(5e9)    # price halved -> mcap halved
    assert approx["B"] == pytest.approx(10e9)   # price doubled since
    # Zero/NaN current close -> NaN, not inf
    bad = approx_historical_mcaps(
        pd.Series({"C": 10.0}), pd.Series({"C": 0.0}), pd.Series({"C": 1e9})
    )
    assert np.isnan(bad["C"])


def test_window_constants_are_sane():
    assert PREFILTER_DAYS > LOOKBACK_DAYS       # prefilter must be wider
    # WHOLE_TABLE horizon must not overflow the date type
    assert date.today() - timedelta(days=WHOLE_TABLE_DAYS) > date.min
