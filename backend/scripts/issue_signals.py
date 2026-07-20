"""Signal Phase S1.3 — issue today's SignalCards (nightly; manual ok).
Idempotent. PREREQUISITE: migration database/013_signal_cards.sql applied."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.signals.cards import issue_cards  # noqa: E402

if __name__ == "__main__":
    summary = issue_cards()
    print("--- signal issue ---")
    for k, v in summary.items():
        print(f"  {k}: {v}")
