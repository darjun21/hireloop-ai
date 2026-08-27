"""Workflow lifecycle status, shared by the graph and any UI observing it."""

from __future__ import annotations

from enum import Enum


class WorkflowStatus(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    RUNNING = "RUNNING"
    WAITING_FOR_HUMAN = "WAITING_FOR_HUMAN"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_NO_RESULTS = "COMPLETED_WITH_NO_RESULTS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
