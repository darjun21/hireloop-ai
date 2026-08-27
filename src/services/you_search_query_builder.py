"""
Deterministic You.com search query construction. No LLM involved.

Builds one short query per target-role family: role + location + work mode
+ up to a handful of top skills. Queries are capped at
settings.you_search_max_queries_per_run as a hard cost control (see
docs/DECISIONS.md) -- this function never issues more queries than that,
regardless of how many roles/skills are supplied.
"""

from __future__ import annotations

_MAX_SKILLS_PER_QUERY = 3


def build_job_search_queries(
    target_roles: list[str],
    *,
    location: str | None = None,
    work_mode: str | None = None,
    skills: list[str] | None = None,
    max_queries: int = 4,
) -> list[str]:
    """One query per target role family (deduped, order-preserving),
    truncated to at most `max_queries`. Skills are truncated to the top
    `_MAX_SKILLS_PER_QUERY` so queries stay short -- not every skill is
    included."""
    max_queries = max(0, max_queries)
    if max_queries == 0:
        return []

    roles = [r.strip() for r in target_roles if r and r.strip()]
    # Dedupe case-insensitively while preserving first-seen order/casing.
    seen: set[str] = set()
    unique_roles: list[str] = []
    for role in roles:
        key = role.lower()
        if key not in seen:
            seen.add(key)
            unique_roles.append(role)

    if not unique_roles:
        unique_roles = ["jobs"]

    top_skills = [s.strip() for s in (skills or []) if s and s.strip()][:_MAX_SKILLS_PER_QUERY]

    queries: list[str] = []
    for role in unique_roles[:max_queries]:
        segments = [role]
        if top_skills:
            segments.append(" ".join(top_skills))
        segments.append("job openings")
        if location and location.strip():
            segments.append(location.strip())
        if work_mode and work_mode.strip():
            segments.append(work_mode.strip())
        queries.append(" ".join(segments))

    return queries
