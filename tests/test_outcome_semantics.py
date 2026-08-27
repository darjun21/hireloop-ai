from src.config.outcomes import NEGATIVE_OUTCOMES, POSITIVE_OUTCOMES, UNRESOLVED_OUTCOMES, is_resolved
from src.models.enums import ApplicationStatus
from src.services.historical_signal import calculate_historical_signal
from tests.factories import build_application


def test_classification_partitions_every_status_exactly_once():
    all_statuses = set(ApplicationStatus)
    classified = POSITIVE_OUTCOMES | NEGATIVE_OUTCOMES | UNRESOLVED_OUTCOMES

    assert classified == all_statuses
    assert not (POSITIVE_OUTCOMES & NEGATIVE_OUTCOMES)
    assert not (POSITIVE_OUTCOMES & UNRESOLVED_OUTCOMES)
    assert not (NEGATIVE_OUTCOMES & UNRESOLVED_OUTCOMES)


def test_positive_outcomes_match_spec():
    assert POSITIVE_OUTCOMES == {
        ApplicationStatus.RECRUITER_RESPONSE,
        ApplicationStatus.INTERVIEW,
        ApplicationStatus.FINAL_ROUND,
        ApplicationStatus.OFFER,
    }


def test_negative_outcomes_match_spec():
    assert NEGATIVE_OUTCOMES == {ApplicationStatus.REJECTED}


def test_unresolved_outcomes_match_spec():
    assert UNRESOLVED_OUTCOMES == {
        ApplicationStatus.SAVED,
        ApplicationStatus.READY_FOR_REVIEW,
        ApplicationStatus.APPROVED,
        ApplicationStatus.APPLIED,
        ApplicationStatus.WITHDRAWN,
        ApplicationStatus.CLOSED,
    }


def test_is_resolved():
    assert is_resolved(ApplicationStatus.INTERVIEW) is True
    assert is_resolved(ApplicationStatus.REJECTED) is True
    assert is_resolved(ApplicationStatus.APPLIED) is False
    assert is_resolved(None) is False


def test_unresolved_applications_are_excluded_from_historical_sample_size():
    apps = [
        build_application(application_id="a1", current_status=ApplicationStatus.INTERVIEW),
        build_application(application_id="a2", current_status=ApplicationStatus.APPLIED),
        build_application(application_id="a3", current_status=ApplicationStatus.SAVED),
        build_application(application_id="a4", current_status=ApplicationStatus.WITHDRAWN),
    ]

    insight = calculate_historical_signal("AI Engineer", apps)

    # Only the single INTERVIEW outcome is resolved; the other three must
    # not count toward the sample at all.
    assert insight.sample_size == 1
