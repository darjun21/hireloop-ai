"""
Resume Tailor Agent.

Proposes resume modifications for a selected job. It may overreach — that
is by design: Truth Guard (src/agents/truth_guard.py), not the Tailor, is
the safety net that decides what's actually truthful. The Tailor never
saves, finalizes, or creates a ResumeVersion; it only returns structured
proposals.

Allowed: reorder skills, emphasize already-supported skills, rewrite
summary/bullets for clarity, surface relevant project work, align
terminology, improve concision.

Forbidden (enforced by Truth Guard, not by trusting the Tailor to behave):
inventing a skill/employer/project/metric/certification, changing dates,
inflating years of experience, changing job title, claiming unsupported
ownership/leadership.

`supporting_evidence_ids` on each proposal is the Tailor's own good-faith
reference to the RequirementEvidence it was shown — it is NOT trusted as
proof by Truth Guard, which independently re-derives grounding from the
candidate's actual Evidence records.
"""

from __future__ import annotations

import json
from uuid import uuid4

from src.llm.client import LLMClient
from src.llm.schemas import TailorLLMOutput
from src.models.candidate import CandidateProfile
from src.models.evidence_retrieval import RequirementEvidence
from src.models.job import JobPosting
from src.models.resume_modification import ResumeModification
from src.services.decision_trace import DecisionTrace
from src.services.job_requirements import extract_job_requirements

_GROUNDING_SYSTEM_PROMPT = """\
You are tailoring a candidate's resume for one specific job. You may reorder skills, emphasize \
already-evidenced skills, rewrite the summary/bullets for clarity and concision, and surface relevant \
project work. You must NEVER invent a skill, employer, project, metric, certification; change dates; \
inflate years of experience; change the job title to something unsupported; or claim ownership/leadership \
not supported by evidence. Every proposal will be independently checked against the candidate's actual \
evidence by a separate verification step -- propose your best attempt, but do not fabricate to make a \
requirement look satisfied.
"""


class ResumeTailorAgent:
    def __init__(self, llm_client: LLMClient, decision_trace: DecisionTrace | None = None) -> None:
        self.llm_client = llm_client
        self.decision_trace = decision_trace

    def propose_modifications(
        self,
        candidate: CandidateProfile,
        job: JobPosting,
        job_requirement_evidence: dict[str, RequirementEvidence] | None = None,
    ) -> list[ResumeModification]:
        job_requirement_evidence = job_requirement_evidence or {}
        requirements = extract_job_requirements(job)
        context = {
            "candidate_skills": [s.name for s in candidate.skills],
            "professional_summary": candidate.professional_summary,
            "job_requirements": requirements,
        }
        prompt = json.dumps(context)

        llm_output, _ = self.llm_client.structured_output(prompt, TailorLLMOutput, system=_GROUNDING_SYSTEM_PROMPT)

        modifications = []
        for item in llm_output.modifications:
            requirement_evidence = job_requirement_evidence.get(item.targeted_job_requirement)
            modifications.append(
                ResumeModification(
                    modification_id=f"mod-{uuid4().hex[:8]}",
                    section=item.section,
                    original_text=item.original_text,
                    proposed_text=item.proposed_text,
                    reason=item.reason,
                    targeted_job_requirement=item.targeted_job_requirement,
                    claim=item.claim or item.proposed_text,
                    supporting_evidence_ids=requirement_evidence.matched_evidence_ids if requirement_evidence else [],
                    confidence=requirement_evidence.confidence if requirement_evidence else 0.5,
                )
            )

        if self.decision_trace:
            self.decision_trace.add(
                "resume_tailor",
                "propose_modifications",
                f"Resume Tailor proposed {len(modifications)} modification(s).",
            )

        return modifications
