"""Nodes covering Resume Tailor proposals, Truth Guard classification, and automated correction."""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from src.agents.resume_tailor import ResumeTailorAgent
from src.agents.truth_guard import TruthGuardAgent
from src.config.workflow import MAX_RESUME_REVISION_LOOPS
from src.graph.helpers import make_error, trace_event
from src.graph.state import HireLoopState
from src.llm.errors import RETRYABLE_ERROR_TYPES, HireLoopLLMError
from src.models.candidate import CandidateProfile
from src.models.evidence import Evidence
from src.models.evidence_retrieval import RequirementEvidence
from src.models.job import JobPosting
from src.models.resume_modification import ResumeModification
from src.models.workflow_error import ErrorCategory
from src.models.workflow_status import WorkflowStatus

_TERMINAL_CORRECTABLE_STATUSES = ("PARTIALLY_SUPPORTED", "UNSUPPORTED")


def tailor_resume_node(state: HireLoopState, config: RunnableConfig) -> dict:
    llm_client = config["configurable"]["llm_client"]
    profile = CandidateProfile(**state["candidate_profile"])
    deduped_by_id = {d["job_id"]: d for d in state.get("deduped_jobs", [])}
    job = JobPosting(**deduped_by_id[state["selected_job_id"]])
    requirement_evidence = {
        req: RequirementEvidence(**data) for req, data in state.get("job_requirement_evidence", {}).items()
    }

    agent = ResumeTailorAgent(llm_client)
    try:
        modifications = agent.propose_modifications(profile, job, requirement_evidence)
    except HireLoopLLMError as exc:
        error = make_error(
            "tailor_resume",
            ErrorCategory.LLM_ERROR,
            f"resume tailoring failed: {exc.error_type.value}",
            retryable=exc.error_type in RETRYABLE_ERROR_TYPES,
            attempt=exc.attempts,
        )
        return {"errors": [error], "workflow_status": WorkflowStatus.FAILED.value, "current_step": "tailor_resume"}

    return {
        "proposed_modifications": [m.model_dump(mode="json") for m in modifications],
        "correction_pass_count": 0,
        "decision_trace": [
            trace_event("resume_tailor", "tailor_resume", f"Resume Tailor proposed {len(modifications)} modification(s).")
        ],
        "current_step": "tailor_resume",
    }


def truth_guard_node(state: HireLoopState, config: RunnableConfig) -> dict:
    llm_client = (config.get("configurable") or {}).get("llm_client")
    profile = CandidateProfile(**state["candidate_profile"])
    evidence_pool = [Evidence(**d) for d in state.get("candidate_evidence", [])]
    modifications = [ResumeModification(**d) for d in state.get("proposed_modifications", [])]

    agent = TruthGuardAgent(llm_client)
    results = agent.classify_modifications(modifications, profile, evidence_pool)
    results_by_id = {r.modification_id: r for r in results}

    updated_modifications = [m.model_copy(update={"status": results_by_id[m.modification_id].status}) for m in modifications]
    truth_guard_results = dict(state.get("truth_guard_results", {}))
    for r in results:
        truth_guard_results[r.modification_id] = r.model_dump(mode="json")

    counts = {"VERIFIED": 0, "PARTIALLY_SUPPORTED": 0, "UNSUPPORTED": 0, "NEEDS_HUMAN_CONFIRMATION": 0}
    for r in results:
        counts[r.status.value] += 1

    message = f"Truth Guard verified {counts['VERIFIED']} modification(s)."
    extra = []
    if counts["PARTIALLY_SUPPORTED"]:
        extra.append(f"{counts['PARTIALLY_SUPPORTED']} partially supported")
    if counts["UNSUPPORTED"]:
        extra.append(f"{counts['UNSUPPORTED']} unsupported")
    if counts["NEEDS_HUMAN_CONFIRMATION"]:
        extra.append(f"{counts['NEEDS_HUMAN_CONFIRMATION']} need human confirmation")
    if extra:
        message += " " + "; ".join(extra) + "."

    return {
        "proposed_modifications": [m.model_dump(mode="json") for m in updated_modifications],
        "truth_guard_results": truth_guard_results,
        "decision_trace": [trace_event("truth_guard", "truth_guard", message, metadata=counts)],
        "current_step": "truth_guard",
    }


def correct_modifications_node(state: HireLoopState, config: RunnableConfig) -> dict:
    modifications = [ResumeModification(**d) for d in state.get("proposed_modifications", [])]
    truth_guard_results = state.get("truth_guard_results", {})

    updated = []
    corrected_count = 0
    for modification in modifications:
        result = truth_guard_results.get(modification.modification_id)
        if result and result["status"] in _TERMINAL_CORRECTABLE_STATUSES:
            safe_rewrite = result.get("suggested_safe_rewrite")
            if safe_rewrite:
                updated.append(modification.model_copy(update={"proposed_text": safe_rewrite, "claim": safe_rewrite, "status": None}))
                corrected_count += 1
                continue
        updated.append(modification)

    correction_pass_count = state.get("correction_pass_count", 0) + 1
    message = (
        f"Truth Guard correction pass {correction_pass_count}/{MAX_RESUME_REVISION_LOOPS} completed: "
        f"{corrected_count} modification(s) rewritten using a deterministic safe fallback."
    )
    return {
        "proposed_modifications": [m.model_dump(mode="json") for m in updated],
        "correction_pass_count": correction_pass_count,
        "decision_trace": [trace_event("truth_guard_correction", "correct_modifications", message)],
        "current_step": "correct_modifications",
    }


def strip_unresolved_modifications_node(state: HireLoopState, config: RunnableConfig) -> dict:
    modifications = [ResumeModification(**d) for d in state.get("proposed_modifications", [])]
    truth_guard_results = state.get("truth_guard_results", {})

    kept = []
    rejected = list(state.get("rejected_modifications", []))
    for modification in modifications:
        result = truth_guard_results.get(modification.modification_id, {})
        status = result.get("status")
        if status in _TERMINAL_CORRECTABLE_STATUSES:
            rejected.append(
                {
                    "modification_id": modification.modification_id,
                    "reason": f"unresolved after {MAX_RESUME_REVISION_LOOPS} correction pass(es): {status}",
                    "claim": modification.proposed_text,
                }
            )
        else:
            kept.append(modification)

    removed_count = len(modifications) - len(kept)
    message = f"{removed_count} unresolved modification(s) removed after {MAX_RESUME_REVISION_LOOPS} correction pass(es)."
    return {
        "proposed_modifications": [m.model_dump(mode="json") for m in kept],
        "rejected_modifications": rejected,
        "decision_trace": [trace_event("truth_guard_correction", "strip_unresolved_modifications", message)],
        "current_step": "strip_unresolved_modifications",
    }
