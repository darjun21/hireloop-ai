"""
Public LLM entry point. The rest of HireLoop imports from here only —
never from src.llm.nebius_provider / fireworks_provider / mock_provider
directly, and never from an SDK. This is what keeps provider-specific
details out of the agents.
"""

from __future__ import annotations

import logging

from src.config.settings import Settings, load_settings
from src.llm.base import LLMProvider, LLMResult, RetryPolicy
from src.llm.client import LLMClient
from src.llm.errors import RETRYABLE_ERROR_TYPES, HireLoopLLMError, LLMErrorType
from src.llm.fireworks_provider import FireworksProvider
from src.llm.mock_provider import MockLLMProvider
from src.llm.nebius_provider import NebiusProvider

logger = logging.getLogger("hireloop.llm")

__all__ = [
    "LLMProvider",
    "LLMResult",
    "RetryPolicy",
    "LLMClient",
    "HireLoopLLMError",
    "LLMErrorType",
    "RETRYABLE_ERROR_TYPES",
    "MockLLMProvider",
    "NebiusProvider",
    "FireworksProvider",
    "build_provider",
    "get_llm_client",
]


def build_provider(name: str, settings: Settings) -> LLMProvider:
    """Build a single named provider ("nebius" | "fireworks" | "mock") from
    settings. Raises ValueError if the provider is unknown or missing the
    configuration it needs (model name is never assumed)."""
    if name == "mock":
        return MockLLMProvider()
    if name == "nebius":
        if not settings.nebius_api_key or not settings.nebius_model:
            raise ValueError("nebius provider requires NEBIUS_API_KEY and NEBIUS_MODEL to be set")
        return NebiusProvider(
            api_key=settings.nebius_api_key, model=settings.nebius_model, timeout_seconds=settings.llm_timeout_seconds
        )
    if name == "fireworks":
        if not settings.fireworks_api_key or not settings.fireworks_model:
            raise ValueError("fireworks provider requires FIREWORKS_API_KEY and FIREWORKS_MODEL to be set")
        return FireworksProvider(
            api_key=settings.fireworks_api_key, model=settings.fireworks_model, timeout_seconds=settings.llm_timeout_seconds
        )
    raise ValueError(f"unknown LLM provider: {name!r}")


def get_llm_client(settings: Settings | None = None) -> LLMClient:
    """Build the default HireLoop LLMClient from settings.

    In DEMO_MODE, if the configured primary provider can't be built (no
    API key/model set), this transparently falls back to the mock
    provider rather than failing startup — the app must be demoable
    without real credentials.
    """
    settings = settings or load_settings()
    retry_policy = RetryPolicy(max_retries=settings.llm_max_retries)

    try:
        primary = build_provider(settings.default_llm_provider, settings)
    except ValueError as exc:
        if not settings.demo_mode:
            raise
        logger.warning("llm_primary_unavailable_falling_back_to_mock reason=%s", exc)
        primary = MockLLMProvider()

    fallback: LLMProvider | None = None
    if settings.fallback_llm_provider:
        try:
            fallback = build_provider(settings.fallback_llm_provider, settings)
        except ValueError as exc:
            if not settings.demo_mode:
                raise
            logger.warning("llm_fallback_unavailable_ignored reason=%s", exc)

    return LLMClient(primary=primary, fallback=fallback, retry_policy=retry_policy)
