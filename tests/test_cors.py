"""
CORS integration tests for api/main.py's CORSMiddleware config.

A real user hit browser CORS failures on every PUT to
/api/career-profile/{owner_id}/... from http://localhost:3000 to a
backend running at http://127.0.0.1:8000. These tests exercise the
actual preflight (OPTIONS) and real-request CORS headers Starlette's
TestClient (which runs the real ASGI middleware stack, unlike a plain
function call) produces for each allowed origin, so a regression here
would fail loudly instead of only being caught by manual browser
testing.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app

ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
]


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.mark.parametrize("origin", ALLOWED_ORIGINS)
def test_preflight_succeeds_for_career_profile_put(client, origin):
    resp = client.options(
        "/api/career-profile/some-owner/personal-info",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert resp.status_code in (200, 204)
    assert resp.headers.get("access-control-allow-origin") == origin
    assert "PUT" in resp.headers.get("access-control-allow-methods", "")


@pytest.mark.parametrize("origin", ALLOWED_ORIGINS)
def test_preflight_succeeds_for_resume_upload(client, origin):
    resp = client.options(
        "/api/career-profile/some-owner/resume/upload",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert resp.status_code in (200, 204)
    assert resp.headers.get("access-control-allow-origin") == origin


@pytest.mark.parametrize("origin", ALLOWED_ORIGINS)
def test_real_put_request_carries_cors_header(client, origin):
    resp = client.put(
        "/api/career-profile/cors-test-owner/personal-info",
        json={"first_name": "A", "last_name": "B", "professional_email": "a@b.com"},
        headers={"Origin": origin},
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == origin


@pytest.mark.parametrize("origin", ALLOWED_ORIGINS)
def test_mission_control_get_carries_cors_header(client, origin):
    create = client.post("/api/session")
    session_id = create.json()["session_id"]
    resp = client.get(f"/api/session/{session_id}/mission-control", headers={"Origin": origin})
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == origin


def test_disallowed_origin_not_echoed(client):
    resp = client.get("/api/health", headers={"Origin": "http://evil.example.com"})
    # Starlette's CORSMiddleware still serves the response (it isn't a
    # server-side gate), but must NOT echo back an untrusted origin.
    assert resp.headers.get("access-control-allow-origin") != "http://evil.example.com"


def test_allow_origins_is_not_wildcard():
    """allow_credentials=True + allow_origins=["*"] is rejected by real
    browsers -- this must remain a real, explicit origin list."""
    assert app.user_middleware  # sanity: middleware is registered
    cors_mw = next(m for m in app.user_middleware if m.cls.__name__ == "CORSMiddleware")
    assert cors_mw.kwargs["allow_origins"] != ["*"]
    assert set(ALLOWED_ORIGINS) <= set(cors_mw.kwargs["allow_origins"])
