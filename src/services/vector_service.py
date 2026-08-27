"""
Pinecone-backed evidence retrieval — semantic retrieval of candidate
evidence ONLY. Pinecone must never compute OpportunityScore, store
application state, store rankings, or become a source of truth; those all
stay in SQLite/state (see docs/DECISIONS.md #3).

Candidate isolation: each candidate's evidence is indexed under its own
Pinecone namespace (the candidate_id), so a query can never structurally
return another candidate's vectors regardless of query content — this is
enforced by the SDK's namespace parameter, not just an application-level
filter, and result rows are defensively re-checked against the requested
candidate_id as a second layer.

Metadata is intentionally minimal (candidate_id, evidence_id, source_type,
source_section) — never the evidence text itself, to avoid putting
unnecessary content in a third-party metadata store. Callers resolve
evidence_id back to full text from the CandidateProfile-derived evidence
list they already hold in memory/state.

No live network calls happen in pytest — see
src/services/local_evidence_search.py for the deterministic fallback used
whenever this service is unavailable or unconfigured (src/services/
evidence_retrieval.py orchestrates the choice).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.models.evidence import Evidence
from src.models.evidence_retrieval import EvidenceSearchResult, RetrievalSource
from src.services.embedding_provider import EmbeddingProvider


class VectorServiceError(Exception):
    """Any Pinecone-layer failure. Callers must treat this as recoverable
    via the local fallback — never a reason to fail the workflow."""


class EvidenceVectorIndex(ABC):
    @abstractmethod
    def index_candidate_evidence(self, candidate_id: str, evidence: list[Evidence]) -> None: ...

    @abstractmethod
    def search_candidate_evidence(self, candidate_id: str, query: str, top_k: int = 5) -> list[EvidenceSearchResult]: ...

    @abstractmethod
    def delete_candidate_evidence(self, candidate_id: str) -> None: ...

    @abstractmethod
    def health_check(self) -> bool: ...


class PineconeEvidenceIndex(EvidenceVectorIndex):
    def __init__(self, api_key: str, index_name: str, embedding_provider: EmbeddingProvider) -> None:
        try:
            from pinecone import Pinecone
        except ImportError as exc:  # pragma: no cover - dependency always declared in requirements.txt
            raise VectorServiceError("pinecone-client is not installed") from exc

        self._embedding_provider = embedding_provider
        try:
            self._client = Pinecone(api_key=api_key)
            self._index = self._client.Index(index_name)
        except Exception as exc:  # noqa: BLE001 - any SDK/network error becomes a controlled VectorServiceError
            raise VectorServiceError(f"failed to connect to Pinecone index {index_name!r}: {exc}") from exc

    def index_candidate_evidence(self, candidate_id: str, evidence: list[Evidence]) -> None:
        if not evidence:
            return
        try:
            vectors = self._embedding_provider.embed([item.source_text for item in evidence])
            records = [
                {
                    "id": item.evidence_id,
                    "values": vector,
                    "metadata": {
                        "candidate_id": candidate_id,
                        "evidence_id": item.evidence_id,
                        "source_type": item.source_type.value,
                        "source_section": item.source_section,
                    },
                }
                for item, vector in zip(evidence, vectors)
            ]
            self._index.upsert(vectors=records, namespace=candidate_id)
        except Exception as exc:  # noqa: BLE001
            raise VectorServiceError(f"failed to index evidence for candidate {candidate_id!r}: {exc}") from exc

    def search_candidate_evidence(self, candidate_id: str, query: str, top_k: int = 5) -> list[EvidenceSearchResult]:
        try:
            query_vector = self._embedding_provider.embed([query])[0]
            response = self._index.query(
                vector=query_vector, top_k=top_k, namespace=candidate_id, include_metadata=True
            )
        except Exception as exc:  # noqa: BLE001
            raise VectorServiceError(f"Pinecone query failed for candidate {candidate_id!r}: {exc}") from exc

        results = []
        for match in getattr(response, "matches", []) or []:
            metadata = match.get("metadata") or {}
            # Defensive second isolation check beyond the namespace itself.
            if metadata.get("candidate_id") != candidate_id:
                continue
            results.append(
                EvidenceSearchResult(evidence_id=match["id"], score=float(match["score"]), source=RetrievalSource.PINECONE)
            )
        return results

    def delete_candidate_evidence(self, candidate_id: str) -> None:
        try:
            self._index.delete(delete_all=True, namespace=candidate_id)
        except Exception as exc:  # noqa: BLE001
            raise VectorServiceError(f"failed to delete evidence for candidate {candidate_id!r}: {exc}") from exc

    def health_check(self) -> bool:
        try:
            self._index.describe_index_stats()
            return True
        except Exception:  # noqa: BLE001 - health checks must never raise
            return False
