"""Step 11.5 — export backtest performance for the frontend chart.

    cd backend
    python scripts/export_performance.py

Runs the exact Gate 3 configuration (top 50, 21d rebalance, 10bps/side)
and upserts the daily strategy/benchmark series into performance_daily.
Re-run after factor backfills or parameter changes.

PREREQUISITE: migration database/009_performance_daily.sql applied.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from app.backtest.engine import perf_summary, run_backtest, to_wide_closes  # noqa: E402
from app.factors.backfill_history import _fetch_all  # noqa: E402

PARAMS = {"top_n": 50, "rebalance": 21, "cost_bps": 10.0,
          "score": "momentum_composite"}


def main() -> int:
    from app.utils.db import supabase

    print("Loading panels ...", flush=True)
    closes_long = _fetch_all("price_features", "id,date,company_id,close", "id")
    closes_long["date"] = pd.to_datetime(closes_long["date"]).dt.date
    closes_long = closes_long.drop_duplicates(subset=["date", "company_id"])
    closes = to_wide_closes(closes_long[["date", "company_id", "close"]])

    scores = _fetch_all("factor_scores",
                        "id,date,company_id,momentum_composite", "id")
    scores["date"] = pd.to_datetime(scores["date"]).dt.date
    scores = scores.drop_duplicates(subset=["date", "company_id"])

    print("Running Gate 3 configuration ...", flush=True)
    result = run_backtest(closes, scores, PARAMS["score"],
                          top_n=PARAMS["top_n"],
                          rebalance_every=PARAMS["rebalance"],
                          cost_bps=PARAMS["cost_bps"])
    strat, bench = result["daily_returns"], result["benchmark_returns"]
    frame = pd.DataFrame({"strategy_return": strat,
                          "benchmark_return": bench}).dropna()
    frame["strategy_equity"] = (1 + frame["strategy_return"]).cumprod()
    frame["benchmark_equity"] = (1 + frame["benchmark_return"]).cumprod()

    records = [
        {"date": str(d),
         "strategy_return": round(float(r.strategy_return), 8),
         "benchmark_return": round(float(r.benchmark_return), 8),
         "strategy_equity": round(float(r.strategy_equity), 8),
         "benchmark_equity": round(float(r.benchmark_equity), 8),
         "params": json.dumps(PARAMS)}
        for d, r in frame.iterrows()
    ]
    for i in range(0, len(records), 500):
        supabase.table("performance_daily").upsert(
            records[i : i + 500], on_conflict="date"
        ).execute()

    s = perf_summary(strat)
    print(f"\n--- Step 11.5 export summary ---\n"
          f"  rows: {len(records)}   sharpe: {s['sharpe']}   "
          f"ann_return: {s['ann_return']:.1%}")
    print("Export PASSES." if records else "Nothing exported — review.")
    return 0 if records else 1


if __name__ == "__main__":
    raise SystemExit(main())
