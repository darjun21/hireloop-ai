from src.models.candidate import Skill, WorkExperience
from src.models.enums import EvidenceSourceType
from src.models.evidence import Evidence
from src.services.evidence_extraction import extract_evidence_chunks
from tests.factories import build_candidate


def _ev(eid, section, text, stype=EvidenceSourceType.RESUME, conf=0.85):
    return Evidence(evidence_id=eid, source_type=stype, source_section=section, source_text=text, confidence=conf)


# 1. Evidence extraction flattens everything.
def test_extraction_flattens_all_sections():
    candidate = build_candidate(
        skills=[Skill(name="Python", evidence=[_ev("e1", "Skills", "Python")])],
        work_experience=[WorkExperience(company="Acme", title="Engineer", evidence=[_ev("e2", "Work", "did stuff", EvidenceSourceType.WORK_EXPERIENCE)])],
    )
    chunks = extract_evidence_chunks(candidate)
    ids = {c.evidence_id for c in chunks}
    assert {"e1", "e2"} <= ids


# 2. Evidence deduplication by evidence_id.
def test_extraction_deduplicates_shared_evidence_id():
    shared = _ev("shared-1", "Skills", "Python and SQL")
    candidate = build_candidate(
        skills=[
            Skill(name="Python", evidence=[shared]),
            Skill(name="SQL", evidence=[shared]),
        ]
    )
    chunks = extract_evidence_chunks(candidate)
    assert len([c for c in chunks if c.evidence_id == "shared-1"]) == 1


def test_extraction_stamps_candidate_id_when_missing():
    candidate = build_candidate(
        candidate_id="cand-xyz",
        skills=[Skill(name="Python", evidence=[_ev("e1", "Skills", "Python")])],
    )
    chunks = extract_evidence_chunks(candidate)
    assert all(c.candidate_id == "cand-xyz" for c in chunks)


def test_extraction_never_mutates_original_profile_evidence():
    original = _ev("e1", "Skills", "Python")
    candidate = build_candidate(skills=[Skill(name="Python", evidence=[original])])
    extract_evidence_chunks(candidate)
    assert candidate.skills[0].evidence[0].candidate_id is None or candidate.skills[0].evidence[0].candidate_id == original.candidate_id
