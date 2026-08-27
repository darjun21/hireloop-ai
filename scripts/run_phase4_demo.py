"""
Phase 4 developer demo: drives the real LangGraph workflow end to end
through resume tailoring, Truth Guard verification, and human approval —
including one deliberately adversarial modification to prove Truth Guard
catches it.

    python -m scripts.run_phase4_demo

Scenario:
    Candidate has: Python, Machine Learning, LangChain, RAG (all with
    work-experience/project evidence).
    Candidate does NOT have: Kubernetes.
    Selected job (job_ai_001) requires: Python, Machine Learning, LangChain
    (preferred: Kubernetes).

Expected outcome:
    - Modifications proposing Python/Machine Learning/LangChain usage are
      VERIFIED.
    - The modification proposing Kubernetes usage is UNSUPPORTED, survives
      2 correction passes unchanged (no safe rewrite possible — there is
      no original text and no verified fragment to fall back to), and is
      stripped before the human ever sees it as an approval candidate.
    - The human approves the remaining verified modifications.
    - A new ResumeVersion is created; the original parsed resume text is
      byte-for-byte unchanged.

Uses MockLLMProvider by default (no API keys needed) and no Pinecone
configuration, so evidence retrieval uses the local fallback — this run is
fully deterministic and requires no network access.

This is a development smoke test, not the final Streamlit UI. All
input()/print() calls live here — none in graph nodes.
"""

from __future__ import annotations

import hashlib
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langgraph.types import Command

from src.config.settings import load_settings
from src.config.workflow import DEFAULT_JOB_BATCH_PATH
from src.graph.checkpointing import get_sqlite_checkpointer
from src.graph.workflow import build_workflow
from src.llm.provider import get_llm_client
from src.services.application_tracker import ApplicationTrackerService
from src.services.database import get_connection, init_schema

DEMO_RESUME_PATH = "data/sample_candidate/phase4_demo_resume.txt"
DEMO_JOB_ID = "job_ai_001"  # requires Python, Machine Learning, LangChain; preferred Kubernetes


def main() -> None:
    print("=" * 70)
    print("HireLoop AI - Phase 4 developer demo (Resume Tailor + Truth Guard)")
    print("=" * 70)

    settings = load_settings()
    llm_client = get_llm_client(settings)
    print(f"\nLLM provider: {llm_client.primary.name}" + (" (mock, not a live model)" if llm_client.primary.name == "mock" else ""))
    print("Vector index: none configured -> evidence retrieval uses the deterministic local fallback.")

    checkpointer = get_sqlite_checkpointer(":memory:")  # demo run, not persisted across processes
    app = build_workflow(checkpointer)

    # The graph continues into Phase 5 application tracking after resume
    # approval (see scripts/run_phase5_demo.py for that part of the demo);
    # this script only needs a tracker so the graph can run structurally,
    # and stops as soon as Phase 4's own concerns (tailoring/approval) are
    # resolved.
    business_db = get_connection(":memory:")
    init_schema(business_db)
    application_tracker = ApplicationTrackerService(business_db)

    run_id = f"demo4-{uuid.uuid4().hex[:8]}"
    config = {
        "configurable": {
            "thread_id": run_id,
            "llm_client": llm_client,
            "job_batch_path": DEFAULT_JOB_BATCH_PATH,
            "application_tracker": application_tracker,
        }
    }

    print(f"\nLoading resume: {DEMO_RESUME_PATH}")
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
    original_resume_text = result["resume_parse_result"]["extracted_text"]
    original_hash = hashlib.sha256(original_resume_text.encode()).hexdigest()

    if result.get("workflow_status") == "FAILED":
        print("Workflow failed:", result.get("errors"))
        return

    print(f"Selecting job: {DEMO_JOB_ID}")
    result = app.invoke(Command(resume={"action": "SELECT", "job_id": DEMO_JOB_ID}), config=config)

    # Drive through any clarification interrupts with the safe default
    # (use the safe rewrite when offered, otherwise reject the claim) --
    # this demo scenario is constructed so none should occur, but stay
    # robust if the mock's proposal set ever changes.
    while "__interrupt__" in result and "clarification_required" in result["__interrupt__"][0].value:
        payload = result["__interrupt__"][0].value["clarification_required"]
        action = "USE_SAFE_REWRITE" if payload.get("safe_option") else "REJECT_CLAIM"
        result = app.invoke(Command(resume={"action": action}), config=config)

    if "__interrupt__" not in result:
        print("Workflow ended before reaching resume approval:", result.get("workflow_status"))
        return

    payload = result["__interrupt__"][0].value
    print("\nProposed modifications and Truth Guard verdicts:")
    tg_results = result["truth_guard_results"]
    for mod in result["proposed_modifications"]:
        status = tg_results.get(mod["modification_id"], {}).get("status", "?")
        print(f"  [{status}] {mod['proposed_text']}")
    for rejected in result.get("rejected_modifications", []):
        print(f"  [REMOVED] {rejected['modification_id']}: {rejected['reason']}")

    print("\nApproval offered for (VERIFIED only):")
    for item in payload["modifications"]:
        print(f"  - {item['proposed']}")

    print("\nApproving all verified modifications...")
    final = app.invoke(Command(resume={"action": "APPROVE_ALL"}), config=config)

    final_hash = hashlib.sha256(final["resume_parse_result"]["extracted_text"].encode()).hexdigest()
    approved_ids = final.get("approved_modification_ids", [])
    unsupported_in_approved = [
        mid for mid in approved_ids if final["truth_guard_results"].get(mid, {}).get("status") != "VERIFIED"
    ]

    print("\n" + "=" * 70)
    print(f"Original resume hash: {original_hash[:16]}...")
    print(f"Final resume hash:    {final_hash[:16]}... ({'UNCHANGED' if final_hash == original_hash else 'CHANGED -- BUG'})")
    print(f"Approved ResumeVersion: {final.get('current_resume_version_id')}")
    print(f"Approved modifications: {len(approved_ids)}")
    print(f"Unsupported modifications in approved set: {len(unsupported_in_approved)} (must be 0)")
    print(f"Workflow status: {final.get('workflow_status')}")
    print()
    print("Decision Trace:")
    for event in final.get("decision_trace", []):
        print(f"  -> {event['message']}")
    print("=" * 70)


if __name__ == "__main__":
    main()
