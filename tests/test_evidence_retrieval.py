from src.models.enums import EvidenceSourceType as ST
from src.models.evidence import Evidence
from src.models.evidence_retrieval import EvidenceStrength, RetrievalSource
from src.services.decision_trace import DecisionTrace
from src.services.evidence_retrieval import EvidenceRetrievalService
from tests.factories import build_candidate
from tests.fakes import InMemoryVectorIndex


def _ev(eid, section, text, stype=ST.WORK_EXPERIENCE):
    return Evidence(evidence_id=eid, source_type=stype, source_section=section, source_text=text, confidence=0.85)


# 4. Relevant evidence retrieval (direct profile match fast path).
def test_direct_profile_match_for_exact_skill():
    from src.models.candidate import Skill

    candidate = build_candidate(skills=[Skill(name="Python", evidence=[_ev("e1", "Skills", "Python")])])
    service = EvidenceRetrievalService(vector_index=None)

    result = service.retrieve_for_requirement(candidate, "Python", [_ev("e1", "Skills", "Python")])

    assert result.retrieval_source == RetrievalSource.DIRECT_PROFILE_MATCH
    assert result.evidence_strength == EvidenceStrength.STRONG
    assert "e1" in result.matched_evidence_ids


def test_no_evidence_at_all_yields_none_strength():
    candidate = build_candidate(skills=[])
    service = EvidenceRetrievalService(vector_index=None)

    result = service.retrieve_for_requirement(candidate, "Kubernetes", [])

    assert result.evidence_strength == EvidenceStrength.NONE
    assert result.matched_evidence_ids == []


# 21. Pinecone outage does not crash / local fallback used with a Decision Trace note.
def test_pinecone_failure_falls_back_to_local_search_with_trace_note():
    candidate = build_candidate(skills=[])
    failing_index = InMemoryVectorIndex(healthy=False)
    trace = DecisionTrace()
    service = EvidenceRetrievalService(vector_index=failing_index, decision_trace=trace)

    pool = [_ev("e1", "Project: RAG", "Built a RAG pipeline using LangChain and Python.", ST.PROJECT)]
    result = service.retrieve_for_requirement(candidate, "RAG", pool)

    assert result.retrieval_source == RetrievalSource.LOCAL_FALLBACK
    assert result.matched_evidence_ids == ["e1"]
    assert any("Pinecone evidence retrieval unavailable; local fallback used." in e.message for e in trace.events)


def test_pinecone_success_is_used_when_healthy():
    candidate = build_candidate(skills=[])
    index = InMemoryVectorIndex(healthy=True)
    index.index_candidate_evidence(candidate.candidate_id, [_ev("e1", "Work", "Deep Kubernetes operations experience.")])
    service = EvidenceRetrievalService(vector_index=index)

    result = service.retrieve_for_requirement(candidate, "Kubernetes", [])

    assert result.retrieval_source == RetrievalSource.PINECONE
    assert "e1" in result.matched_evidence_ids


def test_index_candidate_evidence_falls_back_gracefully_when_indexing_fails():
    class AlwaysFailsToIndex(InMemoryVectorIndex):
        def index_candidate_evidence(self, candidate_id, evidence):
            from src.services.vector_service import VectorServiceError

            raise VectorServiceError("simulated indexing failure")

    trace = DecisionTrace()
    service = EvidenceRetrievalService(vector_index=AlwaysFailsToIndex(), decision_trace=trace)

    source = service.index_candidate_evidence("cand-1", [_ev("e1", "Skills", "Python")])

    assert source == "NONE"
    assert any("Pinecone evidence indexing unavailable" in e.message for e in trace.events)


def test_indexing_returns_none_when_no_vector_index_configured():
    service = EvidenceRetrievalService(vector_index=None)
    assert service.index_candidate_evidence("cand-1", [_ev("e1", "Skills", "Python")]) == "NONE"
