# HireLoop AI — Certification Freeze Report

Date: **2026-08-27.** This is the freeze report for the certification MVP.
Everything in this document was verified directly during this session —
commands re-run, files re-read — not copied forward from an earlier
report without re-checking.

## 1. Freeze audit

**Git state: this working tree is NOT a git repository.** No `.git`
directory exists anywhere in the tree; `git status` fails with
`fatal: not a git repository (or any of the parent directories): .git`.
`git init`, staging, a first commit, and a push to a remote are all
prerequisites the human still has to perform — nothing in this freeze
assumes any of that has happened.

**Files/directories that currently exist and should NOT be committed:**

| Path | Why |
|---|---|
| `.env` | Contains real, live provider credentials (You.com, plus placeholders/keys for Nebius/Fireworks/Pinecone/mem0). Already covered by `.gitignore`'s `.env` entry; `.env.*` was added this session as a belt-and-suspenders pattern, with `!.env.example` negated back in since that file is safe and meant to be committed. |
| `__pycache__/` (12 directories found) | Compiled bytecode caches. Already covered by `.gitignore`. |
| `.pytest_cache/` | Test-run cache. Already covered by `.gitignore`. |

**Nothing was deleted** during this audit — every file above is simply
confirmed already-excluded (or newly excluded) by `.gitignore`, not
removed from disk.

**No `.db` or `.log` files exist anywhere in the working tree** at freeze
time (checked directly this session) — the Streamlit app's default
in-memory SQLite mode (§18 below) means no business or checkpoint DB file
is ever created during a normal demo run.

**Judgment call flagged for the human, not decided unilaterally:**
`evals/results/latest.json` exists as a generated evaluation-run artifact
(the JSON report `python -m evals.run_evals` writes on every run). It is
currently **not** covered by `.gitignore` and would be committed by
default. Two defensible options: (a) commit it as certification evidence
— a concrete, timestamped 94/94 snapshot alongside the code that produced
it, or (b) `.gitignore` it as a regenerable build artifact, since anyone
can reproduce it with one command. This freeze does not choose for you —
see `docs/SUBMISSION_CHECKLIST.md`.

**New files added this session (documentation/config only, nothing under
`src/` or `app.py` was modified):**

- `.env.example` — already existed (created during the earlier You.com
  integration work, along with the `YDC_API_KEY`/`YOU_SEARCH_*` entries);
  this session only added one clarifying comment line confirming it's
  placeholder-only and safe to commit. Not a new file.
- `.gitignore` — extended with `.env.*` / `!.env.example` / `*.log`
  (previous entries untouched).
- `docs/CERTIFICATION_AUDIT.md`, `docs/EVALUATION.md`,
  `docs/BUILD_PROCESS.md`, `docs/SUBMISSION_CHECKLIST.md`,
  `docs/CERTIFICATION_FREEZE.md` (this file) — all new.
- `docs/PROJECT_OVERVIEW.md` — extended (not rewritten): a new You.com
  disclosure section, additional Learnings entries, additional
  Limitations entries.

No other doc required a correction — `docs/ARCHITECTURE.md`,
`docs/WORKFLOW.md`, `docs/TRUTH_GUARD.md`, `docs/LEARNING_LOOP.md`,
`docs/DECISIONS.md`, `docs/SECURITY_PRIVACY.md`, `docs/DEMO_SCRIPT.md`,
`docs/FINAL_REPORT.md`, and `README.md` were all read in full and found
accurate against current code.

## 2. Test / eval snapshot at freeze

- **Unit/integration tests:** 330 passed, 0 failed.
- **Evaluation harness:** 94/94 cases, 12/12 categories, 100% accuracy,
  safety gate **PASSED**.
- **Truth Guard:** 23/23, `false_verified: 0`, `false_unsupported: 0`.
- **Human approval enforcement:** 7/7, `enforcement_violations: 0`.
- **Failure recovery:** 6/6, `UNSAFE_FAILURE: 0` (`RECOVERED: 3,
  SAFE_FAILURE: 3, DEGRADED: 0`).
- **End-to-end:** 7/7, all 7 completion flags true.

Full breakdown and the explicit "not a real-world outcome claim"
disclaimer: `docs/EVALUATION.md`.

## 3. System summary

- **Agents:** 5 — Profile Agent, Match Analyst, Resume Tailor, Truth
  Guard, Learning Agent. Full input/output/boundary detail:
  `docs/CERTIFICATION_AUDIT.md` §3.
- **Main deterministic services:** resume parsing, normalization,
  deduplication, job quality, requirement completeness
  (`job_evidence_sufficiency.py`), Opportunity Scoring, historical signal,
  outcome analytics, actionability classification, application tracking,
  Decision Trace, evidence retrieval (with deterministic local fallback).
  Full list with the deterministic-not-agentic rationale for each:
  `docs/CERTIFICATION_AUDIT.md` §4.
- **External tools:** You.com (live job discovery, optional/opt-in),
  Pinecone (evidence retrieval, optional), mem0 (strategy memory,
  optional), Nebius / Fireworks (live LLM inference, optional — Mock
  provider is the default and what backs the demo). Full inventory with
  fallback behavior: `docs/CERTIFICATION_AUDIT.md` §2.
- **Human checkpoints:** 5 real LangGraph `interrupt()`/
  `Command(resume=...)` pauses — job selection, clarification, resume
  approval, application action, outcome recording. All SQLite-checkpointed
  and independently re-verified this session against `src/graph/nodes/`
  and `docs/WORKFLOW.md`.
- **Offline demo status:** fully functional with zero external network
  dependency by default (`DEMO_MODE=true`, `DEFAULT_LLM_PROVIDER=mock`, no
  Pinecone/mem0/You.com calls) — re-confirmed this session (§Final
  Verification below).
- **Live You.com status:** exercised exactly once this session; full
  factual disclosure in `docs/PROJECT_OVERVIEW.md`'s You.com section —
  real endpoint, real 200 response, 10 results returned against a
  requested count of 5, 5 classified `LIKELY_JOB`, one successfully
  converted to a `JobPosting` with no fabricated fields, key never
  logged.
- **Known limitations:** full list in `docs/EVALUATION.md` and
  `docs/PROJECT_OVERVIEW.md`'s Limitations section (no automatic
  applications, no guarantee of listing freshness, provider result-count
  variance, Truth Guard reduces but doesn't guarantee correctness,
  synthetic outcome history, no causal claims, single-user MVP, no
  production auth/infra, no guarantee the score predicts hiring
  decisions).

## 4. Demo reset mechanism

`app.py::_init_session` calls `get_connection(":memory:")` for the
business database and `get_sqlite_checkpointer(":memory:")` for both the
main and outcome-update checkpointers, on every session — confirmed by
direct code read this session (`app.py` lines 60, 71, 73). **No file is
ever written to disk in the default Streamlit deployment**, regardless of
what `SQLITE_DB_PATH` in `.env` is set to (that setting is only consulted
by the standalone `scripts/run_phase*_demo.py` terminal demos, not by
`app.py`). This means:

**The reset mechanism for the certification demo is: restart the
Streamlit process.**

```bash
# stop the running `streamlit run app.py` process, then:
streamlit run app.py
```

A fresh process gets a fresh in-memory SQLite connection and a fresh
in-memory LangGraph checkpointer — there is no persisted state file to
delete. No new reset script was created, because one would be unnecessary
machinery for a mechanism the app already provides by construction.

If a future non-default deployment points `SQLITE_DB_PATH` at a real file
(a file-based business DB and/or a file-based workflow checkpoint DB),
that deployment does not yet have a corresponding safe-delete reset
script in `scripts/` — `scripts/` currently holds only
`generate_demo_application_history.py` and the four `run_phase*_demo.py`
terminal demos, none of which delete anything. This is noted as a real
gap for that hypothetical future case, not silently built around, since
the certification demo itself does not need it.

## 5. Exact commands (verified this session)

```bash
# Install
python -m venv .venv
.venv\Scripts\activate                 # Windows
pip install -r requirements.txt
pip install -r requirements-dev.txt    # for tests/evals

# Environment (creates a local .env from the newly-added, safe template)
copy .env.example .env
# .env's defaults (DEMO_MODE=true, DEFAULT_LLM_PROVIDER=mock) require no
# keys at all to run the certification demo.

# Run the product
streamlit run app.py

# Run the test suite
python -m pytest -q
# -> 330 passed, 0 failed (this session)

# Run the evaluation harness
python -m evals.run_evals
# -> 94/94 cases, 12/12 categories, 100%, safety gate PASSED (this session)

# Reset the demo
# (stop the running streamlit process, then run it again — see §4 above)
streamlit run app.py
```

`pip install -r requirements.txt` was sanity-checked against the actual
package list this session (`langchain`, `langgraph`, `streamlit`,
`mem0ai`, `pinecone-client`, `python-dotenv`, `pydantic`, `httpx`,
`pypdf`, `python-docx`, `langgraph-checkpoint-sqlite`) — no dependency
was added, removed, or upgraded during this freeze.

## 6. Remaining external submission actions (not performed by this audit)

- `git init` + a first commit (no `.git` directory currently exists).
- Push the repository to GitHub and confirm its visibility settings.
- Record the certification demo video (script ready: `docs/DEMO_SCRIPT.md`,
  5:00 exactly).
- Test the video link in an incognito window / confirm it's viewable by
  the required audience.
- Fill out and submit the certification submission form.
- Decide whether to commit or gitignore `evals/results/latest.json`
  (§1 above — a judgment call left to the human).

None of these are claimed as done anywhere in this freeze — see
`docs/SUBMISSION_CHECKLIST.md` for the itemized, mostly-unchecked list.

## 7. Final verification (this session, exact)

Run in this order:

1. `python -m pytest -q` → **330 passed, 0 failed** (1 unrelated warning:
   `langchain_core`'s Pydantic v1 shim noting Python 3.14 incompatibility
   of a code path HireLoop doesn't use).
2. `python -m evals.run_evals` → **94/94 cases, 12/12 categories, 100.00%,
   safety gate PASSED**, exit code 0. Per-category counters:
   `truth_guard {'false_verified': 0, 'false_unsupported': 0}`,
   `human_approval {'enforcement_violations': 0}`,
   `failure_recovery {'RECOVERED': 3, 'DEGRADED': 0, 'SAFE_FAILURE': 3,
   'UNSAFE_FAILURE': 0}`, `end_to_end` — all 7 flags true.
3. Compile check (`python -m py_compile` over every file under `src/`,
   `evals/`, `tests/`, plus `app.py`) → **0 compile errors**.
4. Offline `DEMO_MODE` smoke check via a headless
   `streamlit.testing.v1.AppTest` run (Candidate page → Run search →
   Opportunities page) → **no exceptions**, real backend state produced
   throughout, no You.com API call made.

No You.com API call was made anywhere in this verification pass — the
only live call made during this entire session was the single,
already-disclosed call documented in `docs/PROJECT_OVERVIEW.md`'s You.com
section, made before this final verification step, not during it.

All four numbers match the numbers verified at the very start of this
session (330/330, 94/94, safety gate PASSED, 0 compile errors) with no
discrepancy found.

**CERTIFICATION BUILD READY TO FREEZE**
