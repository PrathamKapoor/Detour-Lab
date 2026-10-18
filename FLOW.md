# FLOW.md — DETOUR LAB execution flow and checkpoint

Last updated: **18 October 2026**, after **Gate 1** completed and verified.
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
| Backend tests | **202 passed** (`python -m pytest apps/api/tests`), ~6.6 s |
| Static analysis | `ruff check apps/api` → **All checks passed** |
| Live API | uvicorn on `127.0.0.1:8077`; `GET /api/v1/health` returned `ok`; evaluation endpoint returned computed results |
| One-command verify | `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify.ps1 -SkipFrontend` → **VERIFICATION PASSED**, including a byte-identical HTTP replay |
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
| 2 | SQLite persistence, full API contracts, import, JSON manifest, replay | NOT STARTED | — |
| 3 | Real accessible UI journeys, offline E2E | NOT STARTED | — |
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
- [ ] Git commit of the Gate 0/1 baseline (**next action**)

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

## 6. Next exact actions (resume here — Gate 2)

1. `git add -A && git commit` the Gate 0/1 baseline; verify
   `git log -1 --format=fuller` shows `PrathamKapoor <prathamkapoor027@gmail.com>`.
2. SQLite persistence layer `detour_lab/persistence/`:
   migrations, transactional writes, foreign keys, canonical payload storage.
3. Full API contract surface from PRD §10.2:
   `POST /projects`, `POST /projects/{id}/imports`, `POST /scenarios`, `PATCH /scenarios/{id}`
   (optimistic concurrency), `POST /scenarios/{id}/evaluate`, `GET /runs/{id}`.
4. Canonical JSON manifest builder `detour_lab/reporting/manifest.py` (FR-016, INV-06).
5. Integration tests: atomic import rollback, restart persistence, replay hash equality.
6. Generate the TypeScript client contracts into `packages/contracts`.
7. Update `docs/REQUIREMENTS_TRACEABILITY.md` and commit per logical change.

## 7. Recovery / resumption rules

- Never trust a summary of previous work; re-run `scripts/verify.ps1` before editing code.
- If a step fails three times, stop, inspect state, reproduce minimally, and record the root cause
  in `docs/ENGINEERING_POSTMORTEMS.md` (genuine findings only).
- Gate N+1 may not start until Gate N has actual passing output recorded here.
- Missing field data stays `UNKNOWN`. The demo rulepack never becomes a legal standard.