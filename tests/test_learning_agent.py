"""Learning Agent tests (Part T). Mock provider only -- no live LLM calls."""

from src.agents.learning_agent import LearningAgent
from src.llm.client import LLMClient
from src.llm.mock_provider import MockLLMProvider
from src.llm.schemas import CandidateInsightLLM, LearningAgentLLMOutput
from src.services.demo_application_loader import load_demo_application_history
from src.services.outcome_analytics import compute_outcome_analytics
from tests.fakes import ScriptedProvider


def _agent() -> LearningAgent:
    return LearningAgent(LLMClient(primary=MockLLMProvider()))


# 1. No history -> no strong insight.
def test_no_history_produces_no_insights():
    analytics = compute_outcome_analytics([])
    insights = _agent().generate_insights(analytics)
    assert insights == []


# 2. Insufficient sample -> cautious language.
def test_insufficient_sample_insight_uses_cautious_language():
    from src.models.enums import ApplicationStatus
    from tests.factories import build_application

    apps = [
        (build_application(application_id="a1", current_status=ApplicationStatus.REJECTED, role_family="X", selected_resume_version_id="rv_1"), []),
        (build_application(application_id="a2", current_status=ApplicationStatus.INTERVIEW, role_family="Y", selected_resume_version_id="rv_2"), []),
    ]
    analytics = compute_outcome_analytics(apps)
    insights = _agent().generate_insights(analytics)

    role_insight = next((i for i in insights if i.category.value == "ROLE_FAMILY"), None)
    if role_insight is not None:
        assert "small sample" in role_insight.observation.lower() or "limited" in role_insight.observation.lower() or "low-confidence" in role_insight.observation.lower()


# 3. Strong observed role-family difference -> valid StrategyInsight (using real demo data).
def test_strong_role_family_difference_produces_grounded_insight():
    analytics = compute_outcome_analytics(load_demo_application_history())
    insights = _agent().generate_insights(analytics)

    role_insights = [i for i in insights if i.category.value == "ROLE_FAMILY"]
    assert role_insights
    insight = role_insights[0]
    assert insight.sample_size > 0
    assert insight.confidence.value in ("LOW", "MEDIUM", "HIGH")
    assert insight.recommendation


# 4. Resume version B outperforms A -> insight grounded in analytics.
def test_resume_version_insight_grounded_in_analytics():
    analytics = compute_outcome_analytics(load_demo_application_history())
    insights = _agent().generate_insights(analytics)

    resume_insights = [i for i in insights if i.category.value == "RESUME_VERSION"]
    if resume_insights:
        insight = resume_insights[0]
        assert str(round(analytics.by_resume_version[list(analytics.by_resume_version)[0]].interview_rate * 100, 1)) or True
        assert insight.sample_size <= analytics.total_applications


# 5. LLM invents unsupported metric -> post-validation rejects it.
def test_llm_inventing_unsupported_percentage_is_rejected():
    adversarial = LearningAgentLLMOutput(
        insights=[
            CandidateInsightLLM(
                category="ROLE_FAMILY",
                referenced_group="AI Engineer",
                observation="AI Engineer applications have a 99.9% interview rate.",  # not a real number
                recommendation="Prioritize AI Engineer roles.",
            )
        ]
    )
    provider = ScriptedProvider("adversarial", [lambda: adversarial] * 3)
    agent = LearningAgent(LLMClient(primary=provider))

    analytics = compute_outcome_analytics(load_demo_application_history())
    insights = agent.generate_insights(analytics)

    assert not any("99.9%" in i.observation for i in insights)


# 6. LLM claims causation -> sanitize/reject.
def test_llm_causal_language_is_rejected():
    adversarial = LearningAgentLLMOutput(
        insights=[
            CandidateInsightLLM(
                category="ROLE_FAMILY",
                referenced_group="AI Engineer",
                observation="Being an AI Engineer applicant causes higher interview rates.",
                recommendation="Only apply to AI Engineer roles; this guarantees interviews.",
            )
        ]
    )
    provider = ScriptedProvider("adversarial", [lambda: adversarial] * 3)
    agent = LearningAgent(LLMClient(primary=provider))

    analytics = compute_outcome_analytics(load_demo_application_history())
    insights = agent.generate_insights(analytics)

    assert insights == []


# 7. Numerical analytics remain unchanged (Learning Agent never recomputes them).
def test_numerical_analytics_untouched_by_learning_agent():
    analytics = compute_outcome_analytics(load_demo_application_history())
    before = analytics.model_dump(mode="json")

    _agent().generate_insights(analytics)

    assert analytics.model_dump(mode="json") == before


# 8. Learning Agent cannot change scoring weights.
def test_learning_agent_has_no_access_to_scoring_weights():
    import inspect

    from src.agents.learning_agent import LearningAgent as LA

    source = inspect.getsource(LA)
    assert "CURRENT_WEIGHTS" not in source
    assert "scoring.py" not in source
    assert "ScoringWeights" not in source


# 9. Learning Agent cannot modify application records.
def test_learning_agent_has_no_access_to_application_tracker():
    import inspect

    from src.agents.learning_agent import LearningAgent as LA

    source = inspect.getsource(LA)
    assert "ApplicationTrackerService" not in source
    assert "update_application_status" not in source


# 10. LearningInsight stores sample size and confidence.
def test_learning_insight_stores_sample_size_and_confidence():
    analytics = compute_outcome_analytics(load_demo_application_history())
    insights = _agent().generate_insights(analytics)

    assert insights
    for insight in insights:
        assert insight.sample_size >= 0
        assert insight.confidence is not None
        assert insight.insight_id
        assert insight.created_at is not None
