"""
Input-boundary normalization for values arriving from the Next.js
frontend (or any other HTTP client) before they become part of the
initial LangGraph state.

The certified backend (src/graph/nodes/resume.py::_build_preferences)
correctly expects canonical WorkMode enum values (WorkMode.REMOTE.value ==
"REMOTE", etc.) and is not modified here -- it should never have to guess
at display-label spelling. This module is the one place an HTTP client's
user-friendly label ("Remote") is converted to the canonical value before
api/engine.py builds initial_state, so a malformed/mistyped work mode
fails as a controlled 4xx at the API boundary instead of as an uncaught
ValueError deep inside a LangGraph node.
"""

from __future__ import annotations

from src.models.enums import EmploymentType, WorkMode


class InvalidWorkModeError(ValueError):
    def __init__(self, raw_value: object) -> None:
        self.raw_value = raw_value
        super().__init__(f"{raw_value!r} is not a recognized work mode")


class InvalidEmploymentTypeError(ValueError):
    def __init__(self, raw_value: object) -> None:
        self.raw_value = raw_value
        super().__init__(f"{raw_value!r} is not a recognized employment type")


# Friendly display labels (and common alternate spellings) a client might
# send, mapped case-insensitively to the canonical WorkMode. Canonical
# values themselves (any case -- "REMOTE"/"remote"/"Remote") are also
# always accepted; see normalize_work_mode below.
_DISPLAY_LABEL_ALIASES: dict[str, WorkMode] = {
    "remote": WorkMode.REMOTE,
    "hybrid": WorkMode.HYBRID,
    "onsite": WorkMode.ONSITE,
    "on-site": WorkMode.ONSITE,
    "on site": WorkMode.ONSITE,
    "in-office": WorkMode.ONSITE,
    "in office": WorkMode.ONSITE,
    "flexible": WorkMode.FLEXIBLE,
}


def normalize_work_mode(raw: str) -> str:
    """Accepts a display label ("Remote", "On-site"), a canonical value in
    any case ("REMOTE", "remote"), or a known alias, and returns the
    canonical WorkMode.value. Raises InvalidWorkModeError for anything
    else -- never silently drops or guesses at an unrecognized value."""
    if not isinstance(raw, str) or not raw.strip():
        raise InvalidWorkModeError(raw)

    key = raw.strip().lower()
    alias = _DISPLAY_LABEL_ALIASES.get(key)
    if alias is not None:
        return alias.value

    try:
        return WorkMode(raw.strip().upper()).value
    except ValueError:
        raise InvalidWorkModeError(raw) from None


def normalize_work_modes(raw_values: list[str]) -> list[str]:
    """Normalizes a list of work mode values, in order. Raises
    InvalidWorkModeError on the first unrecognized value."""
    return [normalize_work_mode(v) for v in raw_values]


# Same rationale as _DISPLAY_LABEL_ALIASES above, for
# CareerEmploymentPreferences.employment_types (src/models/career_profile.py),
# which is a genuinely free-text input on the Career Profile page (a
# comma-separated field, not a fixed dropdown) -- "Full Time" is the
# natural thing a real user types, but the stored model expects the
# canonical EmploymentType enum value ("FULL_TIME"). Without this
# normalization, that mismatch previously raised an *uncaught*
# pydantic.ValidationError deep inside the route handler, which produced
# a raw 500 response with no CORS headers at all (since the exception
# propagated past CORSMiddleware before Starlette's ServerErrorMiddleware
# caught it) -- in a browser this was indistinguishable from a CORS
# failure. See api/main.py's pydantic ValidationError handler for the
# general safety net, and this function for the specific fix.
_EMPLOYMENT_TYPE_ALIASES: dict[str, EmploymentType] = {
    "full time": EmploymentType.FULL_TIME,
    "full-time": EmploymentType.FULL_TIME,
    "part time": EmploymentType.PART_TIME,
    "part-time": EmploymentType.PART_TIME,
    "contract": EmploymentType.CONTRACT,
    "contractor": EmploymentType.CONTRACT,
    "internship": EmploymentType.INTERNSHIP,
    "intern": EmploymentType.INTERNSHIP,
    "temporary": EmploymentType.TEMPORARY,
    "temp": EmploymentType.TEMPORARY,
}


def normalize_employment_type(raw: str) -> str:
    """Accepts a display label ("Full Time"), a canonical value in any
    case ("FULL_TIME", "full_time"), or a known alias, and returns the
    canonical EmploymentType.value. Raises InvalidEmploymentTypeError for
    anything else."""
    if not isinstance(raw, str) or not raw.strip():
        raise InvalidEmploymentTypeError(raw)

    key = raw.strip().lower()
    alias = _EMPLOYMENT_TYPE_ALIASES.get(key)
    if alias is not None:
        return alias.value

    try:
        return EmploymentType(raw.strip().upper().replace(" ", "_").replace("-", "_")).value
    except ValueError:
        raise InvalidEmploymentTypeError(raw) from None


def normalize_employment_types(raw_values: list[str]) -> list[str]:
    """Normalizes a list of employment type values, in order. Raises
    InvalidEmploymentTypeError on the first unrecognized value."""
    return [normalize_employment_type(v) for v in raw_values]
