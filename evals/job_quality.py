"""
Category 3: Job Quality.

Feeds jobs with sparse vs. rich descriptions through the real deterministic
job quality service (src/services/job_quality.py) and verifies sparse
listings are correctly flagged (LOW requirement_completeness, NEEDS_REVIEW/
LOW_QUALITY) while well-formed rich listings are not penalized.
"""

from __future__ import annotations

from src.models.enums import JobQualityRecommendation, WorkMode
from src.services.job_quality import score_job_quality
from evals.common import CategorySummary, EvalCase, summarize
from tests.factories import build_job

CATEGORY = "job_quality"


def run() -> CategorySummary:
    cases: list[EvalCase] = []

    # 1. Rich, well-formed listing: no flags, HIGH completeness, VALID.
    rich = build_job(job_id="rich-1")
    result = score_job_quality(rich)
    passed = (
        result.flags == []
        and result.requirement_completeness == "HIGH"
        and result.recommendation == JobQualityRecommendation.VALID
        and result.quality_score == 100.0
    )
    cases.append(EvalCase("job_quality:rich_listing_not_penalized", CATEGORY, passed, detail=str(result)))

    # 2. Sparse listing: no required skills, no min years, very short description.
    sparse = build_job(
        job_id="sparse-1",
        description="Join our team.",
        required_skills=[],
        preferred_skills=[],
        minimum_years_experience=None,
        employment_type=None,
    )
    result = score_job_quality(sparse)
    passed = (
        result.requirement_completeness == "LOW"
        and "sparse_requirements" in result.flags
        and result.recommendation in (JobQualityRecommendation.NEEDS_REVIEW, JobQualityRecommendation.LOW_QUALITY)
        and result.quality_score < 100.0
    )
    cases.append(EvalCase("job_quality:sparse_listing_flagged", CATEGORY, passed, detail=str(result)))

    # 3. Missing company/description -> critical flags -> LOW_QUALITY.
    broken = build_job(job_id="broken-1", company="", description="")
    result = score_job_quality(broken)
    passed = (
        "missing_company" in result.flags
        and "missing_description" in result.flags
        and result.recommendation == JobQualityRecommendation.LOW_QUALITY
    )
    cases.append(EvalCase("job_quality:missing_critical_fields_low_quality", CATEGORY, passed, detail=str(result)))

    # 4. Vague title flagged.
    vague = build_job(job_id="vague-1", title="Job")
    result = score_job_quality(vague)
    passed = "vague_title" in result.flags
    cases.append(EvalCase("job_quality:vague_title_flagged", CATEGORY, passed, detail=str(result)))

    # 5. Location/work-mode conflict flagged (REMOTE work mode, onsite-only location text).
    conflict = build_job(job_id="conflict-1", work_mode=WorkMode.REMOTE, location="Onsite in Austin, TX")
    result = score_job_quality(conflict)
    passed = "location_work_mode_conflict" in result.flags
    cases.append(EvalCase("job_quality:location_work_mode_conflict_flagged", CATEGORY, passed, detail=str(result)))

    # 6. Salary is never penalized -- a listing missing salary but otherwise
    #    rich must still score as well as one that specifies it.
    no_salary = build_job(job_id="no-salary-1")
    with_salary = build_job(job_id="with-salary-1", salary_min=100000, salary_max=150000)
    r_no_salary = score_job_quality(no_salary)
    r_with_salary = score_job_quality(with_salary)
    passed = r_no_salary.quality_score == r_with_salary.quality_score == 100.0
    cases.append(
        EvalCase(
            "job_quality:missing_salary_never_penalized",
            CATEGORY,
            passed,
            detail=f"no_salary_score={r_no_salary.quality_score} with_salary_score={r_with_salary.quality_score}",
        )
    )

    # 7. Boilerplate-heavy long description flagged (low unique-word ratio).
    boilerplate_desc = ("Great opportunity great team great culture. " * 20).strip()
    boilerplate = build_job(job_id="boilerplate-1", description=boilerplate_desc)
    result = score_job_quality(boilerplate)
    passed = "boilerplate_heavy" in result.flags
    cases.append(EvalCase("job_quality:boilerplate_heavy_flagged", CATEGORY, passed, detail=str(result)))

    return summarize(CATEGORY, cases)


if __name__ == "__main__":
    result = run()
    print(result.to_dict())
