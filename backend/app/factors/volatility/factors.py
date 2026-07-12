"""Factor group 6 - Volatility (advanced).

WILL compute: idiosyncratic volatility (low-vol anomaly), volatility of
volatility, and realized-vs-implied gap where options data exists.
MVP data source: partial via yfinance (scaffolded). Activation: #3 in Phase 7."""

from __future__ import annotations

from datetime import date

from app.factors.factor_base import FactorBase, FactorStatus


class VolatilityFactor(FactorBase):
    status = FactorStatus.SCAFFOLDED
    name = "volatility"
    category = "price"
    signals = ('idio_vol', 'vol_of_vol')

    def compute(self, ticker: str, as_of_date: date) -> dict:
        raise NotImplementedError("Scaffolded - see factor_spec.md")
