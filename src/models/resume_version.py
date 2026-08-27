"""
ResumeVersion model — deterministic version tracking for tailored resumes.

The original resume text is never mutated: version ORIGINAL is a marker
record pointing at the untouched parse result; version APPROVED (and any
future revision) only ever adds a new record referencing which
modification_ids were approved. Persistence is modeled here even though
src/services/database.py isn't wired into the graph yet (see
docs/ARCHITECTURE.md's storage responsibilities table).
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class ResumeVersionStatus(str, Enum):
    ORIGINAL = "ORIGINAL"
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"


class ResumeVersion(BaseModel):
    resume_version_id: str = Field(..., min_length=1)
    candidate_id: str = Field(..., min_length=1)
    parent_version_id: str | None = None
    selected_job_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    approved_modification_ids: list[str] = Field(default_factory=list)
    status: ResumeVersionStatus
