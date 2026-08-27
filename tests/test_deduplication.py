from src.services.deduplication import DUPLICATE_CONFIDENCE_THRESHOLD, check_duplicate, dedupe_jobs
from tests.factories import LONG_DESCRIPTION, build_job


def test_exact_duplicate_same_url_is_very_high_confidence():
    original = build_job(job_id="j1", url="https://boards.example.com/jobs/123")
    repost = build_job(job_id="j2", url="https://boards.example.com/jobs/123?utm_source=linkedin")

    result = check_duplicate(repost, [original])

    assert result.is_duplicate is True
    assert result.confidence >= 0.95
    assert result.matched_job_id == "j1"


def test_same_company_title_location_different_url_is_likely_duplicate():
    original = build_job(job_id="j1", url="https://boardA.example.com/jobs/123")
    other_posting = build_job(job_id="j2", url="https://boardB.example.com/jobs/456")

    result = check_duplicate(other_posting, [original])

    assert result.is_duplicate is True
    assert 0.80 <= result.confidence < 0.95
    assert any("different or missing url" in r.lower() or "url" in r.lower() for r in result.reasons)


def test_similar_title_different_company_is_not_duplicate():
    original = build_job(job_id="j1", company="Acme Inc.", url="https://a.example.com/jobs/1")
    other_company = build_job(job_id="j2", company="Globex Corp", url="https://b.example.com/jobs/2")

    result = check_duplicate(other_company, [original])

    assert result.is_duplicate is False
    assert result.confidence < DUPLICATE_CONFIDENCE_THRESHOLD
    assert any("different company" in r for r in result.reasons)


def test_same_company_clearly_different_role_is_not_duplicate():
    original = build_job(
        job_id="j1",
        title="Senior AI Engineer",
        description=LONG_DESCRIPTION,
        url="https://a.example.com/jobs/1",
    )
    different_role = build_job(
        job_id="j2",
        title="Enterprise Account Executive",
        description="Own the full sales cycle for our largest enterprise accounts, from prospecting to close.",
        url="https://a.example.com/jobs/2",
    )

    result = check_duplicate(different_role, [original])

    assert result.is_duplicate is False
    assert any("different role" in r for r in result.reasons)


def test_dedupe_jobs_removes_exact_duplicates_and_keeps_first():
    original = build_job(job_id="j1", url="https://boards.example.com/jobs/123")
    duplicate = build_job(job_id="j2", url="https://boards.example.com/jobs/123?ref=xyz")
    distinct = build_job(job_id="j3", title="Data Analyst", company="Globex", url="https://x.example.com/1")

    kept, log = dedupe_jobs([original, duplicate, distinct])

    kept_ids = {job.job_id for job in kept}
    assert kept_ids == {"j1", "j3"}
    assert log["input_count"] == 3
    assert log["kept_count"] == 2
    assert log["removed_count"] == 1
    assert log["removed"][0]["job_id"] == "j2"
    assert log["removed"][0]["matched_job_id"] == "j1"


def test_dedupe_jobs_with_no_candidates_keeps_everything():
    a = build_job(job_id="j1", title="Backend Engineer", company="Acme", url="https://a.example.com")
    b = build_job(job_id="j2", title="Data Analyst", company="Globex", url="https://b.example.com")

    kept, log = dedupe_jobs([a, b])

    assert len(kept) == 2
    assert log["removed_count"] == 0
