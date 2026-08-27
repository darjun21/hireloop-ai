"""
Application tracking nodes (Phase 5, main graph): create_application ->
human_application_action -> phase5_application_complete.

The user is only marking what happened — nothing is ever submitted
externally. `create_application` persists a READY_FOR_REVIEW Application
record; `human_application_action` lets the human mark it APPLIED, save it
for later, or cancel.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt

from src.config.workflow import APPLICATION_ACTION_ALLOWED_ACTIONS
from src.graph.helpers import make_error, trace_event
from src.graph.state import HireLoopState
from src.models.application import Application
from src.models.application_event import ApplicationEvent
from src.models.enums import ApplicationEventType, ApplicationStatus
from src.models.workflow_error import ErrorCategory
from src.models.workflow_status import WorkflowStatus


def create_application_node(state: HireLoopState, config: RunnableConfig) -> dict:
    tracker = config["configurable"]["application_tracker"]
    candidate_id = state["candidate_id"]
    selected_job_id = state["selected_job_id"]
    score = state.get("opportunity_scores", {}).get(selected_job_id, {})

    application = Application(
        application_id=f"app-{uuid4().hex[:10]}",
        candidate_id=candidate_id,
        job_id=selected_job_id,
        selected_resume_version_id=state.get("current_resume_version_id"),
        opportunity_score=score.get("final_score"),
        opportunity_score_version=score.get("scoring_version", "unknown"),
        created_at=datetime.now(timezone.utc),
        current_status=ApplicationStatus.READY_FOR_REVIEW,
        source="hireloop",
    )
    tracker.create_application(application)
    tracker.record_event(
        ApplicationEvent(
            event_id=f"ev-{uuid4().hex[:10]}",
            application_id=application.application_id,
            candidate_id=candidate_id,
            job_id=selected_job_id,
            event_type=ApplicationEventType.APPLICATION_CREATED,
            source="system",
        )
    )

    return {
        "application_id": application.application_id,
        "current_application": application.model_dump(mode="json"),
        "decision_trace": [
            trace_event("application_tracking", "create_application", f"Application record {application.application_id} created.")
        ],
        "current_step": "create_application",
    }


def human_application_action_node(state: HireLoopState, config: RunnableConfig) -> dict:
    tracker = config["configurable"]["application_tracker"]
    application = Application(**state["current_application"])

    events = []
    prompt = {
        "application": {
            "application_id": application.application_id,
            "job_id": application.job_id,
            "current_status": application.current_status.value,
            "opportunity_score": application.opportunity_score,
        },
        "allowed_actions": sorted(APPLICATION_ACTION_ALLOWED_ACTIONS),
    }

    while True:
        human_input = interrupt(prompt) or {}
        action = human_input.get("action")
        if action in APPLICATION_ACTION_ALLOWED_ACTIONS:
            break
        events.append(trace_event("application_tracking", "human_application_action", f"Rejected invalid action {action!r}; awaiting a valid choice."))
        prompt = {**prompt, "error": f"invalid action {action!r}"}

    if action == "CANCEL":
        events.append(trace_event("application_tracking", "human_application_action", "Human cancelled application tracking."))
        return {
            "workflow_status": WorkflowStatus.CANCELLED.value,
            "errors": [make_error("human_application_action", ErrorCategory.HUMAN_CANCELLED, "human cancelled application tracking")],
            "decision_trace": events,
            "current_step": "human_application_action",
        }

    if action == "MARK_APPLIED":
        application.current_status = ApplicationStatus.APPLIED
        application.applied_at = datetime.now(timezone.utc)
        tracker.update_application_status(application)
        tracker.record_event(
            ApplicationEvent(
                event_id=f"ev-{uuid4().hex[:10]}",
                application_id=application.application_id,
                candidate_id=application.candidate_id,
                job_id=application.job_id,
                event_type=ApplicationEventType.APPLIED,
                source="human",
            )
        )
        events.append(trace_event("application_tracking", "human_application_action", "Candidate marked application as APPLIED."))
    else:  # SAVE_FOR_LATER
        application.current_status = ApplicationStatus.SAVED
        tracker.update_application_status(application)
        tracker.record_event(
            ApplicationEvent(
                event_id=f"ev-{uuid4().hex[:10]}",
                application_id=application.application_id,
                candidate_id=application.candidate_id,
                job_id=application.job_id,
                event_type=ApplicationEventType.SAVED,
                source="human",
            )
        )
        events.append(trace_event("application_tracking", "human_application_action", "Application saved for later."))

    return {
        "current_application": application.model_dump(mode="json"),
        "application_action": action,
        "workflow_status": WorkflowStatus.RUNNING.value,
        "decision_trace": events,
        "current_step": "human_application_action",
    }


def phase5_application_complete_node(state: HireLoopState, config: RunnableConfig) -> dict:
    return {
        "workflow_status": WorkflowStatus.COMPLETED.value,
        "decision_trace": [trace_event("completion", "phase5_application_complete", "Application tracking workflow completed.")],
        "current_step": "phase5_application_complete",
    }
