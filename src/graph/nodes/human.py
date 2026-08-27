"""
Human job selection: the centerpiece human-in-the-loop node of Phase 3.

Uses LangGraph's interrupt()/Command(resume=...) mechanism. A single call
to interrupt() pauses the graph and checkpoints state; resuming with an
invalid selection calls interrupt() again *within the same node
execution* to re-prompt without ever leaving the WAITING_FOR_HUMAN state
or advancing past this node — LangGraph replays each already-answered
interrupt call from its cache and only pauses again at the first
unanswered one, so this loop is safe to invoke multiple times across
resumes without repeating side effects.
"""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt

from src.config.workflow import RECOMMENDATION_SET_SIZE
from src.graph.helpers import make_error, trace_event
from src.graph.state import HireLoopState
from src.models.workflow_error import ErrorCategory
from src.models.workflow_status import WorkflowStatus


def _build_selection_payload(state: HireLoopState) -> list[dict]:
    ranked_ids = state.get("ranked_job_ids", [])[:RECOMMENDATION_SET_SIZE]
    scores = state.get("opportunity_scores", {})
    deduped_by_id = {d["job_id"]: d for d in state.get("deduped_jobs", [])}
    analyses = state.get("match_analyses", {})

    payload = []
    for job_id in ranked_ids:
        job = deduped_by_id[job_id]
        score = scores[job_id]
        analysis = analyses.get(job_id)
        payload.append(
            {
                "job_id": job_id,
                "title": job["title"],
                "company": job["company"],
                "location": job.get("location"),
                "final_score": score["final_score"],
                "recommendation": score["recommendation"],
                "confidence": score["confidence"],
                "strengths": analysis["strengths"] if analysis else None,
                "gaps": analysis["gaps"] if analysis else None,
            }
        )
    return payload


def human_select_job_node(state: HireLoopState, config: RunnableConfig) -> dict:
    payload = _build_selection_payload(state)
    valid_ids = {item["job_id"] for item in payload}

    events = [
        trace_event(
            "human_review",
            "human_select_job",
            "Human review required: select one opportunity or cancel.",
            metadata={"options": len(payload)},
        )
    ]

    prompt: dict = {"eligible_selections": payload, "action_required": "SELECT_JOB_OR_CANCEL"}

    while True:
        human_input = interrupt(prompt) or {}
        action = human_input.get("action")

        if action == "CANCEL":
            events.append(trace_event("human_review", "human_select_job", "Human cancelled the workflow."))
            return {
                "human_job_selection_status": "CANCELLED",
                "workflow_status": WorkflowStatus.CANCELLED.value,
                "errors": [make_error("human_select_job", ErrorCategory.HUMAN_CANCELLED, "human cancelled the workflow")],
                "decision_trace": events,
                "current_step": "human_select_job",
            }

        if action == "SELECT" and human_input.get("job_id") in valid_ids:
            selected_id = human_input["job_id"]
            break

        rejected_id = human_input.get("job_id")
        events.append(
            trace_event(
                "human_review",
                "human_select_job",
                f"Rejected invalid selection (action={action!r}, job_id={rejected_id!r}); awaiting a valid choice.",
            )
        )
        prompt = {
            "eligible_selections": payload,
            "action_required": "SELECT_JOB_OR_CANCEL",
            "error": f"'{rejected_id}' is not a valid selection from the eligible set",
        }

    selected_job = next(item for item in payload if item["job_id"] == selected_id)
    events.append(
        trace_event(
            "human_review",
            "human_select_job",
            f"Human selected job {selected_id}: {selected_job['title']} at {selected_job['company']}.",
        )
    )
    return {
        "selected_job_id": selected_id,
        "human_job_selection_status": "SELECTED",
        "workflow_status": WorkflowStatus.RUNNING.value,
        "decision_trace": events,
        "current_step": "human_select_job",
    }


def selection_confirmed_node(state: HireLoopState, config: RunnableConfig) -> dict:
    # Note: this no longer sets workflow_status=COMPLETED -- as of Phase 4
    # the graph continues into resume tailoring after job selection.
    # phase4_complete_node (src/graph/nodes/resume_approval.py) sets the
    # final COMPLETED status.
    selected_id = state.get("selected_job_id")
    return {
        "workflow_status": WorkflowStatus.RUNNING.value,
        "decision_trace": [
            trace_event("completion", "selection_confirmed", f"Job selection confirmed: {selected_id}.")
        ],
        "current_step": "selection_confirmed",
    }
