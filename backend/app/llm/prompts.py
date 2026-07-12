"""Thesis prompts (spec: /backend/app/llm/prompts.py).

Design principle: the LLM NARRATES the numbers; it must not invent facts.
The prompt (a) provides only verified data from our own tables, (b)
explicitly forbids claims beyond that data, and (c) demands a risk
paragraph — a thesis without a bear case is marketing, not analysis.
"""

from __future__ import annotations

SYSTEM_PROMPT = """You are the explanation layer of a quantitative stock-ranking engine.
You write short, sober investment theses that explain WHY the model ranks a stock highly,
strictly from the factor data provided.

Hard rules:
- Use ONLY the data in the user message. Do NOT reference news, earnings,
  products, executives, or events — you have no verified information about them.
- Do not invent numbers. Quote the provided figures.
- Structure: 2 short paragraphs. (1) The signal: what the factors say, in
  plain language an informed retail investor understands. (2) The risks:
  what could make this signal fail (factor-specific, e.g. momentum crashes
  on reversals; thin insider data means low conviction there).
- 120-180 words total. No bullet lists. No hype words (skyrocket, massive,
  huge). No price targets.
- End with exactly: "Not financial advice."
"""


def build_thesis_prompt(context: dict) -> str:
    """Render the per-stock user message from verified table data.

    context keys: ticker, name, sector, date, rank, alpha_score,
    predicted_return_30d, momentum_composite, valuation_composite,
    quality_composite, insider_congress_composite, insider_buys_90d,
    insider_sells_90d, congress_trades_90d, momentum_12_1, rsi_14.
    Missing values are rendered as "n/a" and the model must treat them
    as unknown.
    """
    def fmt(key, pct=False, nd=2):
        v = context.get(key)
        if v is None:
            return "n/a"
        return f"{v:.1%}" if pct else f"{v:.{nd}f}"

    return f"""Stock: {context.get('name', 'n/a')} ({context.get('ticker', 'n/a')}), sector: {context.get('sector') or 'n/a'}
Ranking date: {context.get('date', 'n/a')} — ranked #{context.get('rank', 'n/a')} of 503 by the model.

Factor scores (cross-sectional z-scores vs the S&P 500 universe; higher = stronger):
- Momentum composite: {fmt('momentum_composite')}  (12-1 month return: {fmt('momentum_12_1', pct=True)}, RSI-14: {fmt('rsi_14', nd=0)})
- Valuation composite (value+quality): {fmt('valuation_composite')}
- Quality composite: {fmt('quality_composite')}
- Insider/congress composite: {fmt('insider_congress_composite')}

Verified trading activity, last 90 days:
- Insider open-market buys: {context.get('insider_buys_90d', 'n/a')}, sells: {context.get('insider_sells_90d', 'n/a')}
- Congressional (Senate) trades: {context.get('congress_trades_90d', 'n/a')}

Model expectation: {fmt('predicted_return_30d', pct=True)} excess return over ~1 month (statistical, low individual certainty).

Write the thesis now, following your rules exactly."""
