"""
Deterministic actionability classification (Phase 6 Part 1).

Separates two independent questions that were previously conflated into
one "confidence" label:

- SAMPLE CONFIDENCE (src/config/analytics.py): how much data do we have?
- ACTIONABILITY (this module): how big is the observed effect, given that
  data? A 33.3% vs 28.6% interview-rate difference is a tiny effect even
  at MEDIUM sample confidence -- it does not justify a strategy change on
  its own. Conversely a huge difference on a tiny sample is capped well
  below STRONG_SIGNAL, since a couple of applications can swing a rate
  wildly by chance.

No LLM involved. The Learning Agent interprets this classification; it
never computes it.
"""

from __future__ import annotations

from src.config.analytics import confidence_for_sample_size
from src.models.enums import ActionabilityLevel, SampleConfidence
from src.models.outcome_analytics import GroupAnalytics

# Effect-size bands, in percentage-point difference between two rates.
_SMALL_EFFECT_MIN = 0.05
_MEDIUM_EFFECT_MIN = 0.15
_LARGE_EFFECT_MIN = 0.30

# (effect_band, sample_confidence) -> ActionabilityLevel. "NONE" effect is
# handled separately (always NO_CLEAR_SIGNAL, regardless of confidence --
# more data can't make a non-difference actionable).
_MATRIX: dict[tuple[str, SampleConfidence], ActionabilityLevel] = {
    ("SMALL", SampleConfidence.INSUFFICIENT): ActionabilityLevel.NO_CLEAR_SIGNAL,
    ("SMALL", SampleConfidence.LOW): ActionabilityLevel.NO_CLEAR_SIGNAL,
    ("SMALL", SampleConfidence.MEDIUM): ActionabilityLevel.WEAK_SIGNAL,
    ("SMALL", SampleConfidence.HIGH): ActionabilityLevel.WEAK_SIGNAL,
    ("MEDIUM", SampleConfidence.INSUFFICIENT): ActionabilityLevel.WEAK_SIGNAL,
    ("MEDIUM", SampleConfidence.LOW): ActionabilityLevel.WEAK_SIGNAL,
    ("MEDIUM", SampleConfidence.MEDIUM): ActionabilityLevel.MODERATE_SIGNAL,
    ("MEDIUM", SampleConfidence.HIGH): ActionabilityLevel.MODERATE_SIGNAL,
    ("LARGE", SampleConfidence.INSUFFICIENT): ActionabilityLevel.WEAK_SIGNAL,
    ("LARGE", SampleConfidence.LOW): ActionabilityLevel.MODERATE_SIGNAL,
    ("LARGE", SampleConfidence.MEDIUM): ActionabilityLevel.STRONG_SIGNAL,
    ("LARGE", SampleConfidence.HIGH): ActionabilityLevel.STRONG_SIGNAL,
}

_ACTIONABILITY_LANGUAGE = {
    ActionabilityLevel.NO_CLEAR_SIGNAL: "No clear strategy change is justified yet. Continue collecting outcome data.",
    ActionabilityLevel.WEAK_SIGNAL: "This is a weak, tentative signal. Worth watching, not yet worth acting on.",
    ActionabilityLevel.MODERATE_SIGNAL: "This is a moderate signal that may justify a modest strategy adjustment.",
    ActionabilityLevel.STRONG_SIGNAL: "This is a strong, well-supported signal worth acting on.",
}


def _effect_band(diff: float) -> str | None:
    if diff < _SMALL_EFFECT_MIN:
        return None  # "NONE" -- not a distinct band, handled by caller
    if diff < _MEDIUM_EFFECT_MIN:
        return "SMALL"
    if diff < _LARGE_EFFECT_MIN:
        return "MEDIUM"
    return "LARGE"


def classify_actionability(group_a: GroupAnalytics, group_b: GroupAnalytics, metric: str = "interview_rate") -> ActionabilityLevel:
    """Compares one metric (default interview_rate) between two groups.
    Returns NO_CLEAR_SIGNAL if either group has no resolved data at all --
    there's nothing to compare."""
    if group_a.sample_size == 0 or group_b.sample_size == 0:
        return ActionabilityLevel.NO_CLEAR_SIGNAL

    rate_a = getattr(group_a, metric)
    rate_b = getattr(group_b, metric)
    diff = abs(rate_a - rate_b)

    band = _effect_band(diff)
    if band is None:
        return ActionabilityLevel.NO_CLEAR_SIGNAL

    min_sample = min(group_a.sample_size, group_b.sample_size)
    confidence = confidence_for_sample_size(min_sample)
    return _MATRIX[(band, confidence)]


def actionability_language(level: ActionabilityLevel) -> str:
    return _ACTIONABILITY_LANGUAGE[level]
