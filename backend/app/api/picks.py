"""GET /api/picks — the ranked daily picks (spec Step 9).

Data access is isolated in module functions so tests can monkeypatch them
without a live database.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.ml.predict import CHAMPION_VERSION

router = APIRouter()


class Pick(BaseModel):
    rank: int
    rank_change: int | None = None  # vs previous trading day (+ = climbed)
    ticker: str
    name: str
    sector: str | None
    alpha_score: float
    confidence: float | None
    predicted_return_30d: float | None
    position_size: float | None


class PicksResponse(BaseModel):
    date: str
    model_version: str
    count: int
    picks: list[Pick]
    disclaimer: str = ("Backtested signals, not financial advice. "
                       "Past performance does not guarantee future results.")


# ----------------------------------------------------------- data access

def fetch_latest_prediction_date(model_version: str) -> str | None:
    from app.utils.db import supabase

    resp = (
        supabase.table("predictions")
        .select("date")
        .eq("model_version", model_version)
        .order("date", desc=True)
        .limit(1)
        .execute()
    )
    return resp.data[0]["date"] if resp.data else None


def fetch_predictions(pred_date: str, model_version: str,
                      limit: int) -> list[dict]:
    from app.utils.db import supabase

    resp = (
        supabase.table("predictions")
        .select("company_id,alpha_score,confidence,predicted_return_30d,"
                "position_size")
        .eq("date", pred_date)
        .eq("model_version", model_version)
        .order("alpha_score", desc=True)
        .limit(limit)
        .execute()
    )
    return resp.data


def fetch_momentum_ranks(target_date: str) -> dict[str, int]:
    """company_id -> momentum rank (1 = best) on a factor_scores date."""
    from app.utils.db import supabase

    rows, page = [], 0
    while True:
        resp = (
            supabase.table("factor_scores")
            .select("company_id,momentum_composite")
            .eq("date", target_date)
            .order("momentum_composite", desc=True)
            .range(page * 1000, page * 1000 + 999)
            .execute()
        )
        rows.extend(resp.data)
        if len(resp.data) < 1000:
            break
        page += 1
    return {r["company_id"]: i for i, r in enumerate(
        (r for r in rows if r["momentum_composite"] is not None), 1)}


def fetch_previous_factor_date(before: str) -> str | None:
    from app.utils.db import supabase

    resp = (
        supabase.table("factor_scores").select("date")
        .lt("date", before).order("date", desc=True).limit(1).execute()
    )
    return resp.data[0]["date"] if resp.data else None


def fetch_companies(company_ids: list[str]) -> dict[str, dict]:
    from app.utils.db import supabase

    resp = (
        supabase.table("companies")
        .select("id,ticker,name,sector")
        .in_("id", company_ids)
        .execute()
    )
    return {row["id"]: row for row in resp.data}


# ----------------------------------------------------------------- route

@router.get("/api/picks", response_model=PicksResponse)
def get_picks(
    date: str | None = Query(None, description="YYYY-MM-DD; default latest"),
    limit: int = Query(20, ge=1, le=100),
    model: str = Query(CHAMPION_VERSION, description="model_version"),
) -> PicksResponse:
    pred_date = date or fetch_latest_prediction_date(model)
    if pred_date is None:
        raise HTTPException(404, "no predictions available for this model")
    rows = fetch_predictions(pred_date, model, limit)
    if not rows:
        raise HTTPException(404, f"no predictions for {pred_date}")
    companies = fetch_companies([r["company_id"] for r in rows])
    prev_date = fetch_previous_factor_date(pred_date)
    today_ranks = fetch_momentum_ranks(pred_date) if prev_date else {}
    prev_ranks = fetch_momentum_ranks(prev_date) if prev_date else {}
    picks = []
    for i, r in enumerate(rows, 1):
        c = companies.get(r["company_id"])
        if c is None:
            continue
        cid = r["company_id"]
        change = (prev_ranks[cid] - today_ranks[cid]
                  if cid in prev_ranks and cid in today_ranks else None)
        picks.append(Pick(
            rank=i, rank_change=change,
            ticker=c["ticker"], name=c["name"], sector=c.get("sector"),
            alpha_score=r["alpha_score"], confidence=r.get("confidence"),
            predicted_return_30d=r.get("predicted_return_30d"),
            position_size=r.get("position_size"),
        ))
    return PicksResponse(date=pred_date, model_version=model,
                         count=len(picks), picks=picks)
