"""ApplicationTrackerService / business database tests (Part A/R)."""

from datetime import datetime, timezone

import pytest

from src.models.application import Application
from src.models.application_event import ApplicationEvent
from src.models.enums import ApplicationEventType, ApplicationStatus
from src.services.application_tracker import ApplicationTrackerService
from src.services.database import get_connection, get_schema_version, init_schema


@pytest.fixture()
def tracker() -> ApplicationTrackerService:
    conn = get_connection(":memory:")
    init_schema(conn)
    return ApplicationTrackerService(conn)


def _app(application_id="app-1", candidate_id="cand-1") -> Application:
    return Application(
        application_id=application_id,
        candidate_id=candidate_id,
        job_id="job-1",
        opportunity_score=80.0,
        opportunity_score_version="v1.0",
        created_at=datetime.now(timezone.utc),
        current_status=ApplicationStatus.READY_FOR_REVIEW,
        role_family="AI Engineer",
    )


def test_schema_initializes_with_version(tracker):
    assert get_schema_version(tracker._conn) == 1


def test_create_and_get_application(tracker):
    tracker.create_application(_app())
    fetched = tracker.get_application("app-1")
    assert fetched.application_id == "app-1"
    assert fetched.current_status == ApplicationStatus.READY_FOR_REVIEW


def test_get_missing_application_returns_none(tracker):
    assert tracker.get_application("does-not-exist") is None


def test_update_application_status_does_not_lose_other_fields(tracker):
    app = _app()
    tracker.create_application(app)
    app.current_status = ApplicationStatus.APPLIED
    app.applied_at = datetime.now(timezone.utc)
    tracker.update_application_status(app)

    fetched = tracker.get_application("app-1")
    assert fetched.current_status == ApplicationStatus.APPLIED
    assert fetched.role_family == "AI Engineer"


def test_record_event_and_get_history_is_append_only(tracker):
    tracker.create_application(_app())
    tracker.record_event(
        ApplicationEvent(event_id="e1", application_id="app-1", candidate_id="cand-1", job_id="job-1", event_type=ApplicationEventType.APPLICATION_CREATED)
    )
    tracker.record_event(
        ApplicationEvent(event_id="e2", application_id="app-1", candidate_id="cand-1", job_id="job-1", event_type=ApplicationEventType.APPLIED)
    )

    history = tracker.get_application_history("app-1")
    assert [e.event_type.value for e in history] == ["APPLICATION_CREATED", "APPLIED"]


def test_list_applications_filters_by_candidate(tracker):
    tracker.create_application(_app("app-1", "cand-1"))
    tracker.create_application(_app("app-2", "cand-2"))

    cand1_apps = tracker.get_candidate_applications("cand-1")
    assert [a.application_id for a in cand1_apps] == ["app-1"]


def test_list_applications_can_exclude_demo_data(tracker):
    real = _app("app-real", "cand-1")
    demo = _app("app-demo", "cand-1").model_copy(update={"is_demo_data": True})
    tracker.create_application(real)
    tracker.create_application(demo)

    non_demo = tracker.list_applications(include_demo_data=False)
    assert [a.application_id for a in non_demo] == ["app-real"]

    all_apps = tracker.list_applications(include_demo_data=True)
    assert {a.application_id for a in all_apps} == {"app-real", "app-demo"}


def test_get_applications_with_history_pairs_correctly(tracker):
    tracker.create_application(_app())
    tracker.record_event(
        ApplicationEvent(event_id="e1", application_id="app-1", candidate_id="cand-1", job_id="job-1", event_type=ApplicationEventType.APPLICATION_CREATED)
    )

    pairs = tracker.get_applications_with_history(candidate_id="cand-1")
    assert len(pairs) == 1
    app, events = pairs[0]
    assert app.application_id == "app-1"
    assert len(events) == 1


def test_persist_and_list_strategy_insights(tracker):
    from src.models.enums import InsightCategory, SampleConfidence
    from src.models.learning_insight import LearningInsight

    insight = LearningInsight(
        insight_id="insight-1",
        category=InsightCategory.ROLE_FAMILY,
        observation="obs",
        evidence="evidence",
        sample_size=8,
        confidence=SampleConfidence.MEDIUM,
        recommendation="rec",
    )
    tracker.persist_strategy_insight(insight, candidate_id="cand-1")

    stored = tracker.list_strategy_insights(candidate_id="cand-1")
    assert len(stored) == 1
    assert stored[0].insight_id == "insight-1"
