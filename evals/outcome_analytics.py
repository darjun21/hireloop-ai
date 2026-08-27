"""
Category 9: Outcome Analytics.

Verifies src/services/outcome_analytics.py computes counts correctly
against known synthetic (and the real seeded demo) application/event
history -- especially that a multi-stage progression (e.g. applied ->
interview -> offer) is counted exactly once, never as three separate
successes.
"""

from __future__ import annotations

from datetime import datetime, timezone

from src.models.application import Application
from src.models.application_event import ApplicationEvent
from src.models.enums import ApplicationEventType, ApplicationStatus, WorkMode
from src.services.demo_application_loader import load_demo_application_history
from src.services.outcome_analytics import compute_outcome_analytics
from evals.common import CategorySummary, EvalCase, summarize

CATEGORY = "outcome_analytics"


def _app(app_id: str, status: ApplicationStatus, role_family: str = "AI Engineer", **overrides) -> Application:
    defaults = dict(
        application_id=app_id, candidate_id="cand-1", job_id=f"job-{app_id}",
        opportunity_score_version="v1.0", current_status=status,
        created_at=datetime.now(timezone.utc), role_family=role_family,
    )
    defaults.update(overrides)
    return Application(**defaults)


def _event(app_id: str, event_type: ApplicationEventType, n: int = 0) -> ApplicationEvent:
    return ApplicationEvent(
        event_id=f"{app_id}-ev-{n}", application_id=app_id, candidate_id="cand-1", job_id=f"job-{app_id}",
        event_type=event_type,
    )


def run() -> CategorySummary:
    cases: list[EvalCase] = []

    # 1. A single application that progressed applied -> recruiter_response
    #    -> interview -> offer must count as exactly ONE application, ONE
    #    positive response, ONE interview, and ONE offer -- never three or
    #    four independent successes.
    progressed = _app("multi-1", ApplicationStatus.OFFER)
    events = [
        _event("multi-1", ApplicationEventType.APPLICATION_CREATED, 0),
        _event("multi-1", ApplicationEventType.APPLIED, 1),
        _event("multi-1", ApplicationEventType.RECRUITER_RESPONSE, 2),
        _event("multi-1", ApplicationEventType.INTERVIEW, 3),
        _event("multi-1", ApplicationEventType.OFFER, 4),
    ]
    analytics = compute_outcome_analytics([(progressed, events)])
    group = analytics.by_role_family["AI Engineer"]
    passed = (
        group.sample_size == 1
        and group.positive_responses == 1
        and group.interviews == 1
        and group.offers == 1
        and analytics.total_applications == 1
        and analytics.total_resolved == 1
    )
    cases.append(
        EvalCase(
            "analytics:multi_stage_progression_counted_once",
            CATEGORY,
            passed,
            detail=f"sample_size={group.sample_size} positive={group.positive_responses} "
            f"interviews={group.interviews} offers={group.offers}",
        )
    )

    # 2. A REJECTED application after reaching INTERVIEW still counts the
    #    interview milestone (it happened) but is excluded from a naive
    #    "successful applications" count -- interview and rejection are not
    #    mutually exclusive counters.
    rejected_after_interview = _app("multi-2", ApplicationStatus.REJECTED)
    events2 = [_event("multi-2", ApplicationEventType.INTERVIEW, 0), _event("multi-2", ApplicationEventType.REJECTED, 1)]
    analytics2 = compute_outcome_analytics([(rejected_after_interview, events2)])
    group2 = analytics2.by_role_family["AI Engineer"]
    passed = group2.interviews == 1 and group2.rejections == 1 and group2.sample_size == 1
    cases.append(
        EvalCase(
            "analytics:interview_then_rejected_both_counted_correctly",
            CATEGORY,
            passed,
            detail=f"interviews={group2.interviews} rejections={group2.rejections} sample_size={group2.sample_size}",
        )
    )

    # 3. WITHDRAWN applications are excluded from response-rate performance
    #    entirely (not counted as sample, not counted as positive/negative).
    withdrawn = _app("multi-3", ApplicationStatus.WITHDRAWN)
    analytics3 = compute_outcome_analytics([(withdrawn, [])])
    group3 = analytics3.by_role_family.get("AI Engineer")
    # The group still appears (the role family was seen), but WITHDRAWN
    # contributes to neither its sample_size nor total_resolved.
    passed = group3 is not None and group3.sample_size == 0 and analytics3.total_resolved == 0
    cases.append(
        EvalCase(
            "analytics:withdrawn_excluded_from_group_stats",
            CATEGORY,
            passed,
            detail=f"group_sample_size={group3.sample_size if group3 else None} total_resolved={analytics3.total_resolved}",
        )
    )

    # 4. Still-pending applications (SAVED/READY_FOR_REVIEW/APPROVED/APPLIED)
    #    are not counted as resolved outcomes at all.
    pending = _app("multi-4", ApplicationStatus.APPLIED)
    analytics4 = compute_outcome_analytics([(pending, [])])
    passed = analytics4.total_resolved == 0 and analytics4.total_applications == 1
    cases.append(
        EvalCase(
            "analytics:pending_application_not_counted_as_resolved",
            CATEGORY,
            passed,
            detail=f"total_resolved={analytics4.total_resolved} total_applications={analytics4.total_applications}",
        )
    )

    # 5. Grouping is correct across multiple role families -- one group's
    #    counts never leak into another's.
    a1 = _app("g1", ApplicationStatus.OFFER, role_family="AI Engineer")
    a2 = _app("g2", ApplicationStatus.REJECTED, role_family="Data Scientist")
    events_g1 = [_event("g1", ApplicationEventType.OFFER, 0)]
    events_g2 = [_event("g2", ApplicationEventType.REJECTED, 0)]
    analytics5 = compute_outcome_analytics([(a1, events_g1), (a2, events_g2)])
    ai_group = analytics5.by_role_family["AI Engineer"]
    ds_group = analytics5.by_role_family["Data Scientist"]
    passed = ai_group.sample_size == 1 and ai_group.offers == 1 and ds_group.sample_size == 1 and ds_group.offers == 0
    cases.append(
        EvalCase(
            "analytics:role_family_groups_do_not_leak",
            CATEGORY,
            passed,
            detail=f"ai_offers={ai_group.offers} ds_offers={ds_group.offers}",
        )
    )

    # 6. By-work-mode grouping.
    remote_app = _app("wm-1", ApplicationStatus.INTERVIEW, work_mode=WorkMode.REMOTE)
    analytics6 = compute_outcome_analytics([(remote_app, [_event("wm-1", ApplicationEventType.INTERVIEW, 0)])])
    passed = "REMOTE" in analytics6.by_work_mode and analytics6.by_work_mode["REMOTE"].interviews == 1
    cases.append(EvalCase("analytics:work_mode_grouping_correct", CATEGORY, passed, detail=str(analytics6.by_work_mode.keys())))

    # 7. Real seeded demo data (data/demo_application_history.json) loads
    #    and computes without error, and total counts are internally
    #    consistent (every application counted exactly once overall).
    demo_records = load_demo_application_history()
    demo_analytics = compute_outcome_analytics(demo_records)
    passed = demo_analytics.total_applications == len(demo_records) and demo_analytics.total_resolved <= demo_analytics.total_applications
    cases.append(
        EvalCase(
            "analytics:real_seeded_demo_data_computes_consistently",
            CATEGORY,
            passed,
            detail=f"total_applications={demo_analytics.total_applications} total_resolved={demo_analytics.total_resolved} "
            f"records_loaded={len(demo_records)}",
        )
    )

    return summarize(CATEGORY, cases)


if __name__ == "__main__":
    result = run()
    print(result.to_dict())
