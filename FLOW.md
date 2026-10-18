# FLOW.md — DETOUR LAB execution flow and checkpoint

Last updated: **18 October 2026**, after **Gate 4** completed and verified.
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
| Backend tests | **301 passed** (`python -m pytest apps/api/tests`), ~17 s |
| Static analysis | `ruff check apps/api` → **All checks passed** |
| Contracts | `packages/contracts/{openapi.json,types.ts,domain-schema.json}` generated from Pydantic; byte-identical on re-run |
| Live API | uvicorn on `127.0.0.1:8077`; health, graph, evaluate, manifest and restart checks all exercised |
| One-command verify | `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify.ps1` -> **VERIFICATION PASSED**: ruff, 301 backend tests, tsc, eslint, 114 frontend tests, production build, 40 Playwright tests, live HTTP smoke, restart replay, contract determinism |
| Frontend stack | React 19.3.1, Vite 8.3.4, TypeScript 5.9.3, Vitest 5.0.5, Playwright 1.64.1, ESLint 9.39.5 (pinned in `apps/web/package.json`) |
| Frontend bundle | `index.js` ~305 kB (~91 kB gzip), `index.css` ~23 kB (~5 kB gzip) |
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
| 4 | Multi-phase timeline, branching | NOT STARTED | — |
| 5 | Fix This Plan bounded optimisation | NOT STARTED | — |
| 6 | Evidence queue, Failure Lab, PDF packet | NOT STARTED | — |
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

## 6. Next exact actions (resume here - Gate 5)

1. Re-run `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify.ps1` before anything.
2. Read `MASTER_PROMPT.md` gate-5 section and `prompts/06_GATE_5.md` in full.
3. Reuse what Gate 4 already provides: the phase timeline, the per-phase phase-graph endpoint, the
   branch mechanism and the scorecard. Do not add a second concept of a "phase graph".
4. Optimisation must enumerate candidate interventions **against a phase graph** and re-run the
   real engine for each candidate - never estimate feasibility in the browser.
5. Costs stay demonstration-only (`CostProvenance.DEMO_ONLY`); do not introduce monetary figures.
6. Every candidate result is a new persisted branch or revision, never an in-place overwrite.
7. Extend `e2e/` with a Gate 5 journey using `useIsolatedScenario`-style isolation.
## 7. Recovery / resumption rules

- Never trust a summary of previous work; re-run `scripts/verify.ps1` before editing code.
- If a step fails three times, stop, inspect state, reproduce minimally, and record the root cause
  in `docs/ENGINEERING_POSTMORTEMS.md` (genuine findings only).
- Gate N+1 may not start until Gate N has actual passing output recorded here.
- Missing field data stays `UNKNOWN`. The demo rulepack never becomes a legal standard.
