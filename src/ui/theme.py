"""
HireLoop Mission Control — visual theme (presentation-layer recomposition).

Pure presentation: CSS custom properties, one global stylesheet injected
once per page load, the original "human-in-the-loop" logo mark, a small
inline line-icon set, and the compact reusable "human decision" component.
Nothing in this module reads or computes application state — callers in
app.py / mission_control.py supply every real value; this module only
formats markup and CSS.
"""

from __future__ import annotations

import html

import streamlit as st

# ---------------------------------------------------------------------------
# Design tokens (exact hex values from the design spec)
# ---------------------------------------------------------------------------

CSS_VARS = """
:root {
    --bg: #050B16;
    --sidebar: #08111F;
    --panel: #0B1628;
    --panel-alt: #0E1B30;
    --border: rgba(120,160,220,.16);
    --text: #F5F7FF;
    --muted: #8D9AB2;
    --muted-2: #64708A;
    --cyan: #22C7FF;
    --blue: #2684FF;
    --violet: #8B5CF6;
    --green: #31D17C;
    --amber: #F6B73C;
    --red: #FF5C67;
    --radius: 12px;
    --radius-sm: 8px;
    --shadow-1: 0 12px 35px rgba(0,0,0,.22);
    --grad: linear-gradient(135deg, var(--cyan), var(--violet));
}
"""

_KEYFRAMES = """
@media (prefers-reduced-motion: no-preference) {
  @keyframes hl-loop-chase {
    0%   { stroke-dashoffset: 0; }
    100% { stroke-dashoffset: -276; }
  }
  @keyframes hl-node-pulse {
    0%, 100% { filter: drop-shadow(0 0 0px rgba(139,92,246,.0)); opacity: 1; }
    50%      { filter: drop-shadow(0 0 7px rgba(139,92,246,.85)); opacity: .82; }
  }
  @keyframes hl-active-glow {
    0%, 100% { filter: drop-shadow(0 0 0px rgba(34,199,255,.0)); }
    50%      { filter: drop-shadow(0 0 6px rgba(34,199,255,.75)); }
  }
  .hl-logo-ring-anim { animation: hl-loop-chase 6s linear infinite; }
  .hl-wf-human-decision { animation: hl-node-pulse 2.1s ease-in-out infinite; }
  .hl-wf-active { animation: hl-active-glow 2.4s ease-in-out infinite; }
}
@media (prefers-reduced-motion: reduce) {
  .hl-logo-ring-anim { stroke-dashoffset: 0 !important; }
}
"""

GLOBAL_CSS = f"""
<style>
{CSS_VARS}
{_KEYFRAMES}

/* ---------- Base / chrome removal ---------- */
header[data-testid="stHeader"] {{ background: transparent; height: 0; min-height: 0; }}
[data-testid="stToolbar"], .stDeployButton, #MainMenu, footer {{ display: none !important; visibility: hidden !important; }}
[data-testid="stDecoration"] {{ display: none !important; }}

.stApp {{ background: var(--bg); color: var(--text); }}
.block-container {{ padding-top: 0.6rem !important; padding-bottom: 1.5rem !important; max-width: 1560px; }}
html, body, [class*="css"] {{
    font-family: Inter, ui-sans-serif, system-ui, "Segoe UI", Roboto, sans-serif;
}}
.stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5 {{ color: var(--text); letter-spacing: -0.01em; }}
.stApp h2 {{ font-size: 1.9rem !important; }}
.stApp h3 {{ font-size: 1.25rem !important; }}
.stApp p, .stApp label, .stApp span, .stApp li {{ color: var(--text); }}
.stApp small, .stApp .stCaption, [data-testid="stCaptionContainer"] {{ color: var(--muted) !important; font-size: 0.78rem; }}
hr {{ border-color: var(--border) !important; }}
a {{ color: var(--cyan) !important; }}

/* ---------- Sidebar shell ---------- */
[data-testid="stSidebar"] {{
    background: var(--sidebar);
    border-right: 1px solid var(--border);
    min-width: 258px !important;
    max-width: 258px !important;
}}
[data-testid="stSidebar"] * {{ color: var(--text); }}
[data-testid="stSidebar"] .block-container {{ padding-top: 1rem !important; padding-left: 0.85rem; padding-right: 0.85rem; }}
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {{ color: var(--muted) !important; }}

/* Nav rows — fully hide native radio chrome, render as icon+label rows */
[data-testid="stSidebar"] div[role="radiogroup"] {{ gap: 0.2rem; }}
[data-testid="stSidebar"] div[role="radiogroup"] label {{
    position: relative;
    display: flex;
    align-items: center;
    background: transparent;
    border-radius: var(--radius-sm);
    padding: 0.5rem 0.6rem 0.5rem 2.15rem;
    margin: 0 !important;
    border: 1px solid transparent;
    border-left: 3px solid transparent;
    transition: background .12s ease, border-color .12s ease;
    width: 100%;
    cursor: pointer;
}}
[data-testid="stSidebar"] div[role="radiogroup"] label::before {{
    content: "";
    position: absolute;
    left: 0.65rem;
    top: 50%;
    transform: translateY(-50%);
    width: 16px;
    height: 16px;
    background-repeat: no-repeat;
    background-position: center;
    background-size: contain;
    opacity: .82;
}}
[data-testid="stSidebar"] div[role="radiogroup"] label:hover {{ background: var(--panel-alt); }}
[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) {{
    background: linear-gradient(90deg, rgba(139,92,246,.16), rgba(34,199,255,.05));
    border-left-color: var(--violet);
}}
[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) p {{ color: var(--text) !important; font-weight: 700; }}
[data-testid="stSidebar"] div[role="radiogroup"] input {{ display: none; }}
[data-testid="stSidebar"] div[role="radiogroup"] label > div:first-child {{ display: none; }}
[data-testid="stSidebar"] div[role="radiogroup"] p {{ font-size: 0.85rem; font-weight: 600; color: var(--muted); margin: 0; }}

/* ---------- Metrics / containers / expanders ---------- */
[data-testid="stMetric"] {{
    background: var(--panel-alt); border: 1px solid var(--border);
    border-radius: var(--radius-sm); padding: 0.6rem 0.8rem;
}}
[data-testid="stMetricLabel"] {{ color: var(--muted) !important; font-size: 0.75rem !important; }}
[data-testid="stMetricValue"] {{ color: var(--cyan) !important; font-size: 1.3rem !important; }}

div[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]) {{
    background: var(--panel);
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
    box-shadow: var(--shadow-1);
    transition: border-color .15s ease;
}}
div[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]):hover {{
    border-color: rgba(139,92,246,.4) !important;
}}
div[data-testid="stVerticalBlockBorderWrapper"] > div > [data-testid="stVerticalBlock"] {{ border-radius: var(--radius); }}
div[data-testid="stExpander"] {{ background: var(--panel-alt); border: 1px solid var(--border) !important; border-radius: var(--radius); }}
div[data-testid="stExpander"] summary {{ color: var(--text) !important; font-size: 0.85rem; }}

/* ---------- Buttons ---------- */
.stButton > button {{
    border-radius: var(--radius-sm); border: 1px solid var(--border);
    background: var(--panel-alt); color: var(--text); font-weight: 600; font-size: 0.85rem;
    transition: border-color .12s ease, transform .08s ease, filter .12s ease;
}}
.stButton > button:hover {{ border-color: var(--cyan); color: var(--cyan); transform: translateY(-1px); }}
.stButton > button:active {{ transform: translateY(0px); }}
.stButton > button[kind="primary"] {{
    background: var(--grad); border-color: transparent; color: #061019; font-weight: 700;
}}
.stButton > button[kind="primary"]:hover {{ filter: brightness(1.1); color: #061019; transform: translateY(-1px); }}

/* ---------- Form widgets, dark-adapted ---------- */
.stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"] > div,
.stMultiSelect div[data-baseweb="select"] > div, textarea {{
    background: var(--panel-alt) !important; color: var(--text) !important; border-color: var(--border) !important;
}}
[data-testid="stFileUploader"] section {{ background: var(--panel-alt); border-color: var(--border) !important; }}
[data-testid="stCheckbox"] label p {{ color: var(--text) !important; font-size: 0.85rem; }}

/* ================= HireLoop shell components ================= */

/* Compact top app bar (~68px) */
.hl-topbar {{
    display: flex; align-items: center; gap: 0.75rem;
    padding: 0.5rem 0.95rem;
    margin-bottom: 0.7rem;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    box-shadow: var(--shadow-1);
    min-height: 52px;
}}
.hl-topbar .hl-title {{ font-size: 1.02rem; font-weight: 800; color: var(--text); line-height: 1.15; }}
.hl-topbar .hl-tagline {{ color: var(--muted); font-size: 0.74rem; line-height: 1.15; }}
.hl-topbar .hl-spacer {{ flex-grow: 1; }}
.hl-status-dot {{ display: inline-flex; align-items: center; gap: 0.4rem; font-size: 0.72rem; color: var(--muted); font-weight: 600; }}
.hl-status-dot .dot {{ width: 7px; height: 7px; border-radius: 50%; background: var(--green); box-shadow: 0 0 6px var(--green); }}

/* Sidebar brand */
.hl-sidebar-brand {{
    display: flex; align-items: center; gap: 0.55rem;
    padding: 0.15rem 0.05rem 0.75rem 0.05rem;
    border-bottom: 1px solid var(--border);
    margin-bottom: 0.55rem;
}}
.hl-sidebar-brand .hl-wordmark {{ font-weight: 800; font-size: 1rem; letter-spacing: -0.01em; color: var(--text); line-height: 1.15; }}
.hl-sidebar-brand .hl-tag {{ font-size: 0.65rem; color: var(--muted); line-height: 1.2; }}

.hl-nav-label {{
    font-size: 0.66rem; font-weight: 700; letter-spacing: 0.08em;
    color: var(--muted-2); text-transform: uppercase; margin: 0.8rem 0 0.25rem 0.15rem;
}}

/* Badges */
.hl-badge {{
    display: inline-flex; align-items: center; gap: 0.3rem;
    font-size: 0.65rem; font-weight: 700; letter-spacing: 0.03em;
    padding: 0.2rem 0.5rem; border-radius: 999px; border: 1px solid transparent;
    text-transform: uppercase; white-space: nowrap;
}}
.hl-badge-success {{ background: rgba(49,209,124,.12); color: var(--green); border-color: rgba(49,209,124,.4); }}
.hl-badge-warning {{ background: rgba(246,183,60,.12); color: var(--amber); border-color: rgba(246,183,60,.4); }}
.hl-badge-danger  {{ background: rgba(255,92,103,.12); color: var(--red); border-color: rgba(255,92,103,.4); }}
.hl-badge-info    {{ background: rgba(34,199,255,.12); color: var(--cyan); border-color: rgba(34,199,255,.4); }}
.hl-badge-neutral {{ background: rgba(141,154,178,.12); color: var(--muted); border-color: rgba(141,154,178,.32); }}
.hl-badge-violet  {{ background: rgba(139,92,246,.14); color: var(--violet); border-color: rgba(139,92,246,.45); }}
.hl-badge-mode-demo {{ background: rgba(246,183,60,.14); color: var(--amber); border-color: rgba(246,183,60,.5); }}
.hl-badge-mode-live {{ background: rgba(49,209,124,.14); color: var(--green); border-color: rgba(49,209,124,.5); }}

/* Compact one-line stage indicator (replaces giant stage cards) */
.hl-stage-line {{
    display: flex; align-items: center; flex-wrap: wrap; gap: 0.35rem;
    font-size: 0.72rem; font-weight: 700; letter-spacing: 0.02em;
    color: var(--muted-2); margin: 0.15rem 0 0.85rem 0;
}}
.hl-stage-line .seg {{ display: inline-flex; align-items: center; gap: 0.22rem; padding: 0.12rem 0; }}
.hl-stage-line .seg .mark {{ font-size: 0.85rem; line-height: 1; }}
.hl-stage-line .seg.done {{ color: var(--green); }}
.hl-stage-line .seg.active {{ color: var(--cyan); }}
.hl-stage-line .seg.human {{ color: var(--violet); }}
.hl-stage-line .seg.waiting {{ color: var(--muted-2); }}
.hl-stage-line .sep {{ color: var(--muted-2); opacity: .5; }}

/* KPI dense cards */
.hl-kpi-row {{ display: flex; gap: 0.55rem; margin-bottom: 0.75rem; flex-wrap: wrap; }}
.hl-kpi-card {{
    flex: 1 1 0; min-width: 138px;
    background: var(--panel); border: 1px solid var(--border); border-radius: var(--radius);
    padding: 0.65rem 0.8rem; box-shadow: var(--shadow-1);
    display: flex; align-items: center; gap: 0.6rem;
}}
.hl-kpi-card .hl-kpi-icon {{
    flex: 0 0 auto; width: 32px; height: 32px; border-radius: 8px;
    display: flex; align-items: center; justify-content: center;
    background: rgba(34,199,255,.10); color: var(--cyan);
}}
.hl-kpi-card .hl-kpi-icon svg {{ width: 16px; height: 16px; }}
.hl-kpi-card .hl-kpi-value {{ font-size: 1.35rem; font-weight: 800; color: var(--text); line-height: 1.05; }}
.hl-kpi-card .hl-kpi-label {{ font-size: 0.68rem; color: var(--muted); margin-top: 0.1rem; white-space: nowrap; }}

/* Generic panel/card */
.hl-card-title {{
    font-weight: 700; font-size: 0.72rem; color: var(--muted);
    display: flex; align-items: center; gap: 0.4rem; margin-bottom: 0.6rem;
    text-transform: uppercase; letter-spacing: 0.06em;
}}

/* Empty state — compact, not a giant rectangle */
.hl-empty-compact {{
    display: flex; align-items: center; gap: 0.9rem; flex-wrap: wrap;
    padding: 0.95rem 1.1rem;
    background: var(--panel); border: 1px solid var(--border); border-radius: var(--radius);
    margin: 0.5rem 0 1rem 0; box-shadow: var(--shadow-1);
}}
.hl-empty-compact .hl-empty-icon {{
    flex: 0 0 auto; width: 40px; height: 40px; border-radius: 10px;
    background: rgba(139,92,246,.12); display: flex; align-items: center; justify-content: center; color: var(--violet);
}}
.hl-empty-compact .hl-empty-title {{ font-size: 0.95rem; font-weight: 800; color: var(--text); }}
.hl-empty-compact .hl-empty-sub {{ color: var(--muted); font-size: 0.8rem; max-width: 480px; }}
.hl-empty-compact .hl-empty-body {{ flex: 1 1 260px; min-width: 220px; }}

/* Human decision component (reusable, every interrupt) */
.hl-decision {{
    border: 1px solid var(--violet);
    background: linear-gradient(135deg, rgba(139,92,246,.12), rgba(34,199,255,.03));
    border-radius: var(--radius);
    padding: 0.9rem 1.05rem;
    margin: 0.6rem 0 0.85rem 0;
    box-shadow: 0 0 0 1px rgba(139,92,246,.15), 0 0 22px rgba(139,92,246,.10);
}}
.hl-decision .hl-decision-head {{ display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.45rem; }}
.hl-decision .hl-decision-title {{
    font-weight: 800; color: var(--violet); letter-spacing: 0.04em;
    font-size: 0.78rem; text-transform: uppercase;
}}
.hl-decision .hl-decision-sub {{ color: var(--muted); font-size: 0.78rem; font-style: italic; margin-bottom: 0.5rem; }}
.hl-decision p {{ margin: 0.18rem 0; color: var(--text); font-size: 0.85rem; }}
.hl-decision b {{ color: var(--text); }}

/* Truth Guard claim contrast cards */
.hl-claim-flow {{ border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 0.75rem 0.9rem; background: var(--panel-alt); height: 100%; }}
.hl-claim-flow.blocked {{ border-color: rgba(255,92,103,.5); background: rgba(255,92,103,.05); }}
.hl-claim-flow.verified {{ border-color: rgba(49,209,124,.5); background: rgba(49,209,124,.05); }}
.hl-claim-flow .hl-claim-step {{ color: var(--muted); font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 700; margin-top: 0.45rem; }}
.hl-claim-flow .hl-claim-step:first-child {{ margin-top: 0; }}
.hl-claim-flow .hl-claim-text {{ color: var(--text); margin: 0.12rem 0 0 0; font-size: 0.83rem; }}

/* Score bars */
.hl-scorebar-row {{ margin: 0.5rem 0; }}
.hl-scorebar-label {{ display: flex; justify-content: space-between; font-size: 0.78rem; color: var(--text); margin-bottom: 0.22rem; }}
.hl-scorebar-track {{ background: var(--panel-alt); border: 1px solid var(--border); border-radius: 999px; height: 7px; overflow: hidden; }}
.hl-scorebar-fill {{ height: 100%; border-radius: 999px; background: var(--grad); }}

/* Pipeline / timeline strip */
.hl-pipeline {{ display: flex; align-items: center; margin: 0.5rem 0 0.4rem 0; }}
.hl-pipeline-step {{
    flex: 1 1 0; text-align: center; position: relative;
    font-size: 0.62rem; font-weight: 700; letter-spacing: 0.03em; color: var(--muted-2);
    padding-top: 14px;
}}
.hl-pipeline-step::before {{
    content: ""; position: absolute; top: 4px; left: -50%; width: 100%; height: 2px; background: var(--border);
}}
.hl-pipeline-step:first-child::before {{ display: none; }}
.hl-pipeline-step::after {{
    content: ""; position: absolute; top: 0px; left: 50%; transform: translateX(-50%);
    width: 8px; height: 8px; border-radius: 50%; background: var(--panel-alt); border: 2px solid var(--border);
}}
.hl-pipeline-step.done {{ color: var(--green); }}
.hl-pipeline-step.done::after {{ background: var(--green); border-color: var(--green); }}
.hl-pipeline-step.done::before {{ background: var(--green); }}
.hl-pipeline-step.hl-pipeline-active {{ color: var(--cyan); }}
.hl-pipeline-step.hl-pipeline-active::after {{ background: var(--cyan); border-color: var(--cyan); box-shadow: 0 0 6px var(--cyan); }}

/* Status rows (System page) */
.hl-status-row {{ display: flex; align-items: center; gap: 0.7rem; padding: 0.5rem 0.1rem; border-bottom: 1px solid var(--border); }}
.hl-status-row:last-child {{ border-bottom: none; }}
.hl-status-row .hl-status-dotmark {{ width: 8px; height: 8px; border-radius: 50%; flex: 0 0 auto; }}
.hl-status-row .hl-status-name {{ font-weight: 600; font-size: 0.83rem; flex: 0 0 190px; color: var(--text); }}
.hl-status-row .hl-status-note {{ color: var(--muted); font-size: 0.76rem; }}

/* Circular workflow visualization */
.hl-workflow-wrap {{ display: flex; justify-content: center; margin: 0.4rem 0 1rem 0; }}
.hl-wf-label {{ font-size: 0.6rem; font-weight: 700; letter-spacing: 0.03em; text-transform: uppercase; }}

/* Sidebar loop mini */
.hl-loop-mini-wrap {{ display: flex; justify-content: center; padding: 0.4rem 0; }}

/* Opportunity grid */
.hl-opp-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(430px, 1fr)); gap: 0.7rem; }}

/* Presentation mode: tightened spacing, dev captions hidden */
.hl-presentation .block-container {{ padding-top: 0.35rem !important; }}
.hl-presentation .hl-dev-caption {{ display: none !important; }}
</style>
"""


def inject_global_css() -> None:
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Logo — human-in-the-loop mark
# ---------------------------------------------------------------------------


def render_hireloop_logo(size: int = 32, animate: bool = True) -> str:
    """Inline SVG: a continuous infinity/feedback loop (cyan left arc,
    violet right arc) with a minimal geometric human silhouette integrated
    inside the loop's right-hand opening. Two overlapping rings read as a
    figure-eight / infinity motif at any size; a thin bright dash chases
    around each ring's circumference (CSS stroke-dashoffset animation,
    off under prefers-reduced-motion) to suggest continuous learning.
    Original mark — not a copy of any real company's logo.
    """
    anim_cls = "hl-logo-ring-anim" if animate else ""
    return f"""
<svg width="{size}" height="{size}" viewBox="0 0 96 64" fill="none" xmlns="http://www.w3.org/2000/svg" style="flex-shrink:0;">
  <defs>
    <linearGradient id="hlGradL" x1="0" y1="0" x2="64" y2="64" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#22C7FF"/>
      <stop offset="1" stop-color="#8B5CF6"/>
    </linearGradient>
    <linearGradient id="hlGradR" x1="32" y1="0" x2="96" y2="64" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#22C7FF"/>
      <stop offset="1" stop-color="#8B5CF6"/>
    </linearGradient>
  </defs>
  <!-- left loop (cyan-leaning) -->
  <circle cx="32" cy="32" r="22" stroke="url(#hlGradL)" stroke-width="4.4" fill="none" opacity="0.9"/>
  <!-- right loop (violet-leaning) -->
  <circle cx="64" cy="32" r="22" stroke="url(#hlGradR)" stroke-width="4.4" fill="none"/>
  <!-- animated chase dash tracing the right loop -->
  <circle cx="64" cy="32" r="22" stroke="#EAF6FF" stroke-width="2.2" fill="none"
          stroke-linecap="round" stroke-dasharray="10 128" opacity="0.9" class="{anim_cls}"/>
  <!-- minimal geometric human silhouette centered inside the right loop -->
  <g>
    <circle cx="64" cy="23.5" r="4.6" fill="#F5F7FF"/>
    <path d="M55.5 42c0-6.6 4.2-11 8.5-11s8.5 4.4 8.5 11" stroke="#F5F7FF" stroke-width="4" stroke-linecap="round" fill="none"/>
    <path d="M60 42.5 L57 48 M68 42.5 L71 48" stroke="#F5F7FF" stroke-width="3" stroke-linecap="round"/>
  </g>
</svg>
"""


def render_hireloop_wordmark(
    size: int = 34,
    tagline: bool = True,
    supporting: bool = False,
    animate: bool = True,
) -> str:
    """Primary lockup: [logo] HireLoop AI + tagline, optionally the
    supporting human-in-the-loop / AI-on-the-loop phrase underneath."""
    tagline_html = (
        '<div class="hl-tagline">Every application makes the next one smarter.</div>' if tagline else ""
    )
    supporting_html = (
        '<div style="color:var(--muted-2);font-size:0.66rem;margin-top:0.15rem;font-style:italic;">'
        "Human in the loop. AI on the loop. Better outcomes.</div>"
        if supporting
        else ""
    )
    return (
        '<div style="display:flex;align-items:center;gap:0.6rem;">'
        f"{render_hireloop_logo(size, animate=animate)}"
        '<div><div class="hl-title" style="font-weight:800;">HireLoop AI</div>'
        f"{tagline_html}{supporting_html}</div></div>"
    )


# ---------------------------------------------------------------------------
# Compact outline icon set (line-style, 24x24 viewBox, currentColor stroke)
# ---------------------------------------------------------------------------

_ICON_PATHS: dict[str, str] = {
    "mission_control": '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3"/>',
    "opportunities": '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="4.2"/><circle cx="12" cy="12" r="0.6" fill="currentColor" stroke="none"/>',
    "resume": '<path d="M6 3h9l4 4v14a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z"/><path d="M9 12h6M9 16h6M9 8h3"/>',
    "applications": '<path d="M4 4l16 8-16 8 4-8-4-8z"/>',
    "strategy": '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
    "system": '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1 1.55V21a2 2 0 1 1-4 0v-.09A1.7 1.7 0 0 0 9 19.4a1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-1.55-1H3a2 2 0 1 1 0-4h.09A1.7 1.7 0 0 0 4.6 9a1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-1.55V3a2 2 0 1 1 4 0v.09a1.7 1.7 0 0 0 1 1.55 1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.7 1.7 0 0 0 19.4 9a1.7 1.7 0 0 0 1.55 1H21a2 2 0 1 1 0 4h-.09a1.7 1.7 0 0 0-1.55 1z"/>',
    "candidate": '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4.4 3.6-8 8-8s8 3.6 8 8"/>',
    "truth_guard": '<path d="M12 2l8 3v6c0 5-3.4 8.4-8 11-4.6-2.6-8-6-8-11V5l8-3z"/><path d="M9 12l2 2 4-4"/>',
    "agent": '<rect x="4" y="7" width="16" height="12" rx="2"/><path d="M12 3v4M9 12h.01M15 12h.01M8 19v2M16 19v2"/>',
    "human_decision": '<circle cx="12" cy="8" r="3.4"/><path d="M6 20c0-3.6 2.8-6 6-6s6 2.4 6 6"/><path d="M3 4l3 3M21 4l-3 3"/>',
    "check": '<path d="M20 6L9 17l-5-5"/>',
    "shield_x": '<path d="M12 2l8 3v6c0 5-3.4 8.4-8 11-4.6-2.6-8-6-8-11V5l8-3z"/><path d="M9.5 9.5l5 5M14.5 9.5l-5 5"/>',
    "kpi_search": '<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>',
    "kpi_star": '<path d="M12 2l3 6.6 7 .9-5 5 1.3 7-6.3-3.4-6.3 3.4 1.3-7-5-5 7-.9z"/>',
    "kpi_send": '<path d="M4 4l16 8-16 8 4-8-4-8z"/>',
    "kpi_mic": '<rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v4M8 22h8"/>',
    "kpi_chart": '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
    "bolt": '<path d="M13 2 4 14h6l-1 8 9-12h-6l1-8z"/>',
}


def icon(name: str, size: int = 16, color: str = "currentColor", stroke_width: float = 2.0) -> str:
    """A small inline outline SVG icon (24x24 viewBox). Used inside
    st.markdown(unsafe_allow_html=True) blocks — not inside native widget
    labels, which Streamlit does not render as HTML."""
    path = _ICON_PATHS.get(name, _ICON_PATHS["bolt"])
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
        f'stroke="{color}" stroke-width="{stroke_width}" stroke-linecap="round" '
        f'stroke-linejoin="round" xmlns="http://www.w3.org/2000/svg">{path}</svg>'
    )


def esc(value: object) -> str:
    return html.escape(str(value)) if value is not None else ""
