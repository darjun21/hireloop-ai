"""
Loads the seeded demo application history (data/demo_application_history.json)
into (Application, list[ApplicationEvent]) pairs. Every record carries
is_demo_data=True on the Application itself — callers must never merge
this into real analytics without an explicit DEMO_MODE boundary
(docs/LEARNING_LOOP.md).
"""

from __future__ import annotations

import json
from pathlib import Path

from src.models.application import Application
from src.models.application_event import ApplicationEvent

DEFAULT_DEMO_HISTORY_PATH = "data/demo_application_history.json"


def load_demo_application_history(
    path: str = DEFAULT_DEMO_HISTORY_PATH,
) -> list[tuple[Application, list[ApplicationEvent]]]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    records = []
    for record in raw.get("applications", []):
        application = Application(**record["application"])
        events = [ApplicationEvent(**e) for e in record.get("events", [])]
        records.append((application, events))
    return records
