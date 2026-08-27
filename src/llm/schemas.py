"""
Structured-output schemas requested from the LLM at the agent call
boundary. These are intentionally *not* the domain models
(CandidateProfile, MatchAnalysis, ...) — they're the raw shape we ask the
model to fill in, which the agent then converts into a domain model while
applying grounding/validation rules the model itself cannot be trusted to
enforce.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.models.enums import ConfidenceLevel, TruthGuardStatus


class ExtractedSkill(BaseModel):
    name: str
    source_text: str = ""
    source_section: str = ""
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)


class ExtractedWorkExperience(BaseModel):
    company: str = ""
    title: str = ""
    start_date: str | None = None
    end_date: str | None = None
    description: str | None = None
    skills_used: list[str] = Field(default_factory=list)
    source_text: str = ""


class ExtractedEducation(BaseModel):
    institution: str = ""
    degree: str | None = None
    field_of_study: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    source_text: str = ""


class ExtractedProject(BaseModel):
    name: str = ""
    description: str | None = None
    skills_used: list[str] = Field(default_factory=list)
    source_text: str = ""


class ExtractedCertification(BaseModel):
    name: str = ""
    issuer: str | None = None
    date: str | None = None
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    source_text: str = ""


class ExtractedProfileData(BaseModel):
    """Raw resume extraction requested from the LLM. `years_experience_estimate`
    is the model's own naive guess and is NOT trusted as-is by the Profile
    Agent — see src/agents/profile_agent.py's conservative recomputation.
    """

    name: str | None = None
    professional_summary: str = ""
    years_experience_estimate: float | None = None
    skills: list[ExtractedSkill] = Field(default_factory=list)
    work_experience: list[ExtractedWorkExperience] = Field(default_factory=list)
    education: list[ExtractedEducation] = Field(default_factory=list)
    projects: list[ExtractedProject] = Field(default_factory=list)
    certifications: list[ExtractedCertification] = Field(default_factory=list)


class ProposedModificationLLM(BaseModel):
    """One modification proposal from the Resume Tailor's LLM call. This is
    UNTRUSTED input to Truth Guard -- it may overreach (that's the point:
    the Tailor is allowed to be imperfect because Truth Guard is the
    safety net, never the other way around)."""

    section: str = "Professional Summary"
    original_text: str | None = None
    proposed_text: str
    reason: str = ""
    targeted_job_requirement: str = ""
    claim: str = ""


class TailorLLMOutput(BaseModel):
    modifications: list[ProposedModificationLLM] = Field(default_factory=list)


class TruthGuardLLMOutput(BaseModel):
    """Requested ONLY for the ambiguous portion of a modification that
    survived deterministic pre-checks (ownership/leadership wording,
    subtle escalation, semantic equivalence) -- never for fragments a
    deterministic rule already resolved. See src/agents/truth_guard.py's
    hybrid pipeline and its fail-closed post-validation, which can
    override this output but never let it override a deterministic
    UNSUPPORTED finding.
    """

    status: TruthGuardStatus = TruthGuardStatus.NEEDS_HUMAN_CONFIRMATION
    explanation: str = ""
    supported_fragments: list[str] = Field(default_factory=list)
    unsupported_fragments: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    suggested_safe_rewrite: str | None = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class CandidateInsightLLM(BaseModel):
    """One candidate insight from the Learning Agent's LLM call.
    UNTRUSTED: sample_size/confidence are never read from this -- they are
    always re-derived from the referenced OutcomeAnalytics group by
    src/services/learning_insight_validation.py, which also rejects
    ungrounded numbers and causal language before anything is persisted.
    """

    category: str = "ROLE_FAMILY"
    referenced_group: str
    compared_group: str | None = None  # the group referenced_group is being contrasted against, if any
    observation: str
    recommendation: str


class LearningAgentLLMOutput(BaseModel):
    insights: list[CandidateInsightLLM] = Field(default_factory=list)


class MatchAnalysisLLMOutput(BaseModel):
    """What we ask the LLM for when interpreting a finished OpportunityScore.
    Deliberately has no score/recommendation field — there is nothing for
    the model to override even if it tries."""

    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    explanation: str = ""
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM
