"""Rankings (full universe + search), sparklines (batch), performance
(precomputed backtest series) — Step 11.5 frontend enablers."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.ml.predict import CHAMPION_VERSION

router = APIRouter()


# ------------------------------------------------------ /api/rankings

class RankingRow(BaseModel):
    rank: int
    ticker: str
    name: str
    sector: str | None
    alpha_score: float
    predicted_return_30d: float | None


class RankingsResponse(BaseModel):
    date: str
    total: int
    offset: int
    rows: list[RankingRow]


def fetch_all_predictions(pred_date: str, model_version: str) -> list[dict]:
    from app.utils.db import supabase

    rows, page = [], 0
    while True:
        resp = (
            supabase.table("predictions")
            .select("company_id,alpha_score,predicted_return_30d")
            .eq("date", pred_date).eq("model_version", model_version)
            .order("alpha_score", desc=True)
            .range(page * 1000, page * 1000 + 999)
            .execute()
        )
        rows.extend(resp.data)
        if len(resp.data) < 1000:
            break
        page += 1
    return rows


@router.get("/api/rankings", response_model=RankingsResponse)
def get_rankings(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    search: str | None = Query(None, min_length=1, max_length=40),
):
    from app.api.picks import fetch_companies, fetch_latest_prediction_date

    pred_date = fetch_latest_prediction_date(CHAMPION_VERSION)
    if pred_date is None:
        raise HTTPException(404, "no predictions available")
    preds = fetch_all_predictions(pred_date, CHAMPION_VERSION)
    companies = fetch_companies([p["company_id"] for p in preds])

    ranked = []
    for i, p in enumerate(preds, 1):
        c = companies.get(p["company_id"])
        if c is None:
            continue
        ranked.append(RankingRow(
            rank=i, ticker=c["ticker"], name=c["name"],
            sector=c.get("sector"), alpha_score=p["alpha_score"],
            predicted_return_30d=p.get("predicted_return_30d"),
        ))
    if search:
        needle = search.strip().lower()
        ranked = [r for r in ranked
                  if needle in r.ticker.lower() or needle in r.name.lower()]
    return RankingsResponse(date=pred_date, total=len(ranked), offset=offset,
                            rows=ranked[offset : offset + limit])


# ---------------------------------------------------- /api/sparklines

class SparklinesResponse(BaseModel):
    days: int
    series: dict[str, list[float]]  # ticker -> closes, oldest first


def fetch_sparklines(tickers: list[str], days: int) -> dict[str, list[float]]:
    """Single IN-query for all tickers (was N+1: 27 round-trips for 25
    tickers — review finding #4)."""
    from datetime import date, timedelta

    from app.utils.db import supabase

    comp = (
        supabase.table("companies").select("id,ticker")
        .in_("ticker", tickers).execute()
    )
    id_to_ticker = {r["id"]: r["ticker"] for r in comp.data}
    if not id_to_ticker:
        return {}
    start = (date.today() - timedelta(days=int(days * 1.6) + 10)).isoformat()
    rows, page = [], 0
    while True:
        resp = (
            supabase.table("price_features")
            .select("date,company_id,close")
            .in_("company_id", list(id_to_ticker))
            .gte("date", start)
            .order("id")
            .range(page * 1000, page * 1000 + 999)
            .execute()
        )
        rows.extend(resp.data)
        if len(resp.data) < 1000:
            break
        page += 1
    by_cid: dict[str, list[tuple[str, float]]] = {}
    for r in rows:
        if r["close"] is None:
            continue
        by_cid.setdefault(r["company_id"], []).append(
            (r["date"], float(r["close"])))
    out: dict[str, list[float]] = {}
    for cid, ticker in id_to_ticker.items():
        series = sorted(by_cid.get(cid, []))
        if series:
            out[ticker] = [v for _, v in series][-days:]
    return out


@router.get("/api/sparklines", response_model=SparklinesResponse)
def get_sparklines(
    tickers: str = Query(..., description="comma-separated, max 25"),
    days: int = Query(90, ge=10, le=260),
):
    wanted = [t.strip().upper() for t in tickers.split(",") if t.strip()][:25]
    if not wanted:
        raise HTTPException(422, "no tickers given")
    return SparklinesResponse(days=days, series=fetch_sparklines(wanted, days))


# --------------------------------------------------- /api/performance

class PerformancePoint(BaseModel):
    date: str
    strategy_equity: float
    benchmark_equity: float


class PerformanceResponse(BaseModel):
    points: list[PerformancePoint]
    sharpe: float | None
    ann_return: float | None
    benchmark_ann_return: float | None
    note: str = ("Walk-forward, monthly rebalance, 10bps/side costs. "
                 "Backtested — not indicative of future results.")


def fetch_performance() -> list[dict]:
    from app.utils.db import supabase

    rows, page = [], 0
    while True:
        resp = (
            supabase.table("performance_daily")
            .select("date,strategy_return,benchmark_return,"
                    "strategy_equity,benchmark_equity")
            .order("date")
            .range(page * 1000, page * 1000 + 999)
            .execute()
        )
        rows.extend(resp.data)
        if len(resp.data) < 1000:
            break
        page += 1
    return rows


@router.get("/api/performance", response_model=PerformanceResponse)
def get_performance():
    rows = fetch_performance()
    if not rows:
        raise HTTPException(
            404, "performance series not exported yet — run "
                 "scripts/export_performance.py")
    import numpy as np

    strat = np.array([float(r["strategy_return"]) for r in rows])
    bench = np.array([float(r["benchmark_return"]) for r in rows])
    n = len(strat)
    vol = strat.std(ddof=1) * np.sqrt(252)
    sharpe = float(strat.mean() * 252 / vol) if vol > 0 else None
    ann = float((1 + strat).prod() ** (252 / n) - 1)
    bench_ann = float((1 + bench).prod() ** (252 / n) - 1)
    return PerformanceResponse(
        points=[PerformancePoint(
            date=r["date"],
            strategy_equity=float(r["strategy_equity"]),
            benchmark_equity=float(r["benchmark_equity"]),
        ) for r in rows],
        sharpe=round(sharpe, 3) if sharpe else None,
        ann_return=round(ann, 4),
        benchmark_ann_return=round(bench_ann, 4),
    )
