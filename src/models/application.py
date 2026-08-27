"""
Application domain model.

Represents one candidate's pursuit of one job. `current_status` is a
cached/derived summary of the append-only ApplicationEvent history
(src/models/application_event.py) — it is convenient to query and display,
but the events are the durable record. Never overwrite event history when
`current_status` changes; always append a new ApplicationEvent instead
(src/services/application_tracker.py enforces this).

`role_family` / `work_mode` / `skill_cluster` are denormalized directly
onto Application (rather than requiring a join through JobPosting) so
analytics can group cheaply and so seeded demo history
(`is_demo_data=True`) doesn't need synthetic JobPosting rows to be
meaningful.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from src.models.enums import ApplicationStatus, WorkMode


class Application(BaseModel):
    application_id: str = Field(..., min_length=1)
    candidate_id: str = Field(..., min_length=1)
    job_id: str = Field(..., min_length=1)

    selected_resume_version_id: str | None = None
    opportunity_score: float | None = Field(default=None, ge=0, le=100)
    opportunity_score_version: str = Field(..., min_length=1)

    created_at: datetime
    applied_at: datetime | None = None
    current_status: ApplicationStatus = ApplicationStatus.SAVED

    source: str = "hireloop"
    notes: str | None = None

    # Denormalized grouping fields for analytics (Part G/H).
    role_family: str | None = None
    work_mode: WorkMode | None = None
    skill_cluster: str | None = None

    # Never mixed into real analytics without an explicit DEMO_MODE
    # boundary — see docs/LEARNING_LOOP.md.
    is_demo_data: bool = False
