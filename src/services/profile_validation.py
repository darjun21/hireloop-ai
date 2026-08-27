"""
Deterministic post-extraction validation for a CandidateProfile.

Never trust structured LLM output at face value, even when it validated
against the Pydantic schema — a schema only proves shape, not truth. This
runs a second, deterministic pass looking for internally inconsistent or
suspicious facts. Ambiguous findings are surfaced as warnings, not silently
"corrected" — see docs/ARCHITECTURE.md's Truth Guard boundary for why this
project treats unverified correction as a categorically different action
from flagging.
"""

from __future__ import annotations

from src.models.candidate import CandidateProfile
from src.models.profile_validation import ProfileValidationResult
from src.services.experience_estimation import estimate_years_experience, parse_resume_date

_LOW_CONFIDENCE_THRESHOLD = 0.5
_YEARS_EXCEEDS_TIMELINE_TOLERANCE = 5.0


def validate_profile(
    profile: CandidateProfile,
    conversion_warnings: list[str] | None = None,
) -> ProfileValidationResult:
    errors: list[str] = []
    warnings: list[str] = list(conversion_warnings or [])
    corrected_fields: dict[str, str] = {}

    _check_skills(profile, warnings)
    _check_evidence(profile, errors, warnings)
    _check_work_experience(profile, errors, warnings)
    _check_certifications(profile, errors, warnings)
    _check_years_experience_against_timeline(profile, warnings)

    return ProfileValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings, corrected_fields=corrected_fields)


def _check_skills(profile: CandidateProfile, warnings: list[str]) -> None:
    seen: set[str] = set()
    for skill in profile.skills:
        key = skill.name.strip().lower()
        if key in seen:
            warnings.append(f"duplicate_skill: {skill.name}")
        seen.add(key)
        if not skill.evidence:
            warnings.append(f"unsupported_skill_no_evidence: {skill.name}")


def _check_evidence(profile: CandidateProfile, errors: list[str], warnings: list[str]) -> None:
    seen_ids: set[str] = set()
    all_evidence = list(profile.source_evidence)
    for skill in profile.skills:
        all_evidence.extend(skill.evidence)
    for exp in profile.work_experience:
        all_evidence.extend(exp.evidence)
    for edu in profile.education:
        all_evidence.extend(edu.evidence)
    for proj in profile.projects:
        all_evidence.extend(proj.evidence)
    for cert in profile.certifications:
        all_evidence.extend(cert.evidence)

    for evidence in all_evidence:
        if evidence.evidence_id in seen_ids:
            errors.append(f"duplicate_evidence_id: {evidence.evidence_id}")
        seen_ids.add(evidence.evidence_id)
        if evidence.confidence < _LOW_CONFIDENCE_THRESHOLD:
            warnings.append(f"low_confidence_evidence: {evidence.evidence_id} (confidence={evidence.confidence})")


def _check_work_experience(profile: CandidateProfile, errors: list[str], warnings: list[str]) -> None:
    for exp in profile.work_experience:
        start = parse_resume_date(exp.start_date)
        end = parse_resume_date(exp.end_date)
        if start and end and end < start:
            errors.append(f"impossible_employment_dates: {exp.company} ({exp.start_date} - {exp.end_date})")
        if not exp.start_date and not exp.end_date:
            warnings.append(f"work_experience_missing_dates: {exp.company}")


def _check_certifications(profile: CandidateProfile, errors: list[str], warnings: list[str]) -> None:
    for cert in profile.certifications:
        if not cert.name.strip():
            errors.append("certification_missing_title")
        for evidence in cert.evidence:
            if evidence.confidence < _LOW_CONFIDENCE_THRESHOLD:
                warnings.append(f"low_confidence_certification: {cert.name}")


def _check_years_experience_against_timeline(profile: CandidateProfile, warnings: list[str]) -> None:
    ranges = [(exp.start_date, exp.end_date) for exp in profile.work_experience]
    timeline_years, _ = estimate_years_experience(ranges)
    if timeline_years is not None and profile.years_experience - timeline_years > _YEARS_EXCEEDS_TIMELINE_TOLERANCE:
        warnings.append(
            f"years_experience_exceeds_timeline: candidate profile claims {profile.years_experience} years but "
            f"employment history supports approximately {timeline_years} years"
        )
