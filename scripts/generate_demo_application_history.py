"""
One-off generator for data/demo_application_history.json. Not part of the
runtime app — run manually if the demo dataset needs regenerating:

    python -m scripts.generate_demo_application_history

Produces a deterministic, hand-designed set of ~20 synthetic historical
applications spanning AI Engineer / ML Engineer / Software Engineer /
Applied AI Engineer, matching the worked examples in
docs/LEARNING_LOOP.md and the Phase 5 spec exactly (AI Engineer: 8
applications, response_rate 50%, interview_rate 37.5%; Software Engineer:
7 applications, response_rate 14.3%).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.models.application import Application
from src.models.application_event import ApplicationEvent
from src.models.enums import ApplicationEventType, ApplicationStatus, WorkMode

CANDIDATE_ID = "demo-candidate-1"
BASE_DATE = datetime(2026, 5, 1, tzinfo=timezone.utc)

_WORK_MODES = [WorkMode.REMOTE, WorkMode.HYBRID, WorkMode.ONSITE]
_RESUME_VERSIONS = ["rv_1", "rv_2", "rv_3"]


def _funnel(*event_types: ApplicationEventType) -> list[ApplicationEventType]:
    return [ApplicationEventType.APPLICATION_CREATED, ApplicationEventType.APPLIED, *event_types]


# (role_family, funnel, opportunity_score)
_PLAN: dict[str, list[tuple[list[ApplicationEventType], float]]] = {
    "AI Engineer": [
        (_funnel(ApplicationEventType.RECRUITER_RESPONSE, ApplicationEventType.INTERVIEW, ApplicationEventType.FINAL_ROUND, ApplicationEventType.OFFER), 91.2),
        (_funnel(ApplicationEventType.RECRUITER_RESPONSE, ApplicationEventType.INTERVIEW), 86.4),
        (_funnel(ApplicationEventType.RECRUITER_RESPONSE, ApplicationEventType.INTERVIEW, ApplicationEventType.REJECTED), 79.8),
        (_funnel(ApplicationEventType.RECRUITER_RESPONSE), 74.1),
        (_funnel(ApplicationEventType.REJECTED), 68.5),
        (_funnel(ApplicationEventType.REJECTED), 71.9),
        (_funnel(ApplicationEventType.REJECTED), 65.3),
        (_funnel(ApplicationEventType.REJECTED), 70.0),
    ],
    "ML Engineer": [
        (_funnel(ApplicationEventType.RECRUITER_RESPONSE, ApplicationEventType.INTERVIEW, ApplicationEventType.FINAL_ROUND, ApplicationEventType.OFFER), 88.0),
        (_funnel(ApplicationEventType.RECRUITER_RESPONSE, ApplicationEventType.INTERVIEW), 82.3),
        (_funnel(ApplicationEventType.RECRUITER_RESPONSE), 77.6),
        (_funnel(ApplicationEventType.REJECTED), 66.2),
        (_funnel(ApplicationEventType.REJECTED), 69.4),
    ],
    "Software Engineer": [
        (_funnel(ApplicationEventType.RECRUITER_RESPONSE, ApplicationEventType.INTERVIEW), 75.0),
        (_funnel(ApplicationEventType.REJECTED), 60.1),
        (_funnel(ApplicationEventType.REJECTED), 58.7),
        (_funnel(ApplicationEventType.REJECTED), 62.4),
        (_funnel(ApplicationEventType.REJECTED), 59.9),
        (_funnel(ApplicationEventType.REJECTED), 61.0),
        (_funnel(ApplicationEventType.REJECTED), 57.3),
    ],
    "Applied AI Engineer": [
        ([ApplicationEventType.APPLICATION_CREATED, ApplicationEventType.APPLIED], 80.2),  # still pending
        ([ApplicationEventType.APPLICATION_CREATED, ApplicationEventType.SAVED], 76.5),  # not even applied yet
        (_funnel(ApplicationEventType.WITHDRAWN), 72.0),  # excluded from rates by default
    ],
}

# Final ApplicationStatus reached by the last event type in a funnel.
_EVENT_TO_STATUS = {
    ApplicationEventType.APPLICATION_CREATED: ApplicationStatus.READY_FOR_REVIEW,
    ApplicationEventType.SAVED: ApplicationStatus.SAVED,
    ApplicationEventType.APPLIED: ApplicationStatus.APPLIED,
    ApplicationEventType.RECRUITER_RESPONSE: ApplicationStatus.RECRUITER_RESPONSE,
    ApplicationEventType.INTERVIEW: ApplicationStatus.INTERVIEW,
    ApplicationEventType.FINAL_ROUND: ApplicationStatus.FINAL_ROUND,
    ApplicationEventType.OFFER: ApplicationStatus.OFFER,
    ApplicationEventType.REJECTED: ApplicationStatus.REJECTED,
    ApplicationEventType.WITHDRAWN: ApplicationStatus.WITHDRAWN,
}


def build_records() -> list[dict]:
    records = []
    seq = 0
    for role_family, entries in _PLAN.items():
        for i, (funnel, score) in enumerate(entries):
            seq += 1
            application_id = f"demo-app-{seq:03d}"
            job_id = f"demo-job-{seq:03d}"
            created_at = BASE_DATE + timedelta(days=seq)
            resume_version = _RESUME_VERSIONS[seq % len(_RESUME_VERSIONS)]
            work_mode = _WORK_MODES[seq % len(_WORK_MODES)]

            final_status = _EVENT_TO_STATUS[funnel[-1]]
            applied_at = created_at + timedelta(hours=1) if ApplicationEventType.APPLIED in funnel else None

            application = Application(
                application_id=application_id,
                candidate_id=CANDIDATE_ID,
                job_id=job_id,
                selected_resume_version_id=resume_version,
                opportunity_score=score,
                opportunity_score_version="v1.0",
                created_at=created_at,
                applied_at=applied_at,
                current_status=final_status,
                source="hireloop-demo",
                role_family=role_family,
                work_mode=work_mode,
                skill_cluster="python-ml" if role_family != "Software Engineer" else "backend",
                is_demo_data=True,
                notes=f"Synthetic demo history entry for {role_family}.",
            )

            events = []
            for j, event_type in enumerate(funnel):
                events.append(
                    ApplicationEvent(
                        event_id=f"{application_id}-ev-{j + 1}",
                        application_id=application_id,
                        candidate_id=CANDIDATE_ID,
                        job_id=job_id,
                        event_type=event_type,
                        occurred_at=created_at + timedelta(days=j * 3),
                        source="human" if event_type != ApplicationEventType.APPLICATION_CREATED else "system",
                    )
                )

            records.append(
                {
                    "application": json.loads(application.model_dump_json()),
                    "events": [json.loads(e.model_dump_json()) for e in events],
                }
            )
    return records


def main() -> None:
    records = build_records()
    output = {
        "is_demo_data": True,
        "description": (
            "Synthetic demo historical application data for HireLoop AI. Clearly marked "
            "is_demo_data=true on every record -- never mixed into real candidate analytics "
            "without the explicit DEMO_MODE boundary. See docs/LEARNING_LOOP.md."
        ),
        "candidate_id": CANDIDATE_ID,
        "applications": records,
    }
    out_path = Path(__file__).resolve().parent.parent / "data" / "demo_application_history.json"
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"Wrote {len(records)} demo applications to {out_path}")


if __name__ == "__main__":
    main()
