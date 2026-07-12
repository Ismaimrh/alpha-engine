"""Factor group 14 - Competitive Positioning.

WILL compute: relative margin trajectory vs sector peers, market-share
proxies from fundamental ratios.
MVP data source: partial via yfinance (scaffolded). Activation: #10 in Phase 7."""

from __future__ import annotations

from datetime import date

from app.factors.factor_base import FactorBase, FactorStatus


class CompetitiveFactor(FactorBase):
    status = FactorStatus.SCAFFOLDED
    name = "competitive"
    category = "fundamental"
    signals = ('market_share_trend', 'margin_vs_peers')

    def compute(self, ticker: str, as_of_date: date) -> dict:
        raise NotImplementedError("Scaffolded - see factor_spec.md")
