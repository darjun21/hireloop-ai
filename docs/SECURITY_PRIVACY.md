# Security & Privacy

Status: **Verified against the implemented codebase, Phase 6.**

This document records what HireLoop actually does today, verified by
reading the code — not an aspirational policy. Each claim below names the
file it was checked against.

## API keys

All provider credentials (`NEBIUS_API_KEY`, `FIREWORKS_API_KEY`,
`PINECONE_API_KEY`, `MEM0_API_KEY`) are read exclusively from environment
variables in `src/config/settings.py::load_settings()` — none are
hardcoded, checked into source, or accepted as a request parameter. `.env`
is listed in `.gitignore`; only `.env.example` (with placeholder values) is
committed. HTTP provider calls (`src/llm/http_provider.py`) send the key
only in the `Authorization` header of the outbound request to the
configured provider — it is never included in a log line, error message, or
UI element. The System/Demo page (`app.py::page_system`) shows provider
*availability* status only (`AVAILABLE` / `MOCK` / `UNAVAILABLE`), never the
key value itself.

## Logging

`src/llm/http_provider.py` and `src/llm/provider.py` log only structured
metadata — provider name, model name, latency, error type/classification —
on both success and failure paths. Resume text, prompts, and LLM response
content are never passed to `logger.info`/`logger.warning` anywhere in
`src/llm/`. The Decision Trace (`src/services/decision_trace.py`,
surfaced in the UI via `decision_trace_panel` in `app.py`) is deliberately a
log of *observable actions* ("Truth Guard verified 3 modification(s), 2
unsupported") — it never dumps resume text, full prompts, or an agent's raw
chain-of-thought.

## Pinecone (candidate evidence isolation)

`src/services/vector_service.py` indexes and queries every candidate's
evidence under a Pinecone **namespace equal to their `candidate_id`** — an
SDK-level isolation boundary, not just an application-level filter — and
additionally re-checks `metadata["candidate_id"]` on every search result as
a defensive second layer before returning it. Metadata stored per vector is
minimal: `candidate_id`, `evidence_id`, `source_type`, and enough text to
identify the fragment — never the full resume. When Pinecone is
unconfigured or unavailable, retrieval falls back to a deterministic local
search (`src/services/local_evidence_search.py`) over the same in-memory
evidence — no data leaves the process in that mode.

## mem0 (candidate preference/strategy memory)

`src/services/memory_service.py` namespaces every `add`/`search`/`delete`
call on `candidate_id` (passed as `user_id` to the real mem0 client). Only
candidate preferences and strategy-insight text are ever written — never
raw job listings, application events, or resume content
(`docs/LEARNING_LOOP.md` §1). If mem0 is unavailable, writes degrade to
"persisted locally only" in the business SQLite database; a strategy
insight is never lost, and the failure never surfaces as a fabricated
success.

## SQLite data boundaries

Two SQLite databases are a deliberate, permanent split
(`src/services/database.py`, `src/graph/checkpointing.py`):

- **Workflow checkpoint DB** (`data/workflow_checkpoints.db`) — disposable
  LangGraph run state, needed only for resuming an in-progress interrupt.
- **Business DB** (`data/hireloop.db`) — the durable system of record:
  candidates, applications, application events, resume versions, strategy
  insights, scoring model versions.

Both are excluded from version control (`.gitignore`: `*.db`,
`data/hireloop.db`). The Streamlit app runs both as **in-memory** SQLite
connections per session (`app.py::_init_session`, `get_connection(":memory:")`)
— nothing persists to disk from a UI session unless a developer explicitly
points `SQLITE_DB_PATH` at a file for a long-running deployment.

## Demo data isolation

Every application record carries an explicit `is_demo_data` flag
(`src/services/application_tracker.py`), and every read path that computes
user-facing statistics accepts an `include_demo_data` filter. The Dashboard
and Strategy pages combine live session data with demo history only when
`DEMO_MODE` is on, and every screen that shows demo-influenced numbers
carries a visible "DEMO MODE — Synthetic Data" label (`app.py`,
`page_dashboard`, `page_strategy`). Demo statistics are never presented as
a real user's outcomes.

## Errors surfaced to the user

Errors reaching `HireLoopState.errors` and the UI are categorized
(`ErrorCategory` in `src/models/enums.py`) and carry a short, sanitized
message and category — not a raw stack trace, exception repr, or upstream
provider response body. See `docs/WORKFLOW.md`'s error taxonomy for the
full classification.

## Known limits (explicitly out of scope for this document)

This document covers data handling within the implemented system. It does
**not** cover: infrastructure-level hardening of a production deployment
(TLS termination, secrets manager integration, rate limiting), multi-user
authentication (not implemented — HireLoop is single-candidate-per-session
by design in this MVP), or a formal penetration test. These are reasonable
next steps for a production deployment, not gaps in the MVP's own handling
of the data it touches.
