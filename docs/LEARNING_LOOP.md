# The HireLoop Learning Loop

Status: **Implemented (Phase 5)**

This document covers application tracking, outcome recording, deterministic
analytics, the Learning Agent, and mem0 — the pieces that close the loop:

```
Job Discovery → Opportunity Scoring → Human Selection → Resume Tailoring
→ Truth Guard → Human Approval → Application Tracking → Outcome Recording
→ Outcome Analytics → Learning Agent → Strategy Memory
→ next Job Discovery / Ranking
```

**Observed historical performance guides recommendations but does not
prove causation or guarantee future outcomes.**

## 1. Business DB vs. workflow checkpoint DB

Two SQLite databases, two different jobs, never merged:

| | `data/workflow_checkpoints.db` | `data/hireloop.db` |
|---|---|---|
| Owned by | LangGraph's `SqliteSaver` | `src/services/database.py` |
| Holds | Interrupt/resume points, per-thread node execution history | Candidates, jobs, opportunity scores, applications, application events, resume versions, strategy insights, decision trace events, scoring model versions |
| Keyed by | `thread_id` | Business entity IDs (`application_id`, `candidate_id`, ...) |
| Losing it costs | In-flight workflow runs only | Durable business history |
| Schema management | LangGraph-internal | `init_schema()` + a `schema_meta` version row — no migration framework; justified for an MVP schema that has only ever grown |

No agent or graph node executes SQL directly. Every access goes through
`src/services/application_tracker.py` (`ApplicationTrackerService`), which
is the only caller of `src/services/database.py`.

## 2. The Application event model

`Application.current_status` (`src/models/application.py`) is a
cached/derived summary — convenient to query, but never the record of
truth. `ApplicationEvent` (`src/models/application_event.py`) is
append-only: `APPLICATION_CREATED`, `APPLIED`, `RECRUITER_RESPONSE`,
`INTERVIEW`, `FINAL_ROUND`, `OFFER`, `REJECTED`, `WITHDRAWN`. Recording a
new outcome always *appends* a new event and updates the cached
`current_status`; it never rewrites or deletes a prior event. This is what
makes real analytics possible — the full arc of an application (APPLIED →
RECRUITER_RESPONSE → INTERVIEW → FINAL_ROUND → OFFER, say, over six weeks)
is fully reconstructable, not collapsed into one final label.

## 3. Outcome semantics (reused, not re-derived)

`src/config/outcomes.py` (introduced pre-Phase-4, extended here with
`CLOSED`) remains the single source of truth:

- **Positive:** `RECRUITER_RESPONSE`, `INTERVIEW`, `FINAL_ROUND`, `OFFER`
- **Negative:** `REJECTED`
- **Unresolved (excluded from response-rate math):** `SAVED`,
  `READY_FOR_REVIEW`, `APPROVED`, `APPLIED`, `WITHDRAWN`, `CLOSED`

## 4. Deterministic analytics — counted at the application level

`src/services/outcome_analytics.py` computes every rate from
`(Application, list[ApplicationEvent])` pairs. **No LLM is involved in
this module at all.** The critical rule: an application that progressed
APPLIED → RECRUITER_RESPONSE → INTERVIEW → OFFER is **one** application,
contributing exactly one positive response, one interview, and one offer
— never three independent "successes." This is implemented by checking
whether each *milestone was ever reached* across the full event history
(so an application that interviewed and was later rejected still counts
as one interview), while `rejections` and the final rate denominators
still key off the application's *current* (final) status.

`WITHDRAWN` applications are excluded from rate denominators entirely by
default (`_is_excluded` in `outcome_analytics.py`) — a withdrawal isn't an
employer response signal.

### Why the LLM doesn't calculate metrics

Every number a human or the Learning Agent ever sees — response rate,
interview rate, offer rate, average score — is produced by plain Python
arithmetic over real event data, reproducible byte-for-byte on every run.
Handing that arithmetic to an LLM would mean the same history could
"observe" a different response rate on different days for no reason. The
LLM's only job is *interpreting* numbers that already exist (§6).

## 5. Sample-size handling

`src/config/analytics.py` bands every group by resolved sample size:

| n | Confidence |
|---|---|
| ≤ 2 | `INSUFFICIENT` |
| 3–5 | `LOW` |
| 6–10 | `MEDIUM` |
| > 10 | `HIGH` |

A different defensible scheme could replace this without touching any
caller — it's one function, `confidence_for_sample_size()`. Confidence
travels with every `GroupAnalytics` and every `LearningInsight`; nothing
downstream re-derives it from a different, possibly inconsistent, notion
of "enough data."

## 6. Learning Agent boundaries

`src/agents/learning_agent.py` interprets `OutcomeAnalytics` — it never
computes it. For each dimension (role family, resume version, work mode),
it asks the LLM (Mock or real) for a comparative observation, then
`src/services/learning_insight_validation.py` deterministically enforces:

- **Referenced-group grounding** — an insight about a group not present in
  the analytics is rejected outright.
- **Numeric grounding** — every percentage cited in the text must match a
  number the analytics actually computed (for the referenced group or any
  other group in the same analytics); an invented number is rejected.
- **No causal language** — "causes," "guarantees," "proves," "will result
  in," etc. are rejected outright rather than rewritten, matching Truth
  Guard's "reject, don't guess" posture (docs/TRUTH_GUARD.md).
- **Confidence-appropriate hedging** — every accepted insight's
  observation is deterministically prefixed with wording matching its
  sample-size confidence ("Based on a very small sample...", "Observed
  pattern (moderate confidence): ...") — never left to the LLM's own
  restraint.
- **Sample size and confidence always come from the analytics group**,
  never from the LLM's own stated numbers.

**The Learning Agent has no code path to modify scoring weights, candidate
facts, or application history.** It only returns `LearningInsight`
objects. Nothing in `src/agents/learning_agent.py` imports
`src/config/scoring.py` or `src/services/application_tracker.py`'s write
methods — this is verified directly by
`tests/test_learning_agent.py::test_learning_agent_has_no_access_to_scoring_weights`
and `..._application_tracker`.

### Strategy-change safety (allowed vs. not allowed automatically)

| Allowed automatically | Not allowed automatically |
|---|---|
| Display a strategy recommendation | Change scoring weights |
| Save an insight to SQLite | Remove a target role permanently |
| Sync a memory to mem0 | Submit a job application |
| | Modify a tailored resume |
| | Contact a recruiter |

A recommendation like "reduce Software Engineer priority" is exactly
that — a `LearningInsight.recommendation` string a human reads. Nothing in
the system code path can turn it into a permanent, autonomous change.

## 7. mem0's role

`src/services/memory_service.py`'s `MemoryService` is a thin, namespaced
abstraction over a `MemoryProvider`. It stores **only** concise,
candidate-scoped strategy text:

- Candidate preferences ("Candidate prefers remote roles.")
- A short pointer/summary of a persisted `LearningInsight`
  ("[ROLE_FAMILY] AI Engineer applications... Recommendation: ...")

It **never** stores raw job listings, application events, full resumes,
`OpportunityScore`s, or database rows — those stay in SQLite, which
remains authoritative for everything. Every call is namespaced by
`candidate_id`; `MockMemoryProvider` (used in all tests) enforces this the
same way a real backend's user-scoped storage would — candidate A can
never retrieve candidate B's memories
(`tests/test_memory_service.py::test_candidate_isolation`).

### mem0 fallback

mem0 failure never stops HireLoop. `sync_mem0_node`
(`src/graph/nodes/outcome.py`) always runs *after* `persist_strategy_insight`
— the insight is durably in SQLite before mem0 is ever touched. If the
provider is unhealthy or absent, the workflow records
`mem0_sync_status = "DEGRADED"` (or `"NOT_CONFIGURED"`) and a Decision
Trace note:

```
mem0 unavailable; strategy insight(s) persisted locally only.
```

No insight is ever lost because the memory provider is unavailable.

## 8. The scoring invariant (unchanged from Phase 1)

Before a future job search, the graph *could* retrieve relevant strategy
memories and candidate preferences from mem0 for qualitative context — but
**mem0 does not, and structurally cannot, modify `OpportunityScore`**. The
deterministic historical signal calculator
(`src/services/historical_signal.py`, unchanged since Phase 1) remains the
sole authority for the 10%-capped historical component of the score. mem0
may inform a human-facing explanation or a future UI's framing; it never
touches the number.

## 9. Human control

Three points where the loop only ever *shows* the human something, never
acts on their behalf:

1. **`human_application_action`** — the human explicitly marks an
   application `APPLIED`, saves it for later, or cancels. Nothing is ever
   submitted externally by the system.
2. **`human_record_outcome`** — the human explicitly records what
   happened, with a suspicious-sequence warning (e.g. `OFFER` before the
   application was ever `APPLIED`) requiring explicit confirmation rather
   than being silently accepted or silently blocked (Part X). Timestamps
   are never invented — either explicitly supplied or recorded at the
   moment of submission.
3. **Learning Agent output** — always a recommendation surfaced to the
   human, never an autonomous change (§6).
