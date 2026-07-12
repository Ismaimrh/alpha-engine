"""Factor base class and status (spec: /backend/app/factors/factor_base.py)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from enum import StrEnum


class FactorStatus(StrEnum):
    ACTIVE = "active"
    SCAFFOLDED = "scaffolded"


class FactorBase(ABC):
    """Abstract base for all 17 factor groups.

    Class attributes each concrete factor must define:
        status:   FactorStatus.ACTIVE or .SCAFFOLDED
        name:     registry key, e.g. "momentum"
        category: "price" | "fundamental" | "alternative" | "macro" |
                  "risk" | "meta"
        signals:  tuple of signal names this group produces,
                  e.g. ("momentum_12_1", "rsi_14", "macd_signal")
    """

    status: FactorStatus
    name: str
    category: str
    signals: tuple[str, ...] = ()

    @abstractmethod
    def compute(self, ticker: str, as_of_date: date) -> dict:
        """Return {signal_name: score, ...} for one ticker on one date.

        Must respect point-in-time discipline: use only data that was
        publicly available on `as_of_date` (e.g. gate insider rows on
        filing_date, not transaction_date).
        """
        raise NotImplementedError
