"""
Category 12: Live Job Discovery (optional, You.com).

Covers the deterministic classification accuracy of the optional live job
discovery path and a safe-failure case (simulated You.com outage). No real
network call is made anywhere in this evaluator -- src/services/you_search
is exercised only via monkeypatch-free, direct-object construction, and via
src/services/live_job_discovery.run_live_discovery with an injected fake
that never calls httpx.

This category is entirely orthogonal to the certification demo path: You.com
is opt-in only (YOU_SEARCH_ENABLED=false by default) and DEMO_MODE never
depends on it.
"""

from __future__ import annotations

from unittest.mock import patch

from src.config.settings import Settings
from src.models.web_job_search import WebJobSearchResult
from src.services.job_candidate_classification import classify_web_result
from src.services.you_search_errors import YouSearchError, YouSearchErrorType
from evals.common import CategorySummary, EvalCase, summarize

CATEGORY = "live_discovery"


def _result(**overrides) -> WebJobSearchResult:
    defaults = dict(
        search_result_id="r1",
        title="Senior Backend Engineer at Acme Corp",
        url="https://boards.greenhouse.io/acme/jobs/123",
        snippet="We are hiring a Senior Backend Engineer.",
        highlights=["Responsibilities: build APIs.", "Requirements: 5+ years of experience.", "Apply now!"],
        search_query="backend engineer jobs",
    )
    defaults.update(overrides)
    return WebJobSearchResult(**defaults)


def run() -> CategorySummary:
    cases: list[EvalCase] = []

    likely_cases = [
        _result(),
        _result(
            url="https://acme.com/careers/senior-backend-engineer",
            highlights=["Full-time, remote. Join our team and apply now!", "Requirements: Python, SQL."],
        ),
    ]
    for i, result in enumerate(likely_cases):
        classification = classify_web_result(result)
        cases.append(
            EvalCase(f"live_discovery:likely_job_{i}", CATEGORY, classification == "LIKELY_JOB", detail=classification)
        )

    possible_cases = [
        _result(
            title="Software Engineer - Acme Corp",
            url="https://acme.com/about/engineering-team",
            snippet="Meet our engineering team.",
            highlights=[],
        ),
    ]
    for i, result in enumerate(possible_cases):
        classification = classify_web_result(result)
        cases.append(
            EvalCase(f"live_discovery:possible_job_{i}", CATEGORY, classification == "POSSIBLE_JOB", detail=classification)
        )

    not_job_cases = [
        _result(
            title="Top 10 Software Engineer Interview Questions",
            url="https://blog.acme.com/top-10-interview-questions",
            snippet="Prepare for your next interview with these common questions.",
            highlights=[],
        ),
        _result(
            title="Acme Corp Announces New Product Launch",
            url="https://acme.com/news/product-launch",
            snippet="Acme today announced a new product.",
            highlights=[],
        ),
    ]
    for i, result in enumerate(not_job_cases):
        classification = classify_web_result(result)
        cases.append(
            EvalCase(f"live_discovery:not_job_{i}", CATEGORY, classification == "NOT_JOB", detail=classification)
        )

    # Safe-failure case: simulated You.com outage must not crash and must
    # produce a controlled degraded outcome, never a substituted "live" job
    # silently mislabeled as real.
    from src.services.live_job_discovery import run_live_discovery

    settings = Settings(ydc_api_key="fake-eval-key", you_search_enabled=True, you_search_max_queries_per_run=1)

    with patch("src.services.you_search.search_jobs") as mocked:
        mocked.side_effect = YouSearchError(YouSearchErrorType.PROVIDER_UNAVAILABLE, "simulated outage")
        try:
            outcome = run_live_discovery(
                settings=settings,
                target_roles=["AI Engineer"],
                location=None,
                work_mode=None,
                skills=None,
                freshness="month",
                max_results=5,
            )
            crashed = False
        except Exception:  # noqa: BLE001
            outcome = None
            crashed = True

    safe_failure = (
        not crashed
        and outcome is not None
        and outcome.failed is True
        and outcome.job_dicts == []
        and any("stopped safely" in e for e in outcome.events)
    )
    cases.append(
        EvalCase(
            "live_discovery:outage_produces_safe_degraded_state",
            CATEGORY,
            safe_failure,
            detail=f"crashed={crashed} outcome={outcome}",
            severity="critical",
        )
    )

    severe_failure = not safe_failure
    return summarize(
        CATEGORY,
        cases,
        severe_failure=severe_failure,
        severe_failure_reason="You.com outage did not degrade safely" if severe_failure else "",
    )


if __name__ == "__main__":
    result = run()
    print(result.to_dict())
