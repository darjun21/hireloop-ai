"""
Resume merge-preview diff/apply tests — Task 33: "new-resume merge preview
(diff correctness)" and "profile conflict flagging (existing user-confirmed
data not silently deleted when absent from a new resume)".
"""

from __future__ import annotations

from src.models.candidate import CandidateProfile, Skill as CandSkill, WorkExperience as CandWorkExperience
from src.models.career_profile import CareerProfile, ProfileSkill, ProfileWorkExperience
from src.models.enums import EvidenceSourceType
from src.models.evidence import Evidence
from src.models.field_provenance import FieldProvenance
from src.services.career_profile_merge import apply_profile_update, diff_profile_update


def _candidate(skills=None, work_experience=None, professional_summary="") -> CandidateProfile:
    return CandidateProfile(
        candidate_id="cand-1",
        name="Jane Doe",
        professional_summary=professional_summary,
        years_experience=5,
        skills=[CandSkill(name=s) for s in (skills or [])],
        work_experience=work_experience or [],
    )


def test_diff_reports_new_skills():
    stored = CareerProfile(owner_id="u1", skills=[ProfileSkill(name="python")])
    new = _candidate(skills=["python", "langchain"])

    diff = diff_profile_update(stored, new)

    assert diff.new_skills == ["langchain"]
    assert diff.potential_conflicts == []


def test_diff_flags_user_confirmed_skill_missing_from_new_resume_as_conflict():
    stored = CareerProfile(
        owner_id="u1",
        skills=[ProfileSkill(name="kubernetes", provenance=FieldProvenance.USER_CONFIRMED)],
    )
    new = _candidate(skills=["python"])

    diff = diff_profile_update(stored, new)

    assert len(diff.potential_conflicts) == 1
    assert "kubernetes" in diff.potential_conflicts[0].description
    assert diff.potential_conflicts[0].existing_provenance == FieldProvenance.USER_CONFIRMED
    assert diff.removed_resume_derived == []


def test_diff_does_not_flag_resume_derived_skill_missing_from_new_resume_as_conflict():
    stored = CareerProfile(
        owner_id="u1",
        skills=[ProfileSkill(name="cobol", provenance=FieldProvenance.RESUME_DERIVED)],
    )
    new = _candidate(skills=["python"])

    diff = diff_profile_update(stored, new)

    assert diff.potential_conflicts == []
    assert diff.removed_resume_derived == ["cobol"]


def test_apply_keeps_user_confirmed_skill_absent_from_new_resume():
    stored = CareerProfile(
        owner_id="u1",
        skills=[ProfileSkill(name="kubernetes", provenance=FieldProvenance.USER_CONFIRMED)],
    )
    new = _candidate(skills=["python"])

    updated = apply_profile_update(stored, new)

    names = {s.name.lower() for s in updated.skills}
    assert "kubernetes" in names  # never silently deleted
    assert "python" in names  # newly added


def test_apply_drops_resume_derived_skill_absent_from_new_resume():
    stored = CareerProfile(
        owner_id="u1",
        skills=[ProfileSkill(name="cobol", provenance=FieldProvenance.RESUME_DERIVED)],
    )
    new = _candidate(skills=["python"])

    updated = apply_profile_update(stored, new)

    names = {s.name.lower() for s in updated.skills}
    assert "cobol" not in names
    assert "python" in names


def test_apply_never_persists_without_being_called_explicitly():
    """diff_profile_update() is read-only -- calling it must not mutate the
    stored profile at all."""
    stored = CareerProfile(owner_id="u1", skills=[ProfileSkill(name="python")])
    original_skill_count = len(stored.skills)
    new = _candidate(skills=["python", "rust"])

    diff_profile_update(stored, new)

    assert len(stored.skills) == original_skill_count


def test_apply_new_work_experience_added_with_resume_derived_provenance():
    stored = CareerProfile(owner_id="u1")
    new = _candidate(
        work_experience=[CandWorkExperience(company="Acme", title="Engineer", description="Built things")]
    )

    updated = apply_profile_update(stored, new)

    assert len(updated.work_experience) == 1
    assert updated.work_experience[0].provenance == FieldProvenance.RESUME_DERIVED
    assert updated.resume_source.parsed_profile_version == 1


def test_apply_keeps_user_confirmed_work_experience_absent_from_new_resume():
    stored = CareerProfile(
        owner_id="u1",
        work_experience=[
            ProfileWorkExperience(company="OldCo", title="Consultant", provenance=FieldProvenance.USER_CONFIRMED)
        ],
    )
    new = _candidate(work_experience=[CandWorkExperience(company="Acme", title="Engineer")])

    updated = apply_profile_update(stored, new)

    companies = {w.company for w in updated.work_experience}
    assert "OldCo" in companies
    assert "Acme" in companies


# ---------------------------------------------------------------------------
# Part 1-2/5-8 regression: a skill's real evidence source (which resume
# section grounded it) must survive the merge into the persistent
# CareerProfile, not just its bare name -- this is what makes "Evidence:
# FinRAG project" possible on the Resume & Evidence tab without inventing
# anything. Root-cause was career_profile_merge.py only ever copying
# evidence_ids (references into an ephemeral CandidateProfile that is
# never itself persisted) and discarding the evidence's source_section.
# ---------------------------------------------------------------------------


def test_apply_preserves_skill_evidence_source_sections():
    stored = CareerProfile(owner_id="u1")
    new = CandidateProfile(
        candidate_id="cand-2",
        name="Jane Doe",
        years_experience=5,
        skills=[
            CandSkill(
                name="Python",
                evidence=[
                    Evidence(
                        evidence_id="ev-1",
                        source_type=EvidenceSourceType.PROJECT,
                        source_section="Project: FinRAG",
                        source_text="Built FinRAG using Python.",
                        confidence=0.7,
                    )
                ],
            )
        ],
    )

    updated = apply_profile_update(stored, new)

    python_skill = next(s for s in updated.skills if s.name.lower() == "python")
    assert python_skill.evidence_summaries == ["Project: FinRAG"]
    assert python_skill.resume_evidence_ids == ["ev-1"]


def test_apply_skill_with_no_evidence_gets_empty_evidence_summaries_not_fabricated():
    stored = CareerProfile(owner_id="u1")
    new = CandidateProfile(candidate_id="cand-3", name="Jane Doe", years_experience=0, skills=[CandSkill(name="Rust", evidence=[])])

    updated = apply_profile_update(stored, new)

    rust_skill = next(s for s in updated.skills if s.name.lower() == "rust")
    assert rust_skill.evidence_summaries == []


def test_diff_detects_changed_summary():
    stored = CareerProfile(owner_id="u1", professional_summary="Old summary")
    new = _candidate(professional_summary="New, updated summary")

    diff = diff_profile_update(stored, new)

    assert diff.summary_changed is True
