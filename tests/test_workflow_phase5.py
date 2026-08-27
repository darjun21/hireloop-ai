"""
Phase 5 graph-level tests: application tracking (main graph) and the
separate outcome-update workflow. No real network calls.
"""

from __future__ import annotations

import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from src.graph.workflow import build_outcome_update_workflow
from src.llm.client import LLMClient
from src.services.database import get_connection, init_schema
from tests.graph_helpers import build_app, initial_state, make_application_tracker, make_config


def _memory_checkpointer() -> SqliteSaver:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    saver = SqliteSaver(conn)
    saver.setup()
    return saver


def _run_to_application_interrupt(app, config, thread_id):
    app.invoke(initial_state(thread_id), config=config)
    app.invoke(Command(resume={"action": "SELECT", "job_id": "job_ai_001"}), config=config)
    return app.invoke(Command(resume={"action": "APPROVE_ALL"}), config=config)


# --- Application tracking (main graph) ---


def test_create_application_and_mark_applied():
    app = build_app(_memory_checkpointer())
    tracker = make_application_tracker()
    config = make_config("p5-applied", application_tracker=tracker)

    interrupted = _run_to_application_interrupt(app, config, "p5-applied")
    assert "__interrupt__" in interrupted
    payload = interrupted["__interrupt__"][0].value
    assert payload["application"]["current_status"] == "READY_FOR_REVIEW"

    final = app.invoke(Command(resume={"action": "MARK_APPLIED"}), config=config)

    assert final["workflow_status"] == "COMPLETED"
    application_id = final["application_id"]
    stored = tracker.get_application(application_id)
    assert stored.current_status.value == "APPLIED"
    history = tracker.get_application_history(application_id)
    assert [e.event_type.value for e in history] == ["APPLICATION_CREATED", "APPLIED"]


def test_save_for_later():
    app = build_app(_memory_checkpointer())
    tracker = make_application_tracker()
    config = make_config("p5-save", application_tracker=tracker)

    _run_to_application_interrupt(app, config, "p5-save")
    final = app.invoke(Command(resume={"action": "SAVE_FOR_LATER"}), config=config)

    application_id = final["application_id"]
    stored = tracker.get_application(application_id)
    assert stored.current_status.value == "SAVED"
    assert final["workflow_status"] == "COMPLETED"


def test_application_action_cancel():
    app = build_app(_memory_checkpointer())
    tracker = make_application_tracker()
    config = make_config("p5-cancel", application_tracker=tracker)

    _run_to_application_interrupt(app, config, "p5-cancel")
    final = app.invoke(Command(resume={"action": "CANCEL"}), config=config)

    assert final["workflow_status"] == "CANCELLED"


def test_invalid_application_action_rejected():
    app = build_app(_memory_checkpointer())
    tracker = make_application_tracker()
    config = make_config("p5-invalid-action", application_tracker=tracker)

    _run_to_application_interrupt(app, config, "p5-invalid-action")
    result = app.invoke(Command(resume={"action": "SUBMIT_EXTERNALLY"}), config=config)

    assert "__interrupt__" in result  # rejected, still waiting -- never externally submitted


# --- Outcome update workflow (separate graph) ---


def _create_applied_application(tracker) -> str:
    app = build_app(_memory_checkpointer())
    config = make_config("p5-outcome-seed", application_tracker=tracker)
    _run_to_application_interrupt(app, config, "p5-outcome-seed")
    final = app.invoke(Command(resume={"action": "MARK_APPLIED"}), config=config)
    return final["application_id"]


def test_outcome_workflow_records_interview_and_refreshes_analytics():
    from src.config.settings import Settings
    from src.llm.mock_provider import MockLLMProvider

    tracker = make_application_tracker()
    application_id = _create_applied_application(tracker)

    outcome_app = build_outcome_update_workflow(_memory_checkpointer())
    config = {
        "configurable": {
            "thread_id": "outcome-1",
            "llm_client": LLMClient(primary=MockLLMProvider()),
            "application_tracker": tracker,
            "settings": Settings(default_llm_provider="mock", demo_mode=True),
        }
    }

    interrupted = outcome_app.invoke({"target_application_id": application_id, "workflow_status": "NOT_STARTED"}, config=config)
    assert "__interrupt__" in interrupted
    payload = interrupted["__interrupt__"][0].value
    assert payload["application"]["current_status"] == "APPLIED"

    final = outcome_app.invoke(Command(resume={"action": "INTERVIEW"}), config=config)

    assert final["workflow_status"] == "COMPLETED"
    stored = tracker.get_application(application_id)
    assert stored.current_status.value == "INTERVIEW"
    assert final["outcome_analytics"]["total_resolved"] > 0
    assert "decision_trace" in final
    messages = [e["message"] for e in final["decision_trace"]]
    assert any("Outcome analytics refreshed" in m for m in messages)
    assert any("Learning Agent generated" in m for m in messages)


def test_outcome_workflow_cancel():
    from src.config.settings import Settings
    from src.llm.mock_provider import MockLLMProvider

    tracker = make_application_tracker()
    application_id = _create_applied_application(tracker)

    outcome_app = build_outcome_update_workflow(_memory_checkpointer())
    config = {
        "configurable": {
            "thread_id": "outcome-cancel",
            "llm_client": LLMClient(primary=MockLLMProvider()),
            "application_tracker": tracker,
            "settings": Settings(default_llm_provider="mock", demo_mode=False),
        }
    }
    outcome_app.invoke({"target_application_id": application_id, "workflow_status": "NOT_STARTED"}, config=config)
    final = outcome_app.invoke(Command(resume={"action": "CANCEL"}), config=config)

    assert final["workflow_status"] == "CANCELLED"


def test_outcome_workflow_missing_application_fails_safely():
    from src.config.settings import Settings
    from src.llm.mock_provider import MockLLMProvider

    tracker = make_application_tracker()
    outcome_app = build_outcome_update_workflow(_memory_checkpointer())
    config = {
        "configurable": {
            "thread_id": "outcome-missing",
            "llm_client": LLMClient(primary=MockLLMProvider()),
            "application_tracker": tracker,
            "settings": Settings(default_llm_provider="mock", demo_mode=False),
        }
    }
    result = outcome_app.invoke({"target_application_id": "does-not-exist", "workflow_status": "NOT_STARTED"}, config=config)

    assert result["workflow_status"] == "FAILED"
    assert result["errors"][0]["category"] == "INVALID_STATE"


def test_suspicious_outcome_sequence_requires_confirmation():
    """OFFER recorded before the application was ever marked APPLIED is an
    unusual sequence -- warned, not silently accepted, per Part X."""
    from datetime import datetime, timezone

    from src.config.settings import Settings
    from src.llm.mock_provider import MockLLMProvider
    from src.models.application import Application
    from src.models.enums import ApplicationStatus

    tracker = make_application_tracker()
    tracker.create_application(
        Application(
            application_id="app-never-applied",
            candidate_id="cand-1",
            job_id="job-1",
            opportunity_score_version="v1.0",
            created_at=datetime.now(timezone.utc),
            current_status=ApplicationStatus.READY_FOR_REVIEW,
        )
    )

    outcome_app = build_outcome_update_workflow(_memory_checkpointer())
    config = {
        "configurable": {
            "thread_id": "outcome-suspicious",
            "llm_client": LLMClient(primary=MockLLMProvider()),
            "application_tracker": tracker,
            "settings": Settings(default_llm_provider="mock", demo_mode=False),
        }
    }
    outcome_app.invoke({"target_application_id": "app-never-applied", "workflow_status": "NOT_STARTED"}, config=config)

    # First attempt without confirmation -- rejected, re-prompted with a warning.
    warned = outcome_app.invoke(Command(resume={"action": "OFFER"}), config=config)
    assert "__interrupt__" in warned
    assert "warning" in warned["__interrupt__"][0].value

    # Resubmit with explicit confirmation -- proceeds.
    final = outcome_app.invoke(Command(resume={"action": "OFFER", "confirm": True}), config=config)
    assert tracker.get_application("app-never-applied").current_status.value == "OFFER"
