"""
Models for the optional You.com live job discovery path.

This module intentionally keeps raw web-search retrieval (WebJobSearchResult)
separate from normalized job facts (JobPosting, in src/models/job.py). A web
search result is evidence that *something job-shaped* may exist at a URL --
it is not yet a trustworthy structured job posting. Only after deterministic
classification (src/services/job_candidate_classification.py) does a result
become a JobPostingCandidate, and only LIKELY_JOB candidates are converted to
JobPosting and fed into the existing normalize/dedupe/quality pipeline.

Nothing in this module scores, ranks, or judges candidate fit -- that
remains the job of the existing Opportunity Scoring Engine.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field

WebJobClassification = Literal["LIKELY_JOB", "POSSIBLE_JOB", "NOT_JOB"]


class WebJobSearchResult(BaseModel):
    """One raw result returned by the You.com Web Search API, after being
    parsed out of the vendor response shape (see src/services/you_search.py)
    -- never the raw vendor dict itself."""

    search_result_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    url: str = Field(..., min_length=1)
    source_domain: str = ""
    snippet: str = ""
    highlights: list[str] = Field(default_factory=list)
    published_or_discovered_date: date | None = None
    search_query: str = ""
    provider: Literal["YOU_COM"] = "YOU_COM"
    metadata: dict[str, Any] = Field(default_factory=dict)


class JobPostingCandidate(BaseModel):
    """A WebJobSearchResult plus a deterministic classification and
    best-effort extracted fields, BEFORE conversion to JobPosting. Kept
    separate from JobPosting so a low-confidence guess is never silently
    presented as a normalized job fact."""

    result: WebJobSearchResult
    classification: WebJobClassification

    # Best-effort guesses only -- never fabricated when not confidently
    # extractable. See src/services/job_candidate_classification.py.
    title_guess: str | None = None
    company_guess: str | None = None
    location_guess: str | None = None
