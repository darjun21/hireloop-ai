"""
Deterministic job-requirement extraction. No NLP/LLM — a job's
requirements are already structured data (required_skills,
preferred_skills, minimum_years_experience); this just flattens them into
one ordered list of requirement strings for evidence retrieval.
"""

from __future__ import annotations

from src.models.job import JobPosting


def extract_job_requirements(job: JobPosting) -> list[str]:
    requirements = list(job.required_skills) + list(job.preferred_skills)
    if job.minimum_years_experience is not None:
        years = job.minimum_years_experience
        formatted = f"{years:g}"
        requirements.append(f"{formatted}+ years experience")
    return requirements
