"""GET /api/models — the live model race (champion vs candidates vs
challenger), and GET /api/sectors — sector-level alpha aggregation.
Product batch 1 (post-launch)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


# ------------------------------------------------------------- /api/models

class ModelTopPick(BaseModel):
    rank: int
    ticker: str
    alpha_score: float


class RealizedStats(BaseModel):
    n_days: int
    mean_ic: float | None
    t_stat: float | None
    hit_rate: float | None


class ModelCard(BaseModel):
    model_version: str
    role: str  # champion | candidate | challenger
    top10: list[ModelTopPick]
    realized: RealizedStats | None  # None until first outcomes resolve


class ModelsResponse(BaseModel):
    date: str
    models: list[ModelCard]
    overlap_top50: dict[str, float]  # "modelA vs modelB" -> fraction
    note: str = ("Promotion is data-driven: models are compared on REALIZED "
                 "prediction ICs (paper trading), never on backtests.")


def fetch_model_predictions(pred_date: str) -> dict[str, list[dict]]:
    """model_version -> predictions (desc alpha) for one date."""
    from app.utils.db import supabase

    rows, page = [], 0
    while True:
        resp = (
            supabase.table("predictions")
            .select("model_version,company_id,alpha_score")
            .eq("date", pred_date)
            .order("id")
            .range(page * 1000, page * 1000 + 999)
            .execute()
        )
        rows.extend(resp.data)
        if len(resp.data) < 1000:
            break
        page += 1
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r["model_version"], []).append(r)
    for model in out:
        out[model].sort(key=lambda r: r["alpha_score"], reverse=True)
    return out


def fetch_realized_ic_frame():
    """All resolved outcomes as a DataFrame (may be empty)."""
    import pandas as pd

    from app.factors.backfill_history import _fetch_all

    df = _fetch_all(
        "prediction_outcomes",
        "id,company_id,prediction_date,model_version,alpha_score,"
        "realized_excess_return",
        "id",
    )
    if not df.empty:
        df["prediction_date"] = pd.to_datetime(df["prediction_date"]).dt.date
    return df


def _role(model_version: str) -> str:
    from app.ml.predict import CHAMPION_VERSION

    if model_version == CHAMPION_VERSION:
        return "champion"
    if model_version.startswith("cand-"):
        return "candidate"
    return "challenger"


@router.get("/api/models", response_model=ModelsResponse)
def get_models():
    from app.api.picks import fetch_companies, fetch_latest_prediction_date
    from app.backtest.metrics import ic_summary
    from app.backtest.outcomes import realized_ic_by_day
    from app.ml.predict import CHAMPION_VERSION

    pred_date = fetch_latest_prediction_date(CHAMPION_VERSION)
    if pred_date is None:
        raise HTTPException(404, "no predictions yet")
    by_model = fetch_model_predictions(pred_date)
    all_ids = {r["company_id"] for rows in by_model.values() for r in rows[:50]}
    companies = fetch_companies(list(all_ids))
    outcomes = fetch_realized_ic_frame()

    cards, top50 = [], {}
    for model, rows in sorted(by_model.items(),
                              key=lambda kv: _role(kv[0])):
        top50[model] = {r["company_id"] for r in rows[:50]}
        realized = None
        if not outcomes.empty:
            ic = realized_ic_by_day(
                outcomes.loc[outcomes["model_version"] == model])
            if len(ic) > 0:
                s = ic_summary(ic)
                realized = RealizedStats(
                    n_days=s["n_days"], mean_ic=s["mean_ic"],
                    t_stat=s["t_stat"], hit_rate=s["hit_rate"])
        cards.append(ModelCard(
            model_version=model, role=_role(model),
            top10=[ModelTopPick(
                rank=i, ticker=companies[r["company_id"]]["ticker"],
                alpha_score=round(float(r["alpha_score"]), 4))
                for i, r in enumerate(rows[:10], 1)
                if r["company_id"] in companies],
            realized=realized,
        ))

    overlap = {}
    models = list(top50)
    for i, a in enumerate(models):
        for b in models[i + 1:]:
            denom = min(len(top50[a]), len(top50[b])) or 1
            overlap[f"{a} vs {b}"] = round(
                len(top50[a] & top50[b]) / denom, 3)
    return ModelsResponse(date=pred_date, models=cards,
                          overlap_top50=overlap)


# ------------------------------------------------------------ /api/sectors

class SectorRow(BaseModel):
    sector: str
    n: int
    mean_alpha: float
    top_ticker: str


class SectorsResponse(BaseModel):
    date: str
    sectors: list[SectorRow]


@router.get("/api/sectors", response_model=SectorsResponse)
def get_sectors():
    from app.api.picks import fetch_companies, fetch_latest_prediction_date
    from app.api.rankings import fetch_all_predictions
    from app.ml.predict import CHAMPION_VERSION

    pred_date = fetch_latest_prediction_date(CHAMPION_VERSION)
    if pred_date is None:
        raise HTTPException(404, "no predictions yet")
    preds = fetch_all_predictions(pred_date, CHAMPION_VERSION)
    companies = fetch_companies([p["company_id"] for p in preds])

    agg: dict[str, dict] = {}
    for p in preds:
        c = companies.get(p["company_id"])
        if c is None or not c.get("sector"):
            continue
        entry = agg.setdefault(c["sector"],
                               {"sum": 0.0, "n": 0, "top": None, "best": -1e9})
        entry["sum"] += p["alpha_score"]
        entry["n"] += 1
        if p["alpha_score"] > entry["best"]:
            entry["best"], entry["top"] = p["alpha_score"], c["ticker"]
    sectors = [SectorRow(sector=s, n=v["n"],
                         mean_alpha=round(v["sum"] / v["n"], 4),
                         top_ticker=v["top"])
               for s, v in agg.items()]
    sectors.sort(key=lambda r: r.mean_alpha, reverse=True)
    return SectorsResponse(date=pred_date, sectors=sectors)
