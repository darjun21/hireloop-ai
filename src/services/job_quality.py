"""
Deterministic job quality scoring.

Quality is about whether a listing is well-formed and trustworthy — NOT
candidate fit (that's opportunity scoring) and NOT duplication (that's
deduplication.py). No LLM.

Salary is intentionally never penalized: many legitimate postings omit it.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from src.models.enums import ConfidenceLevel, JobQualityRecommendation, WorkMode
from src.models.job import JobPosting
from src.models.job_quality import JobQualityResult
from src.services.job_evidence_sufficiency import CompletenessLevel, assess_requirement_completeness
from src.services.normalization import normalize_whitespace

_MIN_DESCRIPTION_LENGTH = 40
_SHORT_DESCRIPTION_LENGTH = 120
_VAGUE_TITLES = {"job", "position", "opportunity", "various", "multiple", "n/a", "tbd"}
_BOILERPLATE_MIN_LENGTH = 200
_BOILERPLATE_UNIQUE_WORD_RATIO = 0.30

_PENALTIES: dict[str, float] = {
    "missing_company": 40,
    "missing_description": 30,
    "short_description": 15,
    "vague_title": 20,
    "suspicious_url": 15,
    "boilerplate_heavy": 15,
    "location_work_mode_conflict": 10,
    "missing_key_details": 10,
    "sparse_requirements": 10,
}

_CRITICAL_FLAGS = {"missing_company", "missing_description"}


def _is_vague_title(title: str) -> bool:
    collapsed = normalize_whitespace(title).lower().strip(".,!")
    return len(collapsed) < 4 or collapsed in _VAGUE_TITLES


def _is_suspicious_url(url: str) -> bool:
    parts = urlsplit(url.strip())
    return not parts.scheme or not parts.netloc


def _is_boilerplate_heavy(description: str) -> bool:
    collapsed = normalize_whitespace(description).lower()
    if len(collapsed) < _BOILERPLATE_MIN_LENGTH:
        return False
    words = collapsed.split(" ")
    if not words:
        return False
    unique_ratio = len(set(words)) / len(words)
    return unique_ratio < _BOILERPLATE_UNIQUE_WORD_RATIO


def _has_location_work_mode_conflict(job: JobPosting) -> bool:
    if not job.location or job.work_mode is None:
        return False
    location_lower = job.location.lower()
    if job.work_mode == WorkMode.REMOTE and "onsite" in location_lower:
        return True
    if job.work_mode == WorkMode.ONSITE and "remote" in location_lower:
        return True
    return False


def score_job_quality(job: JobPosting) -> JobQualityResult:
    flags: list[str] = []

    if not job.company or not job.company.strip():
        flags.append("missing_company")

    if not job.description or not job.description.strip():
        flags.append("missing_description")
    else:
        collapsed_desc = normalize_whitespace(job.description)
        if len(collapsed_desc) < _MIN_DESCRIPTION_LENGTH:
            flags.append("missing_description")
        elif len(collapsed_desc) < _SHORT_DESCRIPTION_LENGTH:
            flags.append("short_description")
        elif _is_boilerplate_heavy(job.description):
            flags.append("boilerplate_heavy")

    if _is_vague_title(job.title):
        flags.append("vague_title")

    if job.url and _is_suspicious_url(job.url):
        flags.append("suspicious_url")

    if _has_location_work_mode_conflict(job):
        flags.append("location_work_mode_conflict")

    if not job.required_skills and job.minimum_years_experience is None and job.employment_type is None:
        flags.append("missing_key_details")

    completeness = assess_requirement_completeness(job)
    if completeness.level == CompletenessLevel.LOW:
        flags.append("sparse_requirements")

    quality_score = 100.0
    for flag in flags:
        quality_score -= _PENALTIES.get(flag, 0)
    quality_score = max(0.0, min(100.0, quality_score))

    has_critical_flag = any(f in _CRITICAL_FLAGS for f in flags)
    if has_critical_flag or len(flags) >= 3:
        confidence = ConfidenceLevel.LOW
    elif flags:
        confidence = ConfidenceLevel.MEDIUM
    else:
        confidence = ConfidenceLevel.HIGH

    if has_critical_flag or quality_score < 40:
        recommendation = JobQualityRecommendation.LOW_QUALITY
    elif not flags:
        recommendation = JobQualityRecommendation.VALID
    else:
        recommendation = JobQualityRecommendation.NEEDS_REVIEW

    return JobQualityResult(
        quality_score=quality_score,
        flags=flags,
        confidence=confidence,
        recommendation=recommendation,
        requirement_completeness=completeness.level.value,
    )
