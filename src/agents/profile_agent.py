"""
Profile Agent.

Turns parsed resume text into a structured CandidateProfile. The LLM call
(via src.llm.provider.LLMClient) only ever produces the intermediate
ExtractedProfileData shape — this agent then:

  1. Normalizes skill names (conservative alias map) while preserving the
     original wording as Evidence.source_text.
  2. Independently recomputes years of experience from parsed employment
     dates (overlap-aware) rather than trusting the model's own estimate.
  3. Drops any entry missing a required identifying field (company/title/
     institution/certification name) instead of inventing one, recording a
     warning.
  4. Hands the result to deterministic post-extraction validation
     (src.services.profile_validation) before returning.

See docs/ARCHITECTURE.md section 7 for this agent's declared boundary.
"""

from __future__ import annotations

from uuid import uuid4

from src.llm.client import LLMClient
from src.llm.schemas import ExtractedProfileData
from src.models.candidate import (
    CandidateProfile,
    Certification,
    Education,
    EmploymentPreferences,
    Project,
    Skill,
    WorkExperience,
)
from src.models.enums import EmploymentType, EvidenceSourceType, WorkMode
from src.models.evidence import Evidence
from src.models.profile_validation import ProfileValidationResult
from src.services.decision_trace import DecisionTrace
from src.services.experience_estimation import estimate_years_experience
from src.services.normalization import normalize_skill
from src.services.profile_validation import validate_profile

_GROUNDING_SYSTEM_PROMPT = """\
You are extracting structured facts from a candidate's resume text. Follow these rules strictly:
- Never invent an employer, job title, date, degree, certification, or skill that is not explicitly \
present in the text.
- If a fact is unclear or ambiguous, omit it or note low confidence rather than guessing.
- For every skill, work experience, project, and certification you extract, include the exact \
source_text excerpt from the resume that supports it.
- years_experience_estimate is a rough hint only; it will be independently verified against parsed \
employment dates, so do not inflate it to compensate for unclear dates.
"""


class ProfilePreferences:
    """Optional user-supplied preferences the resume itself doesn't reliably state."""

    def __init__(
        self,
        target_roles: list[str] | None = None,
        target_locations: list[str] | None = None,
        preferred_work_modes: list[WorkMode] | None = None,
        employment_preferences: EmploymentPreferences | None = None,
    ) -> None:
        self.target_roles = target_roles or []
        self.target_locations = target_locations or []
        self.preferred_work_modes = preferred_work_modes or []
        self.employment_preferences = employment_preferences or EmploymentPreferences()


def _new_evidence_id() -> str:
    return f"ev-{uuid4().hex[:12]}"


class ProfileAgent:
    def __init__(self, llm_client: LLMClient, decision_trace: DecisionTrace | None = None) -> None:
        self.llm_client = llm_client
        self.decision_trace = decision_trace

    def build_profile(
        self,
        resume_text: str,
        candidate_id: str,
        preferences: ProfilePreferences | None = None,
    ) -> tuple[CandidateProfile, ProfileValidationResult]:
        preferences = preferences or ProfilePreferences()

        extracted, _ = self.llm_client.structured_output(
            resume_text, ExtractedProfileData, system=_GROUNDING_SYSTEM_PROMPT
        )

        conversion_warnings: list[str] = []
        skills = self._build_skills(extracted, conversion_warnings)
        work_experience = self._build_work_experience(extracted, conversion_warnings)
        education = self._build_education(extracted, conversion_warnings)
        projects = self._build_projects(extracted, conversion_warnings)
        certifications = self._build_certifications(extracted, conversion_warnings)
        years_experience = self._estimate_years_experience(extracted, conversion_warnings)
        source_evidence = self._build_source_evidence(extracted)

        profile = CandidateProfile(
            candidate_id=candidate_id,
            name=extracted.name or "Unknown Candidate",
            professional_summary=extracted.professional_summary,
            years_experience=years_experience,
            skills=skills,
            target_roles=preferences.target_roles,
            target_locations=preferences.target_locations,
            preferred_work_modes=preferences.preferred_work_modes,
            employment_preferences=preferences.employment_preferences,
            education=education,
            work_experience=work_experience,
            projects=projects,
            certifications=certifications,
            source_evidence=source_evidence,
        )

        validation = validate_profile(profile, conversion_warnings=conversion_warnings)

        if self.decision_trace:
            self.decision_trace.add(
                "profile_agent",
                "build_profile",
                f"Candidate profile created: {len(profile.skills)} skills, "
                f"{len(profile.work_experience)} work experiences, {len(profile.projects)} projects.",
                metadata={"warnings": len(validation.warnings), "errors": len(validation.errors)},
            )

        return profile, validation

    @staticmethod
    def _build_skills(extracted: ExtractedProfileData, warnings: list[str]) -> list[Skill]:
        by_canonical_name: dict[str, Skill] = {}
        for extracted_skill in extracted.skills:
            if not extracted_skill.name.strip():
                continue
            canonical = normalize_skill(extracted_skill.name)
            section = extracted_skill.source_section or "Resume"
            if section.startswith("Work Experience"):
                source_type = EvidenceSourceType.WORK_EXPERIENCE
            elif section.startswith("Project"):
                source_type = EvidenceSourceType.PROJECT
            else:
                source_type = EvidenceSourceType.RESUME
            evidence = Evidence(
                evidence_id=_new_evidence_id(),
                source_type=source_type,
                source_section=section,
                source_text=extracted_skill.source_text or extracted_skill.name,
                normalized_concepts=[canonical],
                confidence=extracted_skill.confidence,
            )
            existing = by_canonical_name.get(canonical)
            if existing:
                existing.evidence.append(evidence)
            else:
                by_canonical_name[canonical] = Skill(name=canonical, evidence=[evidence])
        return list(by_canonical_name.values())

    @staticmethod
    def _build_work_experience(extracted: ExtractedProfileData, warnings: list[str]) -> list[WorkExperience]:
        results = []
        for entry in extracted.work_experience:
            if not entry.company.strip() or not entry.title.strip():
                warnings.append(f"dropped a work experience entry with missing company/title: {entry.source_text[:80]!r}")
                continue
            evidence = [
                Evidence(
                    evidence_id=_new_evidence_id(),
                    source_type=EvidenceSourceType.WORK_EXPERIENCE,
                    source_section=f"Work Experience: {entry.title} at {entry.company}",
                    source_text=entry.source_text or entry.description or entry.title,
                    normalized_concepts=[normalize_skill(s) for s in entry.skills_used],
                    confidence=0.85,
                )
            ]
            results.append(
                WorkExperience(
                    company=entry.company,
                    title=entry.title,
                    start_date=entry.start_date,
                    end_date=entry.end_date,
                    description=entry.description,
                    skills_used=[normalize_skill(s) for s in entry.skills_used],
                    evidence=evidence,
                )
            )
        return results

    @staticmethod
    def _build_education(extracted: ExtractedProfileData, warnings: list[str]) -> list[Education]:
        results = []
        for entry in extracted.education:
            if not entry.institution.strip():
                warnings.append(f"dropped an education entry with missing institution: {entry.source_text[:80]!r}")
                continue
            evidence = [
                Evidence(
                    evidence_id=_new_evidence_id(),
                    source_type=EvidenceSourceType.EDUCATION,
                    source_section=f"Education: {entry.institution}",
                    source_text=entry.source_text or entry.institution,
                    confidence=0.85,
                )
            ]
            results.append(
                Education(
                    institution=entry.institution,
                    degree=entry.degree,
                    field_of_study=entry.field_of_study,
                    start_date=entry.start_date,
                    end_date=entry.end_date,
                    evidence=evidence,
                )
            )
        return results

    @staticmethod
    def _build_projects(extracted: ExtractedProfileData, warnings: list[str]) -> list[Project]:
        results = []
        for entry in extracted.projects:
            if not entry.name.strip():
                warnings.append(f"dropped a project entry with missing name: {entry.source_text[:80]!r}")
                continue
            evidence = [
                Evidence(
                    evidence_id=_new_evidence_id(),
                    source_type=EvidenceSourceType.PROJECT,
                    source_section=f"Project: {entry.name}",
                    source_text=entry.source_text or entry.description or entry.name,
                    normalized_concepts=[normalize_skill(s) for s in entry.skills_used],
                    confidence=0.75,
                )
            ]
            results.append(
                Project(
                    name=entry.name,
                    description=entry.description,
                    skills_used=[normalize_skill(s) for s in entry.skills_used],
                    evidence=evidence,
                )
            )
        return results

    @staticmethod
    def _build_certifications(extracted: ExtractedProfileData, warnings: list[str]) -> list[Certification]:
        results = []
        for entry in extracted.certifications:
            if not entry.name.strip():
                warnings.append("dropped a certification entry with no discernible title")
                continue
            evidence = [
                Evidence(
                    evidence_id=_new_evidence_id(),
                    source_type=EvidenceSourceType.CERTIFICATION,
                    source_section="Certifications",
                    source_text=entry.source_text or entry.name,
                    confidence=entry.confidence,
                )
            ]
            results.append(
                Certification(
                    name=entry.name,
                    issuer=entry.issuer,
                    date=entry.date,
                    evidence=evidence,
                )
            )
        return results

    @staticmethod
    def _estimate_years_experience(extracted: ExtractedProfileData, warnings: list[str]) -> float:
        ranges = [
            (entry.start_date, entry.end_date)
            for entry in extracted.work_experience
            if entry.company.strip() and entry.title.strip()
        ]
        deterministic_years, exp_warnings = estimate_years_experience(ranges)
        warnings.extend(exp_warnings)

        if deterministic_years is not None:
            llm_estimate = extracted.years_experience_estimate
            if llm_estimate is not None and llm_estimate > deterministic_years + 0.5:
                warnings.append(
                    f"model-suggested years of experience ({llm_estimate}) exceeded the conservative, "
                    f"overlap-aware timeline estimate ({deterministic_years}); using the conservative estimate"
                )
            return deterministic_years

        if extracted.years_experience_estimate is not None:
            warnings.append(
                "years of experience could not be grounded in parsed employment dates; "
                "using the model's unverified estimate"
            )
            return max(0.0, extracted.years_experience_estimate)

        warnings.append("no employment history evidence found; defaulting years of experience to 0")
        return 0.0

    @staticmethod
    def _build_source_evidence(extracted: ExtractedProfileData) -> list[Evidence]:
        if not extracted.name:
            return []
        return [
            Evidence(
                evidence_id=_new_evidence_id(),
                source_type=EvidenceSourceType.RESUME,
                source_section="Header",
                source_text=extracted.name,
                confidence=0.95,
            )
        ]
