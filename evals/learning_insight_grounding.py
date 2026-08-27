"""
Category 10: Learning Insight Grounding.

Verifies src/services/learning_insight_validation.py rejects invented
numbers and causal language, and that src/services/actionability.py (and
sample confidence) are always derived deterministically from real
OutcomeAnalytics groups, never from LLM-supplied numbers.
"""

from __future__ import annotations

from src.models.enums import ActionabilityLevel, SampleConfidence
from src.models.outcome_analytics import GroupAnalytics, OutcomeAnalytics
from src.services.actionability import classify_actionability
from src.services.learning_insight_validation import validate_and_ground_insights
from evals.common import CategorySummary, EvalCase, summarize

CATEGORY = "learning_insight_grounding"


def _group(name: str, sample_size: int, interview_rate: float, confidence: SampleConfidence) -> GroupAnalytics:
    return GroupAnalytics(
        group=name, sample_size=sample_size, positive_responses=int(sample_size * interview_rate),
        interviews=int(sample_size * interview_rate), offers=0, rejections=sample_size - int(sample_size * interview_rate),
        response_rate=interview_rate, interview_rate=interview_rate, offer_rate=0.0,
        rejection_rate=1 - interview_rate, confidence=confidence,
    )


def _analytics() -> OutcomeAnalytics:
    return OutcomeAnalytics(
        by_role_family={
            "AI Engineer": _group("AI Engineer", 20, 0.40, SampleConfidence.HIGH),
            "Data Scientist": _group("Data Scientist", 20, 0.10, SampleConfidence.HIGH),
        },
        total_applications=40,
        total_resolved=40,
    )


def run() -> CategorySummary:
    cases: list[EvalCase] = []
    analytics = _analytics()

    # 1. A grounded insight (real percentage, present in analytics) is accepted.
    accepted, rejections = validate_and_ground_insights(
        [
            {
                "category": "ROLE_FAMILY", "referenced_group": "AI Engineer", "compared_group": "Data Scientist",
                "observation": "AI Engineer applications have generated a 40.0% interview rate compared with 10.0% for Data Scientist.",
                "recommendation": "Continue prioritizing AI Engineer opportunities.",
            }
        ],
        analytics,
    )
    passed = len(accepted) == 1 and not rejections
    cases.append(EvalCase("learning:grounded_insight_accepted", CATEGORY, passed, detail=f"accepted={accepted} rejections={rejections}"))

    # 2. An invented percentage (not present anywhere in analytics) is rejected outright.
    accepted, rejections = validate_and_ground_insights(
        [
            {
                "category": "ROLE_FAMILY", "referenced_group": "AI Engineer",
                "observation": "AI Engineer applications have generated a 99.9% interview rate.",
                "recommendation": "Prioritize AI Engineer opportunities.",
            }
        ],
        analytics,
    )
    passed = len(accepted) == 0 and any("percentage" in r for r in rejections)
    cases.append(EvalCase("learning:invented_percentage_rejected", CATEGORY, passed, detail=f"rejections={rejections}"))

    # 3. Causal language ("causes", "guarantees", ...) is rejected outright.
    accepted, rejections = validate_and_ground_insights(
        [
            {
                "category": "ROLE_FAMILY", "referenced_group": "AI Engineer",
                "observation": "Targeting AI Engineer roles causes a higher interview rate.",
                "recommendation": "This guarantees better outcomes.",
            }
        ],
        analytics,
    )
    passed = len(accepted) == 0 and any("causal" in r for r in rejections)
    cases.append(EvalCase("learning:causal_language_rejected", CATEGORY, passed, detail=f"rejections={rejections}"))

    # 4. An insight referencing a group not present in analytics at all is rejected.
    accepted, rejections = validate_and_ground_insights(
        [{"category": "ROLE_FAMILY", "referenced_group": "Quantum Wizard", "observation": "Quantum Wizard roles perform well.", "recommendation": "Pursue them."}],
        analytics,
    )
    passed = len(accepted) == 0 and any("unknown group" in r for r in rejections)
    cases.append(EvalCase("learning:unknown_group_reference_rejected", CATEGORY, passed, detail=f"rejections={rejections}"))

    # 5. sample_size and confidence on the accepted LearningInsight are
    #    ALWAYS re-derived from the analytics group -- never trusted from
    #    LLM-supplied values, even if the candidate dict tries to lie about them.
    lying_candidate = {
        "category": "ROLE_FAMILY", "referenced_group": "AI Engineer", "compared_group": "Data Scientist",
        "observation": "AI Engineer applications have generated a 40.0% interview rate compared with 10.0% for Data Scientist.",
        "recommendation": "Prioritize AI Engineer.",
        # These fields aren't even part of the accepted schema -- verifying
        # the validator never reads them from the candidate dict at all.
        "sample_size": 999999, "confidence": "HIGH_BUT_FAKE",
    }
    accepted, _ = validate_and_ground_insights([lying_candidate], analytics)
    passed = len(accepted) == 1 and accepted[0].sample_size == 20 and accepted[0].confidence == SampleConfidence.HIGH
    cases.append(
        EvalCase(
            "learning:sample_size_and_confidence_always_derived_from_analytics",
            CATEGORY,
            passed,
            detail=f"accepted_sample_size={accepted[0].sample_size if accepted else None}",
        )
    )

    # 6. A group below the minimum sample size for an insight is rejected.
    tiny_analytics = OutcomeAnalytics(
        by_role_family={"Tiny Group": _group("Tiny Group", 0, 0.0, SampleConfidence.INSUFFICIENT)},
        total_applications=0, total_resolved=0,
    )
    accepted, rejections = validate_and_ground_insights(
        [{"category": "ROLE_FAMILY", "referenced_group": "Tiny Group", "observation": "Tiny Group performs well.", "recommendation": "Pursue it."}],
        tiny_analytics,
    )
    passed = len(accepted) == 0 and any("insufficient sample size" in r for r in rejections)
    cases.append(EvalCase("learning:insufficient_sample_size_rejected", CATEGORY, passed, detail=f"rejections={rejections}"))

    # 7. Actionability is a deterministic function of the analytics groups,
    #    never an LLM-supplied label: identical inputs always produce the
    #    identical ActionabilityLevel, and a huge rate difference on a huge
    #    sample is a STRONG_SIGNAL while a tiny difference is NO_CLEAR_SIGNAL.
    strong_a = _group("A", 50, 0.60, SampleConfidence.HIGH)
    strong_b = _group("B", 50, 0.10, SampleConfidence.HIGH)
    weak_a = _group("A", 50, 0.31, SampleConfidence.HIGH)
    weak_b = _group("B", 50, 0.30, SampleConfidence.HIGH)
    strong_level = classify_actionability(strong_a, strong_b)
    weak_level = classify_actionability(weak_a, weak_b)
    repeat_level = classify_actionability(strong_a, strong_b)
    passed = (
        strong_level == ActionabilityLevel.STRONG_SIGNAL
        and weak_level == ActionabilityLevel.NO_CLEAR_SIGNAL
        and strong_level == repeat_level  # deterministic / reproducible
    )
    cases.append(
        EvalCase(
            "learning:actionability_deterministic_and_effect_size_aware",
            CATEGORY,
            passed,
            detail=f"strong={strong_level.value} weak={weak_level.value}",
        )
    )

    # 8. A huge rate difference on a near-zero sample is capped well below
    #    STRONG_SIGNAL (small samples cannot manufacture a strong signal).
    tiny_sample_huge_diff = classify_actionability(
        _group("A", 2, 1.0, SampleConfidence.INSUFFICIENT), _group("B", 2, 0.0, SampleConfidence.INSUFFICIENT)
    )
    passed = tiny_sample_huge_diff != ActionabilityLevel.STRONG_SIGNAL
    cases.append(
        EvalCase(
            "learning:tiny_sample_cannot_produce_strong_signal",
            CATEGORY,
            passed,
            detail=f"actionability={tiny_sample_huge_diff.value}",
        )
    )

    return summarize(CATEGORY, cases)


if __name__ == "__main__":
    result = run()
    print(result.to_dict())
