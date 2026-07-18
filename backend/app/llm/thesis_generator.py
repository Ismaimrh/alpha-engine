"""LLM explanation layer (spec Step 10; factor-registry group 17).

ThesisGenerator turns one stock's verified factor data into a short,
sober thesis via the Anthropic API. This is the module the factor
registry's "llm_explanation" entry has pointed at (declaratively) since
Step 4 — resolve("llm_explanation") works from today.

Cost discipline:
- Token usage is read from the API response (not estimated) and priced
  with the rate table below; VERIFY rates at anthropic.com/pricing and
  update if they drift.
- Every thesis row stores prompt_tokens, completion_tokens, cost_usd —
  the llm_theses table doubles as the spend ledger.
- The batch runner enforces a hard --max-cost budget and stops cleanly.
"""

from __future__ import annotations

from app.config import ANTHROPIC_API_KEY
from app.llm.prompts import SYSTEM_PROMPT, build_thesis_prompt

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 400

# USD per million tokens; overridable without a deploy when pricing
# drifts (review #12). Defaults = last verified values.
import os

COST_PER_MTOK_INPUT = float(os.getenv("ANTHROPIC_INPUT_PRICE_PER_MTOK", "3.00"))
COST_PER_MTOK_OUTPUT = float(os.getenv("ANTHROPIC_OUTPUT_PRICE_PER_MTOK", "15.00"))


def estimate_cost(prompt_tokens: int, completion_tokens: int) -> float:
    return round(
        prompt_tokens / 1e6 * COST_PER_MTOK_INPUT
        + completion_tokens / 1e6 * COST_PER_MTOK_OUTPUT,
        6,
    )


class ThesisGenerator:
    """Registry-facing class (group 17: LLM explanation layer).

    Not a numeric factor: it narrates, it does not score. See the Step 8
    decision record for why an LLM must never be the ranker (untestable —
    its training data contains historical outcomes).
    """

    name = "llm_explanation"
    category = "meta"
    signals = ()

    def __init__(self, client=None, model: str = MODEL):
        self._client = client
        self.model = model

    def _get_client(self):
        if self._client is None:
            if not ANTHROPIC_API_KEY:
                raise RuntimeError(
                    "ANTHROPIC_API_KEY missing — set it in .env (see "
                    ".env.example) before generating theses."
                )
            import anthropic

            self._client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        return self._client

    def generate(self, context: dict) -> dict:
        """One thesis. Returns {thesis_text, model, prompt_tokens,
        completion_tokens, cost_usd}."""
        client = self._get_client()
        response = client.messages.create(
            model=self.model,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user",
                       "content": build_thesis_prompt(context)}],
        )
        text = "".join(
            block.text for block in response.content
            if getattr(block, "type", None) == "text"
        ).strip()
        p_tok = response.usage.input_tokens
        c_tok = response.usage.output_tokens
        return {
            "thesis_text": text,
            "model": self.model,
            "prompt_tokens": p_tok,
            "completion_tokens": c_tok,
            "cost_usd": estimate_cost(p_tok, c_tok),
        }
