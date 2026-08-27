"""
Deterministic "requirement completeness" / job evidence sufficiency
assessment.

This does NOT change the Opportunity Scoring Engine's weights or formula
(see docs/DECISIONS.md #1) — a job with a single stated requirement that
the candidate satisfies can still score well numerically. What this module
adds is a signal for how much the job posting actually specified, so a
perfect match against a near-empty requirement list doesn't read as
equally trustworthy as a match against a fully-specified one. It feeds
JobQualityResult (a modest quality flag) and, through the existing
quality -> confidence pipeline, OpportunityScore.confidence — never the
numeric score itself.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from src.models.job import JobPosting
from src.services.normalization import normalize_whitespace

_DESCRIPTION_DETAILED_LENGTH = 300
_DESCRIPTION_MINIMAL_LENGTH = 120

_LOW_MAX = 45
_MEDIUM_MAX = 75


class CompletenessLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class RequirementCompletenessResult(BaseModel):
    completeness_score: float = Field(..., ge=0, le=100)
    level: CompletenessLevel
    signals: dict[str, bool] = Field(default_factory=dict)


def assess_requirement_completeness(job: JobPosting) -> RequirementCompletenessResult:
    signals: dict[str, bool] = {}
    score = 0.0

    required_count = len(job.required_skills)
    signals["has_required_skills"] = required_count > 0
    signals["has_multiple_required_skills"] = required_count >= 2
    if required_count >= 2:
        score += 30
    elif required_count == 1:
        score += 12

    signals["has_preferred_skills"] = len(job.preferred_skills) > 0
    if job.preferred_skills:
        score += 10

    signals["has_experience_requirement"] = job.minimum_years_experience is not None
    if job.minimum_years_experience is not None:
        score += 20

    description = normalize_whitespace(job.description or "")
    signals["description_detailed"] = len(description) >= _DESCRIPTION_DETAILED_LENGTH
    signals["description_present"] = len(description) >= _DESCRIPTION_MINIMAL_LENGTH
    if len(description) >= _DESCRIPTION_DETAILED_LENGTH:
        score += 30
    elif len(description) >= _DESCRIPTION_MINIMAL_LENGTH:
        score += 15

    signals["location_or_work_mode_clear"] = bool(job.work_mode or job.location)
    if job.work_mode or job.location:
        score += 10

    score = min(100.0, score)

    if score < _LOW_MAX:
        level = CompletenessLevel.LOW
    elif score < _MEDIUM_MAX:
        level = CompletenessLevel.MEDIUM
    else:
        level = CompletenessLevel.HIGH

    return RequirementCompletenessResult(completeness_score=score, level=level, signals=signals)
