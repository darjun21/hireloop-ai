"""
Shared enums for domain models. Centralized here so status/label values are
defined exactly once and imported everywhere else.
"""

from __future__ import annotations

from enum import Enum


class WorkMode(str, Enum):
    REMOTE = "REMOTE"
    HYBRID = "HYBRID"
    ONSITE = "ONSITE"
    FLEXIBLE = "FLEXIBLE"


class EmploymentType(str, Enum):
    FULL_TIME = "FULL_TIME"
    PART_TIME = "PART_TIME"
    CONTRACT = "CONTRACT"
    INTERNSHIP = "INTERNSHIP"
    TEMPORARY = "TEMPORARY"


class EvidenceSourceType(str, Enum):
    RESUME = "RESUME"
    WORK_EXPERIENCE = "WORK_EXPERIENCE"
    PROJECT = "PROJECT"
    EDUCATION = "EDUCATION"
    CERTIFICATION = "CERTIFICATION"
    # A human explicitly attesting to a claim during the clarification
    # interrupt (Phase 4). Deliberately distinct from resume-derived
    # evidence — see docs/TRUTH_GUARD.md's evidence hierarchy.
    HUMAN_CONFIRMATION = "HUMAN_CONFIRMATION"
    MANUAL = "MANUAL"
    LINKEDIN = "LINKEDIN"
    PROJECT_REPO = "PROJECT_REPO"
    OTHER = "OTHER"


class ApplicationStatus(str, Enum):
    """Current lifecycle status of an Application (a cached/derived summary
    of its append-only ApplicationEvent history — see
    src/models/application_event.py). Also used to classify individual
    event types for response-rate purposes."""

    SAVED = "SAVED"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    APPROVED = "APPROVED"
    APPLIED = "APPLIED"
    REJECTED = "REJECTED"
    RECRUITER_RESPONSE = "RECRUITER_RESPONSE"
    INTERVIEW = "INTERVIEW"
    FINAL_ROUND = "FINAL_ROUND"
    OFFER = "OFFER"
    WITHDRAWN = "WITHDRAWN"
    CLOSED = "CLOSED"

# Outcome -> response-rate classification (positive/negative/unresolved)
# lives in src/config/outcomes.py, not here — see docs/DECISIONS.md #7.


class ApplicationEventType(str, Enum):
    """One entry in an application's append-only history. Deliberately a
    separate enum from ApplicationStatus even though the values overlap --
    an event is something that *happened at a point in time*; a status is
    the application's *current* derived state."""

    APPLICATION_CREATED = "APPLICATION_CREATED"
    SAVED = "SAVED"
    APPLIED = "APPLIED"
    RECRUITER_RESPONSE = "RECRUITER_RESPONSE"
    INTERVIEW = "INTERVIEW"
    FINAL_ROUND = "FINAL_ROUND"
    OFFER = "OFFER"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"
    CLOSED = "CLOSED"


class InsightCategory(str, Enum):
    ROLE_FAMILY = "ROLE_FAMILY"
    RESUME_VERSION = "RESUME_VERSION"
    WORK_MODE = "WORK_MODE"
    SKILL_CLUSTER = "SKILL_CLUSTER"
    SEARCH_STRATEGY = "SEARCH_STRATEGY"


class ActionabilityLevel(str, Enum):
    """How large an observed effect is, independent of how confident we
    are in the sample (SampleConfidence). A tiny difference is
    NO_CLEAR_SIGNAL even at HIGH sample confidence; a huge difference on a
    tiny sample is capped well below STRONG_SIGNAL. See
    src/services/actionability.py."""

    NO_CLEAR_SIGNAL = "NO_CLEAR_SIGNAL"
    WEAK_SIGNAL = "WEAK_SIGNAL"
    MODERATE_SIGNAL = "MODERATE_SIGNAL"
    STRONG_SIGNAL = "STRONG_SIGNAL"


class SampleConfidence(str, Enum):
    """Qualitative confidence banding driven purely by sample size — see
    src/config/analytics.py for the thresholds. Distinct from
    ConfidenceLevel (which reflects data completeness, not sample size)."""

    INSUFFICIENT = "INSUFFICIENT"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class TruthGuardStatus(str, Enum):
    VERIFIED = "VERIFIED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    NEEDS_HUMAN_CONFIRMATION = "NEEDS_HUMAN_CONFIRMATION"


class RecommendationBand(str, Enum):
    HIGH_PRIORITY = "HIGH_PRIORITY"
    STRONG_MATCH = "STRONG_MATCH"
    CONSIDER = "CONSIDER"
    LOW_PRIORITY = "LOW_PRIORITY"


class ConfidenceLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class JobQualityRecommendation(str, Enum):
    VALID = "VALID"
    LOW_QUALITY = "LOW_QUALITY"
    NEEDS_REVIEW = "NEEDS_REVIEW"
