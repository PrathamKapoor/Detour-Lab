# DETOUR LAB

Pre-construction pedestrian detour **decision support and model verification**.

A planner loads a pedestrian network, edits a proposed closure, picks a construction phase and a
mobility profile, and sees which previously reachable destinations become unconfirmed or
unreachable — with the exact rule, evidence and units behind every verdict.

> **This is a planning visualisation and model-verification prototype.**
> Verdicts read *Pass in modeled checks*, *Fail*, *Unknown* or *Not applicable*.
> They are **not** legal compliance, professional approval, or a statement that anyone can
> physically travel a route. The bundled dataset and rulepack are **synthetic** and the rulepack
> is labelled `DEMO_RULEPACK_NOT_LEGAL` with `legal_applicability = unverified`.

---

## Status (honest)

| Gate | Scope | Status |
|---|---|---|
| 0 | Evidence, repository, docs, dependency-verified skeleton, boot + smoke test | **PASSED** — see `FLOW.md` |
| 1 | Deterministic domain: immutable graph, evidence resolution, four-valued rules, confirmed/possible routing, canonical hashing | **PASSED** |
| 2 | SQLite persistence, full API contracts, atomic import, JSON manifest, replay | **PASSED** — 282 backend tests |
| 3 | Real accessible web UI, offline end-to-end journey | **PASSED** — 114 frontend tests, Playwright suite |
| 4 | Construction phase intelligence: timeline, phase graphs, temporal analysis, branching | **PASSED** |
| 5 | Fix This Plan: bounded candidate search, re-verification, honest ranking, transactional apply-to-branch | **PASSED** — 373 backend tests, 127 frontend tests, 68 Playwright tests |
| 6 | Evidence Intelligence queue, adversarial Failure Lab, audit-ready PDF review packet | **PASSED** — 511 backend tests, 127 frontend tests, 99 Playwright tests (all passing); scripts\verify.ps1 exit code 0 (ar/verify-gate6-final.log); see FLOW.md |
| 7 | Polish, CI, measured benchmarks/baselines, audit | NOT STARTED |
| R2 | Photo measurement, multi-jurisdiction packs, RBAC, scale | OUT OF SCOPE |

Nothing above is a claim about field accuracy. Current results come from a **synthetic** fixture.

Gate 6 adds: a **derived** evidence-verification queue (the resolver's five conditions reproduced
exactly, an explainable category instead of a numeric score), nine **authored** fault suites executed
against an **isolated** copy of the scenario through the unmodified analysis pipeline, a robustness
comparison whose denominators are stated and which is explicitly **not** a probability, and a genuine
12-section PDF packet with a canonical JSON manifest. Design: `docs/FAILURE_LAB_DESIGN.md`,
`docs/REPORTING_DESIGN.md`. Decisions: `DECISIONS.md` D-034..D-044.

## Prerequisites

- Python 3.12 (`python --version`)
- Node.js 20+ and npm (`node --version`, `npm --version`)
- Network access to PyPI/npm for the first install only

No API keys, no cloud services, no basemap subscription, no remote geocoding.

## Install

```powershell
pwsh -File scripts\setup.ps1          # Windows PowerShell 5.1: powershell -NoProfile -File scripts\setup.ps1
bash scripts/setup.sh                 # macOS / Linux
```

`scripts/setup.ps1` also installs the frontend dependencies (`apps/web`) and, once, the Chromium
runtime used by the end-to-end tests.

## Verify (one command, prints real output)

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify.ps1
```

Runs, in order: ruff, the backend pytest suite, frontend type-check, eslint, vitest, the production
Vite build, Playwright end-to-end tests against a real backend, a live HTTP smoke test that asserts
two identical evaluations are byte-identical, a restart-persistence check, and contract-generation
determinism.

Useful switches: `-SkipFrontend` (prints `SKIPPED: frontend checks`, never a pass), `-SkipE2E`,
`-Port <n>`.

## Run the API

```powershell
$env:PYTHONPATH = "$PWD\apps\api"
.\.venv\Scripts\python.exe -m uvicorn detour_lab.api.main:app --app-dir apps\api --port 8077
```

## Run the application (API + web UI)

Two terminals. The backend must be running first; the UI proxies `/api` to it.

```powershell
# Terminal 1 — API on http://127.0.0.1:8077
$env:PYTHONPATH = "$PWD\apps\api"
.\.venv\Scripts\python.exe -m uvicorn detour_lab.api.main:app --app-dir apps\api --port 8077

# Terminal 2 — planning studio on http://127.0.0.1:5173
cd apps\web
npm install          # once
npm run dev
```

Open <http://127.0.0.1:5173>. No tiles, geocoding or third-party services are contacted; the study
area is rendered from API geometry in local planar metres.

To point the UI at a different backend port:

```powershell
$env:DETOUR_LAB_API_URL = "http://127.0.0.1:9000"; npm run dev
```

## Demo walkthrough (about two minutes)

1. **Projects** — the seeded `demo-project-synthetic` is flagged *Synthetic demo data*. Open it.
2. **Network** — the graph renders from `GET /api/v1/projects/{id}/graph`. Select `E_K1` in the
   *Entity table* tab (keyboard works) and read its attributes, its evidence records and the
   modeled state. The dashed ring marks a geometric crossing that is **not** a connection.
3. **Analysis** — choose profile A / phase 1 and press *Run analysis*. Reachability appears with
   *Model-confirmed*, *Possible only* and *No route* kept distinct, plus run id, semantic hash,
   rulepack version and counts.
4. **Compare** — press *Use as baseline*.
5. **Scenario** — back in *Network*, select `E_WM`, then in *Scenario* press
   *Close selected edge*, then *Apply 1 edit*. The revision advances to 2 after the backend
   confirms it.
6. **Analysis** again — the closure shows up as *lost* confirmed connections in *Compare*.
7. **Evidence** — inspect the unresolved attributes and exactly why each is unresolved.
8. **Reports** — the canonical manifest fetched from `GET /api/v1/runs/{id}/manifest`, downloadable
   as JSON.
9. Reload the page: the saved closure is still there, because it was persisted server-side.

The whole journey is executed automatically by `npm run e2e` (see `e2e/demo-journey.spec.ts`),
which also fails on any console error and writes screenshots to `var/screenshots/`.


## Construction phase walkthrough (Gate 4)

1. Open the seeded project and choose **Phases** in the sidebar.
2. The phase rail lists the scenario's phases in authoritative `Phase.order`. The seeded demo has
   two: *Phase 1 - main footway resurfacing* and *Phase 2 - east link reconstruction*. It is an
   ordered sequence, not a calendar - the application never invents construction dates.
3. Select a phase. The **phase graph** is served by
   `GET /api/v1/scenarios/{id}/phases/{phase_id}/graph` and shows that phase's closures and temporary
   connections. Closed edges stay visible so their position stays legible, but they are excluded
   from routing.
4. Press **Evaluate all phases**. Each phase gets its own stored run, identified by phase id.
5. The **continuity matrix** shows, per origin-destination pair and per phase, whether the
   connection is model-confirmed, possible-only, has no route, or was not analysed.
6. **Temporal findings** names the first problematic phase in order and explains it from the
   stored results and the edges whose active state changed between those two phases.
7. Choose **Branches**, create an alternative plan, and open either scenario. The branch is a
   separate persisted scenario; editing it never changes the source.

For the seeded demo, phase 2 opens the temporary east bypass and yet `OD-E → OD-LIB` stays
*possible-only*, because the unresolved curb evidence at `N_EK` is not resolved by the bypass. The
application reports that rather than implying the bypass improved the outcome.
## Endpoints (synthetic seeded dataset, persisted in `var/detour_lab.sqlite3`)

| Method + path | Purpose |
|---|---|
| `GET /api/v1/health` | Engine/rulepack identity, schema version, row counts |
| `GET /api/v1/projects` · `POST /api/v1/projects` | List / create projects |
| `POST /api/v1/projects/{id}/imports` | Validate and ingest a dataset atomically |
| `GET /api/v1/projects/{id}/graph` | Graph version, basis, directed edges, evidence, unlinked crossings |
| `POST /api/v1/projects/{id}/scenarios` · `GET /api/v1/projects/{id}/scenarios` | Create / list scenarios |
| `GET /api/v1/scenarios/{id}` · `PATCH /api/v1/scenarios/{id}` | Load a scenario / append validated edits (optimistic concurrency) |
| `GET /api/v1/scenarios/{id}/timeline` | Ordered phases (`Phase.order`) with closures, temporary connections, phase-graph hash and analysis state |
| `GET /api/v1/scenarios/{id}/phases/{phase_id}/graph` | The authoritative materialised graph of one phase |
| `GET /api/v1/scenarios/{id}/revisions` · `GET /api/v1/scenarios/{id}/runs` | Immutable revision history / stored runs for a scenario |
| `POST /api/v1/scenarios/{id}/evaluate` | Deterministic evaluation; returns a stored run |
| `GET /api/v1/runs/{id}` · `GET /api/v1/runs/{id}/manifest` | Run result / canonical JSON manifest |
| `GET /api/v1/scenarios/{id}/optimization/interventions` · `GET /api/v1/scenarios/{id}/optimization/searches` | Library eligibility for a phase / stored searches for the scenario |
| `POST /api/v1/scenarios/{id}/optimization/search` | Bounded, deterministic search; every candidate is verified by the analysis engine |
| `GET /api/v1/optimization/searches/{search_id}` · `POST /api/v1/optimization/promote` | Replay a stored search byte-for-byte / apply a verified candidate as a new branch |
| `GET /api/v1/rulesets` | Rulepack (with `legal_applicability`) and the two demo profiles |

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8077/api/v1/scenarios/scn-demo-baseline/evaluate -Method Post `
  -ContentType 'application/json' `
  -Body '{"profile_id":"DEMO_PROFILE_MANUAL_WHEELCHAIR","phase_id":"phase-1","evaluation_instant":"2026-03-01T00:00:00Z"}'
```

Every failure returns the same envelope: `{"code", "message", "details", "request_id"}`
(404 unknown entity, 409 revision conflict, 422 invalid input).

## What the seeded demo shows

`data/demo/synthetic_study_area.localplanar.json` is a **synthetic schematic** in local planar
metres. It is deliberately **not** RFC 7946 GeoJSON and is not a real place.

| Feature | Where |
|---|---|
| Closure active in phase 1 | `E_ME` |
| Closure + temporary footway in phase 2 | `E_ES1` closed, `TMP::TMP-EAST-BYPASS` opens |
| Crossing that passes profile A but fails profile B | `E_K1`/`E_K2`, 1100 mm wide |
| Known unusable curb | `N_BC` records `curb_transition = kerb_upstand` (both profiles fail) |
| Unmeasured element → UNKNOWN | `E_ALT` has a surface but no width or gradient |
| Unresolved curb interface → UNKNOWN | `N_EK` has no `curb_transition` record |
| **Crossing that is *not* a connection** | `E_LINK` crosses `E_K2` geometrically, shares no node |

Observed result for profile A, phase 1 (computed, not hardcoded):

```
OD-W -> OD-GATE: confirmed=True  possible=True  distance_m=58.0
OD-W -> OD-LIB:  confirmed=True  possible=True  distance_m=98.0
OD-E -> OD-GATE: confirmed=False possible=False distance_m=None
OD-E -> OD-LIB:  confirmed=False possible=True  distance_m=None
```

Profile B in the same phase loses both confirmed routes because its width threshold is higher.

## Repository layout

```
DETOUR-LAB/
  apps/api/detour_lab/
    domain/       contracts, units, canonical hashing      (no I/O)
    evidence/     observation resolution
    graph/        immutable directed graph, feasibility graphs, routing
    rules/        declarative engine, DEMO rulepack, demo profiles
    scenarios/    typed edits, phase-graph construction
    analysis/     the only place verdicts are produced
    ingestion/    local-planar + RFC 7946 GeoJSON loaders
    persistence/  SQLite schema, migrations, repository
    reporting/    canonical manifest, contract generation
    api/          FastAPI boundary (versioned routes + error envelope)
  apps/api/tests/ 301 backend tests
  packages/contracts/ generated openapi.json, types.ts, domain-schema.json
  apps/web/
    src/api/       typed client, envelope handling, boundary normalisation
    src/lib/       geometry, formatting, status vocabulary, data-loading hook
    src/components/ design-system primitives (Panel, StatusBadge, Dialog, Tabs, fields)
    src/features/  projects, network (SVG studio + inspector + entity table), scenario,
                   analysis, comparison, evidence centre, reports
    e2e/           Playwright journeys against the real backend
  data/demo/      synthetic seeded dataset
  docs/           traceability, test plan, postmortems, assumptions
  scripts/        setup + verify (PowerShell and shell)
  DECISIONS.md    why each choice was made
  FLOW.md         resume point and gate status
```

## Frontend tests

```powershell
cd apps\web
npm run typecheck     # tsc, strict + noUncheckedIndexedAccess + exactOptionalPropertyTypes
npm run lint          # eslint
npm run test          # vitest: geometry, API client, presentation, components
npm run build         # production bundle
npm run e2e           # Playwright: real backend, real browser, fresh database per run
npm run e2e:install   # one-off Chromium download
```

## Safety properties (all enforced by tests)

- **Unknown never becomes Pass** — missing, conflicting, unsupported or expired evidence yields UNKNOWN.
- **Crossing is not connectivity** — edges connect only through shared node IDs.
- **Closed edges are never routed** — and closures are part of the graph version's content hash.
- **Preferences cannot override hard constraints** — they only change ranking cost.
- **Units are exact or rejected** — widths are integer millimetres; conversions are recorded.
- **Baseline graphs are immutable** — every scenario produces a new content-addressed version.
- **No "approved"/"compliant" language** — asserted against every verdict explanation.

## Known limitations

See `docs/ASSUMPTIONS_AND_LIMITATIONS.md`. The most important ones: no real jurisdiction is encoded,
no field survey exists, there is no basemap by design, and no external accessibility or engineering
review has been obtained.

Frontend-specific, stated plainly:

- The graph canvas is one visualisation of the data; the entity table and every inspector are
  equivalent controls. No action exists only on the canvas.
- Reopening a closure creates an immutable branch scenario rather than editing the closure out
  (`DECISIONS.md` D-018).
- Measurements can only be entered for attributes the demonstration rulepack evaluates; the
  attribute list is not user-extensible in R0.
- Automated accessibility checks (axe) report findings, not conformance; no manual audit with
  assistive technologies has been performed.
- The 3D/photogrammetry features of Gates 4–7 do not exist yet and are not represented in the
  interface. Fix This Plan searches a bundled synthetic intervention library only: it does not
  estimate real prices, construction schedules or constructibility, and its costs are demo figures
  that never drive ranking unless explicitly enabled.

## Licence

Apache License 2.0 — see `LICENSE`. Third-party licences are listed in
`docs/RESEARCH_AND_SOURCES.md`.