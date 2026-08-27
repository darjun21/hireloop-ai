"""
human_clarification: pauses for the human to resolve one
NEEDS_HUMAN_CONFIRMATION modification at a time.

If the human confirms with evidence, a NEW Evidence record is created with
source_type=HUMAN_CONFIRMATION — distinct from resume-derived evidence,
never silently merged into it (docs/TRUTH_GUARD.md's evidence hierarchy).
Truth Guard re-classifies afterward; confirming doesn't force VERIFIED by
itself, it gives Truth Guard something concrete to re-evaluate.
"""

from __future__ import annotations

from uuid import uuid4

from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt

from src.config.workflow import CLARIFICATION_ALLOWED_ACTIONS
from src.graph.helpers import make_error, trace_event
from src.graph.state import HireLoopState
from src.models.enums import EvidenceSourceType
from src.models.evidence import Evidence
from src.models.resume_modification import ResumeModification
from src.models.workflow_error import ErrorCategory
from src.models.workflow_status import WorkflowStatus


def human_clarification_node(state: HireLoopState, config: RunnableConfig) -> dict:
    modifications = [ResumeModification(**d) for d in state.get("proposed_modifications", [])]
    truth_guard_results = state.get("truth_guard_results", {})

    pending = [m for m in modifications if truth_guard_results.get(m.modification_id, {}).get("status") == "NEEDS_HUMAN_CONFIRMATION"]
    if not pending:
        return {"current_step": "human_clarification"}

    target = pending[0]
    result = truth_guard_results[target.modification_id]

    events = [
        trace_event(
            "human_clarification",
            "human_clarification",
            f"Human clarification requested for modification {target.modification_id}.",
        )
    ]
    prompt = {
        "clarification_required": {
            "modification_id": target.modification_id,
            "proposed_claim": target.claim or target.proposed_text,
            "status": result["status"],
            "explanation": result["explanation"],
            "closest_evidence_ids": result.get("evidence_ids", []),
            "safe_option": result.get("suggested_safe_rewrite"),
        },
        "allowed_actions": sorted(CLARIFICATION_ALLOWED_ACTIONS),
    }

    while True:
        human_input = interrupt(prompt) or {}
        action = human_input.get("action")
        if action in CLARIFICATION_ALLOWED_ACTIONS:
            break
        events.append(
            trace_event(
                "human_clarification", "human_clarification", f"Rejected invalid clarification action {action!r}; awaiting a valid choice."
            )
        )
        prompt = {**prompt, "error": f"invalid action {action!r}"}

    if action == "CANCEL":
        events.append(trace_event("human_clarification", "human_clarification", "Human cancelled during clarification."))
        return {
            "workflow_status": WorkflowStatus.CANCELLED.value,
            "errors": [make_error("human_clarification", ErrorCategory.HUMAN_CANCELLED, "human cancelled during clarification")],
            "decision_trace": events,
            "current_step": "human_clarification",
        }

    updated_modifications = list(modifications)
    index = next(i for i, m in enumerate(updated_modifications) if m.modification_id == target.modification_id)
    truth_guard_results = dict(truth_guard_results)

    if action == "REJECT_CLAIM":
        updated_modifications.pop(index)
        truth_guard_results.pop(target.modification_id, None)
        rejected = state.get("rejected_modifications", []) + [
            {
                "modification_id": target.modification_id,
                "reason": "human rejected during clarification",
                "claim": target.proposed_text,
            }
        ]
        events.append(trace_event("human_clarification", "human_clarification", f"Human rejected modification {target.modification_id}."))
        return {
            "proposed_modifications": [m.model_dump(mode="json") for m in updated_modifications],
            "truth_guard_results": truth_guard_results,
            "rejected_modifications": rejected,
            "decision_trace": events,
            "current_step": "human_clarification",
        }

    if action == "USE_SAFE_REWRITE":
        safe_text = result.get("suggested_safe_rewrite")
        if safe_text:
            updated_modifications[index] = target.model_copy(update={"proposed_text": safe_text, "claim": safe_text, "status": None})
        truth_guard_results.pop(target.modification_id, None)  # force re-classification
        events.append(
            trace_event("human_clarification", "human_clarification", f"Human selected the safe rewrite for modification {target.modification_id}.")
        )
        return {
            "proposed_modifications": [m.model_dump(mode="json") for m in updated_modifications],
            "truth_guard_results": truth_guard_results,
            "decision_trace": events,
            "current_step": "human_clarification",
        }

    # CONFIRM_WITH_EVIDENCE
    detail = human_input.get("confirmation_detail") or "Human confirmed this claim is accurate."
    new_evidence = Evidence(
        evidence_id=f"human-ev-{uuid4().hex[:8]}",
        candidate_id=state["candidate_id"],
        source_type=EvidenceSourceType.HUMAN_CONFIRMATION,
        source_section=f"Human Confirmation: {target.modification_id}",
        source_text=detail,
        confidence=0.8,
    )
    updated_modifications[index] = target.model_copy(
        update={"supporting_evidence_ids": [*target.supporting_evidence_ids, new_evidence.evidence_id]}
    )
    truth_guard_results.pop(target.modification_id, None)  # force re-classification with the new evidence
    events.append(
        trace_event(
            "human_clarification",
            "human_clarification",
            f"Human confirmed modification {target.modification_id} with new evidence {new_evidence.evidence_id}.",
        )
    )
    return {
        "proposed_modifications": [m.model_dump(mode="json") for m in updated_modifications],
        "truth_guard_results": truth_guard_results,
        "human_provided_evidence": state.get("human_provided_evidence", []) + [new_evidence.model_dump(mode="json")],
        "candidate_evidence": state.get("candidate_evidence", []) + [new_evidence.model_dump(mode="json")],
        "decision_trace": events,
        "current_step": "human_clarification",
    }
