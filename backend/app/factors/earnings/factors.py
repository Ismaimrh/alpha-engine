"""Factor group 4 - Earnings Intelligence.

WILL compute: standardized earnings surprise (SUE), analyst estimate
revision breadth and magnitude over trailing 30/90 days, and
post-earnings-announcement drift exposure.
MVP data source: none (scaffolded). Paid upgrade: Estimize, Zacks.
Activation order: #2 in Phase 7."""

from __future__ import annotations

from datetime import date

from app.factors.factor_base import FactorBase, FactorStatus


class EarningsFactor(FactorBase):
    status = FactorStatus.SCAFFOLDED
    name = "earnings"
    category = "fundamental"
    signals = ('earnings_surprise', 'analyst_revision')

    def compute(self, ticker: str, as_of_date: date) -> dict:
        raise NotImplementedError("Scaffolded - see factor_spec.md")
