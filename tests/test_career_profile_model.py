"""
Career Profile model structural tests: privacy exclusions, provenance,
optional sections, references. See src/models/career_profile.py.
"""

from __future__ import annotations

import ast
from pathlib import Path

from src.models.career_profile import (
    CareerProfile,
    EEODemographics,
    PersonalInfo,
    ReferenceContact,
)
from src.models.field_provenance import FieldProvenance


def test_personal_info_has_no_street_address_field():
    fields = set(PersonalInfo.model_fields.keys())
    assert "street_address" not in fields
    assert "address" not in fields
    assert "address_line_1" not in fields
    assert "address_line_2" not in fields
    # Only structured city/state/country/postal are allowed.
    assert {"city", "state", "country", "postal_code"}.issubset(fields)


def test_no_email_password_field_anywhere_in_career_profile_module():
    """Structural regression test: statically scans the module source (not
    just one model) for any field name resembling a password/credential,
    since a future field addition to any nested model could reintroduce
    one without a targeted per-model test catching it."""
    source = Path("src/models/career_profile.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    suspicious_terms = ("password", "passwd", "secret", "credential")
    offending: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            name = node.target.id.lower()
            if any(term in name for term in suspicious_terms):
                offending.append(node.target.id)
    assert offending == [], f"found suspicious field name(s): {offending}"


def test_eeo_demographics_default_not_provided():
    demo = EEODemographics()
    assert demo.gender == "NOT_PROVIDED"
    assert demo.race_ethnicity == "NOT_PROVIDED"
    assert demo.veteran_status == "NOT_PROVIDED"
    assert demo.disability_status == "NOT_PROVIDED"


def test_references_optional_and_empty_by_default():
    profile = CareerProfile(owner_id="user-1")
    assert profile.references == []
    profile.references.append(ReferenceContact(name="Alex Recruiter"))
    assert len(profile.references) == 1
    assert profile.references[0].relationship is None


def test_field_provenance_enum_values():
    assert {p.value for p in FieldProvenance} == {
        "RESUME_DERIVED",
        "USER_CONFIRMED",
        "APPLICATION_ANSWER",
        "SYSTEM_DERIVED",
        "HUMAN_CONFIRMATION",
    }


def test_skills_and_work_experience_carry_provenance():
    profile = CareerProfile(owner_id="user-1")
    assert hasattr(profile, "skills")
    from src.models.career_profile import ProfileSkill, ProfileWorkExperience

    skill = ProfileSkill(name="Python")
    assert skill.provenance == FieldProvenance.RESUME_DERIVED  # extraction default
    we = ProfileWorkExperience(company="Acme", title="Engineer")
    assert we.provenance == FieldProvenance.RESUME_DERIVED


def test_work_authorization_defaults_to_user_confirmed_never_resume_derived():
    from src.models.career_profile import WorkAuthorization

    wa = WorkAuthorization(authorized_to_work=True)
    assert wa.provenance == FieldProvenance.USER_CONFIRMED
