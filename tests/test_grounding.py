from src.agents.grounding import build_grounded_vocabulary, filter_ungrounded_claims, salary_context
from src.models.candidate import Skill
from tests.factories import build_candidate, build_job


def test_grounded_vocabulary_includes_candidate_and_job_skills():
    candidate = build_candidate(skills=[Skill(name="Python")])
    job = build_job(required_skills=["Kubernetes"], preferred_skills=["Docker"])

    vocab = build_grounded_vocabulary(candidate, job)

    assert "python" in vocab
    assert "kubernetes" in vocab
    assert "docker" in vocab


def test_filter_drops_claims_mentioning_ungrounded_skills():
    vocab = {"python"}
    lines = ["Candidate has Python experience.", "Candidate has Kubernetes experience."]

    kept, dropped = filter_ungrounded_claims(lines, vocab)

    assert kept == ["Candidate has Python experience."]
    assert dropped == ["Candidate has Kubernetes experience."]


def test_filter_keeps_claims_with_no_known_skill_terms_at_all():
    vocab = {"python"}
    lines = ["This role has a generous benefits package."]

    kept, dropped = filter_ungrounded_claims(lines, vocab)

    assert kept == lines
    assert dropped == []


def test_salary_context_omitted_when_job_states_no_salary():
    job = build_job(salary_min=None, salary_max=None)
    assert salary_context(job) is None


def test_salary_context_included_only_when_job_states_a_salary():
    job = build_job(salary_min=100_000, salary_max=150_000)
    context = salary_context(job)
    assert context == {"salary_min": 100_000, "salary_max": 150_000}
