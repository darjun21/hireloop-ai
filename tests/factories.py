"""
Small test-only factory helpers for building valid CandidateProfile /
JobPosting / Application instances with sensible defaults, so individual
tests only need to override the fields relevant to what they're checking.
"""

from __future__ import annotations

from datetime import datetime, timezone

from src.models.application import Application
from src.models.candidate import CandidateProfile, EmploymentPreferences, Skill
from src.models.enums import ApplicationStatus, EmploymentType, WorkMode
from src.models.job import JobPosting

LONG_DESCRIPTION = (
    "We are hiring an experienced engineer to design, build, and operate production "
    "systems end to end. You will collaborate closely with product and design, own "
    "services from prototype through scale, and mentor other engineers on the team."
)


def build_candidate(**overrides) -> CandidateProfile:
    defaults = dict(
        candidate_id="cand-1",
        name="Jane Doe",
        professional_summary="Experienced engineer.",
        years_experience=6,
        skills=[Skill(name="Python"), Skill(name="Machine Learning"), Skill(name="JS")],
        target_roles=["Senior AI Engineer"],
        target_locations=["New York, NY"],
        preferred_work_modes=[WorkMode.REMOTE],
        employment_preferences=EmploymentPreferences(employment_types=[EmploymentType.FULL_TIME]),
    )
    defaults.update(overrides)
    return CandidateProfile(**defaults)


def build_job(**overrides) -> JobPosting:
    defaults = dict(
        job_id="job-1",
        title="Sr. AI Engineer",
        company="Acme Inc.",
        location="New York, NY",
        url="https://boards.example.com/jobs/123",
        description=LONG_DESCRIPTION,
        required_skills=["Python", "Machine Learning"],
        preferred_skills=["JS"],
        minimum_years_experience=4,
        employment_type=EmploymentType.FULL_TIME,
        work_mode=WorkMode.REMOTE,
    )
    defaults.update(overrides)
    return JobPosting(**defaults)


def build_application(**overrides) -> Application:
    defaults = dict(
        application_id="app-1",
        candidate_id="cand-1",
        job_id="job-1",
        opportunity_score_version="v1.0",
        current_status=ApplicationStatus.APPLIED,
        created_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return Application(**defaults)
