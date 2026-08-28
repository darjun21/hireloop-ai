"""
Lightweight frontend/backend route-contract test.

This exists specifically to catch the class of bug a real user hit: the
Next.js frontend calling a URL that doesn't match any actually-registered
FastAPI route (a stale path, a typo'd param name, a method mismatch),
which surfaces in the browser as a 404. Every path here is taken directly
from web/lib/api.ts and web/lib/career-profile-api.ts's request-building
code -- if either drifts from api/main.py or
api/career_profile_routes.py, this test fails instead of a real user
hitting a 404 in production.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import app


def _route_signatures() -> set[tuple[str, str]]:
    """Reads registered (method, path) pairs from the actual OpenAPI
    schema rather than walking app.routes directly -- FastAPI's router
    internals (e.g. how an included APIRouter's sub-routes are
    represented) are an implementation detail that has changed across
    FastAPI versions, but the served OpenAPI schema is the same contract
    the browser (and this test) both rely on."""
    with TestClient(app) as client:
        schema = client.get("/openapi.json").json()
    sigs: set[tuple[str, str]] = set()
    for path, methods in schema["paths"].items():
        for method in methods:
            if method.upper() == "HEAD":
                continue
            sigs.add((method.upper(), path))
    return sigs


# (method, path-template) exactly as built by the frontend clients.
EXPECTED_ROUTES = [
    # Session / Mission Control (web/lib/api.ts)
    ("POST", "/api/session"),
    ("GET", "/api/session/{session_id}"),
    ("GET", "/api/session/{session_id}/mode"),
    ("POST", "/api/session/{session_id}/demo/start"),
    ("POST", "/api/session/{session_id}/run"),
    ("POST", "/api/session/{session_id}/resume"),
    ("GET", "/api/session/{session_id}/mission-control"),
    ("GET", "/api/session/{session_id}/opportunities"),
    ("GET", "/api/session/{session_id}/opportunities/{job_id}"),
    ("GET", "/api/session/{session_id}/resume-studio"),
    ("GET", "/api/session/{session_id}/applications"),
    ("GET", "/api/session/{session_id}/strategy"),
    ("GET", "/api/session/{session_id}/system"),
    ("POST", "/api/session/{session_id}/applications/{application_id}/outcome/start"),
    ("POST", "/api/session/{session_id}/applications/{application_id}/outcome/submit"),
    ("GET", "/api/health"),
    # Career Profile (web/lib/career-profile-api.ts)
    ("POST", "/api/career-profile/{owner_id}"),
    ("GET", "/api/career-profile/{owner_id}"),
    ("GET", "/api/career-profile/{owner_id}/completeness"),
    ("PUT", "/api/career-profile/{owner_id}/personal-info"),
    ("PUT", "/api/career-profile/{owner_id}/work-authorization"),
    ("PUT", "/api/career-profile/{owner_id}/target-roles"),
    ("PUT", "/api/career-profile/{owner_id}/preferences"),
    ("PUT", "/api/career-profile/{owner_id}/application-answers"),
    ("PUT", "/api/career-profile/{owner_id}/demographics"),
    ("PUT", "/api/career-profile/{owner_id}/references"),
    ("POST", "/api/career-profile/{owner_id}/resume/upload"),
    ("POST", "/api/career-profile/{owner_id}/resume/apply"),
    ("POST", "/api/career-profile/{owner_id}/resume/cancel"),
]


def test_every_frontend_called_route_is_registered():
    registered = _route_signatures()
    missing = [sig for sig in EXPECTED_ROUTES if sig not in registered]
    assert not missing, f"Frontend calls a route FastAPI never registered: {missing}"


def test_openapi_schema_is_reachable():
    with TestClient(app) as client:
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        paths = resp.json()["paths"]
        for method, path in EXPECTED_ROUTES:
            assert path in paths, f"{path} missing from OpenAPI schema"
            assert method.lower() in paths[path], f"{method} {path} missing from OpenAPI schema"


# ---------------------------------------------------------------------------
# Priority 2 (owner_id vs session_id contract audit)
#
# The Career Profile identity (owner_id, durable, SQLite-backed) and the
# workflow/Mission-Control identity (session_id, disposable, in-memory)
# must never be swapped -- career-profile-api.ts builds every URL from an
# owner_id, api.ts builds every URL from a session_id. This is a purely
# mechanical, static check on the frontend source itself: it would catch
# an accidental copy-paste swap (e.g. someone wiring a career-profile
# call with a `sid` variable, or a workflow call with an `ownerId`
# variable) even though there is no JS test runner configured in this
# repo to unit-test the TypeScript directly.
# ---------------------------------------------------------------------------

import re
from pathlib import Path

_WEB_LIB = Path(__file__).resolve().parent.parent / "web" / "lib"

# Matches a template-literal URL segment built from an owner/profile
# variable, e.g. `/api/career-profile/${ownerId}`.
_OWNER_URL_VAR = re.compile(r"\$\{\s*(ownerId|owner_id)\s*\}")


def _read(name: str) -> str:
    path = _WEB_LIB / name
    assert path.exists(), f"expected {path} to exist"
    return path.read_text(encoding="utf-8")


def test_career_profile_client_never_builds_a_session_scoped_url():
    """Every function inside the `careerProfileApi` object (career-profile-
    api.ts) must only ever address /api/career-profile/{owner_id}/... --
    never construct a URL against /api/session/{session_id}/... (which
    would silently address the wrong, workflow-scoped, in-memory-only
    backend resource). fetchSessionMode() is a separate, correctly-named
    top-level function that legitimately reads workflow session state
    (GET /api/session/{sessionId}/mode) and is excluded by construction --
    it is declared outside the `careerProfileApi` object literal."""
    src = _read("career-profile-api.ts")
    obj_start = src.index("export const careerProfileApi = {")
    obj_end = src.index("\n};", obj_start)
    careerprofile_obj_body = src[obj_start:obj_end]

    assert "/api/session/" not in careerprofile_obj_body, (
        "careerProfileApi.* builds a /api/session/ URL -- owner_id/session_id contract violation"
    )
    assert "/api/career-profile" in careerprofile_obj_body, "sanity check: expected route prefix not found"

    # fetchSessionMode is the one intentional exception -- confirm it is
    # declared outside the careerProfileApi object and still targets the
    # session-mode endpoint (not silently repurposed for owner_id calls).
    # It now goes through lib/api.ts's shared sessionReq() (the same
    # stale-session recovery every other workflow-session-scoped call
    # uses) rather than a bare apiRequest -- see its own regression test,
    # test_fetch_session_mode_goes_through_shared_session_recovery below.
    # The exact callback parameter name (`sid` vs `sessionId`) is an
    # implementation detail, not part of the contract -- assert on the
    # route pattern instead of one brittle literal.
    tail = src[obj_end:]
    assert "export async function fetchSessionMode" in tail
    assert "sessionReq" in tail, "fetchSessionMode must use the shared sessionReq recovery wrapper, not a bare request"
    assert "/api/session/" in tail and "/mode" in tail


def test_workflow_client_never_builds_an_owner_scoped_url():
    """api.ts's `api.*` functions must only ever address
    /api/session/{session_id}/... -- never construct a URL using an
    owner_id-shaped variable (which would silently address the wrong,
    persistent Career Profile resource with a disposable identity)."""
    src = _read("api.ts")
    for line in src.splitlines():
        if _OWNER_URL_VAR.search(line):
            raise AssertionError(f"api.ts appears to build an owner-scoped URL: {line}")
        if "/api/career-profile" in line:
            raise AssertionError(f"api.ts references a Career Profile route directly: {line}")


def test_owner_id_and_session_id_storage_keys_are_distinct():
    """The two identities must never share (or accidentally collide on) a
    localStorage key -- that would silently merge disposable workflow
    state with the durable Career Profile identity."""
    session_src = _read("api.ts")
    owner_src = _read("career-profile-api.ts")
    session_key = re.search(r'SESSION_KEY\s*=\s*"([^"]+)"', session_src)
    owner_key = re.search(r'OWNER_ID_KEY\s*=\s*"([^"]+)"', owner_src)
    assert session_key and owner_key, "expected both SESSION_KEY and OWNER_ID_KEY constants to exist"
    assert session_key.group(1) != owner_key.group(1)


def test_session_req_is_exported_from_api_ts():
    """lib/api.ts's sessionReq (the single stale-session recovery
    implementation) must be exported, so career-profile-api.ts's
    fetchSessionMode can reuse it instead of maintaining a second,
    divergent recovery implementation (or, as was the real bug, no
    recovery at all)."""
    src = _read("api.ts")
    assert re.search(r"export\s+async\s+function\s+sessionReq", src), (
        "sessionReq must be exported from api.ts so other session-scoped clients can reuse it"
    )


def test_fetch_session_mode_goes_through_shared_session_recovery():
    """Regression test for the exact reported bug: after SessionProvider's
    stale-session recovery rotates session_id (e.g. A -> B following a
    backend restart), EVERY subsequent session-scoped call -- including
    GET /api/session/{sid}/mode -- must use the new id, and must itself
    be able to recover if it independently hits a stale id. Before this
    fix, fetchSessionMode called a bare, unwrapped request with no
    recovery of its own, so it could 404 on a stale id even after
    api.missionControl() had already recovered successfully."""
    src = _read("career-profile-api.ts")
    assert "import { sessionReq } from \"./api\";" in src or "import { sessionReq } from './api';" in src, (
        "fetchSessionMode must import and use the shared sessionReq recovery wrapper from api.ts"
    )
    fn_start = src.index("export async function fetchSessionMode")
    fn_body = src[fn_start : fn_start + 400]
    # sessionReq may be called with a generic type argument (sessionReq<T>(...)),
    # so match the call itself rather than one exact literal.
    assert re.search(r"await\s+sessionReq\s*(<[^(]*>)?\s*\(", fn_body), (
        "fetchSessionMode must call sessionReq(), not a bare apiRequest/req()"
    )
