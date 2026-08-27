"""
LLMClient: the one thing the rest of HireLoop talks to. Owns retry-with-
bounded-backoff on the primary provider, and fallback to a secondary
provider if the primary is exhausted. Never retries indefinitely.
"""

from __future__ import annotations

import logging
import time
from typing import Callable, TypeVar

from pydantic import BaseModel

from src.llm.base import LLMProvider, LLMResult, RetryPolicy
from src.llm.errors import RETRYABLE_ERROR_TYPES, HireLoopLLMError, LLMErrorType

logger = logging.getLogger("hireloop.llm")

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class LLMClient:
    def __init__(
        self,
        primary: LLMProvider,
        fallback: LLMProvider | None = None,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.retry_policy = retry_policy or RetryPolicy()

    def _run_with_retries(self, provider: LLMProvider, fn: Callable[[LLMProvider], LLMResult]) -> LLMResult:
        attempts = 0
        last_error: HireLoopLLMError | None = None

        while attempts < self.retry_policy.max_retries + 1:
            attempts += 1
            try:
                result = fn(provider)
                result.attempts = attempts
                return result
            except HireLoopLLMError as exc:
                exc.attempts = attempts
                last_error = exc
                retryable = exc.error_type in RETRYABLE_ERROR_TYPES
                is_last_attempt = attempts > self.retry_policy.max_retries
                if not retryable or is_last_attempt:
                    raise
                delay = self.retry_policy.delay_for_attempt(attempts)
                logger.warning(
                    "llm_retry provider=%s attempt=%d error_type=%s delay_s=%.2f",
                    provider.name,
                    attempts,
                    exc.error_type.value,
                    delay,
                )
                time.sleep(delay)

        assert last_error is not None  # loop always raises or returns
        raise last_error

    def _with_fallback(self, fn: Callable[[LLMProvider], LLMResult]) -> LLMResult:
        try:
            return self._run_with_retries(self.primary, fn)
        except HireLoopLLMError as primary_error:
            if self.fallback is None:
                raise
            logger.warning(
                "llm_fallback_triggered primary=%s fallback=%s reason=%s",
                self.primary.name,
                self.fallback.name,
                primary_error.error_type.value,
            )
            try:
                result = self._run_with_retries(self.fallback, fn)
                result.used_fallback = True
                return result
            except HireLoopLLMError as fallback_error:
                raise HireLoopLLMError(
                    fallback_error.error_type,
                    f"Both primary ({self.primary.name}) and fallback ({self.fallback.name}) providers failed: "
                    f"{primary_error} / {fallback_error}",
                    provider=f"{self.primary.name}+{self.fallback.name}",
                    attempts=primary_error.attempts + fallback_error.attempts,
                    cause=fallback_error,
                ) from fallback_error

    def invoke(self, prompt: str, *, system: str | None = None, temperature: float = 0.0) -> LLMResult:
        return self._with_fallback(lambda provider: provider.invoke(prompt, system=system, temperature=temperature))

    def structured_output(
        self,
        prompt: str,
        schema: type[SchemaT],
        *,
        system: str | None = None,
        temperature: float = 0.0,
    ) -> tuple[SchemaT, LLMResult]:
        holder: dict[str, SchemaT] = {}

        def _call(provider: LLMProvider) -> LLMResult:
            instance, result = provider.structured_output(prompt, schema, system=system, temperature=temperature)
            holder["instance"] = instance
            return result

        result = self._with_fallback(_call)
        return holder["instance"], result

    def health_check(self) -> dict[str, bool]:
        status = {self.primary.name: self.primary.health_check()}
        if self.fallback is not None:
            status[self.fallback.name] = self.fallback.health_check()
        return status
