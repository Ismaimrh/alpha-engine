"""SignalCard resolution (Signal Phase S1.4, spec rule D3).

D3, close-touch: a card resolves at the FIRST post-issue trading day where
  close >= target  -> HIT     (for BUY; mirrored for AVOID)
  close <= stop    -> STOP    (for BUY; mirrored for AVOID)
and if neither occurs within horizon trading days -> EXPIRED (realized
return recorded; excluded from hit-rate, shown in the ledger — D4).

AVOID cards mirror the envelope: they "hit" when the name FALLS to the
downside target (entry * (1 - TARGET_K * sigma)) and "stop" when it rises
to entry * (1 + STOP_K * sigma). The stored target/stop columns are always
the BUY-frame prices; the mirroring lives here, in one place, tested.

Resolution fields are written exactly once (status transitions only from
'open'); the ledger stays append-only in spirit — no card is ever re-resolved.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd


def resolve_card_path(
    direction: str,
    entry: float,
    target: float,
    stop: float,
    closes_after: pd.Series,  # date-indexed closes AFTER issue, ascending
    horizon_days: int,
    series_terminated: bool = False,  # D3(d): ticker delisted/left universe
) -> dict | None:
    """Pure D3 walk. Returns {status, resolved_date, resolved_close,
    realized_return} or None if still open and unexpired.

    D3(d) (spec v1.2): if the price series has TERMINATED (delisting via
    M&A or bankruptcy, index removal without further data) the card cannot
    stay open forever — it resolves at the last available close: the walk
    still checks touch events on the available path first (a bankruptcy
    slide hits the stop on the way down; an M&A pop hits the target), and
    only a terminated no-event path resolves as expired-at-last-close."""
    if closes_after.empty:
        return None
    window = closes_after.iloc[:horizon_days]
    if direction == "BUY":
        hit_level, stop_level = target, stop
        hit_cmp = window >= hit_level
        stop_cmp = window <= stop_level
    else:  # AVOID mirrors around entry
        hit_level = entry - (target - entry)   # downside target
        stop_level = entry + (entry - stop)    # upside stop
        hit_cmp = window <= hit_level
        stop_cmp = window >= stop_level

    hit_ix = hit_cmp.idxmax() if hit_cmp.any() else None
    stop_ix = stop_cmp.idxmax() if stop_cmp.any() else None

    if hit_ix is not None and (stop_ix is None or hit_ix <= stop_ix):
        status, when = "hit", hit_ix
    elif stop_ix is not None:
        status, when = "stop", stop_ix
    elif len(window) >= horizon_days:
        status, when = "expired", window.index[-1]
    elif series_terminated:
        status, when = "expired", window.index[-1]  # D3(d) terminal case
    else:
        return None  # open, horizon not elapsed

    close = float(closes_after.loc[when])
    raw_ret = close / entry - 1.0
    realized = raw_ret if direction == "BUY" else -raw_ret  # AVOID profits on falls
    return {"status": status, "resolved_date": when,
            "resolved_close": round(close, 4),
            "realized_return": round(float(realized), 6)}


# ------------------------------------------------------------------ DB layer

def resolve_open_cards() -> dict:
    """Resolve every open card whose path has a D3 event or elapsed horizon."""
    from app.factors.backfill_history import _fetch_all
    from app.utils.db import supabase

    open_cards = _fetch_all(
        "signal_cards",
        "id,company_id,ticker,issue_date,direction,entry,target,stop,"
        "horizon_days,status",
        "id",
    )
    if open_cards.empty:
        return {"resolved": 0, "note": "no cards issued yet"}
    open_cards = open_cards.loc[open_cards["status"] == "open"]
    if open_cards.empty:
        return {"resolved": 0, "note": "no open cards"}

    closes = _fetch_all("price_features", "id,date,company_id,close", "id")
    closes["date"] = pd.to_datetime(closes["date"]).dt.date
    closes = closes.drop_duplicates(subset=["date", "company_id"])
    wide = (closes.pivot(index="date", columns="company_id", values="close")
            .sort_index().astype(float))

    panel_last = wide.index.max()
    counts = {"hit": 0, "stop": 0, "expired": 0}
    for _, card in open_cards.iterrows():
        cid = card["company_id"]
        if cid not in wide.columns:
            continue
        issue = pd.to_datetime(card["issue_date"]).date()
        series = wide[cid].dropna()
        after = series.loc[series.index > issue]
        # series terminated = no prints for >5 trading days while the panel
        # itself has moved on (delisting / index removal)
        terminated = (len(after) > 0
                      and (wide.index > after.index.max()).sum() > 5
                      and panel_last > after.index.max())
        outcome = resolve_card_path(
            card["direction"], float(card["entry"]), float(card["target"]),
            float(card["stop"]), after, int(card["horizon_days"]),
            series_terminated=terminated,
        )
        if outcome is None:
            continue
        supabase.table("signal_cards").update({
            "status": outcome["status"],
            "resolved_date": outcome["resolved_date"].isoformat(),
            "resolved_close": outcome["resolved_close"],
            "realized_return": outcome["realized_return"],
        }).eq("id", int(card["id"])).eq("status", "open").execute()
        counts[outcome["status"]] += 1
    return {"resolved": sum(counts.values()), **counts}


def wilson_ci(hits: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson 95% interval for the hit rate (spec D4)."""
    if n == 0:
        return (0.0, 0.0)
    p = hits / n
    denom = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    margin = (z / denom) * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2))
    return (round(max(0.0, center - margin), 4),
            round(min(1.0, center + margin), 4))
