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

from src.models.enums import WorkMode


class InvalidWorkModeError(ValueError):
    def __init__(self, raw_value: object) -> None:
        self.raw_value = raw_value
        super().__init__(f"{raw_value!r} is not a recognized work mode")


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
