"""
WorkflowError model — a structured, display-safe error record appended to
HireLoopState.errors. Reuses src.llm.errors.LLMErrorType's retryability
classification for LLM-originated failures rather than re-deriving it.

`message` and `details` must never contain API keys, full resume/document
text, or raw stack traces — they are shown to the user.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ErrorCategory(str, Enum):
    RESUME_PARSE_ERROR = "RESUME_PARSE_ERROR"
    PROFILE_ERROR = "PROFILE_ERROR"
    JOB_INGESTION_ERROR = "JOB_INGESTION_ERROR"
    SCORING_ERROR = "SCORING_ERROR"
    LLM_ERROR = "LLM_ERROR"
    INVALID_STATE = "INVALID_STATE"
    HUMAN_CANCELLED = "HUMAN_CANCELLED"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"


class WorkflowError(BaseModel):
    node: str = Field(..., min_length=1)
    category: ErrorCategory
    message: str = Field(..., min_length=1)
    retryable: bool = False
    attempt: int = Field(default=1, ge=1)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    details: dict[str, Any] = Field(default_factory=dict)
