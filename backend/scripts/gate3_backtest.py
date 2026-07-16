"""GATE 3 — Portfolio Backtest (run on YOUR machine).

    cd backend
    python scripts/gate3_backtest.py                       # defaults below
    python scripts/gate3_backtest.py --top-n 30 --cost-bps 15

Walk-forward, monthly-rebalanced, equal-weight top-N momentum portfolio
with transaction costs, vs the equal-weight universe benchmark.

Defaults: top_n=50, rebalance every 21 trading days, 10 bps per side.

GATE 3 CRITERION (spec): Sharpe > 1.0 AFTER COSTS. The report also shows
the benchmark so you can see selection skill vs market beta, and a
0-cost variant so the cost drag is explicit.

HONESTY NOTES printed with every run:
- ~2 years of history = ONE market regime. A pass here is necessary, not
  sufficient — Gate 4 (paper trading) is the out-of-sample test.
- Execution at signal close (documented engine assumption).
- Single-factor (momentum) portfolio: the ML ensemble (Step 8) comes next;
  this gate benchmarks the raw factor first.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from app.backtest.engine import perf_summary, run_backtest, to_wide_closes  # noqa: E402
from app.factors.backfill_history import _fetch_all  # noqa: E402

DEFAULT_SCORE_COL = "momentum_composite"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--top-n", type=int, default=50)
    parser.add_argument("--cost-bps", type=float, default=10.0)
    parser.add_argument("--rebalance", type=int, default=21)
    parser.add_argument("--score-col", default=DEFAULT_SCORE_COL,
                        help="factor_scores column to trade (e.g. "
                             "momentum_sector_rel)")
    args = parser.parse_args()

    print("Loading close panel ...", flush=True)
    closes_long = _fetch_all("price_features", "id,date,company_id,close", "id")
    closes_long["date"] = pd.to_datetime(closes_long["date"]).dt.date
    closes_long = closes_long.drop_duplicates(subset=["date", "company_id"])
    closes = to_wide_closes(closes_long[["date", "company_id", "close"]])

    print("Loading factor panel ...", flush=True)
    scores = _fetch_all("factor_scores", f"id,date,company_id,{args.score_col}", "id")
    scores["date"] = pd.to_datetime(scores["date"]).dt.date
    scores = scores.drop_duplicates(subset=["date", "company_id"])

    print("Running backtest ...", flush=True)
    result = run_backtest(closes, scores, args.score_col, top_n=args.top_n,
                          rebalance_every=args.rebalance,
                          cost_bps=args.cost_bps)
    free = run_backtest(closes, scores, args.score_col, top_n=args.top_n,
                        rebalance_every=args.rebalance, cost_bps=0.0)

    strat = perf_summary(result["daily_returns"])
    strat_free = perf_summary(free["daily_returns"])
    bench = perf_summary(result["benchmark_returns"])

    print("=" * 74)
    print(f"GATE 3 — MOMENTUM PORTFOLIO BACKTEST "
          f"(top {args.top_n}, {args.rebalance}d rebalance, "
          f"{args.cost_bps}bps/side)")
    print("=" * 74)
    width = 22
    rows = [
        ("", "strategy", "strategy(0-cost)", "benchmark"),
        ("n_days", strat["n_days"], strat_free["n_days"], bench["n_days"]),
        ("total_return", strat["total_return"], strat_free["total_return"],
         bench["total_return"]),
        ("ann_return", strat["ann_return"], strat_free["ann_return"],
         bench["ann_return"]),
        ("ann_vol", strat["ann_vol"], strat_free["ann_vol"], bench["ann_vol"]),
        ("sharpe", strat["sharpe"], strat_free["sharpe"], bench["sharpe"]),
        ("max_drawdown", strat["max_drawdown"], strat_free["max_drawdown"],
         bench["max_drawdown"]),
    ]
    for r in rows:
        print(f"  {str(r[0]):<14} {str(r[1]):>{width}} {str(r[2]):>{width}} "
              f"{str(r[3]):>{width}}")
    print("-" * 74)
    print(f"  rebalances: {result['rebalances']}   "
          f"avg turnover: {result['avg_turnover']:.1%}   "
          f"cost drag (ann): "
          f"{strat_free['ann_return'] - strat['ann_return']:.2%}")
    print("-" * 74)
    print("  Caveats: single ~2y regime; execution at signal close; "
          "raw momentum only (ensemble in Step 8); Gate 4 paper trading is "
          "the real out-of-sample test.")
    if strat["sharpe"] is not None and strat["sharpe"] > 1.0:
        print(f"\nGATE 3: PASS — after-cost Sharpe {strat['sharpe']} > 1.0.")
        return 0
    print(f"\nGATE 3: FAIL — after-cost Sharpe {strat['sharpe']} <= 1.0. "
          f"Per gate discipline: diagnose (top_n? rebalance freq? costs?) "
          f"before proceeding. Paste this report.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
