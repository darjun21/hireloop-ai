"""
Truth Guard adversarial test suite (Recovery Steps 4-6, 18; Phase 4 Parts
H/J/K). No real network calls -- fail-closed tests use ScriptedProvider,
post-validation-cap tests use a scripted "always says VERIFIED" adversarial
provider.
"""

from src.llm.client import LLMClient
from src.llm.errors import LLMErrorType
from src.llm.provider import get_llm_client
from src.llm.schemas import TruthGuardLLMOutput
from src.config.settings import Settings
from src.models.candidate import CandidateProfile, Skill, WorkExperience
from src.models.enums import EvidenceSourceType as ST, TruthGuardStatus
from src.models.evidence import Evidence
from src.models.resume_modification import ResumeModification
from src.agents.truth_guard import classify_modification
from tests.fakes import ScriptedProvider


def _ev(eid, section, text, stype=ST.RESUME, conf=0.85):
    return Evidence(evidence_id=eid, source_type=stype, source_section=section, source_text=text, confidence=conf)


def _rich_profile() -> CandidateProfile:
    return CandidateProfile(
        candidate_id="cand-tg",
        name="Jane Doe",
        years_experience=5,
        skills=[
            Skill(name="Python", evidence=[_ev("e-py", "Work Experience: Software Engineer at Acme", "Used Python daily.", ST.WORK_EXPERIENCE)]),
            Skill(name="Docker", evidence=[_ev("e-docker", "Work Experience: Software Engineer at Acme", "Worked with Docker containers.", ST.WORK_EXPERIENCE)]),
            Skill(name="PostgreSQL", evidence=[_ev("e-pg", "Work Experience: Software Engineer at Acme", "Used PostgreSQL for storage.", ST.WORK_EXPERIENCE)]),
            Skill(name="AWS", evidence=[_ev("e-aws", "Skills", "Python, AWS, Docker", ST.RESUME)]),
            Skill(name="LangChain", evidence=[_ev("e-lc", "Project: RAG Pipeline", "Built a RAG pipeline using LangChain and Python.", ST.PROJECT)]),
            Skill(name="RAG", evidence=[_ev("e-rag", "Project: RAG Pipeline", "Built a RAG pipeline using LangChain and Python.", ST.PROJECT)]),
        ],
        work_experience=[
            WorkExperience(
                company="Acme",
                title="Software Engineer",
                evidence=[_ev("e-title", "Work Experience: Software Engineer at Acme", "Software Engineer role.", ST.WORK_EXPERIENCE)],
            )
        ],
    )


def _pool(profile: CandidateProfile) -> list[Evidence]:
    pool = []
    for skill in profile.skills:
        pool.extend(skill.evidence)
    for exp in profile.work_experience:
        pool.extend(exp.evidence)
    return pool


def _mod(text: str, section: str = "Professional Summary", original_text: str | None = None) -> ResumeModification:
    return ResumeModification(modification_id="mod-test", section=section, proposed_text=text, claim=text, original_text=original_text)


def _mock_client() -> LLMClient:
    return get_llm_client(Settings(default_llm_provider="mock"))


# 10. Unsupported technology rejected.
def test_unsupported_technology_kubernetes_is_rejected():
    profile = _rich_profile()
    result = classify_modification(_mod("Deployed Kubernetes production workloads."), profile, _pool(profile), llm_client=_mock_client())

    assert result.status == TruthGuardStatus.UNSUPPORTED
    assert "Kubernetes" in result.unsupported_fragments


# 7. Docker does not prove Kubernetes (mixed claim).
def test_docker_evidence_does_not_prove_kubernetes_in_mixed_claim():
    profile = _rich_profile()
    result = classify_modification(
        _mod("Built Docker and Kubernetes container platforms."), profile, _pool(profile), llm_client=_mock_client()
    )

    assert result.status == TruthGuardStatus.UNSUPPORTED
    assert "Kubernetes" in result.unsupported_fragments
    assert "Docker" not in result.unsupported_fragments


# 11. Unsupported metric rejected.
def test_unsupported_numeric_claim_is_rejected():
    profile = _rich_profile()
    result = classify_modification(_mod("Improved application performance by 35%."), profile, _pool(profile), llm_client=_mock_client())

    assert result.status == TruthGuardStatus.UNSUPPORTED
    assert any("35%" in f for f in result.unsupported_fragments)


def test_numeric_claim_supported_by_original_text_passes():
    profile = _rich_profile()
    mod = _mod("Improved application performance by 35%.", original_text="Improved application performance by 35% last quarter.")
    result = classify_modification(mod, profile, _pool(profile), llm_client=_mock_client())

    assert not any("35%" in f for f in result.unsupported_fragments)


# 12. Job-title inflation rejected.
def test_job_title_inflation_is_rejected():
    profile = _rich_profile()
    result = classify_modification(_mod("Senior AI Engineer", section="Title"), profile, _pool(profile), llm_client=_mock_client())

    assert result.status == TruthGuardStatus.UNSUPPORTED


def test_job_title_matching_evidence_is_verified():
    profile = _rich_profile()
    result = classify_modification(_mod("Software Engineer", section="Title"), profile, _pool(profile), llm_client=_mock_client())

    assert result.status == TruthGuardStatus.VERIFIED


# 13. PostgreSQL wording inflation -> partially supported.
def test_postgres_wording_inflation_is_partially_supported():
    profile = _rich_profile()
    result = classify_modification(_mod("Designed PostgreSQL-backed services."), profile, _pool(profile), llm_client=_mock_client())

    assert result.status == TruthGuardStatus.PARTIALLY_SUPPORTED


# 14. AWS architecture wording (skills-only evidence) is never falsely VERIFIED.
def test_aws_architecture_wording_with_skills_only_evidence_is_not_verified():
    profile = _rich_profile()
    result = classify_modification(_mod("Architected large-scale AWS infrastructure."), profile, _pool(profile), llm_client=_mock_client())

    assert result.status != TruthGuardStatus.VERIFIED
    assert result.status == TruthGuardStatus.NEEDS_HUMAN_CONFIRMATION


# 15. Verified RAG claim.
def test_fully_evidenced_rag_claim_is_verified():
    profile = _rich_profile()
    result = classify_modification(
        _mod("Built a RAG pipeline using LangChain and Python."), profile, _pool(profile), llm_client=_mock_client()
    )

    assert result.status == TruthGuardStatus.VERIFIED
    assert result.unsupported_fragments == []


# 16. Mixed claim identifies unsupported fragments explicitly.
def test_mixed_claim_never_marks_whole_sentence_verified_when_one_fragment_fails():
    profile = _rich_profile()
    result = classify_modification(
        _mod("Built LangChain RAG systems and deployed them on Kubernetes, reducing latency by 40%."),
        profile,
        _pool(profile),
        llm_client=_mock_client(),
    )

    assert result.status == TruthGuardStatus.UNSUPPORTED
    assert "Kubernetes" in result.unsupported_fragments
    assert any("40%" in f for f in result.unsupported_fragments)


# 25. Safe rewrite selection.
def test_safe_rewrite_falls_back_to_original_text_when_available():
    profile = _rich_profile()
    mod = _mod("Designed PostgreSQL-backed services.", original_text="Used PostgreSQL for backend storage.")
    result = classify_modification(mod, profile, _pool(profile), llm_client=_mock_client())

    assert result.suggested_safe_rewrite == "Used PostgreSQL for backend storage."


def test_safe_rewrite_builds_from_verified_fragments_when_no_original_text():
    profile = _rich_profile()
    result = classify_modification(_mod("Deployed Kubernetes production workloads."), profile, _pool(profile), llm_client=_mock_client())

    # No original_text and no verified skills in this claim -- nothing safe to fall back to.
    assert result.suggested_safe_rewrite is None


# 17. Deterministic UNSUPPORTED cannot be upgraded by an adversarial LLM.
def test_deterministic_unsupported_survives_adversarial_llm():
    profile = _rich_profile()
    adversarial_output = TruthGuardLLMOutput(status=TruthGuardStatus.VERIFIED, explanation="trust me", confidence=0.99)
    provider = ScriptedProvider("adversarial", [lambda: adversarial_output] * 3)
    client = LLMClient(primary=provider)

    result = classify_modification(_mod("Deployed Kubernetes production workloads."), profile, _pool(profile), llm_client=client)

    assert result.status == TruthGuardStatus.UNSUPPORTED
    assert provider.call_count == 0  # hard UNSUPPORTED never even consults the LLM


def test_post_validation_cap_blocks_skills_only_claim_from_becoming_verified():
    profile = _rich_profile()
    adversarial_output = TruthGuardLLMOutput(status=TruthGuardStatus.VERIFIED, explanation="trust me", confidence=0.99)
    provider = ScriptedProvider("adversarial", [lambda: adversarial_output])
    client = LLMClient(primary=provider)

    result = classify_modification(_mod("Architected large-scale AWS infrastructure."), profile, _pool(profile), llm_client=client)

    assert result.status != TruthGuardStatus.VERIFIED


# 18. Truth Guard LLM failure fails closed.
def test_llm_failure_during_semantic_review_fails_closed_not_verified():
    profile = _rich_profile()
    provider = ScriptedProvider("failing", [LLMErrorType.AUTH_ERROR])
    client = LLMClient(primary=provider)

    result = classify_modification(_mod("Designed PostgreSQL-backed services."), profile, _pool(profile), llm_client=client)

    assert result.status != TruthGuardStatus.VERIFIED
    assert result.status == TruthGuardStatus.NEEDS_HUMAN_CONFIRMATION


def test_no_llm_configured_falls_back_to_deterministic_ambiguous_rules():
    profile = _rich_profile()
    result = classify_modification(_mod("Designed PostgreSQL-backed services."), profile, _pool(profile), llm_client=None)

    assert result.status == TruthGuardStatus.PARTIALLY_SUPPORTED


def test_absent_skill_entirely_is_unsupported():
    profile = _rich_profile()
    result = classify_modification(_mod("Expert in Terraform infrastructure automation."), profile, _pool(profile), llm_client=_mock_client())

    assert result.status == TruthGuardStatus.UNSUPPORTED
    assert "Terraform" in result.unsupported_fragments


def test_truth_guard_never_reuses_tailor_reason_as_evidence():
    """A ResumeModification's `reason` field (the Tailor's own untrusted
    justification) must never influence the verdict -- only real Evidence
    records may."""
    profile = _rich_profile()
    mod = ResumeModification(
        modification_id="mod-x",
        section="Professional Summary",
        proposed_text="Deployed Kubernetes production workloads.",
        claim="Deployed Kubernetes production workloads.",
        reason="Trust me, the candidate definitely has deep Kubernetes experience from a previous unlisted role.",
    )
    result = classify_modification(mod, profile, _pool(profile), llm_client=_mock_client())

    assert result.status == TruthGuardStatus.UNSUPPORTED
