"""
DecisionTraceEvent model.

A structured record of one observable system action (a count, a decision, a
status change, a warning, a user action) — never private chain-of-thought or
hidden reasoning. See docs/ARCHITECTURE.md section 11.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class DecisionTraceEvent(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    step: str = Field(..., min_length=1)
    action: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
