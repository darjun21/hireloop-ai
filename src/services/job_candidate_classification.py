"""
Deterministic (no LLM) classifier for You.com web search results.

Decides whether a raw WebJobSearchResult looks like an actual job posting
before it is allowed to enter the normalize/dedupe/quality pipeline as a
JobPosting. This is a coarse triage filter, not a scraper: it only reads
signals already present in the title/url/snippet/highlights returned by the
search API -- it never fetches the page, never builds a per-domain parser,
and never uses an LLM. Scoring "is this a good job for the candidate" stays
entirely the responsibility of the existing Opportunity Scoring Engine.

Buckets:
  LIKELY_JOB   -- converted to a JobPostingCandidate and enters normalization.
  POSSIBLE_JOB -- surfaced in the Decision Trace as "review manually," not
                  auto-included.
  NOT_JOB      -- dropped, counted in the Decision Trace.
"""

from __future__ import annotations

import re

from src.models.web_job_search import JobPostingCandidate, WebJobClassification, WebJobSearchResult

# URL path segments used by common job boards / ATS platforms. Pattern
# signals only -- never a per-domain scraper.
_JOB_URL_PATTERNS = re.compile(r"/(jobs?|careers?|positions?|openings?)/", re.IGNORECASE)
_JOB_BOARD_DOMAINS = (
    "greenhouse.io",
    "lever.co",
    "myworkdayjobs.com",
    "jobs.ashbyhq.com",
    "ashbyhq.com",
    "smartrecruiters.com",
    "linkedin.com/jobs",
    "indeed.com",
    "workable.com",
    "bamboohr.com",
    "icims.com",
    "jobvite.com",
)

# Non-job content that superficially resembles a job listing (articles,
# listicles, salary-guide content) -- URL/title patterns that count AGAINST
# a job classification.
_NON_JOB_TITLE_PATTERNS = re.compile(
    r"\b(top \d+|best \d+|how to|guide to|salary guide|interview questions|resume tips|"
    r"career advice|\d+ (jobs|companies|tips)|listicle)\b",
    re.IGNORECASE,
)

_ROLE_NOUNS = re.compile(
    r"\b(engineer|developer|manager|analyst|scientist|designer|architect|consultant|specialist|"
    r"director|lead|coordinator|administrator|technician|associate|intern|recruiter)\b",
    re.IGNORECASE,
)

_EMPLOYMENT_LANGUAGE = re.compile(
    r"\b(apply now|we are hiring|we're hiring|now hiring|responsibilities|requirements|"
    r"qualifications|job description|years of experience|years experience|full[- ]time|"
    r"part[- ]time|join our team|open position|equal opportunity employer)\b",
    re.IGNORECASE,
)


def _score_signals(result: WebJobSearchResult) -> tuple[int, int]:
    """Returns (positive_signal_count, negative_signal_count)."""
    positive = 0
    negative = 0

    title = result.title or ""
    url = (result.url or "").lower()
    combined_text = " ".join([result.snippet or "", *(result.highlights or [])])

    if _NON_JOB_TITLE_PATTERNS.search(title):
        negative += 2

    if _ROLE_NOUNS.search(title):
        positive += 1

    if _JOB_URL_PATTERNS.search(url):
        positive += 1

    if any(domain in url for domain in _JOB_BOARD_DOMAINS):
        positive += 2

    employment_matches = len(_EMPLOYMENT_LANGUAGE.findall(combined_text))
    if employment_matches >= 2:
        positive += 2
    elif employment_matches == 1:
        positive += 1

    if not combined_text.strip() and positive == 0:
        # No snippet/highlight text at all and nothing else pointed to a job.
        negative += 1

    return positive, negative


def classify_web_result(result: WebJobSearchResult) -> WebJobClassification:
    """Deterministically bucket a web search result. See module docstring
    for the signals used."""
    positive, negative = _score_signals(result)
    net = positive - negative

    if negative >= 2 and net <= 0:
        return "NOT_JOB"
    if net >= 3:
        return "LIKELY_JOB"
    if net >= 1:
        return "POSSIBLE_JOB"
    return "NOT_JOB"


_LOCATION_HINT = re.compile(r"\b(remote|hybrid|onsite|on-site)\b", re.IGNORECASE)


def build_candidate(result: WebJobSearchResult) -> JobPostingCandidate:
    """Classify a result and attach best-effort (never fabricated) field
    guesses. Only the classification decides downstream handling -- the
    guesses are advisory metadata, not validated job facts."""
    classification = classify_web_result(result)

    title_guess = result.title.strip() or None

    company_guess: str | None = None
    if " at " in result.title:
        candidate = result.title.rsplit(" at ", 1)[-1].strip(" -|")
        if candidate:
            company_guess = candidate
    elif " - " in result.title:
        parts = [p.strip() for p in result.title.split(" - ") if p.strip()]
        if len(parts) >= 2:
            company_guess = parts[-1]

    location_guess: str | None = None
    combined_text = " ".join([result.title, result.snippet, *(result.highlights or [])])
    match = _LOCATION_HINT.search(combined_text)
    if match:
        location_guess = match.group(0).title()

    return JobPostingCandidate(
        result=result,
        classification=classification,
        title_guess=title_guess,
        company_guess=company_guess,
        location_guess=location_guess,
    )
