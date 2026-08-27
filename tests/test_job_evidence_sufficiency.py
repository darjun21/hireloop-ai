"""
Tests for the pre-Phase-4 hardening: deterministic requirement-completeness
assessment. Does not touch the scoring formula -- only feeds JobQualityResult
flags/quality_score and, through the existing pipeline, OpportunityScore
confidence.
"""

from src.services.job_evidence_sufficiency import CompletenessLevel, assess_requirement_completeness
from tests.factories import build_job


# 1. One-skill sparse JD -- the observed Phase 3 case.
def test_one_skill_sparse_jd_is_low_completeness():
    job = build_job(
        required_skills=["Python"],
        preferred_skills=[],
        minimum_years_experience=2,
        description="Great opportunity, apply now for this exciting role at our fast-growing company.",
    )
    result = assess_requirement_completeness(job)

    assert result.level == CompletenessLevel.LOW
    assert result.signals["has_multiple_required_skills"] is False


# 2. Detailed JD -- fully specified.
def test_detailed_jd_is_high_completeness():
    job = build_job()  # factory default: 2 required, 1 preferred, min years, long description, work mode
    result = assess_requirement_completeness(job)

    assert result.level == CompletenessLevel.HIGH


# 3. Sparse but otherwise legitimate JD -- not flagged as "bad," just low-completeness.
def test_sparse_but_legitimate_jd_is_low_completeness_not_penalized_as_invalid():
    from src.models.enums import JobQualityRecommendation
    from src.services.job_quality import score_job_quality

    job = build_job(
        required_skills=["Python", "PostgreSQL"],
        preferred_skills=[],
        minimum_years_experience=None,
        description="Build and operate backend services powering our core product with a strong focus on reliability.",
    )
    completeness = assess_requirement_completeness(job)
    quality = score_job_quality(job)

    assert completeness.level == CompletenessLevel.LOW
    # Sparse is not automatically "bad": the job stays eligible (not LOW_QUALITY).
    assert quality.recommendation != JobQualityRecommendation.LOW_QUALITY


# 4. Missing experience requirement specifically.
def test_missing_experience_requirement_reduces_completeness():
    job = build_job(minimum_years_experience=None)
    with_exp = assess_requirement_completeness(build_job(minimum_years_experience=4))
    without_exp = assess_requirement_completeness(job)

    assert without_exp.completeness_score < with_exp.completeness_score
    assert without_exp.signals["has_experience_requirement"] is False


# 5. Detailed JD with a candidate mismatch: completeness is independent of match quality.
def test_completeness_is_independent_of_candidate_match_quality():
    from src.services.historical_signal import calculate_historical_signal
    from src.services.job_quality import score_job_quality
    from src.services.opportunity_scoring import score_opportunity
    from tests.factories import build_candidate

    job = build_job()  # HIGH completeness
    mismatched_candidate = build_candidate(skills=[], years_experience=0, target_roles=["Sales"])

    completeness = assess_requirement_completeness(job)
    score = score_opportunity(
        mismatched_candidate, job, score_job_quality(job), calculate_historical_signal("role", [])
    )

    assert completeness.level == CompletenessLevel.HIGH
    assert score.final_score < 50  # a poor match on a well-specified job scores low regardless of completeness


def test_job_quality_result_exposes_requirement_completeness_and_sparse_flag():
    from src.services.job_quality import score_job_quality

    sparse_job = build_job(required_skills=["Python"], preferred_skills=[], minimum_years_experience=None)
    result = score_job_quality(sparse_job)

    assert result.requirement_completeness == "LOW"
    assert "sparse_requirements" in result.flags


def test_sparse_job_does_not_reach_high_opportunity_score_confidence_from_full_match_alone():
    from src.models.enums import ConfidenceLevel
    from src.services.historical_signal import calculate_historical_signal
    from src.services.job_quality import score_job_quality
    from src.services.opportunity_scoring import score_opportunity
    from tests.factories import build_candidate

    job = build_job(required_skills=["Python"], preferred_skills=[], minimum_years_experience=None)
    candidate = build_candidate()  # satisfies the single requirement completely

    score = score_opportunity(candidate, job, score_job_quality(job), calculate_historical_signal("role", []))

    assert score.confidence != ConfidenceLevel.HIGH
