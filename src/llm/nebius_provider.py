"""Nebius provider (OpenAI-compatible chat completions API)."""

from __future__ import annotations

from src.llm.http_provider import OpenAICompatibleHTTPProvider

NEBIUS_BASE_URL = "https://api.studio.nebius.ai/v1"


class NebiusProvider(OpenAICompatibleHTTPProvider):
    def __init__(self, *, api_key: str, model: str, timeout_seconds: float = 30.0) -> None:
        super().__init__(name="nebius", base_url=NEBIUS_BASE_URL, api_key=api_key, model=model, timeout_seconds=timeout_seconds)
