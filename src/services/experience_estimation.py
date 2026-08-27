"""
Deterministic, overlap-aware years-of-experience estimator.

This exists specifically so the Profile Agent never has to trust an LLM's
own "years of experience" guess at face value: two overlapping jobs must
not be double-counted, and unparseable dates must not be silently treated
as zero-length or dropped without a trace. No LLM.
"""

from __future__ import annotations

from datetime import date, datetime

_DATE_FORMATS = ("%Y-%m-%d", "%Y-%m", "%Y")
_PRESENT_TOKENS = {"present", "current", "now"}


def parse_resume_date(value: str | None) -> date | None:
    if not value:
        return None
    v = value.strip()
    if v.lower() in _PRESENT_TOKENS:
        return date.today()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(v, fmt).date()
        except ValueError:
            continue
    return None


def merge_intervals(intervals: list[tuple[date, date]]) -> list[tuple[date, date]]:
    if not intervals:
        return []
    ordered = sorted(intervals, key=lambda iv: iv[0])
    merged = [ordered[0]]
    for start, end in ordered[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def estimate_years_experience(date_ranges: list[tuple[str | None, str | None]]) -> tuple[float | None, list[str]]:
    """Returns (years, warnings). years is None when no date in the input
    could be parsed at all — callers must treat that as UNKNOWN, not zero."""
    warnings: list[str] = []
    intervals: list[tuple[date, date]] = []
    unparseable = 0

    for start_raw, end_raw in date_ranges:
        start = parse_resume_date(start_raw)
        if start is None:
            if start_raw is not None:
                unparseable += 1
            continue
        end = parse_resume_date(end_raw) or date.today()
        if end < start:
            warnings.append(f"employment end date before start date ('{start_raw}' - '{end_raw}'); interval ignored")
            continue
        intervals.append((start, end))

    if unparseable:
        warnings.append(
            f"{unparseable} employment date(s) could not be parsed and were excluded from the experience calculation"
        )

    if not intervals:
        warnings.append("no parseable employment dates; years of experience is unknown")
        return None, warnings

    merged = merge_intervals(intervals)
    total_days = sum((end - start).days for start, end in merged)
    return round(total_days / 365.25, 1), warnings
