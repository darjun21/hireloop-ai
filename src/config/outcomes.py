"""
Versioned, single-source definition of what an application outcome means
for the historical signal calculator (src/services/historical_signal.py).

Do not re-derive or hardcode this classification in any other module —
import it from here. See docs/DECISIONS.md #7.
"""

from __future__ import annotations

from src.models.enums import ApplicationStatus

OUTCOME_SEMANTICS_VERSION = "v1.1"  # v1.1: added CLOSED (Phase 5), classified as unresolved

# Outcomes that represent a positive employer response.
POSITIVE_OUTCOMES: frozenset[ApplicationStatus] = frozenset(
    {
        ApplicationStatus.RECRUITER_RESPONSE,
        ApplicationStatus.INTERVIEW,
        ApplicationStatus.FINAL_ROUND,
        ApplicationStatus.OFFER,
    }
)

# The one outcome that represents a definitive negative response.
NEGATIVE_OUTCOMES: frozenset[ApplicationStatus] = frozenset({ApplicationStatus.REJECTED})

# Not yet resolved: excluded entirely from response-rate calculations,
# since we don't yet know how the employer will respond.
# WITHDRAWN is grouped here for MVP; revisit if we later want to treat a
# candidate-initiated withdrawal as informative signal.
# CLOSED (Phase 5, administrative closure with no specific outcome) is also
# unresolved for response-rate purposes -- it's not itself a signal.
UNRESOLVED_OUTCOMES: frozenset[ApplicationStatus] = frozenset(
    {
        ApplicationStatus.SAVED,
        ApplicationStatus.READY_FOR_REVIEW,
        ApplicationStatus.APPROVED,
        ApplicationStatus.APPLIED,
        ApplicationStatus.WITHDRAWN,
        ApplicationStatus.CLOSED,
    }
)


def is_resolved(outcome: ApplicationStatus | None) -> bool:
    """True if `outcome` counts toward a response-rate calculation."""
    if outcome is None:
        return False
    return outcome in POSITIVE_OUTCOMES or outcome in NEGATIVE_OUTCOMES
