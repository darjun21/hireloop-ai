"""
Priority 5 hardening pass: audit every OTHER frontend-controlled,
enum-backed field beyond WorkMode/EmploymentType (already normalized in
api/validation.py and covered by tests/test_api_work_mode_normalization.py
and tests/test_career_profile_field_normalization.py).

Audit findings, field by field:

- TargetRole.priority (src/models/career_profile.py's RolePriority enum,
  reached via PUT /api/career-profile/{owner_id}/target-roles's
  TargetRolesBody.roles: list[TargetRole]) IS a strict enum-backed field
  reachable from the frontend, but it is declared as a nested pydantic
  model type on the request body itself -- FastAPI parses/validates it
  automatically as part of ordinary request-body validation, which is
  handled by FastAPI's own RequestValidationError machinery (registered
  INSIDE CORSMiddleware by FastAPI itself) and already returns a clean,
  CORS-header-carrying 422 for a bad value. This is a different code path
  from the "handler manually constructs a pydantic model from body.
  model_dump()" pattern that caused the original WorkMode/EmploymentType
  500-as-CORS-failure bug (see api/main.py's PydanticValidationError
  handler docstring) -- there is no gap here to fix, only to verify, which
  test_bad_role_priority_case_is_a_controlled_422_not_500 below does. The
  frontend itself (web/app/career-profile/page.tsx's CareerTab) never
  actually sends a priority value today (always null), so this is
  defense-in-depth, not a fix for an observed bug.

- Application status (src/models/enums.py's ApplicationStatus) and
  outcome/resume-approval "action" strings (api/main.py's ResumeRequest.
  action, OutcomeSubmitRequest.action) are NOT enum-typed pydantic fields
  at all -- both are plain `str`, and the values sent are fixed literal
  constants from button click handlers in the Next.js UI (never free
  text/a loosely-typed input a user can mistype), interpreted deep inside
  src/graph/ (out of scope to modify this pass). No gap: there is no
  "friendly label doesn't match canonical value" failure mode possible
  here because there is no friendly-label input surface for these fields.

- EvidenceSourceType, InsightCategory, ActionabilityLevel,
  SampleConfidence, TruthGuardStatus, RecommendationBand, ConfidenceLevel,
  JobQualityRecommendation (src/models/enums.py) are all backend-computed
  output-only values (scoring/verification/analytics results serialized
  to the frontend) -- never accepted as request input anywhere in api/main.py
  or api/career_profile_routes.py. No gap.

- WorkAuthorization.authorization_type is a genuinely free-text field
  (str | None, not enum-backed -- see src/models/career_profile.py and
  the "e.g. US Citizen, H1B, OPT" placeholder in
  web/app/career-profile/page.tsx's AuthorizationTab) -- there is no
  canonical enum to normalize against, so this is correctly NOT
  enum-validated.

Conclusion: WorkMode and EmploymentType (already normalized) remain the
only enum-backed fields on a frontend-controlled request body that accept
a free-text/loosely-typed display label. No new normalizer was added
this pass; this file exists to make that audit conclusion an explicit,
reproducible regression test rather than an unverified claim.
"""

from __future__ import annotations

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


def test_valid_role_priority_values_are_accepted(client):
    owner_id = "audit-owner-1"
    client.post(f"/api/career-profile/{owner_id}")
    resp = client.put(
        f"/api/career-profile/{owner_id}/target-roles",
        json={"roles": [{"title": "AI Engineer", "priority": "PRIMARY"}]},
    )
    assert resp.status_code == 200
    assert resp.json()["target_roles"][0]["priority"] == "PRIMARY"


def test_bad_role_priority_case_is_a_controlled_422_not_500(client):
    """A mistyped/mis-cased priority ("primary" instead of "PRIMARY") must
    come back as a normal, CORS-header-carrying 422 -- FastAPI's own
    request-body validation already guarantees this (see module
    docstring); this test exists to catch a regression if that ever
    changes (e.g. TargetRole.priority becoming a plain str somewhere)."""
    owner_id = "audit-owner-2"
    client.post(f"/api/career-profile/{owner_id}")
    resp = client.put(
        f"/api/career-profile/{owner_id}/target-roles",
        json={"roles": [{"title": "AI Engineer", "priority": "primary"}]},
        headers={"Origin": "http://localhost:3000"},
    )
    assert resp.status_code == 422
    # A 422 raised by FastAPI's own request validation (not a raw
    # ServerErrorMiddleware 500) always carries CORS headers when the
    # request declares an allowed Origin.
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_null_role_priority_still_accepted(client):
    owner_id = "audit-owner-3"
    client.post(f"/api/career-profile/{owner_id}")
    resp = client.put(
        f"/api/career-profile/{owner_id}/target-roles",
        json={"roles": [{"title": "AI Engineer", "priority": None}]},
    )
    assert resp.status_code == 200
    assert resp.json()["target_roles"][0]["priority"] is None


def test_resume_and_outcome_action_fields_are_plain_strings_not_enums():
    """Documents the audit finding that ResumeRequest.action and
    OutcomeSubmitRequest.action are intentionally plain `str` (fixed
    button-driven literals from the UI, not free-text/enum-backed) --
    if either is ever changed to a strict enum type, this test should be
    revisited alongside a normalizer, matching the WorkMode/EmploymentType
    pattern."""
    from api.main import OutcomeSubmitRequest, ResumeRequest

    assert ResumeRequest.model_fields["action"].annotation is str
    assert OutcomeSubmitRequest.model_fields["action"].annotation is str
