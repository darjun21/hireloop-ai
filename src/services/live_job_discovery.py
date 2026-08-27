"""
Thin orchestration for the optional "LIVE SEARCH" Streamlit flow: builds
queries, calls You.com, classifies results, converts LIKELY_JOB candidates
to JobPosting dicts, and returns a job_source_override list plus Decision
Trace-style event strings.

This is the only place the Streamlit app touches src/services/you_search.py
-- app.py itself never calls the vendor client directly, so tests can mock
this module's `search_jobs` reference in one place.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.config.settings import Settings
from src.services import you_search
from src.services.job_candidate_classification import build_candidate
from src.services.web_job_conversion import candidate_to_job_posting_dict
from src.services.you_search_errors import YouSearchError, YouSearchErrorType
from src.services.you_search_query_builder import build_job_search_queries


@dataclass
class LiveDiscoveryOutcome:
    job_dicts: list[dict] = field(default_factory=list)
    events: list[str] = field(default_factory=list)
    failed: bool = False
    failure_reason: str = ""


def run_live_discovery(
    *,
    settings: Settings,
    target_roles: list[str],
    location: str | None,
    work_mode: str | None,
    skills: list[str] | None,
    freshness: str | None,
    max_results: int,
) -> LiveDiscoveryOutcome:
    """Human-triggered only (called from a Streamlit button handler, never
    from a bare rerun). Never raises -- failures come back as a controlled
    LiveDiscoveryOutcome(failed=True, ...) so the UI can degrade gracefully
    to DEMO JOBS. Never includes the API key or raw vendor response bodies
    in any returned event string."""
    events: list[str] = ["Live job search started using You.com."]

    queries = build_job_search_queries(
        target_roles,
        location=location,
        work_mode=work_mode,
        skills=skills,
        max_queries=settings.you_search_max_queries_per_run,
    )
    events.append(f"{len(queries)} role queries executed.")

    all_results = []
    for query in queries:
        try:
            result = you_search.search_jobs(
                query,
                max_results,
                freshness=freshness,
                settings=settings,
            )
            all_results.extend(result.results)
        except YouSearchError as exc:
            if exc.error_type == YouSearchErrorType.EMPTY_SEARCH_RESULTS:
                continue
            events.append("You.com search unavailable; live discovery stopped safely.")
            return LiveDiscoveryOutcome(job_dicts=[], events=events, failed=True, failure_reason=exc.error_type.value)

    events.append(f"{len(all_results)} search results returned.")

    likely: list[dict] = []
    possible_count = 0
    not_job_count = 0
    seen_urls: set[str] = set()
    for result in all_results:
        if result.url in seen_urls:
            continue
        seen_urls.add(result.url)
        candidate = build_candidate(result)
        if candidate.classification == "LIKELY_JOB":
            likely.append(candidate_to_job_posting_dict(candidate))
        elif candidate.classification == "POSSIBLE_JOB":
            possible_count += 1
        else:
            not_job_count += 1

    events.append(f"{len(likely)} results classified as likely job postings.")
    if possible_count:
        events.append(f"{possible_count} possible-job result(s) skipped, review manually.")
    if not_job_count:
        events.append(f"{not_job_count} result(s) classified as not-job and dropped.")

    return LiveDiscoveryOutcome(job_dicts=likely, events=events, failed=False)
