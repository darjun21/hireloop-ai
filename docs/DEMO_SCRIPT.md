# HireLoop AI — 5-Minute Certification Demo Script

Every step below maps to a real, working action in `app.py` — verified with
`streamlit.testing.v1.AppTest` end-to-end (Candidate → Opportunities →
select → Resume Studio approval → Applications → Mark Applied, zero
exceptions, real LangGraph state throughout). Run with `DEMO_MODE=true`
(the default) and no external services configured — everything shown is
produced by the real backend using the Mock LLM provider and local evidence
retrieval.

**0:00–0:30 — Problem & intro.** State the problem: manually comparing
postings and hand-tailoring a resume for each one doesn't compound. Open
the app — sidebar shows "HireLoop AI" / "Every application makes the next
one smarter."

**0:30–1:00 — Candidate profile.** Candidate page → check "Use the seeded
demo candidate" → Run HireLoop Search. Point out skills/experience/projects
are labeled *(resume-derived)* and target roles/locations/work-mode are
labeled *(candidate-provided preference)* — never conflated.

**1:00–1:40 — 14 jobs processed.** Opportunities page. Point out the count
of opportunities analyzed, the score/recommendation/confidence on each
card, and the sparse-listing warning on `job_review_001` ("Limited job
description evidence"). Use the filters (role family, recommendation, work
mode, min score) to show the list is live-filterable, sorted by score
descending.

**1:40–2:10 — Score & selection.** Click "View details" on `job_ai_001`
(Senior AI Engineer). Walk through the full 7-component score breakdown
table, the recommendation/confidence/scoring-model-version row, and the
"Why this matches" / gaps-risks panel. Click "SELECT OPPORTUNITY" — this is
the real LangGraph human-selection interrupt resuming, not a UI-only state
change.

**2:10–3:10 — Tailor + Truth Guard (the core safety moment).** Resume
Studio page. Point out the Truth Guard summary counts (Verified /
Partially Supported / Unsupported / Needs Confirmation). Scroll to the
"Removed (unsupported, could not be corrected)" section and show the
Kubernetes claim: **"✕ UNSUPPORTED — Deployed production workloads using
Kubernetes."** — job_ai_001 lists Kubernetes as a preferred skill, the
demo candidate's resume never mentions it, and Truth Guard correctly
blocked it from ever reaching the approval screen. This is the single most
important beat of the demo: an ungrounded claim never got a chance to be
approved.

**3:10–3:35 — Approval.** Still on Resume Studio: show the offered
(VERIFIED-only) modifications, click "Approve all safe changes." Point out
the resulting "Resume Version Created" block — Version ID, Target Job,
Approved/Rejected counts, and "Original Resume Preserved."

**3:35–4:05 — Tracker.** Applications page. The newly created application
appears in "New Application Ready" — click "Mark Applied." Show the tracked
application card (status, resume version, event timeline) — note every
status change here is a manual human action, never an automatic submission.

**4:05–4:35 — Outcome & learning.** On the same application card, expand
"Record outcome," submit an outcome (e.g. Interview), then go to Strategy
page. Show the role-family/resume-version/work-mode tables (only populated
groups shown) and a Strategy Insight card with OBSERVED DATA vs. AI
INTERPRETATION visually separated, plus its actionability label — call out
that a tiny difference on a small sample is honestly reported as
`NO_CLEAR_SIGNAL` rather than spun into false confidence.

**4:35–5:00 — Trace, architecture, closing.** Expand "How HireLoop handled
this search" (Decision Trace) on any page to show the plain-language
observable-action log — never hidden chain-of-thought. Close on System/Demo
page: the HireLoop loop diagram (DISCOVER → SCORE → TAILOR → VERIFY →
APPLY → TRACK → LEARN → IMPROVE) and the provider status table, both
showing this ran entirely offline. Closing line: "HireLoop is not an
auto-apply bot — every consequential step here was a human decision the
system supported, never replaced."
