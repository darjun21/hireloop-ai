"""
Outcome update workflow nodes (Phase 5, SEPARATE graph entry point —
src/graph/workflow.py::build_outcome_update_workflow). Outcomes usually
happen days or weeks after the initial application, so this deliberately
does not chain off the main application-tracking graph; it's invoked
later with its own thread_id and `target_application_id`.

load_application -> human_record_outcome -> record_application_event ->
calculate_outcome_analytics -> learning_agent -> persist_strategy_insight
-> sync_mem0 -> outcome_update_complete
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt

from src.agents.learning_agent import LearningAgent
from src.config.outcomes import is_resolved
from src.config.settings import load_settings
from src.config.workflow import OUTCOME_ALLOWED_ACTIONS, OUTCOME_EVENTS_REQUIRING_PRIOR_APPLICATION
from src.graph.helpers import make_error, trace_event
from src.graph.state import HireLoopState
from src.models.application import Application
from src.models.application_event import ApplicationEvent
from src.models.enums import ApplicationEventType, ApplicationStatus
from src.models.workflow_error import ErrorCategory
from src.models.workflow_status import WorkflowStatus
from src.services.demo_application_loader import load_demo_application_history
from src.services.outcome_analytics import compute_outcome_analytics


def load_application_node(state: HireLoopState, config: RunnableConfig) -> dict:
    tracker = config["configurable"]["application_tracker"]
    application_id = state["target_application_id"]
    application = tracker.get_application(application_id)

    if application is None:
        error = make_error(
            "load_application", ErrorCategory.INVALID_STATE, f"no application found with id {application_id!r}", retryable=False
        )
        return {"errors": [error], "workflow_status": WorkflowStatus.FAILED.value, "current_step": "load_application"}

    history = tracker.get_application_history(application_id)
    return {
        "candidate_id": application.candidate_id,
        "application_id": application.application_id,
        "current_application": application.model_dump(mode="json"),
        "application_history": [e.model_dump(mode="json") for e in history],
        "decision_trace": [
            trace_event("outcome_update", "load_application", f"Loaded application {application_id} ({len(history)} prior event(s)).")
        ],
        "current_step": "load_application",
        "workflow_status": WorkflowStatus.RUNNING.value,
    }


_EVENT_TYPE_TO_STATUS = {
    "RECRUITER_RESPONSE": ApplicationStatus.RECRUITER_RESPONSE,
    "INTERVIEW": ApplicationStatus.INTERVIEW,
    "FINAL_ROUND": ApplicationStatus.FINAL_ROUND,
    "REJECTED": ApplicationStatus.REJECTED,
    "OFFER": ApplicationStatus.OFFER,
    "WITHDRAWN": ApplicationStatus.WITHDRAWN,
}


def human_record_outcome_node(state: HireLoopState, config: RunnableConfig) -> dict:
    application = Application(**state["current_application"])
    history = [ApplicationEvent(**e) for e in state.get("application_history", [])]
    ever_applied = any(e.event_type == ApplicationEventType.APPLIED for e in history) or application.current_status != ApplicationStatus.READY_FOR_REVIEW

    events = []
    prompt = {
        "application": {
            "application_id": application.application_id,
            "job_id": application.job_id,
            "current_status": application.current_status.value,
        },
        "history_summary": [{"event_type": e.event_type.value, "occurred_at": e.occurred_at.isoformat()} for e in history],
        "allowed_actions": sorted(OUTCOME_ALLOWED_ACTIONS),
    }

    while True:
        human_input = interrupt(prompt) or {}
        action = human_input.get("action")

        if action not in OUTCOME_ALLOWED_ACTIONS:
            events.append(trace_event("outcome_update", "human_record_outcome", f"Rejected invalid outcome action {action!r}; awaiting a valid choice."))
            prompt = {**prompt, "error": f"invalid action {action!r}"}
            continue

        if action == "CANCEL":
            break

        # Suspicious/impossible sequence check (Part X): e.g. OFFER before
        # the application was ever marked APPLIED. Not blocked outright --
        # flagged, and requires explicit confirmation to proceed.
        if action in OUTCOME_EVENTS_REQUIRING_PRIOR_APPLICATION and not ever_applied and not human_input.get("confirm"):
            events.append(
                trace_event(
                    "outcome_update",
                    "human_record_outcome",
                    f"Warning: recording {action} but this application was never marked APPLIED; confirmation required.",
                )
            )
            prompt = {
                **prompt,
                "warning": f"'{action}' before APPLIED is an unusual sequence. Resubmit with confirm=true to proceed anyway.",
            }
            continue

        break

    if action == "CANCEL":
        events.append(trace_event("outcome_update", "human_record_outcome", "Human cancelled outcome recording."))
        return {
            "workflow_status": WorkflowStatus.CANCELLED.value,
            "errors": [make_error("human_record_outcome", ErrorCategory.HUMAN_CANCELLED, "human cancelled outcome recording")],
            "decision_trace": events,
            "current_step": "human_record_outcome",
        }

    # Never invent a timestamp: use the human-supplied occurred_at if given
    # (backdating an already-happened event is legitimate), otherwise now.
    occurred_at_raw = human_input.get("occurred_at")
    occurred_at = datetime.fromisoformat(occurred_at_raw) if occurred_at_raw else datetime.now(timezone.utc)

    events.append(trace_event("outcome_update", "human_record_outcome", f"Outcome {action} recorded."))
    return {
        "outcome_action": action,
        "outcome_occurred_at": occurred_at.isoformat(),
        "current_application": application.model_dump(mode="json"),
        "decision_trace": events,
        "current_step": "human_record_outcome",
    }


def record_application_event_node(state: HireLoopState, config: RunnableConfig) -> dict:
    tracker = config["configurable"]["application_tracker"]
    application = Application(**state["current_application"])
    action = state["outcome_action"]

    new_status = _EVENT_TYPE_TO_STATUS[action]
    application.current_status = new_status
    tracker.update_application_status(application)

    occurred_at_raw = state.get("outcome_occurred_at")
    occurred_at = datetime.fromisoformat(occurred_at_raw) if occurred_at_raw else datetime.now(timezone.utc)

    tracker.record_event(
        ApplicationEvent(
            event_id=f"ev-{uuid4().hex[:10]}",
            application_id=application.application_id,
            candidate_id=application.candidate_id,
            job_id=application.job_id,
            event_type=ApplicationEventType(action),
            occurred_at=occurred_at,
            source="human",
        )
    )

    return {
        "current_application": application.model_dump(mode="json"),
        "decision_trace": [trace_event("outcome_update", "record_application_event", f"Outcome {action} recorded for application {application.application_id}.")],
        "current_step": "record_application_event",
    }


def calculate_outcome_analytics_node(state: HireLoopState, config: RunnableConfig) -> dict:
    tracker = config["configurable"]["application_tracker"]
    settings = (config.get("configurable") or {}).get("settings") or load_settings()

    records = tracker.get_applications_with_history(include_demo_data=settings.demo_mode)
    if settings.demo_mode:
        # Demo history lives in a seed file, not the business DB -- merge
        # it in only under the explicit DEMO_MODE boundary, never silently.
        records = records + load_demo_application_history()

    analytics = compute_outcome_analytics(records)

    return {
        "outcome_analytics": analytics.model_dump(mode="json"),
        "decision_trace": [
            trace_event(
                "outcome_update",
                "calculate_outcome_analytics",
                f"Outcome analytics refreshed using {analytics.total_resolved} resolved application(s) "
                f"(of {analytics.total_applications} total).",
            )
        ],
        "current_step": "calculate_outcome_analytics",
    }


def learning_agent_node(state: HireLoopState, config: RunnableConfig) -> dict:
    from src.models.outcome_analytics import OutcomeAnalytics

    llm_client = config["configurable"]["llm_client"]
    analytics = OutcomeAnalytics(**state["outcome_analytics"])

    agent = LearningAgent(llm_client)
    insights = agent.generate_insights(analytics)

    return {
        "strategy_insights": [i.model_dump(mode="json") for i in insights],
        "decision_trace": [trace_event("learning_agent", "learning_agent", f"Learning Agent generated {len(insights)} strategy insight(s).")],
        "current_step": "learning_agent",
    }


def persist_strategy_insight_node(state: HireLoopState, config: RunnableConfig) -> dict:
    from src.models.learning_insight import LearningInsight

    tracker = config["configurable"]["application_tracker"]
    candidate_id = state.get("candidate_id")
    insights = [LearningInsight(**d) for d in state.get("strategy_insights", [])]

    for insight in insights:
        tracker.persist_strategy_insight(insight, candidate_id=candidate_id)

    return {
        "decision_trace": [
            trace_event("learning_agent", "persist_strategy_insight", f"{len(insights)} strategy insight(s) persisted.")
        ],
        "current_step": "persist_strategy_insight",
    }


def sync_mem0_node(state: HireLoopState, config: RunnableConfig) -> dict:
    from src.models.learning_insight import LearningInsight

    memory_service = (config.get("configurable") or {}).get("memory_service")
    candidate_id = state.get("candidate_id")
    insights = [LearningInsight(**d) for d in state.get("strategy_insights", [])]

    if memory_service is None or not insights:
        status = "NOT_CONFIGURED" if memory_service is None else "SYNCED"
        message = "mem0 not configured; strategy insights persisted locally only." if memory_service is None else "No new strategy insights to sync."
        return {
            "mem0_sync_status": status,
            "decision_trace": [trace_event("learning_agent", "sync_mem0", message)],
            "current_step": "sync_mem0",
        }

    synced_count = 0
    for insight in insights:
        synced, _ = memory_service.remember_strategy_insight(candidate_id, insight)
        if synced:
            synced_count += 1

    if synced_count == len(insights):
        status = "SYNCED"
        message = f"mem0 strategy memory updated ({synced_count} insight(s))."
    elif synced_count == 0:
        status = "DEGRADED"
        message = "mem0 unavailable; strategy insight(s) persisted locally only."
    else:
        status = "DEGRADED"
        message = f"mem0 partially unavailable; {synced_count}/{len(insights)} insight(s) synced, rest persisted locally only."

    return {
        "mem0_sync_status": status,
        "decision_trace": [trace_event("learning_agent", "sync_mem0", message)],
        "current_step": "sync_mem0",
    }


def outcome_update_complete_node(state: HireLoopState, config: RunnableConfig) -> dict:
    return {
        "workflow_status": WorkflowStatus.COMPLETED.value,
        "decision_trace": [trace_event("completion", "outcome_update_complete", "Outcome update workflow completed.")],
        "current_step": "outcome_update_complete",
    }
