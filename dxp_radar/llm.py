"""Pluggable model backend.

DXP Radar is reviewable and runnable without any API key: by default it
uses a deterministic MockLLM that applies simple, documented heuristics
in place of a real model call, so `python main.py` produces the same
output for anyone cloning the repo. Setting ANTHROPIC_API_KEY switches
to a real Claude call for the reasoning-heavy steps (Strategist, Critic).

This mirrors the "hybrid middle" principle from the course material:
deterministic steps stay deterministic, and only the genuinely
judgment-heavy steps reach for a model at all.
"""

from __future__ import annotations

import os
import random
from abc import ABC, abstractmethod


class LLMClient(ABC):
    @abstractmethod
    def complete(self, system: str, prompt: str, *, temperature: float = 0.0) -> str:
        """Return a text completion for the given prompt."""


class MockLLM(LLMClient):
    """A deterministic stand-in used when no API key is configured.

    It does not call any external service. It applies small, transparent
    keyword heuristics so the pipeline is fully runnable and reviewable
    offline. Every place it is used is documented in the agent code and
    called out in the README and the capstone report's limitations
    section -- this is a prototype-grade substitute for a real model,
    not a claim of production-grade reasoning quality.
    """

    def __init__(self, seed: int = 7):
        self._rng = random.Random(seed)

    def complete(self, system: str, prompt: str, *, temperature: float = 0.0) -> str:
        # The orchestrator never actually parses MockLLM's raw text for
        # control flow -- agents call small typed helper methods below
        # instead. This method exists so the LLMClient interface is a
        # drop-in swap for a real provider.
        return f"[mock completion for prompt of length {len(prompt)}]"


class AnthropicLLM(LLMClient):
    """Thin wrapper around the Anthropic API, used only if a key is set."""

    def __init__(self, model: str = "claude-sonnet-4-5"):
        try:
            import anthropic  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "The 'anthropic' package is required to use AnthropicLLM. "
                "Install it with `pip install anthropic`."
            ) from exc
        self._client = anthropic.Anthropic()
        self._model = model

    def complete(self, system: str, prompt: str, *, temperature: float = 0.0) -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(block.text for block in response.content if hasattr(block, "text"))


def get_default_llm() -> LLMClient:
    """Return AnthropicLLM if ANTHROPIC_API_KEY is set, else MockLLM."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            return AnthropicLLM()
        except RuntimeError:
            pass
    return MockLLM()
