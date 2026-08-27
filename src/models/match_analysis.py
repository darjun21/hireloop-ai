"""
MatchAnalysis model.

Produced by the Match Analyst Agent in a later phase, from a finished
OpportunityScore plus retrieved evidence. Defined now so downstream storage
and UI models can reference it; not populated by any logic in Phase 1.

Boundary: this model has no field for a numeric score override — the
Match Analyst interprets src.models.scoring.OpportunityScore, it never
produces or replaces one.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.models.enums import ConfidenceLevel


class MatchAnalysis(BaseModel):
    job_id: str = Field(..., min_length=1)
    candidate_id: str = Field(..., min_length=1)

    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    explanation: str = ""
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM
