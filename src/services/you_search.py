"""
You.com Web Search API client -- the ONLY module in HireLoop that talks to
You.com.

Scope discipline (see docs/ARCHITECTURE.md "Live Job Discovery" section):
this module discovers job pages and returns raw title/url/snippet/highlights
data. It never scores opportunities, never ranks with LLM judgment, never
touches CandidateProfile, never tailors a resume, and never submits an
application. Everything past this module's return value is deterministic
normalization/dedup/quality logic that already exists.

Never logs the API key or full vendor response bodies -- only lengths,
status codes, and classified error types, mirroring
src/llm/http_provider.py's "never log secrets or full text" discipline.
The key is read once from Settings and is never hardcoded, never included
in any exception message, and never written to the Decision Trace.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import date
from urllib.parse import urlsplit

import httpx

from src.config.settings import Settings
from src.models.web_job_search import WebJobSearchResult
from src.services.you_search_errors import RETRYABLE_ERROR_TYPES, YouSearchError, YouSearchErrorType

logger = logging.getLogger("hireloop.you_search")

# Official You.com Web Search API contract (verified 2026-08-27): POST this
# URL, X-API-Key auth, response shape {"results": {"web": [...], "news":
# [...]}, "metadata": {...}}. We only ever read results.web for job
# discovery -- results.news is never treated as job listings (see
# _extract_web_hits below).
_DEFAULT_BASE_URL = "https://ydc-index.io/v1/search"
_MAX_RETRY_BACKOFF_SECONDS = 4.0


@dataclass
class YouSearchResult:
    """Internal structured result of one search call. Raw You.com response
    dicts never leak past this module -- only WebJobSearchResult instances do."""

    query: str
    results: list[WebJobSearchResult] = field(default_factory=list)
    total_results: int = 0
    attempts: int = 1
    latency_seconds: float = 0.0


def _extract_web_hits(data: dict) -> list | None:
    """Pull only results.web out of the official response envelope
    ({"results": {"web": [...], "news": [...]}, "metadata": {...}}).
    results.news is deliberately never read here -- job discovery uses web
    results only, per the official contract; news support would be a
    separate, explicit future addition. Returns None if the envelope
    doesn't have a usable results.web list (missing "results", "results"
    not a dict, or "web" not a list) -- that's treated as MALFORMED_RESPONSE
    by the caller, never silently coerced into an empty result."""
    results_obj = data.get("results") if isinstance(data, dict) else None
    if not isinstance(results_obj, dict):
        return None
    web_hits = results_obj.get("web")
    if not isinstance(web_hits, list):
        return None
    return web_hits


def _parse_hit(hit: dict, *, query: str) -> WebJobSearchResult | None:
    """Parse one results.web entry (official fields: url, title,
    description, snippets) into a WebJobSearchResult. Returns None for a
    hit missing the minimum required fields (title/url) rather than
    fabricating them -- the caller skips such hits.

    The internal `highlights` list is filled defensively, in priority
    order, from whichever of these the vendor actually returned -- never
    requiring any of them and never fabricating content:
      1. an optional extraction-mode "highlights" field, if present
      2. the official "snippets" field, if present
      3. "description" alone, wrapped as a single-item list
      4. empty, if none of the above are present
    """
    if not isinstance(hit, dict):
        return None
    title = (hit.get("title") or "").strip()
    url = (hit.get("url") or "").strip()
    if not title or not url:
        return None

    description = (hit.get("description") or "").strip()

    highlights: list[str] = []
    for key in ("highlights", "snippets"):
        raw = hit.get(key)
        if isinstance(raw, list):
            candidate_highlights = [str(h).strip() for h in raw if isinstance(h, str) and str(h).strip()]
            if candidate_highlights:
                highlights = candidate_highlights
                break
    if not highlights and description:
        highlights = [description]

    # A real structured publish date, if the vendor supplied one -- never
    # derived from search "freshness", which is a search filter, not proof
    # of an actual posting date. Not part of the officially documented
    # contract; read defensively only if present.
    published: date | None = None
    raw_date = hit.get("published_date") or hit.get("page_age")
    if isinstance(raw_date, str) and len(raw_date) >= 10:
        try:
            published = date.fromisoformat(raw_date[:10])
        except ValueError:
            published = None

    domain = urlsplit(url).netloc

    return WebJobSearchResult(
        search_result_id=f"you-{uuid.uuid4().hex[:12]}",
        title=title,
        url=url,
        source_domain=domain,
        snippet=description,
        highlights=highlights,
        published_or_discovered_date=published,
        search_query=query,
        provider="YOU_COM",
        metadata={},
    )


def _classify_http_error(exc: Exception) -> YouSearchErrorType:
    if isinstance(exc, httpx.TimeoutException):
        return YouSearchErrorType.TIMEOUT
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status in (401, 403):
            return YouSearchErrorType.AUTHENTICATION_ERROR
        if status == 402:
            return YouSearchErrorType.CREDIT_EXHAUSTED
        if status == 422:
            return YouSearchErrorType.INVALID_SEARCH_REQUEST
        if status == 429:
            return YouSearchErrorType.RATE_LIMITED
        if status >= 500:
            return YouSearchErrorType.PROVIDER_UNAVAILABLE
        return YouSearchErrorType.UNKNOWN
    if isinstance(exc, (httpx.ConnectError, httpx.NetworkError)):
        return YouSearchErrorType.PROVIDER_UNAVAILABLE
    return YouSearchErrorType.UNKNOWN


def _backoff_seconds(attempt: int) -> float:
    """attempt is 1-indexed (the attempt that just failed)."""
    return min(0.5 * (2 ** (attempt - 1)), _MAX_RETRY_BACKOFF_SECONDS)


def search_jobs(
    query: str,
    count: int,
    *,
    freshness: str | None = None,
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
    settings: Settings,
    base_url: str = _DEFAULT_BASE_URL,
    max_retries: int | None = None,
) -> YouSearchResult:
    """Run one You.com Web Search query. Bounded retries (never infinite)
    only for TIMEOUT / RATE_LIMITED / PROVIDER_UNAVAILABLE. Auth/credit/
    validation failures raise immediately without retrying.

    Raises YouSearchError on any failure, including EMPTY_SEARCH_RESULTS
    (a distinct, non-fatal outcome the caller may choose to treat as a
    controlled "no results" case rather than a hard failure).
    """
    if not settings.ydc_api_key:
        raise YouSearchError(YouSearchErrorType.AUTHENTICATION_ERROR, "You.com API key is not configured")

    retries = settings.llm_max_retries if max_retries is None else max_retries
    retries = max(0, retries)
    timeout = settings.you_search_timeout_seconds
    payload: dict = {"query": query, "num_web_results": max(1, count)}
    if freshness:
        payload["freshness"] = freshness
    if include_domains:
        payload["include_domains"] = include_domains
    if exclude_domains:
        payload["exclude_domains"] = exclude_domains

    started = time.monotonic()
    attempt = 0

    while True:
        attempt += 1
        try:
            response = httpx.post(
                base_url,
                headers={"X-API-Key": settings.ydc_api_key, "Content-Type": "application/json"},
                json=payload,
                timeout=timeout,
            )
            response.raise_for_status()
            try:
                data = response.json()
            except ValueError as exc:
                raise YouSearchError(
                    YouSearchErrorType.MALFORMED_RESPONSE, "You.com returned a non-JSON response", attempts=attempt, cause=exc
                ) from exc

            web_hits = _extract_web_hits(data)
            if web_hits is None:
                raise YouSearchError(
                    YouSearchErrorType.MALFORMED_RESPONSE,
                    "You.com response did not contain a results.web list",
                    attempts=attempt,
                )

            latency = time.monotonic() - started
            logger.info(
                "you_search_succeeded query_chars=%d count=%d web_results=%d attempts=%d latency_s=%.2f",
                len(query),
                count,
                len(web_hits),
                attempt,
                latency,
            )
            if not web_hits:
                raise YouSearchError(YouSearchErrorType.EMPTY_SEARCH_RESULTS, "You.com returned zero web results", attempts=attempt)

            parsed = [r for r in (_parse_hit(h, query=query) for h in web_hits) if r is not None]
            if not parsed:
                raise YouSearchError(YouSearchErrorType.EMPTY_SEARCH_RESULTS, "You.com results had no usable title/url", attempts=attempt)

            return YouSearchResult(query=query, results=parsed, total_results=len(parsed), attempts=attempt, latency_seconds=latency)

        except YouSearchError:
            raise
        except (httpx.TimeoutException, httpx.HTTPStatusError, httpx.ConnectError, httpx.NetworkError) as exc:
            error_type = _classify_http_error(exc)
            logger.warning(
                "you_search_call_failed error_type=%s attempt=%d latency_s=%.2f",
                error_type.value,
                attempt,
                time.monotonic() - started,
            )
            if error_type not in RETRYABLE_ERROR_TYPES or attempt > retries:
                raise YouSearchError(
                    error_type, f"You.com search request failed ({error_type.value})", attempts=attempt, cause=exc
                ) from exc
            time.sleep(_backoff_seconds(attempt))
            continue
        except (KeyError, TypeError) as exc:
            raise YouSearchError(
                YouSearchErrorType.MALFORMED_RESPONSE, "You.com returned an unparseable response", attempts=attempt, cause=exc
            ) from exc
