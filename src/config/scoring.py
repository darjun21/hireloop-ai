"""
Versioned, auditable configuration for the deterministic Opportunity
Scoring Engine. This is the single source of truth for scoring weights —
no other module should hardcode a weight value.

Guardrails (see docs/ARCHITECTURE.md section 8 and docs/DECISIONS.md #1, #7):
- Weights are static configuration. No agent, node, or memory system may
  rewrite these values at runtime.
- The historical outcome signal weight is capped and must never exceed the
  value defined here for the active model version.
- Every opportunity score computed against a given version of these weights
  must record SCORING_MODEL_VERSION alongside the score so historical
  results remain reproducible even if this file changes later.
- The Learning Agent (later phase) may only *recommend* changes to these
  weights. It has no code path that applies changes automatically.
"""

from __future__ import annotations

from dataclasses import dataclass, fields

SCORING_MODEL_VERSION = "v1.0"

# Hard cap on the historical/strategy signal contribution, independent of
# CURRENT_WEIGHTS, so a future config change cannot silently let history
# dominate the score without an explicit, reviewed decision.
MAX_HISTORY_SIGNAL_WEIGHT = 0.10


@dataclass(frozen=True)
class ScoringWeights:
    skill_match: float = 0.30
    experience_match: float = 0.20
    role_alignment: float = 0.15
    location_work_mode: float = 0.10
    candidate_preference: float = 0.10
    historical_signal: float = 0.10
    job_quality: float = 0.05

    def total(self) -> float:
        return sum(getattr(self, f.name) for f in fields(self))

    def as_dict(self) -> dict[str, float]:
        return {f.name: getattr(self, f.name) for f in fields(self)}


# Frozen weight set for SCORING_MODEL_VERSION. Do not mutate at runtime.
CURRENT_WEIGHTS = ScoringWeights()


def get_scoring_config() -> tuple[str, ScoringWeights]:
    """Return the active scoring model version and its frozen weights.

    This is the one clean interface downstream services should use instead
    of importing CURRENT_WEIGHTS directly, so that a future versioned
    config swap only touches this function.
    """
    assert CURRENT_WEIGHTS.historical_signal <= MAX_HISTORY_SIGNAL_WEIGHT, (
        "historical_signal weight exceeds MAX_HISTORY_SIGNAL_WEIGHT"
    )
    assert round(CURRENT_WEIGHTS.total(), 6) == 1.0, "scoring weights must sum to 1.0"
    return SCORING_MODEL_VERSION, CURRENT_WEIGHTS
