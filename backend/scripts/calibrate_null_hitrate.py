"""Derive the NO-ALPHA hit rate empirically (spec v1.2 item 1).

The S1 success bar was set at 40% from an arithmetic-barrier argument; the
external review correctly noted geometric-BM log-barriers imply ~44-47%,
and BOTH are wrong for our actual rule (discrete daily close-touch, finite
horizon, expiry excluded from the denominator). The only defensible bar is
simulated through the REAL resolver on EMPIRICAL returns:

  For each simulated card: pick a random company, a random start date with
  enough forward history, direction at random, build the D2 envelope from
  its actual trailing 63d vol, and walk resolve_card_path over its ACTUAL
  subsequent closes. The signal contains zero information by construction;
  whatever hit rate emerges is the envelope's own geometry + the market's
  drift/fat tails. The pre-registered bar becomes that rate + 5pp.

    cd backend && python scripts/calibrate_null_hitrate.py --n 10000

Prints BUY and AVOID null rates separately (mirrored geometry differs),
for both 21d and 63d horizons. Paste the table into the spec appendix.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from app.signals.cards import STOP_K, TARGET_K
from app.signals.resolve import resolve_card_path


def simulate(wide: pd.DataFrame, n: int, horizon: int, rng) -> dict:
    dates = list(wide.index)
    cols = list(wide.columns)
    need_hist, need_fwd = 63, horizon + 1
    counts = {"BUY": {"hit": 0, "stop": 0, "expired": 0},
              "AVOID": {"hit": 0, "stop": 0, "expired": 0}}
    done = 0
    while done < n:
        cid = cols[rng.integers(len(cols))]
        series = wide[cid].dropna()
        if len(series) < need_hist + need_fwd + 1:
            continue
        ix = int(rng.integers(need_hist, len(series) - need_fwd))
        entry = float(series.iloc[ix])
        rets = series.iloc[ix - 63 : ix].pct_change().dropna()
        vol = float(rets.std(ddof=1))
        if not np.isfinite(vol) or vol <= 0 or entry <= 0:
            continue
        s = vol * np.sqrt(horizon)
        target, stop = entry * (1 + TARGET_K * s), entry * (1 - STOP_K * s)
        direction = "BUY" if rng.random() < 0.5 else "AVOID"
        out = resolve_card_path(direction, entry, target, stop,
                                series.iloc[ix + 1 :], horizon)
        if out is None:
            continue
        counts[direction][out["status"]] += 1
        done += 1
    result = {}
    for d, c in counts.items():
        resolved = c["hit"] + c["stop"]
        result[d] = {"n": done and sum(c.values()), "hit": c["hit"],
                     "stop": c["stop"], "expired": c["expired"],
                     "null_hit_rate": round(c["hit"] / resolved, 4)
                     if resolved else None}
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    from app.factors.backfill_history import _fetch_all

    closes = _fetch_all("price_features", "id,date,company_id,close", "id")
    closes["date"] = pd.to_datetime(closes["date"]).dt.date
    closes = closes.drop_duplicates(subset=["date", "company_id"])
    wide = (closes.pivot(index="date", columns="company_id", values="close")
            .sort_index().astype(float))
    rng = np.random.default_rng(args.seed)
    print(f"panel: {wide.shape[0]} dates x {wide.shape[1]} names; "
          f"{args.n} null cards per horizon\n")
    for horizon in (21, 63):
        res = simulate(wide, args.n, horizon, rng)
        print(f"--- horizon {horizon}d (envelope {TARGET_K}σ/{STOP_K}σ, "
              f"close-touch, expired excluded) ---")
        for d in ("BUY", "AVOID"):
            r = res[d]
            print(f"  {d:<6} null hit rate: {r['null_hit_rate']}   "
                  f"(hit {r['hit']} / stop {r['stop']} / "
                  f"expired {r['expired']})")
        print()
    print("Pre-registered bar per spec v1.2 = null rate + 5pp, per "
          "direction and horizon. Paste this output into the spec appendix.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
