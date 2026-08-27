"""
Phase 3 developer demo: drives the real LangGraph workflow end to end,
including the human job-selection interrupt/resume, from the terminal.

    python -m scripts.run_phase3_demo

This is a thin developer harness, not the Streamlit UI. All input()/print()
calls live here — the graph nodes themselves contain none.

Uses MockLLMProvider by default (no API keys needed). Set
DEFAULT_LLM_PROVIDER=nebius|fireworks with the matching env vars to use a
real provider instead.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langgraph.types import Command

from src.config.settings import load_settings
from src.config.workflow import DEFAULT_CHECKPOINT_DB_PATH, DEFAULT_JOB_BATCH_PATH
from src.graph.checkpointing import get_sqlite_checkpointer
from src.graph.workflow import build_workflow
from src.llm.provider import get_llm_client

DEMO_RESUME_PATH = "data/sample_candidate/demo_resume.txt"


def _print_recommendations(selections: list[dict]) -> None:
    print("\nTop opportunities:\n")
    for i, item in enumerate(selections, start=1):
        print(f"  [{i}] {item['title']} at {item['company']} ({item.get('location') or 'location unknown'})")
        print(f"      Score: {item['final_score']:.1f} - {item['recommendation']} (confidence: {item['confidence']})")
        if item.get("strengths"):
            print(f"      Strengths: {'; '.join(item['strengths'])}")
        if item.get("gaps"):
            print(f"      Gaps: {'; '.join(item['gaps'])}")
        print()


def _prompt_for_selection(selections: list[dict], error: str | None) -> dict:
    if error:
        print(f"  ! {error}\n")
    print("Enter a number to select that opportunity, or 'c' to cancel:")
    raw = input("> ").strip().lower()
    if raw == "c":
        return {"action": "CANCEL"}
    try:
        index = int(raw)
    except ValueError:
        return {"action": "SELECT", "job_id": raw}  # deliberately invalid -> graph rejects and re-prompts
    if 1 <= index <= len(selections):
        return {"action": "SELECT", "job_id": selections[index - 1]["job_id"]}
    return {"action": "SELECT", "job_id": f"<out-of-range:{index}>"}


def main() -> None:
    print("=" * 60)
    print("HireLoop AI - Phase 3 developer demo")
    print("=" * 60)

    settings = load_settings()
    llm_client = get_llm_client(settings)
    print(f"\nLLM provider: {llm_client.primary.name}" + (" (mock, not a live model)" if llm_client.primary.name == "mock" else ""))

    checkpointer = get_sqlite_checkpointer(DEFAULT_CHECKPOINT_DB_PATH)
    app = build_workflow(checkpointer)

    run_id = f"demo-{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": run_id, "llm_client": llm_client, "job_batch_path": DEFAULT_JOB_BATCH_PATH}}

    print(f"\nLoading resume: {DEMO_RESUME_PATH}")
    print(f"Ingesting job batch: {DEFAULT_JOB_BATCH_PATH}")
    print("Running workflow (parse -> profile -> ingest -> score -> rank)...\n")

    result = app.invoke(
        {
            "run_id": run_id,
            "candidate_id": f"cand-{run_id}",
            "resume_file_path": DEMO_RESUME_PATH,
            "preferences": {"target_roles": ["AI Engineer"], "preferred_work_modes": ["REMOTE"]},
            "workflow_status": "NOT_STARTED",
        },
        config=config,
    )

    if result.get("workflow_status") == "FAILED":
        print("Workflow failed:")
        for err in result.get("errors", []):
            print(f"  [{err['category']}] {err['message']}")
        return

    if result.get("workflow_status") == "COMPLETED_WITH_NO_RESULTS":
        print("No suitable jobs remain after filtering/scoring.")
        print(result.get("no_suitable_jobs_reason"))
        return

    while "__interrupt__" in result:
        payload = result["__interrupt__"][0].value
        _print_recommendations(payload["eligible_selections"])
        human_response = _prompt_for_selection(payload["eligible_selections"], payload.get("error"))
        result = app.invoke(Command(resume=human_response), config=config)

    print("\n" + "=" * 60)
    if result.get("workflow_status") == "CANCELLED":
        print("Workflow cancelled by user.")
    else:
        selected_id = result.get("selected_job_id")
        deduped_by_id = {j["job_id"]: j for j in result.get("deduped_jobs", [])}
        selected_job = deduped_by_id.get(selected_id, {})
        print(f"Selected opportunity: {selected_job.get('title')} at {selected_job.get('company')} ({selected_id})")
        print(f"Workflow status: {result.get('workflow_status')}")

    print("\nDecision Trace:")
    for event in result.get("decision_trace", []):
        print(f"  -> {event['message']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
