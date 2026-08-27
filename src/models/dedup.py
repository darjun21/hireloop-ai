"""DuplicateMatchResult model — output of the deterministic dedup service."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DuplicateMatchResult(BaseModel):
    is_duplicate: bool
    confidence: float = Field(..., ge=0.0, le=1.0)
    matched_job_id: str | None = None
    reasons: list[str] = Field(default_factory=list)
