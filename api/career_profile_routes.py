"""
Career Profile API routes — a self-contained FastAPI router mounted by
api/main.py (one `include_router` call there; no existing route in
main.py is modified).

Every endpoint here either reads/writes the new, separate
data/career_profiles.db (via src.services.career_profile_store) or calls
the EXISTING, certified resume-parsing pipeline
(src.services.resume_parser + src.agents.profile_agent.ProfileAgent) as-is.
No scoring, matching, verification, or Truth Guard logic lives here or is
reimplemented here.

Real/demo isolation: this router never reads from or writes to
api/engine.py's in-memory `_SESSIONS` (the certification-demo /
in-progress-workflow session state), data/sample_jobs.json, or
src/services/demo_application_loader.py. A CareerProfile can only ever be
created by an explicit resume upload + "Apply Profile Update" action, or
explicit field edits — never auto-populated from demo data.
"""

from __future__ import annotations

import base64
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from src.agents.profile_agent import ProfileAgent, ProfilePreferences
from src.config.settings import load_settings
from src.llm.provider import get_llm_client
from src.models.career_profile import (
    ApplicationAnswers,
    CareerEmploymentPreferences,
    CareerProfile,
    EEODemographics,
    PersonalInfo,
    ReferenceContact,
    TargetRole,
    WorkAuthorization,
)
from src.models.field_provenance import FieldProvenance
from src.services import career_profile_store as store_module
from src.services.career_profile_completeness import CompletenessStatus, compute_completeness
from src.services.career_profile_merge import (
    apply_profile_update,
    diff_profile_update,
    new_upload_id,
)
from src.services.resume_parser import parse_resume_bytes

router = APIRouter(prefix="/api/career-profile", tags=["career-profile"])

# Hardening: src/services/resume_parser.py already rejects unsupported
# extensions and empty files (see its _SUPPORTED_EXTENSIONS /
# "empty file" checks), but it has no upper bound -- a browser upload
# with no client-side limit could otherwise hand an arbitrarily large
# file to pypdf/python-docx before any validation runs. 10 MB is far
# beyond any real resume.
_MAX_RESUME_UPLOAD_BYTES = 10 * 1024 * 1024

# New, additive storage location for the raw uploaded resume file bytes --
# separate from data/sample_candidate/ (the synthetic certification demo
# resume) and data/sample_jobs.json (synthetic demo jobs). Nothing here is
# ever read by the certification-demo path (api/engine.py's
# DEMO_RESUME_PATH is a hardcoded, separate constant). Consistent with the
# existing "nothing is persisted until Apply" design: a raw file only ever
# gets written here from apply_resume_update() below, never from
# upload_resume() -- see that function's docstring.
_RESUME_STORAGE_ROOT = Path("data/career_profile_resumes")

_conn = store_module.get_connection(store_module.DEFAULT_DB_PATH)
store_module.init_schema(_conn)
_STORE = store_module.CareerProfileStore(_conn)


def get_store() -> store_module.CareerProfileStore:
    """FastAPI dependency. Tests override this via
    app.dependency_overrides[get_store] to point at an isolated in-memory
    store instead of the live data/career_profiles.db file."""
    return _STORE


Store = Annotated[store_module.CareerProfileStore, Depends(get_store)]


def _get_or_404(owner_id: str, store: store_module.CareerProfileStore) -> CareerProfile:
    profile = store.get_by_owner(owner_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="No career profile for this owner_id yet. POST /api/career-profile/{owner_id} first.")
    return profile


# ---------------------------------------------------------------------------
# Confirmation invalidation on MATERIAL changes (Part 7/8 of this round).
#
# "Material" = resume replacement, work experience changes, skills/evidence
# changes, target roles changes, work authorization changes, employment
# preferences changes -- i.e. anything that could change what evidence
# exists or what discovery searches for. Explicitly NOT material: personal
# contact-info-only edits, demographics/references edits, navigation. Those
# endpoints below simply never call _invalidate_if_materially_changed().
#
# A resume apply is unconditionally material (see apply_resume_update,
# which always clears confirmed_at -- a brand new resume version always
# counts, regardless of whether extracted text happens to diff-equal the
# old one). Every other material endpoint below instead compares a
# structural, provenance/timestamp-excluded snapshot of the field taken
# BEFORE the mutation against one taken AFTER, so a no-op save of
# identical data (e.g. re-submitting the same preferences) never
# spuriously invalidates an existing confirmation.
# ---------------------------------------------------------------------------


def _material_snapshot(value: object) -> str:
    """Comparable snapshot of a field's MATERIAL content only -- excludes
    `provenance`/`updated_at` metadata, which can change without any
    underlying fact changing (e.g. re-saving identical field values bumps
    updated_at but must never spuriously invalidate confirmation)."""
    if value is None:
        return "null"
    if isinstance(value, list):
        return "[" + ",".join(_material_snapshot(v) for v in value) + "]"
    if hasattr(value, "model_dump"):
        data = value.model_dump(mode="json")
        data.pop("provenance", None)
        data.pop("updated_at", None)
        return str(sorted(data.items()))
    return repr(value)


def _invalidate_if_materially_changed(profile: CareerProfile, before_snapshot: str, after_value: object) -> None:
    """Clears `confirmed_at` iff the profile was confirmed AND this
    field's material content actually changed (before_snapshot vs. a fresh
    snapshot of after_value) -- never on a no-op save of identical data."""
    if profile.confirmed_at is None:
        return
    if before_snapshot != _material_snapshot(after_value):
        profile.confirmed_at = None


@router.post("/{owner_id}")
def create_or_get_profile(owner_id: str, store: Store):
    profile = store.get_or_create(owner_id)
    return profile.model_dump(mode="json")


@router.get("/{owner_id}")
def get_profile(owner_id: str, store: Store):
    return _get_or_404(owner_id, store).model_dump(mode="json")


@router.get("/{owner_id}/completeness")
def get_completeness(owner_id: str, store: Store):
    profile = _get_or_404(owner_id, store)
    return compute_completeness(profile).model_dump(mode="json")


class PersonalInfoBody(BaseModel):
    first_name: str
    middle_name: str | None = None
    last_name: str
    preferred_name: str | None = None
    professional_email: str
    phone: str | None = None
    linkedin_url: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    postal_code: str | None = None


@router.put("/{owner_id}/personal-info")
def update_personal_info(owner_id: str, body: PersonalInfoBody, store: Store):
    profile = store.get_or_create(owner_id)
    profile.personal_info = PersonalInfo(**body.model_dump(), provenance=FieldProvenance.USER_CONFIRMED)
    store.save(profile)
    return profile.model_dump(mode="json")


class WorkAuthorizationBody(BaseModel):
    target_country: str | None = None
    authorized_to_work: bool | None = None
    authorization_type: str | None = None
    requires_sponsorship_now: bool | None = None
    requires_sponsorship_future: bool | None = None
    expiration_date: str | None = None
    notes: str | None = None


@router.put("/{owner_id}/work-authorization")
def update_work_authorization(owner_id: str, body: WorkAuthorizationBody, store: Store):
    """Work authorization is stored EXACTLY as confirmed by the user here —
    never inferred from a resume. See ProfileAgent boundary notes."""
    profile = store.get_or_create(owner_id)
    before = _material_snapshot(profile.work_authorization)
    profile.work_authorization = WorkAuthorization(**body.model_dump(), provenance=FieldProvenance.USER_CONFIRMED)
    _invalidate_if_materially_changed(profile, before, profile.work_authorization)
    store.save(profile)
    return profile.model_dump(mode="json")


class TargetRolesBody(BaseModel):
    roles: list[TargetRole]


@router.put("/{owner_id}/target-roles")
def update_target_roles(owner_id: str, body: TargetRolesBody, store: Store):
    profile = store.get_or_create(owner_id)
    before = _material_snapshot(profile.target_roles)
    profile.target_roles = body.roles
    _invalidate_if_materially_changed(profile, before, profile.target_roles)
    store.save(profile)
    return profile.model_dump(mode="json")


class PreferencesBody(BaseModel):
    locations: list[str] = []
    work_arrangements: list[str] = []
    employment_types: list[str] = []
    target_compensation_min: float | None = None
    target_compensation_max: float | None = None
    compensation_unit: str | None = None
    relocation_willing: bool | None = None
    travel_willingness: str | None = None
    industry_preferences: list[str] = []
    company_size_preference: str | None = None
    excluded_companies: list[str] = []
    preferred_companies: list[str] = []


@router.put("/{owner_id}/preferences")
def update_preferences(owner_id: str, body: PreferencesBody, store: Store):
    from api.validation import (
        InvalidEmploymentTypeError,
        InvalidWorkModeError,
        normalize_employment_types,
        normalize_work_modes,
    )

    profile = store.get_or_create(owner_id)
    try:
        normalized_modes = normalize_work_modes(body.work_arrangements) if body.work_arrangements else []
    except InvalidWorkModeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        normalized_employment_types = (
            normalize_employment_types(body.employment_types) if body.employment_types else []
        )
    except InvalidEmploymentTypeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    data = body.model_dump()
    data["work_arrangements"] = normalized_modes
    data["employment_types"] = normalized_employment_types
    before = _material_snapshot(profile.employment_preferences)
    profile.employment_preferences = CareerEmploymentPreferences(**data, provenance=FieldProvenance.USER_CONFIRMED)
    _invalidate_if_materially_changed(profile, before, profile.employment_preferences)
    store.save(profile)
    return profile.model_dump(mode="json")


class ApplicationAnswersBody(BaseModel):
    authorized_to_work: bool | None = None
    requires_sponsorship: bool | None = None
    willing_to_relocate: bool | None = None
    earliest_start_date: str | None = None
    notice_period: str | None = None
    desired_compensation: float | None = None
    compensation_unit: str | None = None
    preferred_employment_type: str | None = None
    preferred_work_mode: str | None = None


@router.put("/{owner_id}/application-answers")
def update_application_answers(owner_id: str, body: ApplicationAnswersBody, store: Store):
    from api.validation import (
        InvalidEmploymentTypeError,
        InvalidWorkModeError,
        normalize_employment_type,
        normalize_work_mode,
    )

    profile = store.get_or_create(owner_id)
    data = body.model_dump()
    try:
        if data["preferred_employment_type"]:
            data["preferred_employment_type"] = normalize_employment_type(data["preferred_employment_type"])
    except InvalidEmploymentTypeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        if data["preferred_work_mode"]:
            data["preferred_work_mode"] = normalize_work_mode(data["preferred_work_mode"])
    except InvalidWorkModeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    profile.application_answers = ApplicationAnswers(**data, provenance=FieldProvenance.APPLICATION_ANSWER)
    store.save(profile)
    return profile.model_dump(mode="json")


class DemographicsBody(BaseModel):
    gender: str = "NOT_PROVIDED"
    race_ethnicity: str = "NOT_PROVIDED"
    veteran_status: str = "NOT_PROVIDED"
    disability_status: str = "NOT_PROVIDED"


@router.put("/{owner_id}/demographics")
def update_demographics(owner_id: str, body: DemographicsBody, store: Store):
    """Optional, self-reported, and never read by any scoring/ranking/
    learning code path — see src/models/career_profile.py's module
    docstring."""
    profile = store.get_or_create(owner_id)
    profile.demographics = EEODemographics(**body.model_dump(), provenance=FieldProvenance.USER_CONFIRMED)
    store.save(profile)
    return profile.model_dump(mode="json")


class ReferencesBody(BaseModel):
    references: list[ReferenceContact]


@router.put("/{owner_id}/references")
def update_references(owner_id: str, body: ReferencesBody, store: Store):
    profile = store.get_or_create(owner_id)
    profile.references = body.references
    store.save(profile)
    return profile.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Resume upload -> merge preview -> apply/cancel
# ---------------------------------------------------------------------------


@router.post("/{owner_id}/resume/upload")
async def upload_resume(owner_id: str, store: Store, file: UploadFile = File(...)):
    """Parses + extracts a newly uploaded resume via the EXISTING
    resume_parser + ProfileAgent pipeline, diffs it against the currently
    stored profile, and stages the result for review. Nothing is
    persisted to the CareerProfile yet."""
    profile = store.get_or_create(owner_id)

    data = await file.read()
    if len(data) > _MAX_RESUME_UPLOAD_BYTES:
        raise HTTPException(
            status_code=422,
            detail=f"Resume file is too large ({len(data)} bytes). Maximum size is {_MAX_RESUME_UPLOAD_BYTES // (1024 * 1024)} MB.",
        )
    parse_result = parse_resume_bytes(data, file.filename or "resume")
    if not parse_result.success:
        raise HTTPException(status_code=422, detail=f"Could not extract text from resume: {parse_result.error}")

    settings = load_settings()
    llm_client = get_llm_client(settings)
    agent = ProfileAgent(llm_client)
    candidate_id = f"career-{uuid.uuid4().hex[:10]}"
    preferences = ProfilePreferences(
        target_roles=[r.title for r in profile.target_roles],
    )
    candidate_profile, validation = agent.build_profile(parse_result.extracted_text, candidate_id, preferences)

    diff = diff_profile_update(profile, candidate_profile)

    upload_id = new_upload_id()
    store.save_pending_upload(
        owner_id,
        upload_id,
        file.filename,
        {
            "candidate_profile": candidate_profile.model_dump(mode="json"),
            "diff": diff.model_dump(mode="json"),
            "validation_warnings": validation.warnings,
            "validation_errors": validation.errors,
            # Raw file bytes, staged only -- NOT written to disk yet. Only
            # written to a real file in apply_resume_update() below, once
            # the user explicitly applies the update. Base64-encoded
            # because the pending-upload row is a JSON text column.
            "_raw_file_b64": base64.b64encode(data).decode("ascii"),
        },
    )

    return {
        "upload_id": upload_id,
        "diff": diff.model_dump(mode="json"),
        "validation_warnings": validation.warnings,
        "validation_errors": validation.errors,
    }


class ApplyUploadBody(BaseModel):
    upload_id: str


@router.post("/{owner_id}/resume/apply")
def apply_resume_update(owner_id: str, body: ApplyUploadBody, store: Store):
    from src.models.candidate import CandidateProfile

    profile = store.get_or_create(owner_id)
    pending = store.get_pending_upload(body.upload_id)
    if pending is None:
        raise HTTPException(status_code=404, detail="Unknown or already-applied upload_id.")

    candidate_profile = CandidateProfile.model_validate(pending["candidate_profile"])
    original_filename = pending.get("_original_filename")

    # Persist the raw resume bytes to a real file on disk NOW -- this is
    # the explicit "Apply" moment, consistent with the rest of this
    # endpoint's "nothing persisted until Apply" behavior. This is what
    # makes a real resume_file_path exist for the existing certified
    # parse_resume_node (src/graph/nodes/resume.py) to read on a later
    # Personal Mode /run call, instead of that call silently falling back
    # to the synthetic demo resume.
    resume_file_path: str | None = None
    raw_b64 = pending.get("_raw_file_b64")
    if raw_b64:
        raw_bytes = base64.b64decode(raw_b64)
        owner_dir = _RESUME_STORAGE_ROOT / owner_id
        owner_dir.mkdir(parents=True, exist_ok=True)
        safe_filename = (original_filename or "resume").replace("/", "_").replace("\\", "_")
        dest = owner_dir / f"{body.upload_id}_{safe_filename}"
        dest.write_bytes(raw_bytes)
        resume_file_path = str(dest)

    apply_profile_update(profile, candidate_profile, original_filename, resume_file_path)
    from datetime import datetime, timezone

    profile.resume_source.uploaded_at = datetime.now(timezone.utc)
    # Persist the extraction warnings from THIS apply so the Resume &
    # Evidence tab can show them after a reload, not just in the
    # one-shot upload-preview response. Reused verbatim from the existing
    # ProfileAgent/profile_validation output -- see ResumeSourceInfo's
    # extraction_warnings docstring.
    profile.resume_source.extraction_warnings = list(pending.get("validation_warnings") or [])
    # A new resume apply changes resume-derived facts -- any prior profile
    # confirmation is no longer guaranteed accurate, so it must be
    # re-earned via a fresh "Confirm Profile" action (see confirm_profile
    # below) rather than silently carried forward.
    profile.confirmed_at = None
    store.save(profile)
    store.mark_upload_applied(body.upload_id)
    return profile.model_dump(mode="json")


@router.post("/{owner_id}/resume/cancel")
def cancel_resume_update(owner_id: str, body: ApplyUploadBody, store: Store):
    pending = store.get_pending_upload(body.upload_id)
    if pending is None:
        raise HTTPException(status_code=404, detail="Unknown or already-applied upload_id.")
    store.mark_upload_applied(body.upload_id)  # marks it consumed/discarded, never applied
    return {"status": "cancelled", "upload_id": body.upload_id}


# ---------------------------------------------------------------------------
# Field-level review / confirm actions -- lets the user resolve a flagged
# skill/work-experience/education/project entry (correct it, fill in a
# missing field, or explicitly confirm it as-is) directly from the Resume &
# Evidence tab, WITHOUT re-uploading a resume. Every one of these sets the
# entry's provenance to USER_CONFIRMED, which is exactly what
# src/services/career_profile_completeness.py's professional_history_review_
# reasons() and _professional_history() check for -- so completeness
# recalculates correctly the moment a review action lands, with no separate
# "recompute" step needed (get_completeness() is always derived fresh from
# whatever is currently stored).
# ---------------------------------------------------------------------------


class SkillReviewBody(BaseModel):
    name: str | None = None  # optional correction; omit to confirm as-is


@router.put("/{owner_id}/skills/{skill_name}/review")
def review_skill(owner_id: str, skill_name: str, body: SkillReviewBody, store: Store):
    profile = _get_or_404(owner_id, store)
    for skill in profile.skills:
        if skill.name.lower() == skill_name.lower():
            before = _material_snapshot(skill)
            if body.name and body.name.strip():
                skill.name = body.name.strip()
            skill.provenance = FieldProvenance.USER_CONFIRMED
            _invalidate_if_materially_changed(profile, before, skill)
            store.save(profile)
            return profile.model_dump(mode="json")
    raise HTTPException(status_code=404, detail=f"No skill named {skill_name!r} on this profile.")


class WorkExperienceReviewBody(BaseModel):
    company: str | None = None
    title: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    description: str | None = None
    is_current: bool = False  # explicit "still working here" -- distinguishes a genuinely blank end_date from an unreviewed one


@router.put("/{owner_id}/work-experience/{entry_id}/review")
def review_work_experience(owner_id: str, entry_id: str, body: WorkExperienceReviewBody, store: Store):
    profile = _get_or_404(owner_id, store)
    for entry in profile.work_experience:
        if entry.entry_id == entry_id:
            before = _material_snapshot(entry)
            if body.company and body.company.strip():
                entry.company = body.company.strip()
            if body.title and body.title.strip():
                entry.title = body.title.strip()
            if body.start_date is not None:
                entry.start_date = body.start_date.strip() or entry.start_date
            if body.is_current:
                entry.end_date = "Present"
            elif body.end_date is not None:
                entry.end_date = body.end_date.strip() or entry.end_date
            if body.description is not None:
                entry.description = body.description
            entry.provenance = FieldProvenance.USER_CONFIRMED
            _invalidate_if_materially_changed(profile, before, entry)
            store.save(profile)
            return profile.model_dump(mode="json")
    raise HTTPException(status_code=404, detail=f"No work experience entry {entry_id!r} on this profile.")


class EducationReviewBody(BaseModel):
    institution: str | None = None
    degree: str | None = None
    field_of_study: str | None = None
    start_date: str | None = None
    end_date: str | None = None


@router.put("/{owner_id}/education/{entry_id}/review")
def review_education(owner_id: str, entry_id: str, body: EducationReviewBody, store: Store):
    profile = _get_or_404(owner_id, store)
    for entry in profile.education:
        if entry.entry_id == entry_id:
            before = _material_snapshot(entry)
            if body.institution and body.institution.strip():
                entry.institution = body.institution.strip()
            if body.degree is not None:
                entry.degree = body.degree
            if body.field_of_study is not None:
                entry.field_of_study = body.field_of_study
            if body.start_date is not None:
                entry.start_date = body.start_date
            if body.end_date is not None:
                entry.end_date = body.end_date
            entry.provenance = FieldProvenance.USER_CONFIRMED
            _invalidate_if_materially_changed(profile, before, entry)
            store.save(profile)
            return profile.model_dump(mode="json")
    raise HTTPException(status_code=404, detail=f"No education entry {entry_id!r} on this profile.")


class ProjectReviewBody(BaseModel):
    name: str | None = None
    description: str | None = None


@router.put("/{owner_id}/projects/{entry_id}/review")
def review_project(owner_id: str, entry_id: str, body: ProjectReviewBody, store: Store):
    profile = _get_or_404(owner_id, store)
    for entry in profile.projects:
        if entry.entry_id == entry_id:
            before = _material_snapshot(entry)
            if body.name and body.name.strip():
                entry.name = body.name.strip()
            if body.description is not None:
                entry.description = body.description
            entry.provenance = FieldProvenance.USER_CONFIRMED
            _invalidate_if_materially_changed(profile, before, entry)
            store.save(profile)
            return profile.model_dump(mode="json")
    raise HTTPException(status_code=404, detail=f"No project entry {entry_id!r} on this profile.")


# ---------------------------------------------------------------------------
# Explicit profile confirmation gate (Part 12). Never auto-fires: only an
# explicit POST here can set confirmed_at, and only once every REQUIRED
# completeness category (see career_profile_completeness.py) is COMPLETE --
# optional categories (demographics/references) are never a blocker. This
# does not itself start discovery; the frontend's "Find Opportunities"
# action is a separate, explicit step.
# ---------------------------------------------------------------------------


@router.post("/{owner_id}/confirm")
def confirm_profile(owner_id: str, store: Store):
    profile = _get_or_404(owner_id, store)
    completeness = compute_completeness(profile)
    incomplete = [
        c.category
        for c in completeness.categories
        if not c.category.endswith("_OPTIONAL") and c.status != CompletenessStatus.COMPLETE
    ]
    if incomplete:
        raise HTTPException(
            status_code=409,
            detail=f"Profile is not yet complete: {', '.join(incomplete)} still need review.",
        )
    from datetime import datetime, timezone

    profile.confirmed_at = datetime.now(timezone.utc)
    profile.confirmed_profile_version += 1
    store.save(profile)
    return profile.model_dump(mode="json")
