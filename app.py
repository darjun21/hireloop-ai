"""
HireLoop AI — Streamlit product.

"Every application makes the next one smarter."

This file is a thin UI layer over the existing backend: every action a
button takes either (a) reads already-computed state produced by the real
LangGraph workflows (src/graph/workflow.py), or (b) resumes those same
workflows via Command(resume=...). No scoring, matching, verification, or
analytics logic is reimplemented here — see src/services/ and src/agents/
for all of that.

The "HireLoop Mission Control" visual system (dark navy premium SaaS
dashboard) lives in src/ui/theme.py (CSS + logo) and src/ui/components.py
(render helpers). This module owns page routing and state orchestration
only — every number, badge, and status shown anywhere below is read from
`st.session_state.state`, `st.session_state.tracker`, or a decision_trace /
interrupt payload the backend already produced. Nothing here fabricates a
metric.
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
from src.ui import mission_control as ui
from src.ui.theme import inject_global_css

DEMO_RESUME_PATH = "data/sample_candidate/demo_resume.txt"

PAGE_KEYS = ["Dashboard", "Candidate", "Opportunities", "Resume Studio", "Applications", "Strategy", "System / Demo"]
# NOTE: "Candidate" is kept as a real option of the single sidebar radio
# widget (same widget, same option strings as the pre-rebuild UI) because
# tests/test_you_search.py drives navigation via
# `at.sidebar.radio[0].set_value("Candidate")` — that test file is certified
# and must not be touched. Candidate is visually a secondary/setup entry
# (see _render_sidebar), but functionally it is still just a radio option.
# No emoji in core navigation — each row's icon is painted by pure CSS
# (see ui.sidebar_nav_icon_css) keyed to this fixed order; the on-screen
# text is the label only.
PAGE_NAV = [
    ("Dashboard", "Mission Control"),
    ("Candidate", "Candidate Setup"),
    ("Opportunities", "Opportunities"),
    ("Resume Studio", "Resume Studio"),
    ("Applications", "Applications"),
    ("Strategy", "Strategy Intelligence"),
    ("System / Demo", "System & Demo"),
]
PAGE_LABELS = {key: label for key, label in PAGE_NAV}

TRUTH_STATUS_LABELS = ui.TRUTH_STATUS_LABELS
STAGES = ["DISCOVER", "SCORE", "TAILOR", "VERIFY", "APPLY", "TRACK", "LEARN", "IMPROVE"]


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
# Stage status (pure UI convenience — never drives routing/business logic)
#
# Every stage's status is derived only from real fields already present in
# `state()` / the current interrupt payload / the tracker — never from which
# page happens to be open, and never fabricated. This single map feeds the
# compact one-line breadcrumb (_render_stage_line), the central circular
# workflow visualization, and the sidebar loop ring.
# ---------------------------------------------------------------------------


def _human_decision_stage(interrupt: dict | None) -> str | None:
    if not interrupt:
        return None
    if "eligible_selections" in interrupt:
        return "SCORE"
    if "clarification_required" in interrupt or "modifications" in interrupt:
        return "VERIFY"
    if "application" in interrupt:
        return "TRACK"
    return None


def _stage_status_map(s: dict, interrupt: dict | None) -> dict[str, str]:
    counts = s.get("counts", {}) or {}
    completed = {
        "DISCOVER": bool(counts.get("ingested")),
        "SCORE": bool(s.get("opportunity_scores")),
        "TAILOR": bool(s.get("proposed_modifications")),
        "VERIFY": bool(s.get("truth_guard_results")),
        "APPLY": bool(s.get("current_resume_version_id")),
        "TRACK": bool(st.session_state.tracker.list_applications()),
        "LEARN": bool(st.session_state.tracker.list_strategy_insights()),
        "IMPROVE": False,  # continuous — never reaches a fabricated "complete" state
    }
    statuses: dict[str, str] = {}
    found_active = False
    for stage in STAGES:
        if completed[stage]:
            statuses[stage] = "done"
        elif not found_active:
            statuses[stage] = "active"
            found_active = True
        else:
            statuses[stage] = "waiting"

    human_stage = _human_decision_stage(interrupt)
    if human_stage:
        statuses[human_stage] = "human"
    return statuses


def _render_stage_line() -> None:
    """Compact one-line stage indicator (replaces the previous giant
    per-page stage cards on every non-Dashboard page)."""
    statuses = _stage_status_map(state(), st.session_state.interrupt)
    ui.stage_line(statuses, STAGES)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------


def _goto(page_key: str, **extra_state):
    """Returns an on_click callback that programmatically switches the
    sidebar's nav radio to `page_key` (plus any extra session_state keys),
    e.g. a "VIEW INTELLIGENCE" button on the Dashboard jumping to
    Opportunities. Must run as an on_click callback (not inline after the
    radio widget has already been instantiated this run) — Streamlit
    forbids writing to a widget-bound session_state key outside a
    callback."""

    def _cb() -> None:
        st.session_state["nav_radio"] = page_key
        st.session_state["page"] = page_key
        for k, v in extra_state.items():
            st.session_state[k] = v

    return _cb


def _render_sidebar() -> str:
    settings = st.session_state.settings
    ui.sidebar_brand()
    ui.sidebar_mode_badge(settings.demo_mode)

    nav_keys = [key for key, _ in PAGE_NAV]
    current = st.session_state.get("page", "Dashboard")
    default_main = current if current in nav_keys else "Dashboard"

    st.sidebar.markdown('<div class="hl-nav-label">Workspace</div>', unsafe_allow_html=True)
    # Single radio widget, same option strings as the pre-rebuild UI (see
    # the PAGE_NAV note above) — only the on-screen label is restyled via
    # format_func + CSS, so certified navigation tests keep working. Icons
    # are painted purely via CSS (ui.sidebar_nav_icon_css), never inside
    # the widget's own label text (Streamlit renders that as plain text).
    page = st.sidebar.radio(
        "Navigate",
        nav_keys,
        index=nav_keys.index(default_main),
        format_func=lambda k: PAGE_LABELS[k],
        label_visibility="collapsed",
        key="nav_radio",
    )
    st.session_state.page = page
    ui.sidebar_nav_icon_css(nav_keys)

    presentation_mode = st.sidebar.checkbox(
        "Presentation mode", value=st.session_state.get("presentation_mode", False), key="presentation_mode"
    )
    ui.apply_presentation_mode(presentation_mode)

    stage_status = _stage_status_map(state(), st.session_state.interrupt)
    ui.sidebar_loop_ring(stage_status)

    return page


# ---------------------------------------------------------------------------
# Human decision banner (shared visual, real payload supplied by caller)
# ---------------------------------------------------------------------------


def _human_decision_banner(completed: list[str], decision: str, why: str) -> None:
    ui.human_decision_banner(completed, decision, why)


# ---------------------------------------------------------------------------
# AI Team Activity + Truth Guard Summary (right rail, Dashboard only)
# ---------------------------------------------------------------------------


def _agent_activity_rows(s: dict, interrupt: dict | None) -> list[tuple[str, str, str]]:
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

    return rows


def _render_agent_activity_rail(s: dict, interrupt: dict | None) -> None:
    st.markdown('<div class="hl-nav-label">AI Team Activity</div>', unsafe_allow_html=True)
    for name, status_label, note in _agent_activity_rows(s, interrupt):
        with st.container(border=True):
            top = st.columns([2, 1])
            top[0].markdown(f"**{name}**")
            top[1].markdown(ui.badge_html(status_label), unsafe_allow_html=True)
            st.caption(note)


def _render_truth_guard_summary(s: dict) -> None:
    st.markdown('<div class="hl-nav-label">Truth Guard Summary</div>', unsafe_allow_html=True)
    tg_results = s.get("truth_guard_results", {})
    counts = {"VERIFIED": 0, "PARTIALLY_SUPPORTED": 0, "UNSUPPORTED": 0, "NEEDS_HUMAN_CONFIRMATION": 0}
    for r in tg_results.values():
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    with st.container(border=True):
        c1, c2, c3 = st.columns(3)
        c1.metric("Verified", counts["VERIFIED"])
        c2.metric("Blocked", counts["UNSUPPORTED"])
        c3.metric("Review", counts["NEEDS_HUMAN_CONFIRMATION"] + counts["PARTIALLY_SUPPORTED"])

        modifications = {m["modification_id"]: m for m in s.get("proposed_modifications", [])}
        rejected = {r["modification_id"]: r for r in s.get("rejected_modifications", [])}
        example_rejected = next(iter(rejected.values()), None)
        example_verified_id = next((mid for mid, r in tg_results.items() if r.get("status") == "VERIFIED"), None)

        if example_rejected or example_verified_id:
            st.caption("RECENT VERIFICATION")
        if example_rejected:
            mod = modifications.get(example_rejected["modification_id"])
            claim_text = ui.esc(example_rejected.get("claim") or (mod["proposed_text"] if mod else example_rejected["modification_id"]))
            st.markdown(
                ui.claim_card(
                    "blocked",
                    [
                        ("AI Proposed", claim_text),
                        ("Truth Guard", ui.esc(example_rejected.get("reason", ""))),
                        ("Result", ui.badge_html("UNSUPPORTED")),
                    ],
                ),
                unsafe_allow_html=True,
            )
        if example_verified_id:
            v_mod = modifications.get(example_verified_id, {})
            v_result = tg_results[example_verified_id]
            st.markdown(
                ui.claim_card(
                    "verified",
                    [
                        ("AI Proposed", ui.esc(v_mod.get("proposed_text", example_verified_id))),
                        ("Evidence", ui.esc(", ".join(v_result.get("evidence_ids", [])) or "none")),
                        ("Result", ui.badge_html("VERIFIED")),
                    ],
                ),
                unsafe_allow_html=True,
            )
        if not example_rejected and not example_verified_id:
            st.caption("No verification activity recorded yet.")


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
    ui.pipeline_timeline(steps, lambda step: False)
    st.caption("Illustrative — shows how one recorded outcome eventually reshapes the next search's strategy insights.")


def _application_pipeline_strip(current_status: str) -> None:
    steps = ["SAVED", "APPLIED", "RESPONSE", "INTERVIEW", "FINAL ROUND", "OFFER"]
    normalized = (current_status or "").upper().replace("_", " ")
    ui.pipeline_timeline(steps, lambda step: step in normalized or normalized in step)


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


DEFAULT_TARGET_ROLES = ["AI Engineer"]
DEFAULT_WORK_MODES = [WorkMode.REMOTE.value]


def _load_certification_demo() -> None:
    """The exact same call path the Candidate page's "seeded demo
    candidate" checkbox + "Run HireLoop Search" button already trigger —
    just exposed as a single one-click affordance from the Mission Control
    empty state. Calls the real start_new_run(); the graph's own
    interrupt() naturally stops the run at job selection, so this cannot
    skip or auto-resolve that first human decision."""
    st.session_state.last_run_params = {
        "resume_path": DEMO_RESUME_PATH,
        "roles": DEFAULT_TARGET_ROLES,
        "work_mode": DEFAULT_WORK_MODES,
    }
    st.session_state.job_source_override = None
    start_new_run(DEMO_RESUME_PATH, DEFAULT_TARGET_ROLES, DEFAULT_WORK_MODES)


def page_dashboard() -> None:
    settings = st.session_state.settings
    s = state()
    interrupt = st.session_state.interrupt

    st.markdown("## Mission Control")
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:0.4rem;margin:-0.4rem 0 0.7rem 0;">'
        f'{ui.icon("human_decision", 14, color="var(--violet)")}'
        f'<span style="font-size:0.76rem;color:var(--muted);">'
        "Autonomous discovery, scoring, tailoring, and verification — every consequential step still needs your sign-off."
        "</span></div>",
        unsafe_allow_html=True,
    )

    scores = s.get("opportunity_scores", {})

    if not scores:
        ui.empty_state_compact(
            "bolt",
            "Ready For Your First Loop",
            "Load the certification demo candidate, or set up your own resume and target roles, to see live scoring, matches, and Truth Guard verification here.",
        )
        c1, c2 = st.columns(2)
        if c1.button("Load Certification Demo", type="primary", key="load-cert-demo", use_container_width=True):
            with st.spinner("Loading certification demo — parsing resume, scoring opportunities..."):
                _load_certification_demo()
            st.rerun()
        c2.button("Set Up Candidate", key="dash-goto-candidate", use_container_width=True, on_click=_goto("Candidate"))
        _render_stage_line()
        left, right = st.columns([2.7, 1], gap="medium")
        with right:
            _render_agent_activity_rail(s, interrupt)
            st.markdown("<div style='margin-top:0.9rem;'></div>", unsafe_allow_html=True)
            _render_truth_guard_summary(s)
        return

    left, right = st.columns([2.7, 1], gap="medium")

    with left:
        ranked = s.get("ranked_job_ids", [])
        high_priority = sum(1 for jid in ranked if scores.get(jid, {}).get("recommendation") == "HIGH_PRIORITY")

        demo_records = load_demo_application_history() if settings.demo_mode else []
        live_records = st.session_state.tracker.get_applications_with_history(include_demo_data=False)
        analytics = compute_outcome_analytics(demo_records + live_records)

        total_interviews = sum(g.interviews for g in analytics.by_role_family.values())
        interview_rate = (total_interviews / analytics.total_resolved) if analytics.total_resolved else 0.0

        ui.kpi_row(
            [
                ("kpi_search", str(len(scores)), "Opportunities Analyzed"),
                ("kpi_star", str(high_priority), "Best Fits"),
                ("kpi_send", str(analytics.total_applications), "Applications"),
                ("kpi_mic", str(total_interviews), "Interviews"),
                ("kpi_chart", f"{interview_rate * 100:.1f}%", "Interview Rate"),
            ]
        )

        stage_status = _stage_status_map(s, interrupt)
        ui.workflow_loop(stage_status)

        deduped_by_id = {j["job_id"]: j for j in s.get("deduped_jobs", [])}
        top_id = max(scores, key=lambda jid: scores[jid]["final_score"])
        top = scores[top_id]
        job = deduped_by_id.get(top_id, {})
        analysis = s.get("match_analyses", {}).get(top_id)

        with st.container(border=True):
            ui.card_title("Top Opportunity")
            hc1, hc2 = st.columns([3, 1])
            with hc1:
                st.markdown(f"### {job.get('title', '?')}")
                st.markdown(f"**{job.get('company', '?')}** · {job.get('location') or 'Location unknown'}")
                st.markdown(f"{ui.badge_html(top['recommendation'], 'info')}  {ui.confidence_badge(top['confidence'])}", unsafe_allow_html=True)
            with hc2:
                st.metric("HireLoop Score", f"{top['final_score']:.1f}")

            if analysis:
                gcols = st.columns(2)
                gcols[0].markdown("**Top Matches**")
                for line in analysis.get("strengths", [])[:3]:
                    gcols[0].markdown(f"- {line}")
                gcols[1].markdown("**Top Gaps**")
                for line in analysis.get("gaps", [])[:3]:
                    gcols[1].markdown(f"- {line}")

            bc1, bc2 = st.columns(2)
            bc1.button(
                "VIEW INTELLIGENCE",
                key="dash-view-detail",
                use_container_width=True,
                on_click=_goto("Opportunities", selected_detail_job_id=top_id),
            )
            interrupt = st.session_state.interrupt
            selectable = bool(
                interrupt and "eligible_selections" in interrupt
                and top_id in {item["job_id"] for item in interrupt["eligible_selections"]}
            )
            if bc2.button("SELECT OPPORTUNITY", key="dash-select", type="primary", use_container_width=True, disabled=not selectable):
                resume_graph({"action": "SELECT", "job_id": top_id})
                st.rerun()

        insights = st.session_state.tracker.list_strategy_insights()
        with st.container(border=True):
            ui.card_title("Latest HireLoop Insight")
            if not insights:
                st.caption("No strategy insights recorded yet — record an outcome to generate one.")
            else:
                _render_insight_card(insights[0].model_dump(mode="json"), bordered=False)
                st.button("VIEW FULL STRATEGY", key="dash-view-strategy", on_click=_goto("Strategy"))

        st.markdown('<div class="hl-nav-label">Recent Activity</div>', unsafe_allow_html=True)
        events = s.get("decision_trace", [])
        if not events:
            st.caption("No activity recorded yet for this run.")
        else:
            for event in events[-6:][::-1]:
                ts = event.get("timestamp")
                prefix = f"`{ts}` — " if ts else ""
                st.markdown(f"- {prefix}{event['message']}")

    with right:
        _render_agent_activity_rail(s, st.session_state.interrupt)
        st.markdown("<div style='margin-top:0.9rem;'></div>", unsafe_allow_html=True)
        _render_truth_guard_summary(s)


def page_candidate() -> None:
    st.markdown("## Candidate")
    settings = st.session_state.settings
    _render_stage_line()

    with st.form("candidate_form"):
        uploaded = st.file_uploader("Upload resume (PDF, DOCX, or TXT)", type=["pdf", "docx", "txt"])
        use_demo = st.checkbox("Use the seeded demo candidate instead", value=settings.demo_mode)
        target_roles = st.text_input("Target roles (comma-separated)", value="AI Engineer")
        work_mode = st.multiselect("Preferred work mode", [m.value for m in WorkMode], default=[WorkMode.REMOTE.value])
        submitted = st.form_submit_button("Run HireLoop Search", type="primary")

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
    st.markdown("## Opportunities")
    _render_stage_line()
    _job_source_control()
    s = state()
    scores = s.get("opportunity_scores", {})
    if not scores:
        ui.empty_state_compact("opportunities", "No Opportunities Yet", "Run a search from the Candidate page to see scored opportunities here.")
        return

    deduped_by_id = {j["job_id"]: j for j in s.get("deduped_jobs", [])}
    quality_by_id = s.get("job_quality_results", {})
    analyses = s.get("match_analyses", {})

    counts = s.get("counts", {}) or {}
    summary_parts = []
    if "ingested" in counts:
        summary_parts.append(f"{counts['ingested']} discovered")
    if "unique_after_dedup" in counts:
        summary_parts.append(f"{counts['unique_after_dedup']} unique")
    if "scored" in counts:
        summary_parts.append(f"{counts['scored']} scored")
    strong_fits = sum(1 for sc in scores.values() if sc.get("recommendation") in ("HIGH_PRIORITY", "STRONG_MATCH"))
    summary_parts.append(f"{strong_fits} strong fit(s)")
    st.caption(" · ".join(summary_parts))

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

    grid_cols = st.columns(2)
    for i, (job_id, job, score) in enumerate(rows):
        quality = quality_by_id.get(job_id, {})
        analysis = analyses.get(job_id)
        with grid_cols[i % 2]:
            with st.container(border=True):
                top = st.columns([3, 1, 1])
                top[0].markdown(f"**{job.get('title', '?')}** — {job.get('company', '?')}")
                top[0].caption(f"{job.get('location') or 'Location unknown'} · {job.get('work_mode') or 'Work mode unknown'}")
                if job.get("source") == "you_com":
                    domain = (job.get("metadata") or {}).get("source_domain") or job.get("url") or "unknown source"
                    top[0].caption(f"Source: Web discovery / You.com — {domain} (not verified active; discovered via live search)")
                top[1].metric("HireLoop Score", f"{score['final_score']:.1f}")
                top[2].markdown(f"**{score['recommendation']}**  \nConfidence:", unsafe_allow_html=False)
                top[2].markdown(ui.confidence_badge(score["confidence"]), unsafe_allow_html=True)

                if quality.get("requirement_completeness") == "LOW":
                    st.caption("Limited job-description evidence. Match confidence is reduced.")

                if analysis:
                    cols = st.columns(2)
                    cols[0].markdown("**Why HireLoop Likes It**")
                    for line in analysis.get("strengths", [])[:3]:
                        cols[0].markdown(f"- {line}")
                    cols[1].markdown("**Watch Out For**")
                    for line in analysis.get("gaps", [])[:3]:
                        cols[1].markdown(f"- {line}")

                if st.button("VIEW INTELLIGENCE", key=f"detail-{job_id}", use_container_width=True):
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

    col1, col2, col3, col4 = st.columns([1.2, 1, 1, 1])
    with col1:
        ui.score_ring(score["final_score"])
    col2.markdown(f"**Recommendation**  \n{score['recommendation']}")
    col3.markdown("**Confidence**")
    col3.markdown(ui.confidence_badge(score["confidence"]), unsafe_allow_html=True)
    col4.caption(f"Scoring model: {score['scoring_version']}")

    st.markdown("**Opportunity DNA** — the 7 real components behind the score above")
    for name, comp in score.get("components", {}).items():
        label = name.replace("_", " ").title()
        ui.score_bar(label, comp["value"], comp["weight"], comp["weighted_contribution"])

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
    st.markdown("## Resume Studio")
    st.caption("Tailored for relevance. Guarded by evidence.")
    _render_stage_line()
    s = state()
    interrupt = st.session_state.interrupt

    if not s.get("selected_job_id"):
        ui.empty_state_compact("resume", "No Opportunity Selected", "Select an opportunity first (Opportunities page).")
        return

    tg_results = s.get("truth_guard_results", {})
    counts = {"VERIFIED": 0, "PARTIALLY_SUPPORTED": 0, "UNSUPPORTED": 0, "NEEDS_HUMAN_CONFIRMATION": 0}
    for r in tg_results.values():
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    modifications = {m["modification_id"]: m for m in s.get("proposed_modifications", [])}
    rejected = {r["modification_id"]: r for r in s.get("rejected_modifications", [])}

    with st.container(border=True):
        ui.card_title("Truth Guard Summary")
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
                claim_text = ui.esc(example_rejected.get("claim") or (mod["proposed_text"] if mod else example_rejected["modification_id"]))
                with flow_cols[0]:
                    st.markdown(
                        ui.claim_card(
                            "blocked",
                            [
                                ("AI Proposed", claim_text),
                                ("Truth Guard", ui.esc(example_rejected.get("reason", ""))),
                                ("Result", ui.badge_html("UNSUPPORTED")),
                            ],
                        ),
                        unsafe_allow_html=True,
                    )
            if example_verified_id:
                v_mod = modifications.get(example_verified_id, {})
                v_result = tg_results[example_verified_id]
                with flow_cols[1]:
                    st.markdown(
                        ui.claim_card(
                            "verified",
                            [
                                ("AI Proposed", ui.esc(v_mod.get("proposed_text", example_verified_id))),
                                ("Evidence", ui.esc(", ".join(v_result.get("evidence_ids", [])) or "none")),
                                ("Result", ui.badge_html("VERIFIED")),
                            ],
                        ),
                        unsafe_allow_html=True,
                    )

    st.markdown("**Proposed modifications**")
    for mid, mod in modifications.items():
        result = tg_results.get(mid, {})
        status = result.get("status", "?")
        blocked = status != "VERIFIED"
        with st.container(border=True):
            badge_text = TRUTH_STATUS_LABELS.get(status, status)
            icon_name, icon_color = ui.TRUTH_STATUS_ICON.get(status, ("check", "var(--muted)"))
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:0.4rem;margin-bottom:0.4rem;">'
                f"{ui.icon(icon_name, 16, color=icon_color)}{ui.badge_html(badge_text)}</div>",
                unsafe_allow_html=True,
            )
            st.markdown(f"**SECTION:** {mod.get('section', '—')}")
            st.markdown(f"**ORIGINAL:** {mod.get('original_text') or '*(new addition)*'}")
            st.markdown(f"**PROPOSED:** {mod['proposed_text']}")
            st.caption(f"WHY HIRELOOP SUGGESTED IT: {mod.get('reason', '')}")
            st.caption(f"SUPPORTING EVIDENCE: {', '.join(result.get('evidence_ids', [])) or 'none'}")
            if blocked:
                st.caption(f"Truth Guard explanation: {result.get('explanation', '')}")

    if rejected:
        st.markdown("**Removed (unsupported, could not be corrected)**")
        for r in rejected.values():
            mod = modifications.get(r["modification_id"])
            label = r.get("claim") or (mod["proposed_text"] if mod else r["modification_id"])
            st.markdown(f"- {ui.badge_html('UNSUPPORTED', 'danger')} ~~{label}~~", unsafe_allow_html=True)
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
    st.markdown("## Applications")
    _render_stage_line()
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
        ui.empty_state_compact("applications", "No Applications Tracked Yet", "Once you mark an opportunity as applied, it will appear here with its full pipeline.")
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


def _render_insight_card(insight: dict, bordered: bool = True) -> None:
    ctx = st.container(border=True) if bordered else st.container()
    with ctx:
        st.markdown(f"**[{insight['category']}]**")
        oc1, oc2 = st.columns(2)
        with oc1:
            st.markdown("**OBSERVED DATA**")
            st.write(insight["evidence"])
        with oc2:
            st.markdown("**AI INTERPRETATION**")
            st.write(insight["observation"])
        st.write(f"**Recommendation:** {insight['recommendation']}")
        cols = st.columns(3)
        cols[0].markdown(f"**Sample size**  \n{insight['sample_size']}")
        cols[1].markdown(f"**Confidence**  \n{insight['confidence']}")
        cols[2].markdown(f"**Actionability**  \n{insight.get('actionability', 'NO_CLEAR_SIGNAL')}")


def page_strategy() -> None:
    st.markdown("## Strategy Intelligence")
    st.caption("What's actually working?")
    _render_stage_line()
    settings = st.session_state.settings
    demo_records = load_demo_application_history() if settings.demo_mode else []
    live_records = st.session_state.tracker.get_applications_with_history(include_demo_data=False)
    analytics = compute_outcome_analytics(demo_records + live_records)

    if settings.demo_mode:
        st.caption(f"{ui.badge_html('DEMO MODE')} figures below include synthetic seeded history.", unsafe_allow_html=True)

    resolved_role_groups = {name: g for name, g in analytics.by_role_family.items() if g.sample_size > 0}
    if resolved_role_groups:
        st.markdown("**Interview rate by role family**")
        ui.bar_rows(
            [
                (name, g.interview_rate * 100, f"{g.interview_rate * 100:.1f}% ({g.interviews}/{g.sample_size})")
                for name, g in sorted(resolved_role_groups.items(), key=lambda kv: -kv[1].interview_rate)
            ]
        )
        st.markdown("**Response rate by role family**")
        ui.bar_rows(
            [
                (name, g.response_rate * 100, f"{g.response_rate * 100:.1f}% ({g.positive_responses}/{g.sample_size})")
                for name, g in sorted(resolved_role_groups.items(), key=lambda kv: -kv[1].response_rate)
            ]
        )
    else:
        st.caption("Not enough resolved data yet for a role-family comparison.")

    with st.expander("View Raw Data"):
        st.markdown("**By role family**")
        _render_group_table(analytics.by_role_family)
        st.markdown("**By resume version**")
        _render_group_table(analytics.by_resume_version)
        st.markdown("**By work mode**")
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
    st.markdown("## System & Demo")
    settings = st.session_state.settings
    _render_stage_line()

    mode_label = "DEMO MODE" if settings.demo_mode else "LIVE MODE"
    st.markdown(ui.badge_html("MOCK" if settings.demo_mode else "AVAILABLE") + f" &nbsp; **{mode_label}**", unsafe_allow_html=True)

    with st.container(border=True):
        ui.card_title("Provider Status")
        llm_client = st.session_state.llm_client
        ui.status_row("LLM Provider", "MOCK" if llm_client.primary.name == "mock" else "AVAILABLE", llm_client.primary.name)
        if llm_client.fallback:
            ui.status_row("Fallback LLM", "CONFIGURED", llm_client.fallback.name)
        else:
            ui.status_row("Fallback LLM", "UNAVAILABLE", "none configured")

        ui.status_row("Evidence Retrieval", "MOCK" if settings.demo_mode else "AVAILABLE", "Pinecone not configured -> deterministic local fallback active" if settings.demo_mode else "")
        ui.status_row("Memory (mem0)", "MOCK" if st.session_state.memory_service.provider else "UNAVAILABLE", "in-memory mock provider" if settings.demo_mode else "not configured")
        ui.status_row("Business Database", "AVAILABLE", "in-memory SQLite (this session)")
        ui.status_row("Workflow Checkpointer", "AVAILABLE", "in-memory SQLite (this session)")
        ui.status_row(
            "You.com Live Search",
            "AVAILABLE" if (settings.you_search_enabled and settings.ydc_api_key) else "UNAVAILABLE",
            "opt-in, button-gated, never part of the DEMO_MODE certification path" if not (settings.you_search_enabled and settings.ydc_api_key) else "opt-in, button-gated",
        )

    st.divider()
    st.subheader("The HireLoop Loop")
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
    st.set_page_config(page_title="HireLoop AI", layout="wide", page_icon="🔁")
    _init_session()
    inject_global_css()

    page = _render_sidebar()

    ui.app_topbar(st.session_state.settings.demo_mode, "System Operational")

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
