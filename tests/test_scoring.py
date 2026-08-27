"""
Tests for the versioned scoring configuration (Part B) and the
deterministic Opportunity Scoring Engine (Part F).
"""

from src.config.scoring import MAX_HISTORY_SIGNAL_WEIGHT, SCORING_MODEL_VERSION, get_scoring_config
from src.models.enums import ConfidenceLevel, EmploymentType, RecommendationBand, WorkMode
from src.services.historical_signal import calculate_historical_signal
from src.services.job_quality import score_job_quality
from src.services.opportunity_scoring import score_opportunity
from tests.factories import build_application, build_candidate, build_job


# ---------------------------------------------------------------------------
# Part B: scoring configuration invariants
# ---------------------------------------------------------------------------


def test_weights_sum_to_one():
    _, weights = get_scoring_config()
    assert round(weights.total(), 6) == 1.0


def test_historical_signal_weight_never_exceeds_configured_cap():
    _, weights = get_scoring_config()
    assert weights.historical_signal <= MAX_HISTORY_SIGNAL_WEIGHT


def test_get_scoring_config_returns_current_version():
    version, _ = get_scoring_config()
    assert version == SCORING_MODEL_VERSION


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _neutral_history():
    return calculate_historical_signal("AI Engineer", [])


def _strong_history():
    from src.models.enums import ApplicationStatus

    apps = [
        build_application(
            application_id=f"a{i}",
            current_status=ApplicationStatus.INTERVIEW if i < 12 else ApplicationStatus.REJECTED,
        )
        for i in range(15)
    ]
    return calculate_historical_signal("AI Engineer", apps)


def _good_quality(job):
    return score_job_quality(job)


# ---------------------------------------------------------------------------
# Part F: Opportunity Scoring Engine
# ---------------------------------------------------------------------------


def test_case_1_perfect_match_scores_high_priority():
    candidate = build_candidate()
    job = build_job()

    score = score_opportunity(candidate, job, _good_quality(job), _strong_history())

    assert score.final_score >= 90
    assert score.recommendation == RecommendationBand.HIGH_PRIORITY
    assert score.confidence == ConfidenceLevel.HIGH
    assert score.scoring_version == SCORING_MODEL_VERSION


def test_case_2_strong_skill_match_but_experience_mismatch():
    candidate = build_candidate(years_experience=1)
    job = build_job(minimum_years_experience=8)

    score = score_opportunity(candidate, job, _good_quality(job), _neutral_history())

    assert score.components["skill_match"].value == 100.0
    assert score.components["experience_match"].value == 0.0


def test_case_3_strong_experience_but_poor_role_alignment():
    candidate = build_candidate(years_experience=10, target_roles=["Data Analyst"])
    job = build_job(title="Enterprise Account Executive", minimum_years_experience=3)

    score = score_opportunity(candidate, job, _good_quality(job), _neutral_history())

    assert score.components["experience_match"].value == 100.0
    assert score.components["role_alignment"].value < 50.0


def test_case_4_location_mismatch_scores_low():
    candidate = build_candidate(
        preferred_work_modes=[WorkMode.REMOTE],
        target_locations=["New York, NY"],
    )
    job = build_job(work_mode=WorkMode.ONSITE, location="Austin, TX")

    score = score_opportunity(candidate, job, _good_quality(job), _neutral_history())

    assert score.components["location_work_mode"].value == 20.0


def test_case_5_remote_preference_match_wins_regardless_of_location():
    candidate = build_candidate(
        preferred_work_modes=[WorkMode.REMOTE],
        target_locations=["New York, NY"],
    )
    job = build_job(work_mode=WorkMode.REMOTE, location="Austin, TX")

    score = score_opportunity(candidate, job, _good_quality(job), _neutral_history())

    assert score.components["location_work_mode"].value == 100.0


def test_case_6_missing_job_description_reduces_job_quality_component():
    candidate = build_candidate()
    complete_job = build_job()
    incomplete_job = build_job(job_id="job-2", description=None)

    complete_score = score_opportunity(candidate, complete_job, _good_quality(complete_job), _neutral_history())
    incomplete_score = score_opportunity(candidate, incomplete_job, _good_quality(incomplete_job), _neutral_history())

    assert complete_score.components["job_quality"].value == 100.0
    assert incomplete_score.components["job_quality"].value < 100.0
    assert incomplete_score.components["job_quality"].missing_data is True
    assert incomplete_score.final_score < complete_score.final_score


def test_case_7_missing_candidate_history_is_neutral_component():
    candidate = build_candidate()
    job = build_job()

    score = score_opportunity(candidate, job, _good_quality(job), _neutral_history())

    assert score.components["historical_signal"].value == 50.0
    assert score.components["historical_signal"].missing_data is True
    assert score.historical_sample_size == 0


def test_case_8_sparse_historical_data_stays_close_to_neutral_component():
    from src.models.enums import ApplicationStatus

    sparse_apps = [
        build_application(application_id="a1", current_status=ApplicationStatus.INTERVIEW),
        build_application(application_id="a2", current_status=ApplicationStatus.REJECTED),
        build_application(application_id="a3", current_status=ApplicationStatus.REJECTED),
    ]
    sparse_history = calculate_historical_signal("AI Engineer", sparse_apps)

    candidate = build_candidate()
    job = build_job()
    score = score_opportunity(candidate, job, _good_quality(job), sparse_history)

    assert abs(score.components["historical_signal"].value - 50.0) < 20
    assert score.historical_sample_size == 3


def test_case_9_missing_skills_and_experience_data_yields_neutral_components_and_lower_confidence():
    candidate = build_candidate(target_roles=[], preferred_work_modes=[])
    job = build_job(required_skills=[], preferred_skills=[], minimum_years_experience=None, work_mode=None, location=None)

    score = score_opportunity(candidate, job, _good_quality(job), _neutral_history())

    assert score.components["skill_match"].missing_data is True
    assert score.components["experience_match"].missing_data is True
    assert score.confidence in (ConfidenceLevel.LOW, ConfidenceLevel.MEDIUM)


def test_scores_always_stay_within_zero_to_hundred_even_for_extreme_mismatch():
    candidate = build_candidate(years_experience=0)
    job = build_job(minimum_years_experience=40)

    score = score_opportunity(candidate, job, _good_quality(job), _neutral_history())

    assert 0 <= score.final_score <= 100
    for component in score.components.values():
        assert 0 <= component.value <= 100


def test_historical_signal_never_exceeds_its_configured_influence():
    candidate = build_candidate()
    job = build_job()

    score = score_opportunity(candidate, job, _good_quality(job), _strong_history())

    historical = score.components["historical_signal"]
    assert historical.weight == MAX_HISTORY_SIGNAL_WEIGHT
    assert historical.weighted_contribution <= 100 * MAX_HISTORY_SIGNAL_WEIGHT


def test_scoring_version_is_always_persisted():
    candidate = build_candidate()
    job = build_job()

    score = score_opportunity(candidate, job, _good_quality(job), _neutral_history())

    assert score.scoring_version == SCORING_MODEL_VERSION
    assert score.scoring_version != ""


def test_recommendation_bands_at_boundaries():
    from src.services.opportunity_scoring import _recommendation_for

    assert _recommendation_for(90) == RecommendationBand.HIGH_PRIORITY
    assert _recommendation_for(89.99) == RecommendationBand.STRONG_MATCH
    assert _recommendation_for(80) == RecommendationBand.STRONG_MATCH
    assert _recommendation_for(79.99) == RecommendationBand.CONSIDER
    assert _recommendation_for(70) == RecommendationBand.CONSIDER
    assert _recommendation_for(69.99) == RecommendationBand.LOW_PRIORITY
