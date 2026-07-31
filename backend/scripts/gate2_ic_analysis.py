"""GATE 2 — Factor IC Analysis (run on YOUR machine).

    cd backend
    python scripts/gate2_ic_analysis.py                 # 21d horizon
    python scripts/gate2_ic_analysis.py --horizon 30

Loads the full factor_scores panel + close prices, computes forward
returns, and reports per active factor: mean IC, ICIR, t-stat, hit rate,
and top-minus-bottom decile spread (annualized).

THRESHOLDS (stated so failure is arguable — cross-check against the spec's
Gate 2 wording and tell Claude if they differ):
    mean IC  >= 0.02   (economically meaningful for monthly-horizon factors)
    t-stat   >= 2.0    (statistically distinguishable from zero)
A factor passes on BOTH; the gate passes if >= 1 factor passes (spec: fix
or drop factors that show nothing — the MVP needs at least one live edge).

Valuation caveat printed automatically: with snapshot-only fundamentals it
has ~0 days of usable IC history and is EXCLUDED from the gate verdict
until snapshots accumulate (documented Phase 1 limitation).

Runtime: ~2-5 min (paginated panel fetches dominate).
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from app.backtest.metrics import (  # noqa: E402
    daily_ic,
    decile_spread,
    forward_returns,
    ic_summary,
)
from app.factors.backfill_history import _fetch_all  # noqa: E402

FACTORS = ["momentum_composite", "valuation_composite",
           "insider_congress_composite", "insider_v2",
           "momentum_sector_rel", "reversal_21d", "low_vol",
           "high_52w", "momentum_6_1", "abnormal_volume",
           "momentum_robust", "momentum_ranknorm"]
MIN_DAYS_FOR_VERDICT = 60
IC_THRESHOLD = 0.02
T_THRESHOLD = 2.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--horizon", type=int, default=21,
                        help="forward-return horizon in trading days")
    args = parser.parse_args()

    print("Loading close panel ...", flush=True)
    closes = _fetch_all("price_features", "id,date,company_id,close", "id")
    closes["date"] = pd.to_datetime(closes["date"]).dt.date
    closes = closes.drop_duplicates(subset=["date", "company_id"])

    print("Loading factor panel ...", flush=True)
    scores = _fetch_all(
        "factor_scores",
        "id,date,company_id," + ",".join(FACTORS),
        "id",
    )
    scores["date"] = pd.to_datetime(scores["date"]).dt.date
    scores = scores.drop_duplicates(subset=["date", "company_id"])

    print(f"Computing {args.horizon}d forward returns ...", flush=True)
    fwd = forward_returns(closes[["date", "company_id", "close"]],
                          horizon=args.horizon)

    print("=" * 76)
    print(f"GATE 2 — FACTOR IC ANALYSIS ({args.horizon}d horizon, Spearman)")
    print("=" * 76)
    header = (f"  {'factor':<28} {'days':>5} {'meanIC':>7} {'ICIR':>6} "
              f"{'t':>6} {'hit':>5} {'spread(ann)':>12}  verdict")
    print(header)
    print("-" * 76)

    passing, insufficient = [], []
    for factor in FACTORS:
        ic = daily_ic(scores, fwd, factor)
        s = ic_summary(ic)
        d = decile_spread(scores, fwd, factor, horizon=args.horizon)
        if s["n_days"] < MIN_DAYS_FOR_VERDICT:
            verdict = f"INSUFFICIENT DATA (<{MIN_DAYS_FOR_VERDICT}d)"
            insufficient.append(factor)
        elif s["mean_ic"] >= IC_THRESHOLD and s["t_stat"] >= T_THRESHOLD:
            verdict = "PASS"
            passing.append(factor)
        else:
            verdict = (f"FAIL (need IC>={IC_THRESHOLD}, t>={T_THRESHOLD})")
        print(f"  {factor:<28} {s['n_days']:>5} {s['mean_ic']:>7} "
              f"{s['icir']:>6} {s['t_stat']:>6} {s['hit_rate']:>5} "
              f"{d['mean_spread_ann']:>12}  {verdict}")

    print("-" * 76)
    if insufficient:
        print(f"  excluded from verdict (insufficient history): {insufficient}")
        print("  (valuation is expected here: snapshot-only fundamentals — "
              "documented Phase 1 limitation)")
    if passing:
        print(f"\nGATE 2: PASS — live edge in {passing}. "
              f"Cleared for the portfolio backtest (Gate 3).")
        return 0
    print("\nGATE 2: FAIL — no factor shows a significant IC. STOP: per gate "
          "discipline we diagnose (horizon? universe? signal decay?) before "
          "building the portfolio backtest on dead factors.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
