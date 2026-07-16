"""GATE 4 — Paper-trading scoreboard (run any time; meaningful after
enough real trading days have accrued post-deploy).

    cd backend
    python scripts/paper_scoreboard.py

Reports, per model, the REALIZED (not backtested) daily IC of stored
predictions, plus the champion-vs-challenger promotion verdict.

GATE 4 CRITERIA (stated so failure is arguable — cross-check the spec):
    >= 20 resolved prediction days for the champion, AND
    champion realized mean IC > 0 with t-stat >= 2.0
Promotion (separate from the gate): challenger needs >= 60 common
resolved days AND a higher mean IC on those days (Step 8 decision).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from app.backtest.metrics import ic_summary  # noqa: E402
from app.backtest.outcomes import promotion_verdict, realized_ic_by_day  # noqa: E402
from app.factors.backfill_history import _fetch_all  # noqa: E402
from app.ml.predict import CHAMPION_VERSION  # noqa: E402
from app.ml.train import MODEL_VERSION as CHALLENGER_VERSION  # noqa: E402

MIN_GATE_DAYS = 20


def main() -> int:
    outcomes = _fetch_all(
        "prediction_outcomes",
        "id,company_id,prediction_date,model_version,alpha_score,"
        "realized_excess_return",
        "id",
    )
    if outcomes.empty:
        print("GATE 4: PENDING — no resolved outcomes yet (first ones land "
              "21 trading days after the first nightly prediction).")
        return 0
    outcomes["prediction_date"] = pd.to_datetime(
        outcomes["prediction_date"]).dt.date

    print("=" * 72)
    print("GATE 4 — PAPER TRADING SCOREBOARD (realized, out-of-sample)")
    print("=" * 72)
    print(f"  {'model':<32} {'days':>5} {'meanIC':>8} {'ICIR':>6} "
          f"{'t':>6} {'hit':>5}")
    ics = {}
    for model in sorted(outcomes["model_version"].unique()):
        ic = realized_ic_by_day(outcomes.loc[outcomes["model_version"] == model])
        ics[model] = ic
        s = ic_summary(ic)
        print(f"  {model:<32} {s['n_days']:>5} {s['mean_ic']:>8} "
              f"{s['icir']:>6} {s['t_stat']:>6} {s['hit_rate']:>5}")
    print("-" * 72)

    champ = ics.get(CHAMPION_VERSION, pd.Series(dtype=float))
    for model, ic in ics.items():
        if model == CHAMPION_VERSION:
            continue
        verdict = promotion_verdict(champ, ic)
        print(f"  vs {model}: {verdict}")
    print("-" * 72)

    s = ic_summary(champ)
    if s["n_days"] < MIN_GATE_DAYS:
        print(f"\nGATE 4: PENDING — {s['n_days']}/{MIN_GATE_DAYS} resolved "
              f"champion days accrued.")
        return 0
    if s["mean_ic"] > 0 and s["t_stat"] >= 2.0:
        print(f"\nGATE 4: PASS — champion realized IC {s['mean_ic']} "
              f"(t={s['t_stat']}) over {s['n_days']} live days.")
        return 0
    print(f"\nGATE 4: FAIL — champion realized IC {s['mean_ic']} "
          f"(t={s['t_stat']}). The backtest edge is not showing up live; "
          f"per gate discipline we diagnose before launch.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
