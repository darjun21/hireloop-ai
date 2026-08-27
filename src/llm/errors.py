"""
LLM error contract shared by every provider and the orchestrating client.

Every provider must classify failures into one of these buckets rather than
letting a raw SDK/HTTP exception leak out — that's what lets the client
decide whether a failure is worth retrying or falling back on.
"""

from __future__ import annotations

from enum import Enum


class LLMErrorType(str, Enum):
    TIMEOUT = "TIMEOUT"
    RATE_LIMIT = "RATE_LIMIT"
    AUTH_ERROR = "AUTH_ERROR"
    MALFORMED_RESPONSE = "MALFORMED_RESPONSE"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


# Only genuinely transient failures are retried. Auth/config problems and
# malformed responses are not retryable — retrying them wastes an attempt
# budget on something that won't change.
RETRYABLE_ERROR_TYPES: frozenset[LLMErrorType] = frozenset(
    {LLMErrorType.TIMEOUT, LLMErrorType.RATE_LIMIT, LLMErrorType.PROVIDER_UNAVAILABLE}
)


class HireLoopLLMError(Exception):
    """Raised by providers and the LLM client. Never wraps a raw API key or
    full prompt text — only a short, safe message."""

    def __init__(
        self,
        error_type: LLMErrorType,
        message: str,
        *,
        provider: str,
        attempts: int = 1,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.provider = provider
        self.attempts = attempts
        self.cause = cause

    def __repr__(self) -> str:  # pragma: no cover - debug convenience only
        return f"HireLoopLLMError(type={self.error_type.value}, provider={self.provider}, attempts={self.attempts})"
