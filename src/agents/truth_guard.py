"""
Truth Guard Agent — hybrid deterministic + agentic verification.

Three layers, in order:

1. Deterministic pre-checks (always run, never call an LLM): unsupported
   numeric metrics, entirely-missing technologies, job-title inflation,
   and the clear-cut end of skill verification (a skill either isn't in
   the candidate's profile at all, or is grounded in work/project evidence
   with wording no stronger than the evidence itself). These are cheap,
   fully auditable, and don't need semantic judgment.

2. LLM semantic reasoning — invoked ONLY for the genuinely ambiguous
   remainder: wording that escalates evidenced work into stronger
   ownership/leadership language ("used" -> "designed"), or a skill that
   appears only in a bare Skills list with no work/project context. This
   is where real semantic judgment (is "developed" close enough to
   "built"? does listing a skill imply hands-on ownership?) belongs — and
   where a second LLM pass earns its cost, unlike the clear-cut cases
   above, which don't need one.

3. Deterministic post-validation (fail-closed): the LLM's output can never
   upgrade a fragment layer 1 already ruled UNSUPPORTED, and can never
   mark a skills-only fragment (no work/project evidence at all) VERIFIED
   — at best NEEDS_HUMAN_CONFIRMATION. If the LLM call itself fails
   (timeout, rate limit, malformed output) after the provider layer's own
   retry/fallback is exhausted, every fragment that needed it is forced to
   NEEDS_HUMAN_CONFIRMATION, never silently treated as VERIFIED.

Truth Guard MUST NOT reuse Resume Tailor's stated `reason` or
`targeted_job_requirement` as evidence — only the candidate's
CandidateProfile and its attached Evidence records are ever consulted.
See docs/TRUTH_GUARD.md for the full rationale and evidence hierarchy.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from src.llm.client import LLMClient
from src.llm.errors import HireLoopLLMError
from src.llm.schemas import TruthGuardLLMOutput
from src.models.candidate import CandidateProfile
from src.models.enums import TruthGuardStatus as ClaimStatus
from src.models.evidence import Evidence
from src.models.resume_modification import ResumeModification
from src.models.truth_guard import TruthGuardResult

# Verbs that assert ownership/authority beyond simple usage. A claim using
# one of these for a skill whose only evidence is a bare Skills-section
# listing (no work/project context) cannot be safely judged either way by
# rule alone -- that's exactly what layer 2 (LLM) exists for.
_STRONG_VERBS = {"designed", "architected", "led", "directed", "owned", "spearheaded", "engineered"}

# Verbs that describe doing the work without claiming special ownership.
_MODERATE_VERBS = {"built", "developed", "implemented", "created", "used", "worked", "deployed", "operated"}

# Skill-like terms Truth Guard recognizes as individually checkable
# fragments. Mirrors src/agents/grounding.py's list plus RAG for Phase 4.
SKILL_VOCABULARY: tuple[str, ...] = (
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
    "RAG",
    "Retrieval-Augmented Generation",
)

_NUMERIC_CLAIM_PATTERN = re.compile(
    r"(\$\s?\d[\d,]*(?:\.\d+)?\s?(?:k|m|million|billion)?"
    r"|\d+(?:\.\d+)?\s?%"
    r"|\d+(?:\.\d+)?\s?(?:x|times)\b"
    r"|\d[\d,]*\+?\s?(?:users?|customers?|engineers?|people|requests?)\b"
    r"|\d+(?:\.\d+)?\s?(?:ms|milliseconds?)\b"
    r")",
    re.IGNORECASE,
)

_STATUS_SEVERITY = {
    ClaimStatus.VERIFIED: 0,
    ClaimStatus.PARTIALLY_SUPPORTED: 1,
    ClaimStatus.NEEDS_HUMAN_CONFIRMATION: 2,
    ClaimStatus.UNSUPPORTED: 3,
}

_TRUTH_GUARD_SEMANTIC_SYSTEM_PROMPT = """\
You are the semantic-judgment layer of a resume truthfulness checker. You are given ONLY fragments a \
deterministic rule engine already flagged as ambiguous -- clear-cut cases were already resolved without \
you. For each fragment, judge whether the claimed wording is a fair semantic reading of the candidate's \
own evidence text, or whether it materially overstates what the evidence shows. You may reference ONLY \
the evidence_texts provided. Do not invent context. If evidence is genuinely too thin to judge, prefer \
NEEDS_HUMAN_CONFIRMATION over guessing VERIFIED.
"""


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _extract_skill_mentions(text: str) -> list[str]:
    found = []
    for skill in SKILL_VOCABULARY:
        if re.search(rf"\b{re.escape(skill)}\b", text, flags=re.IGNORECASE):
            found.append(skill)
    return found


def _extract_numeric_claims(text: str) -> list[str]:
    return [match.strip() for match in _NUMERIC_CLAIM_PATTERN.findall(text)]


def _numeric_claim_supported(claim: str, original_text: str | None, evidence_pool: list[Evidence]) -> bool:
    normalized_claim = _normalize(claim)
    haystacks = [original_text or ""] + [e.source_text for e in evidence_pool]
    return any(normalized_claim in _normalize(h) for h in haystacks)


def _skill_evidence(skill_name: str, profile: CandidateProfile, evidence_pool: list[Evidence]) -> list[Evidence]:
    """All evidence anywhere in the profile that supports this skill by name."""
    lowered = skill_name.lower()
    matches: list[Evidence] = []
    for skill in profile.skills:
        if skill.name.lower() == lowered:
            matches.extend(skill.evidence)
    for evidence in evidence_pool:
        if lowered in [c.lower() for c in evidence.normalized_concepts]:
            if evidence not in matches:
                matches.append(evidence)
        elif lowered in evidence.source_text.lower() and evidence.source_type.value in ("WORK_EXPERIENCE", "PROJECT"):
            if evidence not in matches:
                matches.append(evidence)
    return matches


@dataclass
class _FragmentOutcome:
    fragment_text: str
    status: ClaimStatus
    evidence: list[Evidence] = field(default_factory=list)
    explanation: str = ""
    is_ambiguous: bool = False
    is_skills_only: bool = False


# ---------------------------------------------------------------------------
# Layer 1: deterministic pre-checks
# ---------------------------------------------------------------------------


def _classify_skill_fragment_deterministic(
    skill: str, proposed_text: str, profile: CandidateProfile, evidence_pool: list[Evidence]
) -> _FragmentOutcome:
    candidate_has_skill = any(s.name.lower() == skill.lower() for s in profile.skills)
    if not candidate_has_skill:
        return _FragmentOutcome(
            skill, ClaimStatus.UNSUPPORTED, [], f"'{skill}' does not appear anywhere in the candidate's profile."
        )

    evidence = _skill_evidence(skill, profile, evidence_pool)
    has_work_or_project_evidence = any(e.source_type.value in ("WORK_EXPERIENCE", "PROJECT") for e in evidence)

    lowered_text = proposed_text.lower()
    strong_verb_used = next((v for v in _STRONG_VERBS if re.search(rf"\b{v}\b", lowered_text)), None)
    moderate_verb_used = next((v for v in _MODERATE_VERBS if re.search(rf"\b{v}\b", lowered_text)), None)

    if not has_work_or_project_evidence:
        if strong_verb_used or moderate_verb_used:
            return _FragmentOutcome(
                skill,
                ClaimStatus.NEEDS_HUMAN_CONFIRMATION,
                evidence,
                f"'{skill}' is listed as a skill but has no work-experience or project evidence showing how it "
                "was used; the proposed wording claims a specific action.",
                is_ambiguous=True,
                is_skills_only=True,
            )
        return _FragmentOutcome(skill, ClaimStatus.VERIFIED, evidence, f"'{skill}' is listed as a candidate skill.")

    if strong_verb_used:
        verb_grounded = any(re.search(rf"\b{strong_verb_used}\b", e.source_text.lower()) for e in evidence)
        if not verb_grounded:
            return _FragmentOutcome(
                skill,
                ClaimStatus.PARTIALLY_SUPPORTED,
                evidence,
                f"'{skill}' usage is evidenced, but the '{strong_verb_used}'-level wording is stronger than the "
                "source material.",
                is_ambiguous=True,
                is_skills_only=False,
            )

    return _FragmentOutcome(skill, ClaimStatus.VERIFIED, evidence, f"'{skill}' is directly supported by work/project evidence.")


def _classify_numeric_fragment(claim: str, original_text: str | None, evidence_pool: list[Evidence]) -> _FragmentOutcome | None:
    if _numeric_claim_supported(claim, original_text, evidence_pool):
        return None  # not a checkable failure; omit rather than manufacture a VERIFIED numeric fragment
    return _FragmentOutcome(claim, ClaimStatus.UNSUPPORTED, [], f"Numeric claim '{claim}' has no supporting evidence.")


def _classify_title_fragment(modification: ResumeModification, profile: CandidateProfile) -> _FragmentOutcome | None:
    if modification.section.lower() not in ("title", "headline", "job title"):
        return None
    claim = _normalize(modification.claim or modification.proposed_text)
    for experience in profile.work_experience:
        if _normalize(experience.title) == claim:
            return _FragmentOutcome(
                claim, ClaimStatus.VERIFIED, list(experience.evidence), f"Title matches evidenced role '{experience.title}'."
            )
    return _FragmentOutcome(
        claim,
        ClaimStatus.UNSUPPORTED,
        [],
        f"Proposed title {modification.claim or modification.proposed_text!r} does not match any evidenced job title.",
    )


# ---------------------------------------------------------------------------
# Layer 2: LLM semantic reasoning (ambiguous fragments only), with
# Layer 3 (fail-closed post-validation) applied to its output.
# ---------------------------------------------------------------------------


def _resolve_ambiguous_fragments(
    modification: ResumeModification, ambiguous: list[_FragmentOutcome], llm_client: LLMClient | None
) -> tuple[ClaimStatus, str]:
    if llm_client is None:
        worst = max((o.status for o in ambiguous), key=lambda s: _STATUS_SEVERITY[s])
        return worst, "Semantic ambiguity resolved by deterministic fallback rules (no LLM configured)."

    context = {
        "claim": modification.claim or modification.proposed_text,
        "ambiguous_fragments": [
            {
                "skill": o.fragment_text,
                "has_work_or_project_evidence": not o.is_skills_only,
                "evidence_texts": [e.source_text for e in o.evidence],
            }
            for o in ambiguous
        ],
    }

    try:
        llm_output, _ = llm_client.structured_output(
            json.dumps(context), TruthGuardLLMOutput, system=_TRUTH_GUARD_SEMANTIC_SYSTEM_PROMPT
        )
    except HireLoopLLMError:
        # FAIL CLOSED: a failed semantic check is never silently VERIFIED.
        return ClaimStatus.NEEDS_HUMAN_CONFIRMATION, "Semantic verification unavailable (provider failure); flagged for human confirmation."

    llm_status = llm_output.status
    # Post-validation cap: the LLM can never mark a skills-only fragment
    # VERIFIED -- at best it remains a human question.
    if any(o.is_skills_only for o in ambiguous) and llm_status == ClaimStatus.VERIFIED:
        llm_status = ClaimStatus.NEEDS_HUMAN_CONFIRMATION

    return llm_status, llm_output.explanation or "Resolved by semantic review."


def _build_safe_rewrite(modification: ResumeModification, verified_skills: list[str]) -> str | None:
    if modification.original_text:
        return modification.original_text
    if verified_skills:
        return f"Worked with {', '.join(verified_skills)}."
    return None


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def classify_modification(
    modification: ResumeModification,
    profile: CandidateProfile,
    evidence_pool: list[Evidence],
    llm_client: LLMClient | None = None,
) -> TruthGuardResult:
    """Classify one modification against profile evidence only. Never
    reads modification.reason/targeted_job_requirement as evidence."""
    text = modification.claim or modification.proposed_text

    title_outcome = _classify_title_fragment(modification, profile)
    outcomes: list[_FragmentOutcome] = []
    if title_outcome is not None:
        outcomes.append(title_outcome)
    else:
        for skill in _extract_skill_mentions(text):
            outcomes.append(_classify_skill_fragment_deterministic(skill, text, profile, evidence_pool))
        for numeric_claim in _extract_numeric_claims(text):
            numeric_outcome = _classify_numeric_fragment(numeric_claim, modification.original_text, evidence_pool)
            if numeric_outcome is not None:
                outcomes.append(numeric_outcome)

    hard_outcomes = [o for o in outcomes if not o.is_ambiguous]
    ambiguous_outcomes = [o for o in outcomes if o.is_ambiguous]

    hard_status = (
        max((o.status for o in hard_outcomes), key=lambda s: _STATUS_SEVERITY[s]) if hard_outcomes else ClaimStatus.VERIFIED
    )

    ambiguous_status: ClaimStatus | None = None
    ambiguous_explanation = ""
    if hard_status != ClaimStatus.UNSUPPORTED and ambiguous_outcomes:
        # Deterministic UNSUPPORTED already decides the outcome -- no need
        # to spend an LLM call asking a question whose answer can't change it.
        ambiguous_status, ambiguous_explanation = _resolve_ambiguous_fragments(modification, ambiguous_outcomes, llm_client)

    worst_status = hard_status
    if ambiguous_status is not None and _STATUS_SEVERITY[ambiguous_status] > _STATUS_SEVERITY[worst_status]:
        worst_status = ambiguous_status

    evidence_ids: set[str] = set()
    unsupported_fragments: list[str] = []
    verified_skills: list[str] = []
    explanations: list[str] = []

    for outcome in hard_outcomes:
        evidence_ids.update(e.evidence_id for e in outcome.evidence)
        explanations.append(outcome.explanation)
        if outcome.status == ClaimStatus.VERIFIED:
            verified_skills.append(outcome.fragment_text)
        else:
            unsupported_fragments.append(outcome.fragment_text)

    for outcome in ambiguous_outcomes:
        evidence_ids.update(e.evidence_id for e in outcome.evidence)
        if ambiguous_status not in (ClaimStatus.VERIFIED, None):
            unsupported_fragments.append(outcome.fragment_text)
        elif ambiguous_status == ClaimStatus.VERIFIED:
            verified_skills.append(outcome.fragment_text)
    if ambiguous_explanation:
        explanations.append(ambiguous_explanation)

    if not explanations:
        explanations.append("No technology, numeric, or title claims were found to verify; treated as a safe rewrite.")

    safe_rewrite = None
    if worst_status in (ClaimStatus.UNSUPPORTED, ClaimStatus.PARTIALLY_SUPPORTED):
        safe_rewrite = _build_safe_rewrite(modification, verified_skills)

    confidence = {
        ClaimStatus.VERIFIED: 0.9,
        ClaimStatus.PARTIALLY_SUPPORTED: 0.5,
        ClaimStatus.UNSUPPORTED: 0.9,
        ClaimStatus.NEEDS_HUMAN_CONFIRMATION: 0.3,
    }[worst_status]

    return TruthGuardResult(
        modification_id=modification.modification_id,
        status=worst_status,
        evidence_ids=sorted(evidence_ids),
        explanation=" ".join(explanations),
        unsupported_fragments=unsupported_fragments,
        suggested_safe_rewrite=safe_rewrite,
        confidence=confidence,
    )


class TruthGuardAgent:
    """Orchestrates classify_modification() over a batch. Holds an
    optional LLMClient used only for Layer 2 (ambiguous fragments); the
    deterministic layers never depend on it."""

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client

    def classify_modifications(
        self,
        modifications: list[ResumeModification],
        profile: CandidateProfile,
        evidence_pool: list[Evidence],
    ) -> list[TruthGuardResult]:
        return [classify_modification(mod, profile, evidence_pool, llm_client=self.llm_client) for mod in modifications]
