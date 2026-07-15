"""Step 13 — resolve paper-trading outcomes (runs nightly; also manual).

    cd backend
    python scripts/resolve_outcomes.py

Resolves every stored prediction whose 21-trading-day horizon has elapsed
into prediction_outcomes. Idempotent. Before deploy day +21 it will
correctly report 0 resolved — that is honesty, not breakage.

PREREQUISITE: migration database/010_prediction_outcomes.sql applied.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.backtest.outcomes import resolve_outcomes  # noqa: E402


def main() -> int:
    summary = resolve_outcomes()
    print("--- outcome resolution ---")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
