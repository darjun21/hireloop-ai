"""
HireLoop business SQLite persistence — the durable system of record.

Conceptually and physically separate from `data/workflow_checkpoints.db`
(LangGraph's execution/interrupt-resume state): losing the checkpoint DB
only costs in-flight workflow runs, while this database holds durable
product records (candidates, jobs, applications, outcomes, resume
versions, strategy insights). See docs/ARCHITECTURE.md's storage table.

Schema is versioned via a simple `schema_meta` table rather than a
migration framework (Alembic) — appropriate for a single-file MVP schema
that has only ever grown, not branched. If this schema needs real
migrations later, that's the trigger to introduce one.

No agent or graph node executes SQL directly — everything goes through
src/services/application_tracker.py (and future repository modules), which
are the only callers of this module.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

CURRENT_SCHEMA_VERSION = 1

_SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS schema_meta (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS candidates (
        candidate_id TEXT PRIMARY KEY,
        data TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS jobs (
        job_id TEXT PRIMARY KEY,
        data TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS opportunity_scores (
        job_id TEXT NOT NULL,
        candidate_id TEXT NOT NULL,
        scoring_version TEXT NOT NULL,
        data TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY (job_id, candidate_id, scoring_version)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS resume_versions (
        resume_version_id TEXT PRIMARY KEY,
        candidate_id TEXT NOT NULL,
        data TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS applications (
        application_id TEXT PRIMARY KEY,
        candidate_id TEXT NOT NULL,
        job_id TEXT NOT NULL,
        role_family TEXT,
        work_mode TEXT,
        skill_cluster TEXT,
        selected_resume_version_id TEXT,
        opportunity_score REAL,
        opportunity_score_version TEXT NOT NULL,
        current_status TEXT NOT NULL,
        source TEXT NOT NULL,
        is_demo_data INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        applied_at TEXT,
        data TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_applications_candidate ON applications(candidate_id)",
    "CREATE INDEX IF NOT EXISTS idx_applications_role_family ON applications(role_family)",
    """
    CREATE TABLE IF NOT EXISTS application_events (
        event_id TEXT PRIMARY KEY,
        application_id TEXT NOT NULL,
        candidate_id TEXT NOT NULL,
        job_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        occurred_at TEXT NOT NULL,
        data TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_events_application ON application_events(application_id)",
    """
    CREATE TABLE IF NOT EXISTS strategy_insights (
        insight_id TEXT PRIMARY KEY,
        candidate_id TEXT,
        category TEXT NOT NULL,
        data TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS decision_trace_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT,
        data TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS scoring_model_versions (
        version TEXT PRIMARY KEY,
        weights_json TEXT NOT NULL,
        recorded_at TEXT NOT NULL
    )
    """,
]


def get_connection(db_path: str) -> sqlite3.Connection:
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False: Streamlit reruns (and LangGraph's node
    # execution) do not guarantee the same OS thread as the one that
    # opened this connection. Mirrors src/graph/checkpointing.py, which
    # has the same requirement for the workflow checkpoint DB.
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    for statement in _SCHEMA_STATEMENTS:
        conn.execute(statement)
    conn.execute(
        "INSERT OR REPLACE INTO schema_meta (key, value) VALUES ('schema_version', ?)",
        (str(CURRENT_SCHEMA_VERSION),),
    )
    conn.commit()


def get_schema_version(conn: sqlite3.Connection) -> int | None:
    row = conn.execute("SELECT value FROM schema_meta WHERE key = 'schema_version'").fetchone()
    return int(row["value"]) if row else None
