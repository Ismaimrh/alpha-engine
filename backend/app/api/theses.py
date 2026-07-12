"""GET /api/thesis/{ticker} — the LLM-written thesis for one name (Step 11)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.factors import fetch_company_by_ticker

router = APIRouter()


class ThesisResponse(BaseModel):
    ticker: str
    date: str
    thesis_text: str
    model: str


def fetch_latest_thesis(company_id: str) -> dict | None:
    from app.utils.db import supabase

    resp = (
        supabase.table("llm_theses")
        .select("date,thesis_text,model")
        .eq("company_id", company_id)
        .order("date", desc=True)
        .limit(1)
        .execute()
    )
    return resp.data[0] if resp.data else None


@router.get("/api/thesis/{ticker}", response_model=ThesisResponse)
def get_thesis(ticker: str):
    company = fetch_company_by_ticker(ticker)
    if company is None:
        raise HTTPException(404, f"unknown ticker {ticker!r}")
    row = fetch_latest_thesis(company["id"])
    if row is None:
        raise HTTPException(404, f"no thesis for {ticker!r} yet")
    return ThesisResponse(ticker=company["ticker"], **row)
