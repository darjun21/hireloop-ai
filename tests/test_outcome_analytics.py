"""Outcome analytics tests (Part S). No LLM involved -- purely deterministic."""

from datetime import datetime, timezone

from src.models.application_event import ApplicationEvent
from src.models.enums import ApplicationEventType, ApplicationStatus, SampleConfidence
from src.services.outcome_analytics import compute_outcome_analytics
from tests.factories import build_application


def _events(application_id, *event_types) -> list[ApplicationEvent]:
    return [
        ApplicationEvent(
            event_id=f"{application_id}-ev-{i}",
            application_id=application_id,
            candidate_id="cand-1",
            job_id="job-1",
            event_type=et,
            occurred_at=datetime.now(timezone.utc),
        )
        for i, et in enumerate(event_types)
    ]


def _app(app_id, role_family, status, resume_version="rv_1", work_mode=None, score=80.0):
    return build_application(
        application_id=app_id,
        current_status=status,
        role_family=role_family,
        selected_resume_version_id=resume_version,
        work_mode=work_mode,
        opportunity_score=score,
    )


# 1. 0 applications.
def test_zero_applications():
    analytics = compute_outcome_analytics([])
    assert analytics.total_applications == 0
    assert analytics.total_resolved == 0
    assert analytics.by_role_family == {}


# 2. Only unresolved applications.
def test_only_unresolved_applications_excluded_from_group_sample():
    apps = [
        (_app("a1", "AI Engineer", ApplicationStatus.APPLIED), []),
        (_app("a2", "AI Engineer", ApplicationStatus.SAVED), []),
    ]
    analytics = compute_outcome_analytics(apps)
    assert analytics.total_applications == 2
    assert analytics.total_resolved == 0
    # The group is still visible (useful for a UI to show "0 resolved so far"),
    # but its resolved sample is correctly zero and confidence reflects that.
    group = analytics.by_role_family["AI Engineer"]
    assert group.sample_size == 0
    assert group.confidence == SampleConfidence.INSUFFICIENT


# 3. One rejected application.
def test_one_rejected_application():
    apps = [(_app("a1", "AI Engineer", ApplicationStatus.REJECTED), _events("a1", ApplicationEventType.REJECTED))]
    analytics = compute_outcome_analytics(apps)
    group = analytics.by_role_family["AI Engineer"]
    assert group.sample_size == 1
    assert group.rejections == 1
    assert group.positive_responses == 0
    assert group.confidence == SampleConfidence.INSUFFICIENT


# 4. Small sample.
def test_small_sample_gets_low_confidence():
    apps = [
        (_app(f"a{i}", "ML Engineer", ApplicationStatus.REJECTED), _events(f"a{i}", ApplicationEventType.REJECTED))
        for i in range(4)
    ]
    analytics = compute_outcome_analytics(apps)
    assert analytics.by_role_family["ML Engineer"].confidence == SampleConfidence.LOW


# 5 & 6. Larger AI Engineer / Software Engineer samples (from real demo data).
def test_larger_samples_from_demo_data_match_spec_examples():
    from src.services.demo_application_loader import load_demo_application_history

    analytics = compute_outcome_analytics(load_demo_application_history())

    ai = analytics.by_role_family["AI Engineer"]
    assert ai.sample_size == 8
    assert round(ai.response_rate * 100, 1) == 50.0
    assert round(ai.interview_rate * 100, 1) == 37.5

    swe = analytics.by_role_family["Software Engineer"]
    assert swe.sample_size == 7
    assert round(swe.response_rate * 100, 1) == 14.3


# 7, 8, 9. One application progresses through multiple positive stages --
# counted once, interview counted once, offer counted once.
def test_application_progressing_through_funnel_counts_once_not_multiple_times():
    events = _events(
        "a1",
        ApplicationEventType.RECRUITER_RESPONSE,
        ApplicationEventType.INTERVIEW,
        ApplicationEventType.FINAL_ROUND,
        ApplicationEventType.OFFER,
    )
    apps = [(_app("a1", "AI Engineer", ApplicationStatus.OFFER), events)]
    analytics = compute_outcome_analytics(apps)
    group = analytics.by_role_family["AI Engineer"]

    assert group.sample_size == 1
    assert group.positive_responses == 1  # not 3 (recruiter_response + interview + offer)
    assert group.interviews == 1
    assert group.offers == 1


def test_interview_counted_even_if_later_rejected():
    events = _events("a1", ApplicationEventType.RECRUITER_RESPONSE, ApplicationEventType.INTERVIEW, ApplicationEventType.REJECTED)
    apps = [(_app("a1", "AI Engineer", ApplicationStatus.REJECTED), events)]
    analytics = compute_outcome_analytics(apps)
    group = analytics.by_role_family["AI Engineer"]

    assert group.interviews == 1  # milestone reached, even though final status is REJECTED
    assert group.rejections == 1
    assert group.positive_responses == 1  # recruiter_response/interview did happen


# 10. Withdrawn excluded appropriately.
def test_withdrawn_excluded_from_rate_denominator():
    apps = [
        (_app("a1", "AI Engineer", ApplicationStatus.REJECTED), _events("a1", ApplicationEventType.REJECTED)),
        (_app("a2", "AI Engineer", ApplicationStatus.WITHDRAWN), _events("a2", ApplicationEventType.WITHDRAWN)),
    ]
    analytics = compute_outcome_analytics(apps)
    group = analytics.by_role_family["AI Engineer"]

    assert analytics.total_applications == 2
    assert group.sample_size == 1  # only the rejected one counts


# 11. Demo data isolated from real data (DEMO_MODE boundary).
def test_demo_data_marked_and_can_be_excluded():
    from src.services.demo_application_loader import load_demo_application_history

    demo_records = load_demo_application_history()
    assert all(app.is_demo_data for app, _ in demo_records)

    real_app = _app("real-1", "AI Engineer", ApplicationStatus.REJECTED)
    assert real_app.is_demo_data is False


# 12. Resume version comparison.
def test_resume_version_grouping():
    apps = [
        (_app("a1", "AI Engineer", ApplicationStatus.INTERVIEW, resume_version="rv_1"), _events("a1", ApplicationEventType.RECRUITER_RESPONSE, ApplicationEventType.INTERVIEW)),
        (_app("a2", "AI Engineer", ApplicationStatus.REJECTED, resume_version="rv_2"), _events("a2", ApplicationEventType.REJECTED)),
    ]
    analytics = compute_outcome_analytics(apps)
    assert analytics.by_resume_version["rv_1"].interview_rate == 1.0
    assert analytics.by_resume_version["rv_2"].interview_rate == 0.0


# 13. Work-mode comparison.
def test_work_mode_grouping():
    from src.models.enums import WorkMode

    apps = [
        (_app("a1", "AI Engineer", ApplicationStatus.INTERVIEW, work_mode=WorkMode.REMOTE), _events("a1", ApplicationEventType.RECRUITER_RESPONSE, ApplicationEventType.INTERVIEW)),
        (_app("a2", "AI Engineer", ApplicationStatus.REJECTED, work_mode=WorkMode.ONSITE), _events("a2", ApplicationEventType.REJECTED)),
    ]
    analytics = compute_outcome_analytics(apps)
    assert analytics.by_work_mode["REMOTE"].interview_rate == 1.0
    assert analytics.by_work_mode["ONSITE"].interview_rate == 0.0


# 14. Analytics remain deterministic.
def test_analytics_are_deterministic():
    apps = [(_app("a1", "AI Engineer", ApplicationStatus.REJECTED), _events("a1", ApplicationEventType.REJECTED))]
    first = compute_outcome_analytics(apps)
    second = compute_outcome_analytics(apps)
    assert first.by_role_family["AI Engineer"].model_dump(exclude={"group"}) == second.by_role_family["AI Engineer"].model_dump(exclude={"group"})


# 15. Rates always between 0 and 1.
def test_rates_always_between_zero_and_one():
    from src.services.demo_application_loader import load_demo_application_history

    analytics = compute_outcome_analytics(load_demo_application_history())
    for group_map in (analytics.by_role_family, analytics.by_resume_version, analytics.by_work_mode):
        for group in group_map.values():
            for rate in (group.response_rate, group.interview_rate, group.offer_rate, group.rejection_rate):
                assert 0.0 <= rate <= 1.0
