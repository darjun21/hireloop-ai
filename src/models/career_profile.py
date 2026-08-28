"""
CareerProfile domain model — the persistent, editable "Career Profile" for
a real (non-demo) candidate.

This is a NEW, separate model from src.models.candidate.CandidateProfile.
CandidateProfile is the certified, frozen output of a single resume parse
for one workflow run; CareerProfile is a longer-lived, user-owned record
that a resume parse feeds INTO (via merge/diff — see
src.services.career_profile_merge) but that also carries information a
resume never contains: work authorization, application answers, contact
info, EEO/demographic responses, references. Composition, not inheritance
or field-bolting onto CandidateProfile — CandidateProfile is never
imported by name into this file's field types beyond simple reuse of the
existing WorkMode/EmploymentType enums.

Explicit exclusions (see docs brief §5 / Task constraints):
  - No full street address field anywhere in PersonalInfo — city/state/
    country/postal only.
  - No third-party email password field anywhere in this model. (See
    tests/test_career_profile_privacy.py for a structural regression test
    asserting this.)
  - EEODemographics defaults to "NOT_PROVIDED" for every field and is
    never read by any scoring/ranking/learning code path. This is enforced
    by construction: no function in src/models/scoring.py or
    src/agents/match_analyst.py (or any other scoring/ranking code) takes
    a CareerProfile or EEODemographics argument, and this module is never
    imported by those modules.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field

from src.models.enums import EmploymentType, WorkMode
from src.models.field_provenance import FieldProvenance


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Personal / contact
# ---------------------------------------------------------------------------


class PersonalInfo(BaseModel):
    first_name: str = Field(..., min_length=1)
    middle_name: str | None = None
    last_name: str = Field(..., min_length=1)
    preferred_name: str | None = None
    professional_email: str = Field(..., min_length=3)
    phone: str | None = None
    linkedin_url: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    postal_code: str | None = None
    provenance: FieldProvenance = FieldProvenance.USER_CONFIRMED
    updated_at: datetime = Field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
# Work authorization — always exactly what the user confirms, never inferred
# from a resume. See ProfileAgent boundary notes in
# src/services/career_profile_merge.py.
# ---------------------------------------------------------------------------


class WorkAuthorization(BaseModel):
    target_country: str | None = None
    authorized_to_work: bool | None = None
    authorization_type: str | None = None
    requires_sponsorship_now: bool | None = None
    requires_sponsorship_future: bool | None = None
    expiration_date: str | None = None
    notes: str | None = None
    # Always USER_CONFIRMED or HUMAN_CONFIRMATION in practice — the API
    # layer never accepts RESUME_DERIVED for this section (see
    # api/career_profile_routes.py).
    provenance: FieldProvenance = FieldProvenance.USER_CONFIRMED
    updated_at: datetime = Field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
# Target roles — free-text list, not a hardcoded taxonomy
# ---------------------------------------------------------------------------


class RolePriority(str, Enum):
    PRIMARY = "PRIMARY"
    SECONDARY = "SECONDARY"
    EXPLORATORY = "EXPLORATORY"


class TargetRole(BaseModel):
    title: str = Field(..., min_length=1)
    priority: RolePriority | None = None
    provenance: FieldProvenance = FieldProvenance.USER_CONFIRMED


# ---------------------------------------------------------------------------
# Employment preferences
# ---------------------------------------------------------------------------


class CareerEmploymentPreferences(BaseModel):
    locations: list[str] = Field(default_factory=list)
    work_arrangements: list[WorkMode] = Field(default_factory=list)
    employment_types: list[EmploymentType] = Field(default_factory=list)
    target_compensation_min: float | None = Field(default=None, ge=0)
    target_compensation_max: float | None = Field(default=None, ge=0)
    compensation_unit: str | None = None  # e.g. "ANNUAL_USD", "HOURLY_USD"
    relocation_willing: bool | None = None
    travel_willingness: str | None = None
    industry_preferences: list[str] = Field(default_factory=list)
    company_size_preference: str | None = None
    excluded_companies: list[str] = Field(default_factory=list)
    preferred_companies: list[str] = Field(default_factory=list)
    provenance: FieldProvenance = FieldProvenance.USER_CONFIRMED
    updated_at: datetime = Field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
# Professional information
# ---------------------------------------------------------------------------


class ProfileSkill(BaseModel):
    name: str = Field(..., min_length=1)
    provenance: FieldProvenance = FieldProvenance.RESUME_DERIVED
    resume_evidence_ids: list[str] = Field(default_factory=list)
    # NEW: short, structural evidence source labels (e.g. "Work Experience:
    # Staff Engineer at Personal Corp", "Project: FinRAG", "Skills") copied
    # from the CandidateProfile.Skill.evidence.source_section the resume
    # parse produced for this skill, at merge time (see
    # src/services/career_profile_merge.py). Previously only opaque
    # resume_evidence_ids (references into an ephemeral CandidateProfile
    # that is never persisted) were kept, so the Resume & Evidence UI had
    # no real evidence text to show for a skill even after the frontend
    # was fixed to render it -- this is what actually makes "Evidence: ..."
    # possible without inventing anything.
    evidence_summaries: list[str] = Field(default_factory=list)
    notes: str | None = None


class ProfileWorkExperience(BaseModel):
    entry_id: str = Field(default_factory=lambda: _new_id("we"))
    company: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    start_date: str | None = None
    end_date: str | None = None
    description: str | None = None
    skills_used: list[str] = Field(default_factory=list)
    provenance: FieldProvenance = FieldProvenance.RESUME_DERIVED


class ProfileProject(BaseModel):
    entry_id: str = Field(default_factory=lambda: _new_id("proj"))
    name: str = Field(..., min_length=1)
    description: str | None = None
    skills_used: list[str] = Field(default_factory=list)
    provenance: FieldProvenance = FieldProvenance.RESUME_DERIVED


class ProfileEducation(BaseModel):
    entry_id: str = Field(default_factory=lambda: _new_id("edu"))
    institution: str = Field(..., min_length=1)
    degree: str | None = None
    field_of_study: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    provenance: FieldProvenance = FieldProvenance.RESUME_DERIVED


class ProfileCertification(BaseModel):
    entry_id: str = Field(default_factory=lambda: _new_id("cert"))
    name: str = Field(..., min_length=1)
    issuer: str | None = None
    date: str | None = None
    provenance: FieldProvenance = FieldProvenance.RESUME_DERIVED


class ProfileLanguage(BaseModel):
    name: str = Field(..., min_length=1)
    proficiency: str | None = None
    provenance: FieldProvenance = FieldProvenance.USER_CONFIRMED


# ---------------------------------------------------------------------------
# Application answers — genuinely separate from resume facts. These are
# reusable answers to common application questions; they are never derived
# automatically from the resume parse.
# ---------------------------------------------------------------------------


class ApplicationAnswers(BaseModel):
    authorized_to_work: bool | None = None
    requires_sponsorship: bool | None = None
    willing_to_relocate: bool | None = None
    earliest_start_date: str | None = None
    notice_period: str | None = None
    desired_compensation: float | None = Field(default=None, ge=0)
    compensation_unit: str | None = None
    preferred_employment_type: EmploymentType | None = None
    preferred_work_mode: WorkMode | None = None
    provenance: FieldProvenance = FieldProvenance.APPLICATION_ANSWER
    updated_at: datetime = Field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
# Optional EEO / demographics — default NOT_PROVIDED, structurally excluded
# from scoring/ranking/learning (no scoring/ranking/learning function in
# this codebase accepts a CareerProfile or EEODemographics instance).
# ---------------------------------------------------------------------------


class EEODemographics(BaseModel):
    gender: str = "NOT_PROVIDED"
    race_ethnicity: str = "NOT_PROVIDED"
    veteran_status: str = "NOT_PROVIDED"
    disability_status: str = "NOT_PROVIDED"
    provenance: FieldProvenance = FieldProvenance.USER_CONFIRMED
    updated_at: datetime = Field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
# References — empty by default, never required
# ---------------------------------------------------------------------------


class ReferenceContact(BaseModel):
    reference_id: str = Field(default_factory=lambda: _new_id("ref"))
    name: str = Field(..., min_length=1)
    relationship: str | None = None
    company: str | None = None
    email: str | None = None
    phone: str | None = None


# ---------------------------------------------------------------------------
# Resume provenance metadata (which upload most recently fed this profile)
# ---------------------------------------------------------------------------


class ResumeSourceInfo(BaseModel):
    original_filename: str | None = None
    uploaded_at: datetime | None = None
    parsed_profile_version: int = 0
    source_candidate_id: str | None = None
    # NEW field (added on top of the ResumeSourceInfo model itself only
    # added last round -- safe to extend, not part of the original
    # 357-test certified baseline). Path to the raw uploaded resume
    # bytes on disk -- e.g.
    # data/career_profile_resumes/{owner_id}/{upload_id}_{original_filename}
    # -- set only when a resume update is explicitly applied (see
    # api/career_profile_routes.py::apply_resume_update). This is what
    # lets the existing certified src.graph.nodes.resume.parse_resume_node
    # (which always expects state["resume_file_path"] to point at a real
    # file) actually parse the REAL candidate's resume for a Personal
    # Mode /run call, instead of silently falling back to the synthetic
    # demo resume.
    resume_file_path: str | None = None
    # NEW: the ProfileAgent/profile_validation warnings produced by the
    # most recently APPLIED resume parse (e.g. "dropped a work experience
    # entry with missing company/title: ..."). Previously these only ever
    # existed transiently in the upload-preview response and were lost the
    # moment the page was reloaded or the user navigated away and back --
    # so the Resume & Evidence tab's "Extraction Warnings" section (see
    # web/app/career-profile/page.tsx) had nothing persisted to show.
    # Reuses the EXISTING, certified ProfileAgent/profile_validation
    # output verbatim -- nothing here is generated or reworded.
    extraction_warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Top-level CareerProfile
# ---------------------------------------------------------------------------


class CareerProfile(BaseModel):
    profile_id: str = Field(default_factory=lambda: _new_id("career"))
    owner_id: str = Field(..., min_length=1)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    personal_info: PersonalInfo | None = None
    work_authorization: WorkAuthorization | None = None
    target_roles: list[TargetRole] = Field(default_factory=list)
    employment_preferences: CareerEmploymentPreferences = Field(default_factory=CareerEmploymentPreferences)

    professional_summary: str = ""
    total_experience_years: float | None = None
    work_experience: list[ProfileWorkExperience] = Field(default_factory=list)
    projects: list[ProfileProject] = Field(default_factory=list)
    skills: list[ProfileSkill] = Field(default_factory=list)
    education: list[ProfileEducation] = Field(default_factory=list)
    certifications: list[ProfileCertification] = Field(default_factory=list)
    languages: list[ProfileLanguage] = Field(default_factory=list)

    application_answers: ApplicationAnswers = Field(default_factory=ApplicationAnswers)
    demographics: EEODemographics = Field(default_factory=EEODemographics)
    references: list[ReferenceContact] = Field(default_factory=list)

    resume_source: ResumeSourceInfo = Field(default_factory=ResumeSourceInfo)

    # NEW: set only by the explicit "Confirm Profile" action (see
    # api/career_profile_routes.py::confirm_profile), and only once every
    # REQUIRED completeness category is COMPLETE. Cleared automatically
    # whenever a MATERIAL field (resume replacement, work experience/
    # skills/evidence changes, target roles, work authorization,
    # employment preferences) actually changes after confirmation -- see
    # api/career_profile_routes.py's _invalidate_if_materially_changed()
    # -- so it can never go stale and silently over-report readiness. This
    # is the field POST /run's enforcement gate (api/main.py::start_run)
    # actually checks: no confirmed_at means no real discovery run.
    confirmed_at: datetime | None = None
    # NEW: increments by 1 every time confirmed_at is (re)set by an
    # explicit POST /confirm (see confirm_profile below). A simple,
    # inspectable "confirmed version" marker -- lets any future caller
    # detect "have I been confirmed at least once / how many times" without
    # having to diff full profile content. Never decremented, never reset
    # by an invalidation (only confirmed_at is cleared on invalidation --
    # this counter is a historical tally, not a staleness flag itself).
    confirmed_profile_version: int = 0
