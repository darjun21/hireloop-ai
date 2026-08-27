"""
Category 8: Failure Recovery.

Simulates realistic failure conditions and classifies the observed outcome:

- RECOVERED: the system detected the failure and produced a correct/normal
  result anyway (e.g. fallback provider engaged).
- DEGRADED: the system continued with reduced functionality but a safe,
  honest result (e.g. a partial ranking, a documented warning).
- SAFE_FAILURE: the system stopped/raised a controlled, typed error rather
  than crash or silently misbehave.
- UNSAFE_FAILURE: the system crashed with an unhandled exception, or
  produced an unsafe/ungrounded result silently. Target is 0 of these.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command
from pydantic import ValidationError

from src.agents.profile_agent import ProfileAgent
from src.agents.truth_guard import classify_modification
from src.llm.base import RetryPolicy
from src.llm.client import LLMClient
from src.llm.errors import HireLoopLLMError, LLMErrorType
from src.llm.mock_provider import MockLLMProvider
from src.services.job_ingestion import JobIngestionError, load_seeded_jobs
from src.services.resume_parser import parse_resume_bytes
from evals.common import CategorySummary, EvalCase, summarize
from tests.fakes import ScriptedProvider
from tests.graph_helpers import build_app, initial_state, make_config, write_job_batch
from tests.test_truth_guard import _mod as _tg_mod  # reuse small fixture builders, not the tests themselves
from tests.test_truth_guard import _pool as _tg_pool
from tests.test_truth_guard import _rich_profile as _tg_rich_profile

CATEGORY = "failure_recovery"

_OUTCOME_RANK = {"RECOVERED": 0, "DEGRADED": 1, "SAFE_FAILURE": 2, "UNSAFE_FAILURE": 3}


def _memory_checkpointer() -> SqliteSaver:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    saver = SqliteSaver(conn)
    saver.setup()
    return saver


def _case(scenario_id: str, outcome: str, detail: str, expected_max: str = "SAFE_FAILURE") -> EvalCase:
    """A scenario 'passes' if its observed outcome is at or below (better
    than or equal to) the worst acceptable outcome for that scenario --
    almost always SAFE_FAILURE or better; UNSAFE_FAILURE always fails."""
    passed = _OUTCOME_RANK[outcome] <= _OUTCOME_RANK[expected_max]
    return EvalCase(
        id=f"failure_recovery:{scenario_id}",
        category=CATEGORY,
        passed=passed,
        detail=f"outcome={outcome} expected_max={expected_max} :: {detail}",
        severity="critical" if outcome == "UNSAFE_FAILURE" else "normal",
        extra={"outcome": outcome},
    )


def run() -> CategorySummary:
    cases: list[EvalCase] = []

    # 1. Primary LLM provider unavailable -> fallback engages cleanly.
    try:
        failing_primary = ScriptedProvider("failing-primary", [LLMErrorType.PROVIDER_UNAVAILABLE])
        client = LLMClient(primary=failing_primary, fallback=MockLLMProvider(), retry_policy=RetryPolicy(max_retries=0))
        agent = ProfileAgent(llm_client=client)
        profile, _validation = agent.build_profile("Jane Doe\n\nSKILLS\nPython, AWS\n", candidate_id="cand-fallback")
        outcome = "RECOVERED" if any(s.name.lower() == "python" for s in profile.skills) else "DEGRADED"
        detail = f"skills={[s.name for s in profile.skills]}"
    except Exception as exc:  # noqa: BLE001 - deliberately catching anything to classify, not to hide it
        outcome, detail = "UNSAFE_FAILURE", f"unhandled exception: {exc!r}"
    cases.append(_case("primary_llm_unavailable_fallback_engages", outcome, detail, expected_max="RECOVERED"))

    # 2. Malformed LLM output (schema/validation layer catches it) --
    #    a provider that always raises MALFORMED_RESPONSE with no fallback
    #    must surface as a controlled, typed error, not a raw crash.
    try:
        malformed_provider = ScriptedProvider("malformed", [LLMErrorType.MALFORMED_RESPONSE])
        client = LLMClient(primary=malformed_provider)
        agent = ProfileAgent(llm_client=client)
        agent.build_profile("Jane Doe\n\nSKILLS\nPython\n", candidate_id="cand-malformed")
        outcome, detail = "UNSAFE_FAILURE", "expected a HireLoopLLMError to be raised, but call succeeded silently"
    except HireLoopLLMError as exc:
        outcome, detail = "SAFE_FAILURE", f"raised typed HireLoopLLMError({exc.error_type.value}) as expected"
    except Exception as exc:  # noqa: BLE001
        outcome, detail = "UNSAFE_FAILURE", f"raised an untyped/unexpected exception: {exc!r}"
    cases.append(_case("malformed_llm_output_caught_as_typed_error", outcome, detail))

    # 3. Corrupt/unparseable resume input -> a controlled parse failure, not
    #    a crash and not a silently-empty "success".
    try:
        garbage_pdf_bytes = b"%PDF-1.4 this is not a real pdf structure \x00\x01\x02" * 5
        result = parse_resume_bytes(garbage_pdf_bytes, "resume.pdf")
        if result.success:
            outcome, detail = "UNSAFE_FAILURE", "corrupt PDF bytes were reported as a successful parse"
        else:
            outcome, detail = "SAFE_FAILURE", f"error={result.error!r}"
    except Exception as exc:  # noqa: BLE001
        outcome, detail = "UNSAFE_FAILURE", f"unhandled exception on corrupt resume input: {exc!r}"
    cases.append(_case("corrupt_resume_input_fails_safely", outcome, detail))

    # 4. Empty job batch -> the workflow reaches a graceful no-results
    #    terminal state, not a crash and not a fabricated ranking.
    try:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            batch_path = write_job_batch(Path(tmp) / "empty.json", [])
            app = build_app(_memory_checkpointer())
            config = make_config("eval-failure-empty-batch", job_batch_path=batch_path)
            result = app.invoke(initial_state("eval-failure-empty-batch"), config=config)
        if result.get("workflow_status") == "COMPLETED_WITH_NO_RESULTS":
            outcome, detail = "RECOVERED", "graph reached COMPLETED_WITH_NO_RESULTS cleanly"
        elif "__interrupt__" not in result and result.get("workflow_status") != "FAILED":
            outcome, detail = "DEGRADED", f"workflow_status={result.get('workflow_status')}"
        else:
            outcome, detail = "SAFE_FAILURE", f"workflow_status={result.get('workflow_status')}"
    except Exception as exc:  # noqa: BLE001
        outcome, detail = "UNSAFE_FAILURE", f"unhandled exception on empty job batch: {exc!r}"
    cases.append(_case("empty_job_batch_no_crash", outcome, detail, expected_max="RECOVERED"))

    # 5. Malformed job record inside an otherwise-valid batch: one bad row
    #    (missing required 'title') is skipped with a warning, not a crash,
    #    and does not block the good rows in the same batch.
    try:
        import tempfile

        good_job = {
            "job_id": "good-1", "title": "AI Engineer", "company": "Acme",
            "description": "Build and operate AI systems for our platform end to end with product and research.",
            "required_skills": ["Python"], "url": "https://a.example.com/good-1",
        }
        bad_job = {"job_id": "bad-1", "company": "Acme"}  # missing required 'title'
        with tempfile.TemporaryDirectory() as tmp:
            batch_path = Path(tmp) / "mixed.json"
            batch_path.write_text(json.dumps([good_job, bad_job]), encoding="utf-8")
            jobs, warnings = load_seeded_jobs(str(batch_path))
        if len(jobs) == 1 and jobs[0]["job_id"] == "good-1" and warnings:
            outcome, detail = "RECOVERED", f"warnings={warnings}"
        else:
            outcome, detail = "UNSAFE_FAILURE", f"jobs={jobs} warnings={warnings}"
    except (ValidationError, JobIngestionError) as exc:
        outcome, detail = "SAFE_FAILURE", f"raised a controlled ingestion error: {exc!r}"
    except Exception as exc:  # noqa: BLE001
        outcome, detail = "UNSAFE_FAILURE", f"unhandled exception on malformed job record: {exc!r}"
    cases.append(_case("malformed_job_record_skipped_not_crashed", outcome, detail, expected_max="RECOVERED"))

    # 6. Truth Guard's LLM layer is unavailable -> the deterministic layers
    #    still produce a safe, fail-closed result (never VERIFIED, never a
    #    crash) for a fragment that needed semantic judgment.
    try:
        profile = _tg_rich_profile()
        failing_client = LLMClient(primary=ScriptedProvider("tg-failing", [LLMErrorType.AUTH_ERROR]))
        result = classify_modification(
            _tg_mod("Designed PostgreSQL-backed services."), profile, _tg_pool(profile), llm_client=failing_client
        )
        if result.status.value == "VERIFIED":
            outcome, detail = "UNSAFE_FAILURE", f"Truth Guard returned VERIFIED despite an LLM outage: {result}"
        else:
            outcome, detail = "SAFE_FAILURE", f"fail-closed status={result.status.value}"
    except Exception as exc:  # noqa: BLE001
        outcome, detail = "UNSAFE_FAILURE", f"unhandled exception when Truth Guard's LLM layer was unavailable: {exc!r}"
    cases.append(_case("truth_guard_llm_unavailable_fails_closed", outcome, detail))

    unsafe_count = sum(1 for c in cases if c.extra.get("outcome") == "UNSAFE_FAILURE")
    counters = {
        outcome_name: sum(1 for c in cases if c.extra.get("outcome") == outcome_name) for outcome_name in _OUTCOME_RANK
    }
    severe_failure = unsafe_count > 0

    return summarize(
        CATEGORY, cases, counters=counters, severe_failure=severe_failure,
        severe_failure_reason=f"{unsafe_count} UNSAFE_FAILURE scenario(s) observed" if severe_failure else "",
    )


if __name__ == "__main__":
    result = run()
    print(result.to_dict())
