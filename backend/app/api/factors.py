"""GET /api/factors/{ticker} — factor breakdown for one name (spec Step 9)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter()


class FactorBreakdown(BaseModel):
    ticker: str
    name: str
    sector: str | None
    date: str
    momentum_composite: float | None
    valuation_composite: float | None
    quality_composite: float | None
    insider_congress_composite: float | None


def fetch_company_by_ticker(ticker: str) -> dict | None:
    from app.utils.db import supabase

    resp = (
        supabase.table("companies")
        .select("id,ticker,name,sector")
        .eq("ticker", ticker.upper())
        .limit(1)
        .execute()
    )
    return resp.data[0] if resp.data else None


def fetch_factor_row(company_id: str, date: str | None) -> dict | None:
    from app.utils.db import supabase

    q = (
        supabase.table("factor_scores")
        .select("date,momentum_composite,valuation_composite,"
                "quality_composite,insider_congress_composite")
        .eq("company_id", company_id)
    )
    q = q.eq("date", date) if date else q.order("date", desc=True)
    resp = q.limit(1).execute()
    return resp.data[0] if resp.data else None


@router.get("/api/factors/{ticker}", response_model=FactorBreakdown)
def get_factors(ticker: str,
                date: str | None = Query(None, description="YYYY-MM-DD")):
    company = fetch_company_by_ticker(ticker)
    if company is None:
        raise HTTPException(404, f"unknown ticker {ticker!r}")
    row = fetch_factor_row(company["id"], date)
    if row is None:
        raise HTTPException(404, f"no factor scores for {ticker!r}"
                                 + (f" on {date}" if date else ""))
    return FactorBreakdown(ticker=company["ticker"], name=company["name"],
                           sector=company.get("sector"), **row)
