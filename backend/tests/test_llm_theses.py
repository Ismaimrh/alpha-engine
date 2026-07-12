"""Offline tests for the LLM thesis layer (Step 10) — mocked client."""

import pytest

from app.factors.factor_registry import resolve
from app.llm.prompts import SYSTEM_PROMPT, build_thesis_prompt
from app.llm.thesis_generator import ThesisGenerator, estimate_cost

CONTEXT = {
    "ticker": "SNDK", "name": "Sandisk", "sector": "Information Technology",
    "date": "2026-07-08", "rank": 1, "alpha_score": 5.24,
    "predicted_return_30d": 0.0488, "momentum_composite": 5.24,
    "valuation_composite": None, "quality_composite": 0.4,
    "insider_congress_composite": 0.1, "momentum_12_1": 1.42,
    "rsi_14": 71.0, "insider_buys_90d": 0, "insider_sells_90d": 4,
    "congress_trades_90d": 1,
}


def test_prompt_contains_data_and_handles_missing():
    prompt = build_thesis_prompt(CONTEXT)
    assert "SNDK" in prompt and "5.24" in prompt
    assert "142.0%" in prompt           # momentum_12_1 as percent
    assert "n/a" in prompt              # valuation None -> n/a
    assert "sells: 4" in prompt


def test_system_prompt_forbids_fabrication_and_requires_risks():
    low = SYSTEM_PROMPT.lower()
    assert "only the data" in low
    assert "risk" in low
    assert "not financial advice" in low


def test_estimate_cost():
    # 700 in @ $3/M + 250 out @ $15/M = 0.0021 + 0.00375
    assert estimate_cost(700, 250) == pytest.approx(0.00585)


class _FakeUsage:
    input_tokens, output_tokens = 700, 250


class _FakeBlock:
    type, text = "text", "Momentum is strong. Risks exist. Not financial advice."


class _FakeResponse:
    content, usage = [_FakeBlock()], _FakeUsage()


class _FakeMessages:
    def create(self, **kwargs):
        assert kwargs["system"] == SYSTEM_PROMPT
        assert "SNDK" in kwargs["messages"][0]["content"]
        return _FakeResponse()


class _FakeClient:
    messages = _FakeMessages()


def test_generate_with_mocked_client():
    gen = ThesisGenerator(client=_FakeClient())
    out = gen.generate(CONTEXT)
    assert out["thesis_text"].endswith("Not financial advice.")
    assert out["prompt_tokens"] == 700 and out["completion_tokens"] == 250
    assert out["cost_usd"] == pytest.approx(0.00585)


def test_registry_group_17_finally_resolves():
    cls = resolve("llm_explanation")
    assert cls is ThesisGenerator


def test_missing_api_key_raises_actionable(monkeypatch):
    import app.llm.thesis_generator as mod
    monkeypatch.setattr(mod, "ANTHROPIC_API_KEY", None)
    with pytest.raises(RuntimeError, match=".env"):
        ThesisGenerator().generate(CONTEXT)
