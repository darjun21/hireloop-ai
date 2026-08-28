"""
HireLoop AI — thin HTTP API bridge for the Next.js showcase frontend.

Every endpoint below either (a) reads state already computed by the real
LangGraph workflow (api/engine.py, which itself only calls
src/graph/workflow.py, src/services/*, src/config/*, src/llm/*) or (b)
resumes that same workflow via Command(resume=...) — exactly what app.py's
Streamlit buttons already do. No business logic (scoring, matching,
verification, analytics) is implemented in this file or anywhere under
api/ — see api/engine.py's module docstring.

Run with:  uvicorn api.main:app --reload --port 8000
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from api import engine, serializers

app = FastAPI(title="HireLoop AI API Bridge")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _sess(session_id: str) -> engine.Session:
    try:
        return engine.get_session(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Unknown session_id. POST /api/session first.")


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------


@app.post("/api/session")
def create_session():
    sess = engine.create_session()
    return {"session_id": sess.session_id}


@app.get("/api/session/{session_id}")
def read_session(session_id: str):
    sess = _sess(session_id)
    return {"session_id": sess.session_id, "demo_mode": sess.settings.demo_mode}


# ---------------------------------------------------------------------------
# Demo run
# ---------------------------------------------------------------------------


@app.post("/api/session/{session_id}/demo/start")
def demo_start(session_id: str):
    """Direct HTTP twin of app.py's 'Load Certification Demo' button.
    Autonomously advances only until the first real human interrupt (job
    selection), then stops — same rule as the Streamlit version. This
    endpoint is only ever reached by an explicit user-initiated request
    (the "START CERTIFICATION DEMO" button in the Next.js UI); it never
    fires on page load."""
    sess = _sess(session_id)
    engine.load_certification_demo(sess)
    return serializers.mission_control_view(sess)


class RunRequest(BaseModel):
    resume_path: str | None = None
    target_roles: list[str] = ["AI Engineer"]
    work_modes: list[str] = ["Remote"]


@app.post("/api/session/{session_id}/run")
def start_run(session_id: str, body: RunRequest):
    sess = _sess(session_id)
    resume_path = body.resume_path or engine.DEMO_RESUME_PATH
    sess.last_run_params = {"resume_path": resume_path, "roles": body.target_roles, "work_mode": body.work_modes}
    sess.job_source_override = None
    engine.start_new_run(sess, resume_path, body.target_roles, body.work_modes)
    return serializers.mission_control_view(sess)


class ResumeRequest(BaseModel):
    action: str
    job_id: str | None = None
    modification_ids: list[str] | None = None
    confirmation_detail: str | None = None


@app.post("/api/session/{session_id}/resume")
def resume(session_id: str, body: ResumeRequest):
    """Direct HTTP twin of app.py's resume_graph() call sites (SELECT,
    APPROVE_ALL/APPROVE_SELECTED/REJECT_ALL, CONFIRM_WITH_EVIDENCE/
    USE_SAFE_REWRITE/REJECT_CLAIM, MARK_APPLIED/SAVE_FOR_LATER, CANCEL).
    Only ever called by an explicit button click in the Next.js UI."""
    sess = _sess(session_id)
    response: dict = {"action": body.action}
    if body.job_id is not None:
        response["job_id"] = body.job_id
    if body.modification_ids is not None:
        response["modification_ids"] = body.modification_ids
    if body.confirmation_detail is not None:
        response["confirmation_detail"] = body.confirmation_detail
    engine.resume_graph(sess, response)
    return serializers.mission_control_view(sess)


# ---------------------------------------------------------------------------
# View models (read-only)
# ---------------------------------------------------------------------------


@app.get("/api/session/{session_id}/mission-control")
def mission_control(session_id: str):
    return serializers.mission_control_view(_sess(session_id))


@app.get("/api/session/{session_id}/opportunities")
def opportunities(session_id: str):
    return serializers.opportunities_view(_sess(session_id))


@app.get("/api/session/{session_id}/opportunities/{job_id}")
def opportunity_detail(session_id: str, job_id: str):
    view = serializers.opportunity_detail_view(_sess(session_id), job_id)
    if view is None:
        raise HTTPException(status_code=404, detail="Unknown job_id, or it has not been scored in this session yet.")
    return view


@app.get("/api/session/{session_id}/resume-studio")
def resume_studio(session_id: str):
    return serializers.resume_studio_view(_sess(session_id))


@app.get("/api/session/{session_id}/applications")
def applications(session_id: str):
    return serializers.applications_view(_sess(session_id))


@app.get("/api/session/{session_id}/strategy")
def strategy(session_id: str):
    return serializers.strategy_view(_sess(session_id))


@app.get("/api/session/{session_id}/system")
def system(session_id: str):
    return serializers.system_view(_sess(session_id))


# ---------------------------------------------------------------------------
# Outcome-update sub-workflow (Applications page "Record outcome")
# ---------------------------------------------------------------------------


@app.post("/api/session/{session_id}/applications/{application_id}/outcome/start")
def outcome_start(session_id: str, application_id: str):
    sess = _sess(session_id)
    engine.start_outcome_update(sess, application_id)
    return {"interrupt": serializers._jsonable(sess.outcome_interrupt), "state": serializers._jsonable(sess.outcome_state.get("strategy_insights"))}


class OutcomeSubmitRequest(BaseModel):
    action: str
    confirm: bool = False


@app.post("/api/session/{session_id}/applications/{application_id}/outcome/submit")
def outcome_submit(session_id: str, application_id: str, body: OutcomeSubmitRequest):
    sess = _sess(session_id)
    engine.submit_outcome(sess, body.action, body.confirm)
    return {"interrupt": serializers._jsonable(sess.outcome_interrupt), "state": serializers._jsonable(sess.outcome_state.get("strategy_insights"))}


@app.get("/api/health")
def health():
    return {"status": "ok"}
