"""Nodes covering candidate evidence preparation and job-requirement evidence retrieval."""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from src.graph.helpers import trace_event
from src.graph.state import HireLoopState
from src.models.candidate import CandidateProfile
from src.models.evidence import Evidence
from src.models.job import JobPosting
from src.services.decision_trace import DecisionTrace
from src.services.evidence_extraction import extract_evidence_chunks
from src.services.evidence_retrieval import EvidenceRetrievalService
from src.services.job_requirements import extract_job_requirements


def prepare_candidate_evidence_node(state: HireLoopState, config: RunnableConfig) -> dict:
    profile = CandidateProfile(**state["candidate_profile"])
    evidence_chunks = extract_evidence_chunks(profile)

    vector_index = (config.get("configurable") or {}).get("vector_index")
    local_trace = DecisionTrace()
    service = EvidenceRetrievalService(vector_index=vector_index, decision_trace=local_trace)
    source = service.index_candidate_evidence(profile.candidate_id, evidence_chunks)

    if source == "PINECONE":
        summary = f"{len(evidence_chunks)} candidate evidence records indexed."
    else:
        summary = f"{len(evidence_chunks)} candidate evidence records prepared for local retrieval (Pinecone not configured or unavailable)."

    events = [trace_event("evidence_indexing", "prepare_candidate_evidence", summary, metadata={"count": len(evidence_chunks), "source": source})]
    events += local_trace.as_dicts()

    return {
        "candidate_evidence": [e.model_dump(mode="json") for e in evidence_chunks],
        "evidence_index_status": source,
        "decision_trace": events,
        "current_step": "prepare_candidate_evidence",
    }


def retrieve_job_evidence_node(state: HireLoopState, config: RunnableConfig) -> dict:
    profile = CandidateProfile(**state["candidate_profile"])
    deduped_by_id = {d["job_id"]: d for d in state.get("deduped_jobs", [])}
    job = JobPosting(**deduped_by_id[state["selected_job_id"]])
    evidence_pool = [Evidence(**d) for d in state.get("candidate_evidence", [])]

    vector_index = (config.get("configurable") or {}).get("vector_index")
    local_trace = DecisionTrace()
    service = EvidenceRetrievalService(vector_index=vector_index, decision_trace=local_trace)

    requirements = extract_job_requirements(job)
    result = {req: service.retrieve_for_requirement(profile, req, evidence_pool).model_dump(mode="json") for req in requirements}

    events = [
        trace_event(
            "evidence_retrieval",
            "retrieve_job_evidence",
            f"Evidence retrieval completed for {len(requirements)} job requirement(s).",
            metadata={"requirements": len(requirements)},
        )
    ]
    events += local_trace.as_dicts()

    return {
        "job_requirement_evidence": result,
        "decision_trace": events,
        "current_step": "retrieve_job_evidence",
    }
