"""
Match Analyst Agent.

Interprets a finished, deterministic OpportunityScore into a qualitative
MatchAnalysis (strengths/gaps/risks/explanation/confidence). The score
itself is a frozen Pydantic model (see src/models/scoring.py) — this agent
has no attribute path that could mutate it, and the LLM call it makes uses
a schema (MatchAnalysisLLMOutput) with no score/recommendation field at
all, so there is nothing for a model to override even if it tries.

Only CandidateProfile, JobPosting, and OpportunityScore are ever placed in
the prompt context — see src/agents/grounding.py for enforcement.
"""

from __future__ import annotations

import json

from src.agents.grounding import build_grounded_vocabulary, filter_ungrounded_claims, salary_context
from src.llm.client import LLMClient
from src.llm.schemas import MatchAnalysisLLMOutput
from src.models.candidate import CandidateProfile
from src.models.job import JobPosting
from src.models.match_analysis import MatchAnalysis
from src.models.scoring import OpportunityScore
from src.services.decision_trace import DecisionTrace
from src.services.job_evidence_sufficiency import CompletenessLevel, assess_requirement_completeness

_GROUNDING_SYSTEM_PROMPT = """\
You are interpreting a job opportunity match for a candidate. The user message is a JSON object \
containing the only facts you may reference: fields drawn from the CandidateProfile, JobPosting, and \
OpportunityScore. Produce strengths, gaps, risks, a concise explanation, and a confidence level for \
this candidate/job match. Rules:
- Do not invent external company facts.
- Do not infer a salary if none was provided.
- If the candidate lacks a required skill, state it as a gap. Never assume an adjacent skill counts \
as evidence of the missing one.
- Do not restate or change the numeric score or recommendation band; you are explaining it, not \
setting it.
- If a claim cannot be grounded in the provided data, omit it.
"""


def _build_context(candidate: CandidateProfile, job: JobPosting, score: OpportunityScore) -> dict:
    context = {
        "candidate_skills": [s.name for s in candidate.skills],
        "candidate_years_experience": candidate.years_experience,
        "candidate_target_roles": candidate.target_roles,
        "job_title": job.title,
        "job_required_skills": job.required_skills,
        "job_preferred_skills": job.preferred_skills,
        "job_minimum_years_experience": job.minimum_years_experience,
        "final_score": score.final_score,
        "recommendation": score.recommendation.value,
        "score_confidence": score.confidence.value,
    }
    salary = salary_context(job)
    if salary is not None:
        context["salary"] = salary
    return context


class MatchAnalystAgent:
    def __init__(self, llm_client: LLMClient, decision_trace: DecisionTrace | None = None) -> None:
        self.llm_client = llm_client
        self.decision_trace = decision_trace

    def analyze(
        self,
        candidate: CandidateProfile,
        job: JobPosting,
        opportunity_score: OpportunityScore,
    ) -> MatchAnalysis:
        context = _build_context(candidate, job, opportunity_score)
        prompt = json.dumps(context)

        llm_output, _ = self.llm_client.structured_output(
            prompt, MatchAnalysisLLMOutput, system=_GROUNDING_SYSTEM_PROMPT
        )

        grounded_vocabulary = build_grounded_vocabulary(candidate, job)
        strengths, dropped_strengths = filter_ungrounded_claims(llm_output.strengths, grounded_vocabulary)
        gaps, dropped_gaps = filter_ungrounded_claims(llm_output.gaps, grounded_vocabulary)
        risks, dropped_risks = filter_ungrounded_claims(llm_output.risks, grounded_vocabulary)

        # Deterministic, not LLM-dependent: always surface when a job posting
        # specified very little, so a clean skill match against a near-empty
        # requirement list never reads as unqualified confidence.
        completeness = assess_requirement_completeness(job)
        if completeness.level == CompletenessLevel.LOW:
            risks = [
                *risks,
                "Limited job description evidence: this posting specifies very few explicit requirements "
                f"(completeness score {completeness.completeness_score:.0f}/100); treat this match with reduced confidence.",
            ]

        analysis = MatchAnalysis(
            job_id=job.job_id,
            candidate_id=candidate.candidate_id,
            strengths=strengths,
            gaps=gaps,
            risks=risks,
            explanation=llm_output.explanation,
            confidence=llm_output.confidence,
        )

        if self.decision_trace:
            dropped_count = len(dropped_strengths) + len(dropped_gaps) + len(dropped_risks)
            message = f"Match analysis completed for job {job.job_id}."
            if dropped_count:
                message += f" {dropped_count} ungrounded claim(s) filtered."
            self.decision_trace.add(
                "match_analyst",
                "analyze",
                message,
                metadata={"dropped_claims": dropped_count},
            )

        return analysis
