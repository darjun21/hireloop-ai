"""
Deterministic outcome analytics. No LLM anywhere in this module — the
Learning Agent interprets these numbers, it never computes them.

Counting rule (Part F): each application is counted exactly once,
regardless of how many events it accumulated. "Positive response",
"interview", and "offer" are each derived from whether that *milestone
was ever reached* across the application's event history, not just its
final status — an application that reached INTERVIEW and was later
REJECTED still counts as one interview, but is not double-counted as a
separate "successful application."
"""

from __future__ import annotations

from collections import defaultdict

from src.config.analytics import confidence_for_sample_size
from src.config.outcomes import NEGATIVE_OUTCOMES, POSITIVE_OUTCOMES, is_resolved
from src.models.application import Application
from src.models.application_event import ApplicationEvent
from src.models.enums import ApplicationEventType, ApplicationStatus
from src.models.outcome_analytics import GroupAnalytics, OutcomeAnalytics

_INTERVIEW_MILESTONES = frozenset(
    {ApplicationEventType.INTERVIEW, ApplicationEventType.FINAL_ROUND, ApplicationEventType.OFFER}
)
_POSITIVE_EVENT_TYPES = frozenset(
    {ApplicationEventType.RECRUITER_RESPONSE, ApplicationEventType.INTERVIEW, ApplicationEventType.FINAL_ROUND, ApplicationEventType.OFFER}
)


def _milestones(application: Application, events: list[ApplicationEvent]) -> set[ApplicationEventType]:
    milestones = {e.event_type for e in events}
    # Fold the application's own current_status in too, so demo/seed data
    # that doesn't carry a full event list still analyzes correctly.
    try:
        milestones.add(ApplicationEventType(application.current_status.value))
    except ValueError:
        pass
    return milestones


def _is_excluded(application: Application) -> bool:
    # WITHDRAWN is excluded from response-rate performance by default (Part F).
    return application.current_status == ApplicationStatus.WITHDRAWN


def _group_stats(group: str, applications: list[tuple[Application, list[ApplicationEvent]]]) -> GroupAnalytics | None:
    if not applications:
        return None

    sample_size = 0
    positive_responses = 0
    interviews = 0
    offers = 0
    rejections = 0
    scores: list[float] = []

    for application, events in applications:
        if application.opportunity_score is not None:
            scores.append(application.opportunity_score)

        if _is_excluded(application):
            continue
        if not is_resolved(application.current_status):
            continue  # still pending (SAVED/READY_FOR_REVIEW/APPROVED/APPLIED)

        sample_size += 1
        milestones = _milestones(application, events)

        if milestones & _POSITIVE_EVENT_TYPES:
            positive_responses += 1
        if milestones & _INTERVIEW_MILESTONES:
            interviews += 1
        if ApplicationEventType.OFFER in milestones:
            offers += 1
        if application.current_status == ApplicationStatus.REJECTED:
            rejections += 1

    def _rate(count: int) -> float:
        return round(count / sample_size, 4) if sample_size else 0.0

    return GroupAnalytics(
        group=group,
        sample_size=sample_size,
        positive_responses=positive_responses,
        interviews=interviews,
        offers=offers,
        rejections=rejections,
        response_rate=_rate(positive_responses),
        interview_rate=_rate(interviews),
        offer_rate=_rate(offers),
        rejection_rate=_rate(rejections),
        average_opportunity_score=round(sum(scores) / len(scores), 2) if scores else None,
        confidence=confidence_for_sample_size(sample_size),
    )


def _grouped(
    applications: list[tuple[Application, list[ApplicationEvent]]], key_fn
) -> dict[str, GroupAnalytics]:
    buckets: dict[str, list[tuple[Application, list[ApplicationEvent]]]] = defaultdict(list)
    for application, events in applications:
        key = key_fn(application)
        if key is None:
            continue
        buckets[key].append((application, events))

    result = {}
    for key, group_apps in buckets.items():
        stats = _group_stats(key, group_apps)
        if stats is not None:
            result[key] = stats
    return result


def compute_outcome_analytics(applications: list[tuple[Application, list[ApplicationEvent]]]) -> OutcomeAnalytics:
    total_resolved = sum(
        1 for app, _ in applications if not _is_excluded(app) and is_resolved(app.current_status)
    )

    return OutcomeAnalytics(
        by_role_family=_grouped(applications, lambda a: a.role_family),
        by_resume_version=_grouped(applications, lambda a: a.selected_resume_version_id),
        by_work_mode=_grouped(applications, lambda a: a.work_mode.value if a.work_mode else None),
        total_applications=len(applications),
        total_resolved=total_resolved,
    )
