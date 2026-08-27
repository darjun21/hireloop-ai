"""
Candidate domain models.

CandidateProfile is the structured representation produced from a parsed
resume (by the Profile Agent, in a later phase). Every claim-bearing nested
model (Skill, WorkExperience, Project, Certification) can retain Evidence so
Truth Guard can later check tailored resume claims against something
concrete rather than trusting the LLM's own output.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.models.enums import EmploymentType, WorkMode
from src.models.evidence import Evidence


class Skill(BaseModel):
    name: str = Field(..., min_length=1)
    evidence: list[Evidence] = Field(default_factory=list)


class Education(BaseModel):
    institution: str = Field(..., min_length=1)
    degree: str | None = None
    field_of_study: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)


class WorkExperience(BaseModel):
    company: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    start_date: str | None = None
    end_date: str | None = None
    description: str | None = None
    skills_used: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)


class Project(BaseModel):
    name: str = Field(..., min_length=1)
    description: str | None = None
    skills_used: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)


class Certification(BaseModel):
    name: str = Field(..., min_length=1)
    issuer: str | None = None
    date: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)


class EmploymentPreferences(BaseModel):
    employment_types: list[EmploymentType] = Field(default_factory=list)
    minimum_salary: float | None = Field(default=None, ge=0)
    notes: str | None = None


class CandidateProfile(BaseModel):
    candidate_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    professional_summary: str = ""
    years_experience: float = Field(..., ge=0)

    skills: list[Skill] = Field(default_factory=list)
    target_roles: list[str] = Field(default_factory=list)
    target_locations: list[str] = Field(default_factory=list)
    preferred_work_modes: list[WorkMode] = Field(default_factory=list)
    employment_preferences: EmploymentPreferences = Field(default_factory=EmploymentPreferences)

    education: list[Education] = Field(default_factory=list)
    work_experience: list[WorkExperience] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    certifications: list[Certification] = Field(default_factory=list)

    # Resume-level evidence not tied to a specific skill/experience/project.
    source_evidence: list[Evidence] = Field(default_factory=list)
