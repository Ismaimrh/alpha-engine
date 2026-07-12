"""Step 6.1 daily factor computation (run on YOUR machine).

    cd backend
    python scripts/run_daily_factors.py               # as of today
    python scripts/run_daily_factors.py --date 2026-07-08

Computes the 3 active composites cross-sectionally and writes one
factor_scores row per company for the latest trading date <= as_of.
Idempotent (upsert on company_id+date) — safe to re-run.

Verification:
    SELECT count(*),
           count(momentum_composite)          AS momo,
           count(valuation_composite)         AS val,
           count(insider_congress_composite)  AS smart
    FROM factor_scores WHERE date = (SELECT max(date) FROM factor_scores);
"""

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.factors.compute import run_daily_factors  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", type=str, default=None, help="YYYY-MM-DD")
    args = parser.parse_args()

    as_of = date.fromisoformat(args.date) if args.date else None
    summary = run_daily_factors(as_of=as_of)
    print("\n--- Step 6.1 summary ---")
    for key, value in summary.items():
        print(f"  {key}: {value}")

    n = summary["companies_scored"] or 1
    ok = (
        summary["momentum_nonnull"] / n >= 0.90
        and summary["valuation_nonnull"] / n >= 0.40  # hard filters legitimately cut deep
        and summary["insider_nonnull"] / n >= 0.90
    )
    if summary["congress_rows_in_window"] == 0:
        print("\nNOTE: 0 congress rows in window — composite is insider-only "
              "(Gate 1 exception B still open).")
    if ok:
        print("\nStep 6.1 PASSES.")
        return 0
    print("\nStep 6.1 coverage looks off — paste this summary for review.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
