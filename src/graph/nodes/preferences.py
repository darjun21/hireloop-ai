"""
collect_preferences node.

Phase 3 has no UI yet, so preferences are supplied at graph invocation time
(the initial state's `preferences` dict) rather than collected interactively
here. This node's job is to normalize that input to a stable shape and make
its presence/absence observable in the Decision Trace, so a future UI node
can be swapped in later without changing anything downstream.
"""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from src.graph.helpers import trace_event
from src.graph.state import HireLoopState


def collect_preferences_node(state: HireLoopState, config: RunnableConfig) -> dict:
    raw = state.get("preferences") or {}
    normalized = {
        "target_roles": raw.get("target_roles", []),
        "target_locations": raw.get("target_locations", []),
        "preferred_work_modes": raw.get("preferred_work_modes", []),
        "employment_preferences": raw.get("employment_preferences", {}),
    }

    message = (
        f"Preferences confirmed: {len(normalized['target_roles'])} target role(s), "
        f"{len(normalized['target_locations'])} target location(s)."
    )
    return {
        "preferences": normalized,
        "decision_trace": [trace_event("preferences", "collect_preferences", message)],
        "current_step": "collect_preferences",
    }
