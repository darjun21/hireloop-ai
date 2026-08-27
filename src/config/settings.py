"""
Application-wide settings, loaded from environment variables.

No secrets are hardcoded here; everything comes from the environment (see
.env.example). Model names are never assumed/defaulted — if a provider's
model env var isn't set, that provider simply can't be used until it is.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

_VALID_PROVIDERS = {"nebius", "fireworks", "mock"}


@dataclass(frozen=True)
class Settings:
    nebius_api_key: str | None = None
    nebius_model: str | None = None
    fireworks_api_key: str | None = None
    fireworks_model: str | None = None

    default_llm_provider: str = "mock"
    fallback_llm_provider: str | None = None

    llm_max_retries: int = 2
    llm_timeout_seconds: float = 30.0

    pinecone_api_key: str | None = None
    pinecone_environment: str | None = None
    pinecone_index_name: str | None = None
    mem0_api_key: str | None = None
    sqlite_db_path: str = "data/hireloop.db"
    demo_mode: bool = True

    # --- You.com live job discovery (optional, opt-in only; never used by
    # DEMO_MODE or the certification eval/test suite -- see docs/DECISIONS.md) ---
    ydc_api_key: str | None = None
    you_search_enabled: bool = False
    you_search_timeout_seconds: float = 15.0
    you_search_max_results: int = 10
    you_search_extraction_mode: str = "highlights"
    you_search_max_queries_per_run: int = 4

    def validation_issues(self) -> list[str]:
        """Non-fatal configuration issues, surfaced to the caller rather
        than raised, so the app can still run in DEMO_MODE without keys."""
        issues: list[str] = []

        if self.default_llm_provider not in _VALID_PROVIDERS:
            issues.append(
                f"DEFAULT_LLM_PROVIDER={self.default_llm_provider!r} is not one of {sorted(_VALID_PROVIDERS)}"
            )
        if self.fallback_llm_provider is not None and self.fallback_llm_provider not in _VALID_PROVIDERS:
            issues.append(
                f"FALLBACK_LLM_PROVIDER={self.fallback_llm_provider!r} is not one of {sorted(_VALID_PROVIDERS)}"
            )

        if self.default_llm_provider == "nebius" and not (self.nebius_api_key and self.nebius_model):
            if not self.demo_mode:
                issues.append("nebius selected as default provider but NEBIUS_API_KEY/NEBIUS_MODEL are not set")
        if self.default_llm_provider == "fireworks" and not (self.fireworks_api_key and self.fireworks_model):
            if not self.demo_mode:
                issues.append("fireworks selected as default provider but FIREWORKS_API_KEY/FIREWORKS_MODEL are not set")

        if self.llm_max_retries < 0:
            issues.append("LLM_MAX_RETRIES must be >= 0")
        if self.llm_timeout_seconds <= 0:
            issues.append("LLM_TIMEOUT_SECONDS must be > 0")

        return issues


def _get_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _get_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def load_settings() -> Settings:
    """Load settings from environment variables."""
    return Settings(
        nebius_api_key=os.environ.get("NEBIUS_API_KEY") or None,
        nebius_model=os.environ.get("NEBIUS_MODEL") or None,
        fireworks_api_key=os.environ.get("FIREWORKS_API_KEY") or None,
        fireworks_model=os.environ.get("FIREWORKS_MODEL") or None,
        default_llm_provider=os.environ.get("DEFAULT_LLM_PROVIDER", "mock").strip().lower(),
        fallback_llm_provider=(os.environ.get("FALLBACK_LLM_PROVIDER") or "").strip().lower() or None,
        llm_max_retries=_get_int("LLM_MAX_RETRIES", 2),
        llm_timeout_seconds=_get_float("LLM_TIMEOUT_SECONDS", 30.0),
        pinecone_api_key=os.environ.get("PINECONE_API_KEY"),
        pinecone_environment=os.environ.get("PINECONE_ENVIRONMENT"),
        pinecone_index_name=os.environ.get("PINECONE_INDEX_NAME"),
        mem0_api_key=os.environ.get("MEM0_API_KEY"),
        sqlite_db_path=os.environ.get("SQLITE_DB_PATH", "data/hireloop.db"),
        demo_mode=os.environ.get("DEMO_MODE", "true").strip().lower() == "true",
        ydc_api_key=os.environ.get("YDC_API_KEY") or None,
        you_search_enabled=os.environ.get("YOU_SEARCH_ENABLED", "false").strip().lower() == "true",
        you_search_timeout_seconds=_get_float("YOU_SEARCH_TIMEOUT_SECONDS", 15.0),
        you_search_max_results=_get_int("YOU_SEARCH_MAX_RESULTS", 10),
        you_search_extraction_mode=os.environ.get("YOU_SEARCH_EXTRACTION_MODE", "highlights"),
        you_search_max_queries_per_run=_get_int("YOU_SEARCH_MAX_QUERIES_PER_RUN", 4),
    )
