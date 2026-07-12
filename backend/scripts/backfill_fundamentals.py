"""Step 5.2 fundamentals snapshot script (run on YOUR machine).

    cd backend
    python scripts/backfill_fundamentals.py --tickers AAPL,MSFT   # smoke test
    python scripts/backfill_fundamentals.py                       # full universe

NOTE: requires migration database/003_add_eps_std.sql to be applied first.
Full run is per-ticker (~0.5-1s each) — expect 8-15 minutes for 503 names.

Verification:
    SELECT count(*) FROM fundamental_features WHERE as_of_date = current_date;
    SELECT count(*) FROM companies WHERE market_cap IS NOT NULL;
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.data_pipeline.fundamentals_loader import backfill_fundamentals  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", type=str, default=None)
    args = parser.parse_args()

    tickers = args.tickers.split(",") if args.tickers else None
    summary = backfill_fundamentals(tickers=tickers)
    print("\n--- Step 5.2 summary ---")
    for key, value in summary.items():
        print(f"  {key}: {value}")

    total, ok = summary["tickers_requested"], summary["tickers_success"]
    if total and ok / total >= 0.90:
        print(f"\nStep 5.2 PASSES ({ok}/{total} >= 90% — fundamentals are patchier than prices).")
        return 0
    print(f"\nStep 5.2 coverage below 90% ({ok}/{total}) — inspect data_quality_log.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
