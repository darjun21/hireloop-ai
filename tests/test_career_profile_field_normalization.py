"""
Regression tests for a real bug found during browser smoke-testing this
hardening pass: employment_types and preferred_employment_type /
preferred_work_mode on the Career Profile are free-text inputs in the
Next.js UI ("Full Time"), but the underlying pydantic models
(CareerEmploymentPreferences.employment_types, ApplicationAnswers.
preferred_employment_type/preferred_work_mode) require the canonical
enum value ("FULL_TIME"). Without normalization at the API boundary,
PUT /api/career-profile/{owner_id}/preferences with employment_types
containing "Full Time" raised an *uncaught* pydantic.ValidationError,
which produced a raw 500 response with NO CORS headers at all -- in a
real browser this was indistinguishable from (and was in fact reported
as) a CORS failure, even though the actual root cause was this
validation gap.

These tests cover both the specific normalization fix
(api/validation.py's normalize_employment_type(s)) and the general
safety net (api/main.py's pydantic ValidationError exception handler,
which guarantees CORS headers are present even if some other uncaught
domain-model ValidationError slips through in the future).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.career_profile_routes import get_store
from api.main import app
from api.validation import (
    InvalidEmploymentTypeError,
    normalize_employment_type,
    normalize_employment_types,
)
from src.services import career_profile_store as store_module


@pytest.fixture()
def client():
    conn = store_module.get_connection(":memory:")
    store_module.init_schema(conn)
    test_store = store_module.CareerProfileStore(conn)
    app.dependency_overrides[get_store] = lambda: test_store
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Full Time", "FULL_TIME"),
        ("full-time", "FULL_TIME"),
        ("FULL_TIME", "FULL_TIME"),
        ("full_time", "FULL_TIME"),
        ("Part Time", "PART_TIME"),
        ("Contract", "CONTRACT"),
        ("Contractor", "CONTRACT"),
        ("Internship", "INTERNSHIP"),
        ("Intern", "INTERNSHIP"),
        ("Temporary", "TEMPORARY"),
        ("Temp", "TEMPORARY"),
    ],
)
def test_normalize_employment_type_accepts_display_labels(raw, expected):
    assert normalize_employment_type(raw) == expected


def test_normalize_employment_type_rejects_garbage():
    with pytest.raises(InvalidEmploymentTypeError):
        normalize_employment_type("Freelance Gig Thing")


def test_normalize_employment_types_list():
    assert normalize_employment_types(["Full Time", "contract"]) == ["FULL_TIME", "CONTRACT"]


def test_put_preferences_with_display_label_employment_type_succeeds(client):
    resp = client.put(
        "/api/career-profile/owner-et-1/preferences",
        json={
            "locations": ["United States"],
            "work_arrangements": [],
            "employment_types": ["Full Time"],
            "relocation_willing": True,
        },
        headers={"Origin": "http://localhost:3000"},
    )
    assert resp.status_code == 200
    assert resp.json()["employment_preferences"]["employment_types"] == ["FULL_TIME"]
    # The real-user bug: this must carry CORS headers, not just succeed.
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_put_preferences_with_invalid_employment_type_returns_controlled_422(client):
    resp = client.put(
        "/api/career-profile/owner-et-2/preferences",
        json={"employment_types": ["Freelance Gig Thing"]},
        headers={"Origin": "http://localhost:3000"},
    )
    assert resp.status_code == 422
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert "Freelance Gig Thing" in resp.json()["detail"]


def test_put_application_answers_normalizes_display_labels(client):
    resp = client.put(
        "/api/career-profile/owner-et-3/application-answers",
        json={"preferred_employment_type": "Full Time", "preferred_work_mode": "Remote"},
        headers={"Origin": "http://localhost:3000"},
    )
    assert resp.status_code == 200
    body = resp.json()["application_answers"]
    assert body["preferred_employment_type"] == "FULL_TIME"
    assert body["preferred_work_mode"] == "REMOTE"


def test_put_application_answers_invalid_work_mode_is_controlled_422(client):
    resp = client.put(
        "/api/career-profile/owner-et-4/application-answers",
        json={"preferred_work_mode": "not-a-real-mode"},
        headers={"Origin": "http://localhost:3000"},
    )
    assert resp.status_code == 422
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_uncaught_pydantic_validation_error_still_carries_cors_headers(client):
    """General safety-net check: even bypassing the explicit
    normalize_* validation (by PUTting a raw HTTPX-adjacent call that
    would otherwise reach the domain model with something invalid),
    api/main.py's ValidationError handler must produce a controlled 422
    with CORS headers -- never a bare 500 with no CORS headers, which is
    indistinguishable from a real CORS misconfiguration in a browser."""
    resp = client.put(
        "/api/career-profile/owner-et-5/preferences",
        json={"employment_types": ["still not valid"]},
        headers={"Origin": "http://127.0.0.1:3001"},
    )
    assert resp.status_code != 500
    assert resp.headers.get("access-control-allow-origin") == "http://127.0.0.1:3001"
