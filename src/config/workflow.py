"""
Versioned workflow-level thresholds. Single source of truth for the
LangGraph orchestration layer — do not hardcode these values in node code.
"""

from __future__ import annotations

# A job whose JobQualityResult.recommendation is LOW_QUALITY is excluded
# from ranking/recommendation entirely (see src/services/job_quality.py:
# LOW_QUALITY already means quality_score < 40 or a critical flag such as
# missing_company/missing_description). NEEDS_REVIEW jobs remain eligible
# but their reduced quality_score already drags down their weighted
# opportunity score via the job_quality component — no separate penalty
# is applied here.
JOB_QUALITY_EXCLUDED_RECOMMENDATIONS = frozenset({"LOW_QUALITY"})

# How many of the top deterministically-ranked opportunities get a Match
# Analyst (LLM) call. Keeps latency/cost bounded regardless of batch size.
MATCH_ANALYST_TOP_N = 5

# Size of the recommendation set shown to the human for selection.
RECOMMENDATION_SET_SIZE = 5

# Default location of the seeded demo job batch ingested by the ingest_jobs
# node when no other source is configured.
DEFAULT_JOB_BATCH_PATH = "data/sample_jobs.json"

# Default location of the LangGraph checkpoint database. This is workflow
# execution state (interrupt/resume, node history) — a categorically
# different responsibility from src/services/database.py's business data
# (candidates, jobs, applications, outcomes). Never merge the two.
DEFAULT_CHECKPOINT_DB_PATH = "data/workflow_checkpoints.db"

# ---------------------------------------------------------------------------
# Phase 4: Resume Tailor / Truth Guard / evidence retrieval
# ---------------------------------------------------------------------------

# Bound on automated Truth Guard correction passes (propose -> classify ->
# correct -> reclassify). After this many passes, any modification still
# not VERIFIED is stripped from the proposed set rather than looped on
# indefinitely. Both names refer to the same bound -- MAX_TRUTH_GUARD_LOOPS
# is also re-exported from src/graph/routing.py for call sites that
# imported it from there in Phase 3.
MAX_TRUTH_GUARD_LOOPS = 2
MAX_RESUME_REVISION_LOOPS = 2

# How many evidence matches to retrieve per job requirement (Pinecone or
# local fallback).
EVIDENCE_RETRIEVAL_TOP_K = 3

# Local-fallback lexical retrieval score bands (token-overlap ratio) used
# to classify EvidenceStrength. Centralized here rather than inlined in
# src/services/evidence_retrieval.py so they're easy to tune in one place.
EVIDENCE_STRONG_SCORE_THRESHOLD = 0.6
EVIDENCE_MODERATE_SCORE_THRESHOLD = 0.3

# Allowed human actions at each Phase 4 interrupt. Centralized so node code
# validates against one source of truth instead of repeating string
# literals.
CLARIFICATION_ALLOWED_ACTIONS = frozenset(
    {"CONFIRM_WITH_EVIDENCE", "REJECT_CLAIM", "USE_SAFE_REWRITE", "CANCEL"}
)
RESUME_APPROVAL_ALLOWED_ACTIONS = frozenset(
    {"APPROVE_ALL", "APPROVE_SELECTED", "EDIT", "REJECT_ALL", "CANCEL"}
)

# ---------------------------------------------------------------------------
# Phase 5: application tracking / outcome recording
# ---------------------------------------------------------------------------

DEFAULT_BUSINESS_DB_PATH = "data/hireloop.db"

APPLICATION_ACTION_ALLOWED_ACTIONS = frozenset({"MARK_APPLIED", "SAVE_FOR_LATER", "CANCEL"})

OUTCOME_ALLOWED_ACTIONS = frozenset(
    {"RECRUITER_RESPONSE", "INTERVIEW", "FINAL_ROUND", "REJECTED", "OFFER", "WITHDRAWN", "CANCEL"}
)

# Outcome event types that would be a suspicious/impossible sequence if
# recorded before the application has ever been marked APPLIED (or
# further along) -- see src/graph/nodes/outcome.py. Not blocked outright,
# just flagged, requiring an explicit `confirm: true` to proceed.
OUTCOME_EVENTS_REQUIRING_PRIOR_APPLICATION = frozenset({"INTERVIEW", "FINAL_ROUND", "OFFER"})
