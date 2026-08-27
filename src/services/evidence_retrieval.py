"""
Orchestrates candidate evidence indexing and per-requirement retrieval:
Pinecone when configured and healthy, deterministic local fallback
otherwise, and a direct-profile-match fast path for exact skill hits.

Pinecone failure must never break the workflow — every Pinecone call here
is wrapped and degrades to the local fallback with an explicit Decision
Trace note, never a silent difference in behavior.
"""

from __future__ import annotations

from src.config.workflow import (
    EVIDENCE_MODERATE_SCORE_THRESHOLD,
    EVIDENCE_RETRIEVAL_TOP_K,
    EVIDENCE_STRONG_SCORE_THRESHOLD,
)
from src.models.candidate import CandidateProfile
from src.models.evidence import Evidence
from src.models.evidence_retrieval import EvidenceStrength, RequirementEvidence, RetrievalSource
from src.services.decision_trace import DecisionTrace
from src.services.local_evidence_search import local_search_candidate_evidence
from src.services.normalization import normalize_skill
from src.services.vector_service import EvidenceVectorIndex, VectorServiceError


def _strength_for(top_score: float | None) -> EvidenceStrength:
    if top_score is None:
        return EvidenceStrength.NONE
    if top_score >= EVIDENCE_STRONG_SCORE_THRESHOLD:
        return EvidenceStrength.STRONG
    if top_score >= EVIDENCE_MODERATE_SCORE_THRESHOLD:
        return EvidenceStrength.MODERATE
    return EvidenceStrength.WEAK


class EvidenceRetrievalService:
    def __init__(self, vector_index: EvidenceVectorIndex | None = None, decision_trace: DecisionTrace | None = None) -> None:
        self.vector_index = vector_index
        self.decision_trace = decision_trace

    def index_candidate_evidence(self, candidate_id: str, evidence: list[Evidence]) -> str:
        """Returns the source actually used: "PINECONE" or "NONE" (no
        indexing needed/possible — local fallback searches the evidence
        list directly at retrieval time, so this never blocks anything)."""
        if self.vector_index is None:
            return "NONE"
        try:
            if not self.vector_index.health_check():
                raise VectorServiceError("Pinecone health check failed")
            self.vector_index.index_candidate_evidence(candidate_id, evidence)
            return "PINECONE"
        except VectorServiceError:
            if self.decision_trace:
                self.decision_trace.add(
                    "evidence_indexing",
                    "index_candidate_evidence",
                    "Pinecone evidence indexing unavailable; local fallback will be used for retrieval.",
                )
            return "NONE"

    def retrieve_for_requirement(
        self,
        candidate: CandidateProfile,
        requirement: str,
        evidence_pool: list[Evidence],
        top_k: int = EVIDENCE_RETRIEVAL_TOP_K,
    ) -> RequirementEvidence:
        # Fast path: an exact, normalized skill match with resume evidence
        # is a direct profile match — no need for semantic search.
        normalized_requirement = normalize_skill(requirement)
        direct_skill = next((s for s in candidate.skills if s.name == normalized_requirement), None)
        if direct_skill and direct_skill.evidence:
            return RequirementEvidence(
                requirement=requirement,
                matched_evidence_ids=[e.evidence_id for e in direct_skill.evidence],
                evidence_strength=EvidenceStrength.STRONG,
                retrieval_source=RetrievalSource.DIRECT_PROFILE_MATCH,
                confidence=0.9,
            )

        results = []
        source = RetrievalSource.LOCAL_FALLBACK
        if self.vector_index is not None:
            try:
                if not self.vector_index.health_check():
                    raise VectorServiceError("Pinecone health check failed")
                results = self.vector_index.search_candidate_evidence(candidate.candidate_id, requirement, top_k=top_k)
                source = RetrievalSource.PINECONE
            except VectorServiceError:
                results = []

        if not results:
            if source == RetrievalSource.PINECONE:
                source = RetrievalSource.LOCAL_FALLBACK
            if self.vector_index is not None and self.decision_trace:
                self.decision_trace.add(
                    "evidence_retrieval",
                    "retrieve_for_requirement",
                    "Pinecone evidence retrieval unavailable; local fallback used.",
                )
            results = local_search_candidate_evidence(requirement, evidence_pool, top_k=top_k)
            source = RetrievalSource.LOCAL_FALLBACK

        top_score = results[0].score if results else None
        return RequirementEvidence(
            requirement=requirement,
            matched_evidence_ids=[r.evidence_id for r in results],
            evidence_strength=_strength_for(top_score),
            retrieval_source=source,
            confidence=min(0.85, top_score) if top_score is not None else 0.0,
        )
