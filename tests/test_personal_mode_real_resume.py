"""
Regression tests for the Personal Mode "silently uses the demo resume" bug.

Root cause (see api/main.py::start_run and api/career_profile_routes.py):
the Next.js candidate-setup page never sent resume_path, and
api/main.py::start_run used to fall back unconditionally to
engine.DEMO_RESUME_PATH -- so every Personal Mode "Run Discovery" click
silently scored/tailored/verified against the synthetic certification-demo
candidate, regardless of the fact that target roles/work modes were
correctly sourced from the real Career Profile.

The fix:
  1. src/models/career_profile.py::ResumeSourceInfo gained a NEW
     resume_file_path field.
  2. api/career_profile_routes.py::apply_resume_update now writes the raw
     uploaded resume bytes to data/career_profile_resumes/{owner_id}/... and
     sets resume_source.resume_file_path -- only at explicit Apply time,
     never at upload/preview time.
  3. api/main.py::start_run no longer falls back to DEMO_RESUME_PATH: a
     /run call with no resume_path is now a controlled 422.
  4. engine.load_certification_demo() is unaffected -- it calls
     engine.start_new_run() directly with DEMO_RESUME_PATH, bypassing the
     HTTP /run endpoint (and its validation) entirely.

These tests exercise the real, certified pipeline end-to-end (real
resume_parser + real ProfileAgent against the deterministic mock LLM, real
LangGraph workflow via api/engine.py) -- nothing here is a shortcut or a
re-implementation of business logic.
"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from api import engine
from api.career_profile_routes import get_store
from api.main import app
from src.services import career_profile_store as store_module

# A distinctive skill that appears nowhere in data/sample_candidate/demo_resume.txt
# (whose SKILLS line is "Python, Machine Learning, LangChain, AWS, SQL").
PERSONAL_ONLY_SKILL = "ZorbatronCalibration"

PERSONAL_RESUME_TEXT = (
    b"Jordan Personal\n"
    b"AI engineer specializing in distributed systems.\n\n"
    b"SKILLS\n"
    b"Python, ZorbatronCalibration, Kubernetes\n\n"
    b"WORK EXPERIENCE\n"
    b"Staff Engineer | Personal Corp | 2020-01 - Present\n"
    b"Built distributed systems using Python and ZorbatronCalibration.\n\n"
    b"EDUCATION\n"
    b"B.S. Computer Science | Personal University | 2015-09 - 2019-05\n"
)

DEMO_RESUME_TEXT = open("data/sample_candidate/demo_resume.txt", "rb").read()


@pytest.fixture()
def client():
    conn = store_module.get_connection(":memory:")
    store_module.init_schema(conn)
    test_store = store_module.CareerProfileStore(conn)
    app.dependency_overrides[get_store] = lambda: test_store
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _upload_and_apply_resume(client: TestClient, owner_id: str, resume_bytes: bytes, filename: str = "resume.txt") -> dict:
    client.post(f"/api/career-profile/{owner_id}")
    upload_resp = client.post(
        f"/api/career-profile/{owner_id}/resume/upload",
        files={"file": (filename, io.BytesIO(resume_bytes), "text/plain")},
    )
    assert upload_resp.status_code == 200
    upload_id = upload_resp.json()["upload_id"]
    apply_resp = client.post(f"/api/career-profile/{owner_id}/resume/apply", json={"upload_id": upload_id})
    assert apply_resp.status_code == 200
    return apply_resp.json()


# ---------------------------------------------------------------------------
# 1. Personal Mode /run genuinely uses the real resume file
# ---------------------------------------------------------------------------


def test_personal_run_uses_real_resume_not_demo_resume(client, tmp_path):
    profile = _upload_and_apply_resume(client, "real-user-1", PERSONAL_RESUME_TEXT)
    resume_file_path = profile["resume_source"]["resume_file_path"]
    assert resume_file_path is not None
    assert resume_file_path != engine.DEMO_RESUME_PATH

    session_resp = client.post("/api/session")
    session_id = session_resp.json()["session_id"]

    run_resp = client.post(
        f"/api/session/{session_id}/run",
        json={"resume_path": resume_file_path, "target_roles": ["AI Engineer"], "work_modes": ["Remote"]},
    )
    assert run_resp.status_code == 200

    sess = engine.get_session(session_id)
    candidate_profile = sess.state.get("candidate_profile")
    assert candidate_profile is not None
    skill_names = {s["name"].lower() for s in candidate_profile["skills"]}
    assert any(PERSONAL_ONLY_SKILL.lower() in s for s in skill_names)
    assert candidate_profile["name"] == "Jordan Personal"


# ---------------------------------------------------------------------------
# 2. Demo Mode still genuinely uses the demo resume -- unaffected regression
# ---------------------------------------------------------------------------


def test_demo_mode_still_uses_demo_resume(client):
    session_resp = client.post("/api/session")
    session_id = session_resp.json()["session_id"]

    demo_resp = client.post(f"/api/session/{session_id}/demo/start")
    assert demo_resp.status_code == 200

    sess = engine.get_session(session_id)
    assert sess.mode == "CERTIFICATION_DEMO"
    assert sess.last_run_params["resume_path"] == engine.DEMO_RESUME_PATH
    candidate_profile = sess.state.get("candidate_profile")
    assert candidate_profile is not None
    assert candidate_profile["name"] == "Arjun Example"
    skill_names = {s["name"].lower() for s in candidate_profile["skills"]}
    assert not any(PERSONAL_ONLY_SKILL.lower() in s for s in skill_names)


# ---------------------------------------------------------------------------
# 3. /run with no resume on file returns a controlled 422, never a silent
#    fallback
# ---------------------------------------------------------------------------


def test_run_with_no_resume_path_returns_controlled_422(client):
    session_resp = client.post("/api/session")
    session_id = session_resp.json()["session_id"]

    run_resp = client.post(
        f"/api/session/{session_id}/run",
        json={"target_roles": ["AI Engineer"], "work_modes": ["Remote"]},
    )
    assert run_resp.status_code == 422
    assert "resume" in run_resp.json()["detail"].lower()

    # And the session must never have silently started a run against the
    # demo resume as a side effect of the rejected request.
    sess = engine.get_session(session_id)
    assert sess.state == {}
    assert sess.last_run_params is None


# ---------------------------------------------------------------------------
# 4. THE critical evidence-isolation test: a demo-only fact can never leak
#    into a Personal Mode candidate profile, and vice versa.
# ---------------------------------------------------------------------------


def test_personal_and_demo_resume_evidence_never_cross_contaminate(client):
    profile = _upload_and_apply_resume(client, "real-user-2", PERSONAL_RESUME_TEXT)
    resume_file_path = profile["resume_source"]["resume_file_path"]

    # -- Personal Mode run: must see ONLY the personal candidate's facts --
    personal_session = client.post("/api/session").json()["session_id"]
    client.post(
        f"/api/session/{personal_session}/run",
        json={"resume_path": resume_file_path, "target_roles": ["AI Engineer"], "work_modes": ["Remote"]},
    )
    personal_profile = engine.get_session(personal_session).state["candidate_profile"]
    personal_skill_names = {s["name"].lower() for s in personal_profile["skills"]}
    assert any(PERSONAL_ONLY_SKILL.lower() in s for s in personal_skill_names)
    # None of the demo candidate's distinctive skills ("Machine Learning",
    # "LangChain") leak into the personal candidate's profile.
    assert not any("langchain" in s for s in personal_skill_names)

    # -- Demo Mode run: must see ONLY the demo candidate's facts, never the
    #    personal-only skill, even though a real CareerProfile with that
    #    skill now exists in the same process. --
    demo_session = client.post("/api/session").json()["session_id"]
    client.post(f"/api/session/{demo_session}/demo/start")
    demo_profile = engine.get_session(demo_session).state["candidate_profile"]
    demo_skill_names = {s["name"].lower() for s in demo_profile["skills"]}
    assert not any(PERSONAL_ONLY_SKILL.lower() in s for s in demo_skill_names)
    assert any("langchain" in s for s in demo_skill_names)


# ---------------------------------------------------------------------------
# 5. Personal target roles/work modes/location survive end-to-end through
#    the real resume path
# ---------------------------------------------------------------------------


def test_personal_preferences_survive_through_real_resume_path(client):
    profile = _upload_and_apply_resume(client, "real-user-3", PERSONAL_RESUME_TEXT)
    resume_file_path = profile["resume_source"]["resume_file_path"]

    client.put(
        "/api/career-profile/real-user-3/preferences",
        json={"locations": ["Austin, TX"], "work_arrangements": ["Hybrid"]},
    )

    session_id = client.post("/api/session").json()["session_id"]
    run_resp = client.post(
        f"/api/session/{session_id}/run",
        json={"resume_path": resume_file_path, "target_roles": ["ML Engineer"], "work_modes": ["Hybrid"]},
    )
    assert run_resp.status_code == 200

    sess = engine.get_session(session_id)
    candidate_profile = sess.state["candidate_profile"]
    assert "ML Engineer" in candidate_profile["target_roles"]
    assert "HYBRID" in candidate_profile["preferred_work_modes"]
    assert sess.last_run_params["roles"] == ["ML Engineer"]
    assert sess.last_run_params["work_mode"] == ["HYBRID"]


# ---------------------------------------------------------------------------
# 6. Personal Mode Mission Control shows zero synthetic history on this
#    discovery path (reuses the isolation gate from
#    tests/test_career_profile_isolation.py, now checked end-to-end through
#    a real resume-backed /run call).
# ---------------------------------------------------------------------------


def test_personal_mode_run_has_zero_synthetic_history(client):
    profile = _upload_and_apply_resume(client, "real-user-4", PERSONAL_RESUME_TEXT)
    resume_file_path = profile["resume_source"]["resume_file_path"]

    session_id = client.post("/api/session").json()["session_id"]
    client.post(
        f"/api/session/{session_id}/run",
        json={"resume_path": resume_file_path, "target_roles": ["AI Engineer"], "work_modes": ["Remote"]},
    )

    sess = engine.get_session(session_id)
    assert sess.mode == "PERSONAL"
    analytics = engine.outcome_analytics_for(sess)
    assert analytics.total_applications == 0
    assert sess.tracker.list_applications() == []
    assert sess.tracker.list_strategy_insights() == []


# ---------------------------------------------------------------------------
# 7. The demo-resume-source label string must never appear in Personal
#    Mode's rendered output. The label itself is UI copy
#    (web/app/candidate-setup/page.tsx) with no backend equivalent to
#    assert against via an API response, so this is a source-level
#    regression check that the retired string is gone from that file and
#    the page never references the demo-resume framing for Personal Mode.
#    A full rendered-DOM check would require a browser/Playwright pass,
#    which is noted as manually-verifiable-only beyond this check.
# ---------------------------------------------------------------------------


def test_demo_resume_label_removed_from_candidate_setup_page_source():
    with open("web/app/candidate-setup/page.tsx", encoding="utf-8") as f:
        source = f.read()
    assert "certified demo candidate resume" not in source
    assert "synthetic, bundled with HireLoop" not in source
    assert "Your Career Profile" in source


# ---------------------------------------------------------------------------
# 8. Real smoke test (bug report Part 18): drive the graph past job
#    selection into evidence retrieval/tailoring and inspect the resulting
#    Truth Guard evidence retrieval pool directly -- proves resume evidence
#    comes from the REAL personal resume only, not the demo candidate's
#    facts, using the local/mock job source (no paid You.com call).
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 9. Part 13-14 regression: a richer synthetic resume (multiple skills, two
#    work experiences, a project, an education entry, a certification) must
#    survive, in full, from the Career Profile store through to the real
#    graph-built CandidateProfile a Personal Mode /run call produces --
#    proving no additional truncation happens between "what got stored"
#    and "what discovery actually scores against". Both come from the same
#    certified ProfileAgent.build_profile() call over the same resume
#    bytes (the file written to disk at Apply time), so this also proves
#    the Career Profile's stored facts are the SAME facts, not a
#    different, narrower extraction.
# ---------------------------------------------------------------------------

RICH_PERSONAL_RESUME_TEXT = (
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


def test_reviewed_rich_profile_reaches_real_graph_candidate_profile_unchanged(client):
    profile = _upload_and_apply_resume(client, "rich-real-user-1", RICH_PERSONAL_RESUME_TEXT)

    # The Career Profile store has the full, untruncated extraction.
    stored_skill_count = len(profile["skills"])
    stored_work_count = len(profile["work_experience"])
    stored_project_count = len(profile["projects"])
    stored_education_count = len(profile["education"])
    stored_cert_count = len(profile["certifications"])
    assert stored_skill_count >= 5
    assert stored_work_count == 2
    assert stored_project_count == 1
    assert stored_education_count == 1
    assert stored_cert_count == 1

    # Simulate the human review action (Part 9) on every flagged entry --
    # this is what the Resume & Evidence tab's "Confirm"/"Confirm as-is"
    # buttons call.
    for skill in profile["skills"]:
        r = client.put(f"/api/career-profile/rich-real-user-1/skills/{skill['name']}/review", json={})
        assert r.status_code == 200
    for entry in profile["work_experience"]:
        r = client.put(
            f"/api/career-profile/rich-real-user-1/work-experience/{entry['entry_id']}/review",
            json={"is_current": entry["end_date"] is None or entry["end_date"] == "Present"},
        )
        assert r.status_code == 200

    reviewed = client.get("/api/career-profile/rich-real-user-1").json()
    assert all(s["provenance"] == "USER_CONFIRMED" for s in reviewed["skills"])
    assert all(w["provenance"] == "USER_CONFIRMED" for w in reviewed["work_experience"])

    resume_file_path = reviewed["resume_source"]["resume_file_path"]
    session_id = client.post("/api/session").json()["session_id"]
    run_resp = client.post(
        f"/api/session/{session_id}/run",
        json={"resume_path": resume_file_path, "target_roles": ["Backend Engineer"], "work_modes": ["Remote"]},
    )
    assert run_resp.status_code == 200

    sess = engine.get_session(session_id)
    candidate_profile = sess.state["candidate_profile"]

    # The graph's own CandidateProfile (built by the same certified
    # ProfileAgent, from the same underlying resume file) is not a
    # truncated subset of what the Career Profile stored.
    assert len(candidate_profile["skills"]) >= 5
    assert len(candidate_profile["work_experience"]) == 2
    assert len(candidate_profile["projects"]) == 1
    assert len(candidate_profile["education"]) == 1
    assert len(candidate_profile["certifications"]) == 1

    graph_skill_names = {s["name"].lower() for s in candidate_profile["skills"]}
    stored_skill_names = {s["name"].lower() for s in reviewed["skills"]}
    assert stored_skill_names <= graph_skill_names

    graph_companies = {w["company"] for w in candidate_profile["work_experience"]}
    assert {"Widget Systems", "Data Forge"} <= graph_companies


def test_smoke_personal_candidate_evidence_pool_is_real_resume_only(client):
    profile = _upload_and_apply_resume(client, "smoke-user", PERSONAL_RESUME_TEXT)
    resume_file_path = profile["resume_source"]["resume_file_path"]

    session_id = client.post("/api/session").json()["session_id"]
    run_resp = client.post(
        f"/api/session/{session_id}/run",
        json={"resume_path": resume_file_path, "target_roles": ["AI Engineer"], "work_modes": ["Remote"]},
    )
    mc = run_resp.json()
    eligible = mc["interrupt"]["eligible_selections"]
    job_id = eligible[0]["job_id"]

    select_resp = client.post(f"/api/session/{session_id}/resume", json={"action": "SELECT", "job_id": job_id})
    assert select_resp.status_code == 200

    sess = engine.get_session(session_id)
    state = sess.state

    # Candidate identity/preferences come from the real Career Profile's
    # resume, not the demo candidate.
    assert state["candidate_profile"]["name"] == "Jordan Personal"
    assert "AI Engineer" in state["candidate_profile"]["target_roles"]
    assert "REMOTE" in state["candidate_profile"]["preferred_work_modes"]

    # Evidence pool (candidate_evidence -- what Truth Guard's retrieval
    # draws from) is built directly from the real personal resume text and
    # must contain the personal-only skill/employer, and must NOT contain
    # the demo candidate's distinctive employer/skills.
    evidence_pool = state.get("candidate_evidence", [])
    assert evidence_pool, "expected prepare_candidate_evidence_node to have run by the tailoring stage"
    evidence_text = " ".join(e.get("source_text", "") + " " + e.get("skill_name", "") for e in evidence_pool).lower()
    assert "zorbatroncalibration" in evidence_text or "personal corp" in evidence_text
    assert "nova labs" not in evidence_text
    assert "beta corp" not in evidence_text
    assert "langchain" not in evidence_text

    # Zero synthetic demo application history anywhere in this Personal
    # Mode session's resulting analytics.
    analytics = engine.outcome_analytics_for(sess)
    assert analytics.total_applications == 0
