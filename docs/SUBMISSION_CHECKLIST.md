# HireLoop AI — Submission Checklist

Status: **Freeze-phase checklist.** Every checked box below was verified
directly during this freeze audit session (re-run commands, direct code
reads) — nothing is checked on the basis of an earlier doc's claim alone.
Every unchecked box is either a genuine external/manual action the human
still has to perform, or a gap this audit could not independently confirm.

## Code & tests

- [x] `python -m pytest -q` passes — **330 passed, 0 failed** (re-run this
      session).
- [x] `python -m evals.run_evals` passes — **94/94 cases, 12/12
      categories, 100%, safety gate PASSED** (re-run this session).
- [x] Truth Guard safety metric confirmed — **0 false-verified** across 23
      adversarial cases (re-run this session).
- [x] Human approval enforcement confirmed — **0 enforcement violations**
      across 7 cases (re-run this session).
- [x] Failure recovery confirmed — **0 UNSAFE_FAILURE** across 6 cases
      (re-run this session).
- [x] `src/`, `evals/`, `app.py`, `tests/` all compile cleanly
      (`python -m py_compile`, this session, exit 0).
- [x] Offline `DEMO_MODE` smoke path confirmed working end-to-end
      (Candidate → Run search → Opportunities, no exceptions — this
      session, see `docs/CERTIFICATION_FREEZE.md` §Final Verification).

## Secrets & repo hygiene

- [x] Repo-wide secret scan performed (excluding `.env` and
      `__pycache__`) — no genuine secret found outside `.env` itself. The
      only `ydc-`-prefixed string outside `.env` is the deliberately-fake
      `tests/test_you_search.py::_FAKE_KEY`.
- [x] `.env` confirmed excluded from version control via `.gitignore`.
- [x] `.gitignore` audited and extended this session: added `.env.*` +
      `!.env.example`, and `*.log` (see `docs/CERTIFICATION_FREEZE.md`
      §1 for the full before/after).
- [x] `.env.example` (placeholder-only, safe to commit) confirmed present
      and accurate — it already existed from the earlier You.com
      integration work; this session added one clarifying comment line
      ("This file is safe to commit...") but did not create the file.
- [x] No `.db`, `.log`, or temp-upload files found anywhere in the working
      tree at freeze time.
- [x] No secrets are printed, logged, or written by anything run during
      this audit — the actual `.env` values were never echoed in any tool
      output, doc, or report produced this session.

## Documentation

- [x] `README.md` leads with value (name/tagline, Problem → Solution →
      Why It's Different) before Architecture/Tech-stack/Installation, and
      states "HireLoop is not an auto-apply bot" prominently — verified
      this session, no changes needed.
- [x] `docs/PROJECT_OVERVIEW.md` completeness-audited against the full
      required-sections list (overview, problem, target user, one-liner,
      workflow, architecture, agent framework, tools, models/providers,
      datasets, synthetic-data disclosure, prompts/vibe-coding, iterations,
      error handling, human-in-the-loop, evaluation, learnings,
      limitations, roadmap) — all present; extended with a You.com
      disclosure section, additional Learnings entries, and additional
      Limitations entries this session.
- [x] `docs/ARCHITECTURE.md` diagrams re-validated against current code,
      including the You.com "Live Job Discovery" section — already
      accurate (correct endpoint, `results.web`-only contract); no update
      needed.
- [x] `docs/DEMO_SCRIPT.md` re-validated: fits ≤5:00, stays offline for
      the core path, treats You.com as optional bonus only, hits every
      required visible moment — no changes needed.
- [x] `docs/CERTIFICATION_AUDIT.md` (new) — certification requirements
      audit with file/function/test citations, tool inventory, agent
      inventory, deterministic service inventory, dataset audit.
- [x] `docs/EVALUATION.md` (new) — evaluation results and explicit
      real-world-outcome disclaimer.
- [x] `docs/BUILD_PROCESS.md` (new) — phase-by-phase build history.
- [x] `docs/CERTIFICATION_FREEZE.md` (new) — freeze report.
- [x] Datasets documented with source/synthetic-vs-real/purpose for each
      (`docs/CERTIFICATION_AUDIT.md` §Dataset Audit).
- [x] Prompts/vibe-coding process documented
      (`docs/PROJECT_OVERVIEW.md`, `docs/BUILD_PROCESS.md`).
- [x] Iterations documented, including the Truth Guard hybrid correction,
      the SQLite threading fix, the `rejected_modifications` claim-text
      gap, and the You.com endpoint/response-shape correction.
- [x] Learnings documented (`docs/PROJECT_OVERVIEW.md`, extended this
      session).
- [x] Error handling documented (`docs/WORKFLOW.md` §10–11).

## Demo readiness

- [x] Demo fits ≤5 minutes as scripted (`docs/DEMO_SCRIPT.md`, timed
      beats sum to 5:00).
- [x] Offline/deterministic core demo path confirmed (no external network
      calls required for the certified path).
- [x] Live You.com "bonus" path is clearly marked optional, human-
      triggered, and not part of the certified/graded path.
- [ ] **Video recorded.** Not performed by this audit — an external,
      human action.
- [ ] **Video link tested in incognito / confirmed publicly viewable.**
      Not performed by this audit — an external, human action; cannot be
      verified until a video exists.

## Git & GitHub

- [ ] **`git init` run and a first commit made.** **Not done — this
      working tree is not currently a git repository.** `git status`
      fails with `fatal: not a git repository (or any of the parent
      directories): .git`; no `.git` directory exists anywhere in the
      tree. This is a prerequisite the human still has to do before any
      push.
- [ ] **Repository pushed to GitHub.** Not done — depends on the above;
      external action.
- [ ] **GitHub repository visibility confirmed (public, or shared with
      the required reviewers).** Not done — external action, cannot be
      performed by this audit since no remote exists yet.
- [ ] **`evals/results/latest.json` commit decision made.** Open judgment
      call for the human: commit it as certification evidence (a real,
      re-runnable snapshot of the 94/94 result), or `.gitignore` it as a
      regenerable artifact. Not decided unilaterally by this audit — see
      `docs/CERTIFICATION_FREEZE.md` §1.

## Submission

- [ ] **Submission form filled out and submitted.** Not performed by this
      audit — external, human action.

## Summary

Everything checkable from inside this repository and this session's own
command runs is checked. Every remaining unchecked item requires an
action outside this repository (recording, pushing, visibility settings,
form submission) or a judgment call reserved for the human
(`evals/results/latest.json` commit decision) — none of them were silently
assumed done.
