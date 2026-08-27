"""Models for evidence search results and per-requirement evidence retrieval."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class EvidenceStrength(str, Enum):
    NONE = "NONE"
    WEAK = "WEAK"
    MODERATE = "MODERATE"
    STRONG = "STRONG"


class RetrievalSource(str, Enum):
    PINECONE = "PINECONE"
    LOCAL_FALLBACK = "LOCAL_FALLBACK"
    DIRECT_PROFILE_MATCH = "DIRECT_PROFILE_MATCH"


class EvidenceSearchResult(BaseModel):
    evidence_id: str
    score: float = Field(..., ge=0.0)
    source: RetrievalSource


class RequirementEvidence(BaseModel):
    """Retrieval provides candidate evidence for agents to judge — it does
    NOT itself claim the requirement is satisfied. Only Truth Guard makes
    that call."""

    requirement: str
    matched_evidence_ids: list[str] = Field(default_factory=list)
    evidence_strength: EvidenceStrength
    retrieval_source: RetrievalSource
    confidence: float = Field(..., ge=0.0, le=1.0)
