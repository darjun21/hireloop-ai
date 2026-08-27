"""
Category 4: Opportunity Ranking.

Relationship-based checks against the real deterministic Opportunity
Scoring Engine (src/services/opportunity_scoring.py):

- a strongly relevant role outscores an unrelated one
- a location/work-mode mismatch reduces score relative to a match
- the historical signal influences the score but is bounded by
  MAX_HISTORY_SIGNAL_WEIGHT (src/config/scoring.py) and can never dominate
- a sparse job description does not produce unjustified HIGH confidence
"""

from __future__ import annotations

from src.config.scoring import MAX_HISTORY_SIGNAL_WEIGHT
from src.models.enums import ConfidenceLevel, WorkMode
from src.models.strategy_insight import StrategyInsight
from src.services.job_quality import score_job_quality
from src.services.opportunity_scoring import score_opportunity
from evals.common import CategorySummary, EvalCase, summarize
from tests.factories import build_candidate, build_job

CATEGORY = "opportunity_ranking"


def _neutral_signal(role_family: str = "AI Engineer") -> StrategyInsight:
    return StrategyInsight(
        role_family=role_family, sample_size=0, success_rate=None, signal_value=50.0,
        confidence=ConfidenceLevel.LOW, is_neutral=True, explanation="No historical data.",
    )


def _signal(value: float, role_family: str = "AI Engineer") -> StrategyInsight:
    return StrategyInsight(
        role_family=role_family, sample_size=10, success_rate=value / 100.0, signal_value=value,
        confidence=ConfidenceLevel.HIGH, is_neutral=False, explanation="Historical signal.",
    )


def run() -> CategorySummary:
    cases: list[EvalCase] = []
    candidate = build_candidate()

    # 1. A strongly relevant role must outscore a clearly unrelated one.
    relevant_job = build_job(job_id="relevant-1")  # matches candidate skills/role/location closely
    unrelated_job = build_job(
        job_id="unrelated-1",
        title="Warehouse Operations Associate",
        required_skills=["Forklift Operation", "Inventory Management"],
        preferred_skills=[],
        location="Boise, ID",
        work_mode=WorkMode.ONSITE,
        minimum_years_experience=0,
    )
    relevant_score = score_opportunity(candidate, relevant_job, score_job_quality(relevant_job), _neutral_signal())
    unrelated_score = score_opportunity(candidate, unrelated_job, score_job_quality(unrelated_job), _neutral_signal())
    passed = relevant_score.final_score > unrelated_score.final_score
    cases.append(
        EvalCase(
            "ranking:relevant_role_outscores_unrelated",
            CATEGORY,
            passed,
            detail=f"relevant={relevant_score.final_score:.2f} unrelated={unrelated_score.final_score:.2f}",
        )
    )

    # 2. Location/work-mode mismatch reduces score relative to a match, all
    #    else held equal.
    matching_job = build_job(job_id="loc-match", work_mode=WorkMode.REMOTE, location="New York, NY")
    mismatched_job = build_job(job_id="loc-mismatch", work_mode=WorkMode.ONSITE, location="Boise, ID")
    match_score = score_opportunity(candidate, matching_job, score_job_quality(matching_job), _neutral_signal())
    mismatch_score = score_opportunity(candidate, mismatched_job, score_job_quality(mismatched_job), _neutral_signal())
    passed = match_score.final_score > mismatch_score.final_score
    cases.append(
        EvalCase(
            "ranking:location_work_mode_mismatch_reduces_score",
            CATEGORY,
            passed,
            detail=f"match={match_score.final_score:.2f} mismatch={mismatch_score.final_score:.2f}",
        )
    )

    # 3. Historical signal influences score, but never dominates: swinging
    #    signal_value from 0 to 100 (all else equal) can move final_score
    #    by at most MAX_HISTORY_SIGNAL_WEIGHT * 100 points.
    job = build_job(job_id="hist-1")
    quality = score_job_quality(job)
    low_hist = score_opportunity(candidate, job, quality, _signal(0.0))
    high_hist = score_opportunity(candidate, job, quality, _signal(100.0))
    diff = high_hist.final_score - low_hist.final_score
    max_allowed_swing = MAX_HISTORY_SIGNAL_WEIGHT * 100.0 + 1e-6
    passed = 0.0 < diff <= max_allowed_swing
    cases.append(
        EvalCase(
            "ranking:historical_signal_influences_but_bounded",
            CATEGORY,
            passed,
            detail=f"diff={diff:.4f} max_allowed={max_allowed_swing:.4f}",
        )
    )

    # 4. A sparse job description must not produce unjustified HIGH confidence.
    sparse_job = build_job(
        job_id="sparse-conf-1",
        description="Join our team.",
        required_skills=[],
        preferred_skills=[],
        minimum_years_experience=None,
        employment_type=None,
        location=None,
        work_mode=None,
    )
    sparse_quality = score_job_quality(sparse_job)
    sparse_score = score_opportunity(candidate, sparse_job, sparse_quality, _neutral_signal())
    passed = sparse_score.confidence != ConfidenceLevel.HIGH
    cases.append(
        EvalCase(
            "ranking:sparse_jd_never_high_confidence",
            CATEGORY,
            passed,
            detail=f"confidence={sparse_score.confidence.value} components_missing="
            f"{[k for k, c in sparse_score.components.items() if c.missing_data]}",
        )
    )

    # 5. A rich, well-matched job with real (non-neutral) historical data on
    #    every component DOES reach HIGH confidence -- confirms case 4
    #    isn't just "always LOW" regardless of input.
    rich_job = build_job(job_id="rich-conf-1")
    rich_score = score_opportunity(candidate, rich_job, score_job_quality(rich_job), _signal(70.0))
    passed = rich_score.confidence == ConfidenceLevel.HIGH
    cases.append(
        EvalCase(
            "ranking:rich_well_specified_jd_reaches_high_confidence",
            CATEGORY,
            passed,
            detail=f"confidence={rich_score.confidence.value}",
        )
    )

    return summarize(CATEGORY, cases)


if __name__ == "__main__":
    result = run()
    print(result.to_dict())
