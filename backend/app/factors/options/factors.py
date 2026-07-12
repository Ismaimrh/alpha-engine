"""Factor group 10 - Options Intelligence.

WILL compute: put/call ratios, implied volatility skew, unusual options
activity flags.
MVP data source: partial via yfinance (scaffolded). Paid upgrade: CBOE
DataShop / Polygon options. Activation: #7 in Phase 7."""

from __future__ import annotations

from datetime import date

from app.factors.factor_base import FactorBase, FactorStatus


class OptionsFactor(FactorBase):
    status = FactorStatus.SCAFFOLDED
    name = "options"
    category = "price"
    signals = ('put_call_ratio', 'implied_vol_skew')

    def compute(self, ticker: str, as_of_date: date) -> dict:
        raise NotImplementedError("Scaffolded - see factor_spec.md")
