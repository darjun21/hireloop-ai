"""
LangGraph workflow tests (Part O). No real network calls anywhere -- every
LLM interaction goes through MockLLMProvider or a scripted test double.
"""

from __future__ import annotations

import json
import sqlite3

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from src.llm.client import LLMClient
from src.llm.schemas import MatchAnalysisLLMOutput
from tests.graph_helpers import (
    SelectiveFailureProvider,
    build_app,
    drive_to_completion,
    initial_state,
    make_config,
    make_job_dict,
    write_job_batch,
)


def _memory_checkpointer() -> SqliteSaver:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    saver = SqliteSaver(conn)
    saver.setup()
    return saver


# 1. Happy path reaches human interrupt.
def test_happy_path_reaches_human_interrupt():
    app = build_app(_memory_checkpointer())
    config = make_config("run-1")

    result = app.invoke(initial_state("run-1"), config=config)

    assert "__interrupt__" in result
    payload = result["__interrupt__"][0].value
    assert payload["action_required"] == "SELECT_JOB_OR_CANCEL"
    assert len(payload["eligible_selections"]) > 0
    assert result["workflow_status"] == "RUNNING"


# 2. State checkpoint exists at human interrupt.
def test_checkpoint_exists_at_human_interrupt():
    checkpointer = _memory_checkpointer()
    app = build_app(checkpointer)
    config = make_config("run-2")

    app.invoke(initial_state("run-2"), config=config)

    snapshot = app.get_state(config)
    assert snapshot.next == ("human_select_job",)
    assert snapshot.values.get("ranked_job_ids")


# 3 & 4. Valid human selection resumes graph and the selected job persists.
def test_valid_selection_resumes_graph_and_persists_selection():
    app = build_app(_memory_checkpointer())
    config = make_config("run-3")

    result = app.invoke(initial_state("run-3"), config=config)
    top_job_id = result["__interrupt__"][0].value["eligible_selections"][0]["job_id"]

    after_selection = app.invoke(Command(resume={"action": "SELECT", "job_id": top_job_id}), config=config)

    # Selection itself is confirmed immediately -- the graph then continues
    # into Phase 4 resume tailoring rather than ending here.
    assert after_selection["selected_job_id"] == top_job_id
    assert after_selection["human_job_selection_status"] == "SELECTED"
    assert "__interrupt__" in after_selection  # now paused inside Phase 4, not finished

    final = drive_to_completion(app, config, after_selection)
    assert "__interrupt__" not in final
    assert final["workflow_status"] == "COMPLETED"
    assert final["selected_job_id"] == top_job_id

    # persists in the checkpoint after resume, not just the return value
    snapshot = app.get_state(config)
    assert snapshot.values["selected_job_id"] == top_job_id


# 5. Invalid job selection is rejected and the graph keeps waiting.
def test_invalid_job_selection_is_rejected_and_keeps_waiting():
    app = build_app(_memory_checkpointer())
    config = make_config("run-5")

    app.invoke(initial_state("run-5"), config=config)
    result = app.invoke(Command(resume={"action": "SELECT", "job_id": "not-a-real-job"}), config=config)

    assert "__interrupt__" in result
    snapshot = app.get_state(config)
    assert any(task.name == "human_select_job" and task.interrupts for task in snapshot.tasks)
    assert snapshot.values.get("selected_job_id") is None
    rejection_message = result["__interrupt__"][0].value.get("error", "")
    assert "not-a-real-job" in rejection_message


# 6. Human cancellation produces CANCELLED.
def test_human_cancellation_produces_cancelled_status():
    app = build_app(_memory_checkpointer())
    config = make_config("run-6")

    app.invoke(initial_state("run-6"), config=config)
    result = app.invoke(Command(resume={"action": "CANCEL"}), config=config)

    assert result["workflow_status"] == "CANCELLED"
    assert any(e["category"] == "HUMAN_CANCELLED" for e in result["errors"])


# 7. Corrupt/missing resume fails safely.
def test_missing_resume_file_fails_safely():
    app = build_app(_memory_checkpointer())
    config = make_config("run-7")

    result = app.invoke(initial_state("run-7", resume_file_path="data/does_not_exist_at_all.txt"), config=config)

    assert result["workflow_status"] == "FAILED"
    assert result["errors"][0]["category"] == "RESUME_PARSE_ERROR"
    assert "__interrupt__" not in result


# 8. Empty job batch leads to a graceful no-results outcome.
def test_empty_job_batch_leads_to_no_results(tmp_path):
    batch_path = write_job_batch(tmp_path / "empty.json", [])
    app = build_app(_memory_checkpointer())
    config = make_config("run-8", job_batch_path=batch_path)

    result = app.invoke(initial_state("run-8"), config=config)

    assert result["workflow_status"] == "COMPLETED_WITH_NO_RESULTS"
    assert result["no_suitable_jobs_reason"]["ingested"] == 0
    assert "Broaden target roles" in result["no_suitable_jobs_reason"]["recommendation"]


# 9. Duplicate-heavy batch still works end to end.
def test_duplicate_heavy_batch_still_reaches_interrupt(tmp_path):
    jobs = [
        make_job_dict(f"dup-{i}", title="Platform Engineer", company="Acme AI", url=f"https://a.example.com/{i}")
        for i in range(1, 6)
    ]
    batch_path = write_job_batch(tmp_path / "dupes.json", jobs)

    app = build_app(_memory_checkpointer())
    config = make_config("run-9", job_batch_path=batch_path)

    result = app.invoke(initial_state("run-9"), config=config)

    assert "__interrupt__" in result
    assert result["counts"]["ingested"] == 5
    assert result["counts"]["duplicates_removed"] == 4
    assert result["counts"]["unique_after_dedup"] == 1


# 10. Match Analyst individual failure degrades gracefully.
def test_match_analyst_partial_failure_degrades_gracefully(tmp_path):
    jobs = [make_job_dict(f"job-{i}", url=f"https://a.example.com/{i}") for i in range(5)]
    batch_path = write_job_batch(tmp_path / "jobs.json", jobs)

    from src.llm.base import RetryPolicy

    provider = SelectiveFailureProvider(fail_schema=MatchAnalysisLLMOutput, fail_count=1)
    llm_client = LLMClient(primary=provider, retry_policy=RetryPolicy(max_retries=0))

    app = build_app(_memory_checkpointer())
    config = make_config("run-10", llm_client=llm_client, job_batch_path=batch_path)

    result = app.invoke(initial_state("run-10"), config=config)

    assert "__interrupt__" in result
    assert result["opportunity_scores"]  # deterministic scoring untouched
    assert result["ranked_job_ids"]
    assert len(result["match_analyses"]) < len(result["ranked_job_ids"][:5])  # at least one missing
    assert any("failed and were marked unavailable" in e["message"] for e in result["decision_trace"])


# 11. Total LLM failure during match-analysis still returns deterministic ranked jobs.
def test_total_match_analyst_failure_still_returns_deterministic_rankings(tmp_path):
    jobs = [make_job_dict(f"job-{i}", url=f"https://a.example.com/{i}") for i in range(3)]
    batch_path = write_job_batch(tmp_path / "jobs.json", jobs)

    from src.llm.base import RetryPolicy

    provider = SelectiveFailureProvider(fail_schema=MatchAnalysisLLMOutput, always_fail=True)
    llm_client = LLMClient(primary=provider, retry_policy=RetryPolicy(max_retries=0))

    app = build_app(_memory_checkpointer())
    config = make_config("run-11", llm_client=llm_client, job_batch_path=batch_path)

    result = app.invoke(initial_state("run-11"), config=config)

    assert "__interrupt__" in result
    assert result["match_analyses"] == {}
    assert len(result["opportunity_scores"]) == 3
    assert len(result["ranked_job_ids"]) == 3
    assert any("provider outage" in e["message"] for e in result["decision_trace"])


# 12. Scoring configuration failure halts the workflow.
def test_invalid_scoring_configuration_halts(monkeypatch):
    import src.config.scoring as scoring_config
    from src.config.scoring import ScoringWeights

    bad_weights = ScoringWeights(
        skill_match=0.5, experience_match=0.5, role_alignment=0.5, location_work_mode=0, candidate_preference=0,
        historical_signal=0, job_quality=0,
    )
    monkeypatch.setattr(scoring_config, "CURRENT_WEIGHTS", bad_weights)

    app = build_app(_memory_checkpointer())
    config = make_config("run-12")

    result = app.invoke(initial_state("run-12"), config=config)

    assert result["workflow_status"] == "FAILED"
    assert result["errors"][-1]["category"] == "SCORING_ERROR"
    assert "__interrupt__" not in result


# 13. Decision Trace contains expected major events.
def test_decision_trace_contains_expected_major_events():
    app = build_app(_memory_checkpointer())
    config = make_config("run-13")

    interrupted = app.invoke(initial_state("run-13"), config=config)
    top_job_id = interrupted["__interrupt__"][0].value["eligible_selections"][0]["job_id"]
    after_selection = app.invoke(Command(resume={"action": "SELECT", "job_id": top_job_id}), config=config)
    result = drive_to_completion(app, config, after_selection)

    messages = [e["message"] for e in result["decision_trace"]]

    assert any("Resume parsed successfully" in m for m in messages)
    assert any("Candidate profile created" in m for m in messages)
    assert any("demo jobs ingested" in m for m in messages)
    assert any("duplicate posting" in m for m in messages)
    assert any("opportunities scored using scoring model" in m for m in messages)
    assert any("selected for qualitative analysis" in m for m in messages)
    assert any("opportunities ranked" in m for m in messages)
    assert any("Human review required" in m for m in messages)
    assert any("Human selected job" in m for m in messages)
    assert any("Job selection confirmed" in m for m in messages)
    assert any("Phase 4 resume tailoring completed" in m for m in messages)
    assert any("Application tracking workflow completed" in m for m in messages)


# 14. Resume does not repeat already-completed expensive steps.
def test_resume_does_not_repeat_completed_steps():
    app = build_app(_memory_checkpointer())
    config = make_config("run-14")

    result = app.invoke(initial_state("run-14"), config=config)
    top_job_id = result["__interrupt__"][0].value["eligible_selections"][0]["job_id"]

    final = app.invoke(Command(resume={"action": "SELECT", "job_id": top_job_id}), config=config)

    profile_events = [e for e in final["decision_trace"] if e["action"] == "build_candidate_profile"]
    scoring_events = [e for e in final["decision_trace"] if e["action"] == "score_opportunities"]
    assert len(profile_events) == 1
    assert len(scoring_events) == 1


# 15. State remains serializable/checkpointable.
def test_state_remains_json_serializable():
    app = build_app(_memory_checkpointer())
    config = make_config("run-15")

    app.invoke(initial_state("run-15"), config=config)
    snapshot = app.get_state(config)

    # No custom encoder needed -- every field is already a JSON-safe dict.
    serialized = json.dumps(snapshot.values)
    assert isinstance(serialized, str)
    assert json.loads(serialized) == snapshot.values


def test_no_provider_clients_or_connections_in_state():
    app = build_app(_memory_checkpointer())
    config = make_config("run-16")

    app.invoke(initial_state("run-16"), config=config)
    snapshot = app.get_state(config)

    assert "llm_client" not in snapshot.values
    _JSON_SAFE_TYPES = (dict, list, str, int, float, bool, type(None))
    for key, value in snapshot.values.items():
        assert isinstance(value, _JSON_SAFE_TYPES), f"state[{key!r}] is not JSON-safe: {type(value)!r}"
