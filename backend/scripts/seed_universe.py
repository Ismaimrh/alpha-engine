"""Step 3 seeding script (run on YOUR machine).

    cd backend
    python scripts/seed_universe.py            # fetch Wikipedia + upsert to DB
    python scripts/seed_universe.py --offline  # use cached data/universe.csv

Verification (spec Step 3): expects 500+ companies in the DB afterwards.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.data_pipeline.universe_loader import seed  # noqa: E402


def main() -> int:
    refresh = "--offline" not in sys.argv
    summary = seed(refresh=refresh)
    print("\n--- Step 3 summary ---")
    for key, value in summary.items():
        print(f"  {key}: {value}")
    if summary["companies_in_db"] and summary["companies_in_db"] >= 500:
        print("\nStep 3 verification PASSES (companies >= 500).")
        return 0
    print("\nStep 3 verification FAILS (companies < 500).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
