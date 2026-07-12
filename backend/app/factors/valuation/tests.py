"""Unit tests for the valuation factor (co-located per spec structure)."""

import numpy as np
import pandas as pd

from app.factors.valuation.factors import (
    MIN_MARKET_CAP,
    quality_composite,
    quality_value_composite,
    universe_filter_mask,
    value_composite,
)


def _metrics() -> pd.DataFrame:
    return pd.DataFrame(
        {
            #                 CHEAP   FAIR    RICH
            "pe_ratio":      [8.0,    18.0,   60.0],
            "pb_ratio":      [0.9,    2.5,    12.0],
            "ev_ebitda":     [5.0,    11.0,   30.0],
            "fcf_yield":     [0.09,   0.04,   0.01],
            #                 GOOD    OK      POOR
            "roe":           [0.30,   0.12,   0.02],
            "roic":          [0.22,   0.10,   0.01],
            "gross_margin":  [0.55,   0.35,   0.15],
            "eps_std_3y":    [0.20,   0.80,   2.50],
            "market_cap":    [50e9,   10e9,   2e9],
        },
        index=["CHEAP", "FAIR", "RICH"],
    )


def test_value_composite_orders_cheapness():
    v = value_composite(_metrics())
    assert v["CHEAP"] > v["FAIR"] > v["RICH"]


def test_quality_composite_orders_quality():
    q = quality_composite(_metrics())
    assert q["CHEAP"] > q["FAIR"] > q["RICH"]


def test_negative_pe_ranks_worse_than_positive():
    m = _metrics().copy()
    m.loc["LOSSY"] = m.loc["FAIR"]
    m.loc["LOSSY", "pe_ratio"] = -12.0  # negative earnings
    v = value_composite(m)
    assert v["LOSSY"] < v["CHEAP"]  # negative earnings yield ranks lowest


def test_nan_component_is_tolerated():
    m = _metrics().copy()
    m.loc["CHEAP", "ev_ebitda"] = np.nan
    v = value_composite(m)
    assert not np.isnan(v["CHEAP"])  # remaining components carry the score
    assert v["CHEAP"] > v["RICH"]


def test_quality_value_is_equal_weighted():
    v = pd.Series([1.0, -1.0], index=["A", "B"])
    q = pd.Series([0.0, 0.0], index=["A", "B"])
    qv = quality_value_composite(v, q)
    assert qv["A"] == 0.5 and qv["B"] == -0.5


def test_hard_filters():
    m = _metrics().copy()
    m.loc["BADROE"] = m.loc["FAIR"]
    m.loc["BADROE", "roe"] = -0.05
    m.loc["BADFCF"] = m.loc["FAIR"]
    m.loc["BADFCF", "fcf_yield"] = -0.02
    m.loc["TINY"] = m.loc["FAIR"]
    m.loc["TINY", "market_cap"] = MIN_MARKET_CAP - 1
    m.loc["NODATA"] = m.loc["FAIR"]
    m.loc["NODATA", "roe"] = np.nan

    keep = universe_filter_mask(m)
    assert bool(keep["CHEAP"]) and bool(keep["FAIR"]) and bool(keep["RICH"])
    assert not keep["BADROE"]
    assert not keep["BADFCF"]
    assert not keep["TINY"]
    assert not keep["NODATA"]  # conservative: missing data -> excluded
