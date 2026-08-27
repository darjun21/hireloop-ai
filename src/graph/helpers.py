"""Shared helpers for building DecisionTraceEvent / WorkflowError dicts inside graph nodes."""

from __future__ import annotations

from typing import Any

from src.models.decision_trace import DecisionTraceEvent
from src.models.workflow_error import ErrorCategory, WorkflowError


def trace_event(step: str, action: str, message: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    return DecisionTraceEvent(step=step, action=action, message=message, metadata=metadata or {}).model_dump(mode="json")


def make_error(
    node: str,
    category: ErrorCategory,
    message: str,
    *,
    retryable: bool = False,
    attempt: int = 1,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return WorkflowError(
        node=node,
        category=category,
        message=message,
        retryable=retryable,
        attempt=attempt,
        details=details or {},
    ).model_dump(mode="json")
