"""
Phase 4 graph-level tests: correction loop, human clarification, human
resume approval, resume versioning, and the absolute safety invariants.
No real network calls -- MockLLMProvider and FixedTailorProvider only.
"""

from __future__ import annotations

import hashlib
import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from src.llm.client import LLMClient
from src.llm.schemas import ProposedModificationLLM
from tests.graph_helpers import FixedTailorProvider, build_app, initial_state, make_config
from tests.resume_fixtures import AWS_SKILLS_ONLY


def _memory_checkpointer() -> SqliteSaver:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    saver = SqliteSaver(conn)
    saver.setup()
    return saver


def _select_job_ai_001(app, config: dict) -> dict:
    """Runs the graph to the resume-approval-or-earlier interrupt with
    job_ai_001 selected. job_ai_001 requests Kubernetes as a preferred
    skill the demo candidate does not have -- a reliable adversarial case."""
    app.invoke(initial_state(config["configurable"]["thread_id"]), config=config)
    return app.invoke(Command(resume={"action": "SELECT", "job_id": "job_ai_001"}), config=config)


# 19 & 20. Correction loop runs, and stops after MAX_RESUME_REVISION_LOOPS.
def test_correction_loop_runs_and_stops_after_max_passes():
    app = build_app(_memory_checkpointer())
    config = make_config("p4-correction")

    result = _select_job_ai_001(app, config)

    correction_events = [e for e in result["decision_trace"] if e["action"] == "correct_modifications"]
    assert len(correction_events) == 2  # MAX_RESUME_REVISION_LOOPS
    assert "1/2" in correction_events[0]["message"]
    assert "2/2" in correction_events[1]["message"]


# 22. Unsafe unresolved modification removed after max loops.
def test_unresolved_unsupported_modification_is_stripped_after_max_loops():
    app = build_app(_memory_checkpointer())
    config = make_config("p4-strip")

    result = _select_job_ai_001(app, config)

    rejected_ids = [r["modification_id"] for r in result["rejected_modifications"]]
    assert rejected_ids  # the Kubernetes modification was stripped
    proposed_ids = {m["modification_id"] for m in result["proposed_modifications"]}
    assert not (set(rejected_ids) & proposed_ids)  # never present in both


def test_no_unsupported_modification_is_ever_offered_for_approval():
    app = build_app(_memory_checkpointer())
    config = make_config("p4-safety")

    result = _select_job_ai_001(app, config)

    assert "__interrupt__" in result
    payload = result["__interrupt__"][0].value
    assert "modifications" in payload  # reached human_resume_approval
    for item in payload["modifications"]:
        assert item["truth_status"] == "VERIFIED"


# --- Human clarification interrupt (all four actions) ---


def _aws_needs_confirmation_config(thread_id: str) -> dict:
    modifications = [
        ProposedModificationLLM(
            section="Professional Summary",
            proposed_text="Architected large-scale AWS infrastructure.",
            reason="Job requires AWS.",
            targeted_job_requirement="AWS",
            claim="Architected large-scale AWS infrastructure.",
        )
    ]
    llm_client = LLMClient(primary=FixedTailorProvider(modifications))
    return make_config(thread_id, llm_client=llm_client)


def _run_to_clarification(app, config: dict, tmp_path, thread_id: str) -> dict:
    from tests.graph_helpers import write_resume_file

    resume_path = write_resume_file(tmp_path / "resume.txt", AWS_SKILLS_ONLY)
    result = app.invoke(initial_state(thread_id, resume_file_path=resume_path), config=config)
    top_job = result["__interrupt__"][0].value["eligible_selections"][0]["job_id"]
    result = app.invoke(Command(resume={"action": "SELECT", "job_id": top_job}), config=config)
    assert "clarification_required" in result["__interrupt__"][0].value
    return result


def test_human_clarification_reject_claim(tmp_path):
    app = build_app(_memory_checkpointer())
    config = _aws_needs_confirmation_config("p4-clarify-reject")
    _run_to_clarification(app, config, tmp_path, "p4-clarify-reject")

    result = app.invoke(Command(resume={"action": "REJECT_CLAIM"}), config=config)

    assert not any(m["targeted_job_requirement"] == "AWS" for m in result.get("proposed_modifications", []))
    assert any("clarification" in r["reason"] for r in result.get("rejected_modifications", []))


def test_human_clarification_use_safe_rewrite_with_no_safe_option_reprompts_not_silently_approves(tmp_path):
    app = build_app(_memory_checkpointer())
    config = _aws_needs_confirmation_config("p4-clarify-saferewrite")
    interrupted = _run_to_clarification(app, config, tmp_path, "p4-clarify-saferewrite")
    assert interrupted["__interrupt__"][0].value["clarification_required"]["safe_option"] is None

    result = app.invoke(Command(resume={"action": "USE_SAFE_REWRITE"}), config=config)

    # No original_text and no verified fragments in the AWS-only claim, so
    # there was nothing safe to fall back to -- Truth Guard re-classifies
    # the unchanged claim, it's still NEEDS_HUMAN_CONFIRMATION, and the
    # graph correctly pauses again rather than silently approving it.
    assert "__interrupt__" in result
    assert result["__interrupt__"][0].value["clarification_required"]["status"] == "NEEDS_HUMAN_CONFIRMATION"


def test_human_clarification_confirm_with_evidence_creates_human_confirmation_record(tmp_path):
    app = build_app(_memory_checkpointer())
    config = _aws_needs_confirmation_config("p4-clarify-confirm")
    _run_to_clarification(app, config, tmp_path, "p4-clarify-confirm")

    result = app.invoke(
        Command(resume={"action": "CONFIRM_WITH_EVIDENCE", "confirmation_detail": "I led the AWS migration project in 2022."}),
        config=config,
    )

    human_evidence = result.get("human_provided_evidence", [])
    assert human_evidence
    assert human_evidence[0]["source_type"] == "HUMAN_CONFIRMATION"
    assert human_evidence[0]["evidence_id"].startswith("human-ev-")
    # Distinct from resume-derived evidence -- never merged into it.
    resume_evidence_ids = {e["evidence_id"] for e in result.get("candidate_evidence", []) if e["source_type"] != "HUMAN_CONFIRMATION"}
    assert human_evidence[0]["evidence_id"] not in resume_evidence_ids


def test_human_clarification_cancel(tmp_path):
    app = build_app(_memory_checkpointer())
    config = _aws_needs_confirmation_config("p4-clarify-cancel")
    _run_to_clarification(app, config, tmp_path, "p4-clarify-cancel")

    result = app.invoke(Command(resume={"action": "CANCEL"}), config=config)

    assert result["workflow_status"] == "CANCELLED"
    assert any(e["category"] == "HUMAN_CANCELLED" for e in result["errors"])


def test_human_clarification_rejects_invalid_action(tmp_path):
    app = build_app(_memory_checkpointer())
    config = _aws_needs_confirmation_config("p4-clarify-invalid")
    result = _run_to_clarification(app, config, tmp_path, "p4-clarify-invalid")

    result2 = app.invoke(Command(resume={"action": "NOT_A_REAL_ACTION"}), config=config)

    assert "__interrupt__" in result2
    assert "clarification_required" in result2["__interrupt__"][0].value


# --- Human resume approval interrupt ---


def test_human_resume_approval_approve_selected_and_invalid_id_rejected():
    app = build_app(_memory_checkpointer())
    config = make_config("p4-approve-selected")
    result = _select_job_ai_001(app, config)
    valid_id = result["__interrupt__"][0].value["modifications"][0]["modification_id"]

    invalid_attempt = app.invoke(Command(resume={"action": "APPROVE_SELECTED", "modification_ids": ["not-a-real-id"]}), config=config)
    assert "__interrupt__" in invalid_attempt  # rejected, still waiting

    after_approval = app.invoke(Command(resume={"action": "APPROVE_SELECTED", "modification_ids": [valid_id]}), config=config)
    assert after_approval["approved_modification_ids"] == [valid_id]
    # Graph continues into Phase 5 application tracking rather than ending here.
    assert "__interrupt__" in after_approval
    assert "application" in after_approval["__interrupt__"][0].value


def test_human_resume_approval_reject_all():
    app = build_app(_memory_checkpointer())
    config = make_config("p4-reject-all")
    result = _select_job_ai_001(app, config)

    final = app.invoke(Command(resume={"action": "REJECT_ALL"}), config=config)

    assert final["approved_modification_ids"] == []
    assert final["current_resume_version_id"] is not None  # version still created, just with 0 approved changes


def test_human_resume_approval_cancel():
    app = build_app(_memory_checkpointer())
    config = make_config("p4-approval-cancel")
    result = _select_job_ai_001(app, config)

    final = app.invoke(Command(resume={"action": "CANCEL"}), config=config)

    assert final["workflow_status"] == "CANCELLED"


# 29. Human EDIT goes back through Truth Guard, never auto-approved.
def test_human_edit_is_re_verified_not_auto_approved():
    app = build_app(_memory_checkpointer())
    config = make_config("p4-edit")
    result = _select_job_ai_001(app, config)
    payload = result["__interrupt__"][0].value
    valid_id = payload["modifications"][0]["modification_id"]

    # Edit a VERIFIED modification into an unsupported claim -- it must be
    # re-verified and NOT silently kept approved just because it started
    # in the offerable set.
    edited = app.invoke(
        Command(resume={"action": "EDIT", "edits": {valid_id: "Deployed Kubernetes production workloads."}}),
        config=config,
    )
    assert "__interrupt__" in edited
    new_payload = edited["__interrupt__"][0].value
    assert not any(m["modification_id"] == valid_id for m in new_payload["modifications"])  # no longer offerable


# --- Resume versioning + immutability ---


def test_original_resume_hash_unchanged_after_full_phase4_flow():
    app = build_app(_memory_checkpointer())
    config = make_config("p4-hash")

    first = app.invoke(initial_state("p4-hash"), config=config)
    original_text = first["resume_parse_result"]["extracted_text"]
    original_hash = hashlib.sha256(original_text.encode()).hexdigest()

    result = app.invoke(Command(resume={"action": "SELECT", "job_id": "job_ai_001"}), config=config)
    final = app.invoke(Command(resume={"action": "APPROVE_ALL"}), config=config)

    final_hash = hashlib.sha256(final["resume_parse_result"]["extracted_text"].encode()).hexdigest()
    assert final_hash == original_hash


def test_resume_version_only_created_after_approval_and_all_approved_are_verified():
    app = build_app(_memory_checkpointer())
    config = make_config("p4-version")

    app.invoke(initial_state("p4-version"), config=config)
    mid_flow = app.invoke(Command(resume={"action": "SELECT", "job_id": "job_ai_001"}), config=config)
    assert mid_flow.get("resume_versions", []) == []  # not created yet -- still awaiting approval

    final = app.invoke(Command(resume={"action": "APPROVE_ALL"}), config=config)

    versions = final["resume_versions"]
    assert any(v["status"] == "ORIGINAL" for v in versions)
    approved_version = next(v for v in versions if v["status"] == "APPROVED")
    assert approved_version["approved_modification_ids"] == final["approved_modification_ids"]

    tg_results = final["truth_guard_results"]
    for mod_id in approved_version["approved_modification_ids"]:
        assert tg_results[mod_id]["status"] == "VERIFIED"


def test_rejected_modifications_never_appear_in_approved_resume_version():
    app = build_app(_memory_checkpointer())
    config = make_config("p4-rejected-not-in-version")

    app.invoke(initial_state("p4-rejected-not-in-version"), config=config)
    app.invoke(Command(resume={"action": "SELECT", "job_id": "job_ai_001"}), config=config)
    final = app.invoke(Command(resume={"action": "APPROVE_ALL"}), config=config)

    rejected_ids = {r["modification_id"] for r in final["rejected_modifications"]}
    approved_version = next(v for v in final["resume_versions"] if v["status"] == "APPROVED")
    assert not (rejected_ids & set(approved_version["approved_modification_ids"]))


# 24. Checkpoint resume does not repeat previous graph stages.
def test_resume_from_clarification_does_not_repeat_tailor_resume(tmp_path):
    app = build_app(_memory_checkpointer())
    config = _aws_needs_confirmation_config("p4-no-repeat")
    result = _run_to_clarification(app, config, tmp_path, "p4-no-repeat")

    final = app.invoke(Command(resume={"action": "REJECT_CLAIM"}), config=config)

    tailor_events = [e for e in final["decision_trace"] if e["action"] == "tailor_resume"]
    assert len(tailor_events) == 1
