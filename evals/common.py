"""
Shared types and helpers for the evals/ harness.

Every category evaluator produces a list of EvalCase results and hands them
to `summarize()` to build a CategorySummary. run_evals.py collects all
CategorySummary objects, prints a terminal report, and writes a JSON report
via `write_json_report()`. No percentage/accuracy number anywhere in this
package is hardcoded -- every one is computed from actual pass/fail counts
at runtime.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class EvalCase:
    """One individual check within a category."""

    id: str
    category: str
    passed: bool
    detail: str = ""
    # "normal" | "critical" -- critical marks a case whose failure is a
    # safety-relevant event (e.g. a FALSE VERIFIED Truth Guard case, an
    # UNSAFE_FAILURE in failure recovery, a human-approval-enforcement
    # violation), independent of whether the case's own status field
    # already encodes that.
    severity: str = "normal"
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class CategorySummary:
    category: str
    total: int
    passed: int
    accuracy: float  # percentage, 0-100, computed from total/passed
    counters: dict[str, int] = field(default_factory=dict)
    cases: list[EvalCase] = field(default_factory=list)
    severe_failure: bool = False
    severe_failure_reason: str = ""
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "total": self.total,
            "passed": self.passed,
            "accuracy": self.accuracy,
            "counters": self.counters,
            "severe_failure": self.severe_failure,
            "severe_failure_reason": self.severe_failure_reason,
            "notes": self.notes,
            "cases": [asdict(c) for c in self.cases],
        }


def summarize(
    category: str,
    cases: list[EvalCase],
    counters: dict[str, int] | None = None,
    severe_failure: bool = False,
    severe_failure_reason: str = "",
    notes: list[str] | None = None,
) -> CategorySummary:
    total = len(cases)
    passed = sum(1 for c in cases if c.passed)
    accuracy = round(100.0 * passed / total, 2) if total else 0.0
    return CategorySummary(
        category=category,
        total=total,
        passed=passed,
        accuracy=accuracy,
        counters=counters or {},
        cases=cases,
        severe_failure=severe_failure,
        severe_failure_reason=severe_failure_reason,
        notes=notes or [],
    )


def write_json_report(path: str | Path, summaries: list[CategorySummary], overall: dict) -> None:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"overall": overall, "categories": [s.to_dict() for s in summaries]}
    out_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
