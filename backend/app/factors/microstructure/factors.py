"""Factor group 7 - Market Microstructure.

WILL compute: effective spreads, order-flow imbalance, and intraday
liquidity patterns from L2 data.
MVP data source: none (scaffolded). Paid upgrade: Polygon L2. Phase 7 (late)."""

from __future__ import annotations

from datetime import date

from app.factors.factor_base import FactorBase, FactorStatus


class MicrostructureFactor(FactorBase):
    status = FactorStatus.SCAFFOLDED
    name = "microstructure"
    category = "price"
    signals = ('bid_ask_spread', 'order_flow_imbalance')

    def compute(self, ticker: str, as_of_date: date) -> dict:
        raise NotImplementedError("Scaffolded - see factor_spec.md")
