"""Nightly pipeline (spec Step 12) — one entry point for the scheduler.

    python scripts/nightly_update.py            # full nightly run
    python scripts/nightly_update.py --skip-llm # no thesis spend

Order matters: data -> factors -> predictions -> theses -> performance.

Window tuning (fractional years; loaders use int(years*365.25) days):
    prices       1.2y  — momentum_12_1 needs ~13 months + warm-up pad
    fundamentals snapshot (accumulates daily; valuation factor grows teeth)
    insider      0.04y (~15 days) — catches late/amended Form 4s cheaply
    congress     NOT here — needs a display server for Chrome; runs in the
                 weekly workflow under xvfb (see weekly_congress.yml)

Failure policy: prices/factors/predictions are CRITICAL (nonzero exit ->
the workflow alerts); fundamentals/insider/theses/performance log and
continue — one flaky source must not kill the ranking.
"""

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

CRITICAL = {"prices", "factors", "predictions"}


def run_step(name: str, fn) -> tuple[bool, str]:
    started = datetime.now()
    print(f"\n=== {name} ===", flush=True)
    try:
        fn()
        elapsed = (datetime.now() - started).total_seconds()
        print(f"=== {name} OK ({elapsed:.0f}s) ===", flush=True)
        return True, ""
    except Exception as exc:  # noqa: BLE001 — orchestrator must survive
        print(f"=== {name} FAILED: {exc} ===", flush=True)
        return False, str(exc)


def script(path: str, *args: str):
    """Run a verified CLI script as a subprocess, propagating failure."""
    def _run():
        result = subprocess.run(
            [sys.executable, str(BACKEND / "scripts" / path), *args],
            cwd=BACKEND,
        )
        if result.returncode != 0:
            raise RuntimeError(f"{path} exited {result.returncode}")
    return _run


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-llm", action="store_true")
    args = parser.parse_args()

    from app.data_pipeline.fundamentals_loader import backfill_fundamentals
    from app.data_pipeline.sec_form4_loader import backfill_insider
    from app.data_pipeline.yfinance_loader import backfill_prices

    steps: list[tuple[str, object]] = [
        ("prices", lambda: backfill_prices(years=1.2, cache=False)),
        ("fundamentals", lambda: backfill_fundamentals()),
        ("insider", lambda: backfill_insider(years=0.04)),
        ("factors", script("run_daily_factors.py")),
        ("predictions", script("run_daily_predictions.py")),
    ]
    if not args.skip_llm:
        steps.append(("theses",
                      script("generate_theses.py", "--top-n", "10",
                             "--max-cost", "0.25")))
    steps.append(("outcomes", script("resolve_outcomes.py")))
    steps.append(("performance", script("export_performance.py")))
    steps.append(("email", script("send_daily_email.py")))

    results = {name: run_step(name, fn) for name, fn in steps}

    print("\n--- nightly summary ---")
    failed_critical = []
    for name, (ok, err) in results.items():
        print(f"  {name:<13} {'OK' if ok else 'FAILED  ' + err[:80]}")
        if not ok and name in CRITICAL:
            failed_critical.append(name)
    if failed_critical:
        print(f"\nNIGHTLY FAILED — critical steps down: {failed_critical}")
        return 1
    print("\nNIGHTLY OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
