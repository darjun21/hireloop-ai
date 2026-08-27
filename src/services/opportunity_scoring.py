"""
Deterministic Opportunity Scoring Engine.

Computes the final weighted opportunity score for a candidate/job pair
using the versioned, frozen weights in src/config/scoring.py. This module
owns the numeric score; no agent may modify its output
(see docs/ARCHITECTURE.md section 8, docs/DECISIONS.md #1 and #7).

NO LLM CALLS. Every component score is a plain, explainable calculation so
a later Match Analyst agent can narrate *why* a score came out the way it
did without inventing a rationale.
"""

from __future__ import annotations

from difflib import SequenceMatcher

from src.config.scoring import get_scoring_config
from src.models.candidate import CandidateProfile
from src.models.enums import ConfidenceLevel, RecommendationBand
from src.models.job import JobPosting
from src.models.job_quality import JobQualityResult
from src.models.scoring import ComponentScore, OpportunityScore
from src.models.strategy_insight import StrategyInsight
from src.services.normalization import normalize_location, normalize_skill, normalize_title

# Score used for a component when there isn't enough data to evaluate it.
_NEUTRAL_SCORE = 50.0

_OVERQUALIFIED_YEARS_THRESHOLD = 10.0
_OVERQUALIFIED_SCORE = 85.0
_EXPERIENCE_GAP_PENALTY_PER_YEAR = 20.0


def _clip(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _skill_match(candidate: CandidateProfile, job: JobPosting) -> ComponentScore:
    candidate_skills = {normalize_skill(s.name).lower() for s in candidate.skills}
    required = {normalize_skill(s).lower() for s in job.required_skills}
    preferred = {normalize_skill(s).lower() for s in job.preferred_skills}

    if not required and not preferred:
        return ComponentScore(
            name="skill_match",
            value=_NEUTRAL_SCORE,
            weight=0.0,
            weighted_contribution=0.0,
            explanation="Job listed no required or preferred skills; using a neutral score.",
            missing_data=True,
        )

    required_ratio = (len(required & candidate_skills) / len(required)) if required else 1.0
    preferred_ratio = (len(preferred & candidate_skills) / len(preferred)) if preferred else 1.0

    if required:
        value = _clip(100 * (0.8 * required_ratio + 0.2 * preferred_ratio))
    else:
        value = _clip(100 * preferred_ratio)

    matched_required = sorted(required & candidate_skills)
    missing_required = sorted(required - candidate_skills)
    explanation = (
        f"Matched {len(matched_required)}/{len(required)} required skills "
        f"({', '.join(matched_required) or 'none'}); missing: {', '.join(missing_required) or 'none'}."
    )
    return ComponentScore(name="skill_match", value=value, weight=0.0, weighted_contribution=0.0, explanation=explanation)


def _experience_match(candidate: CandidateProfile, job: JobPosting) -> ComponentScore:
    if job.minimum_years_experience is None:
        return ComponentScore(
            name="experience_match",
            value=_NEUTRAL_SCORE,
            weight=0.0,
            weighted_contribution=0.0,
            explanation="Job listed no minimum years of experience; using a neutral score.",
            missing_data=True,
        )

    diff = candidate.years_experience - job.minimum_years_experience
    if diff >= 0:
        value = _OVERQUALIFIED_SCORE if diff > _OVERQUALIFIED_YEARS_THRESHOLD else 100.0
        explanation = (
            f"Candidate has {candidate.years_experience} years vs. a {job.minimum_years_experience}-year "
            "minimum; requirement met."
        )
    else:
        shortfall = abs(diff)
        value = _clip(100 - shortfall * _EXPERIENCE_GAP_PENALTY_PER_YEAR)
        explanation = (
            f"Candidate has {candidate.years_experience} years vs. a {job.minimum_years_experience}-year "
            f"minimum; short by {shortfall:.1f} years."
        )
    return ComponentScore(name="experience_match", value=value, weight=0.0, weighted_contribution=0.0, explanation=explanation)


def _role_alignment(candidate: CandidateProfile, job: JobPosting) -> ComponentScore:
    if not candidate.target_roles:
        return ComponentScore(
            name="role_alignment",
            value=_NEUTRAL_SCORE,
            weight=0.0,
            weighted_contribution=0.0,
            explanation="Candidate listed no target roles; using a neutral score.",
            missing_data=True,
        )

    normalized_title = normalize_title(job.title)
    best_ratio = 0.0
    best_role = ""
    for role in candidate.target_roles:
        ratio = SequenceMatcher(None, normalize_title(role), normalized_title).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_role = role

    value = _clip(best_ratio * 100)
    explanation = f"Closest target role '{best_role}' vs. job title '{job.title}': {best_ratio * 100:.0f}% similarity."
    return ComponentScore(name="role_alignment", value=value, weight=0.0, weighted_contribution=0.0, explanation=explanation)


def _location_work_mode_match(candidate: CandidateProfile, job: JobPosting) -> ComponentScore:
    if job.work_mode is None and not job.location:
        return ComponentScore(
            name="location_work_mode",
            value=_NEUTRAL_SCORE,
            weight=0.0,
            weighted_contribution=0.0,
            explanation="Job listed no location or work mode; using a neutral score.",
            missing_data=True,
        )

    if job.work_mode is not None and job.work_mode in candidate.preferred_work_modes:
        return ComponentScore(
            name="location_work_mode",
            value=100.0,
            weight=0.0,
            weighted_contribution=0.0,
            explanation=f"Job work mode '{job.work_mode.value}' matches a candidate-preferred work mode.",
        )

    if job.location and candidate.target_locations:
        normalized_job_location = normalize_location(job.location)
        if any(normalize_location(loc) == normalized_job_location for loc in candidate.target_locations):
            return ComponentScore(
                name="location_work_mode",
                value=70.0,
                weight=0.0,
                weighted_contribution=0.0,
                explanation=f"Job location '{job.location}' matches a candidate target location.",
            )

    if not candidate.preferred_work_modes and not candidate.target_locations:
        return ComponentScore(
            name="location_work_mode",
            value=_NEUTRAL_SCORE,
            weight=0.0,
            weighted_contribution=0.0,
            explanation="Candidate listed no location/work-mode preferences; using a neutral score.",
            missing_data=True,
        )

    return ComponentScore(
        name="location_work_mode",
        value=20.0,
        weight=0.0,
        weighted_contribution=0.0,
        explanation="Job location and work mode do not match any candidate preference.",
    )


def _candidate_preference_alignment(candidate: CandidateProfile, job: JobPosting) -> ComponentScore:
    allowed_types = candidate.employment_preferences.employment_types
    if job.employment_type is None or not allowed_types:
        return ComponentScore(
            name="candidate_preference",
            value=_NEUTRAL_SCORE,
            weight=0.0,
            weighted_contribution=0.0,
            explanation="Employment type preference or job employment type unknown; using a neutral score.",
            missing_data=True,
        )

    if job.employment_type in allowed_types:
        return ComponentScore(
            name="candidate_preference",
            value=100.0,
            weight=0.0,
            weighted_contribution=0.0,
            explanation=f"Job employment type '{job.employment_type.value}' matches candidate preference.",
        )

    return ComponentScore(
        name="candidate_preference",
        value=20.0,
        weight=0.0,
        weighted_contribution=0.0,
        explanation=f"Job employment type '{job.employment_type.value}' is not among candidate-preferred types.",
    )


def _historical_signal_component(historical_signal: StrategyInsight) -> ComponentScore:
    return ComponentScore(
        name="historical_signal",
        value=historical_signal.signal_value,
        weight=0.0,
        weighted_contribution=0.0,
        explanation=historical_signal.explanation,
        missing_data=historical_signal.is_neutral,
    )


def _job_quality_component(job_quality: JobQualityResult) -> ComponentScore:
    return ComponentScore(
        name="job_quality",
        value=job_quality.quality_score,
        weight=0.0,
        weighted_contribution=0.0,
        explanation=f"Job quality flags: {', '.join(job_quality.flags) or 'none'}.",
        missing_data=bool(job_quality.flags),
    )


def _recommendation_for(final_score: float) -> RecommendationBand:
    if final_score >= 90:
        return RecommendationBand.HIGH_PRIORITY
    if final_score >= 80:
        return RecommendationBand.STRONG_MATCH
    if final_score >= 70:
        return RecommendationBand.CONSIDER
    return RecommendationBand.LOW_PRIORITY


def _confidence_for(components: dict[str, ComponentScore]) -> ConfidenceLevel:
    missing_count = sum(1 for c in components.values() if c.missing_data)
    if missing_count >= 3:
        return ConfidenceLevel.LOW
    if missing_count >= 1:
        return ConfidenceLevel.MEDIUM
    return ConfidenceLevel.HIGH


def score_opportunity(
    candidate: CandidateProfile,
    job: JobPosting,
    job_quality: JobQualityResult,
    historical_signal: StrategyInsight,
) -> OpportunityScore:
    scoring_version, weights = get_scoring_config()
    weight_map = weights.as_dict()

    raw_components = {
        "skill_match": _skill_match(candidate, job),
        "experience_match": _experience_match(candidate, job),
        "role_alignment": _role_alignment(candidate, job),
        "location_work_mode": _location_work_mode_match(candidate, job),
        "candidate_preference": _candidate_preference_alignment(candidate, job),
        "historical_signal": _historical_signal_component(historical_signal),
        "job_quality": _job_quality_component(job_quality),
    }

    components: dict[str, ComponentScore] = {}
    final_score = 0.0
    for key, component in raw_components.items():
        weight = weight_map[key]
        weighted_contribution = component.value * weight
        final_score += weighted_contribution
        components[key] = component.model_copy(update={"weight": weight, "weighted_contribution": weighted_contribution})

    final_score = _clip(final_score)

    return OpportunityScore(
        job_id=job.job_id,
        candidate_id=candidate.candidate_id,
        scoring_version=scoring_version,
        components=components,
        final_score=final_score,
        recommendation=_recommendation_for(final_score),
        confidence=_confidence_for(components),
        historical_sample_size=historical_signal.sample_size,
    )
