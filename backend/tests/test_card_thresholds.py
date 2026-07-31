"""Offline tests for the card-threshold candidates (pre-registered).

docs/CARD_THRESHOLD_PREREG.md — these test the SELECTION rules only; no
live issuance path is touched until the decision closes.
"""

import numpy as np
import pandas as pd
import pytest

from scripts.simulate_card_thresholds import (
    FIXED_THRESHOLD,
    HYBRID_FLOOR,
    QUANTILE_K,
    select_fixed,
    select_hybrid,
    select_quantile,
)


def _cross_section(n=500, seed=3, outlier=None):
    rng = np.random.default_rng(seed)
    a = pd.Series(rng.normal(0, 1, n), index=[f"c{i}" for i in range(n)])
    if outlier is not None:
        a.iloc[0] = outlier
    return a


def test_fixed_threshold_collapses_under_an_outlier():
    """The behaviour that triggered this registration: one extreme name
    inflates sigma, so far fewer names cross a FIXED z threshold."""
    clean = _cross_section()
    # emulate the live path: alpha is a z-score of the underlying values
    z_clean = (clean - clean.mean()) / clean.std(ddof=0)
    spiked_raw = clean.copy()
    spiked_raw.iloc[0] = 60.0
    z_spiked = (spiked_raw - spiked_raw.mean()) / spiked_raw.std(ddof=0)

    assert len(select_fixed(z_spiked)) < len(select_fixed(z_clean)) / 4


def test_quantile_count_is_constant_by_construction():
    for seed in (1, 2, 3):
        a = _cross_section(seed=seed)
        sel = select_quantile(a)
        assert 45 <= len(sel) <= 55            # ~2 * 5% of 500
    # and it is immune to a single extreme value
    a = _cross_section()
    a_spiked = a.copy()
    a_spiked.iloc[0] = 99.0
    assert abs(len(select_quantile(a_spiked)) - len(select_quantile(a))) <= 1


def test_hybrid_is_quantile_intersect_conviction_floor():
    a = _cross_section()
    q, h = set(select_quantile(a)), set(select_hybrid(a))
    assert h <= q                                     # subset
    assert all(abs(a[i]) >= HYBRID_FLOOR for i in h)  # floor enforced


def test_hybrid_shrinks_when_dispersion_collapses():
    """A quiet cross-section should issue FEWER hybrid cards — that is the
    property T-QUANTILE lacks (it always issues 10%)."""
    quiet = pd.Series(np.linspace(-0.2, 0.2, 500),
                      index=[f"c{i}" for i in range(500)])
    assert len(select_quantile(quiet)) > 40
    assert len(select_hybrid(quiet)) == 0     # nothing clears the floor


def test_registered_constants_are_what_the_doc_says():
    assert FIXED_THRESHOLD == 1.0
    assert QUANTILE_K == 0.05
    assert HYBRID_FLOOR == 0.5
