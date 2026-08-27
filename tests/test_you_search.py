"""
Tests for the optional You.com live job discovery path. Zero real network
calls anywhere in this file -- httpx.post is monkeypatched to return real
httpx.Response objects (or raise real httpx exceptions), exactly as
tests/test_llm_provider.py mocks providers rather than hitting a live API.

Covers: successful search, classified error types + bounded retries,
LIKELY/POSSIBLE/NOT_JOB classification, query builder, max-result
enforcement, the ingest_jobs_node override path, sparse-result job quality
degradation via the EXISTING job quality service, the API key never
appearing in exceptions/logs, DEMO_MODE never calling You.com, and the
Streamlit "Search Live Jobs" button being the only thing that can trigger a
paid call (via streamlit.testing.v1.AppTest).
"""

from __future__ import annotations

import logging
from pathlib import Path

import httpx
import pytest

from src.config.settings import Settings
from src.graph.nodes.jobs import ingest_jobs_node
from src.models.job import JobPosting
from src.models.web_job_search import WebJobSearchResult
from src.services import you_search
from src.services.job_candidate_classification import build_candidate, classify_web_result
from src.services.job_quality import score_job_quality
from src.services.web_job_conversion import candidate_to_job_posting_dict
from src.services.you_search_errors import YouSearchError, YouSearchErrorType
from src.services.you_search_query_builder import build_job_search_queries

_FAKE_KEY = "ydc-test-fake-key-never-real-0000"
_APP_PATH = str(Path(__file__).resolve().parent.parent / "app.py")


def _settings(**overrides) -> Settings:
    defaults = dict(
        ydc_api_key=_FAKE_KEY,
        you_search_enabled=True,
        you_search_timeout_seconds=5.0,
        you_search_max_results=10,
        you_search_max_queries_per_run=4,
        llm_max_retries=2,
    )
    defaults.update(overrides)
    return Settings(**defaults)


def _response(status_code: int, json_body: dict | None = None) -> httpx.Response:
    request = httpx.Request("POST", "https://ydc-index.io/v1/search")
    return httpx.Response(status_code, json=json_body or {}, request=request)


def _hit(title="Senior Backend Engineer", url="https://boards.greenhouse.io/acme/jobs/1", **overrides) -> dict:
    """One results.web entry, official fields only (url, title,
    description, snippets)."""
    hit = {
        "title": title,
        "url": url,
        "description": "We are hiring a Senior Backend Engineer. Responsibilities: build APIs. Apply now!",
        "snippets": ["5+ years of experience required.", "Apply now!"],
    }
    hit.update(overrides)
    return hit


def _web_response(hits: list[dict], *, news: list[dict] | None = None) -> dict:
    """The official response envelope: {"results": {"web": [...], "news":
    [...]}, "metadata": {...}}."""
    return {"results": {"web": hits, "news": news or []}, "metadata": {"provider": "you.com"}}


# ---------------------------------------------------------------------------
# you_search.search_jobs
# ---------------------------------------------------------------------------


def test_successful_search_returns_parsed_results(monkeypatch):
    def fake_post(url, headers, json, timeout):
        assert headers["X-API-Key"] == _FAKE_KEY
        return _response(200, _web_response([_hit(), _hit(title="Other Role", url="https://boards.greenhouse.io/acme/jobs/2")]))

    monkeypatch.setattr(you_search.httpx, "post", fake_post)
    result = you_search.search_jobs("backend engineer jobs", 5, settings=_settings())

    assert result.total_results == 2
    assert all(isinstance(r, WebJobSearchResult) for r in result.results)
    assert result.results[0].title == "Senior Backend Engineer"
    assert result.results[0].provider == "YOU_COM"


def test_auth_failure_401_raises_and_does_not_retry(monkeypatch):
    calls = {"n": 0}

    def fake_post(url, headers, json, timeout):
        calls["n"] += 1
        return _response(401, {"error": "unauthorized"})

    monkeypatch.setattr(you_search.httpx, "post", fake_post)
    with pytest.raises(YouSearchError) as exc_info:
        you_search.search_jobs("q", 5, settings=_settings())

    assert exc_info.value.error_type == YouSearchErrorType.AUTHENTICATION_ERROR
    assert calls["n"] == 1


def test_credit_exhausted_402_raises_and_does_not_retry(monkeypatch):
    calls = {"n": 0}

    def fake_post(url, headers, json, timeout):
        calls["n"] += 1
        return _response(402, {"error": "payment required"})

    monkeypatch.setattr(you_search.httpx, "post", fake_post)
    with pytest.raises(YouSearchError) as exc_info:
        you_search.search_jobs("q", 5, settings=_settings())

    assert exc_info.value.error_type == YouSearchErrorType.CREDIT_EXHAUSTED
    assert calls["n"] == 1


def test_invalid_request_422_raises_and_does_not_retry(monkeypatch):
    calls = {"n": 0}

    def fake_post(url, headers, json, timeout):
        calls["n"] += 1
        return _response(422, {"error": "bad query"})

    monkeypatch.setattr(you_search.httpx, "post", fake_post)
    with pytest.raises(YouSearchError) as exc_info:
        you_search.search_jobs("q", 5, settings=_settings())

    assert exc_info.value.error_type == YouSearchErrorType.INVALID_SEARCH_REQUEST
    assert calls["n"] == 1


def test_timeout_then_success_retries(monkeypatch):
    calls = {"n": 0}

    def fake_post(url, headers, json, timeout):
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.TimeoutException("timed out")
        return _response(200, _web_response([_hit()]))

    monkeypatch.setattr(you_search.httpx, "post", fake_post)
    monkeypatch.setattr(you_search.time, "sleep", lambda _s: None)

    result = you_search.search_jobs("q", 5, settings=_settings())
    assert calls["n"] == 2
    assert result.attempts == 2


def test_rate_limited_retries_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def fake_post(url, headers, json, timeout):
        calls["n"] += 1
        if calls["n"] == 1:
            return _response(429, {"error": "rate limited"})
        return _response(200, _web_response([_hit()]))

    monkeypatch.setattr(you_search.httpx, "post", fake_post)
    monkeypatch.setattr(you_search.time, "sleep", lambda _s: None)

    result = you_search.search_jobs("q", 5, settings=_settings())
    assert calls["n"] == 2
    assert result.total_results == 1


def test_transient_5xx_failure_retries_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def fake_post(url, headers, json, timeout):
        calls["n"] += 1
        if calls["n"] <= 2:
            return _response(503, {"error": "unavailable"})
        return _response(200, _web_response([_hit()]))

    monkeypatch.setattr(you_search.httpx, "post", fake_post)
    monkeypatch.setattr(you_search.time, "sleep", lambda _s: None)

    result = you_search.search_jobs("q", 5, settings=_settings())
    assert calls["n"] == 3
    assert result.attempts == 3


def test_retries_are_bounded_not_infinite(monkeypatch):
    calls = {"n": 0}

    def fake_post(url, headers, json, timeout):
        calls["n"] += 1
        return _response(503, {"error": "unavailable"})

    monkeypatch.setattr(you_search.httpx, "post", fake_post)
    monkeypatch.setattr(you_search.time, "sleep", lambda _s: None)

    with pytest.raises(YouSearchError) as exc_info:
        you_search.search_jobs("q", 5, settings=_settings(llm_max_retries=2))

    assert exc_info.value.error_type == YouSearchErrorType.PROVIDER_UNAVAILABLE
    assert calls["n"] == 3  # 1 initial + 2 retries


def test_malformed_response_raises_malformed_response(monkeypatch):
    def fake_post(url, headers, json, timeout):
        return _response(200, {"unexpected": "shape"})

    monkeypatch.setattr(you_search.httpx, "post", fake_post)
    with pytest.raises(YouSearchError) as exc_info:
        you_search.search_jobs("q", 5, settings=_settings())

    assert exc_info.value.error_type == YouSearchErrorType.MALFORMED_RESPONSE


def test_missing_results_key_raises_malformed_response(monkeypatch):
    """Response body has neither a "results" key at all -- e.g. an
    unexpected top-level shape the vendor might return on a partial outage."""

    def fake_post(url, headers, json, timeout):
        return _response(200, {"metadata": {"provider": "you.com"}})

    monkeypatch.setattr(you_search.httpx, "post", fake_post)
    with pytest.raises(YouSearchError) as exc_info:
        you_search.search_jobs("q", 5, settings=_settings())

    assert exc_info.value.error_type == YouSearchErrorType.MALFORMED_RESPONSE


def test_malformed_results_web_not_a_list_raises_malformed_response(monkeypatch):
    """results.web present but not a list (e.g. a dict or string) must be
    treated as malformed, never silently coerced into an empty result."""

    def fake_post(url, headers, json, timeout):
        return _response(200, {"results": {"web": "not-a-list"}, "metadata": {}})

    monkeypatch.setattr(you_search.httpx, "post", fake_post)
    with pytest.raises(YouSearchError) as exc_info:
        you_search.search_jobs("q", 5, settings=_settings())

    assert exc_info.value.error_type == YouSearchErrorType.MALFORMED_RESPONSE


def test_auth_failure_403_raises_and_does_not_retry(monkeypatch):
    calls = {"n": 0}

    def fake_post(url, headers, json, timeout):
        calls["n"] += 1
        return _response(403, {"error": "forbidden"})

    monkeypatch.setattr(you_search.httpx, "post", fake_post)
    with pytest.raises(YouSearchError) as exc_info:
        you_search.search_jobs("q", 5, settings=_settings())

    assert exc_info.value.error_type == YouSearchErrorType.AUTHENTICATION_ERROR
    assert calls["n"] == 1


def test_provider_error_500_retries_then_raises_provider_unavailable(monkeypatch):
    calls = {"n": 0}

    def fake_post(url, headers, json, timeout):
        calls["n"] += 1
        return _response(500, {"error": "internal error"})

    monkeypatch.setattr(you_search.httpx, "post", fake_post)
    monkeypatch.setattr(you_search.time, "sleep", lambda _s: None)
    with pytest.raises(YouSearchError) as exc_info:
        you_search.search_jobs("q", 5, settings=_settings(llm_max_retries=1))

    assert exc_info.value.error_type == YouSearchErrorType.PROVIDER_UNAVAILABLE
    assert calls["n"] == 2  # 1 initial + 1 retry


def test_news_results_never_treated_as_job_listings(monkeypatch):
    """results.news must never be read for job discovery -- only
    results.web. A response with news hits but an empty web list is still
    EMPTY_SEARCH_RESULTS, not silently backfilled from news."""

    def fake_post(url, headers, json, timeout):
        return _response(
            200,
            _web_response(
                [],
                news=[{"title": "Acme raises $50M Series B", "url": "https://news.example.com/acme-funding"}],
            ),
        )

    monkeypatch.setattr(you_search.httpx, "post", fake_post)
    with pytest.raises(YouSearchError) as exc_info:
        you_search.search_jobs("q", 5, settings=_settings())

    assert exc_info.value.error_type == YouSearchErrorType.EMPTY_SEARCH_RESULTS


def test_description_present_snippets_absent_uses_description_as_highlight(monkeypatch):
    def fake_post(url, headers, json, timeout):
        hit = _hit(description="We are hiring a Data Engineer. Apply now!")
        del hit["snippets"]
        return _response(200, _web_response([hit]))

    monkeypatch.setattr(you_search.httpx, "post", fake_post)
    result = you_search.search_jobs("q", 5, settings=_settings())

    assert result.results[0].snippet == "We are hiring a Data Engineer. Apply now!"
    assert result.results[0].highlights == ["We are hiring a Data Engineer. Apply now!"]


def test_snippets_present_used_as_highlights(monkeypatch):
    def fake_post(url, headers, json, timeout):
        return _response(200, _web_response([_hit(snippets=["5+ years required.", "Apply now!"])]))

    monkeypatch.setattr(you_search.httpx, "post", fake_post)
    result = you_search.search_jobs("q", 5, settings=_settings())

    assert result.results[0].highlights == ["5+ years required.", "Apply now!"]


def test_optional_extraction_highlights_field_takes_priority_over_snippets(monkeypatch):
    """An optional, not-officially-guaranteed extraction-mode "highlights"
    field, when present, takes priority over "snippets" -- but is never
    required to exist."""

    def fake_post(url, headers, json, timeout):
        hit = _hit(highlights=["Extracted: 5+ years Python required."], snippets=["generic snippet"])
        return _response(200, _web_response([hit]))

    monkeypatch.setattr(you_search.httpx, "post", fake_post)
    result = you_search.search_jobs("q", 5, settings=_settings())

    assert result.results[0].highlights == ["Extracted: 5+ years Python required."]


def test_no_highlights_no_snippets_no_description_yields_empty_highlights(monkeypatch):
    def fake_post(url, headers, json, timeout):
        hit = _hit(description="", snippets=[])
        return _response(200, _web_response([hit]))

    monkeypatch.setattr(you_search.httpx, "post", fake_post)
    result = you_search.search_jobs("q", 5, settings=_settings())

    assert result.results[0].highlights == []
    assert result.results[0].snippet == ""


def test_empty_results_raises_empty_search_results(monkeypatch):
    def fake_post(url, headers, json, timeout):
        return _response(200, _web_response([]))

    monkeypatch.setattr(you_search.httpx, "post", fake_post)
    with pytest.raises(YouSearchError) as exc_info:
        you_search.search_jobs("q", 5, settings=_settings())

    assert exc_info.value.error_type == YouSearchErrorType.EMPTY_SEARCH_RESULTS


def test_max_results_enforcement_passed_through_as_count(monkeypatch):
    captured = {}

    def fake_post(url, headers, json, timeout):
        captured["num_web_results"] = json["num_web_results"]
        return _response(200, _web_response([_hit()]))

    monkeypatch.setattr(you_search.httpx, "post", fake_post)
    you_search.search_jobs("q", 3, settings=_settings())
    assert captured["num_web_results"] == 3


def test_api_key_never_in_exception_message_or_repr(monkeypatch):
    def fake_post(url, headers, json, timeout):
        return _response(401, {"error": "unauthorized"})

    monkeypatch.setattr(you_search.httpx, "post", fake_post)
    with pytest.raises(YouSearchError) as exc_info:
        you_search.search_jobs("q", 5, settings=_settings())

    assert _FAKE_KEY not in str(exc_info.value)
    assert _FAKE_KEY not in repr(exc_info.value)


def test_api_key_never_in_logs(monkeypatch, caplog):
    def fake_post(url, headers, json, timeout):
        raise httpx.TimeoutException("timed out")

    monkeypatch.setattr(you_search.httpx, "post", fake_post)
    monkeypatch.setattr(you_search.time, "sleep", lambda _s: None)

    with caplog.at_level(logging.WARNING, logger="hireloop.you_search"):
        with pytest.raises(YouSearchError):
            you_search.search_jobs("q", 5, settings=_settings(llm_max_retries=0))

    for record in caplog.records:
        assert _FAKE_KEY not in record.getMessage()


def test_missing_api_key_raises_authentication_error_without_network_call(monkeypatch):
    called = {"n": 0}

    def fake_post(*args, **kwargs):
        called["n"] += 1
        raise AssertionError("should never be called without an api key")

    monkeypatch.setattr(you_search.httpx, "post", fake_post)
    with pytest.raises(YouSearchError) as exc_info:
        you_search.search_jobs("q", 5, settings=_settings(ydc_api_key=None))

    assert exc_info.value.error_type == YouSearchErrorType.AUTHENTICATION_ERROR
    assert called["n"] == 0


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


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


def test_classification_likely_job_board_with_employment_language():
    result = _result()
    assert classify_web_result(result) == "LIKELY_JOB"


def test_classification_likely_job_url_pattern_plus_role_and_language():
    result = _result(
        url="https://acme.com/careers/senior-backend-engineer",
        highlights=["Full-time, remote. Join our team and apply now!", "Requirements: Python, SQL."],
    )
    assert classify_web_result(result) == "LIKELY_JOB"


def test_classification_possible_job_weak_signal():
    result = _result(
        title="Software Engineer - Acme Corp",
        url="https://acme.com/about/engineering-team",
        snippet="Meet our engineering team.",
        highlights=[],
    )
    assert classify_web_result(result) == "POSSIBLE_JOB"


def test_classification_not_job_listicle():
    result = _result(
        title="Top 10 Software Engineer Interview Questions",
        url="https://blog.acme.com/top-10-interview-questions",
        snippet="Prepare for your next interview with these common questions.",
        highlights=[],
    )
    assert classify_web_result(result) == "NOT_JOB"


def test_classification_not_job_unrelated_news():
    result = _result(
        title="Acme Corp Announces New Product Launch",
        url="https://acme.com/news/product-launch",
        snippet="Acme today announced a new product.",
        highlights=[],
    )
    assert classify_web_result(result) == "NOT_JOB"


def test_classification_not_job_empty_content():
    result = _result(title="Acme Update", url="https://acme.com/page", snippet="", highlights=[])
    assert classify_web_result(result) == "NOT_JOB"


def test_build_candidate_only_likely_converts_to_job_posting():
    likely = build_candidate(_result())
    assert likely.classification == "LIKELY_JOB"
    job_dict = candidate_to_job_posting_dict(likely)
    job = JobPosting(**job_dict)  # must validate cleanly
    assert job.source == "you_com"
    assert job.url == likely.result.url
    assert job.posted_date is None  # never inferred from freshness


# ---------------------------------------------------------------------------
# Query builder
# ---------------------------------------------------------------------------


def test_query_builder_one_query_per_role_capped():
    queries = build_job_search_queries(
        ["AI Engineer", "ML Engineer", "Data Scientist", "Backend Engineer", "Frontend Engineer"],
        location="Remote",
        work_mode="REMOTE",
        skills=["Python", "PyTorch", "AWS", "Kubernetes", "SQL"],
        max_queries=3,
    )
    assert len(queries) == 3
    assert "AI Engineer" in queries[0]
    assert "Remote" in queries[0]
    assert "REMOTE" in queries[0]
    # Only the top 3 skills, not all 5.
    assert "Kubernetes" not in queries[0]
    assert "SQL" not in queries[0]


def test_query_builder_dedupes_roles_case_insensitively():
    queries = build_job_search_queries(["AI Engineer", "ai engineer"], max_queries=4)
    assert len(queries) == 1


def test_query_builder_zero_max_queries_returns_empty():
    assert build_job_search_queries(["AI Engineer"], max_queries=0) == []


def test_query_builder_falls_back_when_no_roles():
    queries = build_job_search_queries([], max_queries=2)
    assert queries == ["jobs job openings"]


# ---------------------------------------------------------------------------
# ingest_jobs_node override path + DEMO_MODE unaffected
# ---------------------------------------------------------------------------


def test_ingest_jobs_node_uses_override_when_present():
    override = [candidate_to_job_posting_dict(build_candidate(_result()))]
    state = {}
    config = {"configurable": {"job_source_override": override}}

    result = ingest_jobs_node(state, config)

    assert result["raw_jobs"] == override
    assert result["counts"]["ingested"] == 1
    messages = [e["message"] for e in result["decision_trace"]]
    assert any("live web discovery" in m for m in messages)
    assert not any("demo jobs ingested" in m for m in messages)


def test_ingest_jobs_node_default_path_unchanged_without_override():
    state = {}
    config = {"configurable": {}}

    result = ingest_jobs_node(state, config)

    messages = [e["message"] for e in result["decision_trace"]]
    assert any("demo jobs ingested" in m for m in messages)


def test_ingest_jobs_node_override_flows_into_normalize_dedupe_quality():
    from src.graph.nodes.jobs import dedupe_jobs_node, normalize_jobs_node, score_job_quality_node

    override = [candidate_to_job_posting_dict(build_candidate(_result()))]
    config = {"configurable": {"job_source_override": override}}

    ingested = ingest_jobs_node({}, config)
    normalized = normalize_jobs_node({"raw_jobs": ingested["raw_jobs"]}, config)
    deduped = dedupe_jobs_node({"normalized_jobs": normalized["normalized_jobs"]}, config)
    quality = score_job_quality_node({"deduped_jobs": deduped["deduped_jobs"]}, config)

    assert len(deduped["deduped_jobs"]) == 1
    assert len(quality["job_quality_results"]) == 1


def test_sparse_web_result_gets_reduced_job_quality_via_existing_service():
    sparse_result = _result(
        title="Data Engineer",
        url="https://boards.greenhouse.io/acme/jobs/999",
        snippet="",
        highlights=[],
    )
    # Force LIKELY_JOB classification for this test regardless of the
    # heuristic score, since the point is to verify job-quality behavior on
    # a sparse *converted* posting, not re-test the classifier here.
    from src.models.web_job_search import JobPostingCandidate

    candidate = JobPostingCandidate(result=sparse_result, classification="LIKELY_JOB")
    job_dict = candidate_to_job_posting_dict(candidate)
    job = JobPosting(**job_dict)

    result = score_job_quality(job)

    assert result.requirement_completeness == "LOW" or "missing_description" in result.flags
    assert result.quality_score < 100.0


# ---------------------------------------------------------------------------
# DEMO_MODE never calls You.com
# ---------------------------------------------------------------------------


def test_demo_mode_workflow_never_calls_you_search(monkeypatch):
    from src.graph.checkpointing import get_sqlite_checkpointer
    from src.graph.workflow import build_workflow
    from src.llm.provider import get_llm_client

    calls = {"n": 0}

    def fake_search_jobs(*args, **kwargs):
        calls["n"] += 1
        raise AssertionError("you_search.search_jobs must never be called in the DEMO_MODE flow")

    monkeypatch.setattr(you_search, "search_jobs", fake_search_jobs)

    settings = Settings(demo_mode=True)
    llm_client = get_llm_client(settings)
    checkpointer = get_sqlite_checkpointer(":memory:")
    graph = build_workflow(checkpointer)

    thread_id = "demo-mode-you-search-guard"
    config = {
        "configurable": {
            "thread_id": thread_id,
            "llm_client": llm_client,
            "job_batch_path": "data/sample_jobs.json",
        }
    }
    initial_state = {
        "run_id": thread_id,
        "candidate_id": "cand-demo-mode-guard",
        "resume_file_path": "data/sample_candidate/demo_resume.txt",
        "preferences": {"target_roles": ["AI Engineer"], "preferred_work_modes": ["REMOTE"]},
        "workflow_status": "NOT_STARTED",
    }
    graph.invoke(initial_state, config=config)

    assert calls["n"] == 0


# ---------------------------------------------------------------------------
# Streamlit app: "Search Live Jobs" button is the only trigger for a paid call
# ---------------------------------------------------------------------------


def _fake_you_search_result():
    from src.models.web_job_search import WebJobSearchResult
    from src.services.you_search import YouSearchResult

    return YouSearchResult(
        query="q",
        results=[
            WebJobSearchResult(
                search_result_id="r1",
                title="Senior Backend Engineer at Acme",
                url="https://boards.greenhouse.io/acme/jobs/1",
                snippet="We are hiring. Apply now! Responsibilities: build APIs. Requirements: 5 years of experience.",
                highlights=[],
                search_query="q",
            )
        ],
        total_results=1,
        attempts=1,
    )


def test_streamlit_no_you_search_call_without_live_search_configured(monkeypatch):
    """Default env (no YOU_SEARCH_ENABLED) -- LIVE SEARCH mode must show a
    degraded message and never call you_search.search_jobs."""
    from streamlit.testing.v1 import AppTest

    calls = {"n": 0}
    monkeypatch.setattr(you_search, "search_jobs", lambda *a, **k: calls.__setitem__("n", calls["n"] + 1) or _fake_you_search_result())

    at = AppTest.from_file(_APP_PATH)
    at.timeout = 60
    at.run()
    at.sidebar.radio[0].set_value("Candidate").run()
    at.checkbox[0].set_value(True)
    at.button[0].click().run()
    at.sidebar.radio[0].set_value("Opportunities").run()
    at.radio[0].set_value("LIVE SEARCH").run()

    assert not at.exception
    assert calls["n"] == 0


def test_streamlit_button_click_calls_you_search_exactly_once_reruns_do_not(monkeypatch):
    """Only the explicit "Search Live Jobs" button click may call
    you_search.search_jobs. A bare rerun from an unrelated widget must never
    trigger it, and a second click with identical parameters must be served
    from the session cache rather than issuing a second paid call."""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("YOU_SEARCH_ENABLED", "true")
    monkeypatch.setenv("YDC_API_KEY", _FAKE_KEY)

    calls = {"n": 0}

    def fake_search_jobs(*args, **kwargs):
        calls["n"] += 1
        return _fake_you_search_result()

    monkeypatch.setattr(you_search, "search_jobs", fake_search_jobs)

    at = AppTest.from_file(_APP_PATH)
    at.timeout = 60
    at.run()
    at.sidebar.radio[0].set_value("Candidate").run()
    at.checkbox[0].set_value(True)
    at.button[0].click().run()
    at.sidebar.radio[0].set_value("Opportunities").run()
    at.radio[0].set_value("LIVE SEARCH").run()

    assert calls["n"] == 0  # switching modes alone must never call it

    # A bare rerun from an unrelated widget must not trigger a call.
    at.number_input[0].set_value(3).run()
    assert calls["n"] == 0

    search_button = [b for b in at.button if b.label == "Search Live Jobs"][0]
    search_button.click().run()
    assert not at.exception
    assert calls["n"] == 1

    # A second click with identical parameters must be served from cache.
    at.sidebar.radio[0].set_value("Opportunities").run()
    search_button_again = [b for b in at.button if b.label == "Search Live Jobs"][0]
    search_button_again.click().run()
    assert calls["n"] == 1


def test_streamlit_demo_mode_smoke_test_never_calls_you_search(monkeypatch):
    """Full offline DEMO_MODE smoke test: Candidate -> Run search ->
    Opportunities, with no YOU_SEARCH_ENABLED set. Confirms the default
    certification demo path never touches you_search.search_jobs."""
    from streamlit.testing.v1 import AppTest

    calls = {"n": 0}
    monkeypatch.setattr(you_search, "search_jobs", lambda *a, **k: calls.__setitem__("n", calls["n"] + 1) or _fake_you_search_result())

    at = AppTest.from_file(_APP_PATH)
    at.timeout = 60
    at.run()
    assert not at.exception

    at.sidebar.radio[0].set_value("Candidate").run()
    at.checkbox[0].set_value(True)
    at.button[0].click().run()
    assert not at.exception

    at.sidebar.radio[0].set_value("Opportunities").run()
    assert not at.exception
    assert len(at.button) > 1  # opportunity cards rendered

    assert calls["n"] == 0
