"""
Converts a LIKELY_JOB JobPostingCandidate into a JobPosting dict, ready to
be fed through the existing ingest_jobs_node override path (see
src/graph/nodes/jobs.py) and then the unmodified normalize/dedupe/quality
pipeline.

Fields are never fabricated: anything not confidently extractable from the
web search result is left at its default (empty list / None), so a sparse
web result naturally lands on LOW quality/evidence-completeness via the
EXISTING job quality service -- this module does not build a parallel
sparse-detection path.

posted_date is intentionally never set from search "freshness" metadata --
freshness is a search filter/signal, not proof of an actual posting date.
"""

from __future__ import annotations

import hashlib

from src.models.web_job_search import JobPostingCandidate


def _stable_job_id(candidate: JobPostingCandidate) -> str:
    digest = hashlib.sha256(candidate.result.url.encode("utf-8")).hexdigest()[:16]
    return f"you_com_{digest}"


def _build_description(candidate: JobPostingCandidate) -> str | None:
    result = candidate.result
    parts = [p.strip() for p in [result.snippet, *(result.highlights or [])] if p and p.strip()]
    if not parts:
        return None
    # Dedupe while preserving order -- You.com highlights sometimes repeat
    # the snippet verbatim.
    seen: set[str] = set()
    unique_parts = []
    for part in parts:
        if part not in seen:
            seen.add(part)
            unique_parts.append(part)
    return "\n".join(unique_parts)


def candidate_to_job_posting_dict(candidate: JobPostingCandidate) -> dict:
    """Only call this for LIKELY_JOB candidates -- POSSIBLE_JOB/NOT_JOB are
    handled separately (surfaced-but-not-included / dropped)."""
    result = candidate.result
    return {
        "job_id": _stable_job_id(candidate),
        "title": candidate.title_guess or result.title,
        "company": candidate.company_guess or "",
        "location": candidate.location_guess,
        "source": "you_com",
        "url": result.url,
        "description": _build_description(candidate),
        "required_skills": [],
        "preferred_skills": [],
        "minimum_years_experience": None,
        "employment_type": None,
        "work_mode": None,
        "posted_date": None,  # never inferred from search freshness
        "salary_min": None,
        "salary_max": None,
        "metadata": {
            "discovery_provider": "YOU_COM",
            "search_query": result.search_query,
            "source_domain": result.source_domain,
            "classification": candidate.classification,
        },
    }
