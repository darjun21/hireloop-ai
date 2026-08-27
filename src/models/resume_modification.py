"""
ResumeModification model.

Produced by the Resume Tailor Agent (Phase 4). The Tailor only ever
proposes — it never saves or finalizes a resume. Every modification must
pass through Truth Guard, and only human-approved modifications ever reach
a ResumeVersion (src/models/resume_version.py).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.models.enums import TruthGuardStatus


class ResumeModification(BaseModel):
    modification_id: str = Field(..., min_length=1)
    section: str = Field(..., min_length=1)
    original_text: str | None = None
    proposed_text: str = Field(..., min_length=1)
    reason: str = ""
    targeted_job_requirement: str = ""
    # The specific, checkable claim within proposed_text -- usually equal
    # to proposed_text itself, but can be narrower for a modification that
    # only changes part of a larger block.
    claim: str = ""
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    status: TruthGuardStatus | None = None
