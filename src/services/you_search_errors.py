"""
You.com Web Search error contract, mirroring src/llm/errors.py's pattern:
every failure mode is classified into a controlled bucket rather than
letting a raw httpx/SDK exception leak out of src/services/you_search.py.

YouSearchError never wraps the API key or a full vendor response body --
only a short, safe message.
"""

from __future__ import annotations

from enum import Enum


class YouSearchErrorType(str, Enum):
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"  # 401 / 403
    CREDIT_EXHAUSTED = "CREDIT_EXHAUSTED"  # 402
    RATE_LIMITED = "RATE_LIMITED"  # 429
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"  # 5xx / connect / network
    INVALID_SEARCH_REQUEST = "INVALID_SEARCH_REQUEST"  # 422
    EMPTY_SEARCH_RESULTS = "EMPTY_SEARCH_RESULTS"  # 0 results -- not an error, a distinct outcome
    TIMEOUT = "TIMEOUT"
    MALFORMED_RESPONSE = "MALFORMED_RESPONSE"
    UNKNOWN = "UNKNOWN"


# Only genuinely transient failures are retried. Auth/credit/validation
# problems are not retryable -- retrying them wastes an attempt budget (and,
# for You.com, real money) on something that won't change.
RETRYABLE_ERROR_TYPES: frozenset[YouSearchErrorType] = frozenset(
    {YouSearchErrorType.TIMEOUT, YouSearchErrorType.RATE_LIMITED, YouSearchErrorType.PROVIDER_UNAVAILABLE}
)


class YouSearchError(Exception):
    """Raised by src/services/you_search.py. Never wraps a raw API key or
    full vendor response text -- only a short, safe message."""

    def __init__(
        self,
        error_type: YouSearchErrorType,
        message: str,
        *,
        attempts: int = 1,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.attempts = attempts
        self.cause = cause

    def __repr__(self) -> str:  # pragma: no cover - debug convenience only
        return f"YouSearchError(type={self.error_type.value}, attempts={self.attempts})"
