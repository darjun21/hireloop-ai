"""
HireLoop AI — Streamlit product.

"Every application makes the next one smarter."

This file is a thin UI layer over the existing backend: every action a
button takes either (a) reads already-computed state produced by the real
LangGraph workflows (src/graph/workflow.py), or (b) resumes those same
workflows via Command(resume=...). No scoring, matching, verification, or
analytics logic is reimplemented here — see src/services/ and src/agents/
for all of that.

This module also owns "HireLoop Mission Control" — a restrained dark/navy
visual system layered on top of the same widgets and the same state reads
described above (see the CSS block below and the small render helpers in
the "Visual system" section). None of that layer computes or fabricates
any number: every metric, badge, and status shown anywhere in this file is
read from `st.session_state.state`, `st.session_state.tracker`, or a
`decision_trace` / interrupt payload that the backend already produced.
"""

from __future__ import annotations

import hashlib
import tempfile
import uuid
from pathlib import Path

import streamlit as st
from langgraph.types import Command

from src.config.settings import load_settings
from src.config.workflow import DEFAULT_JOB_BATCH_PATH
from src.graph.checkpointing import get_sqlite_checkpointer
from src.graph.workflow import build_outcome_update_workflow, build_workflow
from src.llm.provider import get_llm_client
from src.models.enums import EmploymentType, WorkMode
from src.services.application_tracker import ApplicationTrackerService
from src.services.database import get_connection, init_schema
from src.services.demo_application_loader import load_demo_application_history
from src.services.live_job_discovery import run_live_discovery
from src.services.memory_service import MemoryService, MockMemoryProvider
from src.services.outcome_analytics import compute_outcome_analytics

DEMO_RESUME_PATH = "data/sample_candidate/demo_resume.txt"
PAGES = ["Dashboard", "Candidate", "Opportunities", "Resume Studio", "Applications", "Strategy", "System / Demo"]

TRUTH_STATUS_LABELS = {
    "VERIFIED": "✓ VERIFIED",
    "PARTIALLY_SUPPORTED": "△ PARTIALLY SUPPORTED",
    "UNSUPPORTED": "✕ UNSUPPORTED",
    "NEEDS_HUMAN_CONFIRMATION": "? NEEDS HUMAN CONFIRMATION",
}

STAGES = ["DISCOVER", "SCORE", "TAILOR", "VERIFY", "APPLY", "TRACK", "LEARN", "IMPROVE"]

# UI-only constant: which HireLoop Loop stage a given status badge belongs
# to, purely for the "Behind the Decision" / stage-strip highlighting. Not
# used for any scoring, routing, or business decision.
_BADGE_KIND = {
    "COMPLETE": "success",
    "VERIFIED": "success",
    "AVAILABLE": "success",
    "CONFIGURED": "success",
    "WORKING": "info",
    "MOCK": "info",
    "PARTIALLY_SUPPORTED": "warning",
    "NEEDS HUMAN": "warning",
    "NEEDS_HUMAN_CONFIRMATION": "warning",
    "DEGRADED": "warning",
    "UNSUPPORTED": "danger",
    "UNAVAILABLE": "danger",
    "WAITING": "neutral",
}


# ---------------------------------------------------------------------------
# Session bootstrap — one set of backend services shared by every page
# ---------------------------------------------------------------------------


def _init_session() -> None:
    if "booted" in st.session_state:
        return

    settings = load_settings()
    llm_client = get_llm_client(settings)

    db_conn = get_connection(":memory:")
    init_schema(db_conn)
    tracker = ApplicationTrackerService(db_conn)

    memory_service = MemoryService(MockMemoryProvider()) if settings.demo_mode else MemoryService(None)

    st.session_state.booted = True
    st.session_state.settings = settings
    st.session_state.llm_client = llm_client
    st.session_state.tracker = tracker
    st.session_state.memory_service = memory_service
    st.session_state.checkpointer = get_sqlite_checkpointer(":memory:")
    st.session_state.graph = build_workflow(st.session_state.checkpointer)
    st.session_state.outcome_checkpointer = get_sqlite_checkpointer(":memory:")
    st.session_state.outcome_graph = build_outcome_update_workflow(st.session_state.outcome_checkpointer)
    st.session_state.thread_id = None
    st.session_state.state = {}
    st.session_state.interrupt = None
    st.session_state.outcome_thread_id = None
    st.session_state.outcome_state = {}
    st.session_state.outcome_interrupt = None
    st.session_state.page = "Dashboard"


def _graph_config() -> dict:
    configurable = {
        "thread_id": st.session_state.thread_id,
        "llm_client": st.session_state.llm_client,
        "application_tracker": st.session_state.tracker,
        "job_batch_path": DEFAULT_JOB_BATCH_PATH,
    }
    # Optional live-discovery override (You.com). Only ever set by the
    # "Search Live Jobs" button handler in page_opportunities(); absent in
    # every other flow, including the full DEMO_MODE path.
    override = st.session_state.get("job_source_override")
    if override:
        configurable["job_source_override"] = override
    return {"configurable": configurable}


def _apply_result(result: dict) -> None:
    st.session_state.state = result
    st.session_state.interrupt = result["__interrupt__"][0].value if "__interrupt__" in result else None


def start_new_run(resume_file_path: str, target_roles: list[str], work_modes: list[str]) -> None:
    thread_id = f"ui-{uuid.uuid4().hex[:10]}"
    st.session_state.thread_id = thread_id
    initial_state = {
        "run_id": thread_id,
        "candidate_id": f"cand-{thread_id}",
        "resume_file_path": resume_file_path,
        "preferences": {"target_roles": target_roles, "preferred_work_modes": work_modes},
        "workflow_status": "NOT_STARTED",
    }
    result = st.session_state.graph.invoke(initial_state, config=_graph_config())
    _apply_result(result)


def resume_graph(response: dict) -> None:
    result = st.session_state.graph.invoke(Command(resume=response), config=_graph_config())
    _apply_result(result)


def state() -> dict:
    return st.session_state.get("state", {}) or {}


def decision_trace_panel(events: list[dict], key: str) -> None:
    """Kept for the raw-event list embedded inside `_behind_the_decision`
    below; pages call `_behind_the_decision` directly, which wraps this."""
    with st.expander("View Full Decision Trace", expanded=False):
        if not events:
            st.caption("No events yet.")
        for event in events:
            st.markdown(f"- {event['message']}")


# ---------------------------------------------------------------------------
# Visual system — "HireLoop Mission Control"
#
# One CSS block, injected once near the top of main(), plus a handful of
# small render helpers. Every helper below only ever formats values it is
# handed by a caller that read them from real state — none of these
# functions compute, guess, or hardcode a metric.
# ---------------------------------------------------------------------------

_CSS = """
<style>
:root {
    --hl-bg: #0b1220;
    --hl-bg-elevated: #121b2e;
    --hl-bg-elevated-2: #17223a;
    --hl-border: #22304a;
}
.stApp {
    background-color: #0b1220;
    color: #e7ecf6;
}
[data-testid="stSidebar"] {
    background-color: #0e1626;
    border-right: 1px solid #22304a;
}
[data-testid="stSidebar"] * { color: #d7e0f0; }
.stApp h1, .stApp h2, .stApp h3, .stApp h4 {
    color: #f2f5fb;
    letter-spacing: 0.01em;
}
.stApp p, .stApp label, .stApp span, .stApp li { color: #d7e0f0; }
.stApp small, .stApp .stCaption, [data-testid="stCaptionContainer"] {
    color: #8fa0bd !important;
}
hr { border-color: #22304a !important; }

[data-testid="stMetric"] {
    background-color: #121b2e;
    border: 1px solid #22304a;
    border-radius: 10px;
    padding: 0.8rem 1rem;
}
[data-testid="stMetricLabel"] { color: #8fa0bd !important; }
[data-testid="stMetricValue"] { color: #3ea6ff !important; }

[data-testid="stVerticalBlockBorderWrapper"] > div > [data-testid="stVerticalBlock"] {
    border-radius: 10px;
}
div[data-testid="stExpander"] {
    background-color: #121b2e;
    border: 1px solid #22304a !important;
    border-radius: 10px;
}

.stButton > button {
    border-radius: 8px;
    border: 1px solid #2c3e5c;
    background-color: #17223a;
    color: #e7ecf6;
}
.stButton > button[kind="primary"] {
    background-color: #3ea6ff;
    border-color: #3ea6ff;
    color: #071018;
    font-weight: 600;
}

.hl-header {
    display: flex;
    align-items: baseline;
    gap: 0.75rem;
    flex-wrap: wrap;
    padding: 0.9rem 1.1rem;
    margin-bottom: 0.6rem;
    background: linear-gradient(90deg, #101a2e 0%, #0e1626 100%);
    border: 1px solid #22304a;
    border-radius: 12px;
}
.hl-header-title { font-size: 1.4rem; font-weight: 700; color: #f2f5fb; }
.hl-header-tagline { color: #8fa0bd; font-size: 0.95rem; }
.hl-header-spacer { flex-grow: 1; }

.hl-badge {
    display: inline-block;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.03em;
    padding: 0.18rem 0.55rem;
    border-radius: 999px;
    border: 1px solid transparent;
    text-transform: uppercase;
    white-space: nowrap;
}
.hl-badge-success { background: rgba(53, 201, 143, 0.14); color: #4fe0ac; border-color: rgba(53, 201, 143, 0.4); }
.hl-badge-warning { background: rgba(240, 180, 41, 0.14); color: #f6c847; border-color: rgba(240, 180, 41, 0.4); }
.hl-badge-danger  { background: rgba(240, 87, 107, 0.14); color: #ff7c8f; border-color: rgba(240, 87, 107, 0.4); }
.hl-badge-info    { background: rgba(62, 166, 255, 0.14); color: #7cc3ff; border-color: rgba(62, 166, 255, 0.4); }
.hl-badge-neutral { background: rgba(143, 160, 189, 0.14); color: #a9b7cd; border-color: rgba(143, 160, 189, 0.35); }
.hl-badge-mode-demo { background: rgba(240, 180, 41, 0.16); color: #f6c847; border-color: rgba(240, 180, 41, 0.5); }
.hl-badge-mode-live { background: rgba(53, 201, 143, 0.16); color: #4fe0ac; border-color: rgba(53, 201, 143, 0.5); }

.hl-stage-strip {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
    margin: 0.4rem 0 1.1rem 0;
}
.hl-stage-item {
    flex: 1 1 auto;
    text-align: center;
    padding: 0.4rem 0.3rem;
    border-radius: 8px;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    background-color: #121b2e;
    border: 1px solid #22304a;
    color: #6c7d9a;
}
.hl-stage-item.hl-stage-active {
    background-color: rgba(62, 166, 255, 0.16);
    border-color: #3ea6ff;
    color: #7cc3ff;
}

.hl-decision-banner {
    border: 1px solid #f0b429;
    background: rgba(240, 180, 41, 0.08);
    border-radius: 10px;
    padding: 0.9rem 1.1rem;
    margin: 0.6rem 0 0.8rem 0;
}
.hl-decision-banner .hl-decision-title {
    font-weight: 700;
    color: #f6c847;
    letter-spacing: 0.03em;
    font-size: 0.85rem;
    margin-bottom: 0.35rem;
}
.hl-decision-banner p { margin: 0.15rem 0; color: #e7ecf6; }
.hl-decision-banner b { color: #f2f5fb; }

.hl-hero {
    border: 1px solid #22304a;
    background: linear-gradient(180deg, #131f36 0%, #101a2e 100%);
    border-radius: 12px;
    padding: 1rem 1.1rem;
    margin-bottom: 0.9rem;
}
.hl-hero-title { font-weight: 700; font-size: 1.02rem; color: #f2f5fb; margin-bottom: 0.5rem; }

.hl-claim-flow {
    border: 1px solid #22304a;
    border-radius: 10px;
    padding: 0.75rem 0.9rem;
    margin: 0.4rem 0;
    background-color: #121b2e;
}
.hl-claim-flow .hl-claim-step { color: #8fa0bd; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.04em; }
.hl-claim-flow .hl-claim-text { color: #e7ecf6; margin: 0.15rem 0 0.45rem 0; }

.hl-pipeline {
    display: flex;
    flex-wrap: wrap;
    gap: 0.35rem;
    margin: 0.5rem 0 0.9rem 0;
}
.hl-pipeline-step {
    flex: 1 1 auto;
    text-align: center;
    padding: 0.35rem 0.3rem;
    border-radius: 8px;
    font-size: 0.7rem;
    font-weight: 600;
    background-color: #121b2e;
    border: 1px solid #22304a;
    color: #6c7d9a;
}
.hl-pipeline-step.hl-pipeline-active {
    background-color: rgba(62, 166, 255, 0.16);
    border-color: #3ea6ff;
    color: #7cc3ff;
}
</style>
"""


def _inject_css() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def _badge_html(label: str) -> str:
    kind = _BADGE_KIND.get(label, "neutral")
    return f'<span class="hl-badge hl-badge-{kind}">{label}</span>'


def _confidence_badge(value: str) -> str:
    return {"HIGH": "🟢 HIGH", "MEDIUM": "🟡 MEDIUM", "LOW": "🔴 LOW"}.get(value, value)


def _infer_stage(page: str, s: dict, interrupt: dict | None) -> str:
    """Best-effort mapping of "where the demo currently is" onto the
    DISCOVER..IMPROVE strip. Primarily driven by which page is open (the
    strip is a navigation aid, not a workflow-status readout), refined by
    a couple of cheap, real state checks where that's unambiguous. When a
    page could plausibly represent more than one stage (Resume Studio
    spans TAILOR/VERIFY/APPLY depending on where the interrupt is), the
    real interrupt/state fields below decide, never a guess."""
    if page == "Candidate":
        return "DISCOVER"
    if page == "Opportunities":
        return "SCORE"
    if page == "Resume Studio":
        if interrupt and ("clarification_required" in interrupt or "modifications" in interrupt):
            return "VERIFY"
        if s.get("current_resume_version_id"):
            return "APPLY"
        return "TAILOR"
    if page == "Applications":
        return "TRACK"
    if page == "Strategy":
        return "LEARN"
    if page == "System / Demo":
        return "IMPROVE"
    # Dashboard: highlight the furthest stage this run has actually reached.
    if s.get("current_resume_version_id"):
        return "APPLY"
    if s.get("proposed_modifications"):
        return "VERIFY"
    if s.get("selected_job_id"):
        return "TAILOR"
    if s.get("opportunity_scores"):
        return "SCORE"
    return "DISCOVER"


def _stage_nav(active_stage: str) -> None:
    items = "".join(
        f'<div class="hl-stage-item{" hl-stage-active" if stage == active_stage else ""}">{stage}</div>'
        for stage in STAGES
    )
    st.markdown(f'<div class="hl-stage-strip">{items}</div>', unsafe_allow_html=True)


def _header_banner() -> None:
    settings = st.session_state.settings
    if settings.demo_mode:
        mode_html = '<span class="hl-badge hl-badge-mode-demo">DEMO MODE — SYNTHETIC DATA</span>'
    else:
        mode_html = '<span class="hl-badge hl-badge-mode-live">LIVE MODE</span>'
    st.markdown(
        '<div class="hl-header">'
        '<span class="hl-header-title">HireLoop AI</span>'
        '<span class="hl-header-tagline">Every application makes the next one smarter.</span>'
        '<span class="hl-header-spacer"></span>'
        f"{mode_html}"
        "</div>",
        unsafe_allow_html=True,
    )


def _human_decision_banner(completed: list[str], decision: str, why: str) -> None:
    completed_html = "".join(f"<p>✓ {line}</p>" for line in completed)
    st.markdown(
        '<div class="hl-decision-banner">'
        '<div class="hl-decision-title">⚠ HUMAN DECISION REQUIRED</div>'
        f"{completed_html}"
        f"<p><b>Waiting on:</b> {decision}</p>"
        f"<p><b>Why a human:</b> {why}</p>"
        "</div>",
        unsafe_allow_html=True,
    )


def _agent_activity_rail(s: dict, interrupt: dict | None) -> None:
    st.markdown("#### Agent Activity")
    profile = s.get("candidate_profile")
    counts = s.get("counts", {}) or {}
    deduped = s.get("deduped_jobs", [])
    match_analyses = s.get("match_analyses", {})
    proposed_mods = s.get("proposed_modifications", [])
    rejected_mods = s.get("rejected_modifications", [])
    tg_results = s.get("truth_guard_results", {})
    insights = st.session_state.tracker.list_strategy_insights()

    rows: list[tuple[str, str, str]] = []

    if profile:
        rows.append(("Profile Agent", "COMPLETE", f"{len(profile.get('skills', []))} skill(s) identified from resume."))
    else:
        rows.append(("Profile Agent", "WAITING", "Awaiting a resume upload on the Candidate page."))

    if counts.get("ingested"):
        rows.append(("Job Scout — Discovery", "COMPLETE", f"{counts.get('ingested', 0)} job(s) ingested, {len(deduped)} after dedup."))
    else:
        rows.append(("Job Scout — Discovery", "WAITING", "No search run yet."))

    if match_analyses:
        rows.append(("Match Analyst", "COMPLETE", f"Top {len(match_analyses)} opportunity(ies) analyzed."))
    elif s.get("opportunity_scores"):
        rows.append(("Match Analyst", "WORKING", "Scoring complete; deep analysis pending."))
    else:
        rows.append(("Match Analyst", "WAITING", "No opportunities scored yet."))

    if proposed_mods:
        rows.append(("Resume Tailor", "COMPLETE", f"{len(proposed_mods)} modification(s) proposed."))
    elif s.get("selected_job_id"):
        rows.append(("Resume Tailor", "WORKING", "Opportunity selected; tailoring in progress."))
    else:
        rows.append(("Resume Tailor", "WAITING", "No opportunity selected yet."))

    needs_human = bool(interrupt and ("clarification_required" in interrupt or "modifications" in interrupt))
    if needs_human:
        rows.append(("Truth Guard", "NEEDS HUMAN", "A claim needs human confirmation or approval before it can proceed."))
    elif tg_results:
        verified = sum(1 for r in tg_results.values() if r["status"] == "VERIFIED")
        rows.append(("Truth Guard", "COMPLETE", f"{verified} verified, {len(rejected_mods)} rejected of {len(tg_results)} checked."))
    else:
        rows.append(("Truth Guard", "WAITING", "No claims submitted for verification yet."))

    if insights:
        rows.append(("Learning Agent", "COMPLETE", f"{len(insights)} strategy insight(s) generated."))
    else:
        rows.append(("Learning Agent", "WAITING", "No outcomes recorded yet."))

    cols = st.columns(3)
    for i, (name, status_label, note) in enumerate(rows):
        with cols[i % 3]:
            with st.container(border=True):
                st.markdown(f"**{name}**")
                st.markdown(_badge_html(status_label), unsafe_allow_html=True)
                st.caption(note)


def _behind_the_decision(s: dict, key: str) -> None:
    st.markdown("### Behind the Decision")
    counts = s.get("counts", {}) or {}
    steps: list[tuple[str, int]] = []
    if "ingested" in counts:
        steps.append(("Ingested", counts["ingested"]))
    if "unique_after_dedup" in counts:
        steps.append(("Deduplicated", counts["unique_after_dedup"]))
    if "eligible_after_quality" in counts:
        steps.append(("Quality Approved", counts["eligible_after_quality"]))
    if "scored" in counts:
        steps.append(("Scored", counts["scored"]))
    if s.get("match_analyses"):
        steps.append(("Analyzed", len(s["match_analyses"])))
    if s.get("selected_job_id"):
        steps.append(("Selected", 1))
    if s.get("proposed_modifications"):
        steps.append(("Modifications Proposed", len(s["proposed_modifications"])))
    if s.get("rejected_modifications"):
        steps.append(("Rejected by Truth Guard", len(s["rejected_modifications"])))
    if s.get("approved_modification_ids"):
        steps.append(("Approved", len(s["approved_modification_ids"])))

    if steps:
        cols = st.columns(len(steps))
        for col, (label, value) in zip(cols, steps):
            col.metric(label, value)
    else:
        st.caption("No pipeline activity recorded yet for this run.")

    decision_trace_panel(s.get("decision_trace", []), key)


def _learning_loop_strip() -> None:
    steps = ["APPLICATION", "OUTCOME", "ANALYTICS", "LEARNING", "STRATEGY", "NEXT SEARCH"]
    items = "".join(f'<div class="hl-pipeline-step">{step}</div>' for step in steps)
    st.markdown(f'<div class="hl-pipeline">{items}</div>', unsafe_allow_html=True)
    st.caption("Illustrative — shows how one recorded outcome eventually reshapes the next search's strategy insights.")


def _application_pipeline_strip(current_status: str) -> None:
    steps = ["SAVED", "APPLIED", "RESPONSE", "INTERVIEW", "FINAL ROUND", "OFFER"]
    normalized = (current_status or "").upper().replace("_", " ")
    items = []
    for step in steps:
        active = step in normalized or normalized in step
        cls = "hl-pipeline-step hl-pipeline-active" if active else "hl-pipeline-step"
        items.append(f'<div class="{cls}">{step}</div>')
    st.markdown(f'<div class="hl-pipeline">{"".join(items)}</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


def page_dashboard() -> None:
    st.header("HireLoop Mission Control")
    settings = st.session_state.settings
    if settings.demo_mode:
        st.info("**DEMO MODE — Synthetic Data.** Statistics below combine any live session activity with clearly-labeled seeded demo history.")

    s = state()
    scores = s.get("opportunity_scores", {})
    ranked = s.get("ranked_job_ids", [])
    high_priority = sum(1 for jid in ranked if scores.get(jid, {}).get("recommendation") == "HIGH_PRIORITY")

    demo_records = load_demo_application_history() if settings.demo_mode else []
    live_records = st.session_state.tracker.get_applications_with_history(include_demo_data=False)
    analytics = compute_outcome_analytics(demo_records + live_records)

    total_positive = sum(g.positive_responses for g in analytics.by_role_family.values())
    total_interviews = sum(g.interviews for g in analytics.by_role_family.values())
    total_offers = sum(g.offers for g in analytics.by_role_family.values())
    response_rate = (total_positive / analytics.total_resolved) if analytics.total_resolved else 0.0
    interview_rate = (total_interviews / analytics.total_resolved) if analytics.total_resolved else 0.0

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Opportunities Analyzed", len(scores))
    col2.metric("Best Fits", high_priority)
    col3.metric("Applications", analytics.total_applications)
    col4.metric("Interviews", total_interviews)
    col5.metric("Interview Rate", f"{interview_rate * 100:.1f}%")

    st.caption(
        f"{analytics.total_resolved} resolved application(s) · "
        f"{total_positive} positive response(s) · {total_offers} offer(s) · "
        f"overall response rate {response_rate * 100:.1f}%."
    )

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("#### Top Opportunity")
        if not scores:
            st.caption("No opportunities scored yet. Run a search from the Candidate page.")
        else:
            deduped_by_id = {j["job_id"]: j for j in s.get("deduped_jobs", [])}
            top_id = max(scores, key=lambda jid: scores[jid]["final_score"])
            top = scores[top_id]
            job = deduped_by_id.get(top_id, {})
            with st.container(border=True):
                st.markdown(f"**{job.get('title', '?')}** — {job.get('company', '?')}")
                st.caption(job.get("location") or "Location unknown")
                m1, m2, m3 = st.columns(3)
                m1.metric("HireLoop Score", f"{top['final_score']:.1f}")
                m2.markdown(f"**Recommendation**  \n{top['recommendation']}")
                m3.markdown(f"**Confidence**  \n{_confidence_badge(top['confidence'])}")

    with col_b:
        st.markdown("#### Latest HireLoop Insight")
        insights = st.session_state.tracker.list_strategy_insights()
        if not insights:
            st.caption("No strategy insights recorded yet — record an outcome to generate one.")
        else:
            _render_insight_card(insights[0].model_dump(mode="json"))

    st.divider()
    _agent_activity_rail(s, st.session_state.interrupt)


def page_candidate() -> None:
    st.header("Candidate")
    settings = st.session_state.settings

    with st.form("candidate_form"):
        uploaded = st.file_uploader("Upload resume (PDF, DOCX, or TXT)", type=["pdf", "docx", "txt"])
        use_demo = st.checkbox("Use the seeded demo candidate instead", value=settings.demo_mode)
        target_roles = st.text_input("Target roles (comma-separated)", value="AI Engineer")
        work_mode = st.multiselect("Preferred work mode", [m.value for m in WorkMode], default=[WorkMode.REMOTE.value])
        submitted = st.form_submit_button("Run HireLoop Search")

    if submitted:
        resume_path = DEMO_RESUME_PATH
        if uploaded is not None and not use_demo:
            suffix = Path(uploaded.name).suffix
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(uploaded.getvalue())
                resume_path = tmp.name
        roles = [r.strip() for r in target_roles.split(",") if r.strip()]
        # Remembered so the Opportunities page's optional LIVE SEARCH mode
        # can re-run the same candidate profile/preferences with a
        # job_source_override, without duplicating the profile-building
        # steps here.
        st.session_state.last_run_params = {"resume_path": resume_path, "roles": roles, "work_mode": work_mode}
        st.session_state.job_source_override = None
        with st.spinner("Parsing resume, building profile, and ranking opportunities..."):
            start_new_run(resume_path, roles, work_mode)
        st.success("Search complete — see the Opportunities page.")

    s = state()
    profile = s.get("candidate_profile")
    if not profile:
        st.caption("No candidate profile yet. Run a search above.")
        return

    validation = s.get("profile_validation", {})
    if validation.get("warnings"):
        st.warning("Extraction warnings:\n" + "\n".join(f"- {w}" for w in validation["warnings"]))
    if validation.get("errors"):
        st.error("Extraction errors:\n" + "\n".join(f"- {e}" for e in validation["errors"]))

    st.subheader(profile.get("name", "Candidate"))
    st.write(profile.get("professional_summary", ""))

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Skills** *(resume-derived)*")
        st.write(", ".join(s["name"] for s in profile.get("skills", [])) or "—")

        st.markdown("**Work Experience** *(resume-derived)*")
        for exp in profile.get("work_experience", []):
            st.markdown(f"- **{exp['title']}** at {exp['company']} ({exp.get('start_date') or '?'} – {exp.get('end_date') or 'present'})")

        st.markdown("**Projects** *(resume-derived)*")
        for proj in profile.get("projects", []):
            st.markdown(f"- **{proj['name']}**: {proj.get('description') or ''}")

    with col2:
        st.markdown("**Education** *(resume-derived)*")
        for edu in profile.get("education", []):
            st.markdown(f"- {edu.get('degree') or ''} — {edu['institution']}")

        st.markdown("**Certifications** *(resume-derived)*")
        for cert in profile.get("certifications", []):
            st.markdown(f"- {cert['name']}")

        st.markdown("---")
        st.markdown("**Target roles** *(candidate-provided preference)*")
        st.write(", ".join(profile.get("target_roles", [])) or "—")
        st.markdown("**Target locations** *(candidate-provided preference)*")
        st.write(", ".join(profile.get("target_locations", [])) or "—")
        st.markdown("**Preferred work mode** *(candidate-provided preference)*")
        st.write(", ".join(profile.get("preferred_work_modes", [])) or "—")

    _behind_the_decision(s, "candidate")


def _job_source_control() -> None:
    """Optional live job discovery via You.com — read-only, opt-in, never
    part of the DEMO_MODE certification path. See docs/DECISIONS.md and
    docs/ARCHITECTURE.md's "Live Job Discovery" section."""
    settings = st.session_state.settings
    with st.expander("LIVE WEB DISCOVERY — Powered by You.com (optional)", expanded=False):
        mode = st.radio("Job Source", ["DEMO JOBS", "LIVE SEARCH"], horizontal=True, key="job_source_mode", label_visibility="collapsed")

        if mode == "DEMO JOBS":
            st.caption("Using the offline seeded demo job batch (data/sample_jobs.json).")
            return

        if not settings.you_search_enabled or not settings.ydc_api_key:
            st.warning(
                "Live search is not configured (set YOU_SEARCH_ENABLED=true and YDC_API_KEY to enable it). "
                "Falling back to DEMO JOBS."
            )
            return

        last_params = st.session_state.get("last_run_params")
        if not last_params:
            st.caption("Run a search from the Candidate page first, then come back here to try LIVE SEARCH.")
            return

        col1, col2, col3 = st.columns(3)
        role = col1.text_input("Target role", value=(last_params["roles"][0] if last_params["roles"] else ""))
        location = col2.text_input("Location", value="")
        work_mode_choice = col3.selectbox("Work mode", ["Any"] + [m.value for m in WorkMode])
        col4, col5 = st.columns(2)
        freshness = col4.selectbox("Freshness", ["month", "week"], index=0)
        max_results = col5.number_input("Max results", min_value=1, max_value=settings.you_search_max_results, value=min(5, settings.you_search_max_results))

        cache_key = (role.strip().lower(), location.strip().lower(), work_mode_choice, freshness, int(max_results))
        cache = st.session_state.setdefault("live_search_cache", {})

        # Only this button click may call You.com — a bare Streamlit rerun
        # from any other widget interaction must never re-issue a paid
        # search. The cache additionally prevents a second identical paid
        # call within the same session even across repeated clicks.
        if st.button("Search Live Jobs", type="primary"):
            if cache_key in cache:
                outcome = cache[cache_key]
            else:
                with st.spinner("Searching live jobs via You.com..."):
                    outcome = run_live_discovery(
                        settings=settings,
                        target_roles=[role] if role.strip() else last_params["roles"],
                        location=location or None,
                        work_mode=None if work_mode_choice == "Any" else work_mode_choice,
                        skills=None,
                        freshness=freshness,
                        max_results=int(max_results),
                    )
                cache[cache_key] = outcome

            st.session_state.live_discovery_events = outcome.events

            if outcome.failed:
                st.error("You.com search unavailable; live discovery stopped safely. You can retry or use DEMO JOBS instead.")
            elif not outcome.job_dicts:
                st.warning("No live results classified as likely job postings. Try different search terms, or use DEMO JOBS.")
            else:
                st.session_state.job_source_override = outcome.job_dicts
                with st.spinner("Re-running HireLoop with live-discovered jobs..."):
                    start_new_run(last_params["resume_path"], last_params["roles"], last_params["work_mode"])
                st.success(f"{len(outcome.job_dicts)} live job(s) moved into scoring.")
                st.rerun()

        if st.session_state.get("live_discovery_events"):
            with st.expander("Live discovery trace", expanded=False):
                for line in st.session_state.live_discovery_events:
                    st.markdown(f"- {line}")


def page_opportunities() -> None:
    st.header("Opportunities")
    _job_source_control()
    s = state()
    scores = s.get("opportunity_scores", {})
    if not scores:
        st.caption("No opportunities yet. Run a search from the Candidate page.")
        return

    deduped_by_id = {j["job_id"]: j for j in s.get("deduped_jobs", [])}
    quality_by_id = s.get("job_quality_results", {})
    analyses = s.get("match_analyses", {})

    col1, col2, col3, col4 = st.columns(4)
    role_family_filter = col1.text_input("Role family contains", "")
    rec_filter = col2.selectbox("Recommendation", ["All", "HIGH_PRIORITY", "STRONG_MATCH", "CONSIDER", "LOW_PRIORITY"])
    mode_filter = col3.selectbox("Work mode", ["All"] + [m.value for m in WorkMode])
    min_score = col4.slider("Minimum score", 0, 100, 0)

    rows = []
    for job_id, score in scores.items():
        job = deduped_by_id.get(job_id, {})
        if role_family_filter and role_family_filter.lower() not in job.get("title", "").lower():
            continue
        if rec_filter != "All" and score["recommendation"] != rec_filter:
            continue
        if mode_filter != "All" and job.get("work_mode") != mode_filter:
            continue
        if score["final_score"] < min_score:
            continue
        rows.append((job_id, job, score))

    rows.sort(key=lambda r: -r[2]["final_score"])

    st.caption(f"{len(rows)} opportunity(ies) shown, sorted by score descending.")

    for job_id, job, score in rows:
        quality = quality_by_id.get(job_id, {})
        analysis = analyses.get(job_id)
        with st.container(border=True):
            top = st.columns([3, 1, 1])
            top[0].markdown(f"**{job.get('title', '?')}** — {job.get('company', '?')}")
            top[0].caption(f"{job.get('location') or 'Location unknown'} · {job.get('work_mode') or 'Work mode unknown'}")
            if job.get("source") == "you_com":
                domain = (job.get("metadata") or {}).get("source_domain") or job.get("url") or "unknown source"
                top[0].caption(f"Source: Web discovery / You.com — {domain} (not verified active; discovered via live search)")
            top[1].metric("HireLoop Score", f"{score['final_score']:.1f}")
            top[2].markdown(f"**{score['recommendation']}**  \nConfidence: {_confidence_badge(score['confidence'])}")

            if quality.get("requirement_completeness") == "LOW":
                st.caption("⚠ Limited job-description evidence. Match confidence is reduced.")

            if analysis:
                cols = st.columns(2)
                cols[0].markdown("**Why HireLoop Likes It**")
                for line in analysis.get("strengths", [])[:3]:
                    cols[0].markdown(f"- {line}")
                cols[1].markdown("**Watch Out For**")
                for line in analysis.get("gaps", [])[:3]:
                    cols[1].markdown(f"- {line}")

            if st.button("VIEW INTELLIGENCE", key=f"detail-{job_id}"):
                st.session_state.selected_detail_job_id = job_id
                st.session_state.page = "Opportunities"

    detail_job_id = st.session_state.get("selected_detail_job_id")
    if detail_job_id and detail_job_id in scores:
        st.divider()
        _render_opportunity_detail(detail_job_id, deduped_by_id, scores, quality_by_id, analyses)

    _behind_the_decision(s, "opportunities")


def _render_opportunity_detail(job_id, deduped_by_id, scores, quality_by_id, analyses) -> None:
    job = deduped_by_id.get(job_id, {})
    score = scores[job_id]
    quality = quality_by_id.get(job_id, {})
    analysis = analyses.get(job_id)

    st.subheader(f"Opportunity Intelligence — {job.get('title', '?')} at {job.get('company', '?')}")
    if job.get("source") == "you_com":
        st.caption(
            f"Source: Web discovery / You.com — [{job.get('url')}]({job.get('url')}). "
            "Discovered via live search; not confirmed to still be active or accepting applications."
        )

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Final score", f"{score['final_score']:.1f}")
    col2.markdown(f"**Recommendation**  \n{score['recommendation']}")
    col3.markdown(f"**Confidence**  \n{_confidence_badge(score['confidence'])}")
    col4.caption(f"Scoring model: {score['scoring_version']}")

    st.markdown("**Opportunity DNA** — the 7 real components behind the score above")
    for name, comp in score.get("components", {}).items():
        label = name.replace("_", " ").title()
        value = comp["value"]
        st.markdown(f"{label} — {value:.1f}/100 · weight {comp['weight'] * 100:.0f}% · contributes {comp['weighted_contribution']:.1f} pts")
        st.progress(min(max(value / 100.0, 0.0), 1.0))

    if quality.get("requirement_completeness") == "LOW":
        st.warning("Limited job-description evidence. Match confidence is reduced.")

    if analysis:
        st.markdown("**Why this matches**")
        st.write(analysis.get("explanation", ""))
        cols = st.columns(2)
        cols[0].markdown("**Why HireLoop Likes It**")
        for line in analysis.get("strengths", []):
            cols[0].markdown(f"- {line}")
        cols[1].markdown("**Watch Out For**")
        for line in analysis.get("gaps", []) + analysis.get("risks", []):
            cols[1].markdown(f"- {line}")

    interrupt = st.session_state.interrupt
    if interrupt and "eligible_selections" in interrupt and job_id in {item["job_id"] for item in interrupt["eligible_selections"]}:
        _human_decision_banner(
            completed=[
                "HireLoop scored and analyzed every eligible opportunity from this search.",
                f"{len(interrupt['eligible_selections'])} opportunity(ies) are eligible for selection right now.",
            ],
            decision="Which opportunity (if any) to pursue next.",
            why="HireLoop never applies on your behalf — selecting a target opportunity is a consequential decision reserved for a human.",
        )
        if st.button("SELECT OPPORTUNITY", type="primary", key=f"select-{job_id}"):
            resume_graph({"action": "SELECT", "job_id": job_id})
            st.rerun()
    else:
        st.caption("This job is not in the current eligible selection set (already selected, or a new search is needed).")


def page_resume_studio() -> None:
    st.header("Resume Studio")
    st.caption("Tailored for relevance. Guarded by evidence.")
    s = state()
    interrupt = st.session_state.interrupt

    if not s.get("selected_job_id"):
        st.caption("Select an opportunity first (Opportunities page).")
        return

    tg_results = s.get("truth_guard_results", {})
    counts = {"VERIFIED": 0, "PARTIALLY_SUPPORTED": 0, "UNSUPPORTED": 0, "NEEDS_HUMAN_CONFIRMATION": 0}
    for r in tg_results.values():
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    modifications = {m["modification_id"]: m for m in s.get("proposed_modifications", [])}
    rejected = {r["modification_id"]: r for r in s.get("rejected_modifications", [])}

    st.markdown('<div class="hl-hero">', unsafe_allow_html=True)
    st.markdown('<div class="hl-hero-title">Truth Guard</div>', unsafe_allow_html=True)
    cols = st.columns(4)
    cols[0].metric("Verified", counts["VERIFIED"])
    cols[1].metric("Partially Supported", counts["PARTIALLY_SUPPORTED"])
    cols[2].metric("Blocked (Unsupported)", counts["UNSUPPORTED"])
    cols[3].metric("Needs Confirmation", counts["NEEDS_HUMAN_CONFIRMATION"])

    # One real blocked claim next to one real verified claim, for contrast.
    example_rejected = next(iter(rejected.values()), None)
    example_verified_id = next((mid for mid, r in tg_results.items() if r.get("status") == "VERIFIED"), None)
    if example_rejected or example_verified_id:
        flow_cols = st.columns(2)
        if example_rejected:
            mod = modifications.get(example_rejected["modification_id"])
            claim_text = example_rejected.get("claim") or (mod["proposed_text"] if mod else example_rejected["modification_id"])
            with flow_cols[0]:
                st.markdown(
                    '<div class="hl-claim-flow">'
                    '<div class="hl-claim-step">AI Proposed</div>'
                    f'<div class="hl-claim-text">{claim_text}</div>'
                    '<div class="hl-claim-step">Truth Guard</div>'
                    f'<div class="hl-claim-text">{example_rejected.get("reason", "")}</div>'
                    '<div class="hl-claim-step">Result</div>'
                    f'<div class="hl-claim-text">{_badge_html("UNSUPPORTED")}</div>'
                    "</div>",
                    unsafe_allow_html=True,
                )
        if example_verified_id:
            v_mod = modifications.get(example_verified_id, {})
            v_result = tg_results[example_verified_id]
            with flow_cols[1]:
                st.markdown(
                    '<div class="hl-claim-flow">'
                    '<div class="hl-claim-step">AI Proposed</div>'
                    f'<div class="hl-claim-text">{v_mod.get("proposed_text", example_verified_id)}</div>'
                    '<div class="hl-claim-step">Truth Guard</div>'
                    f'<div class="hl-claim-text">Evidence: {", ".join(v_result.get("evidence_ids", [])) or "none"}</div>'
                    '<div class="hl-claim-step">Result</div>'
                    f'<div class="hl-claim-text">{_badge_html("VERIFIED")}</div>'
                    "</div>",
                    unsafe_allow_html=True,
                )
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("**Proposed modifications**")
    for mid, mod in modifications.items():
        result = tg_results.get(mid, {})
        status = result.get("status", "?")
        with st.container(border=True):
            st.markdown(f"**{TRUTH_STATUS_LABELS.get(status, status)}**")
            st.markdown(f"ORIGINAL: {mod.get('original_text') or '*(new addition)*'}")
            st.markdown(f"PROPOSED: {mod['proposed_text']}")
            st.caption(f"WHY IT WAS SUGGESTED: {mod.get('reason', '')}")
            st.caption(f"SUPPORTING EVIDENCE: {', '.join(result.get('evidence_ids', [])) or 'none'}")
            if status != "VERIFIED":
                st.caption(f"Truth Guard explanation: {result.get('explanation', '')}")

    if rejected:
        st.markdown("**Removed (unsupported, could not be corrected)**")
        for r in rejected.values():
            mod = modifications.get(r["modification_id"])
            label = r.get("claim") or (mod["proposed_text"] if mod else r["modification_id"])
            st.markdown(f"- ✕ UNSUPPORTED — ~~{label}~~")
            st.caption(r["reason"])

    # Human clarification interrupt
    if interrupt and "clarification_required" in interrupt:
        clarification = interrupt["clarification_required"]
        st.divider()
        _human_decision_banner(
            completed=[
                "Truth Guard checked this claim against retrieved evidence and could not confirm or reject it automatically.",
            ],
            decision="Whether this claim is accurate, should use a safe rewrite instead, or should be rejected.",
            why="The evidence is insufficient for Truth Guard to decide on its own — accepting or rejecting an unverifiable claim about your background is a human call.",
        )
        st.markdown(f"**Claim:** {clarification['proposed_claim']}")
        st.markdown(f"**Why evidence is insufficient:** {clarification['explanation']}")
        st.markdown(f"**Closest evidence:** {', '.join(clarification.get('closest_evidence_ids', [])) or 'none'}")
        st.markdown(f"**Safe rewrite:** {clarification.get('safe_option') or 'none available'}")

        col1, col2, col3, col4 = st.columns(4)
        detail = st.text_input("Confirmation detail (if confirming)", key="clarify-detail")
        if col1.button("Confirm with evidence"):
            resume_graph({"action": "CONFIRM_WITH_EVIDENCE", "confirmation_detail": detail or "Human confirmed this claim is accurate."})
            st.rerun()
        if col2.button("Use safe rewrite"):
            resume_graph({"action": "USE_SAFE_REWRITE"})
            st.rerun()
        if col3.button("Reject"):
            resume_graph({"action": "REJECT_CLAIM"})
            st.rerun()
        if col4.button("Cancel", key="clarify-cancel"):
            resume_graph({"action": "CANCEL"})
            st.rerun()
        return

    # Human resume approval interrupt
    if interrupt and "modifications" in interrupt:
        st.divider()
        _human_decision_banner(
            completed=[
                f"Truth Guard verified {counts['VERIFIED']} modification(s) as fully supported by your real resume/experience.",
                f"{len(rejected)} unsupported modification(s) were already blocked and will never reach your resume.",
            ],
            decision="Which of the verified modifications to actually apply to your resume.",
            why="Even fully verified changes only go live on a human's approval — HireLoop never edits your resume unattended.",
        )
        offered_ids = [m["modification_id"] for m in interrupt["modifications"]]
        selected = st.multiselect("Approve selected (or use Approve All)", offered_ids, default=offered_ids)

        col1, col2, col3, col4 = st.columns(4)
        if col1.button("Approve all safe changes", type="primary"):
            resume_graph({"action": "APPROVE_ALL"})
            st.rerun()
        if col2.button("Approve selected"):
            resume_graph({"action": "APPROVE_SELECTED", "modification_ids": selected})
            st.rerun()
        if col3.button("Reject all"):
            resume_graph({"action": "REJECT_ALL"})
            st.rerun()
        if col4.button("Cancel", key="approval-cancel"):
            resume_graph({"action": "CANCEL"})
            st.rerun()

    if s.get("current_resume_version_id") and not interrupt:
        st.success("Resume Version Created")
        st.markdown(f"**Version ID:** {s['current_resume_version_id']}")
        st.markdown(f"**Target Job:** {s.get('selected_job_id')}")
        st.markdown(f"**Approved changes:** {len(s.get('approved_modification_ids', []))}")
        st.markdown(f"**Rejected changes:** {len(s.get('rejected_modifications', []))}")
        st.caption("Original Resume Preserved — the parsed resume text was never modified.")

    _behind_the_decision(s, "resume-studio")


def page_applications() -> None:
    st.header("Applications")
    s = state()
    interrupt = st.session_state.interrupt

    if interrupt and "application" in interrupt and "modifications" not in interrupt:
        app_info = interrupt["application"]
        _human_decision_banner(
            completed=[
                f"HireLoop created a tracked application record for job {app_info['job_id']} with a verified, approved resume.",
            ],
            decision="Whether — and how — to record this application (applied, saved for later, or cancel).",
            why="HireLoop never submits an application automatically; marking something as applied is a real-world action only you can confirm actually happened.",
        )
        st.subheader("New Application Ready")
        st.markdown(f"**Job:** {app_info['job_id']}  \n**Status:** {app_info['current_status']}  \n**Opportunity Score:** {app_info.get('opportunity_score')}")
        col1, col2, col3 = st.columns(3)
        if col1.button("Mark Applied", type="primary"):
            resume_graph({"action": "MARK_APPLIED"})
            st.rerun()
        if col2.button("Save for later"):
            resume_graph({"action": "SAVE_FOR_LATER"})
            st.rerun()
        if col3.button("Cancel", key="app-action-cancel"):
            resume_graph({"action": "CANCEL"})
            st.rerun()
        st.divider()

    st.subheader("Tracked Applications")
    applications = st.session_state.tracker.list_applications()
    if not applications:
        st.caption("No applications tracked yet.")
    for application in applications:
        history = st.session_state.tracker.get_application_history(application.application_id)
        with st.container(border=True):
            _application_pipeline_strip(application.current_status.value)
            cols = st.columns([2, 1, 1, 1])
            cols[0].markdown(f"**{application.job_id}**  \nRole family: {application.role_family or '—'}")
            cols[1].metric("Opportunity Score", f"{application.opportunity_score:.1f}" if application.opportunity_score else "—")
            cols[2].markdown(f"**Status**  \n{application.current_status.value}")
            cols[3].markdown(f"**Resume Version**  \n{application.selected_resume_version_id or '—'}")
            st.caption(f"Applied: {application.applied_at or 'not yet'} · Latest event: {history[-1].event_type.value if history else '—'}")

            with st.expander("Event timeline"):
                for event in history:
                    st.markdown(f"- {event.occurred_at.isoformat()} — **{event.event_type.value}**")

            with st.expander("Record outcome"):
                _outcome_recorder(application.application_id)


def _outcome_recorder(application_id: str) -> None:
    is_active = st.session_state.get("outcome_thread_id") and st.session_state.get("outcome_active_application") == application_id

    if not is_active:
        if st.button("Start outcome update", key=f"start-outcome-{application_id}"):
            thread_id = f"outcome-ui-{uuid.uuid4().hex[:10]}"
            st.session_state.outcome_thread_id = thread_id
            st.session_state.outcome_active_application = application_id
            config = {
                "configurable": {
                    "thread_id": thread_id,
                    "llm_client": st.session_state.llm_client,
                    "application_tracker": st.session_state.tracker,
                    "memory_service": st.session_state.memory_service,
                    "settings": st.session_state.settings,
                }
            }
            result = st.session_state.outcome_graph.invoke(
                {"target_application_id": application_id, "workflow_status": "NOT_STARTED"}, config=config
            )
            st.session_state.outcome_state = result
            st.session_state.outcome_interrupt = result["__interrupt__"][0].value if "__interrupt__" in result else None
            st.rerun()
        return

    interrupt = st.session_state.outcome_interrupt
    if interrupt is None:
        st.success("Outcome workflow completed for this application.")
        return

    if interrupt.get("warning"):
        st.warning(interrupt["warning"])

    actions = [a for a in interrupt["allowed_actions"] if a != "CANCEL"]
    choice = st.selectbox("Outcome", actions, key=f"outcome-choice-{application_id}")
    confirm = False
    if interrupt.get("warning"):
        confirm = st.checkbox("I confirm this unusual sequence is correct", key=f"confirm-{application_id}")

    config = {
        "configurable": {
            "thread_id": st.session_state.outcome_thread_id,
            "llm_client": st.session_state.llm_client,
            "application_tracker": st.session_state.tracker,
            "memory_service": st.session_state.memory_service,
            "settings": st.session_state.settings,
        }
    }
    col1, col2 = st.columns(2)
    if col1.button("Submit outcome", key=f"submit-outcome-{application_id}"):
        response = {"action": choice}
        if confirm:
            response["confirm"] = True
        result = st.session_state.outcome_graph.invoke(Command(resume=response), config=config)
        st.session_state.outcome_state = result
        st.session_state.outcome_interrupt = result["__interrupt__"][0].value if "__interrupt__" in result else None
        st.rerun()
    if col2.button("Cancel outcome update", key=f"cancel-outcome-{application_id}"):
        result = st.session_state.outcome_graph.invoke(Command(resume={"action": "CANCEL"}), config=config)
        st.session_state.outcome_state = result
        st.session_state.outcome_interrupt = None
        st.rerun()

    if st.session_state.outcome_state.get("strategy_insights"):
        st.markdown("**Strategy insights generated by this outcome update:**")
        for insight in st.session_state.outcome_state["strategy_insights"]:
            _render_insight_card(insight)
        st.caption(f"mem0 sync status: {st.session_state.outcome_state.get('mem0_sync_status')}")


def _render_insight_card(insight: dict) -> None:
    with st.container(border=True):
        st.markdown(f"**[{insight['category']}]**")
        st.markdown("OBSERVED DATA")
        st.write(insight["evidence"])
        st.markdown("AI INTERPRETATION")
        st.write(insight["observation"])
        st.write(f"**Recommendation:** {insight['recommendation']}")
        cols = st.columns(3)
        cols[0].markdown(f"**Sample size**  \n{insight['sample_size']}")
        cols[1].markdown(f"**Confidence**  \n{insight['confidence']}")
        cols[2].markdown(f"**Actionability**  \n{insight.get('actionability', 'NO_CLEAR_SIGNAL')}")


def page_strategy() -> None:
    st.header("Strategy Intelligence")
    st.caption("What's actually working?")
    settings = st.session_state.settings
    demo_records = load_demo_application_history() if settings.demo_mode else []
    live_records = st.session_state.tracker.get_applications_with_history(include_demo_data=False)
    analytics = compute_outcome_analytics(demo_records + live_records)

    if settings.demo_mode:
        st.info("DEMO MODE — role-family/resume-version/work-mode tables below include synthetic seeded history.")

    st.subheader("By role family")
    _render_group_table(analytics.by_role_family)

    st.subheader("By resume version")
    _render_group_table(analytics.by_resume_version)

    st.subheader("By work mode")
    _render_group_table(analytics.by_work_mode)

    st.divider()
    st.subheader("The Learning Loop")
    _learning_loop_strip()

    st.subheader("HireLoop Strategy Insights")
    insights = st.session_state.tracker.list_strategy_insights()
    if not insights:
        st.caption("No strategy insights recorded yet.")
    for insight in insights:
        _render_insight_card(insight.model_dump(mode="json"))


def _render_group_table(groups: dict) -> None:
    if not groups:
        st.caption("No data yet.")
        return
    rows = []
    for name, g in sorted(groups.items()):
        if g.sample_size == 0:
            continue  # only show comparisons when data is sufficient
        rows.append(
            {
                "Group": name,
                "Applications": g.sample_size,
                "Positive Responses": g.positive_responses,
                "Response Rate": f"{g.response_rate * 100:.1f}%",
                "Interviews": g.interviews,
                "Interview Rate": f"{g.interview_rate * 100:.1f}%",
                "Offers": g.offers,
                "Offer Rate": f"{g.offer_rate * 100:.1f}%",
                "Confidence": g.confidence.value,
            }
        )
    if rows:
        st.table(rows)
    else:
        st.caption("Not enough resolved data yet for a meaningful comparison.")


def page_system() -> None:
    st.header("System / Demo")
    settings = st.session_state.settings

    mode_label = "DEMO MODE" if settings.demo_mode else "LIVE MODE"
    st.markdown(_badge_html("MOCK" if settings.demo_mode else "AVAILABLE") + f" &nbsp; **{mode_label}**", unsafe_allow_html=True)

    def status_row(label: str, status: str, note: str = "") -> None:
        cols = st.columns([2, 1, 3])
        cols[0].markdown(f"**{label}**")
        cols[1].markdown(_badge_html(status), unsafe_allow_html=True)
        cols[2].caption(note)

    llm_client = st.session_state.llm_client
    status_row("LLM Provider", "MOCK" if llm_client.primary.name == "mock" else "AVAILABLE", llm_client.primary.name)
    if llm_client.fallback:
        status_row("Fallback LLM", "CONFIGURED", llm_client.fallback.name)
    else:
        status_row("Fallback LLM", "UNAVAILABLE", "none configured")

    status_row("Evidence Retrieval", "MOCK" if settings.demo_mode else "AVAILABLE", "Pinecone not configured -> deterministic local fallback active" if settings.demo_mode else "")
    status_row("Memory (mem0)", "MOCK" if st.session_state.memory_service.provider else "UNAVAILABLE", "in-memory mock provider" if settings.demo_mode else "not configured")
    status_row("Business Database", "AVAILABLE", "in-memory SQLite (this session)")
    status_row("Workflow Checkpointer", "AVAILABLE", "in-memory SQLite (this session)")
    status_row(
        "You.com Live Search",
        "AVAILABLE" if (settings.you_search_enabled and settings.ydc_api_key) else "UNAVAILABLE",
        "opt-in, button-gated, never part of the DEMO_MODE certification path" if not (settings.you_search_enabled and settings.ydc_api_key) else "opt-in, button-gated",
    )

    st.divider()
    st.subheader("The HireLoop Loop")
    _stage_nav(_infer_stage("System / Demo", state(), st.session_state.interrupt))
    st.code(
        "DISCOVER -> SCORE -> TAILOR -> VERIFY -> APPLY -> TRACK -> LEARN -> IMPROVE\n"
        "   ^--------------------------------------------------------------------|",
        language=None,
    )

    st.divider()
    st.subheader("Reset session")
    if st.button("Start a fresh session"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    st.set_page_config(page_title="HireLoop AI", layout="wide")
    _init_session()
    _inject_css()

    st.sidebar.title("HireLoop AI")
    st.sidebar.caption("Every application makes the next one smarter.")
    settings = st.session_state.settings
    sidebar_mode_html = (
        '<span class="hl-badge hl-badge-mode-demo">DEMO MODE — SYNTHETIC DATA</span>'
        if settings.demo_mode
        else '<span class="hl-badge hl-badge-mode-live">LIVE MODE</span>'
    )
    st.sidebar.markdown(sidebar_mode_html, unsafe_allow_html=True)
    page = st.sidebar.radio("Navigate", PAGES, index=PAGES.index(st.session_state.get("page", "Dashboard")))
    st.session_state.page = page

    _header_banner()
    _stage_nav(_infer_stage(page, state(), st.session_state.interrupt))

    renderers = {
        "Dashboard": page_dashboard,
        "Candidate": page_candidate,
        "Opportunities": page_opportunities,
        "Resume Studio": page_resume_studio,
        "Applications": page_applications,
        "Strategy": page_strategy,
        "System / Demo": page_system,
    }
    renderers[page]()


if __name__ == "__main__":
    main()
