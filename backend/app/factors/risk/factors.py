"""Factor group 16 - Risk Engine.

WILL compute: factor exposures, correlation-aware position risk, and
drawdown-risk estimates across the active factor set. Meaningful once
5+ factors are active.
MVP data source: computed from active factors (scaffolded, light).
Paid upgrade: MSCI Barra. Activation: #4 in Phase 7."""

from __future__ import annotations

from datetime import date

from app.factors.factor_base import FactorBase, FactorStatus


class RiskFactor(FactorBase):
    status = FactorStatus.SCAFFOLDED
    name = "risk"
    category = "risk"
    signals = ('factor_exposure', 'drawdown_risk')

    def compute(self, ticker: str, as_of_date: date) -> dict:
        raise NotImplementedError("Scaffolded - see factor_spec.md")
