"""Step 5.4 congressional backfill — PLAN B: Senate EFD direct (run on YOUR machine).

    cd backend
    python scripts/backfill_congress.py             # Senate EFD, 2 years
    python scripts/backfill_congress.py --refresh   # ignore per-PTR cache

HISTORY: Plan A (Stock Watcher S3 mirrors) died — both buckets 403 as of
2026-07-09. This loader goes to the official source, efdsearch.senate.gov.
House PTRs are PDFs and are DEFERRED post-MVP (decision in CLAUDE.md);
the smart-money composite renormalizes to the legs present.

Expect a few hundred to ~2000 electronic PTRs for 2 years at ~0.5s each
-> roughly 5-20 minutes. Per-PTR results are cached to
data/raw/congress/efd/, so re-runs and future daily runs are fast.

If the run fails at the session/CSRF step or returns 0 PTRs, the EFD site
markup likely changed — paste the full output/traceback for loader repair.

Verification:
    SELECT chamber, count(*), max(filing_date) FROM congress_transactions
    GROUP BY chamber;
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.data_pipeline.senate_efd_loader import backfill_senate_efd  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", type=int, default=2)
    parser.add_argument("--refresh", action="store_true",
                        help="re-fetch PTRs even if cached")
    parser.add_argument("--engine", choices=["auto", "requests", "selenium"],
                        default="auto",
                        help="session bootstrap; selenium needs Chrome + "
                             "pip install selenium")
    args = parser.parse_args()

    summary = backfill_senate_efd(years=args.years, refresh=args.refresh,
                                  engine=args.engine)
    print("\n--- Step 5.4 (Plan B: Senate EFD) summary ---")
    for key, value in summary.items():
        print(f"  {key}: {value}")

    if summary["rows_written"] > 0 and not summary["stale"]:
        print("\nStep 5.4 PASSES (Senate leg live; House deferred post-MVP).")
        return 0
    print("\nStep 5.4 NEEDS ATTENTION — paste this output for review.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
