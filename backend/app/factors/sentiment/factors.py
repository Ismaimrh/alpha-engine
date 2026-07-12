"""Factor group 5 - Sentiment (news + social).

WILL compute: aggregated news tone scores, social volume anomalies
(Reddit/X mention z-scores), and sentiment dispersion.
MVP data source: none (scaffolded). Paid upgrade: RavenPack, Reddit API.
Activation order: #1 in Phase 7."""

from __future__ import annotations

from datetime import date

from app.factors.factor_base import FactorBase, FactorStatus


class SentimentFactor(FactorBase):
    status = FactorStatus.SCAFFOLDED
    name = "sentiment"
    category = "alternative"
    signals = ('news_sentiment', 'social_sentiment')

    def compute(self, ticker: str, as_of_date: date) -> dict:
        raise NotImplementedError("Scaffolded - see factor_spec.md")
