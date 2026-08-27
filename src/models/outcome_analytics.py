"""
Deterministic outcome analytics models.

Every rate here is computed at the *application* level: an application
that progressed APPLIED -> RECRUITER_RESPONSE -> INTERVIEW -> OFFER counts
as exactly one application, one positive response, one interview, and one
offer -- never three independent successes. See
src/services/outcome_analytics.py.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from src.models.enums import SampleConfidence


class GroupAnalytics(BaseModel):
    group: str = Field(..., min_length=1)

    sample_size: int = Field(..., ge=0)
    positive_responses: int = Field(..., ge=0)
    interviews: int = Field(..., ge=0)
    offers: int = Field(..., ge=0)
    rejections: int = Field(..., ge=0)

    response_rate: float = Field(..., ge=0.0, le=1.0)
    interview_rate: float = Field(..., ge=0.0, le=1.0)
    offer_rate: float = Field(..., ge=0.0, le=1.0)
    rejection_rate: float = Field(..., ge=0.0, le=1.0)

    average_opportunity_score: float | None = Field(default=None, ge=0, le=100)
    confidence: SampleConfidence


class OutcomeAnalytics(BaseModel):
    by_role_family: dict[str, GroupAnalytics] = Field(default_factory=dict)
    by_resume_version: dict[str, GroupAnalytics] = Field(default_factory=dict)
    by_work_mode: dict[str, GroupAnalytics] = Field(default_factory=dict)

    total_applications: int = Field(..., ge=0)
    total_resolved: int = Field(..., ge=0)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
