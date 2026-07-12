"""Factor group 11 - Macro Regime Engine.

WILL compute: regime classification (risk-on/off, rate cycle) from FRED
series, and per-stock macro sensitivities.
MVP data source: FRED API, free (scaffolded). Activation: #6 in Phase 7."""

from __future__ import annotations

from datetime import date

from app.factors.factor_base import FactorBase, FactorStatus


class MacroFactor(FactorBase):
    status = FactorStatus.SCAFFOLDED
    name = "macro"
    category = "macro"
    signals = ('regime_state', 'rate_sensitivity')

    def compute(self, ticker: str, as_of_date: date) -> dict:
        raise NotImplementedError("Scaffolded - see factor_spec.md")
