"""ProfileValidationResult model — output of deterministic post-extraction checks."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ProfileValidationResult(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    corrected_fields: dict[str, str] = Field(default_factory=dict)
