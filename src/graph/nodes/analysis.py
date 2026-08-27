"""
Nodes covering qualitative match analysis and deterministic ranking.

Ranking authority: rank_opportunities is the only node that produces the
final ordering (with tie-breakers) used for the human recommendation set.
analyze_matches runs first (per the Phase 3 node order) and picks its own
top-N by a simple score-descending sort purely to decide which jobs are
worth an LLM call — since both use final_score as the primary/only
practical sort key for non-tied jobs, the two orderings agree except in
the rare case of an exact tie at the N-th boundary, where it only affects
which of several equally-strong jobs got a qualitative analysis, never the
authoritative numeric ranking itself.
"""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from src.agents.match_analyst import MatchAnalystAgent
from src.config.workflow import MATCH_ANALYST_TOP_N, RECOMMENDATION_SET_SIZE
from src.graph.helpers import trace_event
from src.graph.state import HireLoopState
from src.llm.errors import HireLoopLLMError
from src.models.candidate import CandidateProfile
from src.models.job import JobPosting
from src.models.scoring import OpportunityScore

_CONFIDENCE_RANK = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}


def analyze_matches_node(state: HireLoopState, config: RunnableConfig) -> dict:
    llm_client = config["configurable"]["llm_client"]
    top_n = (config.get("configurable") or {}).get("match_analyst_top_n", MATCH_ANALYST_TOP_N)

    candidate = CandidateProfile(**state["candidate_profile"])
    scores = state.get("opportunity_scores", {})
    deduped_by_id = {d["job_id"]: d for d in state.get("deduped_jobs", [])}

    preview_ranked = sorted(scores.items(), key=lambda kv: (-kv[1]["final_score"], kv[0]))
    top_job_ids = [job_id for job_id, _ in preview_ranked[:top_n]]

    analyst = MatchAnalystAgent(llm_client)
    analyses: dict[str, dict] = {}
    failures = 0

    for job_id in top_job_ids:
        job = JobPosting(**deduped_by_id[job_id])
        score = OpportunityScore(**scores[job_id])
        try:
            analysis = analyst.analyze(candidate, job, score)
            analyses[job_id] = analysis.model_dump(mode="json")
        except HireLoopLLMError:
            failures += 1
            continue  # degrade gracefully: deterministic score/ranking is untouched either way

    if top_job_ids and failures == len(top_job_ids):
        message = (
            f"Match analysis unavailable for all {len(top_job_ids)} top opportunities "
            "(provider outage); deterministic rankings retained."
        )
    else:
        message = f"Top {len(top_job_ids)} opportunities selected for qualitative analysis; {len(analyses)} match analyses completed."
        if failures:
            message += f" {failures} failed and were marked unavailable."

    return {
        "match_analyses": analyses,
        "decision_trace": [trace_event("match_analysis", "analyze_matches", message, metadata={"analyzed": len(analyses), "failed": failures})],
        "current_step": "analyze_matches",
    }


def rank_opportunities_node(state: HireLoopState, config: RunnableConfig) -> dict:
    scores = state.get("opportunity_scores", {})
    quality_results = state.get("job_quality_results", {})

    def sort_key(job_id: str):
        score = scores[job_id]
        quality = quality_results.get(job_id, {})
        skill_match = score.get("components", {}).get("skill_match", {}).get("value", 0)
        return (
            -score["final_score"],
            _CONFIDENCE_RANK.get(score.get("confidence"), 3),
            -quality.get("quality_score", 0),
            -skill_match,
            job_id,
        )

    ranked_ids = sorted(scores.keys(), key=sort_key)
    recommended = ranked_ids[:RECOMMENDATION_SET_SIZE]

    message = f"{len(ranked_ids)} opportunities ranked; top {len(recommended)} selected as recommendations."
    return {
        "ranked_job_ids": ranked_ids,
        "decision_trace": [trace_event("ranking", "rank_opportunities", message)],
        "current_step": "rank_opportunities",
    }
