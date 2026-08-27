# HireLoop AI — Build Process

Status: **Written at certification freeze**, from the phase record already
established in `docs/PROJECT_OVERVIEW.md`'s "Prompts / vibe-coding process"
section and corroborated by growing test counts across the codebase
(143 → 157 → 226 → 278 → 288 → 321 → 330). Built via iterative Claude Code
sessions in an explicit-instruction, phase-gated process: each phase was
approved before the next began, and later phases were instructed not to
casually refactor already-tested earlier work — only to touch it when a
new phase's own integration testing exposed a real defect.

## Phase 1 — Deterministic foundations

**Goal:** freeze architecture and the scoring formula before any agent
code exists, so later phases build on a fixed, testable numeric core.

**Prompt-style summary:** "Design the Opportunity Scoring Engine as a
versioned, weighted, deterministic formula (skill match, experience match,
role alignment, location/work-mode, preference alignment, historical
signal, job quality). No LLM anywhere in this layer. Make every weight
configuration-driven and every score reproducible byte-for-byte given the
same inputs and scoring version."

**Implemented:** `src/services/opportunity_scoring.py`,
`src/services/normalization.py`, `src/services/deduplication.py`,
`src/services/job_quality.py`, `src/services/historical_signal.py`,
`src/config/scoring.py` (versioned weights).

**What tests exposed:** the value of frozen Pydantic models — an early
design question was whether `OpportunityScore` needed runtime write
protection or just convention; making it a frozen model closed that
question structurally rather than by discipline.

**Design decision:** deterministic scoring is the one place in the system
that must never involve an LLM (`docs/DECISIONS.md` #1) — this is the
foundation every later agent's output is graded against, never the
reverse.

## Phase 2 — LLM providers + Profile/Match agents

**Goal:** add the first real agents, but only where genuine reasoning is
needed, on top of Phase 1's frozen scoring.

**Prompt-style summary:** "Build a provider-agnostic `LLMClient` (Nebius,
Fireworks, and a deterministic Mock provider) with bounded retry and
provider fallback. Build the Profile Agent to turn resume text into a
structured `CandidateProfile` — never inventing a fact not present in the
text — and the Match Analyst to explain a score qualitatively without ever
being able to change it."

**Implemented:** `src/llm/` (client, provider, http_provider, mock_provider,
nebius_provider, fireworks_provider, schemas), `src/agents/profile_agent.py`,
`src/agents/match_analyst.py`, `src/agents/grounding.py`.

**What tests exposed:** the need for `src/services/experience_estimation.py`
to independently recompute years-of-experience from parsed employment
dates rather than trusting the model's own estimate — an early test caught
the model inflating a rough hint into a precise-sounding but wrong number.

**Test count reached:** 143.

## Phase 3 — LangGraph orchestration + human job selection

**Goal:** turn the linear pipeline into a real, checkpointed state
machine with the first genuine human-in-the-loop pause.

**Prompt-style summary:** "Compile a LangGraph `StateGraph` over the
Phase 1–2 pieces. Add a human job-selection `interrupt()` that survives a
process restart via SQLite checkpointing. Verify directly against the
installed LangGraph version how repeated/invalid `interrupt()` resumes
actually behave — don't assume."

**Implemented:** `src/graph/workflow.py`, `src/graph/state.py`,
`src/graph/routing.py`, `src/graph/nodes/human.py`,
`src/graph/checkpointing.py`.

**What tests exposed:** the exact replay semantics of LangGraph's
`interrupt()` — an invalid selection needed to re-pause *within the same
node execution* rather than losing the original recommendation set, which
was verified directly (not assumed) via
`tests/test_workflow.py::test_invalid_job_selection_is_rejected_and_keeps_waiting`
before being relied on elsewhere.

**Test count reached:** 157.

## Phase 4 — Resume Tailor + Truth Guard + evidence retrieval

**Goal:** add resume tailoring with a truthfulness safety net that
doesn't just trust the tailoring agent's own restraint.

**Prompt-style summary:** "Build a Resume Tailor that may propose
overreaching claims — that's fine, because Truth Guard is a separate
agent with its own evidence access that independently verifies every
claim fragment. Design the correction loop to be bounded, never
indefinite, and to fail closed (never silently VERIFIED) on any LLM
failure."

**Implemented:** `src/agents/resume_tailor.py`, `src/agents/truth_guard.py`,
`src/services/evidence_retrieval.py`, `src/services/local_evidence_search.py`,
`src/services/vector_service.py`, `src/graph/nodes/tailoring.py`,
`src/graph/nodes/clarification.py`, `src/graph/nodes/resume_approval.py`.

**What tests exposed — the largest architectural correction in the
project:** an earlier, fully-deterministic Truth Guard design was too
rigid for wording that genuinely needs semantic judgment (is "used" close
enough to "designed"? does a bare skills-list entry imply hands-on
ownership?). The resolution was the three-layer hybrid documented in
`docs/TRUTH_GUARD.md`: deterministic pre-checks always run first, an LLM
handles only the genuinely ambiguous remainder, and deterministic
post-validation can only make the result *more* conservative, never less.
This is also where the `rejected_modifications`-missing-claim-text gap was
found: `tests/test_workflow_phase4.py` was verifying that the demo's
Kubernetes claim correctly ended up `UNSUPPORTED` and stripped, and in the
process exposed that `rejected_modifications` entries carried only a
`modification_id`, not the original claim text — making it impossible for
a UI to actually show *what* was rejected and why, without a second
lookup. Fixed in `src/graph/nodes/tailoring.py`, `resume_approval.py`, and
`clarification.py` to carry the claim text directly.

**Test count reached:** 226.

## Phase 5 — Application outcomes + mem0 + Learning Agent

**Goal:** close the loop — track what a human actually did, record
outcomes, and let a Learning Agent propose grounded, hedged strategy
insights without ever computing its own metrics.

**Prompt-style summary:** "Add application tracking as a durable business
SQLite record, separate from the LangGraph checkpoint DB. Add a *separate*
graph for outcome recording, invoked days later, not chained to the main
run. The Learning Agent may only interpret analytics that already exist —
give it no code path to scoring weights or application-tracker writes, and
enforce that with a test, not a comment."

**Implemented:** `src/services/application_tracker.py`,
`src/services/database.py`, `src/services/outcome_analytics.py`,
`src/services/memory_service.py`, `src/agents/learning_agent.py`,
`src/services/learning_insight_validation.py`,
`src/graph/nodes/application.py`, `src/graph/nodes/outcome.py`,
`data/demo_application_history.json` (seeded synthetic history,
`docs/DECISIONS.md` #9).

**What tests exposed:** the value of application-level (not event-level)
counting in `outcome_analytics.py` — an application that progressed
APPLIED → RECRUITER_RESPONSE → INTERVIEW → OFFER needed to count as
exactly one interview and one offer, not three independent "successes";
getting this wrong would have silently inflated every rate shown to the
Learning Agent and the human.

**Test count reached:** 278.

## Phase 6 — Streamlit product + evaluation harness

**Goal:** ship the actual product interface and build a real evaluation
harness that exercises backend code, not a re-description of the unit
tests.

**Prompt-style summary:** "Build `app.py` as a thin renderer — no
duplicated business logic, every mutating action resumes the real
compiled graph via `Command(resume=...)`. Smoke-test it headlessly with
`streamlit.testing.v1.AppTest`, not just a manual click-through. Build a
12-category `evals/` harness with a safety gate that fails the whole run
if any critical safety counter (false_verified, enforcement_violations,
unsafe_failure) is nonzero."

**Implemented:** `app.py` (full rewrite from a scaffold stub),
`src/services/actionability.py`, `evals/` (harness + 12 category modules),
`docs/PROJECT_OVERVIEW.md`, `docs/SECURITY_PRIVACY.md`,
`docs/DEMO_SCRIPT.md`, `docs/FINAL_REPORT.md`.

**What tests exposed — found via runtime testing, not the unit suite:**
the Application Tracker raised
`sqlite3.ProgrammingError: SQLite objects created in a thread can only be
used in that same thread` under real Streamlit rerun behavior, because
`src/services/database.py::get_connection` did not pass
`check_same_thread=False` the way the workflow checkpointer already did.
This was found by headless `streamlit.testing.v1.AppTest` runtime
smoke-testing — a static import check or the existing 278-test unit suite
would not have caught it, because neither exercised the actual
multi-thread behavior of a live Streamlit rerun. Fixed by matching the
checkpointer's existing `check_same_thread=False` pattern.

**Design change:** `actionability.py` was added to separate *sample
confidence* from *effect size* — a strategy insight can be sample-adequate
(enough data points) but still correctly flagged `NO_CLEAR_SIGNAL` when
the observed difference between groups is too small to act on. Before
this, the system risked treating "33% vs. 29% on a small sample" the same
as a genuinely large, well-sampled difference.

**Test count reached:** 288 (278 + 10 new `test_actionability.py` tests).

## Final integration — You.com live discovery

**Goal:** add optional, opt-in live job discovery without letting an
external, rate-limited, non-deterministic API sit on the path the
certification demo or `evals/run_evals.py` exercises (`docs/DECISIONS.md`
#11).

**Prompt-style summary:** "Add a You.com Web Search API client that is the
only module in HireLoop allowed to talk to You.com. Verify the real
endpoint and response contract directly with a live call — don't assume
the shape from documentation alone. Wire it into the existing
`ingest_jobs_node` via one new optional `job_source_override` hook,
touching no other graph file. `DEMO_MODE` must never call it, enforced by
a test that patches `you_search.search_jobs` to raise if invoked during
the demo workflow."

**Implemented:** `src/services/you_search.py`,
`src/services/you_search_errors.py`,
`src/services/you_search_query_builder.py`,
`src/services/job_candidate_classification.py`,
`src/services/web_job_conversion.py`, `src/services/live_job_discovery.py`,
`src/models/web_job_search.py`, the `job_source_override` hook in
`src/graph/nodes/jobs.py`.

**What a live test exposed — the endpoint/response-shape correction:** an
initial assumption about the You.com response envelope was corrected
against the real, live API this session: the actual contract is
`POST https://ydc-index.io/v1/search`, `X-API-Key` auth, and a response
shaped `{"results": {"web": [...], "news": [...]}, "metadata": {...}}` —
confirmed via one direct, real API call (not by modifying `app.py`, and
not by trusting documentation alone). `src/services/you_search.py`'s
`_extract_web_hits()` reads only `results.web`; `results.news` is
deliberately never treated as job listings. The same live call also
surfaced that the vendor does not necessarily honor a requested result
count — `count=5`/`num_web_results=5` was requested and 10 web results
were returned — which is why HireLoop's own `you_search_max_results` cap
and the deterministic `LIKELY_JOB` classifier independently bound what
reaches scoring, rather than trusting the vendor's count parameter.

**Test count reached:** 330 (integration-test additions for
`you_search.py`/classification/conversion on top of the 288 Phase 6
baseline; exact prior interim counts of 321 not independently re-derived
here, but 330 is the confirmed current total).

## Cross-cutting theme: integration testing found what unit testing missed

Two of the project's real defects — the Phase 6 SQLite threading bug and
the You.com endpoint/response-shape assumption — were found by *runtime*
or *live* testing (headless `AppTest` execution, a real API call),
not by the (at the time) 278–330-test unit/integration suite, which
exercised correct logic against assumptions that were themselves untested
against the real runtime environment or the real vendor contract. This is
recorded as an explicit learning in `docs/PROJECT_OVERVIEW.md`'s Learnings
section.
