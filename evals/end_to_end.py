"""
Category 11: End-to-End Task Completion.

Runs one full pipeline scenario through the real LangGraph workflow(s):
resume in -> jobs scored -> human selects one -> resume tailored -> Truth
Guard verifies -> human approves -> ResumeVersion created -> Application
created -> outcome recorded -> strategy (learning) insight created.

Reports boolean flags for each milestone rather than a pass/fail count --
each flag is itself an EvalCase so the JSON report and terminal summary
show exactly which stage of the pipeline (if any) failed to complete.
"""

from __future__ import annotations

import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from src.graph.workflow import build_outcome_update_workflow
from src.llm.client import LLMClient
from src.llm.mock_provider import MockLLMProvider
from src.config.settings import Settings
from evals.common import CategorySummary, EvalCase, summarize
from tests.graph_helpers import build_app, initial_state, make_application_tracker, make_config

CATEGORY = "end_to_end"


def _memory_checkpointer() -> SqliteSaver:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    saver = SqliteSaver(conn)
    saver.setup()
    return saver


def run() -> CategorySummary:
    cases: list[EvalCase] = []
    flags: dict[str, bool] = {
        "task_completion": False,
        "human_selection_enforced": False,
        "unsupported_claim_blocked": False,
        "human_resume_approval_enforced": False,
        "application_created": False,
        "outcome_recorded": False,
        "strategy_insight_created": False,
    }

    try:
        tracker = make_application_tracker()
        app = build_app(_memory_checkpointer())
        config = make_config("eval-e2e-1", application_tracker=tracker)

        # 1. Resume in -> jobs scored -> pauses for human job selection.
        started = app.invoke(initial_state("eval-e2e-1"), config=config)
        flags["human_selection_enforced"] = (
            "__interrupt__" in started and started.get("selected_job_id") is None
            and bool(started["__interrupt__"][0].value.get("eligible_selections"))
        )

        # 2. Human selects job_ai_001 (requests Kubernetes, which the demo
        #    candidate does not have -- forces Truth Guard to actually
        #    reject/downgrade at least one claim along the way).
        after_selection = app.invoke(Command(resume={"action": "SELECT", "job_id": "job_ai_001"}), config=config)
        selection_ok = after_selection.get("selected_job_id") == "job_ai_001"

        # 3. Drive through Phase 4 (Truth Guard / correction loop / resume
        #    approval) with the most permissive valid action at each step,
        #    tracking whether an unsupported claim was ever blocked and
        #    whether human approval was actually required before a
        #    ResumeVersion was created.
        result = after_selection
        saw_resume_approval_interrupt = False
        while "__interrupt__" in result:
            payload = result["__interrupt__"][0].value
            if "clarification_required" in payload:
                response = {"action": "USE_SAFE_REWRITE"}
            elif "modifications" in payload:
                saw_resume_approval_interrupt = True
                response = {"action": "APPROVE_ALL"}
            elif "application" in payload and "allowed_actions" in payload:
                response = {"action": "MARK_APPLIED"}
            else:
                break
            result = app.invoke(Command(resume=response), config=config)

        flags["human_resume_approval_enforced"] = saw_resume_approval_interrupt

        rejected_ids = {r["modification_id"] for r in result.get("rejected_modifications", [])}
        approved_version = next((v for v in result.get("resume_versions", []) if v["status"] == "APPROVED"), None)
        tg_results = result.get("truth_guard_results", {})
        no_unsupported_in_approved = approved_version is not None and all(
            tg_results.get(mod_id, {}).get("status") == "VERIFIED" for mod_id in approved_version["approved_modification_ids"]
        )
        flags["unsupported_claim_blocked"] = bool(rejected_ids) and no_unsupported_in_approved

        application_id = result.get("application_id")
        flags["application_created"] = bool(application_id) and tracker.get_application(application_id) is not None

        task_completed = result.get("workflow_status") == "COMPLETED"

        # 4. Separate outcome-update workflow: record an INTERVIEW outcome
        #    for the just-created application, then confirm analytics and a
        #    Learning Agent strategy insight were actually produced.
        outcome_recorded = False
        strategy_insight_created = False
        if application_id:
            outcome_app = build_outcome_update_workflow(_memory_checkpointer())
            outcome_config = {
                "configurable": {
                    "thread_id": "eval-e2e-1-outcome",
                    "llm_client": LLMClient(primary=MockLLMProvider()),
                    "application_tracker": tracker,
                    "settings": Settings(default_llm_provider="mock", demo_mode=True),
                }
            }
            interrupted = outcome_app.invoke(
                {"target_application_id": application_id, "workflow_status": "NOT_STARTED"}, config=outcome_config
            )
            if "__interrupt__" in interrupted:
                final_outcome = outcome_app.invoke(Command(resume={"action": "INTERVIEW"}), config=outcome_config)
                outcome_recorded = (
                    final_outcome.get("workflow_status") == "COMPLETED"
                    and tracker.get_application(application_id).current_status.value == "INTERVIEW"
                )
                messages = [e["message"] for e in final_outcome.get("decision_trace", [])]
                strategy_insight_created = any("Learning Agent generated" in m for m in messages) or bool(
                    final_outcome.get("strategy_insights")
                )

        flags["outcome_recorded"] = outcome_recorded
        flags["strategy_insight_created"] = strategy_insight_created
        flags["task_completion"] = task_completed and all(
            flags[k] for k in ("human_selection_enforced", "application_created", "outcome_recorded")
        )
    except Exception as exc:  # noqa: BLE001 - a crash anywhere in the pipeline is itself a finding
        cases.append(
            EvalCase(
                "e2e:pipeline_ran_without_crashing",
                CATEGORY,
                False,
                detail=f"unhandled exception during end-to-end run: {exc!r}",
                severity="critical",
            )
        )

    for flag_name, flag_value in flags.items():
        cases.append(EvalCase(f"e2e:{flag_name}", CATEGORY, flag_value, detail=f"{flag_name}={flag_value}"))

    severe_failure = not flags["human_selection_enforced"] or not flags["unsupported_claim_blocked"] or not flags["human_resume_approval_enforced"]

    return summarize(
        CATEGORY, cases, counters={k: int(v) for k, v in flags.items()}, severe_failure=severe_failure,
        severe_failure_reason="a core safety milestone (human selection, unsupported-claim blocking, or human resume approval) did not complete" if severe_failure else "",
    )


if __name__ == "__main__":
    result = run()
    print(result.to_dict())
