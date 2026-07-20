"""Row-level integrity fence for the signal ledger (spec v1.2 / review G5).

Usage: run BEFORE a deploy that touches signal machinery, save the digest,
run again AFTER — identical digest proves the resolved 21d ledger is
byte-identical (counts alone cannot catch a mutated default or column).

    cd backend && python scripts/ledger_hash.py
"""

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    from app.factors.backfill_history import _fetch_all

    df = _fetch_all(
        "signal_cards",
        "id,ticker,issue_date,horizon_days,model_version,direction,entry,"
        "target,stop,status,resolved_date,resolved_close,realized_return",
        "id",
    )
    if df.empty:
        print("ledger empty — digest: <empty>")
        return 0
    df = df.sort_values("id")
    canon = df.to_csv(index=False).encode()
    print(f"rows: {len(df)}")
    print(f"resolved: {(df['status'] != 'open').sum()}")
    print(f"sha256: {hashlib.sha256(canon).hexdigest()}")
    print("\n(compare before/after any signal-machinery deploy; any "
          "difference beyond APPENDED rows fails the gate)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
