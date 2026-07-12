"""Step 2 verification (run on YOUR machine, where Supabase is reachable).

    cd backend
    ../venv/bin/python scripts/verify_db.py    # or: python scripts/verify_db.py
                                               # with your own venv activated

Expects .env at the repo root with SUPABASE_URL and SUPABASE_SERVICE_KEY,
and 001_initial_schema.sql already run in the Supabase SQL editor.

Checks that all 11 tables from the schema exist and are queryable.
"""

import sys
from pathlib import Path

# Allow running from backend/ or repo root without installing the package
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.db import supabase  # noqa: E402

TABLES = [
    "companies",
    "price_features",
    "fundamental_features",
    "insider_transactions",
    "congress_transactions",
    "factor_scores",
    "predictions",
    "llm_theses",
    "subscribers",
    "system_logs",
    "data_quality_log",
]


def main() -> int:
    failures = []
    for table in TABLES:
        try:
            supabase.table(table).select("*").limit(1).execute()
            print(f"  OK   {table}")
        except Exception as exc:  # noqa: BLE001 — report and continue
            failures.append(table)
            print(f"  FAIL {table}: {exc}")
    if failures:
        print(f"\n{len(failures)} table(s) missing or unreachable: {failures}")
        print("Did you run database/001_initial_schema.sql in the SQL editor?")
        return 1
    print(f"\nAll {len(TABLES)} tables verified. Step 2 passes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
