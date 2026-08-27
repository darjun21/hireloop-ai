"""
TruthGuardResult model.

Produced by the deterministic Truth Guard classifier (Phase 4) for one
ResumeModification. See docs/TRUTH_GUARD.md for the full status
definitions and why classification is deterministic rather than
LLM-judged.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.models.enums import TruthGuardStatus


class TruthGuardResult(BaseModel):
    modification_id: str = Field(..., min_length=1)
    status: TruthGuardStatus
    evidence_ids: list[str] = Field(default_factory=list)
    explanation: str = ""
    unsupported_fragments: list[str] = Field(default_factory=list)
    suggested_safe_rewrite: str | None = None
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
