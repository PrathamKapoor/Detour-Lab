# FLOW.md — DETOUR LAB execution flow and checkpoint

Last updated: **19 October 2026**, Gate 5 ("Fix This Plan") implemented and verified after the
Gate 4 baseline was re-verified (`scripts/verify.ps1` → VERIFICATION PASSED, log
`var/verify-gate4-final.log`). Gate 5 verification log: `var/verify-gate5-final.log`.
This file is the single resume point. Update it *before* reporting any step as complete.

## 1. Verified environment facts (observed, not assumed)

| Item | Observed value |
|---|---|
| Host OS | Windows (win32), PowerShell 5.1 shell |
| Repo root | `C:\Pratham\DETOUR-LAB` — Git repo, branch `main`, Apache-2.0 |
| Git | 2.55.0.windows.5; local identity `PrathamKapoor <prathamkapoor027@gmail.com>`; global identity **unset** and untouched |
| Node | v24.21.0, npm 11.19.0 (`npm ping` → PONG) |
| Python | 3.12.10 in repo venv `.venv` |
| Backend deps installed | fastapi 0.143.3, pydantic 2.14.1, networkx 3.7, shapely 2.2.0, reportlab 5.0.1, uvicorn 0.54.0, pytest 9.1.1, httpx 0.28.1, hypothesis 6.170.1, ruff 0.17.1 |
| Backend tests | **373 passed** (`python -m pytest apps/api/tests`), ruff clean |
| Static analysis | `ruff check apps/api` → **All checks passed** |
| Contracts | `packages/contracts/{openapi.json,types.ts,domain-schema.json}` generated from Pydantic; byte-identical on re-run |
| Live API | uvicorn on `127.0.0.1:8077`; health, graph, evaluate, manifest, restart and replay checks all exercised |
| One-command verify | `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify.ps1` -> **VERIFICATION PASSED** (exit 0): ruff, 373 backend tests, tsc, eslint, 127 frontend tests, production build, 68 Playwright tests, live HTTP smoke, restart replay, contract determinism |
| Frontend stack | React 19.3.1, Vite 8.3.4, TypeScript 5.9.3, Vitest 5.0.5, Playwright 1.64.1, ESLint 9.39.5 (pinned in `apps/web/package.json`) |
| Frontend bundle | `index.js` ~367 kB (~106 kB gzip), `index.css` ~28 kB (~6 kB gzip) |
| E2E browsers | Playwright Chromium installed at `%LOCALAPPDATA%\ms-playwright` |
| Pre-existing code in repo | **None** — repository created empty by this session |
| Sibling projects in `C:\Pratham` | AegisCPG, freeflow, mental.ai, MORPH, sofa-problem, VeriKernel — untouched |

## 2. Authoritative processing chain (PRD §10.1 — never bypassed)

```
Import + validate → explicit graph version → scenario edits → phase graph
→ profile/rule evaluation → confirmed/possible reachability → findings
→ candidate interventions → re-verification → comparable results → immutable report manifest
```

Trust boundary: only `detour_lab.analysis` and `detour_lab.rules` produce verdicts, routes,
feasibility graphs and solver states. The UI (Gate 3) renders them; reports (Gate 2/6) are built
from stored canonical facts.

## 3. Gate status (evidence-based)

| Gate | Scope | Status | Evidence |
|---|---|---|---|
| 0 | Evidence, repo, docs, dependency-verified skeleton, boot + smoke | **PASSED** | `scripts/verify.ps1` output recorded in section 5; API booted on 8077 |
| 1 | Immutable graph, evidence, four-valued rules, confirmed/possible routing, hashing | **PASSED** | 202 tests; INV-01..08 classes in `test_invariants.py`; 20-run determinism loop |
| 2 | SQLite persistence, full API contracts, import, JSON manifest, replay | **PASSED** | `test_persistence.py`, `test_api_contracts.py`, `test_api_integration.py`, `test_contracts_generation.py`; restart replay reproduces the same semantic hash |
| 3 | Real accessible UI journeys, offline E2E | **PASSED** | 82 vitest tests (geometry, client, presentation, components); 25 Playwright tests incl. the full demo journey; screenshots in `var/screenshots/`; axe clean on the three primary views |
| 4 | Multi-phase timeline, branching | **PASSED** | 301 backend / 114 frontend / 43 Playwright tests; `scripts/verify.ps1` exit 0; phase reads, continuity matrix, branch explorer; `e59ca27`, `1bc66a7`, `50168c8` |
| 5 | Fix This Plan bounded optimisation | **PASSED** | Engine, library, API, promotion, studio, baselines and E2E-G5-01..G5-25 verified; `scripts\verify.ps1` exit 0 (`var/verify-gate5-final.log`); see sections 5e-5f |
| 6 | Evidence queue, Failure Lab, PDF packet | **PASSED** | 511 backend / 127 frontend / 99 Playwright tests (all passing); scripts\verify.ps1 exit 0 (ar/verify-gate6-final.log); PDF review packet generated and SHA-256 digest verified (ar/verify-gate6-packet.pdf); see sections 5g-5h |
| 7 | Polish, CI, benchmarks/baselines, audit | NOT STARTED | — |

R0 = gates 0–3. R1 = gates 4–7. R2 stays out of scope.

## 4. Gate 0 checklist — COMPLETE

- [x] Repository at owner-approved path; no sibling project modified
- [x] Git initialised; scoped local attribution; global identity untouched
- [x] Apache-2.0 `LICENSE` from canonical upstream text (owner decision)
- [x] `MASTER_PROMPT.md` + `DETOUR_LAB_Final_PRD.md` read in full and copied into repo root
- [x] Environment inventory from real commands
- [x] venv created; pinned dependencies installed from a real resolver run
- [x] `DECISIONS.md`, `FLOW.md`, `docs/REQUIREMENTS_TRACEABILITY.md`,
      `docs/ASSUMPTIONS_AND_LIMITATIONS.md`, `docs/RESEARCH_AND_SOURCES.md`,
      `docs/TEST_PLAN.md`, `docs/ENGINEERING_POSTMORTEMS.md`, `README.md`
- [x] Real backend imports resolve; no pseudo-modules
- [x] API boots under uvicorn and answers real HTTP requests
- [x] Synthetic, explicitly labelled seed dataset loads through the real importer
- [x] `scripts/setup.ps1` + `scripts/verify.ps1` run successfully on this machine
- [x] ruff clean, 202 tests green
- [x] Git commit of the Gate 0/1 baseline (`23cd2a2`, verified author/committer)

## 5. Gate 1 checklist — COMPLETE

- [x] Immutable directed graph with explicit node connectivity and content addressing
- [x] CRS/length/unit validation, exact mm widths, recorded conversions
- [x] Evidence conflict and missing-state handling (`NO_EVIDENCE`, `CONFLICTING_EVIDENCE`,
      `UNSUPPORTED_UNIT`, `EVIDENCE_EXPIRED`, `EVIDENCE_NOT_VERIFIED`)
- [x] Safe declarative rulepack `DEMO_RULEPACK_NOT_LEGAL` (JSON data, no executable rules)
- [x] Two independent synthetic mobility profiles
- [x] Four-state rule engine; FAIL-before-UNKNOWN; N/A never used as an escape hatch
- [x] Phase-specific immutable graph builder with dependency-ordered edits
- [x] Confirmed / possible feasibility graphs (possible never rescues a known FAIL)
- [x] Exact edge-ID routing with documented lexicographic tie-break
- [x] Canonical semantic hashing + 20-run determinism
- [x] Findings carry edge/node, rule, inputs, evidence IDs, reason codes
- [x] INV-01..INV-08 each asserted by a named test class

## 5b. Gate 2 checklist — COMPLETE

- [x] SQLite schema with numbered migrations, foreign keys and transactional writes
- [x] Atomic dataset import: a rejected file leaves zero rows
- [x] Immutable graph versions, scenarios and per-edit revisions, all content-addressed
- [x] Optimistic concurrency on `PATCH /scenarios/{id}` returning 409 with both revisions
- [x] Edits validated against a prospective scenario *before* anything is stored
- [x] Deterministic evaluation stored with input hash, semantic hash and duration
- [x] Canonical JSON manifest with the runtime block excluded from the semantic hash
- [x] One flat error envelope (`code`, `message`, `details`, `request_id`) for every failure
- [x] Restart persistence proven by a second application process over the same file
- [x] TypeScript contracts generated from the Pydantic models, byte-identical on re-run

## 5c. Gate 3 checklist — COMPLETE

- [x] `apps/web` scaffolded (React 19 + Vite 8 + TypeScript strict), no basemap dependency
- [x] Typed API client over the generated contracts, flat error envelope, abort, timeout,
      boundary shape validation
- [x] Three read endpoints added first so a client can load a scenario, list scenarios and list
      runs (D-016, 11 backend tests)
- [x] Offline SVG renderer: local-planar metres only, edge-ID selection, crossings rendered as
      explicit non-connections, zoom/pan/reset
- [x] Keyboard-operable entity table with the same power as the canvas; skip link; focus management
- [x] Scenario editor: stage → apply through `PATCH`, optimistic concurrency, 409 surfaced without
      overwriting newer work, discard, reopen via branch (D-018)
- [x] Analysis workspace: profile/phase/instant, run identity, confirmed vs possible kept distinct,
      findings table, stale-result banner
- [x] Before/after comparison computed from two stored runs, not recomputed in the browser
- [x] Evidence centre: each unresolved attribute grouped by its specific evidence condition
- [x] Manifest fetched from the backend and downloaded verbatim; never re-serialised client-side
- [x] 82 vitest tests, 25 Playwright tests, 282 backend tests, ruff + eslint + tsc + build clean
- [x] Verified in a real browser: demo journey passes with zero console errors, page errors and
      failed requests; screenshots captured under `var/screenshots/`
- [x] Five genuine defects found and fixed, recorded as P-14..P-18

## 5d. Gate 4 checklist - COMPLETE

- [x] Phase model audited and documented **before** writing code: `docs/PHASE_MODEL_AUDIT.md`
- [x] `Scenario.ordered_phases()` makes `Phase.order` the single ordering authority
- [x] `GET /scenarios/{id}/timeline` - ordered phases, declared modifications, phase-graph identity,
      per-phase analysis state (`analysed` / `NOT_ANALYSED` / `stale`)
- [x] `GET /scenarios/{id}/phases/{phase_id}/graph` - authoritative materialised phase graph, so the
      browser never reconstructs closures
- [x] Construction phase explorer: phase rail, previous/next, keyboard selection, details, loading,
      error and empty states
- [x] Phase graph rendered with the existing `GraphCanvas` (reused, not duplicated)
- [x] Evaluate-all-phases orchestration keyed by phase id, `Promise.allSettled`, partial failure
      reported, no global success on partial failure
- [x] Transition classification for all nine state pairs plus `not-evaluated`
- [x] Cross-phase continuity matrix (confirmed / interrupted / uncertain / incomplete)
- [x] First problematic phase located by `Phase.order`, explained from real data
- [x] Scenario branching: persisted branch created from the declared plan; source never mutated
- [x] Branch explorer with revision, parent, content hash and phase scorecard
- [x] Contracts regenerated; contract determinism re-verified
- [x] 301 backend tests, 114 frontend tests, 40 Playwright tests, ruff/tsc/eslint/build clean
- [x] Four genuine defects found and fixed (P-19..P-22)

## 5e. Gate 5 working decisions — implemented (Fix This Plan, R1, MASTER_PROMPT §7)

Working decisions for this gate, recorded before coding and now implemented (promoted to
DECISIONS.md as D-026..D-033):

- **One engine, no second mutation path.** A candidate is materialised as a derived in-memory
  `Scenario` (source declared plan + source edits + intervention effects) and verified by the
  unmodified `build_phase_graph` → `run_analysis` pipeline. The optimizer never computes verdicts
  itself.
- **Intervention library is an immutable, versioned data file** (`data/demo/interventions.demo.json`,
  demo-labelled). Interventions gain typed `effect` (edits / temporary_edges / phase_changes) and
  declarative `preconditions`; an effect is validated against `allowed_ops` and `target_element_ids`.
- **Scenario promotion is clone-with-edits** (preserves the source's edits on this path; ordinary
  branch creation intentionally keeps D-025): the new branch copies the *declared plan and the source
  edits*, appends the intervention effects, records `parent_scenario_id`, and is re-verified from its
  persisted state. Atomic; 409 on a stale `expected_source_revision` or an existing branch id;
  preview-vs-persisted hash mismatch is a surfaced internal defect, never silent.
- **Objective is lexicographic and documented** (monetary off by default): no regression of any
  model-confirmed OD pair → no new model-FAIL verdicts → restored OD pairs (all selected profiles,
  then any) → fewer new unknowns → fewer interventions → demo-cost nominal (only when asked and
  labelled) → comparable added distance (routes present on both sides only; a missing route is
  never 0 m) → semantic proposal id. A Pareto (non-dominated) set is computed alongside; it is
  never called a weighted score.
- **Unknown never becomes Pass silently.** Modelled evidence a candidate introduces is listed in
  the response with its provenance class and "requires field verification" framing. Candidates
  whose benefit exists only in the *possible* graph, and candidates that introduce elements whose
  model verdicts are UNKNOWN, are classified `requires_verification`, never certified. Unknown cost
  renders as null + `cost_unknown: true` (the UI shows "Not estimated").
- **Budgets are hard filters on the stated basis**: `nominal` or `conservative_max`; a currency no
  declared cost uses is refused with `400 INVALID_BUDGET_CURRENCY` (no FX), and an unpriced
  candidate is never assumed to fit.
- **Honest search status** (`SolverStatus`): `OPTIMAL_IN_ENUMERATED_DOMAIN` only after complete
  enumeration of the eligible domain; otherwise `FEASIBLE_NOT_PROVEN_OPTIMAL`;
  `NO_FEASIBLE_IN_ENUMERATED_DOMAIN`; `INVALID_INPUT`; `INCOMPLETE_OR_UNKNOWN` (timeout/errors).
  Domain counts, limits, `truncated_by` and the single-phase `scope_note` are echoed in the response.
- **Search runs are persisted** (`optimization_runs`, schema migration 2) with execution id
  (`opt-…`) and semantic hash so replay across a process restart is provable.
- **Single-phase scope is explicit**: the response states that a phase-scoped improvement is not
  whole-project continuity.

Execution order: (1) contracts extensions → (2) optimization package (library/generator/verify/
rank/service/promotion) → (3) library data file → (4) persistence + API routes → (5) backend tests
incl. fixtures A–J and baselines B1–B4 → (6) Optimization Studio (frontend, panels A–G) →
(7) E2E G5-01..G5-25 → (8) docs + full verify + commits.

## 5f. Gate 5 checklist - COMPLETE

- [x] Intervention contracts extended (typed effects, preconditions, phase changes); every effect
      validated against the library entry's `allowed_ops` and declared targets
- [x] `optimization/{model,library,generator,verify,rank,service,promotion}.py` implemented against
      the unmodified analysis pipeline
- [x] Eligibility reasons recorded for disabled / client-excluded / wrong-phase / failed-precondition
      items
- [x] Bounded enumeration with requires-closure expansion, mutual-exclusion blocking and hard
      `max_candidates` / `max_duration_ms` limits
- [x] Every candidate re-verified per profile; regression of a confirmed **or possible** pair and
      any new hard model-FAIL reject
- [x] Introduced UNKNOWNs ⇒ `requires_verification`; unknown cost stays null + `cost_unknown`
      (UI "Not estimated")
- [x] `DETOUR_LAB_LEXICOGRAPHIC_V1` ranking (monetary off by default), tie groups excluding the
      proposal id, 3-axis Pareto frontier
- [x] Honest solver statuses, echoed limits/truncation and single-phase scope note; a truncated
      search never claims optimality
- [x] Budget as hard filter (`nominal` / `conservative_max`); zero budget rejects;
      `INVALID_BUDGET_CURRENCY` with no FX
- [x] Searches persisted in `optimization_runs` (migration 2) with execution id + semantic hash;
      byte-identical replay across a process restart
- [x] Transactional apply-to-branch: preview-hash gate, ordered 409 refusals, post-persist
      re-verification, source revision and content hash untouched
- [x] Optimization Studio panels A-G + workspace navigation; the browser renders only
      server-computed verdicts, deltas and costs
- [x] Baselines B1-B4 measured into `var/optimization-baseline.json`
- [x] Contracts regenerated (union-array fix) with determinism re-checked
- [x] E2E-G5-01..G5-25 green against the real backend
- [x] Three genuine defects found and fixed (P-23, P-24, P-25)
- [x] `scripts\verify.ps1` → **VERIFICATION PASSED** (`var/verify-gate5-final.log`)

## 5g. Gate 6 working decisions — implemented (Evidence Intelligence, Failure Lab, review packet)

Commits `7dce46f`, `790a107`, `56dafbc`, `ecfdda2`. Full rationale in `DECISIONS.md` D-034..D-044;
design in `docs/FAILURE_LAB_DESIGN.md` and `docs/REPORTING_DESIGN.md`.

- The evidence queue is **derived** from `resolve_attribute` and carries an explainable category,
  never a numeric score (D-034). An unresolved attribute is not a physical defect.
- A queue issue keeps one `issue_id` across scopes; scope is payload, not identity (D-035).
- Faults are typed bounded data with **no expression field on the contract** — nothing here executes
  anything a user wrote (D-036).
- `SUITES` is nine authored entries; `UNSUPPORTED_SCENARIOS` names three deliberately unmodelled
  conditions. Readiness is **per selected phase**; inapplicable is never shown as passing (D-037).
- Multi-phase, profile-specific and candidate-stress behaviours are **natural divergence** from real
  machinery, not per-kind special cases (D-038).
- `ExperimentStatus` (software) is separate from `EngineeringObservation` (modelled). Only completed
  experiments contribute to robustness counts (D-039).
- Robustness ratios carry a runtime-built denominator and are explicitly **not** probabilities (D-040).
- No new PDF dependency: ReportLab 5.0.1 was already pinned. Split
  `report → layout → pdf → service`, one way, no business logic in `layout.py` (D-041).
- `report_id` is excluded from the semantic payload; two packets of the same data share a hash (D-042).
- The download endpoint re-renders from the stored payload and verifies the digest (D-043).
- An unselected section is marked unavailable with a reason, never rendered empty (D-044).

## 5h. Gate 6 checklist — COMPLETE (VERIFIED)

- [x] Derived evidence queue, five resolver statuses reproduced exactly
- [x] Deterministic explained ordering, no numeric priority score
- [x] Nine authored fault suites + three declared unmodelled conditions
- [x] Typed, bounded, validated faults; no code from a fault definition
- [x] Isolated execution; source scenario, evidence and analyses untouched
- [x] Execution status separated from engineering observation
- [x] Robustness comparison with runtime denominators; no probability claimed
- [x] Deterministic semantic hashes; replay reproduces exactly
- [x] Genuine parseable 12-section PDF; canonical JSON manifest
- [x] Unknowns, units, possible-only and synthetic disclosures preserved
- [x] No invented cost, reviewer, approval or certification
- [x] Backend: 138 new test functions executed and passed (511 total backend tests passing in 155s)
- [x] P-33 regression guard verified (`test_issue_identity_survives_a_scope_change`,
      `test_issue_identity_is_independent_of_the_analysis_execution`,
      `test_distinct_evidence_states_do_not_collapse_into_one_issue_identity`)
- [x] P-34 coverage verified: six suite-readiness tests executed and passed
- [x] P-35 coverage verified: nav hint contrast measured in rendered page (9.49:1 idle, 7.31:1 hover, 6.27:1 active)
- [x] P-40 verified: duplicate scenario id returns 409 SCENARIO_ID_EXISTS with schema-compliant envelope
- [x] E2E-G6-08 cross-checks backend catalogue, verified green
- [x] Gate 6 benchmark step in scriptserify.ps1 with JSON serialization guards verified
- [x] Renamed pps/web/e2e/gate6-a11y-probe.spec.ts → gate6-contrast.spec.ts, verified 1/1 passing
- [x] Full Playwright suite executed and passed: 99 tests passing across 10 spec files in 13.1m
- [x] scriptserify.ps1 executed and verified green
- [x] Uncommitted Gate 6 work tracked, staged, and verified for commit as PrathamKapoor

## 6. Next exact actions (resume here - after Gate 6 implementation)

Gate 6 is **implemented**; verification is outstanding. Gate 7 must not begin until Gate 6 has an
actual green run recorded in section 3.

1. Owner decisions still open (do not resolve in code):
   - **O-1** GitHub remote/push permission (publication stays local until approved);
   - **O-2** real study area and map-data rights;
   - **O-3** jurisdictionally reviewed rulepack;
   - **O-4** named accessibility / domain reviewers;
   - **O-5** verified construction unit prices.
2. **Re-verify before anything else.** The uncommitted post-`ecfdda2` changes have never been run:
   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify.ps1
   ```
   Expect unproven behaviour around `issue_id` identity (P-33), per-phase suite readiness (P-34), the
   nav-hint contrast change (P-35) and the 13 rewritten E2E journeys.
   `docs/FAILURE_LAB_DESIGN.md` §I lists the exact tests owed per change.

2a. **Cleanup that needs a shell** (this session had no file-deletion or git capability):
   ```powershell
   # The obsolete probe now holds a real contrast regression test; give it a
   # matching filename. Use Move-Item: the file is untracked, so `git mv`
   # refuses it ("not under version control").
   Move-Item apps/web/e2e/gate6-a11y-probe.spec.ts apps/web/e2e/gate6-contrast.spec.ts

   # Stage the files that were never committed, or the Gate 6 browser coverage
   # and both design records are lost.
   git add apps/web/e2e/gate6-contrast.spec.ts `
           apps/web/e2e/gate6-evidence-failure-report.spec.ts `
           docs/FAILURE_LAB_DESIGN.md docs/REPORTING_DESIGN.md

   git add -A   # then inspect: git status --short
   git commit -m "..."
   ```
   `.git/config` already carries the required local identity, so no `-c` override is
   needed. There is no global gitconfig on this machine and no remote is configured.
3. Re-read `docs/FAILURE_LAB_DESIGN.md` and `docs/REPORTING_DESIGN.md` before changing the queue, the
   failure engine or the reporting modules; their guarantees have named tests that must not be
   weakened to make new behaviour pass.
4. Re-read `docs/OPTIMIZATION_DESIGN.md` before changing the optimisation engine (Gate 5 guarantees).
5. Gate 7 scope, once Gate 6 is green: polish, CI, measured p50/p95 latency and the B-5
   first-listed-ordering benchmark.

## 7. Recovery / resumption rules

- Never trust a summary of previous work; re-run `scripts/verify.ps1` before editing code.
- A checkpoint summary of unverified work is not evidence. `docs/FAILURE_LAB_DESIGN.md` §I exists
  because a Gate 6 handoff recorded "4.33:1 → AA" as evidence the nav-hint contrast fix had passed,
  when 4.33:1 was the **failing** pre-fix ratio and 7.31:1 was the passing one.
- If a step fails three times, stop, inspect state, reproduce minimally, and record the root cause
  in `docs/ENGINEERING_POSTMORTEMS.md` (genuine findings only).
- Gate N+1 may not start until Gate N has actual passing output recorded here.
- Missing field data stays `UNKNOWN`. The demo rulepack never becomes a legal standard.
