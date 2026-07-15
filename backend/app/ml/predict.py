"""Daily predictions — champion/challenger (spec Step 8.2 / Phase 3).

Decision record (2026-07-10, human-approved option (a)): the ensemble's
OOS IC (0.022) trails plain momentum (0.052), so:

    CHAMPION   "champion-momentum-v1"  — drives the user-facing ranking.
               alpha_score = momentum_composite (already a cross-sectional
               z). predicted_return_30d = slope * z, with the slope
               calibrated by OLS of realized 21d excess returns on the
               score over the full resolved history (one number, honest,
               refit daily on resolved data only).
    CHALLENGER "lgbm-v1-..."           — the ensemble, retrained daily on
               all resolved data, predictions stored under its own
               model_version. Promotion is data-driven: when its rolling
               stored-prediction IC beats the champion's, we switch.

Confidence: rank-based heuristic, documented as such — the percentile of
|alpha_score| in today's cross-section, floored at 0.5. It answers "how
extreme is this name's signal today", not a calibrated probability;
proper calibration is a post-MVP upgrade.

position_size: 1/top_n for the champion's top names, else 0 — mirrors the
Gate 3 backtest book exactly.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from app.ml.train import MODEL_VERSION as CHALLENGER_VERSION
from app.ml.train import FEATURES, build_dataset, train_final_model

CHAMPION_VERSION = "champion-momentum-v1"
TOP_N = 50
ALPHA_CLIP = 3.0  # winsorize for predicted_return only (SNDK 5.2σ decision:
                  # rankings/alpha stay raw; clip is monotonic so Gates 2/3
                  # and the top-N book are unaffected)
HORIZON_LABEL = "30d"  # schema column name; actual horizon is 21 trading days


# --------------------------------------------------------------- pure pieces

def calibrate_slope(dataset: pd.DataFrame,
                    score_col: str = "momentum_composite") -> float:
    """OLS slope of realized excess forward return on the score.

    predicted_return = slope * score. Uses only resolved history (the
    dataset excludes unresolved targets by construction).
    """
    df = dataset[[score_col, "target"]].dropna()
    if len(df) < 100:
        return 0.0
    x, y = df[score_col].to_numpy(), df["target"].to_numpy()
    var = float(np.var(x))
    return float(np.cov(x, y, bias=True)[0, 1] / var) if var > 0 else 0.0


def rank_confidence(scores: pd.Series) -> pd.Series:
    """|score| percentile in today's cross-section, floored at 0.5."""
    pct = scores.abs().rank(pct=True)
    return (0.5 + 0.5 * pct).clip(upper=0.99).where(scores.notna())


def position_sizes(alpha: pd.Series, top_n: int = TOP_N) -> pd.Series:
    """Equal weight 1/top_n for the top names, 0 elsewhere (Gate 3 book)."""
    top = alpha.dropna().nlargest(top_n).index
    out = pd.Series(0.0, index=alpha.index)
    out.loc[top] = 1.0 / top_n
    return out.where(alpha.notna())


def build_prediction_rows(
    score_date: date,
    alpha: pd.Series,
    predicted_return: pd.Series,
    model_version: str,
    top_n: int = TOP_N,
) -> list[dict]:
    """predictions-table records for one model on one date."""
    conf = rank_confidence(alpha)
    pos = position_sizes(alpha, top_n=top_n)
    rows = []
    for cid in alpha.index:
        a = alpha.get(cid)
        if a is None or (isinstance(a, float) and np.isnan(a)):
            continue
        pr = predicted_return.get(cid)
        rows.append({
            "company_id": cid,
            "date": score_date.isoformat(),
            "alpha_score": round(float(a), 6),
            "confidence": round(float(conf[cid]), 4),
            "predicted_return_30d": (round(float(pr), 6)
                                     if pr is not None and np.isfinite(pr)
                                     else None),
            "position_size": round(float(pos[cid]), 6),
            "model_version": model_version,
        })
    return rows


# ------------------------------------------------------------------ pipeline

def run_daily_predictions(top_n: int = TOP_N) -> dict:
    """Score the latest cross-section with champion + challenger and write
    both to the predictions table."""
    from app.factors.backfill_history import _fetch_all, fetch_price_panel
    from app.utils.db import supabase

    prices = fetch_price_panel()
    composites = ["momentum_composite", "valuation_composite",
                  "insider_congress_composite"]
    scores = _fetch_all("factor_scores",
                        "id,date,company_id," + ",".join(composites), "id")
    scores["date"] = pd.to_datetime(scores["date"]).dt.date
    scores = scores.drop_duplicates(subset=["date", "company_id"])
    features = prices.merge(scores.drop(columns=["id"]),
                            on=["date", "company_id"], how="left")

    latest = max(features["date"])
    today_frame = (features.loc[features["date"] == latest]
                   .set_index("company_id"))

    # Resolved-history dataset: calibration + challenger training
    dataset = build_dataset(features, prices[["date", "company_id", "close"]])

    # Champion
    champ_alpha = today_frame["momentum_composite"].astype(float)
    slope = calibrate_slope(dataset)
    champ_rows = build_prediction_rows(
        latest, champ_alpha, slope * champ_alpha.clip(-ALPHA_CLIP, ALPHA_CLIP),
        CHAMPION_VERSION, top_n
    )

    # Challenger
    model = train_final_model(dataset)
    chall_pred = pd.Series(
        model.predict(today_frame[FEATURES]), index=today_frame.index
    )
    chall_alpha = ((chall_pred - chall_pred.mean()) / chall_pred.std(ddof=0)
                   if chall_pred.std(ddof=0) > 0 else chall_pred * 0.0)
    chall_rows = build_prediction_rows(
        latest, chall_alpha, chall_pred, CHALLENGER_VERSION, top_n
    )

    written = 0
    for rows in (champ_rows, chall_rows):
        for i in range(0, len(rows), 500):
            supabase.table("predictions").upsert(
                rows[i : i + 500],
                on_conflict="company_id,date,model_version",
            ).execute()
            written += len(rows[i : i + 500])

    top = (pd.Series({r["company_id"]: r["alpha_score"] for r in champ_rows})
           .nlargest(10))
    return {
        "date": latest.isoformat(),
        "champion_rows": len(champ_rows),
        "challenger_rows": len(chall_rows),
        "rows_written": written,
        "calibration_slope": round(slope, 6),
        "champion_top10_ids": list(top.index),
    }
