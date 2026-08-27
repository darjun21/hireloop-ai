"""
Learning Agent.

Interprets already-computed OutcomeAnalytics into human-readable
LearningInsight recommendations. It does NOT calculate metrics — every
number it's allowed to reference already exists in the analytics passed
in, and src/services/learning_insight_validation.py deterministically
rejects any insight that cites an ungrounded number, references an unknown
group, or uses causal language, before anything is persisted.

The Learning Agent has no code path to modify scoring weights, candidate
facts, or application history — it can only produce LearningInsight
objects for a human to read (docs/LEARNING_LOOP.md's strategy-change
safety boundary).
"""

from __future__ import annotations

import json

from src.llm.client import LLMClient
from src.llm.schemas import LearningAgentLLMOutput
from src.models.learning_insight import LearningInsight
from src.models.outcome_analytics import OutcomeAnalytics
from src.services.decision_trace import DecisionTrace
from src.services.learning_insight_validation import validate_and_ground_insights

_GROUNDING_SYSTEM_PROMPT = """\
You are interpreting already-computed job-search outcome analytics for a candidate. You may reference \
ONLY the group statistics provided in the user message -- never invent a company fact, market trend, \
salary figure, skill, or causal explanation. Every number you cite must come directly from the provided \
data. Never claim something "causes," "guarantees," or "proves" an outcome -- describe only what was \
observed. If the data doesn't clearly support an interesting comparison, return no insights rather than \
inventing one.
"""

_CATEGORY_GROUP_MAP = {
    "ROLE_FAMILY": "by_role_family",
    "RESUME_VERSION": "by_resume_version",
    "WORK_MODE": "by_work_mode",
}


def _serialize_groups(analytics: OutcomeAnalytics, attr: str) -> dict:
    groups = getattr(analytics, attr)
    return {
        key: {
            "sample_size": g.sample_size,
            "response_rate": g.response_rate,
            "interview_rate": g.interview_rate,
            "offer_rate": g.offer_rate,
            "rejection_rate": g.rejection_rate,
            "confidence": g.confidence.value,
        }
        for key, g in groups.items()
    }


class LearningAgent:
    def __init__(self, llm_client: LLMClient, decision_trace: DecisionTrace | None = None) -> None:
        self.llm_client = llm_client
        self.decision_trace = decision_trace

    def generate_insights(self, analytics: OutcomeAnalytics) -> list[LearningInsight]:
        all_insights: list[LearningInsight] = []
        all_rejections: list[str] = []

        for category, attr in _CATEGORY_GROUP_MAP.items():
            groups = _serialize_groups(analytics, attr)
            if len(groups) < 2:
                continue  # nothing to compare -- no strong insight possible

            context = json.dumps({"category": category, "groups": groups})
            llm_output, _ = self.llm_client.structured_output(context, LearningAgentLLMOutput, system=_GROUNDING_SYSTEM_PROMPT)

            candidate_insights = [item.model_dump() for item in llm_output.insights]
            accepted, rejections = validate_and_ground_insights(candidate_insights, analytics)
            all_insights.extend(accepted)
            all_rejections.extend(rejections)

        if self.decision_trace:
            message = f"Learning Agent generated {len(all_insights)} strategy insight(s)."
            if all_rejections:
                message += f" {len(all_rejections)} candidate insight(s) rejected by post-validation."
            self.decision_trace.add(
                "learning_agent", "generate_insights", message, metadata={"rejections": len(all_rejections)}
            )

        return all_insights
