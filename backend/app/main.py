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
from app.api.models import router as models_router
from app.api.rankings import router as rankings_router
from app.api.signals import router as signals_router
from app.api.stock import router as stock_router
from app.api.theses import router as theses_router

app = FastAPI(
    title="Alpha Engine API",
    version="0.1.0",
    description=("Factor-based S&P 500 ranking engine. Backtested signals, "
                 "not financial advice."),
)

_origin = (os.getenv("FRONTEND_ORIGIN") or "").strip()
if not _origin:
    import logging
    logging.getLogger(__name__).warning(
        "FRONTEND_ORIGIN unset — CORS is FAIL-CLOSED (no browser origins "
        "allowed). Set it to the frontend URL in production."
    )
app.add_middleware(
    CORSMiddleware,
    allow_origins=[_origin] if _origin else [],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
    allow_credentials=False,
)

app.include_router(picks_router)
app.include_router(factors_router)
app.include_router(subscribe_router)
app.include_router(theses_router)
app.include_router(rankings_router)
app.include_router(models_router)
app.include_router(signals_router)
app.include_router(stock_router)


@app.get("/health")
def health() -> dict:
    """Liveness probe (Railway/UptimeRobot). Deliberately DB-free so a
    database hiccup doesn't flap the deployment health check."""
    return {"status": "ok", "service": "alpha-engine-api"}
