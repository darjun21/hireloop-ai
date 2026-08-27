from src.models.enums import EvidenceSourceType as ST
from src.models.evidence import Evidence
from src.services.local_evidence_search import local_search_candidate_evidence


def _ev(eid, section, text, stype=ST.WORK_EXPERIENCE):
    return Evidence(evidence_id=eid, source_type=stype, source_section=section, source_text=text, confidence=0.85)


def test_python_query_ranks_python_evidence_strongly():
    pool = [
        _ev("e1", "Work", "Built services using Python and PostgreSQL daily."),
        _ev("e2", "Work", "Managed a sales team and closed enterprise deals."),
    ]
    results = local_search_candidate_evidence("Python", pool)
    assert results[0].evidence_id == "e1"


def test_kubernetes_query_does_not_return_docker_as_proof():
    pool = [_ev("e1", "Work", "Worked with Docker containers for local development.")]
    results = local_search_candidate_evidence("Kubernetes", pool)
    assert results == []


def test_langchain_rag_query_ranks_relevant_project_strongly():
    pool = [
        _ev("e1", "Project: RAG Pipeline", "Built a RAG pipeline using LangChain and Python.", ST.PROJECT),
        _ev("e2", "Work", "Managed payroll systems."),
    ]
    results = local_search_candidate_evidence("RAG", pool)
    assert results
    assert results[0].evidence_id == "e1"


def test_top_k_is_respected():
    pool = [_ev(f"e{i}", "Work", "Python engineer building services.") for i in range(10)]
    results = local_search_candidate_evidence("Python", pool, top_k=3)
    assert len(results) == 3


def test_normalized_concepts_contribute_to_matching():
    pool = [_ev("e1", "Skills", "Used K8s in production", ST.WORK_EXPERIENCE)]
    pool[0] = pool[0].model_copy(update={"normalized_concepts": ["kubernetes"]})
    results = local_search_candidate_evidence("Kubernetes", pool)
    assert results and results[0].evidence_id == "e1"


def test_empty_pool_returns_no_results():
    assert local_search_candidate_evidence("Python", []) == []
