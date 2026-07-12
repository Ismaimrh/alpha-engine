"""GATE 1 — Data Quality Validation (run on YOUR machine).

    cd backend
    python scripts/gate1_check.py

PREREQUISITE: migration database/006_gate1_function.sql applied.

This is a STOP-AND-VALIDATE gate (spec): if it FAILS, we fix data before
touching Phase 2. The report prints every metric, the threshold it is held
to, and a verdict per check plus an overall verdict.

Thresholds (from the spec's Phase 1 acceptance criteria, stated explicitly
so failures are arguable rather than mysterious):
    price coverage        >= 95% of universe
    price freshness       max(date) within 5 calendar days
    fundamentals coverage >= 90% of universe
    insider coverage      >= 60% of universe (not all companies have
                          open-market P/S activity in 2y — that is signal,
                          not missingness)
    point-in-time         0 violations (transaction_date > filing_date)
    congress freshness    max(filing_date) within 60 days (else the source
                          is stale -> WARN, factor degrades gracefully to
                          insider-only)
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.db import supabase  # noqa: E402

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"


def verdict(ok: bool, warn_ok: bool = False) -> str:
    return PASS if ok else (WARN if warn_ok else FAIL)


def _days_ago(iso: str | None) -> int | None:
    return (date.today() - date.fromisoformat(iso)).days if iso else None


def main() -> int:
    report = supabase.rpc("gate1_report").execute().data
    uni = report["universe"]
    prices = report["prices"]
    fund = report["fundamentals"]
    insider = report["insider"]
    congress = report["congress"]

    n = uni["companies_in_universe"] or 1
    checks: list[tuple[str, str, str]] = []  # (name, detail, verdict)

    # --- Prices
    cov = prices["distinct_companies"] / n
    fresh = _days_ago(prices["max_date"])
    checks.append(("price coverage", f"{prices['distinct_companies']}/{n} = {cov:.1%} (>=95%)",
                   verdict(cov >= 0.95)))
    checks.append(("price freshness", f"max date {prices['max_date']} ({fresh}d ago, <=5d)",
                   verdict(fresh is not None and fresh <= 5)))
    checks.append(("price integrity", f"{prices['null_close_rows']} NULL closes (=0); "
                   f"{prices['total_rows']} rows total",
                   verdict(prices["null_close_rows"] == 0)))
    checks.append(("momentum warm-up", f"{prices['momentum_nonnull_last_day']}/{n} names have "
                   f"momentum_12_1 on latest day (>=90%)",
                   verdict(prices["momentum_nonnull_last_day"] / n >= 0.90)))

    # --- Fundamentals
    fcov = fund["distinct_companies"] / n
    checks.append(("fundamentals coverage", f"{fund['distinct_companies']}/{n} = {fcov:.1%} (>=90%)",
                   verdict(fcov >= 0.90)))
    for col in ("null_pe", "null_roe", "null_fcf_yield", "null_eps_std_3y"):
        rate = fund[col] / max(fund["total_rows"], 1)
        # NULLs are expected (banks lack EV/EBITDA etc.) — hold to <=30%, warn to 50%
        checks.append((f"fundamentals {col}", f"{rate:.1%} NULL (<=30% pass, <=50% warn)",
                       verdict(rate <= 0.30, warn_ok=rate <= 0.50)))

    # --- Insider (SEC Form 4)
    icov = insider["distinct_companies"] / n
    checks.append(("insider coverage", f"{insider['distinct_companies']}/{n} = {icov:.1%} (>=60%)",
                   verdict(icov >= 0.60)))
    checks.append(("insider point-in-time", f"{insider['pit_violations']} rows with "
                   f"transaction_date > filing_date (=0)",
                   verdict(insider["pit_violations"] == 0)))
    checks.append(("insider volume", f"{insider['total_rows']} rows "
                   f"({insider['buys']} buys / {insider['sells']} sells), "
                   f"{insider['min_transaction']} -> {insider['max_transaction']}",
                   verdict(insider["total_rows"] > 0)))

    # --- Congress
    cfresh = _days_ago(congress["max_filing"])
    checks.append(("congress freshness", f"max filing {congress['max_filing']} "
                   f"({cfresh}d ago, <=60d; stale -> factor degrades to insider-only)",
                   verdict(cfresh is not None and cfresh <= 60, warn_ok=True)))
    checks.append(("congress point-in-time", f"{congress['pit_violations']} violations (=0)",
                   verdict(congress["pit_violations"] == 0)))
    checks.append(("congress volume", f"{congress['total_rows']} rows "
                   f"(House {congress['house_rows']} / Senate {congress['senate_rows']}), "
                   f"{congress['distinct_companies']} companies",
                   verdict(congress["total_rows"] > 0, warn_ok=True)))

    # --- Report
    print("=" * 72)
    print("GATE 1 — DATA QUALITY VALIDATION")
    print("=" * 72)
    width = max(len(c[0]) for c in checks)
    for name, detail, v in checks:
        print(f"  [{v:^4}] {name:<{width}}  {detail}")
    print("-" * 72)
    print("  quality_log:", dict(sorted(report["quality_log"].items())))

    fails = [c for c in checks if c[2] == FAIL]
    warns = [c for c in checks if c[2] == WARN]
    print("-" * 72)
    if fails:
        print(f"GATE 1: FAIL — {len(fails)} failing check(s): "
              f"{[c[0] for c in fails]}. Fix data before Phase 2.")
        return 1
    if warns:
        print(f"GATE 1: PASS WITH WARNINGS — {[c[0] for c in warns]} "
              f"(documented degradations, review before proceeding).")
        return 0
    print("GATE 1: PASS — all checks green. Cleared for Phase 2.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
