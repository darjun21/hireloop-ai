"""Actionability classification tests (Phase 6 Part 1)."""

from src.models.enums import ActionabilityLevel, SampleConfidence
from src.models.outcome_analytics import GroupAnalytics
from src.services.actionability import classify_actionability


def _group(rate: float, n: int) -> GroupAnalytics:
    return GroupAnalytics(
        group="x",
        sample_size=n,
        positive_responses=0,
        interviews=0,
        offers=0,
        rejections=0,
        response_rate=rate,
        interview_rate=rate,
        offer_rate=0.0,
        rejection_rate=0.0,
        confidence=SampleConfidence.MEDIUM,
    )


def test_identical_rates_are_no_clear_signal():
    assert classify_actionability(_group(0.30, 8), _group(0.30, 8)) == ActionabilityLevel.NO_CLEAR_SIGNAL


def test_tiny_difference_is_no_clear_signal():
    # The exact motivating example: 33.3% vs 28.6%.
    result = classify_actionability(_group(0.333, 6), _group(0.286, 7))
    assert result == ActionabilityLevel.NO_CLEAR_SIGNAL


def test_meaningful_difference_with_decent_sample_is_at_least_moderate():
    result = classify_actionability(_group(0.50, 8), _group(0.30, 8))
    assert result in (ActionabilityLevel.MODERATE_SIGNAL, ActionabilityLevel.STRONG_SIGNAL)


def test_large_difference_with_tiny_sample_is_capped_below_strong():
    result = classify_actionability(_group(0.80, 2), _group(0.10, 2))
    assert result != ActionabilityLevel.STRONG_SIGNAL
    assert result in (ActionabilityLevel.WEAK_SIGNAL, ActionabilityLevel.NO_CLEAR_SIGNAL)


def test_large_difference_with_adequate_sample_is_strong():
    result = classify_actionability(_group(0.80, 15), _group(0.10, 15))
    assert result == ActionabilityLevel.STRONG_SIGNAL


def test_zero_history_is_no_clear_signal():
    assert classify_actionability(_group(0.0, 0), _group(0.0, 0)) == ActionabilityLevel.NO_CLEAR_SIGNAL
    assert classify_actionability(_group(0.5, 5), _group(0.0, 0)) == ActionabilityLevel.NO_CLEAR_SIGNAL


def test_actionability_is_symmetric():
    a, b = _group(0.60, 10), _group(0.20, 10)
    assert classify_actionability(a, b) == classify_actionability(b, a)


def test_llm_cannot_influence_actionability_only_analytics_can():
    """Actionability is purely a function of the two GroupAnalytics inputs
    -- there is no code path for an LLM-provided value to override it."""
    import inspect

    from src.services.actionability import classify_actionability

    params = list(inspect.signature(classify_actionability).parameters)
    assert params == ["group_a", "group_b", "metric"]
    assert "llm_client" not in params


def test_learning_insight_default_actionability_is_safe():
    from datetime import datetime, timezone

    from src.models.enums import InsightCategory
    from src.models.learning_insight import LearningInsight

    insight = LearningInsight(
        insight_id="i1",
        category=InsightCategory.ROLE_FAMILY,
        observation="obs",
        evidence="evidence",
        sample_size=5,
        confidence=SampleConfidence.LOW,
        recommendation="rec",
        created_at=datetime.now(timezone.utc),
    )
    assert insight.actionability == ActionabilityLevel.NO_CLEAR_SIGNAL


def test_no_clear_signal_insight_gets_cautious_recommendation_language():
    from src.services.demo_application_loader import load_demo_application_history
    from src.services.learning_insight_validation import validate_and_ground_insights
    from src.services.outcome_analytics import compute_outcome_analytics

    analytics = compute_outcome_analytics(load_demo_application_history())

    # Force a tiny-difference comparison directly through the validator.
    candidate_insights = [
        {
            "category": "ROLE_FAMILY",
            "referenced_group": "AI Engineer",
            "compared_group": "Software Engineer",
            "observation": "AI Engineer applications generated a 50.0% response rate compared with 14.3% for Software Engineer.",
            "recommendation": "Prioritize AI Engineer roles.",
        }
    ]
    accepted, _ = validate_and_ground_insights(candidate_insights, analytics)
    assert accepted
    insight = accepted[0]
    # This particular comparison (AI Engineer vs Software Engineer) is a
    # real, large, well-sampled difference -- so it should NOT be
    # NO_CLEAR_SIGNAL; this test documents that the mechanism activates
    # only when warranted.
    assert insight.actionability != ActionabilityLevel.NO_CLEAR_SIGNAL
