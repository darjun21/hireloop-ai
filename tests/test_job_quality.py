from src.models.enums import JobQualityRecommendation
from src.services.job_quality import score_job_quality
from tests.factories import LONG_DESCRIPTION, build_job


def test_well_formed_job_is_valid():
    job = build_job()
    result = score_job_quality(job)

    assert result.quality_score == 100
    assert result.flags == []
    assert result.recommendation == JobQualityRecommendation.VALID


def test_missing_salary_is_never_penalized():
    with_salary = score_job_quality(build_job(salary_min=100_000, salary_max=150_000))
    without_salary = score_job_quality(build_job(salary_min=None, salary_max=None))

    assert with_salary.quality_score == without_salary.quality_score
    assert "missing_salary" not in without_salary.flags
    assert without_salary.recommendation == JobQualityRecommendation.VALID


def test_missing_description_is_flagged_and_low_quality():
    job = build_job(description=None)
    result = score_job_quality(job)

    assert "missing_description" in result.flags
    assert result.recommendation == JobQualityRecommendation.LOW_QUALITY


def test_missing_company_is_flagged_and_low_quality():
    job = build_job(company="")
    result = score_job_quality(job)

    assert "missing_company" in result.flags
    assert result.recommendation == JobQualityRecommendation.LOW_QUALITY


def test_vague_title_is_flagged():
    job = build_job(title="Various")
    result = score_job_quality(job)

    assert "vague_title" in result.flags
    assert result.recommendation != JobQualityRecommendation.VALID


def test_suspicious_url_is_flagged():
    job = build_job(url="not-a-real-url")
    result = score_job_quality(job)

    assert "suspicious_url" in result.flags


def test_short_description_is_flagged_but_not_critical():
    job = build_job(description="Great opportunity, apply now for this exciting role at our company.")
    result = score_job_quality(job)

    assert "short_description" in result.flags
    assert result.recommendation != JobQualityRecommendation.LOW_QUALITY


def test_boilerplate_heavy_description_is_flagged():
    boilerplate = ("apply now apply now apply now " * 30).strip()
    job = build_job(description=boilerplate)
    result = score_job_quality(job)

    assert "boilerplate_heavy" in result.flags


def test_quality_score_never_goes_below_zero():
    job = build_job(
        company="",
        description=None,
        title="N/A",
        url="not-a-real-url",
    )
    result = score_job_quality(job)

    assert 0 <= result.quality_score <= 100
    assert result.recommendation == JobQualityRecommendation.LOW_QUALITY


def test_deduplication_status_not_part_of_quality():
    # score_job_quality never sees a pool of other jobs; it has no way to
    # flag duplication, by construction.
    import inspect

    from src.services.job_quality import score_job_quality as fn

    params = inspect.signature(fn).parameters
    assert list(params.keys()) == ["job"]
