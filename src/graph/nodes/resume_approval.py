"""
human_resume_approval: pauses to present every remaining VERIFIED
modification for explicit human approval, plus create_resume_version and
phase4_complete.

Absolute safety invariant: only modifications whose latest Truth Guard
status is VERIFIED are ever offered here. A human EDIT is treated as a new
claim and is re-verified through Truth Guard before it can be approved —
editing never bypasses verification.
"""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt

from src.agents.truth_guard import classify_modification
from src.config.workflow import RESUME_APPROVAL_ALLOWED_ACTIONS
from src.graph.helpers import make_error, trace_event
from src.graph.state import HireLoopState
from src.models.candidate import CandidateProfile
from src.models.evidence import Evidence
from src.models.resume_modification import ResumeModification
from src.models.resume_version import ResumeVersion, ResumeVersionStatus
from src.models.workflow_error import ErrorCategory
from src.models.workflow_status import WorkflowStatus


def _build_payload(offerable: list[ResumeModification], truth_guard_results: dict) -> list[dict]:
    payload = []
    for modification in offerable:
        result = truth_guard_results[modification.modification_id]
        payload.append(
            {
                "modification_id": modification.modification_id,
                "original": modification.original_text,
                "proposed": modification.proposed_text,
                "reason": modification.reason,
                "truth_status": result["status"],
                "evidence_ids": result.get("evidence_ids", []),
                "human_confirmed": any(eid.startswith("human-ev-") for eid in result.get("evidence_ids", [])),
            }
        )
    return payload


def human_resume_approval_node(state: HireLoopState, config: RunnableConfig) -> dict:
    modifications_by_id = {m["modification_id"]: ResumeModification(**m) for m in state.get("proposed_modifications", [])}
    truth_guard_results = dict(state.get("truth_guard_results", {}))

    offerable = [m for m in modifications_by_id.values() if truth_guard_results.get(m.modification_id, {}).get("status") == "VERIFIED"]
    valid_ids = {m.modification_id for m in offerable}

    events = [
        trace_event(
            "human_resume_approval",
            "human_resume_approval",
            f"Human resume approval requested for {len(offerable)} verified modification(s).",
        )
    ]
    prompt = {"modifications": _build_payload(offerable, truth_guard_results), "allowed_actions": sorted(RESUME_APPROVAL_ALLOWED_ACTIONS)}

    rejected = list(state.get("rejected_modifications", []))
    approved_ids: list[str] = []
    action = None

    while True:
        human_input = interrupt(prompt) or {}
        action = human_input.get("action")

        if action == "CANCEL":
            events.append(trace_event("human_resume_approval", "human_resume_approval", "Human cancelled at resume approval."))
            return {
                "workflow_status": WorkflowStatus.CANCELLED.value,
                "errors": [make_error("human_resume_approval", ErrorCategory.HUMAN_CANCELLED, "human cancelled at resume approval")],
                "decision_trace": events,
                "current_step": "human_resume_approval",
            }

        if action == "APPROVE_ALL":
            approved_ids = sorted(valid_ids)
            events.append(trace_event("human_resume_approval", "human_resume_approval", f"Human approved all {len(approved_ids)} modification(s)."))
            break

        if action == "REJECT_ALL":
            for modification in offerable:
                rejected.append(
                    {
                        "modification_id": modification.modification_id,
                        "reason": "human rejected (reject all)",
                        "claim": modification.proposed_text,
                    }
                )
            events.append(trace_event("human_resume_approval", "human_resume_approval", "Human rejected all modifications."))
            break

        if action == "APPROVE_SELECTED":
            selected = human_input.get("modification_ids", [])
            invalid = [mid for mid in selected if mid not in valid_ids]
            if invalid:
                events.append(
                    trace_event(
                        "human_resume_approval", "human_resume_approval", f"Rejected invalid modification id(s) {invalid}; awaiting a valid selection."
                    )
                )
                prompt = {**prompt, "error": f"invalid modification id(s): {invalid}"}
                continue
            approved_ids = list(selected)
            for modification in offerable:
                if modification.modification_id not in approved_ids:
                    rejected.append(
                        {
                            "modification_id": modification.modification_id,
                            "reason": "human did not select this modification",
                            "claim": modification.proposed_text,
                        }
                    )
            events.append(
                trace_event(
                    "human_resume_approval", "human_resume_approval", f"Human approved {len(approved_ids)} of {len(offerable)} remaining modifications."
                )
            )
            break

        if action == "EDIT":
            edits = human_input.get("edits", {})
            profile = CandidateProfile(**state["candidate_profile"])
            evidence_pool = [Evidence(**d) for d in state.get("candidate_evidence", [])]
            llm_client = (config.get("configurable") or {}).get("llm_client")

            for modification_id, new_text in edits.items():
                if modification_id not in modifications_by_id:
                    events.append(trace_event("human_resume_approval", "human_resume_approval", f"Ignored edit for unknown modification id {modification_id!r}."))
                    continue
                edited = modifications_by_id[modification_id].model_copy(update={"proposed_text": new_text, "claim": new_text})
                # A human edit is a NEW claim -- it is re-verified, never auto-approved.
                result = classify_modification(edited, profile, evidence_pool, llm_client=llm_client)
                modifications_by_id[modification_id] = edited.model_copy(update={"status": result.status})
                truth_guard_results[modification_id] = result.model_dump(mode="json")
                events.append(
                    trace_event(
                        "human_resume_approval", "human_resume_approval", f"Human edit for {modification_id} re-verified: {result.status.value}."
                    )
                )

            offerable = [m for m in modifications_by_id.values() if truth_guard_results.get(m.modification_id, {}).get("status") == "VERIFIED"]
            valid_ids = {m.modification_id for m in offerable}
            prompt = {"modifications": _build_payload(offerable, truth_guard_results), "allowed_actions": sorted(RESUME_APPROVAL_ALLOWED_ACTIONS)}
            continue

        events.append(trace_event("human_resume_approval", "human_resume_approval", f"Rejected invalid action {action!r}; awaiting a valid choice."))
        prompt = {**prompt, "error": f"invalid action {action!r}"}

    return {
        "proposed_modifications": [m.model_dump(mode="json") for m in modifications_by_id.values()],
        "truth_guard_results": truth_guard_results,
        "approved_modification_ids": approved_ids,
        "rejected_modifications": rejected,
        "resume_approval_status": "APPROVED" if approved_ids else "REJECTED",
        "human_resume_decision": action,
        "workflow_status": WorkflowStatus.RUNNING.value,
        "decision_trace": events,
        "current_step": "human_resume_approval",
    }


def create_resume_version_node(state: HireLoopState, config: RunnableConfig) -> dict:
    candidate_id = state["candidate_id"]
    approved_ids = state.get("approved_modification_ids", [])
    existing_versions = state.get("resume_versions", [])

    original_version_id = f"resume_v1_{candidate_id}"
    if not any(v["resume_version_id"] == original_version_id for v in existing_versions):
        original = ResumeVersion(
            resume_version_id=original_version_id,
            candidate_id=candidate_id,
            parent_version_id=None,
            selected_job_id=None,
            approved_modification_ids=[],
            status=ResumeVersionStatus.ORIGINAL,
        )
        existing_versions = [*existing_versions, original.model_dump(mode="json")]

    new_version_id = f"resume_v{len(existing_versions) + 1}_{candidate_id}"
    approved_version = ResumeVersion(
        resume_version_id=new_version_id,
        candidate_id=candidate_id,
        parent_version_id=original_version_id,
        selected_job_id=state.get("selected_job_id"),
        approved_modification_ids=approved_ids,
        status=ResumeVersionStatus.APPROVED,
    )
    versions = [*existing_versions, approved_version.model_dump(mode="json")]

    message = f"Resume version {new_version_id} approved with {len(approved_ids)} modification(s)."
    return {
        "resume_versions": versions,
        "current_resume_version_id": new_version_id,
        "decision_trace": [trace_event("resume_versioning", "create_resume_version", message)],
        "current_step": "create_resume_version",
    }


def phase4_complete_node(state: HireLoopState, config: RunnableConfig) -> dict:
    # Note: this no longer sets workflow_status=COMPLETED -- as of Phase 5
    # the graph continues into application tracking after resume approval.
    # phase5_application_complete_node (src/graph/nodes/application.py)
    # sets the final COMPLETED status.
    return {
        "workflow_status": WorkflowStatus.RUNNING.value,
        "decision_trace": [trace_event("completion", "phase4_complete", "Phase 4 resume tailoring completed.")],
        "current_step": "phase4_complete",
    }
