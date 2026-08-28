"""
Regression tests for the Career Profile confirmation ENFORCEMENT gate.

Prior round added POST /{owner_id}/confirm and CareerProfile.confirmed_at
as an indicator, but nothing checked it before Personal Mode discovery
ran -- a user could click "Find Opportunities" and get real results with
an unconfirmed (or never-confirmed) profile. This round wires
confirmed_at into POST /api/session/{session_id}/run (api/main.py::
start_run) as a real, server-enforced gate, and adds invalidation of
confirmed_at whenever a MATERIAL field changes after confirmation.

All fixtures here are synthetic, written for this test file only -- never
real profile data, and never printed/logged.
"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from api import engine
from api.career_profile_routes import get_store
from api.main import app
from src.services import career_profile_store as store_module

_RICH_SYNTHETIC_RESUME = (
    b"Taylor Synthetic\n"
    b"AI engineer.\n\n"
    b"SKILLS\n"
    b"Python, Kubernetes, PyTorch\n\n"
    b"WORK EXPERIENCE\n"
    b"Staff Engineer | Synthetic Corp | 2020-01 - 2023-01\n"
    b"Built distributed systems.\n\n"
    b"EDUCATION\n"
    b"B.S. Computer Science | Synthetic University | 2015-09 - 2019-05\n"
)


@pytest.fixture()
def client():
    conn = store_module.get_connection(":memory:")
    store_module.init_schema(conn)
    test_store = store_module.CareerProfileStore(conn)
    app.dependency_overrides[get_store] = lambda: test_store
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _upload_and_apply(client: TestClient, owner_id: str, resume_bytes: bytes = _RICH_SYNTHETIC_RESUME) -> dict:
    client.post(f"/api/career-profile/{owner_id}")
    upload_resp = client.post(
        f"/api/career-profile/{owner_id}/resume/upload",
        files={"file": ("resume.txt", io.BytesIO(resume_bytes), "text/plain")},
    )
    assert upload_resp.status_code == 200
    upload_id = upload_resp.json()["upload_id"]
    apply_resp = client.post(f"/api/career-profile/{owner_id}/resume/apply", json={"upload_id": upload_id})
    assert apply_resp.status_code == 200
    return apply_resp.json()


def _build_complete_confirmed_profile(client: TestClient, owner_id: str) -> dict:
    """Builds a synthetic Career Profile through every REQUIRED category
    and confirms it. Returns the final, confirmed profile dict."""
    client.post(f"/api/career-profile/{owner_id}")
    client.put(
        f"/api/career-profile/{owner_id}/personal-info",
        json={"first_name": "Taylor", "last_name": "Synthetic", "professional_email": "taylor@example.com"},
    )
    client.put(
        f"/api/career-profile/{owner_id}/work-authorization",
        json={"authorized_to_work": True, "authorization_type": "US Citizen"},
    )
    client.put(f"/api/career-profile/{owner_id}/target-roles", json={"roles": [{"title": "Backend Engineer"}]})
    client.put(
        f"/api/career-profile/{owner_id}/preferences",
        json={"locations": ["Remote"], "work_arrangements": ["Remote"]},
    )
    profile = _upload_and_apply(client, owner_id)
    for skill in profile["skills"]:
        client.put(f"/api/career-profile/{owner_id}/skills/{skill['name']}/review", json={})
    for entry in profile["work_experience"]:
        client.put(
            f"/api/career-profile/{owner_id}/work-experience/{entry['entry_id']}/review",
            json={"end_date": entry["end_date"] or "2023-01"},
        )
    confirm_resp = client.post(f"/api/career-profile/{owner_id}/confirm")
    assert confirm_resp.status_code == 200
    return confirm_resp.json()


def _start_run(client: TestClient, owner_id: str, resume_path: str) -> "object":
    session_resp = client.post("/api/session")
    session_id = session_resp.json()["session_id"]
    return client.post(
        f"/api/session/{session_id}/run",
        json={
            "resume_path": resume_path,
            "target_roles": ["Backend Engineer"],
            "work_modes": ["Remote"],
            "owner_id": owner_id,
        },
    )


# ---------------------------------------------------------------------------
# 1. Confirm rejects an incomplete profile with reasons
# ---------------------------------------------------------------------------


def test_incomplete_profile_cannot_confirm(client):
    client.post("/api/career-profile/gate-incomplete-1")
    resp = client.post("/api/career-profile/gate-incomplete-1/confirm")
    assert resp.status_code == 409
    assert "still need review" in resp.json()["detail"]
    profile = client.get("/api/career-profile/gate-incomplete-1").json()
    assert profile["confirmed_at"] is None
    assert profile["confirmed_profile_version"] == 0


# ---------------------------------------------------------------------------
# 2. A fully complete/reviewed profile CAN confirm, and version increments
# ---------------------------------------------------------------------------


def test_complete_profile_can_confirm_and_version_increments(client):
    profile = _build_complete_confirmed_profile(client, "gate-complete-1")
    assert profile["confirmed_at"] is not None
    assert profile["confirmed_profile_version"] == 1


# ---------------------------------------------------------------------------
# 3. Demographics/References being unset never blocks confirmation
# ---------------------------------------------------------------------------


def test_optional_categories_unset_do_not_block_confirmation(client):
    profile = _build_complete_confirmed_profile(client, "gate-optional-1")
    assert profile["demographics"]["gender"] == "NOT_PROVIDED"
    assert profile["references"] == []
    assert profile["confirmed_at"] is not None


# ---------------------------------------------------------------------------
# 4/5. Unconfirmed profile's /run is rejected; confirmed profile's /run succeeds
# ---------------------------------------------------------------------------


def test_run_rejected_for_never_confirmed_profile(client):
    profile = _upload_and_apply(client, "gate-run-unconfirmed-1")
    resp = _start_run(client, "gate-run-unconfirmed-1", profile["resume_source"]["resume_file_path"])
    assert resp.status_code == 403
    assert "confirm your Career Profile" in resp.json()["detail"]


def test_run_rejected_when_no_profile_exists_at_all(client):
    session_resp = client.post("/api/session")
    session_id = session_resp.json()["session_id"]
    resp = client.post(
        f"/api/session/{session_id}/run",
        json={
            "resume_path": "data/career_profile_resumes/nonexistent",
            "target_roles": ["Backend Engineer"],
            "work_modes": ["Remote"],
            "owner_id": "gate-run-no-profile-1",
        },
    )
    assert resp.status_code == 403


def test_run_succeeds_for_confirmed_profile(client):
    profile = _build_complete_confirmed_profile(client, "gate-run-confirmed-1")
    resp = _start_run(client, "gate-run-confirmed-1", profile["resume_source"]["resume_file_path"])
    assert resp.status_code == 200


def test_run_without_owner_id_is_unaffected_by_gate(client):
    """Backward compatibility: an existing caller that never supplies
    owner_id (e.g. the pre-existing certified test suite) must never be
    newly blocked by this gate -- there is no Career Profile confirmation
    concept without an owner_id to check."""
    session_resp = client.post("/api/session")
    session_id = session_resp.json()["session_id"]
    resp = client.post(
        f"/api/session/{session_id}/run",
        json={
            "resume_path": engine.DEMO_RESUME_PATH,
            "target_roles": ["Backend Engineer"],
            "work_modes": ["Remote"],
        },
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 6. A material edit after confirmation invalidates it; /run is rejected again
# ---------------------------------------------------------------------------


def test_material_edit_target_roles_invalidates_confirmation_and_blocks_run(client):
    profile = _build_complete_confirmed_profile(client, "gate-material-roles-1")
    resume_path = profile["resume_source"]["resume_file_path"]

    updated = client.put(
        "/api/career-profile/gate-material-roles-1/target-roles",
        json={"roles": [{"title": "Frontend Engineer"}]},
    ).json()
    assert updated["confirmed_at"] is None

    resp = _start_run(client, "gate-material-roles-1", resume_path)
    assert resp.status_code == 403


def test_material_edit_work_authorization_invalidates_confirmation(client):
    profile = _build_complete_confirmed_profile(client, "gate-material-auth-1")
    assert profile["confirmed_at"] is not None

    updated = client.put(
        "/api/career-profile/gate-material-auth-1/work-authorization",
        json={"authorized_to_work": True, "authorization_type": "H1B"},
    ).json()
    assert updated["confirmed_at"] is None


def test_material_edit_preferences_invalidates_confirmation(client):
    profile = _build_complete_confirmed_profile(client, "gate-material-prefs-1")
    assert profile["confirmed_at"] is not None

    updated = client.put(
        "/api/career-profile/gate-material-prefs-1/preferences",
        json={"locations": ["Onsite - NYC"], "work_arrangements": ["Onsite"]},
    ).json()
    assert updated["confirmed_at"] is None


def test_noop_material_save_does_not_invalidate_confirmation(client):
    """Re-submitting the SAME preferences that are already stored must
    never spuriously invalidate confirmation."""
    profile = _build_complete_confirmed_profile(client, "gate-material-noop-1")
    assert profile["confirmed_at"] is not None

    updated = client.put(
        "/api/career-profile/gate-material-noop-1/preferences",
        json={"locations": ["Remote"], "work_arrangements": ["Remote"]},
    ).json()
    assert updated["confirmed_at"] is not None


# ---------------------------------------------------------------------------
# 7. Resume replacement after confirmation invalidates it
# ---------------------------------------------------------------------------


def test_resume_replacement_invalidates_confirmation(client):
    profile = _build_complete_confirmed_profile(client, "gate-resume-reapply-1")
    assert profile["confirmed_at"] is not None

    reapplied = _upload_and_apply(client, "gate-resume-reapply-1")
    assert reapplied["confirmed_at"] is None
    assert reapplied["confirmed_profile_version"] == 1  # tally, never reset


# ---------------------------------------------------------------------------
# 8. A harmless (non-material) edit does NOT invalidate confirmation
# ---------------------------------------------------------------------------


def test_personal_info_display_name_only_edit_does_not_invalidate_confirmation(client):
    profile = _build_complete_confirmed_profile(client, "gate-harmless-1")
    assert profile["confirmed_at"] is not None

    updated = client.put(
        "/api/career-profile/gate-harmless-1/personal-info",
        json={
            "first_name": "Taylor",
            "last_name": "Synthetic",
            "professional_email": "taylor@example.com",
            "preferred_name": "T.S.",
            "phone": "555-0100",
        },
    ).json()
    assert updated["confirmed_at"] is not None


def test_demographics_edit_does_not_invalidate_confirmation(client):
    profile = _build_complete_confirmed_profile(client, "gate-harmless-2")
    assert profile["confirmed_at"] is not None

    updated = client.put(
        "/api/career-profile/gate-harmless-2/demographics",
        json={"gender": "PREFER_NOT_TO_SAY"},
    ).json()
    assert updated["confirmed_at"] is not None


# ---------------------------------------------------------------------------
# 9. Personal/Demo isolation: /demo/start has zero relationship to
#    Career Profile confirmation state.
# ---------------------------------------------------------------------------


def test_demo_start_is_unaffected_by_confirmation_state(client):
    # No Career Profile at all for this session -- demo must still work.
    session_resp = client.post("/api/session")
    session_id = session_resp.json()["session_id"]
    resp = client.post(f"/api/session/{session_id}/demo/start")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("has_run") is True or "has_run" in body


def test_demo_start_unaffected_even_with_unconfirmed_real_profile_present(client):
    _upload_and_apply(client, "gate-demo-isolation-1")  # unconfirmed, on file
    session_resp = client.post("/api/session")
    session_id = session_resp.json()["session_id"]
    resp = client.post(f"/api/session/{session_id}/demo/start")
    assert resp.status_code == 200
