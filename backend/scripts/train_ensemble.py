"""Step 8.1 — Train + evaluate the LightGBM ensemble (run on YOUR machine).

    cd backend
    python scripts/train_ensemble.py

What it does:
    1. Builds the ML dataset: raw price signals + the 3 composites,
       target = 21d forward EXCESS return (beta removed).
    2. Purged walk-forward (quarterly retrain, 21d+2d purge) -> honest
       out-of-sample predictions.
    3. Reports OOS IC of the ensemble vs the momentum-only baseline ON THE
       SAME DATES — the fair fight. Expected outcome, stated up front:
       ensemble ≈ momentum (insider is weak, valuation has no history).
       The win condition for this step is the PLUMBING, not a big IC jump.
    4. Prints final-model feature importances (trained on all resolved
       data — this is what daily scoring will use in Step 8.2).

Runtime: ~5-10 min (panel loads + ~5 LightGBM fits).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from app.backtest.metrics import ic_summary  # noqa: E402
from app.factors.backfill_history import _fetch_all, fetch_price_panel  # noqa: E402
from app.ml.train import (  # noqa: E402
    MODEL_VERSION,
    build_dataset,
    feature_importances,
    train_final_model,
    walk_forward_predict,
)

COMPOSITES = ["momentum_composite", "valuation_composite",
              "insider_congress_composite", "insider_v2",
              "momentum_sector_rel", "reversal_21d", "low_vol",
              "momentum_6_1", "abnormal_volume"]


def _oos_ic(frame: pd.DataFrame, col: str) -> pd.Series:
    return frame.groupby("date").apply(
        lambda g: g[col].corr(g["target"], method="spearman"),
        include_groups=False,
    ).dropna()


def main() -> int:
    print("Loading price panel ...", flush=True)
    prices = fetch_price_panel()  # date, company_id, momentum_12_1, rsi_14, macd_signal, close

    print("Loading factor panel ...", flush=True)
    scores = _fetch_all("factor_scores",
                        "id,date,company_id," + ",".join(COMPOSITES), "id")
    scores["date"] = pd.to_datetime(scores["date"]).dt.date
    scores = scores.drop_duplicates(subset=["date", "company_id"])

    features = prices.merge(scores.drop(columns=["id"]),
                            on=["date", "company_id"], how="left")

    print("Building dataset (21d excess-return target) ...", flush=True)
    dataset = build_dataset(features, prices[["date", "company_id", "close"]])
    print(f"  {len(dataset)} rows, {dataset['date'].nunique()} dates", flush=True)

    print("Purged walk-forward (quarterly retrain) ...", flush=True)
    oos, folds = walk_forward_predict(dataset)
    if oos.empty:
        print("No OOS folds produced — history too short for the fold "
              "config. Paste this output.")
        return 1

    eval_frame = oos.merge(
        dataset[["date", "company_id", "target", "momentum_composite"]],
        on=["date", "company_id"], how="left",
    )
    ens = ic_summary(_oos_ic(eval_frame, "prediction"))
    momo = ic_summary(_oos_ic(
        eval_frame.dropna(subset=["momentum_composite"]), "momentum_composite"
    ))

    print("=" * 70)
    print(f"STEP 8.1 — ENSEMBLE OOS EVALUATION ({MODEL_VERSION})")
    print("=" * 70)
    print(f"  folds: {len(folds)}   "
          f"purge gaps: {[f['purge_gap_days'] for f in folds]} days "
          f"(all must be >= 23)")
    print(f"  OOS window: {folds[0]['test_start']} -> {folds[-1]['test_end']}")
    print("-" * 70)
    print(f"  {'model':<24} {'days':>5} {'meanIC':>8} {'ICIR':>6} "
          f"{'t':>6} {'hit':>5}")
    print(f"  {'ensemble (OOS)':<24} {ens['n_days']:>5} {ens['mean_ic']:>8} "
          f"{ens['icir']:>6} {ens['t_stat']:>6} {ens['hit_rate']:>5}")
    print(f"  {'momentum baseline':<24} {momo['n_days']:>5} "
          f"{momo['mean_ic']:>8} {momo['icir']:>6} {momo['t_stat']:>6} "
          f"{momo['hit_rate']:>5}")
    print("-" * 70)

    model = train_final_model(dataset)
    print("  final-model feature importances (for Step 8.2 daily scoring):")
    for feat, weight in feature_importances(model).items():
        print(f"    {feat:<30} {weight:.1%}")

    if ens["mean_ic"] > 0 and ens["t_stat"] > 2.0:
        print(f"\nSTEP 8.1 PASSES — ensemble OOS IC {ens['mean_ic']} "
              f"(t={ens['t_stat']}). "
              + ("Beats momentum baseline." if ens["mean_ic"] >= momo["mean_ic"]
                 else "Does not beat momentum baseline — acceptable per the "
                      "stated expectation; the pipeline is the deliverable."))
        return 0
    print(f"\nSTEP 8.1 NEEDS REVIEW — ensemble OOS IC {ens['mean_ic']} "
          f"(t={ens['t_stat']}) is not significantly positive. Paste this "
          f"report before we wire predictions.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
