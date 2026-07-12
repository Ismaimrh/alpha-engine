"""Step 8.2 — daily champion/challenger predictions (run on YOUR machine).

    cd backend
    python scripts/run_daily_predictions.py

PREREQUISITE: migration database/007_predictions_model_version.sql applied.

Writes two prediction sets for the latest trading date:
    champion-momentum-v1  — user-facing ranking (Gate 3-validated factor)
    lgbm-v1-...           — the ensemble challenger, tracked for promotion

Promotion review is data-driven and happens at Gate 4 (paper trading):
both models' stored predictions accrue realized ICs; the challenger is
promoted if/when it beats the champion out-of-sample.

Verification:
    SELECT model_version, count(*), max(date) FROM predictions
    GROUP BY model_version;
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ml.predict import run_daily_predictions  # noqa: E402


def main() -> int:
    summary = run_daily_predictions()
    print("\n--- Step 8.2 summary ---")
    for key, value in summary.items():
        print(f"  {key}: {value}")
    ok = summary["champion_rows"] > 400 and summary["challenger_rows"] > 400
    print("\nStep 8.2 " + ("PASSES." if ok else
          "coverage looks off — paste this summary."))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
