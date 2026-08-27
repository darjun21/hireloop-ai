"""
no_suitable_jobs: the graceful terminal state for "no suitable jobs remain
after filtering/scoring." This is an outcome of the agentic workflow, not
an exception -- it always records *why* (counts at each filtering stage)
and a concrete next action for the user.
"""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from src.graph.helpers import trace_event
from src.graph.state import HireLoopState
from src.models.workflow_status import WorkflowStatus


def no_suitable_jobs_node(state: HireLoopState, config: RunnableConfig) -> dict:
    counts = state.get("counts", {})
    reason = {
        "ingested": counts.get("ingested", 0),
        "duplicates_removed": counts.get("duplicates_removed", 0),
        "low_quality_excluded": counts.get("low_quality_excluded", 0),
        "scoring_failures": counts.get("scoring_failures", 0),
        "eligible_scored": counts.get("scored", 0),
        "recommendation": "Broaden target roles/location or provide another job batch.",
    }
    return {
        "workflow_status": WorkflowStatus.COMPLETED_WITH_NO_RESULTS.value,
        "no_suitable_jobs_reason": reason,
        "decision_trace": [
            trace_event("completion", "no_suitable_jobs", "No suitable jobs remain after filtering/scoring.", metadata=reason)
        ],
        "current_step": "no_suitable_jobs",
    }
