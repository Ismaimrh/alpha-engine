"""FastAPI entry point (spec Step 9: /backend/app/main.py).

Run locally:
    cd backend
    uvicorn app.main:app --reload
    open http://127.0.0.1:8000/docs

CORS origin comes from FRONTEND_ORIGIN (defaults to * for local dev;
set to the Vercel URL at deploy time, Step 12).
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.factors import router as factors_router
from app.api.picks import router as picks_router
from app.api.subscribe import router as subscribe_router
from app.api.rankings import router as rankings_router
from app.api.theses import router as theses_router

app = FastAPI(
    title="Alpha Engine API",
    version="0.1.0",
    description=("Factor-based S&P 500 ranking engine. Backtested signals, "
                 "not financial advice."),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_ORIGIN", "*")],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(picks_router)
app.include_router(factors_router)
app.include_router(subscribe_router)
app.include_router(theses_router)
app.include_router(rankings_router)


@app.get("/health")
def health() -> dict:
    """Liveness probe (Railway/UptimeRobot). Deliberately DB-free so a
    database hiccup doesn't flap the deployment health check."""
    return {"status": "ok", "service": "alpha-engine-api"}
