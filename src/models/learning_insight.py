"""
LearningInsight — the Learning Agent's structured output.

Deliberately a distinct model from src/models/strategy_insight.py's
StrategyInsight, which is Phase 1's deterministic historical-signal
calculator output (a scoring-engine input, one number). LearningInsight is
a richer, human-facing recommendation produced by interpreting already-
computed OutcomeAnalytics — the two serve different layers and must not be
confused: only the former ever feeds into OpportunityScore.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from src.models.enums import ActionabilityLevel, InsightCategory, SampleConfidence


class LearningInsight(BaseModel):
    insight_id: str = Field(..., min_length=1)
    category: InsightCategory
    observation: str = Field(..., min_length=1)
    evidence: str = Field(..., min_length=1)
    sample_size: int = Field(..., ge=0)
    confidence: SampleConfidence
    # How large the observed effect is, independent of sample confidence
    # (src/services/actionability.py). Defaults to NO_CLEAR_SIGNAL for any
    # insight type this doesn't apply to.
    actionability: ActionabilityLevel = ActionabilityLevel.NO_CLEAR_SIGNAL
    recommendation: str = Field(..., min_length=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
