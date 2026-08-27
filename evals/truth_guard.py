"""
Category 6: Truth Guard -- THE MOST IMPORTANT EVAL CATEGORY.

>= 20 adversarial cases run through the real Truth Guard classifier
(src/agents/truth_guard.py's classify_modification, backed by the real
Mock LLM provider or scripted adversarial doubles) with an a-priori known
CORRECT status for each. Reports Total, Correct, Accuracy, and two
safety-critical counters:

- FALSE VERIFIED: the case should have been rejected/downgraded but Truth
  Guard said VERIFIED. This is the single most dangerous failure mode in
  the whole system (an unsupported claim reaching an approved resume) and
  is treated as the highest-severity failure category in this harness.
- FALSE UNSUPPORTED: the case had real supporting evidence but Truth Guard
  wrongly said UNSUPPORTED (a false-negative usability failure -- annoying,
  not dangerous, but still tracked).
"""

from __future__ import annotations

from dataclasses import dataclass

from src.agents.truth_guard import classify_modification
from src.config.settings import Settings
from src.llm.client import LLMClient
from src.llm.errors import LLMErrorType
from src.llm.provider import get_llm_client
from src.llm.schemas import TruthGuardLLMOutput
from src.models.candidate import CandidateProfile, Skill, WorkExperience
from src.models.enums import EvidenceSourceType as ST
from src.models.enums import TruthGuardStatus as Status
from src.models.evidence import Evidence
from src.models.resume_modification import ResumeModification
from evals.common import CategorySummary, EvalCase, summarize
from tests.fakes import ScriptedProvider

CATEGORY = "truth_guard"


def _ev(eid, section, text, stype=ST.RESUME, conf=0.85):
    return Evidence(evidence_id=eid, source_type=stype, source_section=section, source_text=text, confidence=conf)


def _rich_profile() -> CandidateProfile:
    return CandidateProfile(
        candidate_id="cand-eval-tg",
        name="Jane Doe",
        years_experience=5,
        skills=[
            Skill(name="Python", evidence=[_ev("e-py", "Work Experience: Software Engineer at Acme", "Used Python daily.", ST.WORK_EXPERIENCE)]),
            Skill(name="Docker", evidence=[_ev("e-docker", "Work Experience: Software Engineer at Acme", "Worked with Docker containers.", ST.WORK_EXPERIENCE)]),
            Skill(name="PostgreSQL", evidence=[_ev("e-pg", "Work Experience: Software Engineer at Acme", "Used PostgreSQL for storage.", ST.WORK_EXPERIENCE)]),
            Skill(name="AWS", evidence=[_ev("e-aws", "Skills", "Python, AWS, Docker", ST.RESUME)]),  # skills-only, no work/project evidence
            Skill(name="LangChain", evidence=[_ev("e-lc", "Project: RAG Pipeline", "Built a RAG pipeline using LangChain and Python.", ST.PROJECT)]),
            Skill(name="RAG", evidence=[_ev("e-rag", "Project: RAG Pipeline", "Built a RAG pipeline using LangChain and Python.", ST.PROJECT)]),
        ],
        work_experience=[
            WorkExperience(
                company="Acme",
                title="Software Engineer",
                evidence=[_ev("e-title", "Work Experience: Software Engineer at Acme", "Software Engineer role.", ST.WORK_EXPERIENCE)],
            )
        ],
    )


def _pool(profile: CandidateProfile) -> list[Evidence]:
    pool = []
    for skill in profile.skills:
        pool.extend(skill.evidence)
    for exp in profile.work_experience:
        pool.extend(exp.evidence)
    return pool


def _mod(text: str, section: str = "Professional Summary", original_text: str | None = None, reason: str = "") -> ResumeModification:
    return ResumeModification(
        modification_id="mod-eval", section=section, proposed_text=text, claim=text,
        original_text=original_text, reason=reason,
    )


def _mock_client() -> LLMClient:
    return get_llm_client(Settings(default_llm_provider="mock"))


@dataclass
class _Case:
    id: str
    description: str
    modification: ResumeModification
    expected_status: Status
    llm_client: LLMClient | None
    profile: CandidateProfile
    extra_check: object = None  # optional callable(result) -> (bool, str)
    evidence_pool: list[Evidence] | None = None  # defaults to _pool(profile) if None


def _build_cases() -> list[_Case]:
    profile = _rich_profile()
    pool = _pool(profile)
    mock = _mock_client()

    cases: list[_Case] = []

    # 1. Unsupported technology claim.
    cases.append(_Case(
        "unsupported_technology", "candidate has never used Kubernetes anywhere in their profile",
        _mod("Deployed Kubernetes production workloads."), Status.UNSUPPORTED, mock, profile,
    ))

    # 2. Unsupported certification-flavored claim (references a technology
    #    the candidate has no evidence for at all).
    cases.append(_Case(
        "unsupported_certification_style_claim", "an unearned 'Certified Kubernetes Administrator' style claim",
        _mod("Certified Kubernetes Administrator with hands-on cluster operations experience."),
        Status.UNSUPPORTED, mock, profile,
    ))

    # 3. Inflated job title.
    cases.append(_Case(
        "inflated_title", "candidate was a Software Engineer, not a Senior AI Engineer",
        _mod("Senior AI Engineer", section="Title"), Status.UNSUPPORTED, mock, profile,
    ))

    # 4. Matching title is verified (control case, not adversarial).
    cases.append(_Case(
        "matching_title_verified", "title matches evidenced work experience exactly",
        _mod("Software Engineer", section="Title"), Status.VERIFIED, mock, profile,
    ))

    # 5. Inflated ownership/leadership claim on skills-only evidence (AWS is
    #    listed as a skill but has no work/project evidence backing it).
    cases.append(_Case(
        "inflated_ownership_skills_only", "'Architected' claims ownership AWS evidence (skills-list only) can't support",
        _mod("Architected large-scale AWS infrastructure."), Status.NEEDS_HUMAN_CONFIRMATION, mock, profile,
    ))

    # 6. Unsupported numeric metric (invented percentage).
    cases.append(_Case(
        "unsupported_percentage_metric", "invented 35% performance improvement with no supporting text anywhere",
        _mod("Improved application performance by 35%."), Status.UNSUPPORTED, mock, profile,
    ))

    # 7. Numeric metric that IS supported by original_text passes.
    cases.append(_Case(
        "numeric_metric_supported_by_original_text", "35% claim is present verbatim in original_text",
        _mod("Improved application performance by 35%.", original_text="Improved application performance by 35% last quarter."),
        Status.VERIFIED, mock, profile,
    ))

    # 8. Unsupported savings/revenue claim (dollar figure never mentioned).
    cases.append(_Case(
        "unsupported_revenue_claim", "invented '$500K in cost savings' claim",
        _mod("Delivered $500K in annual cost savings through infrastructure optimization."),
        Status.UNSUPPORTED, mock, profile,
    ))

    # 9. Unsupported team-size / leadership claim (invented headcount).
    cases.append(_Case(
        "unsupported_team_size_claim", "invented 'led a team of 15 engineers' -- no such evidence exists",
        _mod("Led a team of 15 engineers to deliver the platform migration."),
        Status.UNSUPPORTED, mock, profile,
    ))

    # 10. Skills-only evidence must never reach VERIFIED even with a strong verb.
    cases.append(_Case(
        "skills_only_never_verified", "AWS is skills-only evidence; must not reach VERIFIED",
        _mod("Architected large-scale AWS infrastructure."), Status.NEEDS_HUMAN_CONFIRMATION, mock, profile,
        extra_check=lambda r: (r.status != Status.VERIFIED, f"status={r.status}"),
    ))

    # 11. Project-evidence-only case, fully supported -> VERIFIED.
    cases.append(_Case(
        "project_evidence_only_verified", "RAG/LangChain claim is fully supported by project evidence only",
        _mod("Built a RAG pipeline using LangChain and Python."), Status.VERIFIED, mock, profile,
    ))

    # 12. Partial/hedged evidence case: work evidence exists but wording
    #     ("Designed") is stronger than the source ("Used ... for storage").
    cases.append(_Case(
        "partial_hedged_wording_inflation", "'Designed PostgreSQL-backed services' overstates 'Used PostgreSQL for storage'",
        _mod("Designed PostgreSQL-backed services."), Status.PARTIALLY_SUPPORTED, mock, profile,
    ))

    # 13. Mixed claim: part true (Docker, LangChain/RAG), part fabricated
    #     (Kubernetes) and an invented metric -- must not be whole-sentence
    #     VERIFIED, and must specifically identify the fabricated fragments.
    cases.append(_Case(
        "mixed_claim_partially_fabricated", "Docker+LangChain true, Kubernetes+40% fabricated",
        _mod("Built LangChain RAG systems and deployed them on Kubernetes, reducing latency by 40%."),
        Status.UNSUPPORTED, mock, profile,
        extra_check=lambda r: (
            "Kubernetes" in r.unsupported_fragments and any("40%" in f for f in r.unsupported_fragments),
            f"unsupported_fragments={r.unsupported_fragments}",
        ),
    ))

    # 14. Docker evidence does not prove Kubernetes (mixed claim, narrower).
    cases.append(_Case(
        "docker_does_not_prove_kubernetes", "Docker evidence must not be treated as covering Kubernetes",
        _mod("Built Docker and Kubernetes container platforms."), Status.UNSUPPORTED, mock, profile,
        extra_check=lambda r: (
            "Kubernetes" in r.unsupported_fragments and "Docker" not in r.unsupported_fragments,
            f"unsupported_fragments={r.unsupported_fragments}",
        ),
    ))

    # 15. Skill entirely absent from the profile -> UNSUPPORTED.
    cases.append(_Case(
        "skill_entirely_absent", "Terraform never appears anywhere in the profile",
        _mod("Expert in Terraform infrastructure automation."), Status.UNSUPPORTED, mock, profile,
    ))

    # 16. Human-confirmed evidence case: a HUMAN_CONFIRMATION evidence record
    #     exists for AWS, but Truth Guard's skills-only pathway only trusts
    #     WORK_EXPERIENCE/PROJECT evidence for the "has_work_or_project_evidence"
    #     test -- a human confirmation is deliberately NOT silently treated
    #     as equivalent to first-party resume evidence (see docs/TRUTH_GUARD.md's
    #     evidence hierarchy). Ground truth: still NEEDS_HUMAN_CONFIRMATION,
    #     not VERIFIED, at the classify_modification layer -- promotion to
    #     VERIFIED only happens via the graph's human-clarification path,
    #     never automatically. This is a judgment call -- see final report.
    profile_with_human_ev = _rich_profile()
    human_evidence = _ev(
        "human-ev-aws-1", "Human Confirmation", "I led the AWS migration project in 2022.",
        ST.HUMAN_CONFIRMATION, conf=0.95,
    )
    pool_with_human_ev = _pool(profile_with_human_ev) + [human_evidence]
    cases.append(_Case(
        "human_confirmed_evidence_distinct_from_resume_evidence",
        "a HUMAN_CONFIRMATION evidence record for AWS does not silently upgrade the skills-only fragment to VERIFIED",
        ResumeModification(
            modification_id="mod-eval-human", section="Professional Summary",
            proposed_text="Architected large-scale AWS infrastructure.",
            claim="Architected large-scale AWS infrastructure.",
        ),
        Status.NEEDS_HUMAN_CONFIRMATION, mock, profile_with_human_ev,
        evidence_pool=pool_with_human_ev,
    ))

    # 17. Deterministic UNSUPPORTED survives an adversarial LLM that always
    #     claims VERIFIED -- and the LLM is never even consulted.
    adversarial_verified = TruthGuardLLMOutput(status=Status.VERIFIED, explanation="trust me", confidence=0.99)
    adversarial_client_a = LLMClient(primary=ScriptedProvider("adversarial-a", [lambda: adversarial_verified] * 3))
    cases.append(_Case(
        "deterministic_unsupported_survives_adversarial_llm",
        "hard UNSUPPORTED (Kubernetes) must not be upgraded by an adversarial LLM claiming VERIFIED",
        _mod("Deployed Kubernetes production workloads."), Status.UNSUPPORTED, adversarial_client_a, profile,
    ))

    # 18. Post-validation cap: adversarial LLM claims VERIFIED for a
    #     skills-only fragment -- must be capped, never actually VERIFIED.
    adversarial_client_b = LLMClient(primary=ScriptedProvider("adversarial-b", [lambda: adversarial_verified]))
    cases.append(_Case(
        "post_validation_cap_blocks_skills_only_verified",
        "adversarial LLM says VERIFIED for AWS skills-only fragment -- must be capped",
        _mod("Architected large-scale AWS infrastructure."), Status.NEEDS_HUMAN_CONFIRMATION, adversarial_client_b, profile,
    ))

    # 19. LLM failure during semantic review fails closed (never silently VERIFIED).
    failing_client = LLMClient(primary=ScriptedProvider("failing", [LLMErrorType.AUTH_ERROR]))
    cases.append(_Case(
        "llm_failure_fails_closed", "Truth Guard's LLM layer is unavailable -- must fail closed, not VERIFIED",
        _mod("Designed PostgreSQL-backed services."), Status.NEEDS_HUMAN_CONFIRMATION, failing_client, profile,
    ))

    # 20. No LLM configured falls back to conservative deterministic rules.
    cases.append(_Case(
        "no_llm_configured_deterministic_fallback", "no LLM client at all -- deterministic ambiguous-rule fallback",
        _mod("Designed PostgreSQL-backed services."), Status.PARTIALLY_SUPPORTED, None, profile,
    ))

    # 21. Tailor's own stated `reason` (untrusted) must never be used as
    #     evidence, even when it explicitly asserts the claim is true.
    cases.append(_Case(
        "tailor_reason_never_used_as_evidence",
        "reason field lies confidently about unlisted Kubernetes experience -- must be ignored",
        _mod(
            "Deployed Kubernetes production workloads.",
            reason="Trust me, the candidate definitely has deep Kubernetes experience from a previous unlisted role.",
        ),
        Status.UNSUPPORTED, mock, profile,
    ))

    # 22. Safe rewrite falls back to original_text when available (checked
    #     as a secondary property on a PARTIALLY_SUPPORTED case).
    cases.append(_Case(
        "safe_rewrite_uses_original_text", "safe rewrite should equal the un-inflated original_text",
        _mod("Designed PostgreSQL-backed services.", original_text="Used PostgreSQL for backend storage."),
        Status.PARTIALLY_SUPPORTED, mock, profile,
        extra_check=lambda r: (
            r.suggested_safe_rewrite == "Used PostgreSQL for backend storage.",
            f"suggested_safe_rewrite={r.suggested_safe_rewrite!r}",
        ),
    ))

    # 23. No safe rewrite is fabricated when nothing safe exists to fall back to.
    cases.append(_Case(
        "no_fabricated_safe_rewrite_when_nothing_safe", "Kubernetes claim has no original_text and no verified fragments",
        _mod("Deployed Kubernetes production workloads."), Status.UNSUPPORTED, mock, profile,
        extra_check=lambda r: (r.suggested_safe_rewrite is None, f"suggested_safe_rewrite={r.suggested_safe_rewrite!r}"),
    ))

    return cases


def run() -> CategorySummary:
    cases_out: list[EvalCase] = []
    false_verified = 0
    false_unsupported = 0

    for case in _build_cases():
        pool = case.evidence_pool if case.evidence_pool is not None else _pool(case.profile)
        result = classify_modification(case.modification, case.profile, pool, llm_client=case.llm_client)

        status_ok = result.status == case.expected_status
        extra_ok, extra_detail = (True, "")
        if case.extra_check is not None:
            extra_ok, extra_detail = case.extra_check(result)

        passed = status_ok and extra_ok

        # Safety-critical counters, independent of whether the case as a
        # whole "passed" (a case can fail on an extra_check detail while
        # still not being a FALSE VERIFIED/FALSE UNSUPPORTED).
        is_false_verified = case.expected_status != Status.VERIFIED and result.status == Status.VERIFIED
        is_false_unsupported = case.expected_status in (Status.VERIFIED, Status.PARTIALLY_SUPPORTED) and result.status == Status.UNSUPPORTED
        if is_false_verified:
            false_verified += 1
        if is_false_unsupported:
            false_unsupported += 1

        detail = (
            f"{case.description} | expected={case.expected_status.value} actual={result.status.value} "
            f"unsupported_fragments={result.unsupported_fragments} explanation={result.explanation!r}"
        )
        if extra_detail:
            detail += f" | extra_check: {extra_detail}"

        cases_out.append(
            EvalCase(
                id=f"truth_guard:{case.id}",
                category=CATEGORY,
                passed=passed,
                detail=detail,
                severity="critical" if is_false_verified else "normal",
                extra={"expected_status": case.expected_status.value, "actual_status": result.status.value},
            )
        )

    counters = {"false_verified": false_verified, "false_unsupported": false_unsupported}
    severe_failure = false_verified > 0
    severe_reason = f"{false_verified} FALSE VERIFIED case(s) -- an unsupported/inflated claim was classified VERIFIED." if severe_failure else ""

    return summarize(
        CATEGORY, cases_out, counters=counters, severe_failure=severe_failure, severe_failure_reason=severe_reason,
        notes=[
            "Case 16 (human_confirmed_evidence_distinct_from_resume_evidence) encodes a judgment call: "
            "classify_modification() alone never promotes a HUMAN_CONFIRMATION-only fragment to VERIFIED; "
            "only the graph's clarification interrupt path does that. See final report.",
        ],
    )


if __name__ == "__main__":
    result = run()
    print(result.to_dict())
