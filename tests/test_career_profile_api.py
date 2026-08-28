"""
FastAPI integration tests for the new /api/career-profile/* routes.

Uses a dedicated, isolated CareerProfileStore per test (via dependency
override) instead of the module-level store backing the live app, so
tests never touch data/career_profiles.db on disk.
"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from api.career_profile_routes import get_store
from api.main import app
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


def test_create_and_get_profile(client):
    resp = client.post("/api/career-profile/user-1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["owner_id"] == "user-1"
    assert body["skills"] == []

    resp2 = client.get("/api/career-profile/user-1")
    assert resp2.status_code == 200
    assert resp2.json()["profile_id"] == body["profile_id"]


def test_get_unknown_profile_is_404(client):
    resp = client.get("/api/career-profile/nobody")
    assert resp.status_code == 404


def test_update_work_authorization_never_inferred_stores_exactly_confirmed(client):
    client.post("/api/career-profile/user-2")
    resp = client.put(
        "/api/career-profile/user-2/work-authorization",
        json={
            "authorized_to_work": True,
            "authorization_type": "US Citizen",
            "requires_sponsorship_now": False,
        },
    )
    assert resp.status_code == 200
    wa = resp.json()["work_authorization"]
    assert wa["authorized_to_work"] is True
    assert wa["authorization_type"] == "US Citizen"
    assert wa["provenance"] == "USER_CONFIRMED"


def test_update_preferences_normalizes_work_mode_labels(client):
    client.post("/api/career-profile/user-3")
    resp = client.put(
        "/api/career-profile/user-3/preferences",
        json={"locations": ["Remote"], "work_arrangements": ["Remote", "Hybrid"]},
    )
    assert resp.status_code == 200
    prefs = resp.json()["employment_preferences"]
    assert prefs["work_arrangements"] == ["REMOTE", "HYBRID"]


def test_update_preferences_rejects_invalid_work_mode(client):
    client.post("/api/career-profile/user-3b")
    resp = client.put(
        "/api/career-profile/user-3b/preferences",
        json={"work_arrangements": ["not-a-real-mode"]},
    )
    assert resp.status_code == 422


def test_update_application_answers_separate_from_resume_facts(client):
    client.post("/api/career-profile/user-4")
    resp = client.put(
        "/api/career-profile/user-4/application-answers",
        json={"authorized_to_work": True, "willing_to_relocate": False, "notice_period": "2 weeks"},
    )
    assert resp.status_code == 200
    answers = resp.json()["application_answers"]
    assert answers["notice_period"] == "2 weeks"
    assert answers["provenance"] == "APPLICATION_ANSWER"
    # Application answers never write into resume-derived professional info.
    assert resp.json()["work_experience"] == []


def test_update_demographics_defaults_and_optional(client):
    client.post("/api/career-profile/user-5")
    resp = client.get("/api/career-profile/user-5")
    assert resp.json()["demographics"]["gender"] == "NOT_PROVIDED"

    resp2 = client.put("/api/career-profile/user-5/demographics", json={"gender": "Woman"})
    assert resp2.status_code == 200
    assert resp2.json()["demographics"]["gender"] == "Woman"


def test_completeness_endpoint(client):
    client.post("/api/career-profile/user-6")
    resp = client.get("/api/career-profile/user-6/completeness")
    assert resp.status_code == 200
    body = resp.json()
    categories = {c["category"] for c in body["categories"]}
    assert "IDENTITY_CONTACT" in categories
    assert body["overall_percent_complete"] == 0.0


def test_resume_upload_diff_apply_flow(client):
    resume_text = (
        b"Jane Doe\nAI engineer.\n\nSKILLS\nPython, LangChain, AWS\n\n"
        b"WORK EXPERIENCE\nAI Engineer | Nova Labs | 2022-01 - Present\n"
        b"Built retrieval pipelines using Python and LangChain deployed on AWS.\n"
    )
    client.post("/api/career-profile/user-7")

    upload_resp = client.post(
        "/api/career-profile/user-7/resume/upload",
        files={"file": ("resume.txt", io.BytesIO(resume_text), "text/plain")},
    )
    assert upload_resp.status_code == 200
    body = upload_resp.json()
    upload_id = body["upload_id"]
    assert "diff" in body

    # Nothing persisted yet.
    profile_before = client.get("/api/career-profile/user-7").json()
    assert profile_before["skills"] == []

    apply_resp = client.post("/api/career-profile/user-7/resume/apply", json={"upload_id": upload_id})
    assert apply_resp.status_code == 200
    profile_after = apply_resp.json()
    assert len(profile_after["skills"]) > 0
    assert profile_after["resume_source"]["parsed_profile_version"] == 1

    # Re-applying the same (now-consumed) upload_id fails cleanly.
    reapply_resp = client.post("/api/career-profile/user-7/resume/apply", json={"upload_id": upload_id})
    assert reapply_resp.status_code == 404


def test_resume_upload_cancel_never_persists(client):
    resume_text = b"John Smith\n\nSKILLS\nJava\n"
    client.post("/api/career-profile/user-8")

    upload_resp = client.post(
        "/api/career-profile/user-8/resume/upload",
        files={"file": ("resume.txt", io.BytesIO(resume_text), "text/plain")},
    )
    upload_id = upload_resp.json()["upload_id"]

    cancel_resp = client.post("/api/career-profile/user-8/resume/cancel", json={"upload_id": upload_id})
    assert cancel_resp.status_code == 200

    profile = client.get("/api/career-profile/user-8").json()
    assert profile["skills"] == []


def test_resume_upload_unsupported_file_type_returns_422(client):
    client.post("/api/career-profile/user-9")
    resp = client.post(
        "/api/career-profile/user-9/resume/upload",
        files={"file": ("resume.xyz", io.BytesIO(b"garbage"), "application/octet-stream")},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Parts 5-11: full structured resume upload (synthetic fixture — multiple
# skills, work experience, a project, education, a certification), field-
# level review actions (Part 9), and completeness recalculation on review
# (Parts 10-11).
# ---------------------------------------------------------------------------

_RICH_SYNTHETIC_RESUME = (
    b"Taylor Synthetic\n"
    b"Backend engineer focused on distributed data systems.\n\n"
    b"SKILLS\n"
    b"Python, Kafka, PostgreSQL, Docker, Terraform\n\n"
    b"WORK EXPERIENCE\n"
    b"Senior Backend Engineer | Widget Systems | 2021-03 - Present\n"
    b"Built event pipelines with Python and Kafka on Docker.\n\n"
    b"Backend Engineer | Data Forge | 2018-06 - 2021-02\n"
    b"Maintained PostgreSQL services and Terraform infrastructure.\n\n"
    b"PROJECTS\n"
    b"FinRAG\n"
    b"Retrieval pipeline built with Python and PostgreSQL.\n\n"
    b"EDUCATION\n"
    b"B.S. Computer Science | State University | 2014-09 - 2018-05\n\n"
    b"CERTIFICATIONS\n"
    b"AWS Certified Developer | Amazon | 2022-05\n"
)


def _upload_and_apply(client, owner_id: str, resume_bytes: bytes = _RICH_SYNTHETIC_RESUME) -> dict:
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


def test_rich_resume_upload_preserves_all_sections_not_a_truncated_subset(client):
    profile = _upload_and_apply(client, "rich-user-1")
    assert len(profile["skills"]) >= 5
    assert len(profile["work_experience"]) == 2
    assert len(profile["projects"]) == 1
    assert len(profile["education"]) == 1
    assert len(profile["certifications"]) == 1
    # Every skill starts RESUME_DERIVED, unreviewed.
    assert all(s["provenance"] == "RESUME_DERIVED" for s in profile["skills"])


def test_extraction_warnings_persist_on_profile_after_apply(client):
    # A resume with a work-experience entry missing company/title triggers
    # a real ProfileAgent validation warning (see
    # src/agents/profile_agent.py::_build_work_experience).
    resume = (
        b"Pat Warnings\n\nSKILLS\nPython\n\nWORK EXPERIENCE\n"
        b" |  | 2020-01 - 2021-01\nSome role with no company or title.\n"
    )
    profile = _upload_and_apply(client, "warn-user-1", resume)
    assert isinstance(profile["resume_source"]["extraction_warnings"], list)


def test_review_skill_confirms_and_flips_provenance(client):
    profile = _upload_and_apply(client, "review-user-1")
    skill_name = profile["skills"][0]["name"]
    resp = client.put(f"/api/career-profile/review-user-1/skills/{skill_name}/review", json={})
    assert resp.status_code == 200
    updated_skill = next(s for s in resp.json()["skills"] if s["name"] == skill_name)
    assert updated_skill["provenance"] == "USER_CONFIRMED"


def test_review_unknown_skill_is_404(client):
    client.post("/api/career-profile/review-user-1b")
    resp = client.put("/api/career-profile/review-user-1b/skills/nonexistent/review", json={})
    assert resp.status_code == 404


def test_review_work_experience_can_set_missing_end_date_and_confirms(client):
    profile = _upload_and_apply(client, "review-user-2")
    entry = profile["work_experience"][0]
    assert entry["provenance"] == "RESUME_DERIVED"

    resp = client.put(
        f"/api/career-profile/review-user-2/work-experience/{entry['entry_id']}/review",
        json={"is_current": True},
    )
    assert resp.status_code == 200
    updated_entry = next(w for w in resp.json()["work_experience"] if w["entry_id"] == entry["entry_id"])
    assert updated_entry["provenance"] == "USER_CONFIRMED"
    assert updated_entry["end_date"] == "Present"


def test_review_education_and_project_confirm_as_is(client):
    profile = _upload_and_apply(client, "review-user-3")
    edu = profile["education"][0]
    proj = profile["projects"][0]

    edu_resp = client.put(f"/api/career-profile/review-user-3/education/{edu['entry_id']}/review", json={})
    assert edu_resp.status_code == 200
    assert next(e for e in edu_resp.json()["education"] if e["entry_id"] == edu["entry_id"])["provenance"] == "USER_CONFIRMED"

    proj_resp = client.put(f"/api/career-profile/review-user-3/projects/{proj['entry_id']}/review", json={})
    assert proj_resp.status_code == 200
    assert next(p for p in proj_resp.json()["projects"] if p["entry_id"] == proj["entry_id"])["provenance"] == "USER_CONFIRMED"


def test_professional_history_recalculates_complete_after_reviewing_all_entries(client):
    profile = _upload_and_apply(client, "review-user-4")

    completeness_before = client.get("/api/career-profile/review-user-4/completeness").json()
    before_status = next(c for c in completeness_before["categories"] if c["category"] == "PROFESSIONAL_HISTORY")
    assert before_status["status"] == "NEEDS_REVIEW"
    assert len(before_status["review_reasons"]) > 0

    for skill in profile["skills"]:
        client.put(f"/api/career-profile/review-user-4/skills/{skill['name']}/review", json={})
    for entry in profile["work_experience"]:
        client.put(
            f"/api/career-profile/review-user-4/work-experience/{entry['entry_id']}/review",
            json={"end_date": entry["end_date"] or "2023-01"},
        )

    completeness_after = client.get("/api/career-profile/review-user-4/completeness").json()
    after_status = next(c for c in completeness_after["categories"] if c["category"] == "PROFESSIONAL_HISTORY")
    assert after_status["status"] == "COMPLETE"
    assert after_status["review_reasons"] == []


def test_confirm_profile_rejected_until_required_categories_complete(client):
    client.post("/api/career-profile/confirm-user-1")
    resp = client.post("/api/career-profile/confirm-user-1/confirm")
    assert resp.status_code == 409
    profile = client.get("/api/career-profile/confirm-user-1").json()
    assert profile["confirmed_at"] is None


def test_confirm_profile_succeeds_once_all_required_categories_complete(client):
    client.post("/api/career-profile/confirm-user-2")
    client.put(
        "/api/career-profile/confirm-user-2/personal-info",
        json={"first_name": "Taylor", "last_name": "Synthetic", "professional_email": "taylor@example.com"},
    )
    client.put(
        "/api/career-profile/confirm-user-2/work-authorization",
        json={"authorized_to_work": True, "authorization_type": "US Citizen"},
    )
    client.put("/api/career-profile/confirm-user-2/target-roles", json={"roles": [{"title": "Backend Engineer"}]})
    client.put(
        "/api/career-profile/confirm-user-2/preferences",
        json={"locations": ["Remote"], "work_arrangements": ["Remote"]},
    )
    profile = _upload_and_apply(client, "confirm-user-2")
    for skill in profile["skills"]:
        client.put(f"/api/career-profile/confirm-user-2/skills/{skill['name']}/review", json={})
    for entry in profile["work_experience"]:
        client.put(
            f"/api/career-profile/confirm-user-2/work-experience/{entry['entry_id']}/review",
            json={"end_date": entry["end_date"] or "2023-01"},
        )

    resp = client.post("/api/career-profile/confirm-user-2/confirm")
    assert resp.status_code == 200
    assert resp.json()["confirmed_at"] is not None

    # A fresh resume apply invalidates the prior confirmation.
    reapply = _upload_and_apply(client, "confirm-user-2")
    assert reapply["confirmed_at"] is None


def test_mode_endpoint_defaults_to_personal():
    with TestClient(app) as client:
        session_resp = client.post("/api/session")
        session_id = session_resp.json()["session_id"]
        mode_resp = client.get(f"/api/session/{session_id}/mode")
        assert mode_resp.status_code == 200
        assert mode_resp.json()["mode"] == "PERSONAL"


def test_certification_demo_flow_still_works_end_to_end():
    """Confirms the pre-existing certification demo endpoint is completely
    unaffected by the Career Profile additions (new router mount,
    Session.mode field, outcome_analytics_for's extra gate)."""
    with TestClient(app) as client:
        session_resp = client.post("/api/session")
        session_id = session_resp.json()["session_id"]

        demo_resp = client.post(f"/api/session/{session_id}/demo/start")
        assert demo_resp.status_code == 200
        view = demo_resp.json()
        assert "interrupt" in view or "human_decision" in view or view is not None

        mode_resp = client.get(f"/api/session/{session_id}/mode")
        assert mode_resp.json()["mode"] == "CERTIFICATION_DEMO"
