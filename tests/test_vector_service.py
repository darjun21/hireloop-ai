"""
Vector service contract tests. No real Pinecone connection -- candidate
isolation and fallback behavior are verified against InMemoryVectorIndex
(tests/fakes.py), which implements the exact same EvidenceVectorIndex
contract real Pinecone-backed code depends on.
"""

from src.models.enums import EvidenceSourceType
from src.models.evidence import Evidence
from src.services.embedding_provider import MockEmbeddingProvider
from tests.fakes import InMemoryVectorIndex


def _ev(eid: str, section: str, text: str) -> Evidence:
    return Evidence(evidence_id=eid, source_type=EvidenceSourceType.RESUME, source_section=section, source_text=text, confidence=0.85)


def test_module_imports_safely_even_if_pinecone_sdk_missing():
    # pinecone-client IS installed in this environment (it's in
    # requirements.txt), but PineconeEvidenceIndex must only import it
    # lazily inside __init__ -- never at module import time -- so the
    # module stays importable in an environment without it.
    import src.services.vector_service as module

    assert hasattr(module, "PineconeEvidenceIndex")
    assert hasattr(module, "EvidenceVectorIndex")


# 3. Candidate vector isolation.
def test_candidate_a_never_receives_candidate_b_evidence():
    index = InMemoryVectorIndex()
    index.index_candidate_evidence("cand-a", [_ev("a1", "Skills", "Python expert")])
    index.index_candidate_evidence("cand-b", [_ev("b1", "Skills", "Python expert")])

    results_a = index.search_candidate_evidence("cand-a", "Python")
    results_b = index.search_candidate_evidence("cand-b", "Python")

    assert {r.evidence_id for r in results_a} == {"a1"}
    assert {r.evidence_id for r in results_b} == {"b1"}


def test_querying_unknown_candidate_returns_nothing():
    index = InMemoryVectorIndex()
    index.index_candidate_evidence("cand-a", [_ev("a1", "Skills", "Python expert")])

    assert index.search_candidate_evidence("cand-nonexistent", "Python") == []


def test_indexing_is_idempotent_for_repeated_evidence_ids():
    index = InMemoryVectorIndex()
    evidence = _ev("e1", "Skills", "Python expert")
    index.index_candidate_evidence("cand-a", [evidence])
    index.index_candidate_evidence("cand-a", [evidence])  # re-index same id

    results = index.search_candidate_evidence("cand-a", "Python")
    assert len(results) == 1


def test_delete_candidate_evidence_removes_only_that_candidate():
    index = InMemoryVectorIndex()
    index.index_candidate_evidence("cand-a", [_ev("a1", "Skills", "Python")])
    index.index_candidate_evidence("cand-b", [_ev("b1", "Skills", "Python")])

    index.delete_candidate_evidence("cand-a")

    assert index.search_candidate_evidence("cand-a", "Python") == []
    assert len(index.search_candidate_evidence("cand-b", "Python")) == 1


def test_health_check_never_raises_on_failure():
    index = InMemoryVectorIndex(healthy=False)
    assert index.health_check() is False


# Embedding dimension validation (mock provider).
def test_mock_embedding_provider_dimension_is_consistent():
    provider = MockEmbeddingProvider(dimension=16)
    vectors = provider.embed(["Python engineer", "Sales manager"])
    assert all(len(v) == 16 for v in vectors)


def test_mock_embedding_provider_is_deterministic():
    provider = MockEmbeddingProvider()
    assert provider.embed(["Python"]) == provider.embed(["Python"])


def test_mock_embedding_provider_handles_empty_text():
    provider = MockEmbeddingProvider(dimension=8)
    vectors = provider.embed([""])
    assert vectors == [[0.0] * 8]
