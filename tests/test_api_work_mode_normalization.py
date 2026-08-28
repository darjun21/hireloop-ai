"""
Regression tests for the "Remote" work-mode boundary bug: the Next.js
frontend/API sends user-friendly display labels (e.g. "Remote"), but
src/models/enums.py::WorkMode's canonical values are uppercase
("REMOTE"). Before the fix, this reached
src/graph/nodes/resume.py::_build_preferences's WorkMode(m) unguarded and
raised ValueError: 'Remote' is not a valid WorkMode, surfacing as an
unhandled 500 at the API boundary.

The fix (api/validation.py) normalizes at the API boundary, before
initial_state is ever built -- src/graph/nodes/resume.py itself is
untouched, exactly as required.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.validation import InvalidWorkModeError, normalize_work_mode, normalize_work_modes
from src.models.enums import WorkMode

# ---------------------------------------------------------------------------
# Unit tests: normalize_work_mode / normalize_work_modes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("raw", ["Remote", "remote", "REMOTE"])
def test_normalizes_remote_variants(raw):
    assert normalize_work_mode(raw) == WorkMode.REMOTE.value


@pytest.mark.parametrize("raw", ["Hybrid", "hybrid", "HYBRID"])
def test_normalizes_hybrid_variants(raw):
    assert normalize_work_mode(raw) == WorkMode.HYBRID.value


@pytest.mark.parametrize("raw", ["Onsite", "onsite", "ONSITE", "On-site", "on-site", "On Site"])
def test_normalizes_onsite_variants(raw):
    assert normalize_work_mode(raw) == WorkMode.ONSITE.value


@pytest.mark.parametrize("raw", ["Flexible", "flexible", "FLEXIBLE"])
def test_normalizes_flexible_variants(raw):
    assert normalize_work_mode(raw) == WorkMode.FLEXIBLE.value


@pytest.mark.parametrize("raw", ["Space", "unknown", "", "  ", None, 42])
def test_invalid_work_mode_raises_controlled_error(raw):
    with pytest.raises(InvalidWorkModeError):
        normalize_work_mode(raw)


def test_normalize_work_modes_preserves_order_and_normalizes_each():
    assert normalize_work_modes(["Remote", "HYBRID", "on-site"]) == [
        WorkMode.REMOTE.value,
        WorkMode.HYBRID.value,
        WorkMode.ONSITE.value,
    ]


def test_normalize_work_modes_raises_on_first_invalid_entry():
    with pytest.raises(InvalidWorkModeError):
        normalize_work_modes(["Remote", "not-a-real-mode"])


# ---------------------------------------------------------------------------
# API-boundary tests: POST /api/session/{id}/run
# ---------------------------------------------------------------------------


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture()
def session_id(client):
    response = client.post("/api/session")
    assert response.status_code == 200
    return response.json()["session_id"]


def test_run_with_display_label_remote_reaches_next_node_not_valueerror(client, session_id):
    """The exact real-user scenario from the bug report: preferred_work_modes
    = ["Remote"] must not raise ValueError('Remote' is not a valid
    WorkMode) -- it must be normalized and the workflow must proceed past
    build_candidate_profile to the next real node/interrupt."""
    response = client.post(
        f"/api/session/{session_id}/run",
        json={"target_roles": ["AI Engineer"], "work_modes": ["Remote"]},
    )
    assert response.status_code == 200
    body = response.json()
    # Reaching the human-selection interrupt (stage_status.SCORE == "human")
    # proves the graph advanced past build_candidate_profile/
    # _build_preferences without crashing on the raw "Remote" label.
    assert body.get("has_run") is True
    assert body.get("stage_status", {}).get("DISCOVER") == "done"


def test_run_with_mixed_case_work_modes_succeeds(client, session_id):
    response = client.post(
        f"/api/session/{session_id}/run",
        json={"target_roles": ["AI Engineer"], "work_modes": ["remote", "HYBRID", "On-site"]},
    )
    assert response.status_code == 200
    assert response.json().get("workflow_status") != "FAILED"


def test_run_with_invalid_work_mode_returns_controlled_422_not_500(client, session_id):
    response = client.post(
        f"/api/session/{session_id}/run",
        json={"target_roles": ["AI Engineer"], "work_modes": ["Anywhere"]},
    )
    assert response.status_code == 422
    assert "Anywhere" in response.json()["detail"]


def test_candidate_preferences_survive_into_candidate_profile(client, session_id):
    """Verifies the normalized work mode actually round-trips into the
    real CandidateProfile the graph builds -- not just that the request
    didn't crash."""
    response = client.post(
        f"/api/session/{session_id}/run",
        json={"target_roles": ["AI Engineer"], "work_modes": ["Remote"]},
    )
    assert response.status_code == 200
    from api import engine

    sess = engine.get_session(session_id)
    profile = sess.state.get("candidate_profile")
    assert profile is not None
    assert WorkMode.REMOTE.value in profile.get("preferred_work_modes", [])
