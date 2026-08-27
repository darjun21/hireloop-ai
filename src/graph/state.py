"""
Shared LangGraph state for the HireLoop Phase 3 workflow.

Design decision (see docs/WORKFLOW.md): every domain-model-shaped field
here is a plain JSON dict (`model.model_dump(mode="json")`), not a live
Pydantic instance. LangGraph's checkpoint serializer *can* round-trip raw
Pydantic instances via a pickle-style fallback, but as of langgraph
1.2.x that path already emits a "deserializing unregistered type" removal
warning. Storing plain dicts instead keeps the checkpoint payload truly
JSON-safe and portable across any checkpointer backend, and matches "no
non-serializable runtime objects in state." Nodes reconstruct the typed
model from the dict when they need to operate on it, and dump it back
before returning a state update.

`decision_trace` and `errors` use an additive reducer (operator.add) so
each node only needs to return the *new* events/errors it produced, not
the full accumulated list.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class HireLoopState(TypedDict, total=False):
    # --- run/session identifiers ---
    run_id: str
    candidate_id: str

    # --- inputs (supplied at invocation, not produced by a node) ---
    resume_file_path: str  # local path to the resume file parse_resume reads

    # --- candidate ---
    resume_parse_result: dict[str, Any]  # ResumeParseResult
    candidate_profile: dict[str, Any]  # CandidateProfile
    profile_validation: dict[str, Any]  # ProfileValidationResult

    # --- search/preferences ---
    preferences: dict[str, Any]  # {target_roles, target_locations, preferred_work_modes, employment_preferences}

    # --- jobs ---
    raw_jobs: list[dict[str, Any]]  # JobPosting dicts, as ingested
    normalized_jobs: list[dict[str, Any]]  # JobPosting dicts + normalized_* metadata
    deduped_jobs: list[dict[str, Any]]  # JobPosting dicts, duplicates removed
    duplicate_results: list[dict[str, Any]]  # removed-job dedup log entries
    job_quality_results: dict[str, dict[str, Any]]  # job_id -> JobQualityResult

    # --- opportunity intelligence ---
    historical_signal_context: dict[str, dict[str, Any]]  # role_family -> StrategyInsight
    opportunity_scores: dict[str, dict[str, Any]]  # job_id -> OpportunityScore
    match_analyses: dict[str, dict[str, Any]]  # job_id -> MatchAnalysis (only for analyzed top-N)
    ranked_job_ids: list[str]  # eligible job_ids, best first

    # --- human interaction ---
    selected_job_id: str | None
    human_job_selection_status: str  # "PENDING" | "SELECTED" | "CANCELLED"

    # --- Phase 4: candidate evidence + job requirement evidence ---
    candidate_evidence: list[dict[str, Any]]  # flattened Evidence chunks (src/services/evidence_extraction.py)
    evidence_index_status: str  # "PINECONE" | "NONE" (see src/services/evidence_retrieval.py)
    job_requirement_evidence: dict[str, dict[str, Any]]  # requirement -> RequirementEvidence

    # --- Phase 4: resume tailoring / truth guard / approval ---
    proposed_modifications: list[dict[str, Any]]  # ResumeModification dicts, status updated in place
    truth_guard_results: dict[str, dict[str, Any]]  # modification_id -> TruthGuardResult
    correction_pass_count: int
    human_provided_evidence: list[dict[str, Any]]  # Evidence dicts, source_type=HUMAN_CONFIRMATION
    pending_clarification_modification_id: str | None
    human_resume_decision: str | None  # the human's action at the resume-approval interrupt
    resume_approval_status: str  # "PENDING" | "APPROVED" | "REJECTED" | "CANCELLED"
    approved_modification_ids: list[str]
    rejected_modifications: list[dict[str, Any]]  # {modification_id, reason}
    resume_versions: list[dict[str, Any]]  # ResumeVersion dicts
    current_resume_version_id: str | None

    # --- Phase 5: application tracking (main graph, after resume approval) ---
    application_id: str | None
    current_application: dict[str, Any] | None  # Application
    application_action: str | None  # human's choice at human_application_action

    # --- Phase 5: outcome update workflow (separate graph entry point) ---
    target_application_id: str  # input: which application this run updates
    application_history: list[dict[str, Any]]  # ApplicationEvent dicts for target_application_id
    outcome_action: str | None  # human's chosen outcome event type
    outcome_occurred_at: str | None  # ISO timestamp, human-supplied or recorded-at-submission-time; never invented
    outcome_analytics: dict[str, Any] | None  # OutcomeAnalytics
    strategy_insights: list[dict[str, Any]]  # LearningInsight dicts produced this run
    mem0_sync_status: str | None  # "SYNCED" | "DEGRADED" | "NOT_CONFIGURED"

    # --- eligibility bookkeeping ---
    eligible_job_ids: list[str]  # current eligible-for-ranking set, refined at each filtering stage
    excluded_jobs: list[dict[str, Any]]  # {job_id, reason, ...} for every job dropped anywhere in the pipeline
    no_suitable_jobs_reason: dict[str, Any] | None
    counts: dict[str, int]  # ingested/duplicates_removed/low_quality_excluded/scored/scoring_failures/...

    # --- operational ---
    current_step: str
    decision_trace: Annotated[list[dict[str, Any]], operator.add]
    errors: Annotated[list[dict[str, Any]], operator.add]
    retry_counts: dict[str, int]
    workflow_status: str  # WorkflowStatus value
