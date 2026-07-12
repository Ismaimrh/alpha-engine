"""Factor group 15 - NLP Research Engine.

WILL compute: tone deltas in 10-K/10-Q MD&A sections, risk-factor
section change detection, using Claude on SEC filings.
MVP data source: partial via yfinance news (scaffolded). Paid upgrade:
RavenPack. Activation: #11 in Phase 7."""

from __future__ import annotations

from datetime import date

from app.factors.factor_base import FactorBase, FactorStatus


class NLPResearchFactor(FactorBase):
    status = FactorStatus.SCAFFOLDED
    name = "nlp_research"
    category = "alternative"
    signals = ('filing_tone_delta', 'risk_section_change')

    def compute(self, ticker: str, as_of_date: date) -> dict:
        raise NotImplementedError("Scaffolded - see factor_spec.md")
