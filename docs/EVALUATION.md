# HireLoop AI — Evaluation

Status: **Re-confirmed at certification freeze, 2026-08-27.** Both commands
below were re-run in full during this freeze audit, not copied from an
earlier report.

## What was run

```bash
python -m pytest -q
python -m evals.run_evals
```

## Results (this session, exact)

**Unit/integration test suite:** `330 passed, 0 failed` (1 warning, unrelated
— `langchain_core`'s Pydantic v1 shim noting Python 3.14 incompatibility of
a code path HireLoop doesn't use).

**Evaluation harness:** `94/94` total cases, `12/12` categories run (0
crashed), **100.00%** accuracy, **safety gate: PASSED**, exit code 0.

| Category | Result | Notes |
|---|---|---|
| Resume Extraction | 7/7 | |
| Deduplication | 6/6 | |
| Job Quality | 7/7 | |
| Opportunity Ranking | 5/5 | |
| Match Grounding | 5/5 | |
| **Truth Guard** | **23/23** | `counters: {'false_verified': 0, 'false_unsupported': 0}` |
| **Human Approval Enforcement** | **7/7** | `counters: {'enforcement_violations': 0}` |
| **Failure Recovery** | **6/6** | `counters: {'RECOVERED': 3, 'DEGRADED': 0, 'SAFE_FAILURE': 3, 'UNSAFE_FAILURE': 0}` |
| Outcome Analytics | 7/7 | |
| Learning Insight Grounding | 8/8 | |
| **End-to-End** | **7/7** | `counters: {'task_completion': 1, 'human_selection_enforced': 1, 'unsupported_claim_blocked': 1, 'human_resume_approval_enforced': 1, 'application_created': 1, 'outcome_recorded': 1, 'strategy_insight_created': 1}` — all 7 boolean flags true in one full pipeline run |
| Live Job Discovery *(optional, You.com)* | 6/6 | Deterministic classification accuracy + a simulated-outage safe-failure case — **no real network calls** made by this category (`evals/live_discovery.py` patches `src.services.you_search.search_jobs`) |

These are the same 94/12/100%/PASSED numbers reported at the start of this
session — re-running both commands independently produced an identical
result, no discrepancy found.

## Truth Guard — the critical safety metric

23 adversarial cases (exceeding the ≥20 minimum), spanning unsupported
technology, unsupported certification, inflated title, inflated ownership,
unsupported metric, unsupported savings, unsupported team size,
skills-only evidence, project-only evidence, partial/hedged evidence,
human-confirmed evidence, and mixed claims. The number that matters most:
**`false_verified: 0`** — no unsupported claim was ever wrongly approved
across any of the 23 cases. `false_unsupported: 0` as well (no true claim
was wrongly blocked).

## Human approval enforcement

7/7 cases, `enforcement_violations: 0` — no path exists in the evaluated
scenarios where a consequential action (resume version creation,
application creation, outcome recording) occurred without the
corresponding human interrupt action reaching the graph.

## Failure safety

6/6 cases: 3 `RECOVERED` (a transient failure that the system retried past
successfully), 3 `SAFE_FAILURE` (a failure the system could not recover
from, but which it reported cleanly rather than producing an unsafe or
fabricated result), 0 `DEGRADED`, and — the number that matters —
**0 `UNSAFE_FAILURE`**.

## End-to-end task completion

One full pipeline run (resume upload → scoring → human job selection →
resume tailoring → Truth Guard blocking an unsupported claim → human
resume approval → application creation → outcome recording → strategy
insight creation) with all 7 completion flags verified `true` in the same
run — this is not seven independent partial checks, it's one coherent
task completed start to finish.

## What this evaluation does — and does not — claim

`python -m evals.run_evals` evaluates **system correctness**: does the
code do what it says it does, deterministically and safely, against known
scenarios. It is **not** a measurement of real-world outcomes.

**Explicitly not claimed anywhere in this evaluation:**

- No claim of any real-world interview-rate improvement, response-rate
  improvement, or hiring outcome. The 94 evaluation cases and 330 unit
  tests test code behavior against synthetic fixtures, not real candidate
  results.
- No claim that HireLoop has ever helped a real person get a real
  interview or job offer.
- No claim that the Opportunity Score predicts actual hiring decisions.

## Limitations

These apply beyond just the evaluation numbers above — they describe
honest boundaries of the whole system as certified:

- **No automatic applications.** HireLoop never submits anything to an
  employer; every application status change is a recorded human action.
- **No guarantee a discovered job is still active.** Neither the seeded
  demo batch nor a live You.com-discovered listing is re-verified against
  the employer's site at the moment a candidate applies.
- **Search-provider result counts may differ from requested counts.** This
  session's live You.com call requested `count=5`/`num_web_results=5` and
  received 10 web results — HireLoop does not rely on the vendor honoring
  a requested count; its own `you_search_max_results` cap and the
  deterministic `LIKELY_JOB` classifier independently bound what actually
  reaches scoring regardless of raw API response size.
- **Truth Guard reduces fabrication risk; it cannot guarantee factual
  correctness.** It can only check a claim against evidence HireLoop has
  recorded — it cannot verify a candidate's real life, and a confident
  `VERIFIED` still ultimately traces back to what the candidate themselves
  supplied.
- **Synthetic outcome history is for demonstration/evaluation only.** The
  23 seeded historical applications are fabricated and are never presented
  as real employment outcomes (`is_demo_data` flag throughout).
- **Observed historical correlations do not establish causality.** The
  Learning Agent's deterministic validation layer rejects causal language
  outright (`docs/LEARNING_LOOP.md` §6) — an insight can describe what was
  *observed*, never what an action *caused*.
- **MVP is single-user/local-oriented.** No multi-user authentication or
  account system.
- **No production authentication.** Not implemented — out of scope for
  this MVP (`docs/SECURITY_PRIVACY.md`, "Known limits").
- **No production-scale infrastructure.** SQLite, in-process mock
  providers by default, no load balancing, no managed deployment — this is
  a certification MVP, not a production service.
- **No guarantee the Opportunity Score predicts actual hiring decisions.**
  It is a transparent, reproducible fit heuristic against stated
  requirements — not a prediction of what any real employer will decide.
