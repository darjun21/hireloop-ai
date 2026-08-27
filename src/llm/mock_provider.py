"""
Deterministic mock LLM provider.

Used for local development, CI, and as a DEMO_MODE fallback when no real
provider is configured. It never makes a network call and never returns a
canned response regardless of input — for the two structured-output shapes
HireLoop actually needs (resume extraction and match analysis) it performs
real, input-dependent, deterministic parsing so tests are meaningful.

Its output must never be presented to a user as if it came from a live
model — callers can check `LLMResult.provider == "mock"` to detect this.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Callable

from pydantic import BaseModel

from src.llm.base import LLMProvider, LLMResult, SchemaT
from src.llm.errors import HireLoopLLMError, LLMErrorType
from src.llm.schemas import (
    ExtractedCertification,
    ExtractedEducation,
    ExtractedProfileData,
    ExtractedProject,
    ExtractedSkill,
    ExtractedWorkExperience,
    CandidateInsightLLM,
    LearningAgentLLMOutput,
    ProposedModificationLLM,
    TailorLLMOutput,
    TruthGuardLLMOutput,
    MatchAnalysisLLMOutput,
)
from src.models.enums import ConfidenceLevel, TruthGuardStatus
from src.services.normalization import normalize_skill, normalize_whitespace

_SECTION_HEADERS = {
    "skills": "skills",
    "work experience": "work_experience",
    "experience": "work_experience",
    "education": "education",
    "projects": "projects",
    "certifications": "certifications",
}

# A small curated vocabulary the mock resume parser can recognize inside
# freeform description text (project/work-experience bullet points).
_KNOWN_SKILL_KEYWORDS = [
    "Python",
    "JavaScript",
    "TypeScript",
    "Java",
    "Go",
    "Rust",
    "SQL",
    "PostgreSQL",
    "MySQL",
    "MongoDB",
    "AWS",
    "Azure",
    "GCP",
    "Docker",
    "Kubernetes",
    "Kafka",
    "React",
    "Node",
    "Django",
    "Flask",
    "Machine Learning",
    "TensorFlow",
    "PyTorch",
    "LangChain",
    "Spark",
    "Terraform",
]


def _extract_known_skills_from_text(text: str) -> list[str]:
    found = []
    for keyword in _KNOWN_SKILL_KEYWORDS:
        if re.search(rf"\b{re.escape(keyword)}\b", text, flags=re.IGNORECASE):
            found.append(keyword)
    return found


def _split_sections(text: str) -> tuple[str, str, dict[str, list[str]]]:
    """Returns (name, professional_summary, {section_key: [lines...]})."""
    lines = [line.rstrip() for line in text.splitlines()]
    sections: dict[str, list[str]] = {}
    current_key: str | None = None
    preamble: list[str] = []

    for line in lines:
        header_key = _SECTION_HEADERS.get(line.strip().lower())
        if header_key is not None:
            current_key = header_key
            sections.setdefault(current_key, [])
            continue
        if current_key is None:
            preamble.append(line)
        else:
            sections[current_key].append(line)

    preamble_nonblank = [l for l in preamble if l.strip()]
    name = preamble_nonblank[0].strip() if preamble_nonblank else None
    summary = " ".join(l.strip() for l in preamble_nonblank[1:]) if len(preamble_nonblank) > 1 else ""
    return name, summary, sections


def _group_by_blank_lines(lines: list[str]) -> list[list[str]]:
    groups: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if not line.strip():
            if current:
                groups.append(current)
                current = []
        else:
            current.append(line)
    if current:
        groups.append(current)
    return groups


def _parse_pipe_line(line: str, field_names: tuple[str, ...]) -> dict[str, str]:
    parts = [p.strip() for p in line.split("|")]
    result = {name: "" for name in field_names}
    for name, value in zip(field_names, parts):
        result[name] = value
    return result


def _parse_date_range(raw: str) -> tuple[str | None, str | None]:
    """Split a "2019-01 - 2022-06" style range on the ' - ' separator
    (spaces required) so it doesn't collide with hyphens inside the dates
    themselves."""
    if " - " not in raw:
        return None, None
    start, _, end = raw.partition(" - ")
    return start.strip() or None, end.strip() or None


def _naive_duration_years(start: str | None, end: str | None) -> float:
    """Naive (overlap-blind) duration estimate, used only to simulate an
    LLM's optimistic-but-ungrounded raw guess. The Profile Agent recomputes
    a proper overlap-aware figure and does not trust this number as-is."""
    start_d = _parse_loose_date(start)
    end_d = _parse_loose_date(end) or date.today()
    if start_d is None:
        return 0.0
    return max(0.0, (end_d - start_d).days / 365.25)


def _parse_loose_date(value: str | None) -> date | None:
    if not value:
        return None
    v = value.strip()
    if v.lower() in {"present", "current", "now"}:
        return date.today()
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            return datetime.strptime(v, fmt).date()
        except ValueError:
            continue
    return None


def _build_extracted_profile(resume_text: str) -> ExtractedProfileData:
    name, summary, sections = _split_sections(resume_text)

    skills: list[ExtractedSkill] = []
    for raw_line in sections.get("skills", []):
        for token in raw_line.split(","):
            token = token.strip()
            if token:
                skills.append(
                    ExtractedSkill(
                        name=token,
                        source_text=raw_line.strip(),
                        source_section="Skills",
                        confidence=0.9,
                    )
                )

    work_experience: list[ExtractedWorkExperience] = []
    naive_years_total = 0.0
    for group in _group_by_blank_lines(sections.get("work_experience", [])):
        header = _parse_pipe_line(group[0], ("title", "company", "dates"))
        start, end = _parse_date_range(header["dates"])
        description = " ".join(l.strip() for l in group[1:]).strip() or None
        used_skills = _extract_known_skills_from_text(description or "")
        for skill_name in used_skills:
            skills.append(
                ExtractedSkill(
                    name=skill_name,
                    source_text=description or "",
                    source_section=f"Work Experience: {header['title']} at {header['company']}",
                    confidence=0.75,
                )
            )
        work_experience.append(
            ExtractedWorkExperience(
                company=header["company"],
                title=header["title"],
                start_date=start,
                end_date=end,
                description=description,
                skills_used=used_skills,
                source_text="\n".join(group),
            )
        )
        naive_years_total += _naive_duration_years(start, end)

    education: list[ExtractedEducation] = []
    for group in _group_by_blank_lines(sections.get("education", [])):
        header = _parse_pipe_line(group[0], ("degree", "institution", "dates"))
        start, end = _parse_date_range(header["dates"])
        education.append(
            ExtractedEducation(
                institution=header["institution"],
                degree=header["degree"],
                field_of_study=None,
                start_date=start,
                end_date=end,
                source_text="\n".join(group),
            )
        )

    projects: list[ExtractedProject] = []
    for group in _group_by_blank_lines(sections.get("projects", [])):
        proj_name = group[0].strip()
        description = " ".join(l.strip() for l in group[1:]).strip() or None
        used_skills = _extract_known_skills_from_text(description or "")
        for skill_name in used_skills:
            skills.append(
                ExtractedSkill(
                    name=skill_name,
                    source_text=description or "",
                    source_section=f"Project: {proj_name}",
                    confidence=0.7,
                )
            )
        projects.append(
            ExtractedProject(
                name=proj_name,
                description=description,
                skills_used=used_skills,
                source_text="\n".join(group),
            )
        )

    certifications: list[ExtractedCertification] = []
    for raw_line in sections.get("certifications", []):
        if not raw_line.strip():
            continue
        if raw_line.count("|") >= 2:
            header = _parse_pipe_line(raw_line, ("name", "issuer", "date"))
            certifications.append(
                ExtractedCertification(
                    name=header["name"],
                    issuer=header["issuer"] or None,
                    date=header["date"] or None,
                    confidence=0.9,
                    source_text=raw_line.strip(),
                )
            )
        else:
            # Doesn't match the well-formed pattern -- low confidence,
            # preserved as-is rather than guessed at.
            certifications.append(
                ExtractedCertification(
                    name=normalize_whitespace(raw_line),
                    issuer=None,
                    date=None,
                    confidence=0.3,
                    source_text=raw_line.strip(),
                )
            )

    return ExtractedProfileData(
        name=name,
        professional_summary=summary,
        years_experience_estimate=round(naive_years_total, 1) if work_experience else None,
        skills=skills,
        work_experience=work_experience,
        education=education,
        projects=projects,
        certifications=certifications,
    )


def _generate_match_analysis(context_json: str) -> MatchAnalysisLLMOutput:
    import json

    context = json.loads(context_json)

    def _canonical_map(raw_names: list[str]) -> dict[str, str]:
        return {normalize_skill(name).lower(): normalize_skill(name) for name in raw_names}

    candidate_map = _canonical_map(context.get("candidate_skills", []))
    required_map = _canonical_map(context.get("job_required_skills", []))
    preferred_map = _canonical_map(context.get("job_preferred_skills", []))

    candidate_skills = set(candidate_map)
    required = set(required_map)
    preferred = set(preferred_map)

    matched_required = sorted(required_map[k] for k in required & candidate_skills)
    missing_required = sorted(required_map[k] for k in required - candidate_skills)
    matched_preferred = sorted(preferred_map[k] for k in preferred & candidate_skills)

    strengths = [f"Candidate has {skill} experience matching a required skill." for skill in matched_required]
    strengths += [f"Candidate has {skill}, a preferred skill for this role." for skill in matched_preferred]
    gaps = [f"{skill} is requested but no evidence exists in the candidate profile." for skill in missing_required]

    risks = []
    min_years = context.get("job_minimum_years_experience")
    candidate_years = context.get("candidate_years_experience", 0)
    if min_years is not None and candidate_years < min_years:
        risks.append(
            f"The role asks for {min_years}+ years of experience while candidate evidence supports "
            f"{candidate_years} years."
        )

    final_score = context.get("final_score", 0)
    recommendation = context.get("recommendation", "")
    explanation_parts = [f"Opportunity score {final_score:.1f} ({recommendation})."]
    if strengths:
        explanation_parts.append(strengths[0])
    if gaps:
        explanation_parts.append(gaps[0])
    explanation = " ".join(explanation_parts)

    confidence_str = context.get("score_confidence", "MEDIUM")
    try:
        confidence = ConfidenceLevel(confidence_str)
    except ValueError:
        confidence = ConfidenceLevel.MEDIUM

    return MatchAnalysisLLMOutput(
        strengths=strengths,
        gaps=gaps,
        risks=risks,
        explanation=explanation,
        confidence=confidence,
    )


_MAX_MOCK_TAILOR_MODIFICATIONS = 6


def _generate_tailor_output(context_json: str) -> TailorLLMOutput:
    """Proposes a modification per job requirement: a grounded rewording
    when the candidate's skill list already contains it, or a deliberately
    confident-sounding (and possibly ungrounded) claim when it doesn't --
    a realistic simulation of an imperfect LLM. Truth Guard, not the
    Tailor, is what's supposed to catch the latter."""
    import json

    context = json.loads(context_json)
    candidate_skills = {normalize_skill(s).lower() for s in context.get("candidate_skills", [])}
    requirements = context.get("job_requirements", [])[: _MAX_MOCK_TAILOR_MODIFICATIONS]

    modifications = []
    for requirement in requirements:
        canonical = normalize_skill(requirement)
        if "+ years experience" in requirement.lower():
            continue  # Tailor must never touch experience/date claims
        if canonical.lower() in candidate_skills:
            proposed_text = f"Applied {canonical} to build and ship production features."
            reason = f"Candidate has evidenced {canonical} experience relevant to this requirement."
        else:
            proposed_text = f"Deployed production workloads using {canonical}."
            reason = f"Job requires {canonical}; highlighting relevant experience."
        modifications.append(
            ProposedModificationLLM(
                section="Professional Summary",
                proposed_text=proposed_text,
                reason=reason,
                targeted_job_requirement=requirement,
                claim=proposed_text,
            )
        )
    return TailorLLMOutput(modifications=modifications)


def _generate_truth_guard_semantic_judgment(context_json: str) -> TruthGuardLLMOutput:
    """Deterministic stand-in for the LLM's semantic-ambiguity judgment
    (src/agents/truth_guard.py's Layer 2). Conservative by design: a
    skills-only fragment (no work/project evidence) is judged
    NEEDS_HUMAN_CONFIRMATION; a fragment with real work/project evidence
    but stronger wording than the source is judged PARTIALLY_SUPPORTED
    with a safe rewrite reverting to the neutral evidence wording. This
    mirrors -- and is deliberately no more lenient than -- Truth Guard's
    own deterministic fallback, so the mock never produces a result an
    equivalent real LLM call couldn't also justify.
    """
    import json

    context = json.loads(context_json)
    fragments = context.get("ambiguous_fragments", [])

    supported, unsupported, evidence_ids = [], [], []
    worst = TruthGuardStatus.VERIFIED
    order = {
        TruthGuardStatus.VERIFIED: 0,
        TruthGuardStatus.PARTIALLY_SUPPORTED: 1,
        TruthGuardStatus.NEEDS_HUMAN_CONFIRMATION: 2,
        TruthGuardStatus.UNSUPPORTED: 3,
    }
    safe_rewrite_parts = []

    for fragment in fragments:
        skill = fragment.get("skill", "")
        has_evidence = bool(fragment.get("has_work_or_project_evidence"))
        if has_evidence:
            unsupported.append(skill)
            safe_rewrite_parts.append(skill)
            status = TruthGuardStatus.PARTIALLY_SUPPORTED
        else:
            unsupported.append(skill)
            status = TruthGuardStatus.NEEDS_HUMAN_CONFIRMATION
        if order[status] > order[worst]:
            worst = status

    explanation = (
        "Semantic review: wording claims more than the source evidence literally states for "
        f"{', '.join(f.get('skill', '') for f in fragments) or 'the reviewed fragment(s)'}."
    )
    safe_rewrite = f"Worked with {', '.join(safe_rewrite_parts)}." if safe_rewrite_parts else None

    return TruthGuardLLMOutput(
        status=worst,
        explanation=explanation,
        supported_fragments=supported,
        unsupported_fragments=unsupported,
        evidence_ids=evidence_ids,
        suggested_safe_rewrite=safe_rewrite,
        confidence=0.6,
    )


def _generate_learning_insights(context_json: str) -> LearningAgentLLMOutput:
    """Deterministic stand-in for the Learning Agent's interpretive pass.
    Picks the group with the highest interview_rate vs. the group with the
    lowest (both with actual data) and proposes ONE comparative,
    analytics-grounded insight. Numbers cited are read straight from the
    provided analytics, so this always passes
    src/services/learning_insight_validation.py's numeric-grounding check
    -- exactly what an equivalent well-behaved real LLM call should do.
    """
    import json

    context = json.loads(context_json)
    groups: dict = context.get("groups", {})
    category = context.get("category", "ROLE_FAMILY")

    candidates = [(key, value) for key, value in groups.items() if value.get("sample_size", 0) > 0]
    if len(candidates) < 2:
        return LearningAgentLLMOutput(insights=[])

    candidates.sort(key=lambda kv: kv[1]["interview_rate"], reverse=True)
    best_key, best = candidates[0]
    worst_key, worst = candidates[-1]
    if best_key == worst_key:
        return LearningAgentLLMOutput(insights=[])

    # Actionability (is this difference even worth mentioning) is decided
    # deterministically downstream (src/services/actionability.py), not by
    # this mock -- it always proposes the comparison; the analytics layer
    # decides how much weight the wording should carry.
    observation = (
        f"{best_key} applications have generated a {best['interview_rate'] * 100:.1f}% interview rate "
        f"compared with {worst['interview_rate'] * 100:.1f}% for {worst_key}."
    )
    recommendation = f"Continue prioritizing {best_key} opportunities while collecting more data."

    return LearningAgentLLMOutput(
        insights=[
            CandidateInsightLLM(
                category=category,
                referenced_group=best_key,
                compared_group=worst_key,
                observation=observation,
                recommendation=recommendation,
            )
        ]
    )


_GENERATORS: dict[type, Callable[[str], BaseModel]] = {
    ExtractedProfileData: _build_extracted_profile,
    MatchAnalysisLLMOutput: _generate_match_analysis,
    TailorLLMOutput: _generate_tailor_output,
    TruthGuardLLMOutput: _generate_truth_guard_semantic_judgment,
    LearningAgentLLMOutput: _generate_learning_insights,
}


class MockLLMProvider(LLMProvider):
    name = "mock"

    def invoke(self, prompt: str, *, system: str | None = None, temperature: float = 0.0) -> LLMResult:
        return LLMResult(text=f"[mock response for {len(prompt)}-char prompt]", provider=self.name, model="mock-echo")

    def structured_output(
        self,
        prompt: str,
        schema: type[SchemaT],
        *,
        system: str | None = None,
        temperature: float = 0.0,
    ) -> tuple[SchemaT, LLMResult]:
        generator = _GENERATORS.get(schema)
        if generator is None:
            raise HireLoopLLMError(
                LLMErrorType.MALFORMED_RESPONSE,
                f"MockLLMProvider has no deterministic generator registered for schema {schema.__name__}",
                provider=self.name,
            )
        instance = generator(prompt)
        result = LLMResult(text=instance.model_dump_json(), provider=self.name, model="mock-deterministic")
        return instance, result

    def health_check(self) -> bool:
        return True
