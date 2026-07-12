"""Step 5.1 backfill script (run on YOUR machine).

    cd backend
    python scripts/backfill_prices.py                  # full universe, 2 years
    python scripts/backfill_prices.py --tickers AAPL,MSFT --years 1   # smoke test

Recommended first run: the 2-ticker smoke test above, then the full run
(~503 tickers, expect 10-20 minutes mostly on Yahoo throttling).

Verification (spec Step 5): after the run,
    SELECT count(*) FROM price_features;   -- expect ~250k rows (503 x ~504d)
    SELECT status, count(*) FROM data_quality_log
      WHERE source='yfinance' GROUP BY status;
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.data_pipeline.yfinance_loader import backfill_prices  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", type=str, default=None,
                        help="comma-separated subset, e.g. AAPL,MSFT")
    parser.add_argument("--years", type=int, default=2)
    parser.add_argument("--no-cache", action="store_true",
                        help="skip parquet caching to data/raw/yfinance/")
    args = parser.parse_args()

    tickers = args.tickers.split(",") if args.tickers else None
    summary = backfill_prices(tickers=tickers, years=args.years,
                              cache=not args.no_cache)
    print("\n--- Step 5.1 summary ---")
    for key, value in summary.items():
        print(f"  {key}: {value}")

    total = summary["tickers_requested"]
    ok = summary["tickers_success"]
    if total and ok / total >= 0.95:
        print(f"\nStep 5.1 PASSES ({ok}/{total} tickers >= 95%).")
        return 0
    print(f"\nStep 5.1 coverage below 95% ({ok}/{total}) — inspect data_quality_log.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
