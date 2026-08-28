"""
CareerProfile persistence — a genuinely separate SQLite database from both
src/services/database.py's business DB and src/graph/checkpointing.py's
workflow-checkpoint DB.

Follows the same established pattern (one dedicated SQLite file per
concern, schema_meta version row, `check_same_thread=False` because
FastAPI/Streamlit reruns don't guarantee the same OS thread) WITHOUT
modifying either of those frozen modules — this file only imports
`sqlite3` itself.

Default location: data/career_profiles.db. Completely separate from:
  - the demo/certification in-memory session state in api/engine.py
    (Session.state / Session.tracker, both per-HTTP-session and
    ephemeral),
  - data/sample_jobs.json and src/services/demo_application_loader.py
    (synthetic certification-demo data),
so a Personal Mode profile can never be conjured from, or leak into,
certification-demo state. See tests/test_career_profile_isolation.py.

Keyed by `owner_id`, a caller-supplied real-user identifier. This project
has no authentication layer; `owner_id` is currently supplied by the API
client (defaulting to a single local user in the reference frontend). A
real multi-tenant auth layer is out of scope for this pass — see the
Remaining Limitations section of the task report.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from src.models.career_profile import CareerProfile

DEFAULT_DB_PATH = "data/career_profiles.db"
CURRENT_SCHEMA_VERSION = 1

_SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS schema_meta (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS career_profiles (
        profile_id TEXT PRIMARY KEY,
        owner_id TEXT NOT NULL UNIQUE,
        data TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_career_profiles_owner ON career_profiles(owner_id)",
    """
    CREATE TABLE IF NOT EXISTS career_profile_resume_uploads (
        upload_id TEXT PRIMARY KEY,
        owner_id TEXT NOT NULL,
        original_filename TEXT,
        uploaded_at TEXT NOT NULL,
        applied INTEGER NOT NULL DEFAULT 0,
        data TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_resume_uploads_owner ON career_profile_resume_uploads(owner_id)",
]


def get_connection(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    for statement in _SCHEMA_STATEMENTS:
        conn.execute(statement)
    conn.execute(
        "INSERT OR REPLACE INTO schema_meta (key, value) VALUES ('schema_version', ?)",
        (str(CURRENT_SCHEMA_VERSION),),
    )
    conn.commit()


class CareerProfileStore:
    """The only intended caller of the raw SQL in this module."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get_by_owner(self, owner_id: str) -> CareerProfile | None:
        row = self._conn.execute(
            "SELECT data FROM career_profiles WHERE owner_id = ?", (owner_id,)
        ).fetchone()
        if row is None:
            return None
        return CareerProfile.model_validate(json.loads(row["data"]))

    def get_or_create(self, owner_id: str) -> CareerProfile:
        existing = self.get_by_owner(owner_id)
        if existing is not None:
            return existing
        profile = CareerProfile(owner_id=owner_id)
        self.save(profile)
        return profile

    def save(self, profile: CareerProfile) -> CareerProfile:
        from datetime import datetime, timezone

        profile.updated_at = datetime.now(timezone.utc)
        payload = profile.model_dump(mode="json")
        self._conn.execute(
            """
            INSERT INTO career_profiles (profile_id, owner_id, data, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(owner_id) DO UPDATE SET
                data = excluded.data,
                updated_at = excluded.updated_at
            """,
            (
                profile.profile_id,
                profile.owner_id,
                json.dumps(payload),
                profile.created_at.isoformat(),
                profile.updated_at.isoformat(),
            ),
        )
        self._conn.commit()
        return profile

    def delete(self, owner_id: str) -> None:
        self._conn.execute("DELETE FROM career_profiles WHERE owner_id = ?", (owner_id,))
        self._conn.commit()

    # -- pending resume uploads (merge-preview staging area) ---------------

    def save_pending_upload(self, owner_id: str, upload_id: str, original_filename: str | None, data: dict[str, Any]) -> None:
        from datetime import datetime, timezone

        self._conn.execute(
            """
            INSERT INTO career_profile_resume_uploads
                (upload_id, owner_id, original_filename, uploaded_at, applied, data)
            VALUES (?, ?, ?, ?, 0, ?)
            """,
            (upload_id, owner_id, original_filename, datetime.now(timezone.utc).isoformat(), json.dumps(data)),
        )
        self._conn.commit()

    def get_pending_upload(self, upload_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM career_profile_resume_uploads WHERE upload_id = ? AND applied = 0",
            (upload_id,),
        ).fetchone()
        if row is None:
            return None
        result = json.loads(row["data"])
        result["_original_filename"] = row["original_filename"]
        return result

    def mark_upload_applied(self, upload_id: str) -> None:
        self._conn.execute(
            "UPDATE career_profile_resume_uploads SET applied = 1 WHERE upload_id = ?",
            (upload_id,),
        )
        self._conn.commit()
