from src.agents.profile_agent import ProfileAgent, ProfilePreferences
from src.llm.client import LLMClient
from src.llm.mock_provider import MockLLMProvider
from tests.resume_fixtures import (
    LANGCHAIN_SKILLS,
    NO_KUBERNETES,
    OVERLAPPING_DATES,
    SKILL_ALIASES_RESUME,
    SKILL_ONLY_IN_PROJECT,
    UNCLEAR_CERTIFICATION,
    WELL_STRUCTURED_ENGINEER,
)


def _agent() -> ProfileAgent:
    return ProfileAgent(LLMClient(primary=MockLLMProvider()))


def _skill_names(profile) -> set[str]:
    return {s.name for s in profile.skills}


# A. Well-structured resume produces a coherent, evidence-backed profile.
def test_well_structured_resume_produces_complete_profile():
    profile, validation = _agent().build_profile(WELL_STRUCTURED_ENGINEER, candidate_id="cand-a")

    assert profile.name == "Jane Doe"
    assert len(profile.work_experience) == 2
    assert len(profile.education) == 1
    assert len(profile.projects) == 1
    assert len(profile.certifications) == 1
    assert validation.valid is True
    assert all(skill.evidence for skill in profile.skills)


# B. "Python, LangChain, AWS" must all be extracted.
def test_explicit_skill_list_is_extracted():
    profile, _ = _agent().build_profile(LANGCHAIN_SKILLS, candidate_id="cand-b")

    assert {"Python", "LangChain", "AWS"} <= _skill_names(profile)


# C. Kubernetes must never appear just because the role is AI-adjacent.
def test_kubernetes_never_invented_for_ai_adjacent_role():
    profile, _ = _agent().build_profile(NO_KUBERNETES, candidate_id="cand-c")

    assert "Kubernetes" not in _skill_names(profile)
    assert _skill_names(profile) == {"Python", "TensorFlow"}


# D. Overlapping employment dates must not be blindly summed.
def test_overlapping_employment_dates_yield_conservative_years():
    profile, validation = _agent().build_profile(OVERLAPPING_DATES, candidate_id="cand-d")

    # Two roles span 2018-01..2022-01 with full overlap in the middle; the
    # naive (double-counted) sum would be 6.0 years. The merged timeline is 4.0.
    assert profile.years_experience == 4.0
    assert any("conservative" in w for w in validation.warnings)


# E. An unclear certification produces uncertainty, not fabrication.
def test_unclear_certification_is_low_confidence_not_fabricated():
    profile, validation = _agent().build_profile(UNCLEAR_CERTIFICATION, candidate_id="cand-e")

    assert len(profile.certifications) == 1
    cert = profile.certifications[0]
    assert cert.name  # preserved verbatim, not fabricated into a clean title
    assert all(e.confidence < 0.5 for e in cert.evidence)
    assert any("low_confidence_certification" in w for w in validation.warnings)


# F. A skill appearing only in a project must have evidence pointing there.
def test_skill_only_in_project_has_project_evidence():
    profile, _ = _agent().build_profile(SKILL_ONLY_IN_PROJECT, candidate_id="cand-f")

    kafka = next(s for s in profile.skills if s.name == "Kafka")
    assert any("Project" in e.source_section for e in kafka.evidence)
    assert not any("Skills" == e.source_section for e in kafka.evidence)


# G. Aliases normalize while preserving what the resume actually said.
def test_skill_aliases_normalize_but_preserve_original_evidence_text():
    profile, _ = _agent().build_profile(SKILL_ALIASES_RESUME, candidate_id="cand-g")

    assert {"PostgreSQL", "JavaScript", "Kubernetes"} <= _skill_names(profile)
    postgres_skill = next(s for s in profile.skills if s.name == "PostgreSQL")
    assert "Postgres" in postgres_skill.evidence[0].source_text


def test_never_fabricates_employer_when_none_present():
    resume = "No Employer Person\nSKILLS\nPython\n"
    profile, _ = _agent().build_profile(resume, candidate_id="cand-h")

    assert profile.work_experience == []


def test_preferences_are_applied_but_not_extracted_from_resume():
    from src.models.enums import WorkMode

    prefs = ProfilePreferences(target_roles=["AI Engineer"], preferred_work_modes=[WorkMode.REMOTE])
    profile, _ = _agent().build_profile(WELL_STRUCTURED_ENGINEER, candidate_id="cand-i", preferences=prefs)

    assert profile.target_roles == ["AI Engineer"]
    assert profile.preferred_work_modes == [WorkMode.REMOTE]


def test_decision_trace_records_profile_creation_without_dumping_resume():
    from src.services.decision_trace import DecisionTrace

    trace = DecisionTrace()
    agent = ProfileAgent(LLMClient(primary=MockLLMProvider()), decision_trace=trace)

    agent.build_profile(WELL_STRUCTURED_ENGINEER, candidate_id="cand-j")

    assert len(trace.events) == 1
    message = trace.events[0].message
    assert "Candidate profile created" in message
    assert WELL_STRUCTURED_ENGINEER not in message
    assert len(message) < 200
