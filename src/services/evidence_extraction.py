"""
Deterministic evidence extraction/chunk preparation from a CandidateProfile.

Flattens the Evidence records already attached across skills, work
experience, education, projects, and certifications into one deduplicated
list, ready for indexing (src/services/vector_service.py) or local search
(src/services/local_evidence_search.py). No LLM.
"""

from __future__ import annotations

from src.models.candidate import CandidateProfile
from src.models.evidence import Evidence


def extract_evidence_chunks(profile: CandidateProfile) -> list[Evidence]:
    """Every distinct Evidence record on the profile, stamped with
    candidate_id, deduplicated by evidence_id. Never mutates the profile."""
    chunks: dict[str, Evidence] = {}

    def _add(evidence_list: list[Evidence]) -> None:
        for evidence in evidence_list:
            if evidence.evidence_id in chunks:
                continue
            stamped = evidence if evidence.candidate_id else evidence.model_copy(update={"candidate_id": profile.candidate_id})
            chunks[evidence.evidence_id] = stamped

    for skill in profile.skills:
        _add(skill.evidence)
    for experience in profile.work_experience:
        _add(experience.evidence)
    for education in profile.education:
        _add(education.evidence)
    for project in profile.projects:
        _add(project.evidence)
    for certification in profile.certifications:
        _add(certification.evidence)
    _add(profile.source_evidence)

    return list(chunks.values())
