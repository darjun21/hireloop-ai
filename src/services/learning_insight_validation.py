"""
Deterministic post-validation for Learning Agent output (Part K).

The Learning Agent may reference ONLY: OutcomeAnalytics, candidate
preferences, existing LearningInsights, application-history summaries. It
may not invent company facts, market trends, causal explanations, salary
information, or skills never present in the input. This module enforces
that mechanically rather than trusting the LLM's self-restraint:

- Every insight must reference a real group present in the analytics.
- Every numeric/percentage claim in the text must match a number actually
  computed in that group's GroupAnalytics (or another group's, for
  comparative observations) -- an invented number is rejected outright.
- Causal language ("causes", "guarantees", "proves", "will result in", ...)
  is rejected outright rather than rewritten -- consistent with Truth
  Guard's "reject, don't guess" posture (docs/TRUTH_GUARD.md).
- Confidence and sample_size are always taken from the analytics group,
  never from the LLM's own stated numbers.
"""

from __future__ import annotations

import re
from uuid import uuid4

from src.config.analytics import MIN_SAMPLE_SIZE_FOR_INSIGHT
from src.models.enums import ActionabilityLevel, SampleConfidence
from src.models.learning_insight import LearningInsight
from src.models.outcome_analytics import GroupAnalytics, OutcomeAnalytics
from src.services.actionability import actionability_language, classify_actionability

_CAUSAL_PHRASES = (
    "causes",
    "caused by",
    "will result in",
    "guarantees",
    "guaranteed",
    "proves",
    "proven to",
    "will definitely",
    "ensures",
)

_PERCENT_PATTERN = re.compile(r"\d+(?:\.\d+)?\s?%")

_HEDGE_PREFIXES = {
    SampleConfidence.INSUFFICIENT: "Based on a very small sample (treat as an early, low-confidence signal): ",
    SampleConfidence.LOW: "Based on a limited sample (low confidence): ",
    SampleConfidence.MEDIUM: "Observed pattern (moderate confidence): ",
    SampleConfidence.HIGH: "Observed pattern: ",
}


def _contains_causal_language(text: str) -> str | None:
    lowered = text.lower()
    for phrase in _CAUSAL_PHRASES:
        if phrase in lowered:
            return phrase
    return None


def _all_analytics_percentages(analytics: OutcomeAnalytics) -> set[str]:
    percentages: set[str] = set()
    for group_map in (analytics.by_role_family, analytics.by_resume_version, analytics.by_work_mode):
        for group in group_map.values():
            for rate in (group.response_rate, group.interview_rate, group.offer_rate, group.rejection_rate):
                percentages.add(f"{rate * 100:.1f}%")
                percentages.add(f"{round(rate * 100)}%")
    return percentages


def _numeric_claims_are_grounded(text: str, known_percentages: set[str]) -> bool:
    for match in _PERCENT_PATTERN.findall(text):
        normalized = match.replace(" ", "")
        if not any(normalized == p.replace(" ", "") for p in known_percentages):
            return False
    return True


def _find_group(analytics: OutcomeAnalytics, referenced_group: str) -> GroupAnalytics | None:
    for group_map in (analytics.by_role_family, analytics.by_resume_version, analytics.by_work_mode):
        if referenced_group in group_map:
            return group_map[referenced_group]
    return None


def validate_and_ground_insights(
    candidate_insights: list[dict],
    analytics: OutcomeAnalytics,
) -> tuple[list[LearningInsight], list[str]]:
    """Returns (accepted_insights, rejection_reasons). Never trusts the
    LLM's own sample_size/confidence -- both are re-derived from the
    referenced analytics group."""
    accepted: list[LearningInsight] = []
    rejections: list[str] = []

    known_percentages = _all_analytics_percentages(analytics)

    for candidate in candidate_insights:
        referenced_group = candidate.get("referenced_group", "")
        group = _find_group(analytics, referenced_group)
        if group is None:
            rejections.append(f"insight referenced unknown group {referenced_group!r}; rejected")
            continue

        if group.sample_size < MIN_SAMPLE_SIZE_FOR_INSIGHT:
            rejections.append(f"group {referenced_group!r} has insufficient sample size ({group.sample_size}); rejected")
            continue

        observation = candidate.get("observation", "")
        recommendation = candidate.get("recommendation", "")
        combined_text = f"{observation} {recommendation}"

        causal_phrase = _contains_causal_language(combined_text)
        if causal_phrase:
            rejections.append(f"insight for {referenced_group!r} used causal language ({causal_phrase!r}); rejected")
            continue

        if not _numeric_claims_are_grounded(combined_text, known_percentages):
            rejections.append(f"insight for {referenced_group!r} cited a percentage not present in analytics; rejected")
            continue

        hedged_observation = _HEDGE_PREFIXES[group.confidence] + observation

        # Actionability (effect size) is a separate axis from sample
        # confidence -- computed deterministically here, never by the LLM.
        compared_group_key = candidate.get("compared_group")
        compared_group = _find_group(analytics, compared_group_key) if compared_group_key else None
        actionability = (
            classify_actionability(group, compared_group) if compared_group is not None else ActionabilityLevel.NO_CLEAR_SIGNAL
        )

        # A tiny effect shouldn't carry a "prioritize X" recommendation
        # even if the LLM proposed one -- replace it with the honest,
        # deterministic caution language instead of trusting the LLM's
        # own sense of how strong its finding is.
        final_recommendation = (
            actionability_language(actionability) if actionability == ActionabilityLevel.NO_CLEAR_SIGNAL else recommendation
        )

        accepted.append(
            LearningInsight(
                insight_id=f"insight-{uuid4().hex[:10]}",
                category=candidate.get("category", "ROLE_FAMILY"),
                observation=hedged_observation,
                evidence=(
                    f"{group.sample_size} resolved application(s) for {referenced_group!r}: "
                    f"response_rate={group.response_rate * 100:.1f}%, interview_rate={group.interview_rate * 100:.1f}%, "
                    f"offer_rate={group.offer_rate * 100:.1f}%."
                ),
                sample_size=group.sample_size,
                confidence=group.confidence,
                actionability=actionability,
                recommendation=final_recommendation,
            )
        )

    return accepted, rejections
