"""Shadow simulation of signal-card issue thresholds.

Pre-registration: docs/CARD_THRESHOLD_PREREG.md. Measures the three
candidate selection rules over the STORED factor history without issuing,
writing, or touching a single live card.

    cd backend && python scripts/simulate_card_thresholds.py --dates 120

Reports per scheme and per signal column:
  cards/day, |Δ count| when the most extreme name is deleted (rule 1),
  mean |alpha| of issued cards vs T-FIXED (rule 2), and the usable-band
  check (rule 3). Prints a verdict line per rule; it does NOT change
  anything.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

FIXED_THRESHOLD = 1.0
QUANTILE_K = 0.05        # top/bottom 5% (registered)
HYBRID_FLOOR = 0.5       # conviction floor for T-HYBRID (registered)
BAND = (5, 40)           # usable cards/day per stream (registered)


def select_fixed(alpha: pd.Series) -> pd.Index:
    return alpha.index[alpha.abs() >= FIXED_THRESHOLD]


def select_quantile(alpha: pd.Series, k: float = QUANTILE_K) -> pd.Index:
    if alpha.empty:
        return alpha.index[:0]
    hi = alpha.quantile(1 - k)
    lo = alpha.quantile(k)
    return alpha.index[(alpha >= hi) | (alpha <= lo)]


def select_hybrid(alpha: pd.Series) -> pd.Index:
    q = set(select_quantile(alpha))
    return alpha.index[[i in q and abs(alpha[i]) >= HYBRID_FLOOR
                        for i in alpha.index]]


SCHEMES = {
    "T-FIXED (live)": select_fixed,
    "T-QUANTILE 5%": select_quantile,
    "T-HYBRID": select_hybrid,
}


def evaluate(panel: pd.DataFrame, column: str, dates: list) -> dict:
    stats = {name: {"n": [], "dn": [], "conv": []} for name in SCHEMES}
    for d in dates:
        day = panel.loc[panel["date"] == d]
        alpha = day.set_index("company_id")[column].astype(float).dropna()
        if len(alpha) < 100:
            continue
        extreme = alpha.abs().idxmax()
        alpha_minus = alpha.drop(index=extreme)
        for name, fn in SCHEMES.items():
            sel = fn(alpha)
            sel_minus = fn(alpha_minus)
            n, n_minus = len(sel), len(sel_minus)
            stats[name]["n"].append(n)
            if n:
                stats[name]["dn"].append(abs(n_minus - n) / n)
                stats[name]["conv"].append(float(alpha[sel].abs().mean()))
    return stats


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dates", type=int, default=120)
    parser.add_argument("--columns", default="momentum_composite,momentum_6_1")
    args = parser.parse_args()

    from app.factors.backfill_history import _fetch_all

    cols = [c.strip() for c in args.columns.split(",")]
    panel = _fetch_all(
        "factor_scores", "id,date,company_id," + ",".join(cols), "id")
    panel["date"] = pd.to_datetime(panel["date"]).dt.date
    panel = panel.drop_duplicates(subset=["date", "company_id"])
    all_dates = sorted(panel["date"].unique())[-args.dates:]

    print(f"shadow simulation over {len(all_dates)} dates "
          f"(no cards issued, nothing written)\n")
    for column in cols:
        stats = evaluate(panel, column, all_dates)
        base_conv = (np.mean(stats["T-FIXED (live)"]["conv"])
                     if stats["T-FIXED (live)"]["conv"] else np.nan)
        print(f"=== {column} ===")
        print(f"  {'scheme':<16} {'cards/day':>10} {'Δcount':>8} "
              f"{'mean|α|':>9} {'vs live':>8}  rules 1/2/3")
        print("  " + "-" * 66)
        for name in SCHEMES:
            s = stats[name]
            if not s["n"]:
                continue
            n = float(np.mean(s["n"]))
            dn = float(np.mean(s["dn"])) if s["dn"] else float("nan")
            conv = float(np.mean(s["conv"])) if s["conv"] else float("nan")
            ratio = conv / base_conv if np.isfinite(base_conv) else np.nan
            r1 = "ok" if dn < 0.10 else "FAIL"
            r2 = "ok" if ratio >= 0.70 else "FAIL"
            r3 = "ok" if BAND[0] <= n <= BAND[1] else "FAIL"
            print(f"  {name:<16} {n:>10.1f} {dn:>7.1%} {conv:>9.2f} "
                  f"{ratio:>7.0%}  {r1}/{r2}/{r3}")
        print()
    print("Rules (pre-registered, docs/CARD_THRESHOLD_PREREG.md):")
    print("  1 count stability: mean |Δ count| after deleting the most")
    print("    extreme name must be < 10%")
    print("  2 conviction retention: mean |alpha| >= 70% of T-FIXED's")
    print("  3 usable band: 5-40 cards/day")
    print("  If none passes all three, T-FIXED STAYS.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
