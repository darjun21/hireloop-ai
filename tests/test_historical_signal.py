from src.models.enums import ApplicationStatus, ConfidenceLevel
from src.services.historical_signal import calculate_historical_signal
from tests.factories import build_application


def _applications(n: int, positive: int) -> list:
    apps = []
    for i in range(n):
        outcome = ApplicationStatus.INTERVIEW if i < positive else ApplicationStatus.REJECTED
        apps.append(build_application(application_id=f"app-{i}", current_status=outcome))
    return apps


def test_zero_history_is_exactly_neutral():
    insight = calculate_historical_signal("AI Engineer", [])

    assert insight.sample_size == 0
    assert insight.success_rate is None
    assert insight.signal_value == 50.0
    assert insight.is_neutral is True
    assert insight.confidence == ConfidenceLevel.LOW


def test_single_application_stays_close_to_neutral():
    positive = calculate_historical_signal("AI Engineer", _applications(1, 1))
    negative = calculate_historical_signal("AI Engineer", _applications(1, 0))

    assert abs(positive.signal_value - 50.0) < 15
    assert abs(negative.signal_value - 50.0) < 15
    assert positive.is_neutral is True
    assert negative.is_neutral is True


def test_small_sample_does_not_produce_extreme_score():
    insight = calculate_historical_signal("AI Engineer", _applications(3, 3))

    # Even a perfect 3/3 record should be pulled well away from 100.
    assert insight.signal_value < 80
    assert insight.confidence in (ConfidenceLevel.LOW, ConfidenceLevel.MEDIUM)


def test_sparse_data_stays_reasonably_close_to_neutral():
    insight = calculate_historical_signal("AI Engineer", _applications(3, 1))

    assert abs(insight.signal_value - 50.0) < 20


def test_larger_sample_with_high_success_rate_pulls_signal_up():
    insight = calculate_historical_signal("AI Engineer", _applications(20, 15))

    assert insight.sample_size == 20
    assert insight.signal_value > 60
    assert insight.confidence == ConfidenceLevel.HIGH
    assert insight.is_neutral is False


def test_larger_sample_with_low_success_rate_pulls_signal_down():
    insight = calculate_historical_signal("AI Engineer", _applications(20, 2))

    assert insight.signal_value < 40
    assert insight.confidence == ConfidenceLevel.HIGH


def test_explanation_never_claims_causation():
    insight = calculate_historical_signal("AI Engineer", _applications(20, 15))

    assert "causal" in insight.explanation.lower()
    assert "not causal evidence" in insight.explanation.lower()


def test_signal_value_always_within_bounds():
    for n, positive in [(0, 0), (1, 1), (1, 0), (50, 50), (50, 0)]:
        insight = calculate_historical_signal("Role", _applications(n, positive))
        assert 0 <= insight.signal_value <= 100
