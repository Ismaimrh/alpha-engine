"""Offline tests for daily factor assembly (Step 6.1) — pure function only."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.factors.compute import assemble_factor_scores

AS_OF = date(2026, 7, 9)
IDS = ["co-momo", "co-value", "co-insider", "co-filtered"]


def _price_signals() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "momentum_12_1": [0.40, 0.05, 0.10, -0.05],
            "rsi_14": [72.0, 48.0, 55.0, 41.0],
            "macd_signal": [1.5, 0.1, 0.3, -0.4],
        },
        index=IDS,
    )


def _fundamentals() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "pe_ratio":     [45.0, 9.0, 20.0, 30.0],
            "pb_ratio":     [10.0, 1.1, 3.0, 4.0],
            "ev_ebitda":    [28.0, 6.0, 12.0, 15.0],
            "fcf_yield":    [0.015, 0.08, 0.04, -0.01],  # co-filtered: negative FCF
            "roe":          [0.25, 0.18, 0.15, 0.10],
            "roic":         [0.18, 0.14, 0.11, 0.07],
            "gross_margin": [0.60, 0.40, 0.35, 0.30],
            "eps_std_3y":   [0.5, 0.3, 0.6, 0.9],
        },
        index=IDS,
    )


def _mcaps() -> pd.Series:
    return pd.Series([500e9, 20e9, 10e9, 8e9], index=IDS)


def _insider() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "company_id": ["co-insider"] * 3,
            "transaction_date": ["2026-06-20", "2026-06-25", "2026-07-01"],
            "filing_date": ["2026-06-22", "2026-06-27", "2026-07-02"],
            "insider_name": ["CEO", "CFO", "COO"],  # cluster -> doubled
            "transaction_code": ["P", "P", "P"],
            "total_value": [1e6, 1e6, 1e6],
        }
    )


@pytest.fixture(scope="module")
def scores() -> pd.DataFrame:
    return assemble_factor_scores(
        AS_OF, _price_signals(), _fundamentals(), _mcaps(),
        _insider(), pd.DataFrame(),
    )


def test_shape_and_columns(scores):
    assert sorted(scores.index) == sorted(IDS)
    assert set(scores.columns) == {
        "momentum_composite", "valuation_composite",
        "quality_composite", "insider_congress_composite",
        "insider_v2",  # candidate column (research cycle 1)
        "momentum_sector_rel", "reversal_21d", "low_vol",  # batch 2
        "high_52w", "momentum_6_1", "abnormal_volume",  # batch 3
        "momentum_robust", "momentum_ranknorm",  # scoring schemes
    }


def test_momentum_ranks_the_trend_leader(scores):
    assert scores["momentum_composite"].idxmax() == "co-momo"


def test_valuation_ranks_the_cheap_quality_name(scores):
    assert scores["valuation_composite"].idxmax() == "co-value"


def test_hard_filtered_name_excluded_from_valuation_only(scores):
    assert np.isnan(scores.loc["co-filtered", "valuation_composite"])
    assert np.isnan(scores.loc["co-filtered", "quality_composite"])
    # ...but still ranked on momentum and insider
    assert not np.isnan(scores.loc["co-filtered", "momentum_composite"])
    assert not np.isnan(scores.loc["co-filtered", "insider_congress_composite"])


def test_insider_cluster_dominates_composite(scores):
    assert scores["insider_congress_composite"].idxmax() == "co-insider"


def test_no_congress_data_degrades_gracefully(scores):
    # congress_df empty -> composite = insider-only leg, still defined
    assert scores["insider_congress_composite"].notna().all()


def test_zero_activity_names_share_the_same_score(scores):
    quiet = scores.loc[["co-momo", "co-value", "co-filtered"],
                       "insider_congress_composite"]
    assert quiet.nunique() == 1  # all zero-activity -> identical z


def test_point_in_time_late_filing_excluded():
    """A buy filed after as_of must not move the composite."""
    late = _insider().copy()
    late.loc[3] = {
        "company_id": "co-momo", "transaction_date": "2026-07-05",
        "filing_date": "2026-07-15",  # filed AFTER as_of
        "insider_name": "CEO", "transaction_code": "P", "total_value": 5e7,
    }
    with_late = assemble_factor_scores(
        AS_OF, _price_signals(), _fundamentals(), _mcaps(), late, pd.DataFrame()
    )
    base = assemble_factor_scores(
        AS_OF, _price_signals(), _fundamentals(), _mcaps(), _insider(), pd.DataFrame()
    )
    pd.testing.assert_series_equal(
        with_late["insider_congress_composite"],
        base["insider_congress_composite"],
    )


def test_duplicated_mcap_index_does_not_crash():
    """Regression: offset pagination without total ordering produced
    duplicated company_ids; .get() then returned a Series and
    insider_buy_signal crashed on `market_cap <= 0`."""
    dup_mcaps = pd.Series(
        [500e9, 500e9, 20e9, 10e9, 8e9],
        index=["co-momo", "co-momo", "co-value", "co-insider", "co-filtered"],
    )
    dup_prices = pd.concat([_price_signals(), _price_signals().iloc[[0]]])
    result = assemble_factor_scores(
        AS_OF, dup_prices, _fundamentals(), dup_mcaps, _insider(), pd.DataFrame()
    )
    assert result.index.is_unique
    assert result["insider_congress_composite"].notna().all()


# ------------------------------------------------- insider v2 (candidate)

def _v2_txns(rows):
    return pd.DataFrame(rows, columns=["transaction_date", "filing_date",
                                       "insider_name", "transaction_code",
                                       "total_value"])


def test_v2_ignores_sells_entirely():
    from app.factors.insider_congressional.factors import insider_buy_signal_v2

    only_sells = _v2_txns([
        ("2026-06-01", "2026-06-03", "Alice CEO", "S", 50_000_000),
        ("2026-06-10", "2026-06-11", "Bob CFO", "S", 80_000_000),
    ])
    assert insider_buy_signal_v2(only_sells, AS_OF, 10e9) == 0.0

    with_buy = _v2_txns([
        ("2026-06-01", "2026-06-03", "Alice CEO", "S", 50_000_000),
        ("2026-06-10", "2026-06-11", "Bob CFO", "P", 1_000_000),
    ])
    assert insider_buy_signal_v2(with_buy, AS_OF, 10e9) > 0.0


def test_v2_breadth_beats_single_whale():
    from app.factors.insider_congressional.factors import insider_buy_signal_v2

    whale = _v2_txns([("2026-06-01", "2026-06-03", "Alice CEO", "P", 3_000_000)])
    trio = _v2_txns([
        ("2026-06-01", "2026-06-03", "Alice CEO", "P", 1_000_000),
        ("2026-06-05", "2026-06-07", "Bob CFO", "P", 1_000_000),
        ("2026-06-09", "2026-06-11", "Carol COO", "P", 1_000_000),
    ])
    # same total dollars, three distinct buyers > one whale
    assert (insider_buy_signal_v2(trio, AS_OF, 10e9)
            > insider_buy_signal_v2(whale, AS_OF, 10e9))


def test_v2_log_scaling_tames_outliers():
    from app.factors.insider_congressional.factors import insider_buy_signal_v2

    small = _v2_txns([("2026-06-01", "2026-06-03", "A", "P", 1_000_000)])
    huge = _v2_txns([("2026-06-01", "2026-06-03", "A", "P", 100_000_000)])
    s, h = (insider_buy_signal_v2(small, AS_OF, 10e9),
            insider_buy_signal_v2(huge, AS_OF, 10e9))
    assert h > s                      # monotonic
    assert h / s < 100                # but far sublinear (100x $ -> <100x signal)


def test_v2_respects_point_in_time_and_180d_window():
    from app.factors.insider_congressional.factors import insider_buy_signal_v2

    unfiled = _v2_txns([("2026-06-01", "2026-08-01", "A", "P", 1_000_000)])
    assert insider_buy_signal_v2(unfiled, AS_OF, 10e9) == 0.0  # filed in future

    old = _v2_txns([("2025-10-01", "2025-10-03", "A", "P", 1_000_000)])
    recent = _v2_txns([("2026-02-01", "2026-02-03", "A", "P", 1_000_000)])
    assert insider_buy_signal_v2(old, AS_OF, 10e9) == 0.0      # > 180d ago
    assert insider_buy_signal_v2(recent, AS_OF, 10e9) > 0.0    # inside 180d


def test_assemble_emits_insider_v2_column():
    result = assemble_factor_scores(
        AS_OF, _price_signals(), _fundamentals(), _mcaps(), _insider(),
        pd.DataFrame(),
    )
    assert "insider_v2" in result.columns
    assert result["insider_v2"].notna().any()


# ------------------------------------------- research batch 2 candidates

def _batch2_inputs():
    sectors = pd.Series({"co-momo": "Tech", "co-value": "Tech",
                         "co-insider": "Health", "co-filtered": "Health"})
    ret21 = pd.Series({"co-momo": 0.30, "co-value": 0.05,
                       "co-insider": -0.15, "co-filtered": 0.01})
    vol63 = pd.Series({"co-momo": 0.045, "co-value": 0.015,
                       "co-insider": 0.030, "co-filtered": 0.010})
    return sectors, ret21, vol63


def _assemble_batch2():
    sectors, ret21, vol63 = _batch2_inputs()
    return assemble_factor_scores(
        AS_OF, _price_signals(), _fundamentals(), _mcaps(), _insider(),
        pd.DataFrame(), sectors=sectors, trailing_ret_21d=ret21,
        realized_vol_63d=vol63,
    )


def test_batch2_columns_emitted_and_none_inputs_degrade():
    scores = _assemble_batch2()
    for col in ("momentum_sector_rel", "reversal_21d", "low_vol"):
        assert col in scores.columns
        assert scores[col].notna().any()
    # None inputs -> NaN columns, no crash (old call sites keep working)
    bare = assemble_factor_scores(
        AS_OF, _price_signals(), _fundamentals(), _mcaps(), _insider(),
        pd.DataFrame(),
    )
    for col in ("momentum_sector_rel", "reversal_21d", "low_vol"):
        assert bare[col].isna().all()


def test_reversal_ranks_the_biggest_loser_highest():
    scores = _assemble_batch2()
    assert scores["reversal_21d"].idxmax() == "co-insider"   # -15% loser
    assert scores["reversal_21d"].idxmin() == "co-momo"      # +30% winner


def test_low_vol_ranks_the_calmest_highest():
    scores = _assemble_batch2()
    assert scores["low_vol"].idxmax() == "co-filtered"       # vol 1.0%
    assert scores["low_vol"].idxmin() == "co-momo"           # vol 4.5%


def test_sector_relative_uses_global_fallback_for_tiny_sectors():
    # 2-name sectors (<5) must fall back to the GLOBAL momentum z
    scores = _assemble_batch2()
    pd.testing.assert_series_equal(
        scores["momentum_sector_rel"].sort_index(),
        scores["momentum_composite"].sort_index(),
        check_names=False,
    )


# ------------------------------------------- research batch 3 candidates

def _assemble_batch3():
    sectors, ret21, vol63 = _batch2_inputs()
    high52 = pd.Series({"co-momo": 0.99, "co-value": 0.80,
                        "co-insider": 0.60, "co-filtered": 0.90})
    mom61 = pd.Series({"co-momo": 0.25, "co-value": 0.02,
                       "co-insider": -0.10, "co-filtered": 0.05})
    abnvol = pd.Series({"co-momo": 2.0, "co-value": 1.0,
                        "co-insider": 0.5, "co-filtered": -1.0})  # bad ratio
    return assemble_factor_scores(
        AS_OF, _price_signals(), _fundamentals(), _mcaps(), _insider(),
        pd.DataFrame(), sectors=sectors, trailing_ret_21d=ret21,
        realized_vol_63d=vol63, high_52w_prox=high52,
        momentum_6_1_raw=mom61, abn_volume_ratio=abnvol,
    )


def test_batch3_columns_and_ordering():
    s = _assemble_batch3()
    assert s["high_52w"].idxmax() == "co-momo"       # nearest its high
    assert s["high_52w"].idxmin() == "co-insider"
    assert s["momentum_6_1"].idxmax() == "co-momo"
    # abnormal_volume: log of ratio; non-positive ratio -> NaN, not -inf
    assert s["abnormal_volume"].idxmax() == "co-momo"
    assert np.isnan(s.loc["co-filtered", "abnormal_volume"])


def test_batch3_none_inputs_degrade():
    bare = assemble_factor_scores(
        AS_OF, _price_signals(), _fundamentals(), _mcaps(), _insider(),
        pd.DataFrame(),
    )
    for col in ("high_52w", "momentum_6_1", "abnormal_volume"):
        assert bare[col].isna().all()


# ------------------------------- scoring-scheme candidates (pre-registered)

def test_robust_zscore_resists_a_single_outlier():
    from app.factors.cross_section import robust_zscore, zscore

    base = pd.Series(np.linspace(-0.2, 0.2, 200))
    spiked = pd.concat([base, pd.Series([47.0])], ignore_index=True)

    plain_base = zscore(base).abs().ge(1.0).sum()
    plain_spiked = zscore(spiked).abs().ge(1.0).sum()
    rob_base = robust_zscore(base).abs().ge(1.0).sum()
    rob_spiked = robust_zscore(spiked).abs().ge(1.0).sum()

    # the incumbent collapses when one name explodes; MAD barely moves
    assert plain_spiked < plain_base / 4
    assert rob_spiked >= rob_base - 1


def test_robust_zscore_matches_plain_on_gaussian_data():
    """1.4826*MAD is a consistent sigma estimator, so ±1.0 keeps meaning."""
    from app.factors.cross_section import robust_zscore, zscore

    rng = np.random.default_rng(5)
    g = pd.Series(rng.normal(0, 1, 5000))
    assert robust_zscore(g).std() == pytest.approx(zscore(g).std(), rel=0.05)


def test_robust_zscore_degenerate_mad_falls_back():
    from app.factors.cross_section import robust_zscore

    zero_inflated = pd.Series([0.0] * 90 + [5.0] * 10)  # MAD == 0
    out = robust_zscore(zero_inflated)
    assert out.notna().all() and np.isfinite(out).all()


def test_assemble_emits_scheme_candidates_without_touching_live():
    scores = assemble_factor_scores(
        AS_OF, _price_signals(), _fundamentals(), _mcaps(), _insider(),
        pd.DataFrame(),
    )
    for col in ("momentum_robust", "momentum_ranknorm"):
        assert col in scores.columns
    # the live composite is byte-identical to the incumbent computation
    from app.factors.momentum.factors import momentum_composite_cross_section
    incumbent = momentum_composite_cross_section(
        _price_signals().reindex(scores.index))
    pd.testing.assert_series_equal(
        scores["momentum_composite"], incumbent, check_names=False)
