"""
JobPosting domain model.

Job-board data is inherently incomplete — most fields beyond identity and
title are optional so a sparse listing can still be ingested. Missing data
is handled downstream by job quality scoring and score confidence, not by
validation errors here.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field, model_validator

from src.models.enums import EmploymentType, WorkMode


class JobPosting(BaseModel):
    job_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    # Not min_length-constrained: a missing company is a real-world quality
    # issue (see src/services/job_quality.py's "missing_company" flag), not
    # a structural validation error — bad source data should be ingestable
    # and then flagged, not rejected.
    company: str = ""

    location: str | None = None
    source: str | None = None
    url: str | None = None
    description: str | None = None

    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    minimum_years_experience: float | None = Field(default=None, ge=0)

    employment_type: EmploymentType | None = None
    work_mode: WorkMode | None = None
    posted_date: date | None = None

    salary_min: float | None = Field(default=None, ge=0)
    salary_max: float | None = Field(default=None, ge=0)

    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_salary_range(self) -> "JobPosting":
        if self.salary_min is not None and self.salary_max is not None:
            if self.salary_min > self.salary_max:
                raise ValueError("salary_min must not exceed salary_max")
        return self
