# HireLoop AI

**Every application makes the next one smarter.**

HireLoop AI helps job seekers identify and pursue high-fit opportunities in
one web application, replacing hours of job comparison and manual resume
tailoring. It autonomously processes and evaluates opportunities, prepares
evidence-grounded resume recommendations, hands off consequential decisions
to the user, and learns from recorded outcomes to improve future strategy.

**HireLoop is not an auto-apply bot.** It never submits an application to an
employer, never scrapes live job boards, and never makes a consequential
decision (which job to pursue, what resume changes to keep, what to record
as an outcome) without an explicit human action. An optional, opt-in "Live
Job Discovery" mode can query the You.com Web Search API for job pages — see
[Live Job Discovery](#live-job-discovery) below — but it is read-only,
human-triggered, and never used by the default demo path.

## Problem

Job seekers evaluating dozens of postings do the same work over and over:
reading a description, guessing how well they fit, hand-editing a resume per
role, and rarely tracking what actually worked. That process doesn't
compound — each application starts from the same blank state as the last
one.

## Solution

HireLoop turns that loop into a system: it scores opportunities against a
candidate's real profile using a transparent, versioned formula (not a black
box); tailors resume language against evidence it can point to, with a
dedicated verification agent that blocks anything it can't support; and
tracks real outcomes so its own strategy suggestions get more grounded over
time — all while keeping every consequential step in the user's hands.

## Core Philosophy

- **Deterministic where correctness matters, agentic where judgment is
  needed.** Scoring, deduplication, job-quality flags, outcome analytics,
  and actionability classification are plain Python — reproducible and
  auditable. LLM agents are used only where genuine reasoning is required
  (resume extraction, tailoring language, qualitative match interpretation),
  and every agent's output passes through deterministic validation that can
  reject or cap it.
- **Fail closed, never fail silent.** When a verification layer can't reach
  a confident answer, it defaults to the safer, more conservative status —
  never to "assume it's fine."
- **Human-in-the-loop for every consequential action.** Job selection,
  resume approval, and application/outcome recording are real pauses in the
  workflow, not confirmations layered on top of something that already
  happened.
- **Grounded, not persuasive.** Every claim HireLoop's agents produce —
  resume language, match explanations, strategy recommendations — must
  trace back to real evidence or real recorded data. No invented numbers, no
  causal claims the data doesn't support.

## Why Agentic AI

A rule engine alone can't extract a resume, judge whether "used Kubernetes"
is a fair rewording of "deployed containerized services," or write a
qualitative explanation of why a job fits. But an LLM alone can't be trusted
to grade its own output, respect scoring weights, or resist inventing a
number that sounds plausible. HireLoop's architecture is built around that
tension: agents do the reasoning, deterministic code does the judging.

## Architecture

LangGraph orchestrates the pipeline as a single checkpointed graph (plus a
second graph for outcome updates, invoked separately once an outcome is
known). Full system diagrams, state model, and node table:
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Workflow

Resume in → parse → build candidate profile → score & rank opportunities →
**human selects one** → prepare evidence → tailor resume → Truth Guard
verifies → bounded auto-correction → **human clarification** (if needed) →
**human resume approval** → resume version created → application record
created → **human records what they did** → *(later)* **human records an
outcome** → outcome analytics recomputed → Learning Agent proposes a
grounded, hedged insight. Full node-by-node mechanics, routing, and error
taxonomy: [docs/WORKFLOW.md](docs/WORKFLOW.md).

## Agents

| Agent | Job | Cannot do |
|---|---|---|
| Profile Agent | Structures a parsed resume into a candidate profile | Score or rank anything |
| Match Analyst | Explains a computed score (strengths/gaps/risks) | Modify the frozen numeric score |
| Resume Tailor | Proposes resume language for a selected job (may overreach) | Save or submit anything directly |
| Truth Guard | Verifies every proposed claim against real evidence | Let an LLM upgrade a deterministic UNSUPPORTED, or upgrade skills-only evidence to VERIFIED |
| Learning Agent | Interprets outcome analytics into a strategy insight | Compute its own metrics, invent numbers, use causal language, or change scoring weights |

## Deterministic Services

Normalization, deduplication, job-quality scoring (including
requirement-completeness / sparse-listing detection), the Opportunity
Scoring Engine, outcome analytics, and actionability classification
(`src/services/actionability.py`) are all plain, versioned Python — no LLM
call sits on their critical path, and their output is what every agent is
graded against, never the reverse.

## Opportunity Intelligence

Each opportunity gets a versioned, weighted score (skill match, experience
match, target-role alignment, location/work-mode fit, candidate preference
alignment, historical outcome signal capped at its configured weight, and
job quality) plus a recommendation, a confidence level, and a full component
breakdown. A sparse job description is flagged rather than silently scored
as if it were a rich one.

## Truth Guard

A three-layer hybrid: deterministic pre-checks catch the clear-cut cases
(unsupported technology, inflated title, invented metrics); an LLM handles
genuinely ambiguous wording; a deterministic post-validation layer can only
make the result *more* conservative, never less. Full design and reasoning:
[docs/TRUTH_GUARD.md](docs/TRUTH_GUARD.md).

## Human-in-the-Loop

Five real interrupts, each a genuine LangGraph pause with SQLite-backed
checkpointing: job selection, clarification, resume approval, application
action, and outcome recording. Nothing downstream of any of these happens
without the corresponding human action reaching the graph.

## Application Tracking

Applications and their event history live in a dedicated business SQLite
database, separate from the workflow checkpoint database. Status changes
are only ever recorded by explicit human action — never inferred, never
submitted anywhere by HireLoop itself.

## Learning Loop

Once an outcome is recorded, deterministic `OutcomeAnalytics` recompute
grouped response/interview/offer rates (never double-counting a multi-stage
progression), and the Learning Agent proposes a `LearningInsight` — but only
after deterministic validation rejects invented numbers and causal language,
and only after an independent **actionability** classification (effect size
× sample confidence) decides whether the observed difference is even large
enough to act on. A 33% vs. 29% difference on a small sample is correctly
labeled `NO_CLEAR_SIGNAL`, not spun into a confident recommendation. Full
design: [docs/LEARNING_LOOP.md](docs/LEARNING_LOOP.md).

## Technology Stack

- Python, Pydantic v2 for domain models
- LangGraph for orchestration, human-in-the-loop interrupts, and SQLite
  checkpointing
- Streamlit for the product UI
- Nebius / Fireworks for LLM inference, with a deterministic Mock provider
  for offline/demo use
- Pinecone for semantic evidence retrieval only (never a verdict), with a
  deterministic local fallback
- mem0 for lightweight candidate preference / strategy memory, with a
  local-only fallback
- SQLite for the workflow checkpoint store and the business system of record

## Demo Mode

`DEMO_MODE=true` runs the entire product fully offline: a seeded candidate,
a seeded batch of synthetic jobs (including a duplicate, a low-quality
listing, a sparse listing, and a spread of strong/weak matches), and a
history of synthetic past applications — all processed through the same
real backend, using the Mock LLM provider and local evidence retrieval, with
no Pinecone, mem0, or external LLM calls. Every demo figure is clearly
labeled as synthetic; it is never presented as a real user's outcome data.

## Live Job Discovery

By default HireLoop (`DEMO_MODE=true`) only evaluates the offline seeded
batch at `data/sample_jobs.json` — fully reproducible, no external calls.
Optionally, the Opportunities page offers a **LIVE SEARCH** job source that
queries the You.com Web Search API for real job pages instead. This is
strictly additive and opt-in:

- **DEMO JOBS** (default) — offline, deterministic, always available, and
  the only path exercised by the certification demo/eval suite.
- **LIVE SEARCH** (opt-in) — requires `YDC_API_KEY` and
  `YOU_SEARCH_ENABLED=true` in `.env`, and only ever runs when a human
  clicks "Search Live Jobs" on the Opportunities page (never on a page
  rerun, and never automatically).

You.com is a **discovery** tool, not a scoring or judgment tool: it returns
title/url/snippet/highlights for candidate job pages, a deterministic
(non-LLM) classifier filters out non-job results, and only then do the
results enter the same normalization, deduplication, and job-quality
pipeline that DEMO JOBS uses — followed by the same Opportunity Scoring
Engine and Match Analyst. Live-sourced cards are labeled "Source: Web
discovery / You.com" with the original URL, and are never presented as
verified-active listings. If You.com is unreachable or misconfigured, the
UI degrades to a clear message and the user can fall back to DEMO JOBS —
it never silently substitutes synthetic jobs labeled as live.

## Installation

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
pip install -r requirements-dev.txt   # for running tests/evals
```

## Environment Setup

```bash
copy .env.example .env
```

Fill in Nebius/Fireworks/Pinecone/mem0 keys only if you want live mode; the
app and demo run fully offline without any of them (`DEMO_MODE=true`, the
default). API keys are read from environment variables only, never
hardcoded or logged — see [docs/SECURITY_PRIVACY.md](docs/SECURITY_PRIVACY.md).

## Running

```bash
streamlit run app.py
```

## Testing

```bash
python -m pytest -q
```

## Evaluation

```bash
python -m evals.run_evals
```

Prints a per-category terminal summary and writes a machine-readable report
to `evals/results/latest.json`. See [docs/PROJECT_OVERVIEW.md](docs/PROJECT_OVERVIEW.md)
for the current evaluation results, [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md)
for the 5-minute demo walkthrough, and [docs/FINAL_REPORT.md](docs/FINAL_REPORT.md)
for the certification final report.

## Failure Handling

Provider unavailability, malformed LLM output, corrupt/empty input, and a
Truth Guard LLM outage are all handled without an unhandled crash and
without ever silently producing an unsafe result — verification layers fail
closed to the more conservative status rather than defaulting to "assume
it's fine." See `evals/failure_recovery.py` and docs/WORKFLOW.md's error
taxonomy.

## Privacy

Resume text is not logged beyond what's needed to run the current request;
the Decision Trace records observable actions, not resume dumps or raw
chain-of-thought. Pinecone and mem0 entries are scoped per candidate. See
[docs/SECURITY_PRIVACY.md](docs/SECURITY_PRIVACY.md) for the full breakdown.

## Limitations

By default HireLoop only evaluates the seeded/uploaded job batch it's
given. The optional Live Job Discovery mode (see above) can query You.com
for new postings, but only when explicitly enabled and human-triggered —
it is never part of the default flow. Truth Guard can only check a claim
against evidence HireLoop has recorded; it cannot verify a candidate's life.
Strategy insights require enough recorded outcome history to be actionable
and are explicitly withheld (`NO_CLEAR_SIGNAL`) when the sample is too thin
or the effect too small.

## Roadmap

Not part of this project and explicitly out of scope: automatic application
submission, per-domain job-board scraping, recruiter outreach, multi-user
authentication, and voice-based interview practice. (The optional Live Job
Discovery mode uses the You.com Web Search API for read-only discovery — it
is not a scraper and never submits anything.) See
[docs/PROJECT_OVERVIEW.md](docs/PROJECT_OVERVIEW.md) for the full deferred
list and reasoning.
