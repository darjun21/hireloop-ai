"""
FieldProvenance — where a CareerProfile field's value came from.

Deliberately a separate, new enum from src.models.enums.EvidenceSourceType.
EvidenceSourceType is Truth Guard's frozen evidence hierarchy (what kind of
resume section grounds a claim); FieldProvenance is a different concept for
the new Career Profile feature — who/what most recently *set* a field's
current value (the resume parser, the human confirming it, an application
answer, etc.). Keeping them separate avoids retrofitting new meanings onto a
certified, frozen enum.

Not wired into Truth Guard itself in this pass (that would touch frozen
code under src/agents, src/graph, src/services' certified modules) — this
is intentionally just data-model support so the UI can show "SOURCE:
RESUME" vs "USER CONFIRMED" today, and Truth Guard can consume it later.
"""

from __future__ import annotations

from enum import Enum


class FieldProvenance(str, Enum):
    # Extracted directly from a parsed resume via the existing ProfileAgent,
    # not yet reviewed/confirmed by the human.
    RESUME_DERIVED = "RESUME_DERIVED"
    # The human explicitly typed, edited, or confirmed this value in the
    # Career Profile UI.
    USER_CONFIRMED = "USER_CONFIRMED"
    # Captured as part of the separate application-answers structure
    # (reusable answers for application questions), not a resume fact.
    APPLICATION_ANSWER = "APPLICATION_ANSWER"
    # Computed deterministically by the system (e.g. profile completeness,
    # a derived total-experience figure) rather than supplied by a human or
    # extracted from a resume.
    SYSTEM_DERIVED = "SYSTEM_DERIVED"
    # A human explicitly attested to this claim during a clarification/
    # confirmation step (mirrors, but is distinct from, Truth Guard's own
    # EvidenceSourceType.HUMAN_CONFIRMATION).
    HUMAN_CONFIRMATION = "HUMAN_CONFIRMATION"
