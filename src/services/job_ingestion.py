"""
Deterministic job ingestion from a seeded local batch (JSON, MVP-only).

Live scraping is explicitly out of scope for the MVP (docs/DECISIONS.md #10).
A file-level failure (missing file, invalid JSON, wrong top-level shape) is
a controlled JobIngestionError. An individual malformed job entry inside an
otherwise-valid batch is skipped with a warning rather than failing the
whole ingestion — one bad row shouldn't block 14 good ones.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from src.models.job import JobPosting


class JobIngestionError(Exception):
    """File-level ingestion failure: missing file, invalid JSON, wrong shape."""


def load_seeded_jobs(path: str) -> tuple[list[dict], list[str]]:
    """Returns (job_dicts, warnings). Raises JobIngestionError on a
    file-level failure that makes the whole batch unusable."""
    file_path = Path(path)
    if not file_path.exists():
        raise JobIngestionError(f"job batch file not found: {path}")

    try:
        raw = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise JobIngestionError(f"job batch file is not valid JSON: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise JobIngestionError(f"job batch file is not valid UTF-8 text: {exc}") from exc

    if not isinstance(raw, list):
        raise JobIngestionError("job batch file must contain a JSON array of job objects")

    jobs: list[dict] = []
    warnings: list[str] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            warnings.append(f"skipped malformed job entry at index {index}: not a JSON object")
            continue
        try:
            job = JobPosting(**entry)
        except ValidationError as exc:
            warnings.append(f"skipped malformed job entry at index {index}: {exc.error_count()} validation error(s)")
            continue
        jobs.append(job.model_dump(mode="json"))

    return jobs, warnings
