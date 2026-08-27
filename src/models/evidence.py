"""
Evidence model.

Every important skill/experience/project claim on a CandidateProfile can
carry a list of Evidence. This is the *only* authoritative grounding
source for Truth Guard (Phase 4) — an LLM's memory of "the resume probably
said X" is never evidence; only a recorded Evidence instance is.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from src.models.enums import EvidenceSourceType


class Evidence(BaseModel):
    evidence_id: str = Field(..., min_length=1)
    candidate_id: str | None = None
    source_type: EvidenceSourceType
    source_section: str = Field(..., min_length=1)
    source_text: str = Field(..., min_length=1)
    normalized_concepts: list[str] = Field(default_factory=list)
    confidence: float = Field(..., ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)
