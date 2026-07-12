"""ML ensemble: purged walk-forward LightGBM (spec Step 8 / Phase 3).

Learns to combine factor signals into one alpha score. Leakage discipline
(the whole point of this module):

- TARGET: 21d forward EXCESS return (name return minus the cross-sectional
  mean that day). Excess, not raw — otherwise the model learns market
  timing/beta instead of stock selection.
- PURGED WALK-FORWARD: the model predicting fold [t0, t1) trains only on
  rows whose TARGET WINDOW is fully resolved before t0: feature_date <=
  t0 - horizon - embargo. Without the purge, a training row dated t0-1
  contains return information from inside the test fold (overlapping
  windows) — the classic quant leakage. Every fold's boundaries are
  returned so tests can assert the purge held.
- Retrain quarterly (63 trading days), expanding window, min 120 train days.

Expected honest outcome with today's factors: the ensemble ≈ momentum,
because insider is weak (Gate 2) and valuation has no history yet. The
value is the ARCHITECTURE — as factors come online (valuation snapshots
accumulate, insider formula rework, Phase 7 activations), the ensemble
absorbs them with zero pipeline change. The eval script proves the
plumbing by comparing ensemble OOS IC vs the momentum baseline.

Features (NaN-friendly — LightGBM handles missing natively):
    momentum_12_1, rsi_14, macd_signal (raw price signals)
    momentum_composite, valuation_composite, insider_congress_composite
"""

from __future__ import annotations

from datetime import date

import lightgbm as lgb
import numpy as np
import pandas as pd

HORIZON = 21          # forward-return horizon (trading days)
EMBARGO = 2           # extra safety days on top of the horizon purge
RETRAIN_EVERY = 63    # quarterly
MIN_TRAIN_DAYS = 120
MODEL_VERSION = "lgbm-v1-momentum-insider-valuation"

FEATURES = [
    "momentum_12_1", "rsi_14", "macd_signal",
    "momentum_composite", "valuation_composite", "insider_congress_composite",
]

LGB_PARAMS = dict(
    n_estimators=200,
    learning_rate=0.05,
    num_leaves=31,
    min_child_samples=50,
    subsample=0.8,
    colsample_bytree=0.8,
    random_state=42,
    verbose=-1,
)


# ------------------------------------------------------------------ dataset

def build_dataset(
    features_panel: pd.DataFrame, closes_panel: pd.DataFrame,
    horizon: int = HORIZON,
) -> pd.DataFrame:
    """Join features with the forward EXCESS return target.

    features_panel: [date, company_id, <FEATURES...>] (missing cols allowed
    -> filled NaN). closes_panel: [date, company_id, close].
    Returns [date, company_id, <FEATURES...>, target]; rows without a
    resolvable target (last `horizon` dates) are dropped.
    """
    wide = closes_panel.pivot(index="date", columns="company_id",
                              values="close").sort_index()
    fwd = wide.shift(-horizon) / wide - 1.0
    excess = fwd.sub(fwd.mean(axis=1), axis=0)  # vs cross-sectional mean
    target = excess.stack().dropna().rename("target").reset_index()
    target.columns = ["date", "company_id", "target"]

    df = features_panel.copy()
    for col in FEATURES:
        if col not in df.columns:
            df[col] = np.nan
    df = df[["date", "company_id", *FEATURES]]
    return df.merge(target, on=["date", "company_id"], how="inner")


# -------------------------------------------------------------- walk-forward

def walk_forward_predict(
    dataset: pd.DataFrame,
    horizon: int = HORIZON,
    embargo: int = EMBARGO,
    retrain_every: int = RETRAIN_EVERY,
    min_train_days: int = MIN_TRAIN_DAYS,
    params: dict | None = None,
) -> tuple[pd.DataFrame, list[dict]]:
    """Purged expanding-window walk-forward.

    Returns (oos_predictions [date, company_id, prediction], folds) where
    each fold dict records {test_start, test_end, train_max_date, n_train}
    so the purge is externally verifiable:
        train_max_date <= test_start - (horizon + embargo) trading days.
    """
    params = {**LGB_PARAMS, **(params or {})}
    dates = np.array(sorted(dataset["date"].unique()))
    date_ix = {d: i for i, d in enumerate(dates)}

    preds, folds = [], []
    fold_starts = range(min_train_days + horizon + embargo,
                        len(dates), retrain_every)
    for start in fold_starts:
        test_dates = dates[start : start + retrain_every]
        purge_cut = dates[start - horizon - embargo]  # exclusive-of purge zone
        train = dataset.loc[dataset["date"] <= purge_cut]
        test = dataset.loc[dataset["date"].isin(test_dates)]
        if train["date"].nunique() < min_train_days or test.empty:
            continue
        model = lgb.LGBMRegressor(**params)
        model.fit(train[FEATURES], train["target"])
        out = test[["date", "company_id"]].copy()
        out["prediction"] = model.predict(test[FEATURES])
        preds.append(out)
        folds.append({
            "test_start": test_dates[0],
            "test_end": test_dates[-1],
            "train_max_date": train["date"].max(),
            "purge_gap_days": int(date_ix[test_dates[0]]
                                  - date_ix[train["date"].max()]),
            "n_train": len(train),
            "n_test": len(test),
        })
    oos = (pd.concat(preds, ignore_index=True)
           if preds else pd.DataFrame(columns=["date", "company_id",
                                               "prediction"]))
    return oos, folds


def train_final_model(dataset: pd.DataFrame,
                      params: dict | None = None) -> lgb.LGBMRegressor:
    """Fit on ALL resolved data — the production model for daily scoring
    (its targets are all fully in the past by construction)."""
    params = {**LGB_PARAMS, **(params or {})}
    model = lgb.LGBMRegressor(**params)
    model.fit(dataset[FEATURES], dataset["target"])
    return model


def feature_importances(model: lgb.LGBMRegressor) -> dict[str, float]:
    imp = model.feature_importances_.astype(float)
    total = imp.sum() or 1.0
    return {f: round(v / total, 3)
            for f, v in sorted(zip(FEATURES, imp), key=lambda x: -x[1])}
