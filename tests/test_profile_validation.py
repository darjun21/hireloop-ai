from src.models.candidate import Certification, WorkExperience
from src.models.enums import EvidenceSourceType
from src.models.evidence import Evidence
from src.services.profile_validation import validate_profile
from tests.factories import build_candidate


def _evidence(evidence_id="ev-1", confidence=0.9, text="some resume text"):
    return Evidence(
        evidence_id=evidence_id,
        source_type=EvidenceSourceType.RESUME,
        source_section="Work Experience",
        source_text=text,
        confidence=confidence,
    )


def test_valid_profile_has_no_errors():
    candidate = build_candidate()
    result = validate_profile(candidate)

    assert result.valid is True
    assert result.errors == []


def test_impossible_employment_dates_are_an_error():
    candidate = build_candidate(
        work_experience=[
            WorkExperience(
                company="Acme",
                title="Engineer",
                start_date="2022-01",
                end_date="2020-01",
                evidence=[_evidence()],
            )
        ]
    )

    result = validate_profile(candidate)

    assert result.valid is False
    assert any("impossible_employment_dates" in e for e in result.errors)


def test_years_experience_far_exceeding_timeline_is_a_warning_not_an_error():
    candidate = build_candidate(
        years_experience=20,
        work_experience=[
            WorkExperience(
                company="Acme",
                title="Engineer",
                start_date="2021-01",
                end_date="2023-01",
                evidence=[_evidence()],
            )
        ],
    )

    result = validate_profile(candidate)

    assert result.valid is True
    assert any("years_experience_exceeds_timeline" in w for w in result.warnings)


def test_unsupported_skill_with_no_evidence_is_a_warning():
    from src.models.candidate import Skill

    candidate = build_candidate(skills=[Skill(name="Python", evidence=[])])

    result = validate_profile(candidate)

    assert any("unsupported_skill_no_evidence" in w for w in result.warnings)


def test_duplicate_evidence_id_is_an_error():
    from src.models.candidate import Skill

    shared_evidence = _evidence(evidence_id="ev-dup")
    candidate = build_candidate(
        skills=[
            Skill(name="Python", evidence=[shared_evidence]),
            Skill(name="SQL", evidence=[shared_evidence]),
        ]
    )

    result = validate_profile(candidate)

    assert result.valid is False
    assert any("duplicate_evidence_id" in e for e in result.errors)


def test_low_confidence_evidence_is_a_warning():
    from src.models.candidate import Skill

    candidate = build_candidate(skills=[Skill(name="Python", evidence=[_evidence(confidence=0.2)])])

    result = validate_profile(candidate)

    assert any("low_confidence_evidence" in w for w in result.warnings)


def test_work_experience_missing_dates_is_a_warning():
    candidate = build_candidate(
        work_experience=[
            WorkExperience(company="Acme", title="Engineer", start_date=None, end_date=None, evidence=[_evidence()])
        ]
    )

    result = validate_profile(candidate)

    assert any("work_experience_missing_dates" in w for w in result.warnings)


def test_conversion_warnings_are_preserved_in_result():
    candidate = build_candidate()
    result = validate_profile(candidate, conversion_warnings=["dropped a project entry with missing name: 'x'"])

    assert "dropped a project entry with missing name: 'x'" in result.warnings
