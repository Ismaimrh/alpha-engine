"""SignalCard construction (Signal Phase S1.2, spec D1/D2).

Pure core: build_cards() maps the champion cross-section + vol inputs to
issuable cards. Thin DB wrapper issue_cards() writes them idempotently.
Constants are PRE-REGISTERED in docs/SIGNAL_PHASE_SPEC.md — changing them
requires a spec version bump, not a quiet edit.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

# --- D1: direction thresholds (spec v1) ---
BUY_THRESHOLD = 1.0
AVOID_THRESHOLD = -1.0
# --- D2: vol-scaled envelope (spec v1) ---
TARGET_K = 1.5
STOP_K = 1.0
HORIZON_DAYS = 21


def sigma_21_from_daily_vol(daily_vol: float, horizon: int = HORIZON_DAYS) -> float:
    """Horizon sigma from realized daily vol (63d window upstream).
    S2: sigma scales with sqrt(horizon) — 63d envelopes are wider."""
    return float(daily_vol) * float(np.sqrt(horizon))


def build_cards(
    issue_date: date,
    alpha: pd.Series,           # company_id -> champion alpha_score
    closes: pd.Series,          # company_id -> latest close
    daily_vol: pd.Series,       # company_id -> realized 63d daily vol
    tickers: pd.Series,         # company_id -> ticker
    expires_date: date,
    model_version: str,
    horizon_days: int = HORIZON_DAYS,
) -> list[dict]:
    """Apply D1 selection + D2 envelope. Rows with any missing/invalid
    input are skipped (a card with a NaN stop is worse than no card)."""
    cards: list[dict] = []
    for cid, a in alpha.items():
        if not np.isfinite(a):
            continue
        if a >= BUY_THRESHOLD:
            direction = "BUY"
        elif a <= AVOID_THRESHOLD:
            direction = "AVOID"
        else:
            continue
        entry = closes.get(cid)
        vol = daily_vol.get(cid)
        ticker = tickers.get(cid)
        if (entry is None or vol is None or ticker is None
                or not np.isfinite(entry) or not np.isfinite(vol)
                or entry <= 0 or vol <= 0):
            continue
        s21 = sigma_21_from_daily_vol(vol, horizon=horizon_days)
        cards.append({
            "company_id": cid,
            "ticker": str(ticker),
            "issue_date": issue_date.isoformat(),
            "model_version": model_version,
            "horizon_days": horizon_days,
            "direction": direction,
            "alpha_score": round(float(a), 4),
            "entry": round(float(entry), 4),
            "target": round(float(entry) * (1 + TARGET_K * s21), 4),
            "stop": round(float(entry) * (1 - STOP_K * s21), 4),
            "sigma_21": round(s21, 6),
            "expires_date": expires_date.isoformat(),
        })
    return cards


# ------------------------------------------------------------------ DB layer

# (model_version, horizon_days, calendar_expiry_days) per issuing stream.
# S2 adds the 63d position stream; 21d swing cards unchanged.
ISSUING_STREAMS: list[tuple[str, int, int]] = []  # filled below to avoid import cycle


def issue_cards() -> dict:
    """Issue today's cards for every issuing stream (21d swing from the
    champion; 63d position from cand-mom61-63d-v1 — spec v1.1/S2).
    Idempotent via the unique key (re-runs upsert identical rows)."""
    from app.api.picks import fetch_latest_prediction_date
    from app.factors.backfill_history import _fetch_all
    from app.factors.compute import fetch_trailing_stats
    from app.ml.predict import CHAMPION_VERSION, MOM61_63D_VERSION
    from app.utils.db import supabase

    streams = [(CHAMPION_VERSION, HORIZON_DAYS, 31),
               (MOM61_63D_VERSION, 63, 93)]

    pred_date_s = fetch_latest_prediction_date(CHAMPION_VERSION)
    if pred_date_s is None:
        return {"issued": 0, "note": "no predictions yet"}
    pred_date = date.fromisoformat(pred_date_s)

    preds_all = _fetch_all("predictions",
                           "id,date,company_id,model_version,alpha_score", "id")
    preds_all = preds_all.loc[
        pd.to_datetime(preds_all["date"]).dt.date == pred_date]

    comp = supabase.table("companies").select("id,ticker").execute()
    tickers = pd.Series({r["id"]: r["ticker"] for r in comp.data})

    # latest closes from the panel
    rows, page = [], 0
    while True:
        resp = (supabase.table("price_features")
                .select("company_id,close")
                .eq("date", pred_date.isoformat())
                .order("id").range(page * 1000, page * 1000 + 999).execute())
        rows.extend(resp.data)
        if len(resp.data) < 1000:
            break
        page += 1
    closes = pd.Series({r["company_id"]: r["close"] for r in rows}).astype(float)

    _, vol63 = fetch_trailing_stats(pred_date)

    # expiry = issue + HORIZON trading days, approximated from the stored
    # date grid at resolution time; at issue we store calendar +31d and the
    # resolver treats expiry by trading-day count (authoritative).
    from datetime import timedelta

    cards: list[dict] = []
    per_stream: dict[str, int] = {}
    for model, horizon, cal_days in streams:
        p = (preds_all.loc[preds_all["model_version"] == model]
             .drop_duplicates(subset=["company_id"]))
        if p.empty:
            per_stream[model] = 0
            continue
        alpha = p.set_index("company_id")["alpha_score"].astype(float)
        stream_cards = build_cards(
            pred_date, alpha, closes, vol63, tickers,
            pred_date + timedelta(days=cal_days), model,
            horizon_days=horizon,
        )
        per_stream[model] = len(stream_cards)
        cards.extend(stream_cards)
    if not cards:
        return {"issued": 0, "date": pred_date.isoformat(), **per_stream}
    for i in range(0, len(cards), 500):
        supabase.table("signal_cards").upsert(
            cards[i : i + 500],
            on_conflict="company_id,issue_date,horizon_days,model_version",
        ).execute()
    n_buy = sum(1 for c in cards if c["direction"] == "BUY")
    return {"issued": len(cards), "buy": n_buy, "avoid": len(cards) - n_buy,
            "date": pred_date.isoformat(), **per_stream}
