"""GET /api/stock/{ticker} — consolidated detail payload for one name.
Product batch 2: everything the /stock/[ticker] page needs in ONE call
(company, 1y closes, 90d factor history, per-model latest predictions,
signal cards) — the page must not re-create the N+1 pattern client-side.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

PRICE_DAYS = 260
FACTOR_DAYS = 90


class PricePoint(BaseModel):
    date: str
    close: float


class FactorPoint(BaseModel):
    date: str
    momentum: float | None
    valuation: float | None
    quality: float | None
    insider_congress: float | None


class ModelView(BaseModel):
    model_version: str
    alpha_score: float
    predicted_return_30d: float | None
    rank: int | None


class StockCard(BaseModel):
    issue_date: str
    direction: str
    entry: float
    target: float
    stop: float
    status: str
    resolved_date: str | None = None
    realized_return: float | None = None


class StockResponse(BaseModel):
    ticker: str
    name: str
    sector: str | None
    date: str                       # latest data date
    prices: list[PricePoint]
    factors: list[FactorPoint]
    models: list[ModelView]
    cards: list[StockCard]
    thesis: str | None


def fetch_company(ticker: str) -> dict | None:
    from app.utils.db import supabase

    resp = (supabase.table("companies").select("id,ticker,name,sector")
            .eq("ticker", ticker.upper()).limit(1).execute())
    return resp.data[0] if resp.data else None


def fetch_price_series(company_id: str, days: int = PRICE_DAYS) -> list[dict]:
    from app.utils.db import supabase

    resp = (supabase.table("price_features").select("date,close")
            .eq("company_id", company_id).order("date", desc=True)
            .limit(days).execute())
    rows = [r for r in resp.data if r["close"] is not None]
    return sorted(rows, key=lambda r: r["date"])


def fetch_factor_series(company_id: str, days: int = FACTOR_DAYS) -> list[dict]:
    from app.utils.db import supabase

    resp = (supabase.table("factor_scores")
            .select("date,momentum_composite,valuation_composite,"
                    "quality_composite,insider_congress_composite")
            .eq("company_id", company_id).order("date", desc=True)
            .limit(days).execute())
    return sorted(resp.data, key=lambda r: r["date"])


def fetch_model_views(company_id: str, pred_date: str) -> list[dict]:
    """Latest alpha/return for this name under every tracked model, plus
    the name's rank within each model's cross-section."""
    from app.utils.db import supabase

    out = []
    resp = (supabase.table("predictions")
            .select("model_version,alpha_score,predicted_return_30d")
            .eq("company_id", company_id).eq("date", pred_date).execute())
    for row in resp.data:
        higher = (supabase.table("predictions")
                  .select("id", count="exact")
                  .eq("date", pred_date)
                  .eq("model_version", row["model_version"])
                  .gt("alpha_score", row["alpha_score"])
                  .limit(1).execute())
        out.append({**row, "rank": (higher.count or 0) + 1})
    return sorted(out, key=lambda r: r["model_version"])


def fetch_stock_cards(company_id: str) -> list[dict]:
    from app.utils.db import supabase

    resp = (supabase.table("signal_cards")
            .select("issue_date,direction,entry,target,stop,status,"
                    "resolved_date,realized_return")
            .eq("company_id", company_id).order("issue_date", desc=True)
            .limit(20).execute())
    return resp.data


def fetch_thesis_text(company_id: str, pred_date: str) -> str | None:
    """Delegates to the proven Step-11 fetcher (table llm_theses, column
    thesis_text) — a hand-rolled duplicate here shipped a 500 by querying
    a nonexistent 'theses' table. Reuse beats memory."""
    from app.api.theses import fetch_latest_thesis

    row = fetch_latest_thesis(company_id)
    return row["thesis_text"] if row else None


def _safe_thesis(cid: str, pred_date: str) -> str | None:
    try:
        return fetch_thesis_text(cid, pred_date)
    except Exception:  # noqa: BLE001 — thesis is garnish, page must render
        return None


@router.get("/api/stock/{ticker}", response_model=StockResponse)
def get_stock(ticker: str):
    from app.api.picks import fetch_latest_prediction_date
    from app.ml.predict import CHAMPION_VERSION

    company = fetch_company(ticker)
    if company is None:
        raise HTTPException(404, f"unknown ticker: {ticker}")
    pred_date = fetch_latest_prediction_date(CHAMPION_VERSION)
    if pred_date is None:
        raise HTTPException(404, "no predictions yet")
    cid = company["id"]
    return StockResponse(
        ticker=company["ticker"],
        name=company["name"],
        sector=company.get("sector"),
        date=pred_date,
        prices=[PricePoint(date=r["date"], close=float(r["close"]))
                for r in fetch_price_series(cid)],
        factors=[FactorPoint(
            date=r["date"],
            momentum=r.get("momentum_composite"),
            valuation=r.get("valuation_composite"),
            quality=r.get("quality_composite"),
            insider_congress=r.get("insider_congress_composite"),
        ) for r in fetch_factor_series(cid)],
        models=[ModelView(**r) for r in fetch_model_views(cid, pred_date)],
        cards=[StockCard(**r) for r in fetch_stock_cards(cid)],
        thesis=_safe_thesis(cid, pred_date),
    )
