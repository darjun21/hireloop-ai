"""
Shared base for OpenAI-chat-completions-compatible HTTP providers (Nebius,
Fireworks both expose this shape). Concrete providers only supply a
base_url and a name.

Never logs the API key or full prompt/response text — only lengths and
metadata, per the "never log secrets or full resume text" requirement.
"""

from __future__ import annotations

import json
import logging
import time

import httpx
from pydantic import BaseModel, ValidationError

from src.llm.base import LLMProvider, LLMResult, SchemaT
from src.llm.errors import HireLoopLLMError, LLMErrorType

logger = logging.getLogger("hireloop.llm")


def _classify_http_error(exc: Exception) -> LLMErrorType:
    if isinstance(exc, httpx.TimeoutException):
        return LLMErrorType.TIMEOUT
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status == 401 or status == 403:
            return LLMErrorType.AUTH_ERROR
        if status == 429:
            return LLMErrorType.RATE_LIMIT
        if status >= 500:
            return LLMErrorType.PROVIDER_UNAVAILABLE
        return LLMErrorType.UNKNOWN
    if isinstance(exc, (httpx.ConnectError, httpx.NetworkError)):
        return LLMErrorType.PROVIDER_UNAVAILABLE
    return LLMErrorType.UNKNOWN


class OpenAICompatibleHTTPProvider(LLMProvider):
    """Base for providers exposing a POST /chat/completions endpoint with
    the OpenAI request/response shape."""

    def __init__(self, *, name: str, base_url: str, api_key: str, model: str, timeout_seconds: float = 30.0) -> None:
        self.name = name
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._timeout_seconds = timeout_seconds

    def _chat_completion(self, messages: list[dict], temperature: float) -> str:
        started = time.monotonic()
        try:
            response = httpx.post(
                f"{self._base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                json={"model": self._model, "messages": messages, "temperature": temperature},
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except (httpx.TimeoutException, httpx.HTTPStatusError, httpx.ConnectError, httpx.NetworkError) as exc:
            error_type = _classify_http_error(exc)
            logger.warning(
                "llm_call_failed provider=%s model=%s error_type=%s latency_s=%.2f",
                self.name,
                self._model,
                error_type.value,
                time.monotonic() - started,
            )
            raise HireLoopLLMError(error_type, f"{self.name} request failed", provider=self.name, cause=exc) from exc
        except (KeyError, IndexError, json.JSONDecodeError) as exc:
            raise HireLoopLLMError(
                LLMErrorType.MALFORMED_RESPONSE, f"{self.name} returned an unparseable response", provider=self.name, cause=exc
            ) from exc

    def invoke(self, prompt: str, *, system: str | None = None, temperature: float = 0.0) -> LLMResult:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        started = time.monotonic()
        text = self._chat_completion(messages, temperature)
        latency = time.monotonic() - started

        logger.info(
            "llm_call_succeeded provider=%s model=%s latency_s=%.2f prompt_chars=%d",
            self.name,
            self._model,
            latency,
            len(prompt),
        )
        return LLMResult(text=text, provider=self.name, model=self._model, latency_seconds=latency)

    def structured_output(
        self,
        prompt: str,
        schema: type[SchemaT],
        *,
        system: str | None = None,
        temperature: float = 0.0,
    ) -> tuple[SchemaT, LLMResult]:
        schema_instructions = (
            "Respond with ONLY a single JSON object matching this schema, no prose, no markdown fences:\n"
            f"{json.dumps(schema.model_json_schema())}"
        )
        combined_system = f"{system}\n\n{schema_instructions}" if system else schema_instructions

        result = self.invoke(prompt, system=combined_system, temperature=temperature)
        try:
            parsed = json.loads(result.text)
            instance = schema.model_validate(parsed)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise HireLoopLLMError(
                LLMErrorType.MALFORMED_RESPONSE,
                f"{self.name} structured output did not match {schema.__name__}",
                provider=self.name,
                cause=exc,
            ) from exc
        return instance, result

    def health_check(self) -> bool:
        try:
            self.invoke("ping", temperature=0.0)
            return True
        except HireLoopLLMError:
            return False
