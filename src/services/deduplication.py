"""
Deterministic job duplicate detection.

No LLM, no Pinecone/embeddings — signals are normalized field equality plus
a lexical description-similarity ratio (difflib), which is enough to
distinguish reposts of the same listing from genuinely different roles.
"""

from __future__ import annotations

from difflib import SequenceMatcher

from src.models.dedup import DuplicateMatchResult
from src.models.job import JobPosting
from src.services.normalization import (
    normalize_company,
    normalize_location,
    normalize_title,
    normalize_url,
    normalize_whitespace,
)

# Best-match confidence at/above this threshold is treated as a duplicate.
DUPLICATE_CONFIDENCE_THRESHOLD = 0.70

_DESC_SIMILARITY_STRONG = 0.85
_DESC_SIMILARITY_POSSIBLE_REPOST = 0.90


def _description_similarity(a: str | None, b: str | None) -> float | None:
    if not a or not b:
        return None
    return SequenceMatcher(None, normalize_whitespace(a).lower(), normalize_whitespace(b).lower()).ratio()


def _compare_pair(job: JobPosting, other: JobPosting) -> tuple[float, list[str]]:
    """Return (confidence, reasons) that `job` is a duplicate of `other`."""
    same_company = normalize_company(job.company) == normalize_company(other.company)
    same_title = normalize_title(job.title) == normalize_title(other.title)

    same_location: bool | None = None
    if job.location and other.location:
        same_location = normalize_location(job.location) == normalize_location(other.location)

    same_url = False
    if job.url and other.url:
        same_url = normalize_url(job.url) == normalize_url(other.url)

    desc_similarity = _description_similarity(job.description, other.description)

    # 1. Identical canonicalized URL -> very high confidence, regardless of
    #    anything else (the listing is provably the same page).
    if same_url:
        return 0.98, ["identical canonicalized URL"]

    # 2. Same company + title, and same location (or location unknown for
    #    at least one side), but not matched by URL above -> likely a
    #    duplicate posted separately or re-scraped.
    if same_company and same_title:
        if same_location is True:
            return 0.90, ["same company, title, and location; different or missing URL"]
        if same_location is None:
            return 0.80, ["same company and title; location unknown on at least one listing"]
        # same_location is False: same company/title but stated locations
        # differ. Still plausibly the same role posted for multiple offices
        # only if the description is a near-exact match; otherwise treat as
        # distinct postings.
        if desc_similarity is not None and desc_similarity >= _DESC_SIMILARITY_STRONG:
            return 0.75, ["same company and title; differing location but near-identical description"]
        return 0.0, ["same company and title but differing location and dissimilar description"]

    # 3. Similar/same title but a different company is not a duplicate —
    #    many companies post nearly identical titles.
    if same_title and not same_company:
        return 0.0, ["similar title but different company"]

    # 4. Same company but a different title is only a duplicate if the
    #    description is essentially identical (e.g. a straight repost of
    #    the same role text under a slightly reworded title).
    if same_company and not same_title:
        if desc_similarity is not None and desc_similarity >= _DESC_SIMILARITY_POSSIBLE_REPOST:
            return 0.65, ["same company; different title but near-identical description"]
        return 0.0, ["same company but clearly different role"]

    return 0.0, ["no matching signals"]


def check_duplicate(job: JobPosting, existing_jobs: list[JobPosting]) -> DuplicateMatchResult:
    """Check `job` against a pool of already-accepted jobs.

    Returns the best (highest-confidence) match found, even below the
    duplicate threshold, so callers can inspect near-misses if needed.
    """
    best_confidence = -1.0
    best_reasons: list[str] = ["no candidates to compare against"]
    best_match_id: str | None = None

    for other in existing_jobs:
        if other.job_id == job.job_id:
            continue
        confidence, reasons = _compare_pair(job, other)
        if confidence > best_confidence:
            best_confidence = confidence
            best_reasons = reasons
            best_match_id = other.job_id

    best_confidence = max(best_confidence, 0.0)
    is_duplicate = best_confidence >= DUPLICATE_CONFIDENCE_THRESHOLD
    return DuplicateMatchResult(
        is_duplicate=is_duplicate,
        confidence=best_confidence,
        matched_job_id=best_match_id if is_duplicate else None,
        reasons=best_reasons,
    )


def dedupe_jobs(jobs: list[JobPosting]) -> tuple[list[JobPosting], dict]:
    """Filter a batch of jobs down to unique postings.

    Processes jobs in order, keeping the first occurrence of each duplicate
    group. Returns (deduped_jobs, dedup_log) where dedup_log feeds the
    Decision Trace.
    """
    kept: list[JobPosting] = []
    removed: list[dict] = []

    for job in jobs:
        result = check_duplicate(job, kept)
        if result.is_duplicate:
            removed.append(
                {
                    "job_id": job.job_id,
                    "matched_job_id": result.matched_job_id,
                    "confidence": result.confidence,
                    "reasons": result.reasons,
                }
            )
        else:
            kept.append(job)

    dedup_log = {
        "input_count": len(jobs),
        "kept_count": len(kept),
        "removed_count": len(removed),
        "removed": removed,
    }
    return kept, dedup_log
