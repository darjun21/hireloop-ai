"""
ApplicationEvent — append-only history for one Application.

The journey of an application is never modeled as a single mutable status
field alone. `Application.current_status` is a cached summary; this is the
durable, ordered record analytics and the Learning Agent actually read
from. Events are never deleted or rewritten — a correction is a new event,
never an edit to an old one.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from src.models.enums import ApplicationEventType


class ApplicationEvent(BaseModel):
    event_id: str = Field(..., min_length=1)
    application_id: str = Field(..., min_length=1)
    candidate_id: str = Field(..., min_length=1)
    job_id: str = Field(..., min_length=1)

    event_type: ApplicationEventType
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    source: str = "human"  # "human" | "system"
    notes: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
