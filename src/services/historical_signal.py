"""
Deterministic historical outcome signal calculator.

This is an observed response signal, not causal evidence — see
docs/DECISIONS.md #7. It is intentionally shrunk toward neutral (50) when
the sample size is small, so a handful of applications cannot swing a
candidate's opportunity score. The Learning Agent (a later phase) is what
turns this into broader strategy recommendations; this module only answers
"what does the observed history for this role family suggest, if anything."

No LLM.
"""

from __future__ import annotations

from typing import Sequence

from src.config.outcomes import POSITIVE_OUTCOMES, is_resolved
from src.models.application import Application
from src.models.enums import ConfidenceLevel
from src.models.strategy_insight import StrategyInsight

# Neutral-prior pseudo-count used to shrink small-sample success rates
# toward 50/50. With 0 real applications this alone yields exactly 0.5.
_PRIOR_STRENGTH = 5.0
_PRIOR_SUCCESS_RATE = 0.5

_LOW_CONFIDENCE_MAX_SAMPLE = 2
_MEDIUM_CONFIDENCE_MAX_SAMPLE = 10


def calculate_historical_signal(role_family: str, applications: Sequence[Application]) -> StrategyInsight:
    # Only resolved applications (a definitive positive or negative outcome)
    # count toward the sample — an application still SAVED, APPLIED, etc.
    # tells us nothing about how the employer will respond.
    resolved = [a for a in applications if is_resolved(a.current_status)]
    sample_size = len(resolved)
    positive_count = sum(1 for a in resolved if a.current_status in POSITIVE_OUTCOMES)

    raw_rate = (positive_count / sample_size) if sample_size else None

    adjusted_rate = (positive_count + _PRIOR_STRENGTH * _PRIOR_SUCCESS_RATE) / (sample_size + _PRIOR_STRENGTH)
    signal_value = round(adjusted_rate * 100, 2)

    is_neutral = sample_size <= _LOW_CONFIDENCE_MAX_SAMPLE

    if sample_size <= _LOW_CONFIDENCE_MAX_SAMPLE:
        confidence = ConfidenceLevel.LOW
    elif sample_size <= _MEDIUM_CONFIDENCE_MAX_SAMPLE:
        confidence = ConfidenceLevel.MEDIUM
    else:
        confidence = ConfidenceLevel.HIGH

    if sample_size == 0:
        explanation = (
            f"No historical applications recorded for role family '{role_family}'. "
            "Using a neutral signal (50) since there is no observed data. "
            "This is an observed response signal only, not causal evidence."
        )
    else:
        observation = (
            f"Observed {positive_count} positive employer response(s) out of {sample_size} "
            f"application(s) ({raw_rate * 100:.1f}%) for role family '{role_family}'. "
            f"Adjusted signal: {signal_value:.1f}/100. This is an observed response signal "
            "only, not causal evidence."
        )
        if sample_size <= _MEDIUM_CONFIDENCE_MAX_SAMPLE:
            observation += " Sample size is small; treat this as a weak, low-confidence signal."
        explanation = observation

    return StrategyInsight(
        role_family=role_family,
        sample_size=sample_size,
        success_rate=raw_rate,
        signal_value=signal_value,
        confidence=confidence,
        is_neutral=is_neutral,
        explanation=explanation,
    )
