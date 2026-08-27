"""
Category 5: Match Grounding.

Verifies the real Match Analyst agent (src/agents/match_analyst.py) and its
grounding filter (src/agents/grounding.py) never let a strengths/gaps/risks
claim reference a skill absent from both the CandidateProfile and the
JobPosting -- no invented skills reach the user, even if an (adversarial)
LLM output tries to introduce one. Uses the deterministic Mock LLM
provider.
"""

from __future__ import annotations

from src.agents.grounding import build_grounded_vocabulary, filter_ungrounded_claims
from src.agents.match_analyst import MatchAnalystAgent
from src.llm.client import LLMClient
from src.llm.mock_provider import MockLLMProvider
from src.services.job_quality import score_job_quality
from src.services.opportunity_scoring import score_opportunity
from evals.common import CategorySummary, EvalCase, summarize
from tests.factories import build_candidate, build_job

CATEGORY = "match_grounding"


def _neutral_signal():
    from src.models.enums import ConfidenceLevel
    from src.models.strategy_insight import StrategyInsight

    return StrategyInsight(
        role_family="AI Engineer", sample_size=0, success_rate=None, signal_value=50.0,
        confidence=ConfidenceLevel.LOW, is_neutral=True, explanation="No historical data.",
    )


def run() -> CategorySummary:
    cases: list[EvalCase] = []
    agent = MatchAnalystAgent(llm_client=LLMClient(primary=MockLLMProvider()))

    # 1. End-to-end: every strength/gap/risk from a real analyze() call must
    #    reference only vocabulary present in the candidate profile or job.
    candidate = build_candidate()
    job = build_job(job_id="grounding-1", required_skills=["Python", "Kubernetes"], preferred_skills=["AWS"])
    score = score_opportunity(candidate, job, score_job_quality(job), _neutral_signal())
    analysis = agent.analyze(candidate, job, score)

    vocabulary = build_grounded_vocabulary(candidate, job)
    all_lines = analysis.strengths + analysis.gaps + analysis.risks
    _, dropped_by_construction = filter_ungrounded_claims(all_lines, vocabulary)
    # analyze() already filters before returning, so nothing it hands back
    # should itself get dropped by a second independent pass.
    passed = dropped_by_construction == []
    cases.append(
        EvalCase(
            "grounding:real_analysis_output_fully_grounded",
            CATEGORY,
            passed,
            detail=f"strengths={analysis.strengths} gaps={analysis.gaps} risks={analysis.risks} "
            f"re_filtered_dropped={dropped_by_construction}",
        )
    )

    # 2. Missing required skill (Kubernetes) is correctly reported as a gap,
    #    not silently invented as a strength.
    passed = any("kubernetes" in g.lower() for g in analysis.gaps) and not any(
        "kubernetes" in s.lower() for s in analysis.strengths
    )
    cases.append(
        EvalCase(
            "grounding:missing_required_skill_reported_as_gap_not_strength",
            CATEGORY,
            passed,
            detail=f"gaps={analysis.gaps} strengths={analysis.strengths}",
        )
    )

    # 3. The score/recommendation itself is never altered by the agent --
    #    only the deterministic OpportunityScore's own values appear.
    passed = analysis.job_id == job.job_id and analysis.candidate_id == candidate.candidate_id
    cases.append(EvalCase("grounding:analysis_identity_matches_inputs", CATEGORY, passed, detail=str(analysis)))

    # 4. Direct adversarial test of the grounding filter itself: a line
    #    mentioning a skill vocabulary term absent from both candidate and
    #    job (an "invented" skill) must be dropped.
    vocab = build_grounded_vocabulary(candidate, job)
    adversarial_lines = [
        "Candidate has Rust experience matching a required skill.",  # Rust not in candidate or job
        "Candidate has Python experience matching a required skill.",  # Python IS grounded
    ]
    kept, dropped = filter_ungrounded_claims(adversarial_lines, vocab)
    passed = (
        len(dropped) == 1
        and "Rust" in dropped[0]
        and len(kept) == 1
        and "Python" in kept[0]
    )
    cases.append(
        EvalCase(
            "grounding:ungrounded_skill_claim_dropped_grounded_claim_kept",
            CATEGORY,
            passed,
            detail=f"kept={kept} dropped={dropped}",
        )
    )

    # 5. Salary is never inferred when the job posting states none.
    no_salary_job = build_job(job_id="grounding-no-salary")
    assert no_salary_job.salary_min is None and no_salary_job.salary_max is None
    no_salary_score = score_opportunity(candidate, no_salary_job, score_job_quality(no_salary_job), _neutral_signal())
    no_salary_analysis = agent.analyze(candidate, no_salary_job, no_salary_score)
    mentions_salary = any(
        "salary" in line.lower() or "$" in line for line in no_salary_analysis.strengths + no_salary_analysis.gaps + no_salary_analysis.risks
    )
    cases.append(
        EvalCase(
            "grounding:no_salary_stated_never_inferred",
            CATEGORY,
            not mentions_salary,
            detail=str(no_salary_analysis.explanation),
        )
    )

    return summarize(CATEGORY, cases)


if __name__ == "__main__":
    result = run()
    print(result.to_dict())
