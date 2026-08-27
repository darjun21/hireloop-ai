"""JobQualityResult model — output of the deterministic job quality service."""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.models.enums import ConfidenceLevel, JobQualityRecommendation


class JobQualityResult(BaseModel):
    quality_score: float = Field(..., ge=0, le=100)
    flags: list[str] = Field(default_factory=list)
    confidence: ConfidenceLevel
    recommendation: JobQualityRecommendation
    # Informational: how much the posting actually specified (see
    # src/services/job_evidence_sufficiency.py). LOW also appears in
    # `flags` as "sparse_requirements" so it participates in quality_score
    # and downstream OpportunityScore.confidence like any other flag.
    requirement_completeness: str = "MEDIUM"
