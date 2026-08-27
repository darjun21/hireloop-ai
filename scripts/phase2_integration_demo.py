"""
Phase 2 developer smoke test: proves Phase 1 (deterministic scoring) and
Phase 2 (LLM foundation, resume parsing, Profile Agent, Match Analyst) work
together end to end WITHOUT LangGraph, mem0, Pinecone, or a UI.

    sample resume -> resume parser -> Profile Agent -> CandidateProfile
    sample JobPosting -> Opportunity Scoring Engine -> OpportunityScore
    CandidateProfile + JobPosting + OpportunityScore -> Match Analyst -> MatchAnalysis

Run from the hireloop-ai/ directory:

    python scripts/phase2_integration_demo.py

Uses the MockLLMProvider by default so it runs with zero API keys. Set
DEFAULT_LLM_PROVIDER=nebius (or fireworks) with the matching *_API_KEY and
*_MODEL env vars to exercise a real provider instead.

This is a development smoke test, not the final Streamlit UI.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agents.match_analyst import MatchAnalystAgent
from src.agents.profile_agent import ProfileAgent, ProfilePreferences
from src.config.settings import load_settings
from src.llm.provider import get_llm_client
from src.models.enums import EmploymentType, WorkMode
from src.models.job import JobPosting
from src.services.decision_trace import DecisionTrace
from src.services.historical_signal import calculate_historical_signal
from src.services.job_quality import score_job_quality
from src.services.opportunity_scoring import score_opportunity
from src.services.resume_parser import parse_resume_bytes

SAMPLE_RESUME = """\
Arjun Example
AI engineer building retrieval-augmented systems for production use.

SKILLS
Python, LangChain, AWS

WORK EXPERIENCE
ML Platform Engineer | Nova Labs | 2021-01 - Present
Built retrieval pipelines and fine-tuning workflows using Python and LangChain, deployed on AWS.

Backend Engineer | Beta Corp | 2018-06 - 2021-01
Developed backend services in Python.

PROJECTS
Realtime Recommender
Used Python and Kafka to build a recommender system for internal tooling.

EDUCATION
B.S. Computer Science | State University | 2014-09 - 2018-05
"""

SAMPLE_JOB = JobPosting(
    job_id="job-ai-engineer-001",
    title="AI Engineer",
    company="Globex",
    location="Remote",
    work_mode=WorkMode.REMOTE,
    employment_type=EmploymentType.FULL_TIME,
    required_skills=["Python", "LangChain"],
    preferred_skills=["Kubernetes"],
    minimum_years_experience=3,
    description=(
        "Join our AI platform team building retrieval-augmented generation systems that power "
        "production features used by millions of users. You will design, build, and operate "
        "LLM-backed services end to end."
    ),
)


def main() -> None:
    trace = DecisionTrace()
    settings = load_settings()
    llm_client = get_llm_client(settings)
    provider_name = llm_client.primary.name

    parse_result = parse_resume_bytes(SAMPLE_RESUME.encode("utf-8"), "sample_resume.txt")
    trace.add(
        "resume_parsing",
        "parse_resume",
        f"Resume parsed successfully: {parse_result.character_count:,} characters extracted.",
    )
    if not parse_result.success:
        print(f"Resume parsing failed: {parse_result.error}")
        return

    profile_agent = ProfileAgent(llm_client, decision_trace=trace)
    profile, validation = profile_agent.build_profile(
        parse_result.extracted_text,
        candidate_id="cand-demo-1",
        preferences=ProfilePreferences(target_roles=["AI Engineer"], preferred_work_modes=[WorkMode.REMOTE]),
    )

    job_quality = score_job_quality(SAMPLE_JOB)
    historical_signal = calculate_historical_signal("AI Engineer", [])
    opportunity_score = score_opportunity(profile, SAMPLE_JOB, job_quality, historical_signal)
    trace.add(
        "scoring",
        "score_opportunity",
        f"1 opportunity scored: {opportunity_score.final_score:.1f} ({opportunity_score.recommendation.value}).",
    )

    match_analyst = MatchAnalystAgent(llm_client, decision_trace=trace)
    analysis = match_analyst.analyze(profile, SAMPLE_JOB, opportunity_score)

    print("=" * 60)
    print("Candidate:")
    print(f"  {profile.name}")
    print()
    print("Job:")
    print(f"  {SAMPLE_JOB.title} at {SAMPLE_JOB.company}")
    print()
    print("Opportunity Score:")
    print(f"  {opportunity_score.final_score:.1f} - {opportunity_score.recommendation.value}")
    print()
    print("Strengths:")
    for line in analysis.strengths or ["(none)"]:
        print(f"  - {line}")
    print()
    print("Gaps:")
    for line in analysis.gaps or ["(none)"]:
        print(f"  - {line}")
    print()
    print("Risks:")
    for line in analysis.risks or ["(none)"]:
        print(f"  - {line}")
    print()
    print("Explanation:")
    print(f"  {analysis.explanation}")
    print()
    print(f"Confidence: {analysis.confidence.value}")
    print()
    print(f"Provider: {provider_name}{' (mock output, not a live model)' if provider_name == 'mock' else ''}")
    print()
    if validation.warnings:
        print(f"Profile validation warnings ({len(validation.warnings)}):")
        for w in validation.warnings:
            print(f"  - {w}")
        print()
    print("Decision Trace:")
    for line in trace.as_lines():
        print(f"  -> {line}")
    print("=" * 60)


if __name__ == "__main__":
    main()
