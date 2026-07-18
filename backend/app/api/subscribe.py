"""POST /api/subscribe and GET /api/stats (spec Step 9)."""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr

router = APIRouter()
log = logging.getLogger(__name__)

# Dependency-free per-IP rate limit (review #3). Fine for a single worker;
# swap for slowapi/redis if the API ever scales out.
_RATE_WINDOW_S, _RATE_MAX = 60, 5
_hits: dict[str, deque] = defaultdict(deque)


def _rate_limited(ip: str) -> bool:
    now = time.monotonic()
    q = _hits[ip]
    while q and now - q[0] > _RATE_WINDOW_S:
        q.popleft()
    if len(q) >= _RATE_MAX:
        return True
    q.append(now)
    return False


class SubscribeRequest(BaseModel):
    email: EmailStr
    source: str | None = "landing_page"


class SubscribeResponse(BaseModel):
    status: str
    email: str


def upsert_subscriber(email: str, source: str | None) -> None:
    from app.utils.db import supabase

    supabase.table("subscribers").upsert(
        {"email": email, "source": source}, on_conflict="email"
    ).execute()


@router.post("/api/subscribe", response_model=SubscribeResponse, status_code=201)
def subscribe(body: SubscribeRequest, request: Request):
    ip = request.client.host if request.client else "unknown"
    if _rate_limited(ip):
        raise HTTPException(429, "too many subscription attempts — try later")
    try:
        upsert_subscriber(body.email, body.source)
    except Exception as exc:  # noqa: BLE001
        log.exception("subscribe failed for %s", body.email)
        raise HTTPException(503, "subscription storage unavailable") from exc
    log.info("subscribed %s (source=%s, ip=%s)", body.email, body.source, ip)
    return SubscribeResponse(status="subscribed", email=body.email)


# ---------------------------------------------------------------- /api/stats

class StatsResponse(BaseModel):
    companies_in_universe: int
    latest_price_date: str | None
    latest_prediction_date: str | None
    model_versions: list[str]


def fetch_stats() -> dict:
    from app.utils.db import supabase

    companies = (
        supabase.table("companies").select("id", count="exact")
        .eq("in_universe", True).limit(1).execute()
    )
    price = (
        supabase.table("price_features").select("date")
        .order("date", desc=True).limit(1).execute()
    )
    pred = (
        supabase.table("predictions").select("date,model_version")
        .order("date", desc=True).limit(50).execute()
    )
    versions = sorted({r["model_version"] for r in pred.data}) if pred.data else []
    return {
        "companies_in_universe": companies.count or 0,
        "latest_price_date": price.data[0]["date"] if price.data else None,
        "latest_prediction_date": pred.data[0]["date"] if pred.data else None,
        "model_versions": versions,
    }


@router.get("/api/stats", response_model=StatsResponse)
def get_stats():
    return StatsResponse(**fetch_stats())


# ------------------------------------------------------- /api/unsubscribe

@router.get("/api/unsubscribe")
def unsubscribe(email: str, sig: str):
    """Signed one-click unsubscribe (link embedded in every daily email)."""
    from app.notify.daily_email import unsubscribe_sig

    if not hmac_compare(sig, unsubscribe_sig(email)):
        raise HTTPException(403, "invalid unsubscribe link")
    try:
        remove_subscriber(email)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, "unsubscribe storage unavailable") from exc
    return {"status": "unsubscribed", "email": email}


def hmac_compare(a: str, b: str) -> bool:
    import hmac as _hmac

    return _hmac.compare_digest(a, b)


def remove_subscriber(email: str) -> None:
    from app.utils.db import supabase

    supabase.table("subscribers").delete().eq("email", email).execute()
