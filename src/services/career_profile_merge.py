"""
Resume update / merge-preview logic for the Career Profile feature.

Reuses the EXISTING, certified src.agents.profile_agent.ProfileAgent and
src.services.resume_parser as-is (imported, never reimplemented or
modified) to turn a newly uploaded resume into a CandidateProfile, then
diffs that against the currently stored CareerProfile. Nothing is ever
silently overwritten: diff_profile_update() is pure/read-only, and
apply_profile_update() only runs after an explicit human "Apply Profile
Update" action.

ProfileAgent boundary (unchanged, verified by inspection of
src/agents/profile_agent.py): it extracts/structures/flags ambiguity from
resume TEXT only. It never infers legal status, demographics, compensation
expectations, or relocation willingness — those fields
(WorkAuthorization, EEODemographics, ApplicationAnswers.desired_compensation,
CareerEmploymentPreferences.relocation_willing) are never touched by any
function in this module either; a resume merge only ever writes to
resume-derived sections (skills, work experience, projects, education,
certifications, professional_summary, total_experience_years).
"""

from __future__ import annotations

from uuid import uuid4

from pydantic import BaseModel, Field

from src.models.candidate import CandidateProfile
from src.models.career_profile import (
    CareerProfile,
    ProfileCertification,
    ProfileEducation,
    ProfileProject,
    ProfileSkill,
    ProfileWorkExperience,
    ResumeSourceInfo,
)
from src.models.field_provenance import FieldProvenance


class ProfileConflict(BaseModel):
    """A currently-stored, human-confirmed fact that is absent from the
    newly parsed resume. Never auto-resolved — always surfaced for human
    review; the existing value is kept unless the human explicitly removes
    it via a future edit."""

    category: str
    description: str
    existing_provenance: FieldProvenance


class ProfileUpdateDiff(BaseModel):
    new_skills: list[str] = Field(default_factory=list)
    new_work_experience: list[str] = Field(default_factory=list)
    new_education: list[str] = Field(default_factory=list)
    new_certifications: list[str] = Field(default_factory=list)
    changed_work_experience: list[str] = Field(default_factory=list)
    removed_resume_derived: list[str] = Field(default_factory=list)
    potential_conflicts: list[ProfileConflict] = Field(default_factory=list)
    summary_changed: bool = False


def _skill_names(items) -> set[str]:
    return {s.name.lower() for s in items}


def _evidence_summaries_for(skill) -> list[str]:
    """Short, structural evidence-source labels for one newly-extracted
    skill (e.g. "Work Experience: Staff Engineer at Personal Corp",
    "Project: FinRAG", "Skills") -- taken verbatim from the source_section
    of the CandidateProfile.Skill.evidence this skill already carries.
    Never fabricated: if the resume parse produced no evidence for this
    skill, the result is an empty list, not a guess."""
    return sorted({e.source_section for e in skill.evidence if e.source_section})


def _work_key(company: str, title: str) -> str:
    return f"{company.strip().lower()}::{title.strip().lower()}"


def _edu_key(institution: str, degree: str | None) -> str:
    return f"{institution.strip().lower()}::{(degree or '').strip().lower()}"


def diff_profile_update(stored: CareerProfile, new_candidate: CandidateProfile) -> ProfileUpdateDiff:
    """Read-only comparison. Never mutates `stored`."""
    diff = ProfileUpdateDiff()

    stored_skill_names = _skill_names(stored.skills)
    new_skill_names = _skill_names(new_candidate.skills)
    diff.new_skills = sorted(n for n in new_skill_names if n not in stored_skill_names)
    missing_skills = stored_skill_names - new_skill_names
    for skill in stored.skills:
        if skill.name.lower() in missing_skills:
            if skill.provenance == FieldProvenance.USER_CONFIRMED:
                diff.potential_conflicts.append(
                    ProfileConflict(
                        category="skill",
                        description=f"'{skill.name}' was manually confirmed but does not appear in the new resume.",
                        existing_provenance=skill.provenance,
                    )
                )
            else:
                diff.removed_resume_derived.append(skill.name)

    stored_work_keys = {_work_key(w.company, w.title): w for w in stored.work_experience}
    new_work_keys = {_work_key(w.company, w.title): w for w in new_candidate.work_experience}
    for key, entry in new_work_keys.items():
        if key not in stored_work_keys:
            diff.new_work_experience.append(f"{entry.title} at {entry.company}")
        else:
            existing = stored_work_keys[key]
            if (existing.description or "") != (entry.description or "") or set(existing.skills_used) != set(
                entry.skills_used
            ):
                diff.changed_work_experience.append(f"{entry.title} at {entry.company}")
    for key, existing in stored_work_keys.items():
        if key not in new_work_keys:
            desc = f"{existing.title} at {existing.company}"
            if existing.provenance == FieldProvenance.USER_CONFIRMED:
                diff.potential_conflicts.append(
                    ProfileConflict(
                        category="work_experience",
                        description=f"'{desc}' was manually confirmed but does not appear in the new resume.",
                        existing_provenance=existing.provenance,
                    )
                )
            else:
                diff.removed_resume_derived.append(desc)

    stored_edu_keys = {_edu_key(e.institution, e.degree) for e in stored.education}
    for entry in new_candidate.education:
        if _edu_key(entry.institution, entry.degree) not in stored_edu_keys:
            diff.new_education.append(f"{entry.degree or 'Degree'} — {entry.institution}")

    stored_cert_names = {c.name.lower() for c in stored.certifications}
    for entry in new_candidate.certifications:
        if entry.name.lower() not in stored_cert_names:
            diff.new_certifications.append(entry.name)

    diff.summary_changed = bool(
        new_candidate.professional_summary
        and new_candidate.professional_summary.strip()
        and new_candidate.professional_summary.strip() != (stored.professional_summary or "").strip()
    )

    return diff


def apply_profile_update(
    stored: CareerProfile,
    new_candidate: CandidateProfile,
    original_filename: str | None = None,
    resume_file_path: str | None = None,
) -> CareerProfile:
    """Applies a previously-previewed resume update to `stored`.

    Additive-first: new skills/work experience/education/certifications are
    appended with RESUME_DERIVED provenance. Existing USER_CONFIRMED items
    that are absent from the new resume are NEVER deleted here — they were
    already surfaced as potential_conflicts by diff_profile_update() for
    human review; deleting them still requires an explicit, separate user
    edit action (not part of a resume merge). RESUME_DERIVED items absent
    from the new resume ARE dropped, since they were themselves only ever
    an unconfirmed extraction from a prior resume.
    """
    new_skill_names = _skill_names(new_candidate.skills)
    kept_skills: list[ProfileSkill] = [
        s
        for s in stored.skills
        if s.name.lower() in new_skill_names or s.provenance == FieldProvenance.USER_CONFIRMED
    ]
    kept_names = {s.name.lower() for s in kept_skills}
    for skill in new_candidate.skills:
        if skill.name.lower() not in kept_names:
            kept_skills.append(
                ProfileSkill(
                    name=skill.name,
                    provenance=FieldProvenance.RESUME_DERIVED,
                    resume_evidence_ids=[e.evidence_id for e in skill.evidence],
                    evidence_summaries=_evidence_summaries_for(skill),
                )
            )
            kept_names.add(skill.name.lower())
    stored.skills = kept_skills

    new_work_keys = {_work_key(w.company, w.title): w for w in new_candidate.work_experience}
    kept_work: list[ProfileWorkExperience] = [
        w
        for w in stored.work_experience
        if _work_key(w.company, w.title) in new_work_keys or w.provenance == FieldProvenance.USER_CONFIRMED
    ]
    kept_work_keys = {_work_key(w.company, w.title) for w in kept_work}
    for key, entry in new_work_keys.items():
        if key in kept_work_keys:
            # Refresh the resume-derived copy in place with the latest text.
            for i, w in enumerate(kept_work):
                if _work_key(w.company, w.title) == key and w.provenance == FieldProvenance.RESUME_DERIVED:
                    kept_work[i] = ProfileWorkExperience(
                        entry_id=w.entry_id,
                        company=entry.company,
                        title=entry.title,
                        start_date=entry.start_date,
                        end_date=entry.end_date,
                        description=entry.description,
                        skills_used=list(entry.skills_used),
                        provenance=FieldProvenance.RESUME_DERIVED,
                    )
        else:
            kept_work.append(
                ProfileWorkExperience(
                    company=entry.company,
                    title=entry.title,
                    start_date=entry.start_date,
                    end_date=entry.end_date,
                    description=entry.description,
                    skills_used=list(entry.skills_used),
                    provenance=FieldProvenance.RESUME_DERIVED,
                )
            )
    stored.work_experience = kept_work

    stored_edu_keys = {_edu_key(e.institution, e.degree): e for e in stored.education}
    for entry in new_candidate.education:
        key = _edu_key(entry.institution, entry.degree)
        if key not in stored_edu_keys:
            stored.education.append(
                ProfileEducation(
                    institution=entry.institution,
                    degree=entry.degree,
                    field_of_study=entry.field_of_study,
                    start_date=entry.start_date,
                    end_date=entry.end_date,
                    provenance=FieldProvenance.RESUME_DERIVED,
                )
            )

    stored_cert_names = {c.name.lower() for c in stored.certifications}
    for entry in new_candidate.certifications:
        if entry.name.lower() not in stored_cert_names:
            stored.certifications.append(
                ProfileCertification(
                    name=entry.name,
                    issuer=entry.issuer,
                    date=entry.date,
                    provenance=FieldProvenance.RESUME_DERIVED,
                )
            )

    stored_proj_names = {p.name.lower() for p in stored.projects}
    for entry in new_candidate.projects:
        if entry.name.lower() not in stored_proj_names:
            stored.projects.append(
                ProfileProject(
                    name=entry.name,
                    description=entry.description,
                    skills_used=list(entry.skills_used),
                    provenance=FieldProvenance.RESUME_DERIVED,
                )
            )

    if new_candidate.professional_summary and new_candidate.professional_summary.strip():
        stored.professional_summary = new_candidate.professional_summary
    if new_candidate.years_experience is not None:
        stored.total_experience_years = new_candidate.years_experience

    stored.resume_source = ResumeSourceInfo(
        original_filename=original_filename,
        uploaded_at=stored.resume_source.uploaded_at,
        parsed_profile_version=stored.resume_source.parsed_profile_version + 1,
        source_candidate_id=new_candidate.candidate_id,
        resume_file_path=resume_file_path if resume_file_path is not None else stored.resume_source.resume_file_path,
    )
    return stored


def new_upload_id() -> str:
    return f"upload-{uuid4().hex[:12]}"
