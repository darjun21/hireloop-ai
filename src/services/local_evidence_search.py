"""
Deterministic local evidence retrieval fallback.

Used whenever Pinecone is unavailable or unconfigured, so a demo/test never
breaks for lack of network access. Normalized token overlap + a direct
substring check — no embeddings, no network, no LLM.
"""

from __future__ import annotations

from src.models.evidence import Evidence
from src.models.evidence_retrieval import EvidenceSearchResult, RetrievalSource
from src.services.normalization import normalize_whitespace


def local_search_candidate_evidence(query: str, evidence: list[Evidence], top_k: int = 5) -> list[EvidenceSearchResult]:
    query_tokens = set(normalize_whitespace(query).lower().split())
    query_lower = query.lower()

    scored: list[tuple[float, Evidence]] = []
    for item in evidence:
        text_tokens = set(normalize_whitespace(item.source_text).lower().split())
        concept_tokens = {c.lower() for c in item.normalized_concepts}
        overlap = len(query_tokens & (text_tokens | concept_tokens))

        if overlap == 0 and query_lower in item.source_text.lower():
            overlap = 1

        if overlap > 0:
            score = overlap / max(len(query_tokens), 1)
            scored.append((score, item))

    scored.sort(key=lambda pair: (-pair[0], pair[1].evidence_id))
    return [
        EvidenceSearchResult(evidence_id=item.evidence_id, score=score, source=RetrievalSource.LOCAL_FALLBACK)
        for score, item in scored[:top_k]
    ]
