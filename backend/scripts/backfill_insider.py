"""Step 5.3 insider backfill script (run on YOUR machine).

    cd backend
    python scripts/backfill_insider.py --tickers AAPL,MSFT   # smoke test
    python scripts/backfill_insider.py                       # full universe

PREREQUISITES:
    1. Migration database/004_insider_dedup.sql applied.
    2. SEC_USER_AGENT set in .env to your real "Name email" — the loader
       hard-fails on the placeholder (SEC fair-access policy).

RUNTIME WARNING: the full run makes one submissions request per ticker
plus one request per Form 4 filing, throttled to ~5 req/s per SEC policy.
For 503 large caps x 2 years this is typically 15k-30k filings — expect
SEVERAL HOURS (3-6h observed extrapolation).

RECOMMENDED LAUNCH (background + monitorable log):
    nohup python -u scripts/backfill_insider.py > insider.log 2>&1 &
    tail -f insider.log        # progress lines every 10 tickers, with ETA
(`-u` = unbuffered; prints are also flush=True, so tail -f works either way.)

RESUME SEMANTICS: each fully-processed ticker is checkpointed to
data/raw/insider/backfill_checkpoint.json (atomic writes). Re-running the
same day skips checkpointed tickers entirely — no SEC re-downloads — and
retries only errored/unfinished ones. DB writes are idempotent upserts
regardless. Use --restart to ignore the checkpoint and redo everything.

Verification:
    SELECT count(*), min(transaction_date), max(transaction_date)
    FROM insider_transactions;
    SELECT status, count(*) FROM data_quality_log
      WHERE source='sec_edgar' GROUP BY status;
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.data_pipeline.sec_form4_loader import backfill_insider  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", type=str, default=None)
    parser.add_argument("--years", type=int, default=2)
    parser.add_argument("--restart", action="store_true",
                        help="ignore checkpoint, reprocess all tickers")
    args = parser.parse_args()

    tickers = args.tickers.split(",") if args.tickers else None
    summary = backfill_insider(tickers=tickers, years=args.years,
                               restart=args.restart)
    print("\n--- Step 5.3 summary ---")
    for key, value in summary.items():
        print(f"  {key}: {value}")

    total, ok = summary["tickers_requested"], summary["tickers_success"]
    if total and ok / total >= 0.95:
        print(f"\nStep 5.3 PASSES ({ok}/{total} >= 95%).")
        return 0
    print(f"\nStep 5.3 coverage below 95% ({ok}/{total}) — inspect data_quality_log.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
