"""Nodes covering job ingestion through quality scoring/eligibility."""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from src.config.workflow import DEFAULT_JOB_BATCH_PATH, JOB_QUALITY_EXCLUDED_RECOMMENDATIONS
from src.graph.helpers import make_error, trace_event
from src.graph.state import HireLoopState
from src.models.job import JobPosting
from src.models.workflow_error import ErrorCategory
from src.models.workflow_status import WorkflowStatus
from src.services.deduplication import dedupe_jobs
from src.services.job_ingestion import JobIngestionError, load_seeded_jobs
from src.services.job_quality import score_job_quality
from src.services.normalization import normalize_company, normalize_location, normalize_title


def ingest_jobs_node(state: HireLoopState, config: RunnableConfig) -> dict:
    configurable = config.get("configurable") or {}
    batch_path = configurable.get("job_batch_path", DEFAULT_JOB_BATCH_PATH)

    # Optional live-discovery override (You.com Web Search, opt-in only --
    # see src/services/you_search.py). Absent in every DEMO_MODE run, so the
    # branch below is dead code in the certification demo path and behavior
    # there is byte-for-byte unchanged from before this override existed.
    job_source_override = configurable.get("job_source_override")
    if job_source_override:
        job_dicts = list(job_source_override)
        ingestion_warnings: list[str] = []
        events = [
            trace_event(
                "ingestion",
                "ingest_jobs",
                f"{len(job_dicts)} job(s) ingested from live web discovery (You.com).",
                metadata={"source": "you_com"},
            )
        ]
    else:
        try:
            job_dicts, ingestion_warnings = load_seeded_jobs(batch_path)
        except JobIngestionError as exc:
            error = make_error("ingest_jobs", ErrorCategory.JOB_INGESTION_ERROR, str(exc), retryable=False)
            return {"errors": [error], "workflow_status": WorkflowStatus.FAILED.value, "current_step": "ingest_jobs"}

        events = [trace_event("ingestion", "ingest_jobs", f"{len(job_dicts)} demo jobs ingested.", metadata={"source": batch_path})]

    for warning in ingestion_warnings:
        events.append(trace_event("ingestion", "ingest_jobs", warning))

    counts = dict(state.get("counts") or {})
    counts["ingested"] = len(job_dicts)

    return {
        "raw_jobs": job_dicts,
        "decision_trace": events,
        "current_step": "ingest_jobs",
        "counts": counts,
    }


def normalize_jobs_node(state: HireLoopState, config: RunnableConfig) -> dict:
    raw_jobs = state.get("raw_jobs", [])
    normalized = []
    for job_dict in raw_jobs:
        enriched = dict(job_dict)
        metadata = dict(enriched.get("metadata") or {})
        metadata["normalized_title"] = normalize_title(enriched["title"])
        metadata["normalized_company"] = normalize_company(enriched["company"])
        if enriched.get("location"):
            metadata["normalized_location"] = normalize_location(enriched["location"])
        enriched["metadata"] = metadata
        normalized.append(enriched)

    return {
        "normalized_jobs": normalized,
        "decision_trace": [trace_event("normalization", "normalize_jobs", f"{len(normalized)} jobs normalized for comparison.")],
        "current_step": "normalize_jobs",
    }


def dedupe_jobs_node(state: HireLoopState, config: RunnableConfig) -> dict:
    jobs = [JobPosting(**d) for d in state.get("normalized_jobs", [])]
    kept, dedup_log = dedupe_jobs(jobs)

    counts = dict(state.get("counts") or {})
    counts["duplicates_removed"] = dedup_log["removed_count"]
    counts["unique_after_dedup"] = len(kept)

    return {
        "deduped_jobs": [job.model_dump(mode="json") for job in kept],
        "duplicate_results": dedup_log["removed"],
        "decision_trace": [
            trace_event(
                "dedup",
                "dedupe_jobs",
                f"{dedup_log['removed_count']} duplicate posting(s) removed.",
                metadata={"removed_count": dedup_log["removed_count"]},
            )
        ],
        "current_step": "dedupe_jobs",
        "counts": counts,
    }


def score_job_quality_node(state: HireLoopState, config: RunnableConfig) -> dict:
    jobs = [JobPosting(**d) for d in state.get("deduped_jobs", [])]

    quality_results: dict[str, dict] = {}
    excluded: list[dict] = []
    eligible_ids: list[str] = []
    needs_review_count = 0

    for job in jobs:
        result = score_job_quality(job)
        quality_results[job.job_id] = result.model_dump(mode="json")
        if result.recommendation.value in JOB_QUALITY_EXCLUDED_RECOMMENDATIONS:
            excluded.append(
                {"job_id": job.job_id, "reason": "low_quality", "quality_score": result.quality_score, "flags": result.flags}
            )
        else:
            eligible_ids.append(job.job_id)
            if result.recommendation.value == "NEEDS_REVIEW":
                needs_review_count += 1

    counts = dict(state.get("counts") or {})
    counts["low_quality_excluded"] = len(excluded)
    counts["needs_review"] = needs_review_count
    counts["eligible_after_quality"] = len(eligible_ids)

    message = f"{len(excluded)} low-quality listing(s) excluded; {len(eligible_ids)} eligible for scoring."
    if needs_review_count:
        message += f" {needs_review_count} flagged NEEDS_REVIEW but remain eligible."

    return {
        "job_quality_results": quality_results,
        "eligible_job_ids": eligible_ids,
        "excluded_jobs": state.get("excluded_jobs", []) + excluded,
        "decision_trace": [trace_event("quality", "score_job_quality", message, metadata={"excluded": len(excluded)})],
        "current_step": "score_job_quality",
        "counts": counts,
    }
