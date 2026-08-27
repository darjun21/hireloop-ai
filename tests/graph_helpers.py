"""Shared test helpers for LangGraph workflow tests. No real network calls."""

from __future__ import annotations

import json
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from src.graph.workflow import build_workflow
from src.llm.base import LLMResult
from src.llm.client import LLMClient
from src.llm.errors import HireLoopLLMError, LLMErrorType
from src.llm.mock_provider import MockLLMProvider
from src.llm.schemas import ProposedModificationLLM, TailorLLMOutput
from src.services.application_tracker import ApplicationTrackerService
from src.services.database import get_connection, init_schema

DEMO_RESUME_PATH = "data/sample_candidate/demo_resume.txt"


def build_app(checkpointer: SqliteSaver | None = None):
    return build_workflow(checkpointer=checkpointer)


def make_application_tracker() -> ApplicationTrackerService:
    conn = get_connection(":memory:")
    init_schema(conn)
    return ApplicationTrackerService(conn)


def make_config(thread_id: str, llm_client: LLMClient | None = None, **extra_configurable) -> dict:
    configurable = {
        "thread_id": thread_id,
        "llm_client": llm_client or LLMClient(primary=MockLLMProvider()),
        "application_tracker": make_application_tracker(),
        **extra_configurable,
    }
    return {"configurable": configurable}


def initial_state(
    run_id: str,
    resume_file_path: str = DEMO_RESUME_PATH,
    target_roles: list[str] | None = None,
) -> dict:
    return {
        "run_id": run_id,
        "candidate_id": f"cand-{run_id}",
        "resume_file_path": resume_file_path,
        "preferences": {"target_roles": target_roles or ["AI Engineer"], "preferred_work_modes": ["REMOTE"]},
        "workflow_status": "NOT_STARTED",
    }


def write_job_batch(path: Path, jobs: list[dict]) -> str:
    path.write_text(json.dumps(jobs), encoding="utf-8")
    return str(path)


def write_resume_file(path: Path, text: str) -> str:
    path.write_text(text, encoding="utf-8")
    return str(path)


def make_job_dict(job_id: str, **overrides) -> dict:
    defaults = dict(
        job_id=job_id,
        title=f"AI Engineer ({job_id})",
        company=f"Acme AI {job_id}",
        location="Remote",
        url=f"https://jobs.example.com/{job_id}",
        description=(
            "Build and operate AI systems for our platform team end to end, working closely with "
            "product and research on production machine learning features."
        ),
        required_skills=["Python", "Machine Learning"],
        preferred_skills=["AWS"],
        minimum_years_experience=2,
        employment_type="FULL_TIME",
        work_mode="REMOTE",
    )
    defaults.update(overrides)
    return defaults


def drive_to_completion(app, config: dict, result: dict) -> dict:
    """After a job has been SELECTed, resume through any remaining Phase 4
    (clarification, resume approval) and Phase 5 (application action)
    interrupts using the most permissive valid action each time, until the
    graph reaches a terminal state. Used by Phase 3 tests that only care
    that the graph *continues* correctly past job selection, not by Phase
    4/5 tests exercising that logic in detail."""
    while "__interrupt__" in result:
        payload = result["__interrupt__"][0].value
        if "clarification_required" in payload:
            response = {"action": "USE_SAFE_REWRITE"}
        elif "application" in payload and "allowed_actions" in payload and "modifications" not in payload:
            response = {"action": "MARK_APPLIED"}
        elif "modifications" in payload:
            response = {"action": "APPROVE_ALL"}
        else:
            raise AssertionError(f"drive_to_completion got an unexpected interrupt payload: {payload}")
        result = app.invoke(Command(resume=response), config=config)
    return result


class SelectiveFailureProvider:
    """Delegates to a real MockLLMProvider except for calls whose schema
    matches `fail_schema`, which fail per the given policy. Used to test
    Match Analyst degradation without touching resume/profile extraction."""

    def __init__(self, fail_schema, fail_count: int | None = None, always_fail: bool = False) -> None:
        self.name = "selective-failure"
        self._delegate = MockLLMProvider()
        self._fail_schema = fail_schema
        self._fail_count = fail_count
        self._always_fail = always_fail
        self._calls = 0

    def invoke(self, *args, **kwargs) -> LLMResult:
        return self._delegate.invoke(*args, **kwargs)

    def structured_output(self, prompt, schema, *, system=None, temperature=0.0):
        if schema is self._fail_schema:
            self._calls += 1
            if self._always_fail or (self._fail_count is not None and self._calls <= self._fail_count):
                raise HireLoopLLMError(LLMErrorType.PROVIDER_UNAVAILABLE, "scripted failure", provider=self.name)
        return self._delegate.structured_output(prompt, schema, system=system, temperature=temperature)

    def health_check(self) -> bool:
        return True


class FixedTailorProvider:
    """Delegates everything to a real MockLLMProvider except
    TailorLLMOutput, which it always returns as a fixed, caller-supplied
    set of modifications -- used to deterministically exercise specific
    Truth Guard verdicts (e.g. NEEDS_HUMAN_CONFIRMATION) at the graph
    level without depending on the general-purpose mock Tailor's phrasing."""

    def __init__(self, modifications: list[ProposedModificationLLM]) -> None:
        self.name = "fixed-tailor"
        self._delegate = MockLLMProvider()
        self._modifications = modifications

    def invoke(self, *args, **kwargs) -> LLMResult:
        return self._delegate.invoke(*args, **kwargs)

    def structured_output(self, prompt, schema, *, system=None, temperature=0.0):
        if schema is TailorLLMOutput:
            output = TailorLLMOutput(modifications=self._modifications)
            return output, LLMResult(text=output.model_dump_json(), provider=self.name, model="fixed-tailor")
        return self._delegate.structured_output(prompt, schema, system=system, temperature=temperature)

    def health_check(self) -> bool:
        return True
