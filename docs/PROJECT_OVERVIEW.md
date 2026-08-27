# HireLoop AI — Project Overview

This document is the certification write-up foundation. It is meant to be
truthful and specific — every claim below is checkable against the code in
this repository.

## Overview

HireLoop AI is a self-improving, multi-agent job search assistant. A
candidate uploads a resume once; the system scores and ranks job
opportunities against it deterministically, tailors resume language for a
human-selected opportunity with a dedicated verification agent standing
between "proposed" and "approved," tracks what the candidate actually does
next, and learns — cautiously, with explicit sample-size and effect-size
gating — from recorded outcomes.

## Problem

Evaluating and tailoring for many job postings is repetitive, manual work
that doesn't compound: every application starts from the same blank
comparison the last one did, and there's rarely a structured record of what
actually worked.

## User

A single job seeker managing an active search across multiple roles, who
wants help triaging opportunities and tailoring their resume — without
handing over the actual decisions of what to apply to or what to submit.

## Agent one-liner

HireLoop AI helps job seekers identify and pursue high-fit opportunities in
one web application, replacing hours of job comparison and manual resume
tailoring. It autonomously processes and evaluates opportunities, prepares
evidence-grounded resume recommendations, hands off consequential decisions
to the user, and learns from recorded outcomes to improve future strategy.

## Workflow

One LangGraph graph carries a run from resume upload through resume
approval and initial application recording; a second, separate graph
handles outcome updates whenever the user later reports what happened.
Both are real, checkpointed LangGraph state machines — every human
interrupt is a genuine `interrupt()`/`Command(resume=...)` pause, not a UI
confirmation layered on top of an action that already happened. Full
node-by-node detail: [WORKFLOW.md](WORKFLOW.md).

```
resume → parse → Profile Agent → validate → preferences
  → ingest jobs → normalize → dedupe → job quality → historical signal
  → Opportunity Scoring Engine → Match Analyst → rank
  → [human selects a job]
  → prepare evidence → retrieve job-requirement evidence
  → Resume Tailor → Truth Guard → bounded auto-correction
  → [human clarification, if needed] → [human resume approval]
  → ResumeVersion created → Application record created
  → [human records what they did]

  ... later, separate graph entry point ...

  → [human records an outcome] → OutcomeAnalytics recomputed
  → Learning Agent → LearningInsight persisted → mem0 sync (fallback-safe)
```

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full system diagram, state
model, node table, and storage responsibilities.

## Agent framework

LangGraph, chosen for durable checkpointed state and first-class
human-in-the-loop `interrupt()` support — every pause in the workflow needs
to survive a page reload or a days-later resume, which a simple in-memory
agent loop cannot do.

## Tools

The "tools" an agent can reach for are deliberately narrow and typed:
resume text extraction, candidate-evidence retrieval (Pinecone or a
deterministic local fallback), and the frozen `OpportunityScore` object the
Match Analyst explains but cannot edit. No agent has a general-purpose
code-execution or filesystem tool — every action with real consequence
(saving a resume version, creating an application, recording an outcome) is
a deterministic node, not something an LLM call can trigger directly.
Optionally, You.com's Web Search API is available as a read-only job
*discovery* tool (title/url/snippet/highlights only) — it never scores,
ranks, or judges fit, is opt-in and human-triggered, and is not part of the
default DEMO_MODE tool set. See docs/DECISIONS.md #11.

## You.com live discovery — this session's disclosure

This section records exactly what happened when Live Job Discovery was
exercised against the real You.com API, once, during development — a
factual account, not a projection of what it *would* do.

- The live endpoint tested was `https://ydc-index.io/v1/search`
  (`X-API-Key` auth), confirmed directly against the real API rather than
  assumed from documentation.
- Exactly **one** paid request was made. It returned HTTP 200.
- The response genuinely had `results.web` as a documented list —
  confirmed via a direct verification script, not by modifying `app.py`.
- **10** web results were returned even though `count=5`/
  `num_web_results=5` was requested. This is reported as an observed fact;
  no assumption is made about why the vendor returned more than requested.
  HireLoop independently caps/filters downstream results and does not rely
  solely on provider-returned count — `you_search_max_results` and the
  deterministic `LIKELY_JOB` classifier both bound what actually reaches
  scoring regardless of raw API response size.
- Of the 10 results, **5** were classified `LIKELY_JOB` by the real
  deterministic classifier (`src/services/job_candidate_classification.py`).
- One `LIKELY_JOB` candidate was successfully converted into a
  `JobPosting` via the existing `candidate_to_job_posting_dict`/model
  validation path, with **no fabricated fields**: `posted_date=None`,
  `required_skills=[]`, and `salary_min=None` were all left unset because
  the vendor didn't supply them — never inferred or guessed.
- The API key was never printed, logged, or written to the Decision Trace
  at any point during this call, consistent with `src/services/you_search.py`'s
  documented discipline.

See `docs/ARCHITECTURE.md` §13 for the full Live Job Discovery pipeline
diagram (already updated to reflect this corrected endpoint/response
contract) and `docs/DECISIONS.md` #11 for why this path is opt-in and
never a certification-demo dependency.

## Models / providers

Nebius and Fireworks are supported live LLM providers
(`src/llm/http_provider.py`), selected via `DEFAULT_LLM_PROVIDER` with an
optional `FALLBACK_LLM_PROVIDER`. A deterministic `MockLLMProvider`
(`src/llm/mock_provider.py`) is the default and what backs Demo Mode — it
produces realistic but fully input-dependent output (skills extracted from
actual keyword matches, tailored text built from actual job requirements
and actual candidate skills, Truth Guard verdicts computed by mirroring the
same deterministic evidence rules the real hybrid pipeline uses) so the
demo is a faithful stand-in for the live path, not a scripted fake.

## Datasets

- `data/sample_candidate/demo_resume.txt` — one seeded synthetic candidate
  resume.
- `data/sample_jobs.json` — 14 synthetic job postings, deliberately
  including a duplicate, a sparse/low-quality listing, and a spread of
  strong and weak matches across role families and work modes.
- `src/services/demo_application_loader.py` — a synthetic history of past
  applications and outcomes (~20 records) used to give the Learning Agent
  and OutcomeAnalytics enough sample size to demonstrate real pattern
  synthesis.

## Synthetic data disclosure

All of the above is fabricated for demonstration purposes. No real job
postings, real company data, or real candidate information is used
anywhere in this repository or its demo path. Every UI surface that shows
demo-influenced figures is explicitly labeled "DEMO MODE — Synthetic Data"
(see `app.py`), and every demo application record carries an `is_demo_data`
flag so it can never be silently conflated with real session activity.

## Prompts / vibe-coding process

Each subsystem was built and reviewed in an explicit-instruction, phase-gated
process: architecture and scoring were frozen before any agent code was
written (Phase 1); LLM provider abstraction, resume parsing, and the first
two agents were added and tested to 143 tests (Phase 2); LangGraph
orchestration and the first human-in-the-loop interrupt were added and
tested to 157 tests (Phase 3); resume tailoring, evidence retrieval, and
the three-layer Truth Guard hybrid were added and tested to 226 tests
(Phase 4); application tracking, outcome analytics, and the Learning Agent
were added and tested to 278 tests (Phase 5); the Streamlit product,
actionability hardening, the evaluation harness, and this documentation
were added in Phase 6. Each phase was explicitly approved before the next
began, and later phases were instructed not to redo or casually refactor
earlier, already-tested work — only to touch it when a new phase's own
integration testing exposed a real defect.

## Iterations

The single largest architectural correction happened in Phase 4: an
earlier, fully-deterministic Truth Guard design was too rigid for wording
that genuinely needs semantic judgment (is "used" close enough to
"designed"? does a bare skills-list entry imply hands-on ownership?). The
resolution — documented in [TRUTH_GUARD.md](TRUTH_GUARD.md) and
[DECISIONS.md](DECISIONS.md) — was a three-layer hybrid where an LLM only
ever handles the genuinely ambiguous remainder, and a deterministic
post-validation layer can make its output more conservative but never less.

A smaller Phase 6 correction: the Streamlit product's Application Tracker
initially raised `sqlite3.ProgrammingError: SQLite objects created in a
thread can only be used in that same thread` under real Streamlit rerun
behavior, because `src/services/database.py::get_connection` did not pass
`check_same_thread=False` the way the workflow checkpointer already did.
Found via headless `streamlit.testing.v1.AppTest` runtime smoke-testing
(not a static import check), and fixed by matching the checkpointer's
existing pattern.

## Architecture decisions

See [DECISIONS.md](DECISIONS.md) for the full record — in particular why
scoring is deterministic, why agents are reserved for judgment-heavy tasks,
why Pinecone is retrieval-only, why historical signal is capped, and why
Truth Guard is architecturally separate from Resume Tailor.

## Error handling

Errors are categorized (`ErrorCategory` in `src/models/enums.py`) and
handled per node rather than with a single blanket try/except: a resume
parse failure, a provider outage, a malformed LLM response, and a Truth
Guard LLM outage each degrade differently, but never by silently producing
an unsafe or fabricated result. See WORKFLOW.md's error taxonomy and
`evals/failure_recovery.py` for the evaluated failure scenarios and their
classification (RECOVERED / DEGRADED / SAFE_FAILURE / UNSAFE_FAILURE).

## Human-in-the-loop

Five real interrupts — job selection, clarification, resume approval,
application action, and outcome recording — each a genuine LangGraph pause
with SQLite checkpointing. No downstream action (resume version creation,
application creation, outcome recording) happens without the corresponding
human action reaching the graph. Verified both by the existing pytest suite
and by `evals/human_approval.py`.

## Evaluation

`python -m evals.run_evals` runs twelve categories against real backend
code (not a re-description of the unit tests): resume extraction,
deduplication, job quality, opportunity ranking, match grounding, Truth
Guard (≥20 adversarial cases), human approval enforcement, failure
recovery, outcome analytics, learning insight grounding, end-to-end
task completion, and (optional) live job discovery classification/safe-
failure. Results are written to `evals/results/latest.json`.

Current results (94 total cases across 12 categories, 100% overall pass
rate, safety gate PASSED, exit code 0):

| Category | Result |
|---|---|
| Resume Extraction | 7/7 |
| Deduplication | 6/6 |
| Job Quality | 7/7 |
| Opportunity Ranking | 5/5 |
| Match Grounding | 5/5 |
| **Truth Guard** | **23/23** — `FALSE VERIFIED: 0`, `FALSE UNSUPPORTED: 0` |
| **Human Approval Enforcement** | **7/7** — `enforcement_violations: 0` |
| **Failure Recovery** | **6/6** — `RECOVERED: 3, DEGRADED: 0, SAFE_FAILURE: 3, UNSAFE_FAILURE: 0` |
| Outcome Analytics | 7/7 |
| Learning Insight Grounding | 8/8 |
| End-to-End | 7/7 — task_completion, human_selection_enforced, unsupported_claim_blocked, human_resume_approval_enforced, application_created, outcome_recorded, and strategy_insight_created all confirmed true in one full pipeline run |
| Live Job Discovery *(optional, You.com)* | 6/6 — deterministic classification accuracy + a simulated-outage safe-failure case, no real network calls |

Truth Guard's 23 adversarial cases (exceeding the ≥20 requirement) cover
unsupported technology, unsupported certification, inflated title, inflated
ownership, unsupported metric, unsupported savings, unsupported team size,
skills-only evidence, project-only evidence, partial/hedged evidence,
human-confirmed evidence, and mixed claims. The critical safety number —
**FALSE VERIFIED, cases where an unsupported claim was wrongly approved —
is 0.**

## Learnings

Deterministic post-validation is what actually makes an "agentic but safe"
claim credible — an LLM's own restraint is not a control, and every agent
boundary in this system (Truth Guard's fail-closed layer, the Learning
Agent's grounding/actionability gate, the Match Analyst's frozen score)
exists because a plausible-sounding but ungrounded output was a real,
anticipated failure mode, not a hypothetical one. Actionability hardening
in Phase 6 in particular clarified that "confidence in a number" and
"whether that number justifies a strategy change" are genuinely two
different axes — a well-sampled tiny difference and a poorly-sampled huge
difference are both real patterns a naive system would misreport in
opposite directions.

Additional learnings, consolidated at certification freeze:

- **Not every step should be an agent.** The system is more auditable,
  faster, and cheaper because most of it (scoring, dedup, quality flags,
  analytics, actionability) is plain Python with one correct answer, not
  because an LLM was avoided for its own sake.
- **Deterministic numerical scoring is more auditable than an LLM score.**
  A fixed, versioned formula lets a score be regression-tested and
  reproduced; an LLM producing a slightly different number each run cannot
  be audited the same way (`docs/DECISIONS.md` #1).
- **LLMs are better at interpretation than arithmetic authority.** Every
  agent in this system explains, proposes, or verifies against evidence —
  none of them compute a number that a human or another system component
  treats as ground truth.
- **Persistent workflow state and long-term memory solve different
  problems.** LangGraph's SQLite checkpointing exists to resume an
  in-flight, paused run; mem0 exists to recall candidate-scoped strategy
  text *across* separate runs. Conflating the two (e.g. trying to make
  mem0 double as workflow state) would have broken both jobs.
- **Vector similarity retrieves evidence; it doesn't prove truth.**
  Pinecone/local-fallback retrieval only locates candidate text that might
  be relevant — Truth Guard's actual verdict always traces back to a
  concrete `Evidence` record, never to a bare similarity score
  (`docs/TRUTH_GUARD.md`).
- **Human approval should gate consequential actions, not just surface
  information.** All five HireLoop interrupts are real pauses that block
  the next state-changing node, not confirmations layered on top of
  something that already happened.
- **Tool failure must be designed for, not an afterthought.** Provider
  fallback, bounded retries, and fail-closed verification all exist
  because a plausible-but-wrong output under failure was a real
  anticipated risk, not a hypothetical edge case — `evals/failure_recovery.py`
  exists specifically to keep `UNSAFE_FAILURE` at 0 as a regression gate.
- **Sparse job descriptions can create artificially high apparent match
  rates.** A posting with one stated requirement that the candidate meets
  scores well mathematically — that's correct, not a bug — but it's
  misleading without a completeness signal, which is exactly what
  `src/services/job_evidence_sufficiency.py` adds without touching the
  scoring formula itself.
- **Sample size and effect size are different axes.** A confident-sounding
  percentage difference can come from too few data points; a real,
  actionable difference can look unremarkable if it's small. Conflating
  the two is precisely what `src/services/actionability.py` was built to
  prevent.
- **A self-improving system needs outcome feedback, not just memory.**
  Storing preferences alone (mem0) never would have let the Learning Agent
  say anything grounded — it's the append-only `ApplicationEvent` history
  and deterministic `OutcomeAnalytics` that make a real (hedged, sample-
  size-aware) insight possible.
- **Live APIs must be tested against real contracts, not assumptions.**
  The You.com integration's endpoint and response-envelope shape
  (`results.web`/`results.news`, not an assumed alternate shape) were only
  confirmed correct by making one real, live call this session — not by
  reading documentation and assuming it matched.
- **Integration testing exposed real defects that the unit-test suite
  missed.** Two separate real bugs — the Phase 6 SQLite
  `check_same_thread` threading defect (found only under a headless
  `streamlit.testing.v1.AppTest` runtime run) and the You.com response-shape
  correction (found only via a live network call) — were invisible to the
  (at the time) 278–330-test unit/integration suite, because that suite
  was correctly testing logic built on an untested runtime/vendor
  assumption. Both are recorded in detail in `docs/BUILD_PROCESS.md`.

## Limitations

- HireLoop only evaluates the job batch it's given (seeded JSON in this
  MVP) — it does not discover new postings.
- Truth Guard can only check a claim against evidence HireLoop has
  recorded; it cannot verify a candidate's life, and a confident-sounding
  `VERIFIED` still ultimately traces back to what the candidate themselves
  supplied.
- Strategy insights require enough recorded outcome history to be
  actionable, and are explicitly withheld (`NO_CLEAR_SIGNAL`) rather than
  guessed when the sample is too thin or the effect too small.
- Single-candidate-per-session in this MVP — no multi-user authentication.
- No automatic applications — every application status change is a
  recorded human action, never a submission HireLoop performs itself.
- No guarantee a discovered or seeded job is still active at the moment a
  candidate applies — neither the demo batch nor a live You.com result is
  re-verified against the employer's site.
- Search-provider result counts may differ from requested counts (observed
  directly this session — see the You.com disclosure section above);
  HireLoop's own caps and classifier bound what reaches scoring regardless.
- No production authentication and no production-scale infrastructure —
  this is a certification MVP (SQLite, in-process defaults, single
  session), not a deployed service.
- No guarantee the Opportunity Score predicts actual hiring decisions — it
  is a transparent, reproducible fit heuristic against stated
  requirements, not a prediction of any real employer's outcome. See
  `docs/EVALUATION.md` for the full evaluation-scoped limitations list.

## Roadmap (explicitly deferred, not part of this project)

Automatic application submission, live job-board scraping (LinkedIn/Indeed),
recruiter outreach, complex n8n automation, ElevenLabs interview practice,
and multi-user authentication/infrastructure. Each was excluded
deliberately — see [DECISIONS.md](DECISIONS.md) §6 for the reasoning behind
the auto-apply exclusion specifically, which is the one most directly tied
to the project's human-in-the-loop requirement.
