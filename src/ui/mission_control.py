"""
"HireLoop Mission Control" render helpers — presentation-layer recomposition.

Every function here is a pure presentation helper: it takes values the
caller already read from real backend state (`st.session_state.state`,
`st.session_state.tracker`, an interrupt payload, etc.) and formats them
as HTML/Streamlit widgets. Nothing in this module computes, guesses, or
hardcodes a metric, status, or business number — callers in app.py are
responsible for supplying real data.

Kept separate from the pre-existing (and pre-frozen) src/ui/components.py
placeholder stub so that file is never touched by this UI rebuild.
"""

from __future__ import annotations

import math

import streamlit as st

from src.ui.theme import esc, icon, render_hireloop_logo, render_hireloop_wordmark

# ---------------------------------------------------------------------------
# Badges / status
# ---------------------------------------------------------------------------

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
    "NEEDS_HUMAN_CONFIRMATION": "violet",
}

TRUTH_STATUS_LABELS = {
    "VERIFIED": "VERIFIED",
    "PARTIALLY_SUPPORTED": "PARTIALLY SUPPORTED",
    "UNSUPPORTED": "BLOCKED — UNSUPPORTED",
    "NEEDS_HUMAN_CONFIRMATION": "NEEDS HUMAN CONFIRMATION",
}
TRUTH_STATUS_ICON = {
    "VERIFIED": ("check", "var(--green)"),
    "PARTIALLY_SUPPORTED": ("shield_x", "var(--amber)"),
    "UNSUPPORTED": ("shield_x", "var(--red)"),
    "NEEDS_HUMAN_CONFIRMATION": ("human_decision", "var(--violet)"),
}


def badge_html(label: str, kind: str | None = None) -> str:
    kind = kind or _BADGE_KIND.get(label, "neutral")
    return f'<span class="hl-badge hl-badge-{kind}">{esc(label)}</span>'


def confidence_badge(value: str) -> str:
    kind = {"HIGH": "success", "MEDIUM": "warning", "LOW": "danger"}.get(value, "neutral")
    return badge_html(value, kind)


# ---------------------------------------------------------------------------
# App shell — compact top bar, sidebar brand, nav icon injection, loop ring
# ---------------------------------------------------------------------------


def app_topbar(demo_mode: bool, status_text: str) -> None:
    mode_html = (
        '<span class="hl-badge hl-badge-mode-demo">DEMO MODE</span>'
        if demo_mode
        else '<span class="hl-badge hl-badge-mode-live">LIVE MODE</span>'
    )
    st.markdown(
        '<div class="hl-topbar">'
        f"{render_hireloop_logo(30)}"
        '<div><div class="hl-title">HireLoop AI</div>'
        '<div class="hl-tagline">Every application makes the next one smarter.</div></div>'
        '<span class="hl-spacer"></span>'
        f"{mode_html}"
        f'<span class="hl-status-dot"><span class="dot"></span>{esc(status_text)}</span>'
        "</div>",
        unsafe_allow_html=True,
    )


def sidebar_brand() -> None:
    st.sidebar.markdown(
        '<div class="hl-sidebar-brand">'
        f"{render_hireloop_logo(30)}"
        '<div><div class="hl-wordmark">HireLoop AI</div>'
        '<div class="hl-tag">Mission Control</div></div>'
        "</div>",
        unsafe_allow_html=True,
    )


def sidebar_mode_badge(demo_mode: bool) -> None:
    mode_html = (
        '<span class="hl-badge hl-badge-mode-demo">DEMO MODE — SYNTHETIC DATA</span>'
        if demo_mode
        else '<span class="hl-badge hl-badge-mode-live">LIVE MODE</span>'
    )
    st.sidebar.markdown(mode_html, unsafe_allow_html=True)


# Nav icon name per page key, in the same order app.py's PAGE_NAV lists them.
NAV_ICON_NAMES = {
    "Dashboard": "mission_control",
    "Candidate": "candidate",
    "Opportunities": "opportunities",
    "Resume Studio": "resume",
    "Applications": "applications",
    "Strategy": "strategy",
    "System / Demo": "system",
}


def _svg_data_uri(name: str, color: str = "%238D9AB2") -> str:
    """URL-safe inline SVG for a CSS background-image (used to inject an
    icon into a native st.radio label, which Streamlit renders as plain
    text and does not allow raw HTML inside)."""
    raw = icon(name, size=16, color=color.replace("%23", "#"))
    # Minimal escaping sufficient for our own generated markup (no quotes
    # inside attribute values other than the ones we control).
    encoded = raw.replace("#", "%23").replace('"', "'").replace("\n", "")
    return encoded


def sidebar_nav_icon_css(nav_keys: list[str]) -> None:
    """Injects one small <style> block that paints a distinct outline icon
    on each sidebar nav row via :nth-of-type, keyed to the fixed PAGE_NAV
    order app.py already uses for the underlying st.radio options. Pure
    CSS — the radio widget itself, and the certified test that drives it
    via `at.sidebar.radio[0].set_value(...)`, are untouched."""
    rules = []
    for i, key in enumerate(nav_keys, start=1):
        name = NAV_ICON_NAMES.get(key, "bolt")
        muted_uri = _svg_data_uri(name, "%238D9AB2")
        bright_uri = _svg_data_uri(name, "%23F5F7FF")
        rules.append(
            f'[data-testid="stSidebar"] div[role="radiogroup"] label:nth-of-type({i})::before {{ '
            f'background-image: url("data:image/svg+xml,{muted_uri}"); }}'
        )
        rules.append(
            f'[data-testid="stSidebar"] div[role="radiogroup"] label:nth-of-type({i}):has(input:checked)::before {{ '
            f'background-image: url("data:image/svg+xml,{bright_uri}"); }}'
        )
    st.sidebar.markdown(f"<style>{''.join(rules)}</style>", unsafe_allow_html=True)


LOOP_STAGES = ["DISCOVER", "SCORE", "TAILOR", "VERIFY", "TRACK", "LEARN", "IMPROVE"]


def sidebar_loop_ring(stage_status: dict[str, str]) -> None:
    """Compact circular 'THE HIRELOOP' visualization for the sidebar
    bottom: stages arranged around a small ring with a human icon at the
    center. Color-only status state (no animation here, per spec) —
    stage_status maps stage name -> 'done' | 'active' | 'human' | 'waiting'."""
    color = {"done": "#31D17C", "active": "#22C7FF", "human": "#8B5CF6", "waiting": "#3A4560"}
    n = len(LOOP_STAGES)
    size, cx, cy, r = 150, 75, 75, 54
    nodes = []
    for i, stage in enumerate(LOOP_STAGES):
        angle = -math.pi / 2 + (2 * math.pi * i / n)
        x = cx + r * math.cos(angle)
        y = cy + r * math.sin(angle)
        status = stage_status.get(stage, "waiting")
        c = color[status]
        nodes.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.2" fill="{c}"/>')
        lx = cx + (r + 13) * math.cos(angle)
        ly = cy + (r + 13) * math.sin(angle)
        anchor = "middle"
        if lx < cx - 8:
            anchor = "end"
        elif lx > cx + 8:
            anchor = "start"
        nodes.append(
            f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anchor}" '
            f'font-size="6.2" font-weight="700" fill="{c}" '
            f'style="font-family:Inter,sans-serif;">{stage[:4]}</text>'
        )
    svg = f"""
<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" xmlns="http://www.w3.org/2000/svg">
  <circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="rgba(120,160,220,.16)" stroke-width="1.4" stroke-dasharray="2 3"/>
  {''.join(nodes)}
  <circle cx="{cx}" cy="{cy}" r="19" fill="rgba(139,92,246,.10)" stroke="rgba(139,92,246,.4)" stroke-width="1"/>
  <circle cx="{cx}" cy="{cy - 4}" r="3.4" fill="#F5F7FF"/>
  <path d="M{cx - 6} {cy + 9}c0-4.6 2.9-7.6 6-7.6s6 3 6 7.6" stroke="#F5F7FF" stroke-width="2.6" stroke-linecap="round" fill="none"/>
</svg>
"""
    st.sidebar.markdown('<div class="hl-nav-label">The HireLoop</div>', unsafe_allow_html=True)
    st.sidebar.markdown(f'<div class="hl-loop-mini-wrap">{svg}</div>', unsafe_allow_html=True)
    st.sidebar.markdown(
        '<div style="text-align:center;color:var(--muted-2);font-size:0.63rem;font-style:italic;'
        'padding:0 0.4rem;">Human in the loop. AI on the loop. Better outcomes.</div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Compact one-line stage indicator (replaces the eight giant stage cards)
# ---------------------------------------------------------------------------

_STAGE_MARK = {"done": "✓", "active": "●", "human": "◆", "waiting": "○"}
_STAGE_CLASS = {"done": "done", "active": "active", "human": "human", "waiting": "waiting"}


def stage_line(stage_status: dict[str, str], stages: list[str]) -> None:
    segs = []
    for i, stage in enumerate(stages):
        status = stage_status.get(stage, "waiting")
        mark = _STAGE_MARK[status]
        cls = _STAGE_CLASS[status]
        segs.append(f'<span class="seg {cls}"><span class="mark">{mark}</span>{esc(stage)}</span>')
        if i < len(stages) - 1:
            segs.append('<span class="sep">·</span>')
    st.markdown(f'<div class="hl-stage-line">{"".join(segs)}</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# KPI row (dense, icon-tile cards — not st.metric, not giant rectangles)
# ---------------------------------------------------------------------------


def kpi_row(items: list[tuple[str, str, str]]) -> None:
    """items: list of (icon_name, value_str, label)."""
    cards = "".join(
        '<div class="hl-kpi-card">'
        f'<div class="hl-kpi-icon">{icon(icon_name, 16)}</div>'
        f'<div><div class="hl-kpi-value">{esc(value)}</div>'
        f'<div class="hl-kpi-label">{esc(label)}</div></div>'
        "</div>"
        for icon_name, value, label in items
    )
    st.markdown(f'<div class="hl-kpi-row">{cards}</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Empty state — compact card, not a giant rectangle
# ---------------------------------------------------------------------------


def empty_state_compact(icon_name: str, title: str, subtitle: str) -> None:
    st.markdown(
        '<div class="hl-empty-compact">'
        f'<div class="hl-empty-icon">{icon(icon_name, 20)}</div>'
        '<div class="hl-empty-body">'
        f'<div class="hl-empty-title">{esc(title)}</div>'
        f'<div class="hl-empty-sub">{esc(subtitle)}</div>'
        "</div></div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Reusable human-decision component (every interrupt uses this)
# ---------------------------------------------------------------------------


def render_human_decision(completed: list[str], decision: str, why: str) -> None:
    completed_html = "".join(f"<p>{icon('check', 12, color='var(--green)')} {esc(line)}</p>" for line in completed)
    st.markdown(
        '<div class="hl-decision">'
        '<div class="hl-decision-head">'
        f'{icon("human_decision", 18, color="var(--violet)")}'
        '<span class="hl-decision-title">Human Decision Required</span>'
        "</div>"
        '<div class="hl-decision-sub">HireLoop completed autonomous work. This decision remains yours.</div>'
        f"{completed_html}"
        f"<p><b>Waiting on:</b> {esc(decision)}</p>"
        f"<p><b>Why a human:</b> {esc(why)}</p>"
        "</div>",
        unsafe_allow_html=True,
    )


# Backwards-compatible alias used by earlier draft call sites.
human_decision_banner = render_human_decision


# ---------------------------------------------------------------------------
# Truth Guard claim contrast cards
# ---------------------------------------------------------------------------


def claim_card(kind: str, steps: list[tuple[str, str]]) -> str:
    """kind: 'blocked' | 'verified'. steps: list of (step_label, text)."""
    body = "".join(
        f'<div class="hl-claim-step">{esc(step)}</div><div class="hl-claim-text">{text}</div>' for step, text in steps
    )
    return f'<div class="hl-claim-flow {kind}">{body}</div>'


# ---------------------------------------------------------------------------
# Score bars ("Opportunity DNA")
# ---------------------------------------------------------------------------


def score_bar(label: str, value: float, weight: float, contribution: float) -> None:
    pct = max(0.0, min(100.0, value))
    st.markdown(
        '<div class="hl-scorebar-row">'
        f'<div class="hl-scorebar-label"><span>{esc(label)}</span>'
        f"<span>{value:.1f}/100 · weight {weight * 100:.0f}% · contributes {contribution:.1f} pts</span></div>"
        f'<div class="hl-scorebar-track"><div class="hl-scorebar-fill" style="width:{pct:.1f}%;"></div></div>'
        "</div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Pipeline / timeline strip (Applications page)
# ---------------------------------------------------------------------------


def pipeline_timeline(steps: list[str], status_fn) -> None:
    """status_fn(step) -> True if this step is reached/complete (done),
    used with an extra "active" class the caller marks separately if
    needed. Kept simple: True => done-styled node+line, False => pending."""
    items = []
    for step in steps:
        done = status_fn(step)
        cls = "hl-pipeline-step done" if done else "hl-pipeline-step"
        items.append(f'<div class="{cls}">{esc(step)}</div>')
    st.markdown(f'<div class="hl-pipeline">{"".join(items)}</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# System / Demo status rows — colored dot + always-present text label
# ---------------------------------------------------------------------------

_STATUS_DOT_COLOR = {
    "AVAILABLE": "var(--green)",
    "CONFIGURED": "var(--green)",
    "MOCK": "var(--cyan)",
    "DEGRADED": "var(--amber)",
    "UNAVAILABLE": "var(--red)",
}


def status_row(label: str, status: str, note: str = "") -> None:
    dot_color = _STATUS_DOT_COLOR.get(status, "var(--muted-2)")
    st.markdown(
        '<div class="hl-status-row">'
        f'<span class="hl-status-dotmark" style="background:{dot_color};box-shadow:0 0 6px {dot_color};"></span>'
        f'<span class="hl-status-name">{esc(label)}</span>'
        f"{badge_html(status)}"
        f'<span class="hl-status-note">{esc(note)}</span>'
        "</div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Card title helper
# ---------------------------------------------------------------------------


def card_title(text: str) -> None:
    st.markdown(f'<div class="hl-card-title">{esc(text)}</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Presentation mode (UI-only; zero backend effect) — tightens spacing and
# hides developer-only helper captions, while every safety/demo/human
# disclosure keeps its own markup untouched (nothing in this module ever
# hides a DEMO badge or a human-decision component).
# ---------------------------------------------------------------------------


def apply_presentation_mode(active: bool) -> None:
    if not active:
        return
    st.markdown(
        "<style>"
        ".block-container { padding-top: 0.3rem !important; }"
        ".hl-dev-caption { display: none !important; }"
        "</style>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Horizontal bar rows (Strategy Intelligence primary visualization)
# ---------------------------------------------------------------------------


def bar_rows(rows: list[tuple[str, float, str]]) -> None:
    """rows: list of (label, pct_0_100, right_text). Renders each as a
    labeled horizontal bar using the same fill treatment as score_bar."""
    for label, pct, right_text in rows:
        pct = max(0.0, min(100.0, pct))
        st.markdown(
            '<div class="hl-scorebar-row">'
            f'<div class="hl-scorebar-label"><span>{esc(label)}</span><span>{esc(right_text)}</span></div>'
            f'<div class="hl-scorebar-track"><div class="hl-scorebar-fill" style="width:{pct:.1f}%;"></div></div>'
            "</div>",
            unsafe_allow_html=True,
        )


def score_ring(value: float, size: int = 108) -> None:
    """A large circular score treatment (opportunity detail hero)."""
    r = size / 2 - 8
    circumference = 2 * math.pi * r
    pct = max(0.0, min(100.0, value)) / 100.0
    offset = circumference * (1 - pct)
    cx = cy = size / 2
    svg = f"""
<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}">
  <circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="rgba(120,160,220,.16)" stroke-width="8"/>
  <circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="url(#ringGrad)" stroke-width="8"
          stroke-linecap="round" stroke-dasharray="{circumference:.1f}" stroke-dashoffset="{offset:.1f}"
          transform="rotate(-90 {cx} {cy})"/>
  <defs>
    <linearGradient id="ringGrad" x1="0" y1="0" x2="{size}" y2="{size}" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#22C7FF"/><stop offset="1" stop-color="#8B5CF6"/>
    </linearGradient>
  </defs>
  <text x="{cx}" y="{cy + 6}" text-anchor="middle" font-size="22" font-weight="800" fill="#F5F7FF"
        style="font-family:Inter,sans-serif;">{value:.0f}</text>
</svg>
"""
    st.markdown(f'<div class="hl-radial-wrap" style="display:flex;justify-content:center;">{svg}</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Central circular workflow visualization (replaces the eight giant
# rectangular stage cards entirely on Mission Control)
# ---------------------------------------------------------------------------

WORKFLOW_STAGES = ["DISCOVER", "SCORE", "TAILOR", "VERIFY", "APPLY", "TRACK", "LEARN", "IMPROVE"]

_WF_COLOR = {"done": "#31D17C", "active": "#22C7FF", "human": "#8B5CF6", "waiting": "#3A4560"}
_WF_STATUS_LABEL = {"done": "Complete", "active": "In progress", "human": "Human decision", "waiting": "Waiting"}


def workflow_loop(stage_status: dict[str, str]) -> None:
    """SVG/CSS circular (elliptical) workflow visualization. Nodes for
    DISCOVER..IMPROVE arranged around an ellipse; a human icon sits at the
    center with 'HUMAN IN THE LOOP'. Status per stage is supplied by the
    caller from real state — never invented here."""
    stages = WORKFLOW_STAGES
    n = len(stages)
    w, h = 620, 300
    cx, cy = w / 2, h / 2
    rx, ry = 250, 108

    nodes_svg = []
    labels_html = []
    for i, stage in enumerate(stages):
        angle = -math.pi / 2 + (2 * math.pi * i / n)
        x = cx + rx * math.cos(angle)
        y = cy + ry * math.sin(angle)
        status = stage_status.get(stage, "waiting")
        color = _WF_COLOR[status]
        node_cls = ""
        if status == "human":
            node_cls = "hl-wf-human-decision"
        elif status == "active":
            node_cls = "hl-wf-active"
        ring_r = 21
        nodes_svg.append(
            f'<g class="{node_cls}">'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{ring_r}" fill="#0B1628" stroke="{color}" stroke-width="2.4"/>'
            f'<text x="{x:.1f}" y="{y + 3.5:.1f}" text-anchor="middle" font-size="8.5" font-weight="800" '
            f'fill="{color}" style="font-family:Inter,sans-serif;">{i + 1}</text>'
            "</g>"
        )
        label_top = y > cy
        badge = (
            f'<div style="font-size:0.58rem;font-weight:700;color:var(--violet);margin-top:0.1rem;">HUMAN DECISION</div>'
            if status == "human"
            else ""
        )
        labels_html.append(
            f'<div style="position:absolute;left:{x / w * 100:.2f}%;top:{(y + (34 if label_top else -34)) / h * 100:.2f}%;'
            f'transform:translate(-50%,-50%);text-align:center;width:96px;">'
            f'<div class="hl-wf-label" style="color:{color};">{esc(stage)}</div>{badge}</div>'
        )

    # static ellipse guide path
    guide = f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="none" stroke="rgba(120,160,220,.14)" stroke-width="1.4" stroke-dasharray="2 4"/>'

    center_html = (
        f'<div style="position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);text-align:center;width:190px;">'
        f'<div style="display:flex;justify-content:center;margin-bottom:0.25rem;">{icon("human_decision", 26, color="var(--violet)")}</div>'
        '<div style="font-weight:800;font-size:0.82rem;letter-spacing:0.02em;color:var(--text);">HUMAN IN THE LOOP</div>'
        '<div style="font-size:0.68rem;color:var(--muted);margin-top:0.15rem;">You make the call. HireLoop does the heavy lifting.</div>'
        "</div>"
    )

    svg = f'<svg width="100%" height="{h}" viewBox="0 0 {w} {h}" style="max-width:{w}px;">{guide}{"".join(nodes_svg)}</svg>'
    st.markdown(
        f'<div class="hl-workflow-wrap"><div style="position:relative;width:100%;max-width:{w}px;">'
        f"{svg}{''.join(labels_html)}{center_html}</div></div>",
        unsafe_allow_html=True,
    )
