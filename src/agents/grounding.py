"""
Grounding utilities for the Match Analyst Agent.

Allowed sources for any claim in a MatchAnalysis are ONLY: CandidateProfile,
JobPosting, and OpportunityScore. The agent must not invent external
company facts, infer a salary the job never stated, or claim a candidate
has a skill they don't have evidence for. This module gives it a concrete,
testable way to enforce that instead of relying on prompt wording alone.
"""

from __future__ import annotations

from src.models.candidate import CandidateProfile
from src.models.job import JobPosting
from src.services.normalization import normalize_skill

# A curated vocabulary of skill-like terms the grounding filter watches for.
# This mirrors the mock provider's keyword list (src/llm/mock_provider.py)
# so both sides of the boundary agree on what counts as a "skill claim"
# worth checking.
KNOWN_SKILL_VOCABULARY: tuple[str, ...] = (
    "Python",
    "JavaScript",
    "TypeScript",
    "Java",
    "Go",
    "Rust",
    "SQL",
    "PostgreSQL",
    "MySQL",
    "MongoDB",
    "AWS",
    "Azure",
    "GCP",
    "Docker",
    "Kubernetes",
    "Kafka",
    "React",
    "Node",
    "Django",
    "Flask",
    "Machine Learning",
    "TensorFlow",
    "PyTorch",
    "LangChain",
    "Spark",
    "Terraform",
)


def build_grounded_vocabulary(candidate: CandidateProfile, job: JobPosting) -> set[str]:
    """Every skill term that legitimately appears in either source."""
    terms = {normalize_skill(s.name).lower() for s in candidate.skills}
    terms |= {normalize_skill(s).lower() for s in job.required_skills}
    terms |= {normalize_skill(s).lower() for s in job.preferred_skills}
    return terms


def filter_ungrounded_claims(lines: list[str], grounded_vocabulary: set[str]) -> tuple[list[str], list[str]]:
    """Drop any line that references a known skill term absent from both
    the candidate's profile and the job posting. Returns (kept, dropped)."""
    kept: list[str] = []
    dropped: list[str] = []
    for line in lines:
        lowered = line.lower()
        mentioned = [term for term in KNOWN_SKILL_VOCABULARY if term.lower() in lowered]
        ungrounded = [term for term in mentioned if term.lower() not in grounded_vocabulary]
        if ungrounded:
            dropped.append(line)
        else:
            kept.append(line)
    return kept, dropped


def salary_context(job: JobPosting) -> dict[str, float] | None:
    """Only include salary in a prompt's context if the job actually stated
    one — never let the model infer or fill in a salary figure."""
    if job.salary_min is None and job.salary_max is None:
        return None
    return {"salary_min": job.salary_min, "salary_max": job.salary_max}
