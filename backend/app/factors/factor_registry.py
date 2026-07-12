"""17-factor registry (spec: /backend/app/factors/factor_registry.py).

One entry per FACTOR GROUP — 16 factor modules under app/factors/ plus the
LLM Explanation Layer (group 17, architecture map row 17), whose home is
app/llm/ and which is built in Step 10.

Design note (v3.1, agreed with the human): the spec's example registry was
keyed per-signal, which yields 21 entries and contradicts the binding
acceptance check `assert len(FACTOR_REGISTRY) == 17`. Group-level keys are
the only arithmetic that satisfies it. Signal names remain visible on each
factor class (`.signals`) and in SIGNAL_INDEX below.

Entry format: key -> (module_path, class_name, FactorStatus)
Entries are declarative strings; nothing is imported at registry load.
Use resolve() / active_factors() to import lazily.
"""

from __future__ import annotations

from importlib import import_module

from app.factors.factor_base import FactorBase, FactorStatus

FACTOR_REGISTRY: dict[str, tuple[str, str, FactorStatus]] = {
    # --- ACTIVE (MVP) ---
    "momentum": ("app.factors.momentum.factors", "MomentumFactor", FactorStatus.ACTIVE),
    "valuation": ("app.factors.valuation.factors", "ValuationFactor", FactorStatus.ACTIVE),
    "insider_congressional": (
        "app.factors.insider_congressional.factors",
        "InsiderCongressionalFactor",
        FactorStatus.ACTIVE,
    ),
    # --- SCAFFOLDED (Phases 6-7) ---
    "earnings": ("app.factors.earnings.factors", "EarningsFactor", FactorStatus.SCAFFOLDED),
    "sentiment": ("app.factors.sentiment.factors", "SentimentFactor", FactorStatus.SCAFFOLDED),
    "volatility": ("app.factors.volatility.factors", "VolatilityFactor", FactorStatus.SCAFFOLDED),
    "microstructure": (
        "app.factors.microstructure.factors",
        "MicrostructureFactor",
        FactorStatus.SCAFFOLDED,
    ),
    "alternative_data": (
        "app.factors.alternative_data.factors",
        "AlternativeDataFactor",
        FactorStatus.SCAFFOLDED,
    ),
    "institutional": (
        "app.factors.institutional.factors",
        "InstitutionalFactor",
        FactorStatus.SCAFFOLDED,
    ),
    "options": ("app.factors.options.factors", "OptionsFactor", FactorStatus.SCAFFOLDED),
    "macro": ("app.factors.macro.factors", "MacroFactor", FactorStatus.SCAFFOLDED),
    "geopolitical": (
        "app.factors.geopolitical.factors",
        "GeopoliticalFactor",
        FactorStatus.SCAFFOLDED,
    ),
    "esg": ("app.factors.esg.factors", "ESGFactor", FactorStatus.SCAFFOLDED),
    "competitive": (
        "app.factors.competitive.factors",
        "CompetitiveFactor",
        FactorStatus.SCAFFOLDED,
    ),
    "nlp_research": (
        "app.factors.nlp_research.factors",
        "NLPResearchFactor",
        FactorStatus.SCAFFOLDED,
    ),
    "risk": ("app.factors.risk.factors", "RiskFactor", FactorStatus.SCAFFOLDED),
    # --- Group 17: LLM Explanation Layer (ACTIVE, lives outside factors/) ---
    # Not a numeric factor: generates investment theses, not scores.
    # Module app.llm.thesis_generator is built in Step 10; resolve() on this
    # entry raises until then.
    "llm_explanation": (
        "app.llm.thesis_generator",
        "ThesisGenerator",
        FactorStatus.ACTIVE,
    ),
}

# Signal-level index (the spec example's per-signal keys, preserved as a
# lookup): signal name -> group key.
SIGNAL_INDEX: dict[str, str] = {
    "momentum_12_1": "momentum",
    "rsi_14": "momentum",
    "macd_signal": "momentum",
    "value_composite": "valuation",
    "quality_composite": "valuation",
    "insider_buy_signal": "insider_congressional",
    "congress_buy_signal": "insider_congressional",
}


def resolve(key: str) -> type:
    """Import and return the class for a registry entry."""
    module_path, class_name, _status = FACTOR_REGISTRY[key]
    return getattr(import_module(module_path), class_name)


def numeric_factor_keys() -> list[str]:
    """The 16 score-producing groups (excludes the LLM explanation layer)."""
    return [k for k in FACTOR_REGISTRY if k != "llm_explanation"]


def active_factors() -> dict[str, type[FactorBase]]:
    """Import and return {key: class} for ACTIVE numeric factors."""
    return {
        k: resolve(k)
        for k in numeric_factor_keys()
        if FACTOR_REGISTRY[k][2] is FactorStatus.ACTIVE
    }
