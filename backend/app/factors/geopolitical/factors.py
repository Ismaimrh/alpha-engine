"""Factor group 12 - Geopolitical Intelligence.

WILL compute: country/region revenue-exposure risk scores driven by news
and LLM analysis of geopolitical events.
MVP data source: none (scaffolded). Activation: #8 in Phase 7."""

from __future__ import annotations

from datetime import date

from app.factors.factor_base import FactorBase, FactorStatus


class GeopoliticalFactor(FactorBase):
    status = FactorStatus.SCAFFOLDED
    name = "geopolitical"
    category = "macro"
    signals = ('geo_risk_exposure',)

    def compute(self, ticker: str, as_of_date: date) -> dict:
        raise NotImplementedError("Scaffolded - see factor_spec.md")
