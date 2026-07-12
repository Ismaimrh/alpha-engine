"""Factor group 13 - ESG & Reputation.

WILL compute: ESG score changes and controversy-event flags.
MVP data source: none (scaffolded). Paid upgrade: MSCI, Sustainalytics.
Activation: #9 in Phase 7."""

from __future__ import annotations

from datetime import date

from app.factors.factor_base import FactorBase, FactorStatus


class ESGFactor(FactorBase):
    status = FactorStatus.SCAFFOLDED
    name = "esg"
    category = "fundamental"
    signals = ('esg_score_delta', 'controversy_flag')

    def compute(self, ticker: str, as_of_date: date) -> dict:
        raise NotImplementedError("Scaffolded - see factor_spec.md")
