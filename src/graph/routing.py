"""
Conditional edge / routing functions for the HireLoop LangGraph workflow.

Each function inspects HireLoopState only (no side effects) and returns a
short label consumed by add_conditional_edges' path_map in
src/graph/workflow.py. Kept as small, explicit functions rather than
branching logic buried inside node bodies.
"""

from __future__ import annotations

from src.config.workflow import MAX_RESUME_REVISION_LOOPS
from src.config.workflow import MAX_TRUTH_GUARD_LOOPS as MAX_TRUTH_GUARD_LOOPS  # re-exported for Phase 3 call sites
from src.graph.state import HireLoopState
from src.models.workflow_status import WorkflowStatus

_CORRECTABLE_STATUSES = ("PARTIALLY_SUPPORTED", "UNSUPPORTED")


def _is_failed(state: HireLoopState) -> bool:
    return state.get("workflow_status") == WorkflowStatus.FAILED.value


def route_after_parse_resume(state: HireLoopState) -> str:
    return "failed" if _is_failed(state) else "build_candidate_profile"


def route_after_build_profile(state: HireLoopState) -> str:
    return "failed" if _is_failed(state) else "validate_candidate_profile"


def route_after_profile_validation(state: HireLoopState) -> str:
    return "failed" if _is_failed(state) else "collect_preferences"


def route_after_ingest_jobs(state: HireLoopState) -> str:
    return "failed" if _is_failed(state) else "normalize_jobs"


def route_after_job_quality(state: HireLoopState) -> str:
    if not state.get("eligible_job_ids"):
        return "no_suitable_jobs"
    return "calculate_historical_signal"


def route_after_scoring(state: HireLoopState) -> str:
    if _is_failed(state):
        return "failed"
    if not state.get("opportunity_scores"):
        return "no_suitable_jobs"
    return "analyze_matches"


def route_after_human_selection(state: HireLoopState) -> str:
    if state.get("human_job_selection_status") == "CANCELLED":
        return "cancelled"
    return "selection_confirmed"


# ---------------------------------------------------------------------------
# Phase 4: resume tailoring / truth guard / approval routing
# ---------------------------------------------------------------------------


def route_after_truth_guard(state: HireLoopState) -> str:
    statuses = [m.get("status") for m in state.get("proposed_modifications", [])]
    correctable = any(s in _CORRECTABLE_STATUSES for s in statuses)
    needs_human = any(s == "NEEDS_HUMAN_CONFIRMATION" for s in statuses)
    correction_pass_count = state.get("correction_pass_count", 0)

    # Prefer automated correction while budget remains -- it doesn't need
    # to interrupt the human. Only ask for clarification once nothing more
    # can be auto-corrected, and only strip once even clarification is done.
    if correctable and correction_pass_count < MAX_RESUME_REVISION_LOOPS:
        return "correction_required"
    if needs_human:
        return "human_confirmation"
    if correctable:
        return "max_loops"
    return "verified"


def route_after_human_clarification(state: HireLoopState) -> str:
    if state.get("workflow_status") == WorkflowStatus.CANCELLED.value:
        return "cancelled"
    return "continue"


def route_after_human_resume_approval(state: HireLoopState) -> str:
    if state.get("workflow_status") == WorkflowStatus.CANCELLED.value:
        return "cancelled"
    return "continue"


# ---------------------------------------------------------------------------
# Phase 5: application tracking / outcome update routing
# ---------------------------------------------------------------------------


def route_after_human_application_action(state: HireLoopState) -> str:
    if state.get("workflow_status") == WorkflowStatus.CANCELLED.value:
        return "cancelled"
    return "continue"


def route_after_load_application(state: HireLoopState) -> str:
    return "failed" if _is_failed(state) else "continue"


def route_after_human_record_outcome(state: HireLoopState) -> str:
    if state.get("workflow_status") == WorkflowStatus.CANCELLED.value:
        return "cancelled"
    return "continue"
