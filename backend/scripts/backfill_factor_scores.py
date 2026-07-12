"""Step 6.2 historical factor backfill (run on YOUR machine).

    cd backend
    python scripts/backfill_factor_scores.py             # all trading dates
    python scripts/backfill_factor_scores.py --restart   # recompute everything
    python scripts/backfill_factor_scores.py --start 2025-01-01

RUN THIS ONLY AFTER:
    1. The insider backfill has FINISHED (insider.log shows its summary) —
       otherwise past dates get computed on partial insider data.
    2. gate1_check.py is green (or consciously accepted).

If you ran run_daily_factors.py earlier on partial insider data, recompute
that date too — simplest is --restart (idempotent, just recomputes all).

Expect ~504 dates x 503 names ≈ 250k rows; runtime roughly 10-30 min
(dominated by per-date insider window computation + upserts). Resumable:
already-computed dates are skipped unless --restart.

Verification:
    SELECT count(DISTINCT date) AS days,
           count(*) AS rows,
           count(momentum_composite) AS momo,
           count(insider_congress_composite) AS smart,
           count(valuation_composite) AS val
    FROM factor_scores;
    -- val will be small (snapshot-only fundamentals): expected, documented.
"""

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.factors.backfill_history import backfill_factor_history  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--restart", action="store_true",
                        help="recompute dates already present")
    parser.add_argument("--start", type=str, default=None, help="YYYY-MM-DD")
    args = parser.parse_args()

    summary = backfill_factor_history(
        restart=args.restart,
        start=date.fromisoformat(args.start) if args.start else None,
    )
    print("\n--- Step 6.2 summary ---")
    for key, value in summary.items():
        print(f"  {key}: {value}")

    if summary["rows_written"] > 0 or summary["dates_computed"] == 0:
        print("\nStep 6.2 PASSES — factor history panel ready for Gate 2 IC analysis.")
        return 0
    print("\nStep 6.2 wrote nothing — paste this output for review.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
