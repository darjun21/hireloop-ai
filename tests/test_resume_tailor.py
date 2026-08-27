from src.agents.resume_tailor import ResumeTailorAgent
from src.llm.client import LLMClient
from src.llm.mock_provider import MockLLMProvider
from src.models.evidence_retrieval import EvidenceStrength, RequirementEvidence, RetrievalSource
from src.models.resume_modification import ResumeModification
from tests.factories import build_candidate, build_job


# 9. Resume Tailor structured output.
def test_tailor_returns_structured_modifications_only():
    candidate = build_candidate()
    job = build_job(required_skills=["Python", "Machine Learning"], preferred_skills=[])
    agent = ResumeTailorAgent(LLMClient(primary=MockLLMProvider()))

    modifications = agent.propose_modifications(candidate, job)

    assert modifications
    assert all(isinstance(m, ResumeModification) for m in modifications)
    for m in modifications:
        assert m.modification_id
        assert m.section
        assert m.proposed_text
        assert isinstance(m.supporting_evidence_ids, list)
        assert 0.0 <= m.confidence <= 1.0


def test_tailor_never_touches_experience_years_requirement():
    candidate = build_candidate()
    job = build_job(required_skills=["Python"], minimum_years_experience=5)
    agent = ResumeTailorAgent(LLMClient(primary=MockLLMProvider()))

    modifications = agent.propose_modifications(candidate, job)

    assert not any("years experience" in (m.targeted_job_requirement or "").lower() for m in modifications)


def test_tailor_populates_supporting_evidence_ids_from_requirement_evidence():
    candidate = build_candidate()
    job = build_job(required_skills=["Python"], preferred_skills=[])
    requirement_evidence = {
        "Python": RequirementEvidence(
            requirement="Python",
            matched_evidence_ids=["ev-1", "ev-2"],
            evidence_strength=EvidenceStrength.STRONG,
            retrieval_source=RetrievalSource.DIRECT_PROFILE_MATCH,
            confidence=0.9,
        )
    }
    agent = ResumeTailorAgent(LLMClient(primary=MockLLMProvider()))

    modifications = agent.propose_modifications(candidate, job, requirement_evidence)

    python_mod = next(m for m in modifications if m.targeted_job_requirement == "Python")
    assert python_mod.supporting_evidence_ids == ["ev-1", "ev-2"]


def test_tailor_proposes_overreaching_claim_for_unevidenced_requirement():
    """The mock deliberately proposes a confident-sounding claim even when
    the candidate lacks the skill -- Truth Guard, not the Tailor, is the
    safety net (see docs/TRUTH_GUARD.md)."""
    candidate = build_candidate(skills=[])
    job = build_job(required_skills=["Kubernetes"], preferred_skills=[])
    agent = ResumeTailorAgent(LLMClient(primary=MockLLMProvider()))

    modifications = agent.propose_modifications(candidate, job)

    assert any("Kubernetes" in m.proposed_text for m in modifications)
