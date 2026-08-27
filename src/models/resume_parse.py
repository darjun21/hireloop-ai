"""ResumeParseResult model — output of deterministic text extraction only."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ResumeParseResult(BaseModel):
    extracted_text: str = ""
    file_type: str
    character_count: int = 0
    warnings: list[str] = Field(default_factory=list)
    success: bool
    error: str | None = None
