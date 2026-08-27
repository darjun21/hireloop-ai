"""
LangGraph workflow wiring for HireLoop AI Phase 3 + Phase 4.

Dependency injection: nodes are plain functions of (state, config) rather
than closures, so non-serializable dependencies (the LLM client, the
optional Pinecone vector index) are passed via
`config["configurable"]["llm_client" | "vector_index"]` at invoke() time
instead of living in checkpointed state. See src/graph/state.py's module
docstring for why state itself only ever holds JSON-safe dicts.
"""

from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.graph.nodes.analysis import analyze_matches_node, rank_opportunities_node
from src.graph.nodes.application import create_application_node, human_application_action_node, phase5_application_complete_node
from src.graph.nodes.clarification import human_clarification_node
from src.graph.nodes.evidence import prepare_candidate_evidence_node, retrieve_job_evidence_node
from src.graph.nodes.human import human_select_job_node, selection_confirmed_node
from src.graph.nodes.jobs import dedupe_jobs_node, ingest_jobs_node, normalize_jobs_node, score_job_quality_node
from src.graph.nodes.outcome import (
    calculate_outcome_analytics_node,
    human_record_outcome_node,
    learning_agent_node,
    load_application_node,
    outcome_update_complete_node,
    persist_strategy_insight_node,
    record_application_event_node,
    sync_mem0_node,
)
from src.graph.nodes.preferences import collect_preferences_node
from src.graph.nodes.resume import build_candidate_profile_node, parse_resume_node, validate_candidate_profile_node
from src.graph.nodes.resume_approval import create_resume_version_node, human_resume_approval_node, phase4_complete_node
from src.graph.nodes.scoring import calculate_historical_signal_node, score_opportunities_node
from src.graph.nodes.tailoring import correct_modifications_node, strip_unresolved_modifications_node, tailor_resume_node, truth_guard_node
from src.graph.nodes.terminal import no_suitable_jobs_node
from src.graph.routing import (
    route_after_build_profile,
    route_after_human_application_action,
    route_after_human_clarification,
    route_after_human_record_outcome,
    route_after_human_resume_approval,
    route_after_human_selection,
    route_after_ingest_jobs,
    route_after_job_quality,
    route_after_load_application,
    route_after_parse_resume,
    route_after_profile_validation,
    route_after_scoring,
    route_after_truth_guard,
)
from src.graph.state import HireLoopState


def build_workflow(checkpointer: BaseCheckpointSaver | None = None) -> CompiledStateGraph:
    """Construct and compile the HireLoop workflow graph (Phase 3 job
    selection, extended by Phase 4 resume tailoring)."""
    graph = StateGraph(HireLoopState)

    # Phase 3 nodes
    graph.add_node("parse_resume", parse_resume_node)
    graph.add_node("build_candidate_profile", build_candidate_profile_node)
    graph.add_node("validate_candidate_profile", validate_candidate_profile_node)
    graph.add_node("collect_preferences", collect_preferences_node)
    graph.add_node("ingest_jobs", ingest_jobs_node)
    graph.add_node("normalize_jobs", normalize_jobs_node)
    graph.add_node("dedupe_jobs", dedupe_jobs_node)
    graph.add_node("score_job_quality", score_job_quality_node)
    graph.add_node("calculate_historical_signal", calculate_historical_signal_node)
    graph.add_node("score_opportunities", score_opportunities_node)
    graph.add_node("analyze_matches", analyze_matches_node)
    graph.add_node("rank_opportunities", rank_opportunities_node)
    graph.add_node("human_select_job", human_select_job_node)
    graph.add_node("selection_confirmed", selection_confirmed_node)
    graph.add_node("no_suitable_jobs", no_suitable_jobs_node)

    # Phase 4 nodes
    graph.add_node("prepare_candidate_evidence", prepare_candidate_evidence_node)
    graph.add_node("retrieve_job_evidence", retrieve_job_evidence_node)
    graph.add_node("tailor_resume", tailor_resume_node)
    graph.add_node("truth_guard", truth_guard_node)
    graph.add_node("correct_modifications", correct_modifications_node)
    graph.add_node("strip_unresolved_modifications", strip_unresolved_modifications_node)
    graph.add_node("human_clarification", human_clarification_node)
    graph.add_node("human_resume_approval", human_resume_approval_node)
    graph.add_node("create_resume_version", create_resume_version_node)
    graph.add_node("phase4_complete", phase4_complete_node)

    # Phase 5 nodes (application tracking only -- outcome recording is a
    # separate graph, build_outcome_update_workflow(), below)
    graph.add_node("create_application", create_application_node)
    graph.add_node("human_application_action", human_application_action_node)
    graph.add_node("phase5_application_complete", phase5_application_complete_node)

    graph.add_edge(START, "parse_resume")

    graph.add_conditional_edges(
        "parse_resume", route_after_parse_resume, {"build_candidate_profile": "build_candidate_profile", "failed": END}
    )
    graph.add_conditional_edges(
        "build_candidate_profile",
        route_after_build_profile,
        {"validate_candidate_profile": "validate_candidate_profile", "failed": END},
    )
    graph.add_conditional_edges(
        "validate_candidate_profile",
        route_after_profile_validation,
        {"collect_preferences": "collect_preferences", "failed": END},
    )
    graph.add_edge("collect_preferences", "ingest_jobs")
    graph.add_conditional_edges(
        "ingest_jobs", route_after_ingest_jobs, {"normalize_jobs": "normalize_jobs", "failed": END}
    )
    graph.add_edge("normalize_jobs", "dedupe_jobs")
    graph.add_edge("dedupe_jobs", "score_job_quality")
    graph.add_conditional_edges(
        "score_job_quality",
        route_after_job_quality,
        {"calculate_historical_signal": "calculate_historical_signal", "no_suitable_jobs": "no_suitable_jobs"},
    )
    graph.add_edge("calculate_historical_signal", "score_opportunities")
    graph.add_conditional_edges(
        "score_opportunities",
        route_after_scoring,
        {"analyze_matches": "analyze_matches", "no_suitable_jobs": "no_suitable_jobs", "failed": END},
    )
    graph.add_edge("analyze_matches", "rank_opportunities")
    graph.add_edge("rank_opportunities", "human_select_job")
    graph.add_conditional_edges(
        "human_select_job",
        route_after_human_selection,
        {"selection_confirmed": "selection_confirmed", "cancelled": END},
    )

    # Phase 4 continuation: selection_confirmed no longer ends the graph.
    graph.add_edge("selection_confirmed", "prepare_candidate_evidence")
    graph.add_edge("prepare_candidate_evidence", "retrieve_job_evidence")
    graph.add_edge("retrieve_job_evidence", "tailor_resume")
    graph.add_conditional_edges(
        "tailor_resume",
        lambda state: "failed" if state.get("workflow_status") == "FAILED" else "truth_guard",
        {"truth_guard": "truth_guard", "failed": END},
    )
    graph.add_conditional_edges(
        "truth_guard",
        route_after_truth_guard,
        {
            "correction_required": "correct_modifications",
            "human_confirmation": "human_clarification",
            "max_loops": "strip_unresolved_modifications",
            "verified": "human_resume_approval",
        },
    )
    graph.add_edge("correct_modifications", "truth_guard")
    graph.add_edge("strip_unresolved_modifications", "human_resume_approval")
    graph.add_conditional_edges(
        "human_clarification",
        route_after_human_clarification,
        {"continue": "truth_guard", "cancelled": END},
    )
    graph.add_conditional_edges(
        "human_resume_approval",
        route_after_human_resume_approval,
        {"continue": "create_resume_version", "cancelled": END},
    )
    graph.add_edge("create_resume_version", "phase4_complete")

    # Phase 5 continuation: phase4_complete no longer ends the graph.
    graph.add_edge("phase4_complete", "create_application")
    graph.add_edge("create_application", "human_application_action")
    graph.add_conditional_edges(
        "human_application_action",
        route_after_human_application_action,
        {"continue": "phase5_application_complete", "cancelled": END},
    )
    graph.add_edge("phase5_application_complete", END)

    graph.add_edge("no_suitable_jobs", END)

    return graph.compile(checkpointer=checkpointer)


def build_outcome_update_workflow(checkpointer: BaseCheckpointSaver | None = None) -> CompiledStateGraph:
    """Separate graph entry point for recording an application outcome —
    deliberately not chained off build_workflow()'s graph, since outcomes
    happen days or weeks after the initial application (Part E/W). Invoked
    with its own thread_id and `target_application_id` in the initial
    state.

    load_application -> human_record_outcome -> record_application_event
    -> calculate_outcome_analytics -> learning_agent
    -> persist_strategy_insight -> sync_mem0 -> outcome_update_complete
    """
    graph = StateGraph(HireLoopState)

    graph.add_node("load_application", load_application_node)
    graph.add_node("human_record_outcome", human_record_outcome_node)
    graph.add_node("record_application_event", record_application_event_node)
    graph.add_node("calculate_outcome_analytics", calculate_outcome_analytics_node)
    graph.add_node("learning_agent", learning_agent_node)
    graph.add_node("persist_strategy_insight", persist_strategy_insight_node)
    graph.add_node("sync_mem0", sync_mem0_node)
    graph.add_node("outcome_update_complete", outcome_update_complete_node)

    graph.add_edge(START, "load_application")
    graph.add_conditional_edges(
        "load_application", route_after_load_application, {"continue": "human_record_outcome", "failed": END}
    )
    graph.add_conditional_edges(
        "human_record_outcome",
        route_after_human_record_outcome,
        {"continue": "record_application_event", "cancelled": END},
    )
    graph.add_edge("record_application_event", "calculate_outcome_analytics")
    graph.add_edge("calculate_outcome_analytics", "learning_agent")
    graph.add_edge("learning_agent", "persist_strategy_insight")
    graph.add_edge("persist_strategy_insight", "sync_mem0")
    graph.add_edge("sync_mem0", "outcome_update_complete")
    graph.add_edge("outcome_update_complete", END)

    return graph.compile(checkpointer=checkpointer)
