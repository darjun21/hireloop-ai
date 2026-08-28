"""
Deterministic Career Profile completeness calculation.

Purely rule-based (no LLM call, nothing fabricated) so the UI can show a
COMPLETE / NEEDS_REVIEW / MISSING badge per category that is always
reproducible from the stored CareerProfile alone. Optional sections
(demographics, references) are explicitly excluded from every category's
rule set and can never reduce completeness — see
tests/test_career_profile_completeness.py.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel

from src.models.career_profile import CareerProfile
from src.models.field_provenance import FieldProvenance


class CompletenessStatus(str, Enum):
    COMPLETE = "COMPLETE"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    MISSING = "MISSING"


class CategoryCompleteness(BaseModel):
    category: str
    status: CompletenessStatus
    missing_fields: list[str] = []
    # NEW: specific, itemized, deterministic reasons for a NEEDS_REVIEW/
    # MISSING status -- e.g. "No work experience entries recorded.",
    # "1 work experience entry is missing a start date." Every string here
    # is generated from a real, checkable condition on the stored
    # CareerProfile (see professional_history_review_reasons() below) --
    # never a vague/generic placeholder. Empty for COMPLETE categories and
    # for categories that don't yet have a reasons function wired in.
    review_reasons: list[str] = []


class ProfileCompleteness(BaseModel):
    categories: list[CategoryCompleteness]
    overall_percent_complete: float


def _identity_contact(p: CareerProfile) -> CategoryCompleteness:
    missing = []
    pi = p.personal_info
    if pi is None:
        missing = ["first_name", "last_name", "professional_email"]
    else:
        if not pi.first_name:
            missing.append("first_name")
        if not pi.last_name:
            missing.append("last_name")
        if not pi.professional_email:
            missing.append("professional_email")
    status = CompletenessStatus.COMPLETE if not missing else (
        CompletenessStatus.MISSING if pi is None else CompletenessStatus.NEEDS_REVIEW
    )
    return CategoryCompleteness(category="IDENTITY_CONTACT", status=status, missing_fields=missing)


def _resume(p: CareerProfile) -> CategoryCompleteness:
    missing = []
    if p.resume_source.uploaded_at is None and p.resume_source.parsed_profile_version == 0:
        missing.append("resume_upload")
    if not p.work_experience and not p.education:
        missing.append("work_experience_or_education")
    status = CompletenessStatus.COMPLETE if not missing else (
        CompletenessStatus.MISSING if "resume_upload" in missing else CompletenessStatus.NEEDS_REVIEW
    )
    return CategoryCompleteness(category="RESUME", status=status, missing_fields=missing)


def _work_authorization(p: CareerProfile) -> CategoryCompleteness:
    wa = p.work_authorization
    missing = []
    if wa is None or wa.authorized_to_work is None:
        missing.append("authorized_to_work")
    if wa is None or not wa.authorization_type:
        missing.append("authorization_type")
    status = CompletenessStatus.COMPLETE if not missing else (
        CompletenessStatus.MISSING if wa is None else CompletenessStatus.NEEDS_REVIEW
    )
    return CategoryCompleteness(category="WORK_AUTHORIZATION", status=status, missing_fields=missing)


def _target_roles(p: CareerProfile) -> CategoryCompleteness:
    if p.target_roles:
        return CategoryCompleteness(category="TARGET_ROLES", status=CompletenessStatus.COMPLETE)
    return CategoryCompleteness(
        category="TARGET_ROLES", status=CompletenessStatus.MISSING, missing_fields=["target_roles"]
    )


def _preferences(p: CareerProfile) -> CategoryCompleteness:
    prefs = p.employment_preferences
    missing = []
    if not prefs.locations:
        missing.append("locations")
    if not prefs.work_arrangements:
        missing.append("work_arrangements")
    status = CompletenessStatus.COMPLETE if not missing else (
        CompletenessStatus.MISSING if len(missing) == 2 else CompletenessStatus.NEEDS_REVIEW
    )
    return CategoryCompleteness(category="PREFERENCES", status=status, missing_fields=missing)


def professional_history_review_reasons(p: CareerProfile) -> list[str]:
    """Specific, itemized reasons Professional History is not COMPLETE --
    every entry here comes from a real, checkable condition on the stored
    CareerProfile, never a vague/generic message. Returns [] when there is
    nothing to flag (regardless of overall status)."""
    reasons: list[str] = []

    if not p.work_experience:
        if p.projects:
            reasons.append(
                f"No work experience entries recorded, but {len(p.projects)} project(s) were extracted "
                "from your resume — review whether any of them should be added as work experience."
            )
        else:
            reasons.append("No work experience recorded.")

    if not p.skills:
        reasons.append("No skills recorded.")

    missing_start = [w for w in p.work_experience if not (w.start_date or "").strip()]
    if missing_start:
        entries = "entry is" if len(missing_start) == 1 else "entries are"
        reasons.append(f"{len(missing_start)} work experience {entries} missing a start date.")

    missing_end = [w for w in p.work_experience if not (w.end_date or "").strip()]
    if missing_end:
        entries = "entry is" if len(missing_end) == 1 else "entries are"
        reasons.append(
            f"{len(missing_end)} work experience {entries} missing an end date "
            "(leave blank only if this role is still current)."
        )

    unreviewed = [w for w in p.work_experience if w.provenance == FieldProvenance.RESUME_DERIVED]
    if unreviewed:
        entries = "entry has" if len(unreviewed) == 1 else "entries have"
        reasons.append(
            f"{len(unreviewed)} work experience {entries} not yet been reviewed/confirmed "
            "since they were extracted from your resume."
        )

    unreviewed_skills = [s for s in p.skills if s.provenance == FieldProvenance.RESUME_DERIVED]
    if unreviewed_skills:
        entries = "skill has" if len(unreviewed_skills) == 1 else "skills have"
        reasons.append(
            f"{len(unreviewed_skills)} {entries} not yet been reviewed/confirmed "
            "since they were extracted from your resume."
        )

    return reasons


def _professional_history(p: CareerProfile) -> CategoryCompleteness:
    missing = []
    if not p.work_experience:
        missing.append("work_experience")
    if not p.skills:
        missing.append("skills")

    reasons = professional_history_review_reasons(p)
    if not missing and reasons:
        # Both sections have at least one entry, but a real, checkable
        # condition (missing dates, or a RESUME_DERIVED entry the human
        # has never reviewed/confirmed) is still outstanding -- see
        # professional_history_review_reasons(). Status is NEEDS_REVIEW,
        # not COMPLETE, until the human takes the review/confirm action
        # (api/career_profile_routes.py's field-level review endpoints)
        # that resolves it -- that's what makes "reviewed" actually mean
        # something instead of just "an entry exists".
        missing.append("review")

    status = CompletenessStatus.COMPLETE if not missing else (
        CompletenessStatus.MISSING
        if ("work_experience" in missing and "skills" in missing)
        else CompletenessStatus.NEEDS_REVIEW
    )
    return CategoryCompleteness(
        category="PROFESSIONAL_HISTORY",
        status=status,
        missing_fields=missing,
        review_reasons=reasons if status != CompletenessStatus.COMPLETE else [],
    )


# Optional categories are surfaced for UI display but are NEVER included in
# overall_percent_complete's denominator — see compute_completeness().
def _demographics(p: CareerProfile) -> CategoryCompleteness:
    provided = any(
        getattr(p.demographics, field) != "NOT_PROVIDED"
        for field in ("gender", "race_ethnicity", "veteran_status", "disability_status")
    )
    return CategoryCompleteness(
        category="DEMOGRAPHICS_OPTIONAL",
        status=CompletenessStatus.COMPLETE if provided else CompletenessStatus.NEEDS_REVIEW,
    )


def _references(p: CareerProfile) -> CategoryCompleteness:
    return CategoryCompleteness(
        category="REFERENCES_OPTIONAL",
        status=CompletenessStatus.COMPLETE if p.references else CompletenessStatus.NEEDS_REVIEW,
    )


_REQUIRED_CATEGORY_FNS = [
    _identity_contact,
    _resume,
    _work_authorization,
    _target_roles,
    _preferences,
    _professional_history,
]
_OPTIONAL_CATEGORY_FNS = [_demographics, _references]


def compute_completeness(profile: CareerProfile) -> ProfileCompleteness:
    required = [fn(profile) for fn in _REQUIRED_CATEGORY_FNS]
    optional = [fn(profile) for fn in _OPTIONAL_CATEGORY_FNS]
    complete_count = sum(1 for c in required if c.status == CompletenessStatus.COMPLETE)
    percent = round(100 * complete_count / len(required), 1) if required else 0.0
    return ProfileCompleteness(categories=required + optional, overall_percent_complete=percent)
