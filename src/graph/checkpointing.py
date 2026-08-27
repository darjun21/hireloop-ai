"""
LangGraph checkpoint persistence.

This is workflow execution state (interrupt/resume points, node history,
per-thread graph state) — a categorically different responsibility from
src/services/database.py's business data (candidates, jobs, applications,
outcomes). They intentionally live in separate SQLite files and must never
be merged: losing the checkpoint DB should only cost in-flight workflow
runs, never business records, and vice versa.

No Redis/Postgres/cloud infrastructure for MVP — SQLite is sufficient for
a single-user local demo.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver

from src.config.workflow import DEFAULT_CHECKPOINT_DB_PATH


def get_sqlite_checkpointer(db_path: str = DEFAULT_CHECKPOINT_DB_PATH) -> SqliteSaver:
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    saver = SqliteSaver(conn)
    saver.setup()
    return saver
