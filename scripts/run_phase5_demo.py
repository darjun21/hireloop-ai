"""
Phase 5 developer demo: closes the HireLoop feedback loop end to end.

    python -m scripts.run_phase5_demo

Story:
1. Shows the seeded DEMO historical data (AI Engineer: 8 applications /
   3 interviews, ML Engineer: 5/2, Software Engineer: 7/1, plus a small
   Applied AI Engineer group) and its deterministic OutcomeAnalytics.
2. Runs the full Phase 3->4->5 graph for a new AI Engineer application,
   marks it APPLIED.
3. Runs the SEPARATE outcome-update workflow to record an INTERVIEW for
   that new application (simulating this happening days later).
4. Outcome analytics refresh (now including the new application) and the
   Learning Agent produces a grounded, sample-size-aware StrategyInsight.
5. Shows the mem0 memory write (mock provider — no network) and the full
   Decision Trace.

Uses MockLLMProvider by default — fully deterministic, no network access
required. All seeded/demo data is explicitly labeled DEMO DATA.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langgraph.types import Command

from src.config.settings import load_settings
from src.config.workflow import DEFAULT_JOB_BATCH_PATH
from src.graph.checkpointing import get_sqlite_checkpointer
from src.graph.workflow import build_outcome_update_workflow, build_workflow
from src.llm.provider import get_llm_client
from src.services.database import get_connection, init_schema
from src.services.application_tracker import ApplicationTrackerService
from src.services.demo_application_loader import load_demo_application_history
from src.services.memory_service import MemoryService, MockMemoryProvider
from src.services.outcome_analytics import compute_outcome_analytics

DEMO_RESUME_PATH = "data/sample_candidate/demo_resume.txt"


def _print_analytics(analytics, label: str) -> None:
    print(f"\n{label}:")
    for role, group in sorted(analytics.by_role_family.items()):
        print(
            f"  {role}: n={group.sample_size}, response_rate={group.response_rate * 100:.1f}%, "
            f"interview_rate={group.interview_rate * 100:.1f}%, offer_rate={group.offer_rate * 100:.1f}%, "
            f"confidence={group.confidence.value}"
        )


def main() -> None:
    print("=" * 70)
    print("HireLoop AI - Phase 5 developer demo (Application Tracking + Learning Loop)")
    print("=" * 70)
    print("\n*** DEMO DATA: all historical statistics below are synthetic/seeded, ***")
    print("*** clearly marked is_demo_data=true, never mixed into real analytics  ***")
    print("*** without the explicit DEMO_MODE boundary.                           ***")

    settings = load_settings()
    llm_client = get_llm_client(settings)
    print(f"\nLLM provider: {llm_client.primary.name}" + (" (mock, not a live model)" if llm_client.primary.name == "mock" else ""))

    demo_records = load_demo_application_history()
    baseline_analytics = compute_outcome_analytics(demo_records)
    _print_analytics(baseline_analytics, "Baseline demo historical performance")

    # Business DB (separate from the workflow checkpoint DB) -- in-memory
    # for this demo run so repeated runs start clean.
    db_conn = get_connection(":memory:")
    init_schema(db_conn)
    tracker = ApplicationTrackerService(db_conn)

    print("\n--- Step 1: run the full job-search + tailoring + application flow ---")
    checkpointer = get_sqlite_checkpointer(":memory:")
    app = build_workflow(checkpointer)
    run_id = f"demo5-{uuid.uuid4().hex[:8]}"
    config = {
        "configurable": {
            "thread_id": run_id,
            "llm_client": llm_client,
            "application_tracker": tracker,
            "job_batch_path": DEFAULT_JOB_BATCH_PATH,
        }
    }

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
    result = app.invoke(Command(resume={"action": "SELECT", "job_id": "job_ai_001"}), config=config)
    result = app.invoke(Command(resume={"action": "APPROVE_ALL"}), config=config)
    result = app.invoke(Command(resume={"action": "MARK_APPLIED"}), config=config)

    application_id = result["application_id"]
    print(f"Application {application_id} created and marked APPLIED (job_ai_001, AI Engineer).")

    print("\n--- Step 2: (simulating days later) record the outcome: INTERVIEW ---")
    outcome_checkpointer = get_sqlite_checkpointer(":memory:")
    outcome_app = build_outcome_update_workflow(outcome_checkpointer)
    memory_service = MemoryService(MockMemoryProvider())
    outcome_config = {
        "configurable": {
            "thread_id": f"outcome-{run_id}",
            "llm_client": llm_client,
            "application_tracker": tracker,
            "memory_service": memory_service,
            "settings": settings,
        }
    }
    outcome_app.invoke({"target_application_id": application_id, "workflow_status": "NOT_STARTED"}, config=outcome_config)
    outcome_result = outcome_app.invoke(Command(resume={"action": "INTERVIEW"}), config=outcome_config)

    refreshed_analytics_dict = outcome_result["outcome_analytics"]
    print(f"\nOutcome analytics refreshed using {refreshed_analytics_dict['total_resolved']} resolved application(s).")

    print("\n--- Step 3: Learning Agent strategy insights ---")
    insights = outcome_result.get("strategy_insights", [])
    if not insights:
        print("  (no insights generated this run)")
    for insight in insights:
        print(f"\n  [{insight['category']}] confidence={insight['confidence']}, sample_size={insight['sample_size']}")
        print(f"  Observation: {insight['observation']}")
        print(f"  Evidence: {insight['evidence']}")
        print(f"  Recommendation: {insight['recommendation']}")

    print(f"\nmem0 sync status: {outcome_result.get('mem0_sync_status')}")

    print("\n--- Decision Trace ---")
    for event in outcome_result.get("decision_trace", []):
        print(f"  -> {event['message']}")

    print("\n" + "=" * 70)
    print(f"Final application status: {tracker.get_application(application_id).current_status.value}")
    print(f"Workflow status: {outcome_result.get('workflow_status')}")
    print("=" * 70)


if __name__ == "__main__":
    main()
