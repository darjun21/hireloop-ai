"""Nodes covering historical signal calculation and deterministic opportunity scoring."""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from src.config.scoring import get_scoring_config
from src.graph.helpers import make_error, trace_event
from src.graph.state import HireLoopState
from src.models.application import Application
from src.models.candidate import CandidateProfile
from src.models.job import JobPosting
from src.models.job_quality import JobQualityResult
from src.models.strategy_insight import StrategyInsight
from src.models.workflow_error import ErrorCategory
from src.models.workflow_status import WorkflowStatus
from src.services.historical_signal import calculate_historical_signal
from src.services.opportunity_scoring import score_opportunity


def calculate_historical_signal_node(state: HireLoopState, config: RunnableConfig) -> dict:
    preferences = state.get("preferences") or {}
    role_families = preferences.get("target_roles") or ["general"]

    # No application-history persistence is wired into the graph yet
    # (mem0/Learning Agent are later phases) -- historical_applications is
    # an optional dev/test injection point via config, empty by default,
    # which correctly yields a neutral signal for every role family.
    raw_applications = (config.get("configurable") or {}).get("historical_applications", [])
    applications = [Application(**a) for a in raw_applications]

    context = {}
    for role in role_families:
        insight = calculate_historical_signal(role, applications)
        context[role] = insight.model_dump(mode="json")

    sample_sizes = [v["sample_size"] for v in context.values()]
    message = f"Historical signal computed for {len(context)} role famil{'y' if len(context) == 1 else 'ies'} (sample sizes: {sample_sizes})."

    return {
        "historical_signal_context": context,
        "decision_trace": [trace_event("historical_signal", "calculate_historical_signal", message)],
        "current_step": "calculate_historical_signal",
    }


def score_opportunities_node(state: HireLoopState, config: RunnableConfig) -> dict:
    candidate_dict = state.get("candidate_profile")
    if not candidate_dict:
        error = make_error(
            "score_opportunities",
            ErrorCategory.SCORING_ERROR,
            "candidate profile is unavailable; cannot produce trustworthy recommendations",
            retryable=False,
        )
        return {"errors": [error], "workflow_status": WorkflowStatus.FAILED.value, "current_step": "score_opportunities"}

    try:
        scoring_version, weights = get_scoring_config()
    except AssertionError as exc:
        error = make_error(
            "score_opportunities", ErrorCategory.SCORING_ERROR, f"scoring configuration is invalid: {exc}", retryable=False
        )
        return {"errors": [error], "workflow_status": WorkflowStatus.FAILED.value, "current_step": "score_opportunities"}

    candidate = CandidateProfile(**candidate_dict)
    eligible_ids = state.get("eligible_job_ids", [])
    quality_results = state.get("job_quality_results", {})
    deduped_by_id = {d["job_id"]: d for d in state.get("deduped_jobs", [])}
    historical_context = state.get("historical_signal_context", {})

    default_role = next(iter(historical_context), None)
    default_insight = (
        StrategyInsight(**historical_context[default_role]) if default_role else calculate_historical_signal("general", [])
    )

    scores: dict[str, dict] = {}
    still_eligible: list[str] = []
    scoring_failures: list[dict] = []

    for job_id in eligible_ids:
        job_dict = deduped_by_id.get(job_id)
        quality_dict = quality_results.get(job_id)
        if not job_dict or not quality_dict:
            scoring_failures.append({"job_id": job_id, "reason": "missing job or quality data for this job_id"})
            continue
        try:
            job = JobPosting(**job_dict)
            quality = JobQualityResult(**quality_dict)
            score = score_opportunity(candidate, job, quality, default_insight)
        except Exception as exc:  # noqa: BLE001 - isolate one bad job, keep the batch going
            scoring_failures.append({"job_id": job_id, "reason": str(exc)[:200]})
            continue
        scores[job_id] = score.model_dump(mode="json")
        still_eligible.append(job_id)

    counts = dict(state.get("counts") or {})
    counts["scored"] = len(scores)
    counts["scoring_failures"] = len(scoring_failures)

    message = f"{len(scores)} opportunities scored using scoring model {scoring_version}."
    if scoring_failures:
        message += f" {len(scoring_failures)} job(s) could not be scored and were isolated."

    update: dict = {
        "opportunity_scores": scores,
        "eligible_job_ids": still_eligible,
        "decision_trace": [trace_event("scoring", "score_opportunities", message, metadata={"failures": len(scoring_failures)})],
        "current_step": "score_opportunities",
        "counts": counts,
    }
    if scoring_failures:
        update["excluded_jobs"] = state.get("excluded_jobs", []) + [
            {"job_id": f["job_id"], "reason": "scoring_failed", "detail": f["reason"]} for f in scoring_failures
        ]
    return update
