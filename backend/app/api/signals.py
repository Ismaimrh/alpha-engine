"""Signal Phase S1.5 — GET /api/signals, /api/signals/ledger, /api/hitrate.

D4 honesty rules are enforced HERE, at the API boundary: hit-rate carries
Wilson CI + N always, and reports state="collecting" below N=30 resolved.
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel

MIN_N_FOR_DISPLAY = 30  # spec D4

router = APIRouter()


class SignalCard(BaseModel):
    ticker: str
    issue_date: str
    direction: str
    alpha_score: float
    entry: float
    target: float
    stop: float
    sigma_21: float
    horizon_days: int
    status: str
    resolved_date: str | None = None
    resolved_close: float | None = None
    realized_return: float | None = None


class SignalsResponse(BaseModel):
    open_cards: list[SignalCard]
    note: str = ("Resolution uses daily closes (close-touch rule) — intraday "
                 "touches do not trigger. See methodology.")


class LedgerResponse(BaseModel):
    cards: list[SignalCard]
    total: int
    offset: int
    limit: int


class DirectionStats(BaseModel):
    state: str
    n_resolved: int
    n_hit: int
    n_stop: int
    n_expired: int
    hit_rate: float | None
    wilson_low: float | None
    wilson_high: float | None


class HitRateResponse(BaseModel):
    state: str                      # "collecting" | "reporting"
    n_resolved: int                 # hit + stop (expired excluded, D4)
    n_hit: int
    n_stop: int
    n_expired: int
    hit_rate: float | None          # None while collecting
    wilson_low: float | None
    wilson_high: float | None
    avg_realized_return: float | None
    by_direction: dict[str, DirectionStats] = {}  # v1.2: BUY/AVOID nulls
                                                  # differ ~2x — never pool
    note: str = ("Hit rate = hits / (hits + stops), close-touch rule, "
                 "expired cards excluded but listed in the ledger. "
                 "Displayed only once N >= 30 resolved (pre-registered).")


def fetch_cards(status_filter: list[str] | None, offset: int, limit: int):
    from app.utils.db import supabase

    q = supabase.table("signal_cards").select("*", count="exact")
    if status_filter:
        q = q.in_("status", status_filter)
    resp = (q.order("issue_date", desc=True).order("alpha_score", desc=True)
            .range(offset, offset + limit - 1).execute())
    return resp.data, (resp.count or 0)


@router.get("/api/signals", response_model=SignalsResponse)
def get_signals():
    rows, _ = fetch_cards(["open"], 0, 200)
    return SignalsResponse(open_cards=[SignalCard(**_shape(r)) for r in rows])


@router.get("/api/signals/ledger", response_model=LedgerResponse)
def get_ledger(offset: int = Query(0, ge=0),
               limit: int = Query(50, ge=1, le=200)):
    rows, total = fetch_cards(["hit", "stop", "expired"], offset, limit)
    return LedgerResponse(cards=[SignalCard(**_shape(r)) for r in rows],
                          total=total, offset=offset, limit=limit)


def _direction_stats(rows: list[dict]) -> "DirectionStats":
    from app.signals.resolve import wilson_ci

    n_hit = sum(1 for r in rows if r["status"] == "hit")
    n_stop = sum(1 for r in rows if r["status"] == "stop")
    n_exp = sum(1 for r in rows if r["status"] == "expired")
    n = n_hit + n_stop
    if n < MIN_N_FOR_DISPLAY:
        return DirectionStats(state="collecting", n_resolved=n, n_hit=n_hit,
                              n_stop=n_stop, n_expired=n_exp, hit_rate=None,
                              wilson_low=None, wilson_high=None)
    lo, hi = wilson_ci(n_hit, n)
    return DirectionStats(state="reporting", n_resolved=n, n_hit=n_hit,
                          n_stop=n_stop, n_expired=n_exp,
                          hit_rate=round(n_hit / n, 4),
                          wilson_low=lo, wilson_high=hi)


@router.get("/api/hitrate", response_model=HitRateResponse)
def get_hitrate():
    from app.signals.resolve import wilson_ci

    rows, _ = fetch_cards(["hit", "stop", "expired"], 0, 10000)
    n_hit = sum(1 for r in rows if r["status"] == "hit")
    n_stop = sum(1 for r in rows if r["status"] == "stop")
    n_exp = sum(1 for r in rows if r["status"] == "expired")
    n = n_hit + n_stop
    rets = [float(r["realized_return"]) for r in rows
            if r.get("realized_return") is not None]
    avg_ret = round(sum(rets) / len(rets), 6) if rets else None
    by_dir = {d: _direction_stats([r for r in rows if r["direction"] == d])
              for d in ("BUY", "AVOID")}
    if n < MIN_N_FOR_DISPLAY:
        return HitRateResponse(state="collecting", n_resolved=n, n_hit=n_hit,
                               n_stop=n_stop, n_expired=n_exp, hit_rate=None,
                               wilson_low=None, wilson_high=None,
                               avg_realized_return=avg_ret,
                               by_direction=by_dir)
    lo, hi = wilson_ci(n_hit, n)
    return HitRateResponse(state="reporting", n_resolved=n, n_hit=n_hit,
                           n_stop=n_stop, n_expired=n_exp,
                           hit_rate=round(n_hit / n, 4),
                           wilson_low=lo, wilson_high=hi,
                           avg_realized_return=avg_ret,
                           by_direction=by_dir)


def _shape(r: dict) -> dict:
    keep = {"ticker", "issue_date", "direction", "alpha_score", "entry",
            "target", "stop", "sigma_21", "horizon_days", "status",
            "resolved_date", "resolved_close", "realized_return"}
    return {k: v for k, v in r.items() if k in keep}
