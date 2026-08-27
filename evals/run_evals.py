"""
HireLoop AI evaluation harness entry point.

Runs every category evaluator against real backend code (offline,
deterministic, Mock LLM provider only), prints a terminal summary, and
writes a machine-readable JSON report to evals/results/latest.json.

Usage: python -m evals.run_evals

Exit code is non-zero if any category reports a severe/safety-relevant
failure (e.g. any FALSE VERIFIED Truth Guard case, any UNSAFE_FAILURE in
failure recovery, any human-approval-enforcement violation) -- this is the
safety gate other tooling can check (`echo $?` / `$LASTEXITCODE`).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from evals.common import CategorySummary, write_json_report

_RESULTS_PATH = Path(__file__).parent / "results" / "latest.json"

_CATEGORY_MODULES = [
    "evals.resume_extraction",
    "evals.deduplication",
    "evals.job_quality",
    "evals.opportunity_ranking",
    "evals.match_grounding",
    "evals.truth_guard",
    "evals.human_approval",
    "evals.failure_recovery",
    "evals.outcome_analytics",
    "evals.learning_insight_grounding",
    "evals.end_to_end",
    "evals.live_discovery",
]


def _run_category(module_name: str) -> tuple[CategorySummary | None, str | None]:
    import importlib

    try:
        module = importlib.import_module(module_name)
        summary = module.run()
        return summary, None
    except Exception as exc:  # noqa: BLE001 - a crashing evaluator is itself a finding, not a harness bug to hide
        return None, f"{type(exc).__name__}: {exc}"


def _print_summary(summaries: list[CategorySummary], crashed: dict[str, str]) -> None:
    print("=" * 78)
    print("HireLoop AI Evaluation Harness")
    print("=" * 78)

    total_cases = 0
    total_passed = 0
    any_severe = False

    for summary in summaries:
        total_cases += summary.total
        total_passed += summary.passed
        marker = "SEVERE FAILURE" if summary.severe_failure else ("OK" if summary.accuracy == 100.0 else "issues")
        print(f"\n[{summary.category}] {summary.passed}/{summary.total} passed ({summary.accuracy:.1f}%) -- {marker}")
        if summary.counters:
            print(f"  counters: {summary.counters}")
        if summary.severe_failure:
            any_severe = True
            print(f"  !!! {summary.severe_failure_reason}")
        for case in summary.cases:
            if not case.passed:
                sev = " [CRITICAL]" if case.severity == "critical" else ""
                print(f"  FAIL{sev}: {case.id} -- {case.detail}")
        for note in summary.notes:
            print(f"  note: {note}")

    for module_name, error in crashed.items():
        any_severe = True
        print(f"\n[{module_name}] CRASHED -- {error}")

    print("\n" + "-" * 78)
    overall_accuracy = round(100.0 * total_passed / total_cases, 2) if total_cases else 0.0
    print(f"OVERALL: {total_passed}/{total_cases} cases passed ({overall_accuracy:.2f}%)")
    print(f"Categories run: {len(summaries)}/{len(_CATEGORY_MODULES)}  Categories crashed: {len(crashed)}")
    print(f"Safety gate: {'FAILED -- see SEVERE FAILURE / CRASHED entries above' if any_severe else 'PASSED'}")
    print("=" * 78)


def main() -> int:
    started_at = time.time()
    summaries: list[CategorySummary] = []
    crashed: dict[str, str] = {}

    for module_name in _CATEGORY_MODULES:
        summary, error = _run_category(module_name)
        if summary is not None:
            summaries.append(summary)
        if error is not None:
            crashed[module_name] = error

    _print_summary(summaries, crashed)

    total_cases = sum(s.total for s in summaries)
    total_passed = sum(s.passed for s in summaries)
    overall_accuracy = round(100.0 * total_passed / total_cases, 2) if total_cases else 0.0
    any_severe = any(s.severe_failure for s in summaries) or bool(crashed)

    overall = {
        "total_cases": total_cases,
        "total_passed": total_passed,
        "accuracy": overall_accuracy,
        "categories_run": len(summaries),
        "categories_total": len(_CATEGORY_MODULES),
        "categories_crashed": crashed,
        "safety_gate_passed": not any_severe,
        "duration_seconds": round(time.time() - started_at, 2),
    }
    write_json_report(_RESULTS_PATH, summaries, overall)
    print(f"\nJSON report written to {_RESULTS_PATH}")

    return 1 if any_severe else 0


if __name__ == "__main__":
    sys.exit(main())
