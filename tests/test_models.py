"""
Validation tests for core domain models: rejecting out-of-range scores,
negative experience, invalid salary ranges, impossible confidence values,
and missing required identifiers.
"""

import pytest
from pydantic import ValidationError

from src.models.enums import (
    ApplicationStatus,
    ConfidenceLevel,
    EvidenceSourceType,
    RecommendationBand,
)
from src.models.evidence import Evidence
from src.models.job import JobPosting
from src.models.scoring import ComponentScore, OpportunityScore
from tests.factories import build_application, build_candidate, build_job


def _evidence(**overrides) -> dict:
    defaults = dict(
        evidence_id="ev-1",
        source_type=EvidenceSourceType.RESUME,
        source_section="Work Experience",
        source_text="Built and shipped a production recommendation service.",
        confidence=0.9,
    )
    defaults.update(overrides)
    return defaults


def test_candidate_profile_valid_defaults():
    candidate = build_candidate()
    assert candidate.candidate_id == "cand-1"
    assert candidate.years_experience == 6


def test_candidate_profile_requires_candidate_id():
    with pytest.raises(ValidationError):
        build_candidate(candidate_id="")


def test_candidate_profile_rejects_negative_experience():
    with pytest.raises(ValidationError):
        build_candidate(years_experience=-1)


def test_job_posting_requires_job_id():
    with pytest.raises(ValidationError):
        build_job(job_id="")


def test_job_posting_optional_fields_can_be_omitted():
    job = JobPosting(job_id="j1", title="Engineer", company="Acme")
    assert job.location is None
    assert job.salary_min is None
    assert job.salary_max is None


def test_job_posting_rejects_invalid_salary_range():
    with pytest.raises(ValidationError):
        build_job(salary_min=150_000, salary_max=90_000)


def test_job_posting_accepts_valid_salary_range():
    job = build_job(salary_min=90_000, salary_max=150_000)
    assert job.salary_min < job.salary_max


def test_evidence_rejects_confidence_above_one():
    with pytest.raises(ValidationError):
        Evidence(**_evidence(confidence=1.5))


def test_evidence_rejects_confidence_below_zero():
    with pytest.raises(ValidationError):
        Evidence(**_evidence(confidence=-0.1))


def test_evidence_accepts_boundary_confidence_values():
    assert Evidence(**_evidence(confidence=0.0)).confidence == 0.0
    assert Evidence(**_evidence(confidence=1.0)).confidence == 1.0


def test_component_score_rejects_value_below_zero():
    with pytest.raises(ValidationError):
        ComponentScore(name="skill_match", value=-1, weight=0.3, weighted_contribution=0)


def test_component_score_rejects_value_above_hundred():
    with pytest.raises(ValidationError):
        ComponentScore(name="skill_match", value=101, weight=0.3, weighted_contribution=0)


def test_opportunity_score_rejects_final_score_out_of_range():
    component = ComponentScore(name="skill_match", value=50, weight=0.3, weighted_contribution=15)
    with pytest.raises(ValidationError):
        OpportunityScore(
            job_id="j1",
            candidate_id="c1",
            scoring_version="v1.0",
            components={"skill_match": component},
            final_score=150,
            recommendation=RecommendationBand.CONSIDER,
            confidence=ConfidenceLevel.HIGH,
        )


def test_application_requires_candidate_and_job_ids():
    with pytest.raises(ValidationError):
        build_application(candidate_id="")
    with pytest.raises(ValidationError):
        build_application(job_id="")


def test_application_defaults_and_current_status():
    application = build_application(current_status=ApplicationStatus.OFFER)
    assert application.current_status == ApplicationStatus.OFFER
