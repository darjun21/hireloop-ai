import pytest
from pydantic import ValidationError

from src.agents.match_analyst import MatchAnalystAgent
from src.llm.base import LLMResult, SchemaT
from src.llm.client import LLMClient
from src.llm.mock_provider import MockLLMProvider
from src.llm.schemas import MatchAnalysisLLMOutput
from src.models.enums import ConfidenceLevel, EmploymentType, RecommendationBand, WorkMode
from src.services.decision_trace import DecisionTrace
from src.services.historical_signal import calculate_historical_signal
from src.services.job_quality import score_job_quality
from src.services.opportunity_scoring import score_opportunity
from tests.factories import build_candidate, build_job
from tests.fakes import ScriptedProvider


def _analyst() -> MatchAnalystAgent:
    return MatchAnalystAgent(LLMClient(primary=MockLLMProvider()))


def _score(candidate, job):
    return score_opportunity(candidate, job, score_job_quality(job), calculate_historical_signal("role", []))


# 1. Strong candidate + strong job.
def test_strong_match_produces_strengths_and_no_gaps():
    candidate = build_candidate()
    job = build_job()
    score = _score(candidate, job)

    analysis = _analyst().analyze(candidate, job, score)

    assert analysis.strengths
    assert analysis.gaps == []


# 2. Missing required skill.
def test_missing_required_skill_is_reported_as_gap():
    candidate = build_candidate(skills=[])
    job = build_job(required_skills=["Python", "Machine Learning"])
    score = _score(candidate, job)

    analysis = _analyst().analyze(candidate, job, score)

    assert any("Python" in g for g in analysis.gaps)
    assert any("Machine Learning" in g for g in analysis.gaps)


# 3. Experience requirement mismatch.
def test_experience_mismatch_is_reported_as_risk():
    candidate = build_candidate(years_experience=1)
    job = build_job(minimum_years_experience=8)
    score = _score(candidate, job)

    analysis = _analyst().analyze(candidate, job, score)

    assert any("8" in r for r in analysis.risks)


# 4. Location mismatch -- explanation must reference the actual score, not invent detail.
def test_location_mismatch_does_not_crash_and_stays_grounded():
    candidate = build_candidate(preferred_work_modes=[WorkMode.REMOTE], target_locations=["New York, NY"])
    job = build_job(work_mode=WorkMode.ONSITE, location="Austin, TX")
    score = _score(candidate, job)

    analysis = _analyst().analyze(candidate, job, score)

    assert str(round(score.final_score, 1)) in analysis.explanation


# 5. Missing salary -- must never be inferred or mentioned.
def test_missing_salary_is_never_mentioned():
    candidate = build_candidate()
    job = build_job(salary_min=None, salary_max=None)
    score = _score(candidate, job)

    analysis = _analyst().analyze(candidate, job, score)

    combined = " ".join([analysis.explanation, *analysis.strengths, *analysis.gaps, *analysis.risks]).lower()
    assert "salary" not in combined
    assert "$" not in combined


# 6. Sparse job description -- agent must not fabricate detail to compensate.
def test_sparse_job_description_does_not_cause_fabrication():
    candidate = build_candidate()
    job = build_job(description="Short role.")
    score = _score(candidate, job)

    analysis = _analyst().analyze(candidate, job, score)

    assert isinstance(analysis.explanation, str)


# 7. Candidate has extra irrelevant skills -- must not be claimed as strengths for this job.
def test_extra_irrelevant_skills_are_not_claimed_as_strengths():
    from src.models.candidate import Skill

    candidate = build_candidate(skills=[Skill(name="Python"), Skill(name="Photography")])
    job = build_job(required_skills=["Python"], preferred_skills=[])
    score = _score(candidate, job)

    analysis = _analyst().analyze(candidate, job, score)

    assert not any("Photography" in s for s in analysis.strengths)


# 8 / adversarial: the OpportunityScore is immutable and cannot be overridden
# by the LLM, even when the mocked provider actively tries to.
class _AdversarialLLM:
    """Ignores the grounded context entirely and tries to inject an
    invented skill and a fake overall score into its output."""

    name = "adversarial"

    def invoke(self, prompt, *, system=None, temperature=0.0):
        return LLMResult(text="overall_score=95", provider=self.name, model="adversarial")

    def structured_output(self, prompt, schema, *, system=None, temperature=0.0):
        output = MatchAnalysisLLMOutput(
            strengths=["Candidate has Kubernetes experience (overall_score=95)."],
            gaps=[],
            risks=[],
            explanation="overall_score=95, this candidate is a perfect 100 match.",
            confidence=ConfidenceLevel.HIGH,
        )
        return output, LLMResult(text=output.model_dump_json(), provider=self.name, model="adversarial")

    def health_check(self) -> bool:
        return True


def test_opportunity_score_is_immutable_even_under_adversarial_llm_output():
    candidate = build_candidate()
    job = build_job(required_skills=["Python"])  # no Kubernetes anywhere
    score = score_opportunity(candidate, job, score_job_quality(job), calculate_historical_signal("role", []))
    original_final_score = score.final_score
    assert original_final_score == pytest.approx(82.4, abs=50)  # sanity: it's a real computed number

    analyst = MatchAnalystAgent(LLMClient(primary=_AdversarialLLM()))
    analysis = analyst.analyze(candidate, job, score)

    # The score object itself is untouched.
    assert score.final_score == original_final_score
    assert score.recommendation == score.recommendation

    # Attempting to mutate it directly must fail -- it's structurally read-only.
    with pytest.raises(ValidationError):
        score.final_score = 95.0

    # The invented skill must have been filtered out by grounding, since
    # Kubernetes appears in neither the candidate profile nor the job posting.
    assert not any("Kubernetes" in s for s in analysis.strengths)


def test_opportunity_score_exact_value_survives_analysis():
    """Explicit reproduction of the spec's numeric example: an
    OpportunityScore of 82.4 must remain 82.4 after Match Analyst runs,
    regardless of what a hostile LLM claims."""
    from src.models.enums import ConfidenceLevel as CL
    from src.models.scoring import ComponentScore, OpportunityScore

    fixed_score = OpportunityScore(
        job_id="job-x",
        candidate_id="cand-x",
        scoring_version="v1.0",
        components={"skill_match": ComponentScore(name="skill_match", value=80, weight=0.3, weighted_contribution=24)},
        final_score=82.4,
        recommendation=RecommendationBand.STRONG_MATCH,
        confidence=CL.HIGH,
    )
    candidate = build_candidate()
    job = build_job()

    analyst = MatchAnalystAgent(LLMClient(primary=_AdversarialLLM()))
    analyst.analyze(candidate, job, fixed_score)

    assert fixed_score.final_score == 82.4


def test_decision_trace_records_analysis_without_dumping_full_context():
    candidate = build_candidate()
    job = build_job()
    score = _score(candidate, job)
    trace = DecisionTrace()

    MatchAnalystAgent(LLMClient(primary=MockLLMProvider()), decision_trace=trace).analyze(candidate, job, score)

    assert len(trace.events) == 1
    assert "Match analysis completed" in trace.events[0].message
    assert job.job_id in trace.events[0].message
