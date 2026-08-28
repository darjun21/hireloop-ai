"""
HireLoop AI — API bridge engine.

This module is the HTTP-facing twin of app.py's session orchestration. It
imports and calls the SAME backend functions app.py already calls
(`build_workflow`, `build_outcome_update_workflow`, the graph's
`.invoke()` / `Command(resume=...)` pattern, `load_settings`,
`get_llm_client`, `ApplicationTrackerService`, `compute_outcome_analytics`,
`load_demo_application_history`) — it does not reimplement any scoring,
matching, verification, or analytics logic. Every function below is a
direct analogue of a function in app.py, just keyed per HTTP session
instead of per `st.session_state`.

No code under src/agents, src/graph, src/services, src/models, src/llm, or
src/config is modified by this module — it only imports and calls them.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from langgraph.types import Command

from src.config.settings import load_settings
from src.config.workflow import DEFAULT_JOB_BATCH_PATH
from src.graph.checkpointing import get_sqlite_checkpointer
from src.graph.workflow import build_outcome_update_workflow, build_workflow
from src.llm.provider import get_llm_client
from src.models.enums import WorkMode
from src.services.application_tracker import ApplicationTrackerService
from src.services.database import get_connection, init_schema
from src.services.demo_application_loader import load_demo_application_history
from src.services.outcome_analytics import compute_outcome_analytics

DEMO_RESUME_PATH = "data/sample_candidate/demo_resume.txt"
DEFAULT_TARGET_ROLES = ["AI Engineer"]
DEFAULT_WORK_MODES = [WorkMode.REMOTE.value]

STAGES = ["DISCOVER", "SCORE", "TAILOR", "VERIFY", "APPLY", "TRACK", "LEARN", "IMPROVE"]


@dataclass
class Session:
    """Direct analogue of the set of st.session_state keys app.py's
    _init_session() sets up — one instance per browser/API session
    instead of one per Streamlit script run."""

    session_id: str
    settings: Any
    llm_client: Any
    tracker: ApplicationTrackerService
    checkpointer: Any
    graph: Any
    outcome_checkpointer: Any
    outcome_graph: Any
    thread_id: str | None = None
    state: dict = field(default_factory=dict)
    interrupt: dict | None = None
    outcome_thread_id: str | None = None
    outcome_active_application: str | None = None
    outcome_state: dict = field(default_factory=dict)
    outcome_interrupt: dict | None = None
    last_run_params: dict | None = None
    job_source_override: Any = None
    # PERSONAL (default) or CERTIFICATION_DEMO. Set to CERTIFICATION_DEMO
    # only by load_certification_demo() below. Gates whether synthetic
    # demo history (data/sample_jobs.json-derived applications via
    # demo_application_loader) is ever mixed into this session's
    # analytics — see outcome_analytics_for(). A PERSONAL session must
    # never see synthetic data regardless of the global
    # settings.demo_mode flag.
    mode: str = "PERSONAL"


_SESSIONS: dict[str, Session] = {}


def create_session() -> Session:
    """Direct analogue of app.py's _init_session()."""
    settings = load_settings()
    llm_client = get_llm_client(settings)

    db_conn = get_connection(":memory:")
    init_schema(db_conn)
    tracker = ApplicationTrackerService(db_conn)

    session_id = uuid.uuid4().hex[:16]
    checkpointer = get_sqlite_checkpointer(":memory:")
    outcome_checkpointer = get_sqlite_checkpointer(":memory:")
    sess = Session(
        session_id=session_id,
        settings=settings,
        llm_client=llm_client,
        tracker=tracker,
        checkpointer=checkpointer,
        graph=build_workflow(checkpointer),
        outcome_checkpointer=outcome_checkpointer,
        outcome_graph=build_outcome_update_workflow(outcome_checkpointer),
    )
    _SESSIONS[session_id] = sess
    return sess


def get_session(session_id: str) -> Session:
    sess = _SESSIONS.get(session_id)
    if sess is None:
        raise KeyError(f"unknown session_id: {session_id}")
    return sess


def _graph_config(sess: Session) -> dict:
    """Direct analogue of app.py's _graph_config()."""
    configurable = {
        "thread_id": sess.thread_id,
        "llm_client": sess.llm_client,
        "application_tracker": sess.tracker,
        "job_batch_path": DEFAULT_JOB_BATCH_PATH,
    }
    if sess.job_source_override:
        configurable["job_source_override"] = sess.job_source_override
    return {"configurable": configurable}


def _apply_result(sess: Session, result: dict) -> None:
    """Direct analogue of app.py's _apply_result()."""
    sess.state = result
    sess.interrupt = result["__interrupt__"][0].value if "__interrupt__" in result else None


def start_new_run(sess: Session, resume_file_path: str, target_roles: list[str], work_modes: list[str]) -> None:
    """Direct analogue of app.py's start_new_run()."""
    thread_id = f"api-{uuid.uuid4().hex[:10]}"
    sess.thread_id = thread_id
    initial_state = {
        "run_id": thread_id,
        "candidate_id": f"cand-{thread_id}",
        "resume_file_path": resume_file_path,
        "preferences": {"target_roles": target_roles, "preferred_work_modes": work_modes},
        "workflow_status": "NOT_STARTED",
    }
    result = sess.graph.invoke(initial_state, config=_graph_config(sess))
    _apply_result(sess, result)


def resume_graph(sess: Session, response: dict) -> None:
    """Direct analogue of app.py's resume_graph()."""
    result = sess.graph.invoke(Command(resume=response), config=_graph_config(sess))
    _apply_result(sess, result)


def load_certification_demo(sess: Session) -> None:
    """Direct analogue of app.py's _load_certification_demo(). Calls the
    real start_new_run(); the graph's own interrupt() naturally stops the
    run at the first human decision (job selection) — this cannot skip or
    auto-resolve that decision."""
    sess.last_run_params = {
        "resume_path": DEMO_RESUME_PATH,
        "roles": DEFAULT_TARGET_ROLES,
        "work_mode": DEFAULT_WORK_MODES,
    }
    sess.job_source_override = None
    sess.mode = "CERTIFICATION_DEMO"
    start_new_run(sess, DEMO_RESUME_PATH, DEFAULT_TARGET_ROLES, DEFAULT_WORK_MODES)


def start_outcome_update(sess: Session, application_id: str) -> None:
    """Direct analogue of app.py's _outcome_recorder() 'Start outcome
    update' button handler."""
    thread_id = f"outcome-api-{uuid.uuid4().hex[:10]}"
    sess.outcome_thread_id = thread_id
    sess.outcome_active_application = application_id
    config = {
        "configurable": {
            "thread_id": thread_id,
            "llm_client": sess.llm_client,
            "application_tracker": sess.tracker,
            "memory_service": None,
            "settings": sess.settings,
        }
    }
    result = sess.outcome_graph.invoke({"target_application_id": application_id, "workflow_status": "NOT_STARTED"}, config=config)
    sess.outcome_state = result
    sess.outcome_interrupt = result["__interrupt__"][0].value if "__interrupt__" in result else None


def submit_outcome(sess: Session, action: str, confirm: bool = False) -> None:
    """Direct analogue of app.py's 'Submit outcome' button handler."""
    config = {
        "configurable": {
            "thread_id": sess.outcome_thread_id,
            "llm_client": sess.llm_client,
            "application_tracker": sess.tracker,
            "memory_service": None,
            "settings": sess.settings,
        }
    }
    response: dict[str, Any] = {"action": action}
    if confirm:
        response["confirm"] = True
    result = sess.outcome_graph.invoke(Command(resume=response), config=config)
    sess.outcome_state = result
    sess.outcome_interrupt = result["__interrupt__"][0].value if "__interrupt__" in result else None


# ---------------------------------------------------------------------------
# Stage status derivation — identical logic to app.py's _stage_status_map,
# duplicated here (not imported) only because app.py itself is frozen and
# not an importable "library" module; the derivation rules are copied
# verbatim from the certified app.py, not reinvented.
# ---------------------------------------------------------------------------


def human_decision_stage(interrupt: dict | None) -> str | None:
    if not interrupt:
        return None
    if "eligible_selections" in interrupt:
        return "SCORE"
    if "clarification_required" in interrupt or "modifications" in interrupt:
        return "VERIFY"
    if "application" in interrupt:
        return "TRACK"
    return None


def stage_status_map(sess: Session) -> dict[str, str]:
    s = sess.state or {}
    interrupt = sess.interrupt
    counts = s.get("counts", {}) or {}
    completed = {
        "DISCOVER": bool(counts.get("ingested")),
        "SCORE": bool(s.get("opportunity_scores")),
        "TAILOR": bool(s.get("proposed_modifications")),
        "VERIFY": bool(s.get("truth_guard_results")),
        "APPLY": bool(s.get("current_resume_version_id")),
        "TRACK": bool(sess.tracker.list_applications()),
        "LEARN": bool(sess.tracker.list_strategy_insights()),
        "IMPROVE": False,
    }
    statuses: dict[str, str] = {}
    found_active = False
    for stage in STAGES:
        if completed[stage]:
            statuses[stage] = "done"
        elif not found_active:
            statuses[stage] = "active"
            found_active = True
        else:
            statuses[stage] = "waiting"

    human_stage = human_decision_stage(interrupt)
    if human_stage:
        statuses[human_stage] = "human"
    return statuses


def outcome_analytics_for(sess: Session) -> Any:
    """Direct analogue of the analytics computation used on the Dashboard
    and Strategy pages of app.py.

    Synthetic demo history is only ever mixed in for a CERTIFICATION_DEMO
    session, never a PERSONAL one -- gating on sess.mode in addition to the
    global settings.demo_mode flag is required for real/demo isolation:
    settings.demo_mode is process-wide, so without this per-session check a
    PERSONAL session running alongside demo_mode=True would otherwise
    inherit synthetic applications. See
    tests/test_career_profile_isolation.py."""
    demo_records = (
        load_demo_application_history() if sess.settings.demo_mode and sess.mode == "CERTIFICATION_DEMO" else []
    )
    live_records = sess.tracker.get_applications_with_history(include_demo_data=False)
    return compute_outcome_analytics(demo_records + live_records)
