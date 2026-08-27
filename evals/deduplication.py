"""
Category 2: Deduplication.

Feeds job batches with known exact and near-duplicate postings through the
real deterministic dedup service (src/services/deduplication.py) and
verifies it keeps the right jobs and removes the right ones.
"""

from __future__ import annotations

from src.services.deduplication import check_duplicate, dedupe_jobs
from evals.common import CategorySummary, EvalCase, summarize
from tests.factories import build_job

CATEGORY = "deduplication"


def run() -> CategorySummary:
    cases: list[EvalCase] = []

    # 1. Exact duplicate (identical canonicalized URL) is removed.
    a = build_job(job_id="j1", url="https://boards.example.com/jobs/123")
    b = build_job(job_id="j2", url="https://boards.example.com/jobs/123?utm_source=linkedin")
    kept, log = dedupe_jobs([a, b])
    passed = [j.job_id for j in kept] == ["j1"] and log["removed_count"] == 1
    cases.append(EvalCase("dedup:exact_url_duplicate_removed", CATEGORY, passed, detail=str(log)))

    # 2. Same company/title/location, different URL -> near-duplicate, removed.
    c = build_job(job_id="j3", url="https://boards.example.com/jobs/999")
    d = build_job(job_id="j4", url="https://other-boards.example.com/postings/abc", company="Acme Inc")
    kept, log = dedupe_jobs([c, d])
    passed = [j.job_id for j in kept] == ["j3"] and log["removed_count"] == 1
    cases.append(EvalCase("dedup:same_company_title_location_removed", CATEGORY, passed, detail=str(log)))

    # 3. Same title, different company -> NOT a duplicate (kept both).
    e = build_job(job_id="j5", title="Sr. AI Engineer", company="Acme Inc.", url="https://a.example.com/1")
    f = build_job(job_id="j6", title="Sr. AI Engineer", company="Globex Corp", url="https://b.example.com/1")
    kept, log = dedupe_jobs([e, f])
    passed = {j.job_id for j in kept} == {"j5", "j6"} and log["removed_count"] == 0
    cases.append(EvalCase("dedup:same_title_different_company_kept", CATEGORY, passed, detail=str(log)))

    # 4. Same company, clearly different role and description -> kept.
    g = build_job(job_id="j7", title="Sr. AI Engineer", company="Acme Inc.", url="https://a.example.com/2")
    h = build_job(
        job_id="j8",
        title="Recruiter",
        company="Acme Inc.",
        url="https://a.example.com/3",
        description="We are hiring a technical recruiter to source and screen candidates across engineering teams.",
        required_skills=[],
        preferred_skills=[],
    )
    kept, log = dedupe_jobs([g, h])
    passed = {j.job_id for j in kept} == {"j7", "j8"} and log["removed_count"] == 0
    cases.append(EvalCase("dedup:same_company_different_role_kept", CATEGORY, passed, detail=str(log)))

    # 5. Same company, different title, near-identical description: the
    #    pairwise comparator recognizes this as a plausible-repost signal
    #    (confidence 0.65, reasons mention "near-identical description")
    #    but 0.65 sits below DUPLICATE_CONFIDENCE_THRESHOLD (0.70), so it is
    #    correctly NOT auto-removed -- a human/near-miss case, not an
    #    auto-dedup case. This asserts that boundary behavior precisely.
    i = build_job(job_id="j9", title="Software Engineer II", company="Acme Inc.", url="https://a.example.com/4")
    j = build_job(
        job_id="j10", title="Software Engineer 2", company="Acme Inc.", url="https://a.example.com/5",
        description=i.description,
    )
    result = check_duplicate(j, [i])
    passed = (
        not result.is_duplicate
        and 0.6 <= result.confidence < 0.70
        and any("description" in r for r in result.reasons)
    )
    cases.append(
        EvalCase(
            "dedup:near_identical_description_below_threshold_not_auto_removed",
            CATEGORY,
            passed,
            detail=f"confidence={result.confidence} reasons={result.reasons}",
        )
    )

    # 6. Batch-level accounting: input_count == kept_count + removed_count, always.
    batch = [
        build_job(job_id=f"batch-{n}", url=f"https://batch.example.com/{n % 3}") for n in range(6)
    ]
    kept, log = dedupe_jobs(batch)
    passed = log["input_count"] == 6 and log["kept_count"] + log["removed_count"] == 6 and len(kept) == log["kept_count"]
    cases.append(EvalCase("dedup:batch_accounting_consistent", CATEGORY, passed, detail=str(log)))

    return summarize(CATEGORY, cases)


if __name__ == "__main__":
    result = run()
    print(result.to_dict())
