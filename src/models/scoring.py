"""
Opportunity scoring models.

OpportunityScore is produced only by the deterministic Opportunity Scoring
Engine (src/services/opportunity_scoring.py). No agent may construct or
mutate one directly with a different final_score than the engine computed
— see docs/DECISIONS.md #1 and #7.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field

from src.models.enums import ConfidenceLevel, RecommendationBand


class ComponentScore(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(..., min_length=1)
    value: float = Field(..., ge=0, le=100)
    weight: float = Field(..., ge=0, le=1)
    weighted_contribution: float = Field(..., ge=0, le=100)
    explanation: str = ""
    missing_data: bool = False


class OpportunityScore(BaseModel):
    """Produced only by the deterministic Opportunity Scoring Engine.
    Frozen so no agent (Match Analyst included) can mutate a score after
    the fact — see docs/DECISIONS.md #1 and #7."""

    model_config = ConfigDict(frozen=True)

    job_id: str = Field(..., min_length=1)
    candidate_id: str = Field(..., min_length=1)
    scoring_version: str = Field(..., min_length=1)

    components: dict[str, ComponentScore]

    final_score: float = Field(..., ge=0, le=100)
    recommendation: RecommendationBand
    confidence: ConfidenceLevel

    historical_sample_size: int = Field(default=0, ge=0)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
