"""Signal Phase S1.5 — GET /api/signals, /api/signals/ledger, /api/hitrate.

D4 honesty rules are enforced HERE, at the API boundary: hit-rate carries
Wilson CI + N always, and reports state="collecting" below N=30 resolved.
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel

MIN_N_FOR_DISPLAY = 30  # spec D4

# Pre-registered success bars = empirical null + 5pp (spec v1.2 Appendix A,
# measured 2026-07-19). Wilson lower bound must exceed these at N>=30.
NULL_BARS = {
    21: {"BUY": 0.422, "AVOID": 0.313},
    63: {"BUY": 0.460, "AVOID": 0.280},
}

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
    open_cards: list[SignalCard]                 # all, for back-compat
    by_horizon: dict[str, list[SignalCard]] = {}  # "21"/"63" -> cards (D7)
    note: str = ("Resolution uses daily closes (close-touch rule) — intraday "
                 "touches do not trigger. Horizons are reported separately. "
                 "See methodology.")


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


class HorizonHitRate(BaseModel):
    horizon_days: int
    by_direction: dict[str, DirectionStats]
    null_bars: dict[str, float]     # pre-registered null+5pp per direction


class HitRateResponse(BaseModel):
    state: str                      # overall collecting|reporting (21d BUY)
    n_resolved: int
    n_hit: int
    n_stop: int
    n_expired: int
    hit_rate: float | None
    wilson_low: float | None
    wilson_high: float | None
    avg_realized_return: float | None
    by_direction: dict[str, DirectionStats] = {}
    by_horizon: list[HorizonHitRate] = []   # D7: per-horizon, per-direction
    note: str = ("Hit rate = hits / (hits + stops), close-touch, expired "
                 "excluded but listed. Shown at N>=30 (pre-registered). "
                 "Bars are the empirical no-alpha null + 5pp, per direction "
                 "and horizon — never pooled.")
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
    rows, _ = fetch_cards(["open"], 0, 500)
    cards = [SignalCard(**_shape(r)) for r in rows]
    by_h: dict[str, list[SignalCard]] = {}
    for c in cards:
        by_h.setdefault(str(c.horizon_days), []).append(c)
    return SignalsResponse(open_cards=cards, by_horizon=by_h)


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
    horizons = []
    for h in sorted({int(r["horizon_days"]) for r in rows} | {21}):
        hrows = [r for r in rows if int(r["horizon_days"]) == h]
        horizons.append(HorizonHitRate(
            horizon_days=h,
            by_direction={d: _direction_stats(
                [r for r in hrows if r["direction"] == d])
                for d in ("BUY", "AVOID")},
            null_bars=NULL_BARS.get(h, {}),
        ))
    if n < MIN_N_FOR_DISPLAY:
        return HitRateResponse(state="collecting", n_resolved=n, n_hit=n_hit,
                               n_stop=n_stop, n_expired=n_exp, hit_rate=None,
                               wilson_low=None, wilson_high=None,
                               avg_realized_return=avg_ret,
                               by_direction=by_dir, by_horizon=horizons)
    lo, hi = wilson_ci(n_hit, n)
    return HitRateResponse(state="reporting", n_resolved=n, n_hit=n_hit,
                           n_stop=n_stop, n_expired=n_exp,
                           hit_rate=round(n_hit / n, 4),
                           wilson_low=lo, wilson_high=hi,
                           avg_realized_return=avg_ret,
                           by_direction=by_dir, by_horizon=horizons)


def _shape(r: dict) -> dict:
    keep = {"ticker", "issue_date", "direction", "alpha_score", "entry",
            "target", "stop", "sigma_21", "horizon_days", "status",
            "resolved_date", "resolved_close", "realized_return"}
    return {k: v for k, v in r.items() if k in keep}
