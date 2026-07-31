"""Scoring-scheme diagnostic (docs/ROBUST_Z_PREREG.md, decision rule 3).

Measures, per scheme, on the latest N trading dates:
  - how many names cross |score| >= 1.0 (the signal-card threshold)
  - how that count CHANGES when the single most extreme name is removed
    and the universe is re-scored  <- the registered stability metric
  - top-50 book overlap vs the incumbent
  - Spearman rank correlation vs the incumbent

Prints a table. It does NOT decide anything: the predictive bar and the
non-inferiority test come from gate2_ic_analysis.py; this only breaks ties
among schemes that already passed those. Run:

    cd backend && python scripts/compare_scoring_schemes.py --dates 20
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from app.factors.cross_section import rank_normalize, robust_zscore, zscore

SCHEMES = {
    "S-PLAIN (live)": zscore,
    "S-ROBUST (MAD)": robust_zscore,
    "S-RANK (vdW)": rank_normalize,
}
THRESHOLD = 1.0


def crossings(scored: pd.Series) -> int:
    return int((scored.abs() >= THRESHOLD).sum())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dates", type=int, default=20)
    args = parser.parse_args()

    from app.factors.backfill_history import _fetch_all

    panel = _fetch_all(
        "price_features", "id,date,company_id,momentum_12_1", "id")
    panel["date"] = pd.to_datetime(panel["date"]).dt.date
    panel = panel.drop_duplicates(subset=["date", "company_id"])
    dates = sorted(panel["date"].unique())[-args.dates:]

    print(f"scoring schemes on momentum_12_1, last {len(dates)} dates, "
          f"threshold |score| >= {THRESHOLD}\n")
    print(f"  {'scheme':<16} {'cross':>7} {'cross-1':>8} {'Δ%':>7} "
          f"{'top50∩':>8} {'rankρ':>7}")
    print("  " + "-" * 58)

    base_by_date = {}
    rows = {name: {"cross": [], "cross1": [], "ov": [], "rho": []}
            for name in SCHEMES}
    for d in dates:
        day = panel.loc[panel["date"] == d].set_index("company_id")
        raw = day["momentum_12_1"].astype(float).dropna()
        if len(raw) < 100:
            continue
        # drop the single most extreme name (by plain z) and re-score
        extreme = (raw - raw.mean()).abs().idxmax()
        raw_minus = raw.drop(index=extreme)
        base = zscore(raw)
        base_by_date[d] = base
        base_top = set(base.nlargest(50).index)
        for name, fn in SCHEMES.items():
            s = fn(raw)
            s_minus = fn(raw_minus)
            rows[name]["cross"].append(crossings(s))
            rows[name]["cross1"].append(crossings(s_minus))
            rows[name]["ov"].append(
                len(set(s.nlargest(50).index) & base_top) / 50)
            rows[name]["rho"].append(s.corr(base, method="spearman"))

    for name in SCHEMES:
        r = rows[name]
        if not r["cross"]:
            continue
        c = sum(r["cross"]) / len(r["cross"])
        c1 = sum(r["cross1"]) / len(r["cross1"])
        delta = (c1 - c) / c * 100 if c else 0.0
        ov = sum(r["ov"]) / len(r["ov"])
        rho = sum(r["rho"]) / len(r["rho"])
        print(f"  {name:<16} {c:>7.1f} {c1:>8.1f} {delta:>6.1f}% "
              f"{ov:>7.0%} {rho:>7.3f}")

    print("\n  cross    = mean names crossing the threshold")
    print("  cross-1  = same, after deleting the single most extreme name")
    print("  Δ%       = stability metric (registered rule 3; smaller is more")
    print("             stable — the scale should not hinge on one name)")
    print("  top50∩   = book overlap vs the live scheme; rankρ = Spearman vs live")
    print("\n  Decision requires gate2 first (IC bar + non-inferiority).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
