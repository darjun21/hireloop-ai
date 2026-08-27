# Truth Guard

Status: **Implemented (Phase 4)**

Truth Guard reduces fabrication risk in tailored resume content. It does
**not** guarantee factual correctness — it can only check a claim against
the evidence HireLoop has recorded; it cannot verify the candidate's life.
See "Limits" at the end of this document.

## Why Truth Guard is a separate agent

Resume Tailor and Truth Guard are architecturally distinct, and Truth
Guard is never allowed to reuse Resume Tailor's own stated `reason` or
`targeted_job_requirement` as evidence. A single agent grading its own
work is a well-known reliability failure mode — it tends to rationalize
its own output rather than critique it adversarially. Truth Guard only
ever consults the candidate's `CandidateProfile` and its attached
`Evidence` records (`src/models/evidence.py`); the Tailor's justification
text is treated as untrusted, exactly like everything else it produces.

## Why a hybrid (deterministic + LLM), not "ask an LLM to judge truthfulness"

An earlier version of this system implemented Truth Guard as a single,
fully deterministic rule engine. That design was correct but too rigid for
one requirement: some claims genuinely need semantic judgment (is "built"
close enough to "developed"? does listing a skill imply hands-on
ownership?), not just pattern matching. Asking a second LLM to judge a
first LLM's output, unconstrained, just adds a new class of hallucination
risk instead of removing one. The resolution is a **three-layer hybrid**
(`src/agents/truth_guard.py`):

1. **Deterministic pre-checks** (always run, no LLM call): unsupported
   numeric metrics, technologies entirely absent from the profile,
   job-title inflation, and the clear-cut end of skill verification (a
   skill is either missing outright, or grounded in work/project evidence
   with wording no stronger than the evidence itself). These are cheap,
   fully auditable, and don't benefit from semantic judgment.
2. **LLM semantic reasoning** — invoked *only* for the genuinely ambiguous
   remainder: wording that escalates evidenced work into stronger
   ownership language ("used" → "designed"), or a skill that appears only
   in a bare Skills list with no work/project context.
3. **Deterministic post-validation, fail-closed**: the LLM's output can
   never upgrade a fragment Layer 1 already ruled `UNSUPPORTED`, and can
   never mark a skills-only fragment `VERIFIED` — at best
   `NEEDS_HUMAN_CONFIRMATION`. If the LLM call itself fails after the
   provider layer's own retry/fallback is exhausted, every fragment that
   needed it is forced to `NEEDS_HUMAN_CONFIRMATION`, never silently
   treated as `VERIFIED`.

This gives deterministic safety guardrails *and* real semantic judgment
where it's actually needed, without either weakening the guardrails or
pretending an LLM alone is a sufficient safety mechanism.

## Evidence hierarchy

Not all evidence carries equal weight. Truth Guard's rules encode this
explicitly:

1. **Direct resume / work-experience / project evidence** — the strongest
   tier. A skill mentioned inside a specific job or project description is
   evidence the candidate actually *did* something with it.
2. **`HUMAN_CONFIRMATION` evidence** — created only when a human explicitly
   attests to a claim during the clarification interrupt
   (`src/models/enums.py::EvidenceSourceType.HUMAN_CONFIRMATION`).
   Deliberately a distinct source type, never merged into or presented as
   resume-derived evidence — a human saying "yes I did that" is recorded,
   not silently trusted forever.
3. **Skills-only evidence** — a skill appearing only in a flat Skills list
   with no work/project context. Enough to verify a plain statement like
   "has experience with AWS," but never enough on its own to verify a
   claim of specific action, especially an ownership/authority claim like
   "architected enterprise-scale AWS infrastructure." Truth Guard caps
   such fragments at `NEEDS_HUMAN_CONFIRMATION` — an LLM cannot upgrade
   this to `VERIFIED` (see the post-validation cap above).
4. **Semantic retrieval candidates** (Pinecone or the local fallback) — the
   weakest tier and explicitly *not proof*. A vector similarity match only
   *locates* potentially-relevant evidence text for a human or the
   deterministic layers to look at; Truth Guard's actual verdict always
   traces back to a concrete `Evidence` object with a real `evidence_id`,
   never to a bare similarity score.

## Pinecone is retrieval, not truth

`src/services/vector_service.py` and `src/services/evidence_retrieval.py`
exist purely to help *locate* which of the candidate's own Evidence
records are relevant to a job requirement. Pinecone never computes a
verdict, never stores a score, and never becomes a source of truth — see
docs/DECISIONS.md #3 for the same principle applied to Opportunity
Scoring. A Pinecone similarity match only earns a fragment a spot in the
"candidate evidence to consider" list; Truth Guard's rules and the
optional semantic layer still have to actually judge it.

## Candidate isolation

Each candidate's evidence is indexed under its own Pinecone **namespace**
(the `candidate_id`), so a query is structurally incapable of returning
another candidate's vectors regardless of query content — enforced by the
SDK's namespace parameter, not just an application-level filter. Every
result row is defensively re-checked against the requested `candidate_id`
as a second layer. Tested directly against `InMemoryVectorIndex`, which
implements the identical `EvidenceVectorIndex` contract real Pinecone-backed
code depends on (`tests/test_vector_service.py`).

## Local fallback

Pinecone failure — misconfiguration, outage, or simply not being
configured at all (the MVP demo's default) — must never break the
workflow. `src/services/evidence_retrieval.py` wraps every Pinecone call;
on any `VectorServiceError` or a failed health check, it falls back to
`src/services/local_evidence_search.py` (deterministic normalized-token
overlap, no embeddings, no network) and appends an explicit Decision Trace
event: *"Pinecone evidence retrieval unavailable; local fallback used."*
Nothing about correctness degrades silently — see docs/WORKFLOW.md's
failure table.

## Numeric metric rules

Any new percentage, dollar amount, user/customer count, latency number,
team size, or similar figure appearing in a proposed modification must be
found verbatim (or near-verbatim, whitespace-normalized) in either the
original resume text or a specific Evidence record. If it isn't, the
fragment is `UNSUPPORTED` — always a deterministic, Layer-1 check; no
semantic judgment is extended to invented numbers.

## Claim granularity

Truth Guard never validates an entire sentence as one giant claim. A
modification like *"Built LangChain RAG systems and deployed them on
Kubernetes, reducing latency by 40%"* is broken into independent
fragments — LangChain, RAG, Kubernetes, "40%" — each classified on its
own. If any fragment is `UNSUPPORTED`, the whole modification's status is
`UNSUPPORTED` and `unsupported_fragments` names exactly which piece(s)
failed, so a correction pass (or a human) can act on precisely that
wording rather than discarding an otherwise-truthful sentence.

## Fail-closed behavior

If the LLM semantic layer's provider call fails (timeout, rate limit,
auth error, malformed output) even after the provider layer's own
retry/fallback is exhausted, the affected fragment is forced to
`NEEDS_HUMAN_CONFIRMATION` — never silently `VERIFIED`. Verified by
`tests/test_truth_guard.py::test_llm_failure_during_semantic_review_fails_closed_not_verified`.
Deterministic `UNSUPPORTED` findings are never even sent to the LLM in the
first place (there's nothing left for semantic judgment to change), which
both saves a call and closes off any path for an adversarial or buggy LLM
response to upgrade them — verified directly by
`test_deterministic_unsupported_survives_adversarial_llm`.

## Human clarification (`NEEDS_HUMAN_CONFIRMATION`)

A dedicated LangGraph interrupt (`human_clarification`,
`src/graph/nodes/clarification.py`) presents the proposed claim, why the
evidence was insufficient, the closest evidence available, and the
suggested safe rewrite if one exists. Four actions:

- `CONFIRM_WITH_EVIDENCE` — creates a new `HUMAN_CONFIRMATION` Evidence
  record (never mutates or merges into resume-derived evidence), then
  re-runs Truth Guard.
- `REJECT_CLAIM` — the modification is dropped and recorded in
  `rejected_modifications`.
- `USE_SAFE_REWRITE` — applies the suggested safe rewrite (falling back to
  the modification's `original_text` when one exists); if no safe rewrite
  exists, the claim is unchanged and Truth Guard re-evaluates it as-is —
  the graph re-prompts rather than silently approving.
- `CANCEL` — clean `CANCELLED` end.

## Human resume approval boundary

Only modifications whose latest Truth Guard status is `VERIFIED` are ever
offered at the `human_resume_approval` interrupt
(`src/graph/nodes/resume_approval.py`) — an `UNSUPPORTED` or
`PARTIALLY_SUPPORTED` modification is structurally never in the offered
set. A human `EDIT` produces a *new* claim, which is re-verified through
Truth Guard before it can appear as approvable — editing never bypasses
verification. Only explicitly approved `modification_id`s enter
`approved_modification_ids`; everything else is preserved in
`rejected_modifications` and the Decision Trace, never silently discarded.

## Correction loop cap

Automated correction (`correct_modifications` → `truth_guard`, repeated)
is capped at `MAX_RESUME_REVISION_LOOPS = 2`
(`src/config/workflow.py`). Each pass applies a modification's
deterministic `suggested_safe_rewrite` — never asks the Tailor to guess
again, which would risk a second, differently-wrong fabrication. After 2
passes, any modification still not `VERIFIED` is stripped from the
proposed set (`strip_unresolved_modifications`) and reported to the human
as removed, with the reason — never silently dropped, never silently kept.

## ResumeVersion immutability

The original parsed resume text is never mutated — `resume_v1_<candidate>`
is a marker `ResumeVersion` (`status=ORIGINAL`) pointing at it, created
once and never touched again. Approval only ever adds a new
`ResumeVersion` (`status=APPROVED`) referencing the approved
`modification_id`s. Verified directly by
`tests/test_workflow_phase4.py::test_original_resume_hash_unchanged_after_full_phase4_flow`
(byte-for-byte hash comparison of `resume_parse_result.extracted_text`
before and after the full Phase 4 flow).

## Verified vs. unsupported: worked examples

| Proposed claim | Evidence | Verdict |
|---|---|---|
| "Built a RAG pipeline using LangChain and Python." | Project evidence literally describing building a RAG pipeline with LangChain and Python | `VERIFIED` |
| "Deployed Kubernetes production workloads." | No Kubernetes evidence anywhere | `UNSUPPORTED` |
| "Built Docker and Kubernetes container platforms." | Docker evidenced via work experience; Kubernetes absent | `UNSUPPORTED` (Kubernetes fragment fails; Docker portion alone would not) |
| "Improved application performance by 35%." | Evidence says only "Improved application performance." | `UNSUPPORTED` (unsupported numeric claim) |
| "Senior AI Engineer" (title) | Evidenced title is "Software Engineer" | `UNSUPPORTED` |
| "Designed PostgreSQL-backed services." | Evidence says "Used PostgreSQL for storage" (no design/architecture wording) | `PARTIALLY_SUPPORTED` |
| "Architected large-scale AWS infrastructure." | AWS listed only in a Skills line, no work/project evidence | `NEEDS_HUMAN_CONFIRMATION` (never `VERIFIED` from skills-only evidence + a strong verb) |

## Limits

**Truth Guard reduces fabrication risk. It does not guarantee factual
correctness.** It can only check a claim against the evidence HireLoop has
recorded — a candidate profile with sparse or inaccurate source data will
produce correspondingly limited verification. It cannot independently
confirm anything about the real world.
