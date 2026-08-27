# HireLoop AI — Architecture Decisions

This document records why key architectural choices were made, so future
changes can be evaluated against the original reasoning rather than
rediscovered from scratch.

---

### 1. Why numerical opportunity scoring is deterministic

An LLM producing a slightly different score on every run makes rankings
unreproducible and impossible to audit or regression-test. The Opportunity
Scoring Engine uses a fixed, versioned, weighted formula so that a given
candidate/job pair always produces the same score under the same model
version. Reproducibility is required for a "measurable end-to-end success
outcome" — you cannot measure improvement against a moving target.

### 2. Why agents only handle judgment-heavy tasks

Every step that has a single correct mechanical answer (parsing, dedup,
normalization, arithmetic scoring, DB writes) is implemented as plain
Python. Agents are reserved for steps that require interpreting ambiguous
or unstructured input: building a profile from free-text resume content,
explaining a fit score in human terms, proposing resume language, verifying
truthfulness, and synthesizing patterns from outcome history. This keeps
the system cheap, fast, testable, and easy to debug — and it demonstrates
a deliberate, defensible boundary between "agentic" and "deterministic"
rather than routing everything through an LLM by default.

### 3. Why Pinecone is evidence retrieval, not scoring

Semantic similarity between a resume and a job description is a weak, easily
gamed proxy for actual fit (it rewards keyword overlap, not real
qualification). Using Pinecone only to retrieve supporting evidence — e.g.
"which resume bullet points relate to this claim or this required skill" —
keeps embeddings in their strongest role (retrieval) and keeps the scoring
formula transparent, deterministic, and free of vector-store nondeterminism.

### 4. Why SQLite is the source of truth

Applications, outcomes, and scores are structured, relational, and need to
be queried and reported on (e.g., "how many applications resulted in
interviews"). SQLite gives ACID guarantees and simple querying without
operational overhead, and it is the one place all other subsystems (mem0,
Pinecone, LangGraph checkpoints) can be safely rebuilt from if lost.

### 5. Why mem0 stores learned strategy/preferences

Candidate preferences and learned strategy need to persist *across sessions*
in a form suited to natural-language recall ("this candidate responds well
to fully-remote listings," "recommend leading with backend experience for
platform roles"). mem0 is purpose-built for this kind of evolving,
retrievable long-term memory, whereas SQLite is better suited to fixed-shape
transactional records.

### 6. Why automatic job applications are excluded

Submitting an application is an irreversible, externally-visible action on
the candidate's behalf. Autonomously doing this without review risks
sending inaccurate or untruthful content, and directly violates the
project's own human-in-the-loop requirement. The MVP draws a hard line: no
autonomous action may submit, send, or finalize anything a human hasn't
approved.

### 7. Why historical signals are capped

Early in the system's life, outcome history is small and noisy. Letting the
historical signal grow beyond its configured weight (10%) would let a
handful of data points dominate the score and produce unstable, overfit
rankings. Capping the weight — and keeping it configuration-driven rather
than dynamically adjustable — keeps the score's behavior predictable and
prevents the system from confidently overreacting to weak evidence.

### 8. Why Truth Guard is separate from Resume Tailor

A single agent grading its own work is a well-known reliability failure mode
— it tends to rationalize its own output rather than critique it
adversarially. Splitting verification into a distinct agent, with its own
prompt, its own evidence retrieval, and its own claim-by-claim
classification, produces a genuine independent check rather than a
self-report. This is also what makes the "truthful resume tailoring" claim
credible rather than cosmetic.

### 9. Why the demo uses seeded historical data

A real learning signal needs enough data points to distinguish a pattern
from noise. With only 1-3 live outcomes generated during a demo, any
"learning" the system shows would be a coincidence dressed up as insight.
Seeding ~15-25 clearly-labeled synthetic historical applications, spanning
multiple role categories and outcomes, lets the Learning Agent demonstrate
real pattern synthesis — with honest sample-size and confidence reporting —
without misrepresenting a handful of demo actions as statistically
meaningful.

### 10. Why the MVP uses seeded job listings instead of live scraping

Live scraping introduces external dependencies, rate limits, ToS concerns,
and non-reproducible input data — none of which are necessary to
demonstrate the core agentic workflow (fit scoring, tailoring, truth
verification, learning). A fixed, seeded job batch keeps the MVP
demonstrable in under 5 minutes, fully reproducible between runs, and keeps
the scope focused on the orchestration and agent behavior the certification
is actually evaluating. Live ingestion is explicitly deferred to post-MVP.

### 11. Why live job discovery (You.com) is optional and never a certification-demo dependency

Once live ingestion (deferred by decision #10) was worth adding, the same
reproducibility argument that justified the seeded batch also bounds how
live discovery is wired in: an external, rate-limited, non-deterministic
search API cannot be allowed to sit on the path the certification demo or
`evals/run_evals.py` exercises, or a vendor outage/quota change would make
the "288/288 tests, 88/88 evals, fully offline DEMO_MODE" claim fragile. So
You.com is integrated as a strictly additive, opt-in mode: `DEMO_MODE`
never calls it (enforced by a test that patches `you_search.search_jobs` to
raise if invoked during the demo workflow), it is only reachable via a
human clicking "Search Live Jobs" in the UI, and it re-uses the existing
`ingest_jobs_node`'s new `job_source_override` hook rather than a parallel
ingestion path — so everything downstream (normalize/dedupe/quality/score)
is exactly the same, already-certified code regardless of which job source
was used. You.com itself is scoped narrowly to discovery only: it returns
title/url/snippet/highlights and nothing else — it never scores, ranks, or
judges fit, and a deterministic (non-LLM) classifier, not the vendor's own
relevance ranking, decides what's job-like enough to enter the pipeline.
