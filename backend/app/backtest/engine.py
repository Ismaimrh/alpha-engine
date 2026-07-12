"""Walk-forward portfolio backtest engine (spec Step 7.2 / Phase 3).

Design (deliberately simple, honest about costs — spec: NEVER report
results without transaction costs):

- Rebalance every `rebalance_every` trading days (21 ≈ monthly).
- On each rebalance date t: rank names by the factor score dated t,
  hold the top `top_n` equal-weighted until the next rebalance.
- Execution assumption (documented): trade at the close of t — the same
  close the momentum signal is computed from. Mildly optimistic vs
  next-open execution; acceptable for a monthly-horizon signal, revisit
  in paper trading (Gate 4).
- Costs: `cost_bps` per side on traded notional. Traded fraction at a
  rebalance = sum(|w_new - w_old|)/2 in {0..1} (1 = full replacement,
  including the initial buy-in). Cost deducted from the first day's
  return of each holding period.
- Missing prices: closes are forward-filled up to `ffill_limit` days
  (halts); a name still missing at rebalance is simply not selectable,
  and a holding that stops printing contributes its last known price
  (conservative flat) until the next rebalance drops it.
- Benchmark: equal-weight portfolio of ALL names scored that day —
  isolates selection skill from market beta.

Everything is pure (panels in, results out) — offline-testable.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def to_wide_closes(panel: pd.DataFrame, ffill_limit: int = 5) -> pd.DataFrame:
    """date x company close matrix, forward-filled up to ffill_limit."""
    wide = panel.pivot(index="date", columns="company_id", values="close")
    return wide.sort_index().ffill(limit=ffill_limit)


def select_top(scores_on_date: pd.Series, top_n: int) -> list[str]:
    """Top-n company_ids by score (NaNs excluded)."""
    return list(scores_on_date.dropna().nlargest(top_n).index)


def turnover(old: list[str], new: list[str]) -> float:
    """Traded fraction in [0,1] for equal-weight books: 1 - overlap/n.
    Initial buy-in (old empty) = 1.0."""
    if not new:
        return 0.0
    if not old:
        return 1.0
    overlap = len(set(old) & set(new))
    return 1.0 - overlap / len(new)


def run_backtest(
    closes: pd.DataFrame,
    scores: pd.DataFrame,
    score_col: str,
    top_n: int = 50,
    rebalance_every: int = 21,
    cost_bps: float = 10.0,
) -> dict:
    """Walk-forward simulation.

    closes: wide date x company close matrix (see to_wide_closes).
    scores: long frame [date, company_id, score_col].
    Returns {daily_returns, benchmark_returns, rebalances, avg_turnover,
    holdings_last}.
    """
    dates = list(closes.index)
    score_panel = scores.pivot(index="date", columns="company_id",
                               values=score_col)
    daily_rets = closes.pct_change()

    rebalance_ix = list(range(0, len(dates), rebalance_every))
    port_rets: dict = {}
    bench_rets: dict = {}
    holdings: list[str] = []
    turnovers = []

    for k, start_ix in enumerate(rebalance_ix):
        t = dates[start_ix]
        if t not in score_panel.index:
            continue
        day_scores = score_panel.loc[t]
        # only names with a live price at t are selectable
        priced = day_scores[closes.loc[t].notna()]
        new_holdings = select_top(priced, top_n)
        if not new_holdings:
            continue
        to = turnover(holdings, new_holdings)
        turnovers.append(to)
        holdings = new_holdings
        bench_names = list(priced.dropna().index)

        end_ix = rebalance_ix[k + 1] if k + 1 < len(rebalance_ix) else len(dates) - 1
        period = dates[start_ix + 1 : end_ix + 1]
        cost = to * (cost_bps / 1e4)
        for i, d in enumerate(period):
            r = float(daily_rets.loc[d, holdings].mean())
            if i == 0:
                r -= cost  # pay the rebalance cost on day one of the period
            port_rets[d] = r
            bench_rets[d] = float(daily_rets.loc[d, bench_names].mean())

    daily = pd.Series(port_rets).sort_index().rename("strategy")
    bench = pd.Series(bench_rets).sort_index().rename("benchmark")
    return {
        "daily_returns": daily,
        "benchmark_returns": bench,
        "rebalances": len(turnovers),
        "avg_turnover": round(float(np.mean(turnovers)), 3) if turnovers else 0.0,
        "holdings_last": holdings,
    }


def perf_summary(daily: pd.Series) -> dict:
    """Annualized return/vol, Sharpe (rf=0), max drawdown, total return."""
    daily = daily.dropna()
    n = len(daily)
    if n == 0:
        return {"n_days": 0, "total_return": np.nan, "ann_return": np.nan,
                "ann_vol": np.nan, "sharpe": np.nan, "max_drawdown": np.nan}
    equity = (1 + daily).cumprod()
    total = float(equity.iloc[-1] - 1)
    ann_ret = float(equity.iloc[-1] ** (TRADING_DAYS / n) - 1)
    ann_vol = float(daily.std(ddof=1) * np.sqrt(TRADING_DAYS))
    sharpe = float((daily.mean() * TRADING_DAYS) / ann_vol) if ann_vol > 0 else np.nan
    drawdown = float((equity / equity.cummax() - 1).min())
    return {
        "n_days": n,
        "total_return": round(total, 4),
        "ann_return": round(ann_ret, 4),
        "ann_vol": round(ann_vol, 4),
        "sharpe": round(sharpe, 3),
        "max_drawdown": round(drawdown, 4),
    }
