"""
ApplicationTrackerService — the only way any agent or graph node touches
application/event/strategy-insight rows. No raw SQL reaches callers.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from src.models.application import Application
from src.models.application_event import ApplicationEvent
from src.models.learning_insight import LearningInsight


class ApplicationTrackerService:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # --- applications ---

    def create_application(self, application: Application) -> Application:
        self._conn.execute(
            """
            INSERT INTO applications (
                application_id, candidate_id, job_id, role_family, work_mode, skill_cluster,
                selected_resume_version_id, opportunity_score, opportunity_score_version,
                current_status, source, is_demo_data, created_at, applied_at, data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                application.application_id,
                application.candidate_id,
                application.job_id,
                application.role_family,
                application.work_mode.value if application.work_mode else None,
                application.skill_cluster,
                application.selected_resume_version_id,
                application.opportunity_score,
                application.opportunity_score_version,
                application.current_status.value,
                application.source,
                int(application.is_demo_data),
                application.created_at.isoformat(),
                application.applied_at.isoformat() if application.applied_at else None,
                application.model_dump_json(),
            ),
        )
        self._conn.commit()
        return application

    def get_application(self, application_id: str) -> Application | None:
        row = self._conn.execute(
            "SELECT data FROM applications WHERE application_id = ?", (application_id,)
        ).fetchone()
        return Application.model_validate_json(row["data"]) if row else None

    def update_application_status(self, application: Application) -> Application:
        self._conn.execute(
            "UPDATE applications SET current_status = ?, applied_at = ?, data = ? WHERE application_id = ?",
            (
                application.current_status.value,
                application.applied_at.isoformat() if application.applied_at else None,
                application.model_dump_json(),
                application.application_id,
            ),
        )
        self._conn.commit()
        return application

    def list_applications(
        self,
        candidate_id: str | None = None,
        include_demo_data: bool = True,
        role_family: str | None = None,
    ) -> list[Application]:
        query = "SELECT data FROM applications WHERE 1=1"
        params: list = []
        if candidate_id is not None:
            query += " AND candidate_id = ?"
            params.append(candidate_id)
        if not include_demo_data:
            query += " AND is_demo_data = 0"
        if role_family is not None:
            query += " AND role_family = ?"
            params.append(role_family)
        query += " ORDER BY created_at ASC"

        rows = self._conn.execute(query, params).fetchall()
        return [Application.model_validate_json(row["data"]) for row in rows]

    def get_candidate_applications(self, candidate_id: str, include_demo_data: bool = True) -> list[Application]:
        return self.list_applications(candidate_id=candidate_id, include_demo_data=include_demo_data)

    # --- events ---

    def record_event(self, event: ApplicationEvent) -> ApplicationEvent:
        self._conn.execute(
            """
            INSERT INTO application_events (event_id, application_id, candidate_id, job_id, event_type, occurred_at, data)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.event_id,
                event.application_id,
                event.candidate_id,
                event.job_id,
                event.event_type.value,
                event.occurred_at.isoformat(),
                event.model_dump_json(),
            ),
        )
        self._conn.commit()
        return event

    def get_application_history(self, application_id: str) -> list[ApplicationEvent]:
        rows = self._conn.execute(
            "SELECT data FROM application_events WHERE application_id = ? ORDER BY occurred_at ASC",
            (application_id,),
        ).fetchall()
        return [ApplicationEvent.model_validate_json(row["data"]) for row in rows]

    def get_applications_with_history(
        self, candidate_id: str | None = None, include_demo_data: bool = True
    ) -> list[tuple[Application, list[ApplicationEvent]]]:
        applications = self.list_applications(candidate_id=candidate_id, include_demo_data=include_demo_data)
        return [(app, self.get_application_history(app.application_id)) for app in applications]

    # --- strategy insights ---

    def persist_strategy_insight(self, insight: LearningInsight, candidate_id: str | None = None) -> LearningInsight:
        self._conn.execute(
            "INSERT OR REPLACE INTO strategy_insights (insight_id, candidate_id, category, data, created_at) VALUES (?, ?, ?, ?, ?)",
            (insight.insight_id, candidate_id, insight.category.value, insight.model_dump_json(), insight.created_at.isoformat()),
        )
        self._conn.commit()
        return insight

    def list_strategy_insights(self, candidate_id: str | None = None) -> list[LearningInsight]:
        if candidate_id is not None:
            rows = self._conn.execute(
                "SELECT data FROM strategy_insights WHERE candidate_id = ? ORDER BY created_at DESC", (candidate_id,)
            ).fetchall()
        else:
            rows = self._conn.execute("SELECT data FROM strategy_insights ORDER BY created_at DESC").fetchall()
        return [LearningInsight.model_validate_json(row["data"]) for row in rows]
