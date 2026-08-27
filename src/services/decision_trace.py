"""
Deterministic Decision Trace helper.

Records only observable system actions, decisions, counts, statuses,
warnings, and user actions — never private chain-of-thought or hidden
reasoning. See docs/ARCHITECTURE.md section 11.
"""

from __future__ import annotations

from typing import Any

from src.models.decision_trace import DecisionTraceEvent


class DecisionTrace:
    def __init__(self) -> None:
        self._events: list[DecisionTraceEvent] = []

    def add(self, step: str, action: str, message: str, metadata: dict[str, Any] | None = None) -> DecisionTraceEvent:
        event = DecisionTraceEvent(step=step, action=action, message=message, metadata=metadata or {})
        self._events.append(event)
        return event

    @property
    def events(self) -> list[DecisionTraceEvent]:
        return list(self._events)

    def as_dicts(self) -> list[dict[str, Any]]:
        return [event.model_dump(mode="json") for event in self._events]

    def as_lines(self) -> list[str]:
        """Human-readable rendering, e.g. for the Streamlit UI in a later phase."""
        return [event.message for event in self._events]
