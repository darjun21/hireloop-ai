"""
Provider-agnostic LLM abstraction. The rest of HireLoop depends only on
LLMProvider / LLMResult / RetryPolicy from this module (re-exported via
src/llm/provider.py) — never on a specific SDK.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TypeVar

from pydantic import BaseModel

SchemaT = TypeVar("SchemaT", bound=BaseModel)


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str
    attempts: int = 1
    latency_seconds: float = 0.0
    used_fallback: bool = False


@dataclass(frozen=True)
class RetryPolicy:
    max_retries: int = 2
    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 4.0

    def delay_for_attempt(self, attempt: int) -> float:
        """attempt is 1-indexed (the attempt that just failed)."""
        return min(self.base_delay_seconds * (2 ** (attempt - 1)), self.max_delay_seconds)


class LLMProvider(ABC):
    """Every concrete provider (Nebius, Fireworks, Mock, ...) implements this."""

    name: str = "unknown"

    @abstractmethod
    def invoke(self, prompt: str, *, system: str | None = None, temperature: float = 0.0) -> LLMResult:
        """Return raw text output. Must raise HireLoopLLMError on failure,
        never a raw SDK/HTTP exception."""

    @abstractmethod
    def structured_output(
        self,
        prompt: str,
        schema: type[SchemaT],
        *,
        system: str | None = None,
        temperature: float = 0.0,
    ) -> tuple[SchemaT, LLMResult]:
        """Return a validated instance of `schema`. Must raise
        HireLoopLLMError(error_type=MALFORMED_RESPONSE, ...) if the
        provider's output cannot be parsed/validated into `schema` —
        never silently invent a value to fill the gap."""

    @abstractmethod
    def health_check(self) -> bool:
        """Cheap liveness check. Must not raise."""
