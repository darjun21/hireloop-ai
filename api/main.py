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

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from api import engine, serializers
from api.career_profile_routes import Store, router as career_profile_router
from api.validation import InvalidWorkModeError, normalize_work_modes
from src.services.career_profile_completeness import CompletenessStatus, compute_completeness

app = FastAPI(title="HireLoop AI API Bridge")

# Real-user bug fix: the Next.js dev server falls back to port 3001 when
# 3000 is already busy (a very common local-dev situation), and browsers
# treat http://localhost and http://127.0.0.1 as distinct origins even
# when they resolve to the same machine. All four are the same frontend
# app in practice, so all four must be explicitly listed here -- with
# allow_credentials=True, FastAPI/Starlette will not echo back an
# Access-Control-Allow-Origin header for "*" (browsers reject that
# combination outright), so a real origin list is required, not a
# wildcard.
allow_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

# Career Profile feature — a self-contained router (see
# api/career_profile_routes.py's docstring). Mounting it here does not
# change any existing route above or below.
app.include_router(career_profile_router)


# Safety net (not a replacement for the explicit normalize_* validation
# in api/validation.py, which stays the primary path): a route handler
# that constructs a pydantic domain model directly from request data
# (e.g. CareerEmploymentPreferences(**data) in
# api/career_profile_routes.py) can still raise an uncaught
# pydantic.ValidationError if some other field is malformed in a way not
# yet covered by explicit normalization. Uncaught, that exception
# bypasses CORSMiddleware entirely (it propagates up to Starlette's
# ServerErrorMiddleware, which sits OUTSIDE user middleware) and comes
# back to the browser as a raw 500 with no Access-Control-Allow-Origin
# header at all -- which a browser reports as a CORS failure, masking
# the real cause. Registering this handler here means FastAPI's
# ExceptionMiddleware (which sits INSIDE CORSMiddleware) catches it
# first and returns a normal, CORS-header-carrying 422 response instead.
@app.exception_handler(PydanticValidationError)
async def _pydantic_validation_exception_handler(request: Request, exc: PydanticValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})


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
    return {"session_id": sess.session_id, "demo_mode": sess.settings.demo_mode, "mode": sess.mode}


@app.get("/api/session/{session_id}/mode")
def session_mode(session_id: str):
    """PERSONAL or CERTIFICATION_DEMO — see Session.mode's docstring in
    api/engine.py. Drives the mode-switcher badge in the frontend."""
    sess = _sess(session_id)
    return {"mode": sess.mode}


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
    # NEW, optional: the Career Profile owner_id this run is for. The
    # Next.js frontend already fetches the caller's Career Profile before
    # ever reaching /candidate-setup (see web/lib/career-profile-api.ts's
    # getOwnerId() + web/app/candidate-setup/page.tsx) -- this just wires
    # that same id through onto the /run call so this endpoint can enforce
    # the confirmation gate below. Left optional (not required) so every
    # EXISTING test/caller that never supplied one keeps working exactly
    # as before -- the gate below only activates when an owner_id is
    # actually present on the request, which is also correct behavior:
    # there is no Career Profile confirmation concept without an owner_id
    # to check it against.
    owner_id: str | None = None


@app.post("/api/session/{session_id}/run")
def start_run(session_id: str, body: RunRequest, store: Store):
    sess = _sess(session_id)
    try:
        work_modes = normalize_work_modes(body.work_modes)
    except InvalidWorkModeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Confirmation enforcement gate (real enforcement, not just a UI
    # indicator): a real Personal Mode discovery run for a given Career
    # Profile owner may only proceed once that profile has been
    # EXPLICITLY confirmed (POST /api/career-profile/{owner_id}/confirm)
    # AND that confirmation hasn't since gone stale. `confirmed_at` is the
    # single source of truth for both: it is only ever set by the explicit
    # confirm action, and is cleared the instant any MATERIAL field
    # changes afterward (see api/career_profile_routes.py's
    # _invalidate_if_materially_changed and apply_resume_update) -- so
    # "confirmed_at is not None" already means "confirmed AND still
    # fresh". The completeness re-check below is defense-in-depth only
    # (catches any path that could otherwise leave confirmed_at set on an
    # incomplete profile), not the primary mechanism.
    #
    # This check lives HERE, in the HTTP /run handler, and nowhere inside
    # engine.start_new_run() -- so engine.load_certification_demo() (which
    # calls engine.start_new_run() directly, bypassing this HTTP endpoint
    # entirely) never touches Career Profile confirmation at all. See
    # engine.load_certification_demo()'s docstring and Session.mode.
    if body.owner_id:
        profile = store.get_by_owner(body.owner_id)
        if profile is None or profile.confirmed_at is None:
            raise HTTPException(
                status_code=403,
                detail="Review and confirm your Career Profile before searching for opportunities.",
            )
        completeness = compute_completeness(profile)
        incomplete = [
            c.category
            for c in completeness.categories
            if not c.category.endswith("_OPTIONAL") and c.status != CompletenessStatus.COMPLETE
        ]
        if incomplete:
            raise HTTPException(
                status_code=403,
                detail=(
                    "Your Career Profile confirmation is no longer valid because "
                    f"{', '.join(incomplete)} still need review. Re-confirm your profile "
                    "before searching for opportunities."
                ),
            )

    # Real-user bug fix: this endpoint used to silently fall back to
    # engine.DEMO_RESUME_PATH (the synthetic certification demo resume)
    # whenever the caller didn't supply resume_path -- which the Next.js
    # frontend never did, so every Personal Mode "Run Discovery" click was
    # silently scoring/tailoring/verifying against the demo candidate's
    # resume, not the real user's. DEMO_RESUME_PATH must only ever be
    # reached via engine.load_certification_demo()'s own direct call to
    # engine.start_new_run() (which bypasses this HTTP endpoint entirely
    # and passes DEMO_RESUME_PATH itself) -- never as a silent default
    # here. A direct /run call with no resume on file is now a controlled
    # 422, not a silent substitution.
    if not body.resume_path:
        raise HTTPException(
            status_code=422,
            detail="No resume on file. Upload a resume to your Career Profile before running discovery.",
        )
    resume_path = body.resume_path
    sess.last_run_params = {"resume_path": resume_path, "roles": body.target_roles, "work_mode": work_modes}
    sess.job_source_override = None
    # A real /run call is always Personal Mode, even if this session
    # previously ran the certification demo — see Session.mode's docstring
    # in api/engine.py.
    sess.mode = "PERSONAL"
    engine.start_new_run(sess, resume_path, body.target_roles, work_modes)
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
