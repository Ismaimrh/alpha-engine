"""Paper-trading outcome resolution (spec Step 13 / Gate 4).

A prediction made at date t with horizon h (trading days) RESOLVES when
the price panel contains date t+h. The realized excess return uses the
same definition as the ML training target (name return minus the
cross-sectional mean over the window) so predicted and realized live on
the same scale — no apples-to-oranges.

Pure core (compute_outcomes) + thin DB wrapper (resolve_outcomes), same
pattern as the rest of the codebase.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

HORIZON = 21  # trading days — matches the model target and Gate 2/3


def compute_outcomes(
    predictions: pd.DataFrame,
    closes: pd.DataFrame,
    horizon: int = HORIZON,
) -> pd.DataFrame:
    """Resolve every prediction whose horizon has elapsed.

    predictions: [date, company_id, model_version, alpha_score,
                  predicted_return_30d]
    closes:      [date, company_id, close]  (the price panel)

    Returns [company_id, prediction_date, model_version, horizon_days,
    resolved_date, realized_return, realized_excess_return, alpha_score,
    predicted_return] — empty (with columns) if nothing has resolved yet.
    """
    cols = ["company_id", "prediction_date", "model_version", "horizon_days",
            "resolved_date", "realized_return", "realized_excess_return",
            "alpha_score", "predicted_return"]
    if predictions.empty or closes.empty:
        return pd.DataFrame(columns=cols)

    wide = closes.pivot(index="date", columns="company_id",
                        values="close").sort_index()
    dates = list(wide.index)
    date_ix = {d: i for i, d in enumerate(dates)}

    out_rows = []
    for pdate, group in predictions.groupby("date"):
        ix = date_ix.get(pdate)
        if ix is None or ix + horizon >= len(dates):
            continue  # unknown date or horizon not yet elapsed
        rdate = dates[ix + horizon]
        start, end = wide.loc[pdate], wide.loc[rdate]
        rets = (end / start - 1.0).dropna()
        if rets.empty:
            continue
        mean_ret = float(rets.mean())
        for _, p in group.iterrows():
            r = rets.get(p["company_id"])
            if r is None or not np.isfinite(r):
                continue
            out_rows.append({
                "company_id": p["company_id"],
                "prediction_date": pdate,
                "model_version": p["model_version"],
                "horizon_days": horizon,
                "resolved_date": rdate,
                "realized_return": round(float(r), 8),
                "realized_excess_return": round(float(r) - mean_ret, 8),
                "alpha_score": p.get("alpha_score"),
                "predicted_return": p.get("predicted_return_30d"),
            })
    return pd.DataFrame(out_rows, columns=cols)


def realized_ic_by_day(outcomes: pd.DataFrame, min_names: int = 30) -> pd.Series:
    """Per prediction-date Spearman IC of alpha_score vs realized excess."""
    if outcomes.empty:
        return pd.Series(dtype=float)

    def _ic(g: pd.DataFrame) -> float:
        g = g.dropna(subset=["alpha_score", "realized_excess_return"])
        if len(g) < min_names:
            return np.nan
        return g["alpha_score"].corr(g["realized_excess_return"],
                                     method="spearman")

    ic = outcomes.groupby("prediction_date").apply(_ic, include_groups=False)
    return ic.dropna()


def promotion_verdict(
    champ_ic: pd.Series, chall_ic: pd.Series, min_days: int = 60,
    alpha: float = 0.05,
) -> dict:
    """Data-driven promotion rule (Step 8 decision + review finding #11):
    promote iff >= min_days COMMON resolved days AND the challenger's mean
    IC is higher AND the paired difference is statistically significant
    (paired t-test, p < alpha) — a challenger must not win by noise.
    Zero-variance identical-delta edge case: treated as significant if the
    (deterministic) difference is positive."""
    common = champ_ic.index.intersection(chall_ic.index)
    n = len(common)
    if n < min_days:
        return {"decision": "keep_champion", "common_days": n,
                "reason": f"insufficient common resolved days ({n} < {min_days})"}
    c, ch = float(champ_ic[common].mean()), float(chall_ic[common].mean())
    diffs = (chall_ic[common] - champ_ic[common]).to_numpy()
    if float(np.std(diffs, ddof=1)) == 0.0:
        significant = bool(diffs.mean() > 0)
        p_value = 0.0 if significant else 1.0
    else:
        from scipy.stats import ttest_rel

        _, p_value = ttest_rel(chall_ic[common], champ_ic[common])
        p_value = float(p_value)
        significant = p_value < alpha and ch > c
    if ch > c and significant:
        return {"decision": "promote_challenger", "common_days": n,
                "champion_ic": round(c, 4), "challenger_ic": round(ch, 4),
                "p_value": round(p_value, 4),
                "reason": "challenger IC higher AND significant (paired t)"}
    return {"decision": "keep_champion", "common_days": n,
            "champion_ic": round(c, 4), "challenger_ic": round(ch, 4),
            "p_value": round(p_value, 4),
            "reason": ("difference not significant" if ch > c
                       else "champion realized IC higher or equal")}


# ------------------------------------------------------------------ DB layer

def resolve_outcomes(horizon: int = HORIZON) -> dict:
    """Fetch, resolve, upsert. Idempotent via the unique key."""
    from app.factors.backfill_history import _fetch_all
    from app.utils.db import supabase

    preds = _fetch_all(
        "predictions",
        "id,date,company_id,model_version,alpha_score,predicted_return_30d",
        "id",
    )
    if preds.empty:
        return {"resolved": 0, "note": "no predictions stored yet"}
    preds["date"] = pd.to_datetime(preds["date"]).dt.date
    preds = preds.drop_duplicates(subset=["date", "company_id",
                                          "model_version"])

    closes = _fetch_all("price_features", "id,date,company_id,close", "id")
    closes["date"] = pd.to_datetime(closes["date"]).dt.date
    closes = closes.drop_duplicates(subset=["date", "company_id"])

    outcomes = compute_outcomes(preds, closes, horizon=horizon)
    if outcomes.empty:
        latest_pred = preds["date"].max()
        latest_price = closes["date"].max()
        return {"resolved": 0,
                "note": f"nothing resolved yet — newest prediction "
                        f"{latest_pred}, prices through {latest_price}, "
                        f"horizon {horizon} trading days"}

    records = outcomes.copy()
    records["prediction_date"] = records["prediction_date"].astype(str)
    records["resolved_date"] = records["resolved_date"].astype(str)
    rows = records.to_dict("records")
    for i in range(0, len(rows), 500):
        supabase.table("prediction_outcomes").upsert(
            rows[i : i + 500],
            on_conflict="company_id,prediction_date,model_version,horizon_days",
        ).execute()
    return {"resolved": len(rows),
            "prediction_dates": sorted(outcomes["prediction_date"]
                                       .astype(str).unique().tolist()),
            "models": sorted(outcomes["model_version"].unique().tolist())}
