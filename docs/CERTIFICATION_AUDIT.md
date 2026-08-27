# HireLoop AI — Certification Requirements Audit

Status: **Freeze-phase audit, written against the codebase as it exists
today** (330 passing tests, 94/94 evaluation cases). Every `PASS` below
names the actual file/function/test it was checked against — this document
does not accept a claim from another doc as proof; it re-verifies against
code.

Legend: **PASS** — implemented and directly verifiable in code/tests.
**NEEDS_POLISH** — implemented but with a caveat worth knowing about.
**MISSING** — not implemented.

## 1. Requirement-by-requirement audit

### Agentic multi-step workflow (not one-shot, not merely RAG)

**PASS.** `src/graph/workflow.py::build_workflow()` compiles a LangGraph
`StateGraph` with 27+ nodes spanning resume parsing through application
tracking (see `docs/WORKFLOW.md` §1–2 for the full node list); a second,
separate graph (`build_outcome_update_workflow()`) handles outcome
recording. This is not RAG-with-a-wrapper: only two of the ~30 nodes
(`prepare_candidate_evidence`, `retrieve_job_evidence`) involve retrieval,
and retrieval there feeds Truth Guard's verification, not a single
generate-an-answer step. Verified by `tests/test_workflow.py` and
`tests/test_workflow_phase4.py`/`test_workflow_phase5.py`, which drive the
real compiled graph end-to-end through interrupts, not a mock.

### Tool calling

**PASS.** Agents call structured LLM tools via `src/llm/client.py::LLMClient`
(schema-constrained JSON output, e.g. `TailorLLMOutput`, `TruthGuardLLMOutput`
in `src/llm/schemas.py`), and one agentic-adjacent external tool exists:
`src/services/you_search.py::search_jobs()` (You.com Web Search API,
read-only job discovery). Verified by `tests/test_you_search.py` (mocked
HTTP) and this session's live call (§10, `docs/PROJECT_OVERVIEW.md`).

### Stateful orchestration

**PASS.** `src/graph/state.py::HireLoopState` (a `TypedDict`) carries
~40 fields threaded through every node; `decision_trace` and `errors` use
LangGraph's additive reducers. Verified by `tests/test_workflow.py` and
the node table in `docs/ARCHITECTURE.md` §3–4.

### Persistent state

**PASS.** `src/graph/checkpointing.py::get_sqlite_checkpointer()` wraps
LangGraph's `SqliteSaver` over SQLite (file-backed by default at
`data/workflow_checkpoints.db`, in-memory in the Streamlit app — see §18
below). A run resumes from exactly where it paused after a process
restart, verified by `tests/test_workflow.py::test_resume_does_not_repeat_completed_steps`
and `test_resume_from_clarification_does_not_repeat_tailor_resume`.

### Persistent memory

**PASS.** Two distinct persistence layers: `src/services/database.py`
(business SQLite — candidates, applications, resume versions, strategy
insights) and `src/services/memory_service.py::MemoryService` (mem0,
candidate-scoped preference/strategy text only, with a documented
`MockMemoryProvider` fallback). Verified by `tests/test_memory_service.py`
(including `test_candidate_isolation`) and `docs/LEARNING_LOOP.md` §7.

### Control flow / conditional routing

**PASS.** `src/graph/routing.py` — 12 pure routing functions (e.g.
`route_after_truth_guard`, `route_after_job_quality`), each a small
function of `HireLoopState` with no side effects, documented with their
exact branch conditions in `docs/WORKFLOW.md` §3. Verified by
`tests/test_workflow.py` and `tests/test_workflow_phase4.py`.

### Tool failure handling / retry / fallback

**PASS.** `src/llm/client.py::LLMClient` implements a bounded retry loop
(`while attempts < self.retry_policy.max_retries + 1`) and provider
fallback is exercised directly by `python -m evals.run_evals`, which
printed `llm_fallback_triggered primary=failing-primary fallback=mock
reason=PROVIDER_UNAVAILABLE` in this session's run (see
`evals/failure_recovery.py`). You.com's client
(`src/services/you_search.py`) separately classifies errors
(auth/credit/rate-limit/unavailable/timeout/malformed/empty,
`src/services/you_search_errors.py::RETRYABLE_ERROR_TYPES`) and retries
only transient failures with bounded backoff. Verified by
`tests/test_you_search.py` and `evals/failure_recovery.py`
(6/6, `UNSAFE_FAILURE: 0` in this session's run).

### Human-in-the-loop / human approval before consequential actions

**PASS.** Five real `interrupt()`/`Command(resume=...)` pauses:
`human_select_job`, `human_clarification`, `human_resume_approval`
(`src/graph/nodes/resume_approval.py` — only `VERIFIED` modifications are
ever offered, enforced structurally in `_build_payload`, not by
convention), `human_application_action`, `human_record_outcome`. Verified
by `tests/test_workflow_phase4.py::test_human_edit_is_re_verified_not_auto_approved`
and `evals/human_approval.py` (7/7, `enforcement_violations: 0` in this
session's run).

### Clear autonomous-vs-human boundary

**PASS.** Documented per-agent in `docs/ARCHITECTURE.md` §7 and enforced
in code, not just prose: `src/agents/learning_agent.py` has no import of
`src/config/scoring.py` or `application_tracker.py`'s write methods,
verified directly by
`tests/test_learning_agent.py::test_learning_agent_has_no_access_to_scoring_weights`
and `..._application_tracker`. `src/models/scoring.py::OpportunityScore`
is a frozen Pydantic model — the Match Analyst has no attribute path to
mutate it.

### End-to-end task completion / measurable success

**PASS.** `evals/end_to_end.py` drives one full pipeline run (resume →
selection → tailoring → Truth Guard block → approval → application →
outcome → insight) and asserts 7 boolean flags — all `true` in this
session's run: `task_completion`, `human_selection_enforced`,
`unsupported_claim_blocked`, `human_resume_approval_enforced`,
`application_created`, `outcome_recorded`, `strategy_insight_created`.

### Working interface / demo capability

**PASS.** `app.py` (Streamlit, 7 pages) is a thin renderer over the real
graph state — every mutating UI action resumes the same compiled graph via
`Command(resume=...)`, verified in Phase 6 by headless
`streamlit.testing.v1.AppTest` smoke runs (per `docs/FINAL_REPORT.md`) and
independently re-confirmed this session (§22 below, Candidate → Run search
→ Opportunities, zero exceptions).

### Project documentation

**PASS.** `docs/ARCHITECTURE.md`, `docs/WORKFLOW.md`, `docs/TRUTH_GUARD.md`,
`docs/LEARNING_LOOP.md`, `docs/DECISIONS.md`, `docs/PROJECT_OVERVIEW.md`,
`docs/SECURITY_PRIVACY.md`, `docs/DEMO_SCRIPT.md`, `docs/FINAL_REPORT.md`
all exist and were verified for accuracy against current code during this
freeze audit (no material inaccuracies found — see §8 architecture-diagram
check in the main freeze report).

### Datasets documented

**PASS.** See "Dataset Audit" below.

### Prompts / vibe-coding documented

**PASS.** `docs/PROJECT_OVERVIEW.md` "Prompts / vibe-coding process"
section; expanded phase-by-phase in `docs/BUILD_PROCESS.md` (new, this
freeze).

### Iterations documented

**PASS.** `docs/PROJECT_OVERVIEW.md` "Iterations" section (Truth Guard
hybrid correction, SQLite threading fix); `docs/BUILD_PROCESS.md` adds the
`rejected_modifications` claim-text gap and the You.com endpoint/response-
shape correction.

### Learnings documented

**PASS.** `docs/PROJECT_OVERVIEW.md` "Learnings" section, extended this
freeze with additional entries (see that file).

### Error handling documented

**PASS.** `docs/WORKFLOW.md` §10–11 (full error taxonomy and
per-node failure table); `src/models/enums.py::ErrorCategory`.

### GitHub readiness

**NEEDS_POLISH.** No blocking code issue, but **this working tree is not
currently a git repository** — `git status` fails with `fatal: not a git
repository (or any of the parent directories): .git`, and no `.git`
directory exists anywhere in the tree. `git init`, a first commit, and a
push to a remote are prerequisites the human still has to do — see
`docs/SUBMISSION_CHECKLIST.md`. Everything else needed for a clean first
commit (`.gitignore` covering secrets/caches, `.env.example` present,
`.env` itself excluded) is now in place as of this freeze.

### <=5 minute demo readiness

**PASS.** `docs/DEMO_SCRIPT.md`'s 12 timed beats sum to 5:00 exactly and
were re-read against current `app.py` page structure this session — no
drift found (see §17 of the main freeze report).

## 2. Tool Inventory

| Technology | Purpose | Actually used? | Certification-demo role | Fallback |
|---|---|---|---|---|
| **LangGraph** | Orchestration, checkpointing, `interrupt()`-based HITL | Yes — `src/graph/` | Core: every node/edge/interrupt in the demo runs through it | None needed — it's the orchestration substrate itself |
| **LangChain** | `langchain_core.runnables.RunnableConfig` typing for node signatures; `langgraph`'s own dependency | Yes, minimally — type only, no LangChain agents/chains used | Supporting | N/A |
| **Nebius** | Live LLM inference provider | Implemented (`src/llm/http_provider.py`, `nebius_provider.py`) but **not used in the demo** — `DEFAULT_LLM_PROVIDER=mock` in `.env` | Not exercised by `DEMO_MODE` or `evals/` | Falls back to `mock` if unset/unreachable |
| **Fireworks** | Live LLM inference provider (fallback option) | Implemented, same status as Nebius | Not exercised by `DEMO_MODE` or `evals/` | Falls back to `mock` |
| **You.com** | Live job-discovery Web Search API | Yes — `src/services/you_search.py`, one real paid call made this session (see `docs/PROJECT_OVERVIEW.md` §You.com disclosure) | Optional bonus only; `YOU_SEARCH_ENABLED=false` by default, never in `DEMO_MODE` or `evals/` | Degrades to a clear UI message; user falls back to DEMO JOBS |
| **Pinecone** | Semantic evidence retrieval (never a verdict) | Implemented (`src/services/vector_service.py`) but not configured in this environment (`PINECONE_ENVIRONMENT` empty) | Not exercised by `DEMO_MODE`; local fallback used instead | `src/services/local_evidence_search.py` — deterministic token overlap, no network |
| **mem0** | Candidate preference / strategy-insight memory | Implemented (`src/services/memory_service.py`); `DEMO_MODE` uses `MockMemoryProvider`, a real mem0 API key is present in `.env` but `DEMO_MODE` never calls the network client | Demo uses the mock in-process provider | Degrades to "persisted locally only" (business SQLite remains authoritative) |
| **SQLite** | Workflow checkpoints + business system of record | Yes — two separate DBs by design (`docs/WORKFLOW.md` §9) | Core: in-memory per Streamlit session by default | N/A — this *is* the storage layer |
| **Streamlit** | Product UI | Yes — `app.py`, 7 pages | Core: the entire demo interface | N/A |
| **n8n** | Workflow automation | **ROADMAP / NOT USED IN MVP** — confirmed absent: `grep -ri "n8n" src/ app.py` returns no matches | Not part of the demo | N/A |
| **ElevenLabs** | Voice/interview practice | **ROADMAP / NOT USED IN MVP** — confirmed absent: `grep -ri "elevenlabs" src/ app.py` returns no matches | Not part of the demo | N/A |
| **Claude Code** | Build tool | Yes — this project was built through iterative Claude Code sessions (phase-gated: architecture frozen before code, explicit approval between phases, integration-testing-driven fixes such as the SQLite threading bug and the You.com endpoint correction — see `docs/BUILD_PROCESS.md`). This freeze audit itself was also produced via a Claude Code agent session. | N/A (build-time tool, not a runtime dependency) | N/A |
| **Codex** | — | **Not used.** No evidence in the repository (commit history, comments, config) of Codex involvement. Stated honestly as "not used" rather than guessed. | N/A | N/A |

## 3. Agent Inventory

For each agent: Input / Output / Tools-data used / Autonomous responsibility
/ What it cannot do / Human boundary. (Table form in `docs/ARCHITECTURE.md`
§7 covers responsibility/boundary only — this adds the input/output/tool
specificity.)

### Profile Agent (`src/agents/profile_agent.py`)

- **Input:** raw resume text (`resume_parse_result.extracted_text`) plus
  optional `ProfilePreferences` (target roles/locations/work mode supplied
  separately from the resume).
- **Output:** `CandidateProfile` (skills, work experience, projects,
  education, certifications, each carrying `Evidence.source_text`).
- **Tools/data used:** one LLM call (`ExtractedProfileData` schema) is
  post-processed with `src/services/normalization.py::normalize_skill`,
  `src/services/experience_estimation.py::estimate_years_experience`
  (independently recomputes years from parsed dates rather than trusting
  the model), and `src/services/profile_validation.py`.
- **Autonomous responsibility:** deciding which resume facts become
  structured profile fields; dropping entries missing a required
  identifying field rather than inventing one.
- **Cannot do:** score or rank anything; invent an employer/title/date/
  degree/certification/skill not explicitly present in the resume text
  (system-prompt-enforced, `_GROUNDING_SYSTEM_PROMPT`).
- **Human boundary:** none directly — its output feeds
  `validate_candidate_profile` (deterministic), which can halt the workflow
  on fatal errors before anything downstream sees a bad profile.

### Match Analyst (`src/agents/match_analyst.py`)

- **Input:** `CandidateProfile`, `JobPosting`, and an already-computed,
  frozen `OpportunityScore` (built via `_build_context`, which whitelists
  exactly which fields enter the prompt).
- **Output:** `MatchAnalysis` (strengths, gaps, risks, explanation,
  confidence) via the `MatchAnalysisLLMOutput` schema — which has **no
  score/recommendation field at all**, so there's nothing for the model to
  override even adversarially.
- **Tools/data used:** `src/agents/grounding.py::build_grounded_vocabulary`/
  `filter_ungrounded_claims` post-filters LLM output against the actual
  candidate/job vocabulary; `src/services/job_evidence_sufficiency.py`
  deterministically appends a "limited job description evidence" risk note
  when completeness is LOW, independent of what the LLM says.
- **Autonomous responsibility:** producing the qualitative explanation of
  a fit that's already numerically decided.
- **Cannot do:** modify the frozen `OpportunityScore`; infer a salary not
  provided; assume an adjacent skill counts as evidence of a missing one.
- **Human boundary:** none directly — feeds the human-selection interrupt's
  displayed recommendation set, but the human is choosing among
  deterministically-ranked jobs, not trusting the Analyst's own ordering
  (`rank_opportunities` is the sole ranking authority).

### Resume Tailor (`src/agents/resume_tailor.py`)

- **Input:** `CandidateProfile`, the selected `JobPosting`,
  `RequirementEvidence` per job requirement (from
  `retrieve_job_evidence`).
- **Output:** `list[ResumeModification]` (proposed text changes, each with
  a `reason` and `supporting_evidence_ids` the Tailor itself believes
  apply — explicitly **not trusted** by Truth Guard).
- **Tools/data used:** one LLM call (`TailorLLMOutput` schema);
  `src/services/job_requirements.py::extract_job_requirements`.
- **Autonomous responsibility:** proposing plausible resume language —
  **by design it may overreach** (propose a claim it can't actually
  support); Truth Guard, not the Tailor, is the safety net.
- **Cannot do:** save, finalize, or create a `ResumeVersion` directly;
  its own `supporting_evidence_ids` claim is never accepted as proof.
- **Human boundary:** every proposal must pass Truth Guard, then the
  `human_resume_approval` interrupt, before it can ever reach a
  `ResumeVersion`.

### Truth Guard (`src/agents/truth_guard.py`)

- **Input:** each `ResumeModification`, the candidate's `CandidateProfile`
  and attached `Evidence` records (**never** the Tailor's own `reason` or
  `targeted_job_requirement` text).
- **Output:** `TruthGuardResult` per modification —
  `VERIFIED`/`PARTIALLY_SUPPORTED`/`UNSUPPORTED`/`NEEDS_HUMAN_CONFIRMATION`,
  claim-fragment-level, with `unsupported_fragments` and
  `suggested_safe_rewrite`.
- **Tools/data used:** deterministic pre-checks (numeric-claim matching,
  technology-presence checks, skill-evidence-strength checks) always run
  first; the LLM (`TruthGuardLLMOutput` schema) is invoked only for the
  genuinely ambiguous remainder; a deterministic post-validation layer
  fail-closes the LLM's output.
- **Autonomous responsibility:** the actual truthfulness verdict — this is
  the one agent whose output is treated as authoritative rather than
  advisory (subject to the human still being the one who approves).
- **Cannot do:** let the LLM upgrade a deterministic `UNSUPPORTED`, or
  upgrade skills-only evidence straight to `VERIFIED`
  (`src/agents/truth_guard.py` post-validation cap; tested by
  `tests/test_truth_guard.py::test_deterministic_unsupported_survives_adversarial_llm`).
- **Human boundary:** `NEEDS_HUMAN_CONFIRMATION` routes to the
  `human_clarification` interrupt; only `VERIFIED` reaches
  `human_resume_approval`.

### Learning Agent (`src/agents/learning_agent.py`)

- **Input:** already-computed `OutcomeAnalytics` (grouped by role family,
  resume version, work mode) — never raw application rows.
- **Output:** `LearningInsight` objects (observation + recommendation +
  actionability), one attempt per analytics dimension.
- **Tools/data used:** one LLM call (`LearningAgentLLMOutput` schema) per
  dimension; `src/services/learning_insight_validation.py` deterministically
  enforces referenced-group grounding, numeric grounding, no-causal-language,
  and confidence-appropriate hedging before anything is accepted.
- **Autonomous responsibility:** synthesizing a human-readable pattern
  from numbers that already exist — it never computes a rate itself.
- **Cannot do:** compute its own metrics, invent numbers, use causal
  language ("causes," "guarantees," "proves"), or reach any code path that
  touches `src/config/scoring.py` or `application_tracker.py`'s write
  methods (verified by
  `tests/test_learning_agent.py::test_learning_agent_has_no_access_to_scoring_weights`).
- **Human boundary:** output is always a `LearningInsight.recommendation`
  string a human reads on the Strategy page — never an autonomous change
  (`docs/LEARNING_LOOP.md` §6 strategy-change safety table).

## 4. Deterministic Service Inventory

All under `src/services/`. Each is deterministic — not agentic — because
each has a single mechanically-correct answer for a given input; see
`docs/DECISIONS.md` #2 for the general principle this project committed to
(agents are reserved for genuinely judgment-heavy interpretation, not
mechanical computation).

| Service | Why deterministic |
|---|---|
| `resume_parser.py` | Text extraction from a PDF/DOCX/TXT file is a mechanical operation — there's one correct extracted string, not a matter of interpretation. |
| `normalization.py` | Title/company/location/skill-name normalization is lookup/rule-based; an LLM would make the same job match differently on different runs. |
| `deduplication.py` | Duplicate detection is a similarity-threshold rule — needs to be reproducible so the same batch always dedupes the same way. |
| `job_quality.py` | Quality scoring/flagging (missing fields, thin descriptions) is a checklist, not a judgment call. |
| `job_evidence_sufficiency.py` | Requirement-completeness scoring (skill counts, whether experience is stated) is arithmetic over structured fields. |
| `opportunity_scoring.py` | The core scoring formula — see `docs/DECISIONS.md` #1: reproducibility is required for a measurable, auditable outcome; an LLM producing a different score per run would make rankings untestable. |
| `historical_signal.py` | A capped, versioned weighted signal (`docs/DECISIONS.md` #7) — deliberately not dynamically adjustable so the score stays predictable. |
| `outcome_analytics.py` | Response/interview/offer rate arithmetic over real event data must be byte-for-byte reproducible (`docs/LEARNING_LOOP.md` §4) — handing this to an LLM would let the same history "observe" a different rate on different days. |
| `application_tracker.py` | The sole write path to the business DB — a data-access layer, not an interpretation task. |
| `decision_trace.py` | Appends plain-language observable-action strings — a logging utility, not a reasoning step. |
| `evidence_retrieval.py` / `local_evidence_search.py` | *Retrieval*, not verdict — `docs/DECISIONS.md` #3: semantic similarity is a weak, gameable proxy for truth, so it only ever locates candidate evidence for Truth Guard/Tailor to actually judge. |
| `actionability.py` | Classifies effect size × sample confidence via fixed statistical bands (`src/config/analytics.py`) — an LLM's own restraint is not a control (`docs/PROJECT_OVERVIEW.md` Learnings). |

## 5. Dataset Audit

| Dataset | Source | Synthetic vs. real | Purpose |
|---|---|---|---|
| `data/sample_candidate/demo_resume.txt` | Authored for this project | Synthetic | Seeded demo candidate resume, used by `DEMO_MODE`'s "Use the seeded demo candidate" checkbox. |
| `data/sample_candidate/phase4_demo_resume.txt` | Authored for this project | Synthetic | A second seeded resume used by `scripts/run_phase4_demo.py`'s standalone terminal demo (deliberately missing Kubernetes evidence, to reliably reproduce the Truth Guard `UNSUPPORTED` case). |
| `data/sample_jobs.json` | Authored for this project | Synthetic | 14 job postings, including one deliberate duplicate and one deliberately sparse/low-quality listing, spanning strong/weak matches across role families and work modes. |
| `data/demo_application_history.json` (loaded via `src/services/demo_application_loader.py`) | Authored for this project | Synthetic | 23 historical application records (with an explicit `is_demo_data: true` flag on the file and on every resulting `Application`) — gives the Learning Agent and `OutcomeAnalytics` enough sample size to demonstrate real pattern synthesis (`docs/DECISIONS.md` #9). **Not real employment-performance evidence** — no real candidate ever produced these outcomes. |
| `evals/*.py` fixtures | Authored for this project, inline in each eval module | Synthetic | Deterministic input fixtures per evaluation category (resume text samples, job postings, application/event sequences) — designed to exercise specific, known-answer scenarios, not sampled from real usage. |
| `evals/truth_guard.py`'s adversarial cases | Authored for this project | Synthetic | 23 cases (exceeds the ≥20 requirement) covering unsupported technology, unsupported certification, inflated title, inflated ownership, unsupported metric, unsupported savings, unsupported team size, skills-only evidence, project-only evidence, partial/hedged evidence, human-confirmed evidence, and mixed claims. |

**Explicit disclosure:** every dataset above is fabricated for
demonstration/evaluation purposes. No real job postings, real company
data, or real candidate information is used anywhere in this repository's
default demo path. The one exception is the live You.com call made this
session, which returned real (but ephemeral, not stored/committed) public
web search results — see `docs/PROJECT_OVERVIEW.md`'s You.com disclosure
section for the full, factual account of that single call.
