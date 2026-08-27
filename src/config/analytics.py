"""
Versioned, configurable sample-size confidence thresholds for outcome
analytics (Part I). A different defensible scheme could be substituted
here without touching any calling code.

Scheme: n < 3 -> INSUFFICIENT, 3-5 -> LOW, 6-10 -> MEDIUM, > 10 -> HIGH.
"""

from __future__ import annotations

from src.models.enums import SampleConfidence

INSUFFICIENT_MAX_SAMPLE = 2  # n <= this -> INSUFFICIENT
LOW_MAX_SAMPLE = 5  # n <= this -> LOW
MEDIUM_MAX_SAMPLE = 10  # n <= this -> MEDIUM  (n > this -> HIGH)

# Minimum sample size for the Learning Agent to generate an insight about a
# group at all. Zero resolved applications means there is nothing to
# observe -- but a small nonzero sample can still produce an insight, as
# long as it's framed with confidence-appropriate hedging (enforced
# deterministically, not left to the LLM's wording -- see
# src/services/learning_insight_validation.py).
MIN_SAMPLE_SIZE_FOR_INSIGHT = 1


def confidence_for_sample_size(n: int) -> SampleConfidence:
    if n <= INSUFFICIENT_MAX_SAMPLE:
        return SampleConfidence.INSUFFICIENT
    if n <= LOW_MAX_SAMPLE:
        return SampleConfidence.LOW
    if n <= MEDIUM_MAX_SAMPLE:
        return SampleConfidence.MEDIUM
    return SampleConfidence.HIGH
