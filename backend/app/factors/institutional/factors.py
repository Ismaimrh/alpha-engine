"""Factor group 9 - Institutional / 13F.

WILL compute: quarter-over-quarter 13F position deltas, smart-money
crowding, and new-position initiation signals.
MVP data source: partial via SEC EDGAR (scaffolded). Paid upgrade:
WhaleWisdom. Activation: #5 in Phase 7."""

from __future__ import annotations

from datetime import date

from app.factors.factor_base import FactorBase, FactorStatus


class InstitutionalFactor(FactorBase):
    status = FactorStatus.SCAFFOLDED
    name = "institutional"
    category = "alternative"
    signals = ('thirteen_f_delta', 'crowding')

    def compute(self, ticker: str, as_of_date: date) -> dict:
        raise NotImplementedError("Scaffolded - see factor_spec.md")
