"""
Deterministic normalization utilities.

These functions produce a *comparable* derived value from a raw string —
they never mutate or replace the original value stored on a model. Callers
that need the original text (e.g. for display) keep it separately; callers
that need to compare two values for equality/similarity (deduplication,
skill matching) use these.

No LLM calls. Alias/abbreviation maps here are intentionally small and
conservative — expand them only with clear, unambiguous entries.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

# Conservative title abbreviation expansions, applied per whitespace token
# (after stripping trailing punctuation) so "Sr." / "Sr" / "SENIOR" all
# converge to "senior" without touching unrelated words.
_TITLE_ABBREVIATIONS: dict[str, str] = {
    "sr": "senior",
    "jr": "junior",
}

# Legal-entity suffixes stripped only when they trail the normalized company
# name, so "Acme Inc." and "Acme" compare equal without mangling names that
# legitimately contain these words mid-string.
_COMPANY_SUFFIXES: tuple[str, ...] = (
    "incorporated",
    "corporation",
    "company",
    "limited",
    "inc",
    "llc",
    "ltd",
    "corp",
    "co",
)

# Small, explicit skill alias map. Matching is exact and case-insensitive —
# no fuzzy/partial matching, no LLM.
SKILL_ALIASES: dict[str, str] = {
    "js": "JavaScript",
    "javascript": "JavaScript",
    "ts": "TypeScript",
    "typescript": "TypeScript",
    "postgres": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "k8s": "Kubernetes",
    "kubernetes": "Kubernetes",
    "ml": "Machine Learning",
    "machine learning": "Machine Learning",
}

# Query parameters that identify tracking/campaign data rather than the
# resource itself, stripped when canonicalizing a URL for deduplication.
_TRACKING_QUERY_PARAMS: frozenset[str] = frozenset(
    {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "gclid",
        "fbclid",
        "ref",
        "referrer",
    }
)


def normalize_whitespace(text: str) -> str:
    """Collapse runs of whitespace to single spaces and strip the ends."""
    return re.sub(r"\s+", " ", text).strip()


def normalize_title(title: str) -> str:
    """Case/whitespace/abbreviation-insensitive form of a job title.

    "Sr. AI Engineer", "Senior AI Engineer", and "SENIOR AI ENGINEER" all
    normalize to "senior ai engineer".
    """
    collapsed = normalize_whitespace(title).lower()
    tokens = collapsed.split(" ")
    expanded = []
    for token in tokens:
        bare = token.strip(".,")
        expanded.append(_TITLE_ABBREVIATIONS.get(bare, bare))
    return " ".join(t for t in expanded if t)


def normalize_company(company: str) -> str:
    """Case/whitespace/legal-suffix-insensitive form of a company name."""
    collapsed = normalize_whitespace(company).lower().replace(",", "")
    collapsed = collapsed.rstrip(".")
    tokens = collapsed.split(" ")
    while tokens and tokens[-1].strip(".") in _COMPANY_SUFFIXES:
        tokens.pop()
    return " ".join(tokens).strip()


def normalize_location(location: str) -> str:
    """Case/whitespace-insensitive form of a location string."""
    collapsed = normalize_whitespace(location).lower().replace(".", "")
    collapsed = re.sub(r"\s*,\s*", ", ", collapsed)
    return collapsed


def normalize_skill(skill: str) -> str:
    """Map a skill to its canonical alias when one is explicitly known.

    Unknown skills are returned whitespace-normalized but otherwise
    untouched — we do not guess at canonical forms.
    """
    collapsed = normalize_whitespace(skill)
    return SKILL_ALIASES.get(collapsed.lower(), collapsed)


def normalize_url(url: str) -> str:
    """Canonicalize a URL for comparison: lowercase scheme/host, drop the
    fragment and known tracking query params, drop a trailing slash.
    """
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    netloc = parts.netloc.lower()
    path = parts.path.rstrip("/") or ""

    kept_query = [
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.lower() not in _TRACKING_QUERY_PARAMS
    ]
    kept_query.sort()
    query = urlencode(kept_query)

    return urlunsplit((scheme, netloc, path, query, ""))
