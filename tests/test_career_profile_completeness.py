"""Deterministic profile completeness tests."""

from __future__ import annotations

from src.models.career_profile import (
    CareerEmploymentPreferences,
    CareerProfile,
    EEODemographics,
    PersonalInfo,
    ProfileSkill,
    ProfileWorkExperience,
    ReferenceContact,
    TargetRole,
    WorkAuthorization,
)
from src.models.enums import WorkMode
from src.models.field_provenance import FieldProvenance
from src.services.career_profile_completeness import (
    CompletenessStatus,
    compute_completeness,
    professional_history_review_reasons,
)


def test_empty_profile_is_fully_missing():
    profile = CareerProfile(owner_id="u1")
    result = compute_completeness(profile)
    statuses = {c.category: c.status for c in result.categories}
    assert statuses["IDENTITY_CONTACT"] == CompletenessStatus.MISSING
    assert statuses["RESUME"] == CompletenessStatus.MISSING
    assert statuses["WORK_AUTHORIZATION"] == CompletenessStatus.MISSING
    assert statuses["TARGET_ROLES"] == CompletenessStatus.MISSING
    assert result.overall_percent_complete == 0.0


def _fully_complete_profile() -> CareerProfile:
    from datetime import datetime, timezone

    profile = CareerProfile(
        owner_id="u1",
        personal_info=PersonalInfo(first_name="Jane", last_name="Doe", professional_email="jane@example.com"),
        work_authorization=WorkAuthorization(authorized_to_work=True, authorization_type="US Citizen"),
        target_roles=[TargetRole(title="AI Engineer")],
        employment_preferences=CareerEmploymentPreferences(
            locations=["Remote"], work_arrangements=[WorkMode.REMOTE]
        ),
        skills=[ProfileSkill(name="python", provenance=FieldProvenance.USER_CONFIRMED)],
        work_experience=[
            ProfileWorkExperience(
                company="Acme",
                title="Engineer",
                start_date="2020-01",
                end_date="2023-01",
                provenance=FieldProvenance.USER_CONFIRMED,
            )
        ],
    )
    profile.resume_source.uploaded_at = datetime.now(timezone.utc)
    profile.resume_source.parsed_profile_version = 1
    return profile


def test_fully_populated_profile_is_100_percent_on_required_categories():
    profile = _fully_complete_profile()
    result = compute_completeness(profile)
    required_statuses = [
        c.status for c in result.categories if c.category not in ("DEMOGRAPHICS_OPTIONAL", "REFERENCES_OPTIONAL")
    ]
    assert all(s == CompletenessStatus.COMPLETE for s in required_statuses)
    assert result.overall_percent_complete == 100.0


def test_demographics_and_references_never_reduce_completeness():
    with_optional = _fully_complete_profile()
    with_optional.demographics = EEODemographics(gender="Woman")
    with_optional.references = [ReferenceContact(name="Ref One")]

    without_optional = _fully_complete_profile()
    # defaults: demographics all NOT_PROVIDED, references empty

    assert compute_completeness(with_optional).overall_percent_complete == compute_completeness(
        without_optional
    ).overall_percent_complete
    assert compute_completeness(without_optional).overall_percent_complete == 100.0


def test_completeness_is_deterministic_same_input_same_output():
    profile = _fully_complete_profile()
    r1 = compute_completeness(profile)
    r2 = compute_completeness(profile)
    assert r1.model_dump() == r2.model_dump()


# ---------------------------------------------------------------------------
# Part 3-4 regression: "PROFESSIONAL HISTORY — NEEDS REVIEW" must always
# come with a specific, itemized, checkable reason -- never a bare status
# with no explanation. Every scenario below is a synthetic, minimal
# CareerProfile built directly from the model (no real resume content).
# ---------------------------------------------------------------------------


def test_review_reasons_empty_when_nothing_to_flag():
    profile = _fully_complete_profile()
    assert professional_history_review_reasons(profile) == []
    statuses = {c.category: c for c in compute_completeness(profile).categories}
    assert statuses["PROFESSIONAL_HISTORY"].status == CompletenessStatus.COMPLETE
    assert statuses["PROFESSIONAL_HISTORY"].review_reasons == []


def test_review_reasons_no_work_experience_but_has_projects():
    from src.models.career_profile import ProfileProject

    profile = CareerProfile(
        owner_id="u1",
        skills=[ProfileSkill(name="python", provenance=FieldProvenance.USER_CONFIRMED)],
        projects=[ProfileProject(name="FinRAG", provenance=FieldProvenance.RESUME_DERIVED)],
    )
    reasons = professional_history_review_reasons(profile)
    assert any("No work experience entries recorded, but 1 project(s)" in r for r in reasons)


def test_review_reasons_no_work_experience_no_projects():
    profile = CareerProfile(owner_id="u1", skills=[ProfileSkill(name="python")])
    reasons = professional_history_review_reasons(profile)
    assert "No work experience recorded." in reasons


def test_review_reasons_missing_start_date():
    profile = CareerProfile(
        owner_id="u1",
        skills=[ProfileSkill(name="python", provenance=FieldProvenance.USER_CONFIRMED)],
        work_experience=[
            ProfileWorkExperience(
                company="Acme",
                title="Engineer",
                end_date="2023-01",
                provenance=FieldProvenance.USER_CONFIRMED,
            )
        ],
    )
    reasons = professional_history_review_reasons(profile)
    assert "1 work experience entry is missing a start date." in reasons


def test_review_reasons_missing_end_date():
    profile = CareerProfile(
        owner_id="u1",
        skills=[ProfileSkill(name="python", provenance=FieldProvenance.USER_CONFIRMED)],
        work_experience=[
            ProfileWorkExperience(
                company="Acme",
                title="Engineer",
                start_date="2020-01",
                provenance=FieldProvenance.USER_CONFIRMED,
            )
        ],
    )
    reasons = professional_history_review_reasons(profile)
    assert any("missing an end date" in r for r in reasons)


def test_review_reasons_unreviewed_resume_derived_entries():
    profile = CareerProfile(
        owner_id="u1",
        skills=[ProfileSkill(name="python", provenance=FieldProvenance.RESUME_DERIVED)],
        work_experience=[
            ProfileWorkExperience(
                company="Acme",
                title="Engineer",
                start_date="2020-01",
                end_date="2023-01",
                provenance=FieldProvenance.RESUME_DERIVED,
            )
        ],
    )
    reasons = professional_history_review_reasons(profile)
    assert any("not yet been reviewed/confirmed" in r and "work experience" in r for r in reasons)
    assert any("not yet been reviewed/confirmed" in r and "skill" in r for r in reasons)
    # Unreviewed resume-derived data means NEEDS_REVIEW, not COMPLETE, even
    # though both work_experience and skills are non-empty.
    statuses = {c.category: c for c in compute_completeness(profile).categories}
    assert statuses["PROFESSIONAL_HISTORY"].status == CompletenessStatus.NEEDS_REVIEW
    assert statuses["PROFESSIONAL_HISTORY"].review_reasons == reasons


def test_professional_history_flips_to_complete_only_once_reviewed():
    profile = CareerProfile(
        owner_id="u1",
        skills=[ProfileSkill(name="python", provenance=FieldProvenance.RESUME_DERIVED)],
        work_experience=[
            ProfileWorkExperience(
                company="Acme",
                title="Engineer",
                start_date="2020-01",
                end_date="2023-01",
                provenance=FieldProvenance.RESUME_DERIVED,
            )
        ],
    )
    before = {c.category: c.status for c in compute_completeness(profile).categories}
    assert before["PROFESSIONAL_HISTORY"] == CompletenessStatus.NEEDS_REVIEW

    # Simulate the review/confirm action (api/career_profile_routes.py's
    # /work-experience/{entry_id}/review and /skills/{name}/review) --
    # both just set provenance to USER_CONFIRMED.
    profile.work_experience[0].provenance = FieldProvenance.USER_CONFIRMED
    profile.skills[0].provenance = FieldProvenance.USER_CONFIRMED

    after = {c.category: c.status for c in compute_completeness(profile).categories}
    assert after["PROFESSIONAL_HISTORY"] == CompletenessStatus.COMPLETE

    # Other categories are untouched by this change -- overall completeness
    # only moves for the category that was actually reviewed, never forced
    # to 100% as a side effect.
    before_other = {k: v for k, v in before.items() if k != "PROFESSIONAL_HISTORY"}
    after_other = {c.category: c.status for c in compute_completeness(profile).categories if c.category != "PROFESSIONAL_HISTORY"}
    assert before_other == after_other
