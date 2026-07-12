"""Factor group 8 - Alternative Data (web, hiring, GitHub).

WILL compute: web-traffic growth, job-posting velocity, developer
activity signals for tech names.
MVP data source: none (scaffolded). Paid upgrade: Thinknum, YipitData. Phase 7 (late)."""

from __future__ import annotations

from datetime import date

from app.factors.factor_base import FactorBase, FactorStatus


class AlternativeDataFactor(FactorBase):
    status = FactorStatus.SCAFFOLDED
    name = "alternative_data"
    category = "alternative"
    signals = ('web_traffic', 'hiring_velocity')

    def compute(self, ticker: str, as_of_date: date) -> dict:
        raise NotImplementedError("Scaffolded - see factor_spec.md")
