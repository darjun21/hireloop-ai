"""
StrategyInsight model.

This is the output of the deterministic historical signal calculator
(src/services/historical_signal.py) and, in a later phase, of the Learning
Agent's broader recommendations. It deliberately separates observation
(sample_size, success_rate) from interpretation (signal_value, explanation)
and never claims causality — see docs/DECISIONS.md #7 and #9.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.models.enums import ConfidenceLevel


class StrategyInsight(BaseModel):
    role_family: str = Field(..., min_length=1)

    sample_size: int = Field(..., ge=0)
    success_rate: float | None = Field(default=None, ge=0, le=1)

    signal_value: float = Field(..., ge=0, le=100)
    confidence: ConfidenceLevel
    is_neutral: bool

    explanation: str = ""
