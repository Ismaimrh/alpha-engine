"""Signal Phase S1.4 — resolve open SignalCards (nightly; manual ok).
Applies the D3 close-touch rule. Idempotent (status transitions once)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.signals.resolve import resolve_open_cards  # noqa: E402

if __name__ == "__main__":
    summary = resolve_open_cards()
    print("--- signal resolution ---")
    for k, v in summary.items():
        print(f"  {k}: {v}")
