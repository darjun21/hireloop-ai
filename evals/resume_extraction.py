"""
Category 1: Resume Extraction.

Feeds real resume texts through the real Profile Agent (src/agents/
profile_agent.py) backed by the deterministic Mock LLM provider, and
checks that expected skills/sections come out the other side -- and that
skills never mentioned anywhere do NOT get invented.

Reuses tests/resume_fixtures.py rather than reinventing resume text.
"""

from __future__ import annotations

from src.agents.profile_agent import ProfileAgent, ProfilePreferences
from src.llm.client import LLMClient
from src.llm.mock_provider import MockLLMProvider
from evals.common import CategorySummary, EvalCase, summarize
from tests import resume_fixtures as fx

CATEGORY = "resume_extraction"


def _skill_names(profile) -> set[str]:
    return {s.name.lower() for s in profile.skills}


def _agent() -> ProfileAgent:
    return ProfileAgent(llm_client=LLMClient(primary=MockLLMProvider()))


def run() -> CategorySummary:
    agent = _agent()
    cases: list[EvalCase] = []

    scenarios = [
        (
            "well_structured_engineer",
            fx.WELL_STRUCTURED_ENGINEER,
            {"python", "postgresql", "aws", "docker", "kafka"},  # kafka comes from the Projects section
            set(),
            2,  # work experience entries
            1,  # certifications
        ),
        (
            "langchain_skills",
            fx.LANGCHAIN_SKILLS,
            {"python", "langchain", "aws"},
            set(),
            1,
            0,
        ),
        (
            "no_kubernetes",
            fx.NO_KUBERNETES,
            {"python", "tensorflow"},
            {"kubernetes"},
            1,
            0,
        ),
        (
            "skill_only_in_project",
            fx.SKILL_ONLY_IN_PROJECT,
            {"python", "postgresql", "kafka"},
            set(),
            1,
            0,
        ),
        (
            "aws_skills_only",
            fx.AWS_SKILLS_ONLY,
            {"python", "aws"},
            set(),
            1,
            0,
        ),
        (
            "skill_aliases",
            fx.SKILL_ALIASES_RESUME,
            {"postgresql", "javascript", "kubernetes"},  # normalized from Postgres/JS/K8s
            set(),
            1,
            0,
        ),
    ]

    for name, text, expected_present, expected_absent, min_work_exp, min_certs in scenarios:
        profile, validation = agent.build_profile(text, candidate_id=f"cand-{name}", preferences=ProfilePreferences())
        found = _skill_names(profile)

        missing = sorted(s for s in expected_present if s not in found)
        unexpected = sorted(s for s in expected_absent if s in found)
        work_ok = len(profile.work_experience) >= min_work_exp
        certs_ok = len(profile.certifications) >= min_certs

        passed = not missing and not unexpected and work_ok and certs_ok
        detail = (
            f"skills_found={sorted(found)} missing={missing} unexpected={unexpected} "
            f"work_experience={len(profile.work_experience)} (min {min_work_exp}) "
            f"certifications={len(profile.certifications)} (min {min_certs})"
        )
        cases.append(EvalCase(id=f"extraction:{name}", category=CATEGORY, passed=passed, detail=detail))

    # Every extracted skill/work/project/certification must carry evidence
    # with a non-empty source_text -- extraction must never invent a fact
    # with no textual grounding.
    profile, _ = agent.build_profile(fx.WELL_STRUCTURED_ENGINEER, candidate_id="cand-evidence-check")
    all_evidenced = all(skill.evidence and all(e.source_text.strip() for e in skill.evidence) for skill in profile.skills)
    cases.append(
        EvalCase(
            id="extraction:every_skill_has_grounded_evidence",
            category=CATEGORY,
            passed=all_evidenced,
            detail="every extracted skill must carry at least one Evidence record with non-empty source_text",
        )
    )

    return summarize(CATEGORY, cases)


if __name__ == "__main__":
    result = run()
    print(result.to_dict())
