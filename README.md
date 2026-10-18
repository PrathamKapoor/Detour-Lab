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
| 2 | SQLite persistence, full API contracts, atomic import, JSON manifest, replay | **PASSED** — 270 backend tests |
| 3 | Real accessible web UI, offline end-to-end journey | NOT STARTED |
| 4–7 | Phase timeline, Fix This Plan, Failure Lab, PDF packet, audit | NOT STARTED |
| R2 | Photo measurement, multi-jurisdiction packs, RBAC, scale | OUT OF SCOPE |

Nothing above is a claim about field accuracy. Current results come from a **synthetic** fixture.

## Prerequisites

- Python 3.12 (`python --version`)
- Node.js 20+ and npm (needed from Gate 3 onward)
- Network access to PyPI/npm for the first install only

No API keys, no cloud services, no basemap subscription, no remote geocoding.

## Install

```powershell
pwsh -File scripts\setup.ps1          # Windows PowerShell 5.1: powershell -NoProfile -File scripts\setup.ps1
bash scripts/setup.sh                 # macOS / Linux
```

## Verify (one command, prints real output)

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify.ps1 -SkipFrontend
```

This runs static analysis, the full pytest suite, starts a real `uvicorn` process, hits
`/api/v1/health` and the evaluation endpoint over HTTP, prints the computed OD matrix, and asserts
that two identical HTTP evaluations return byte-identical payloads.

## Run the API

```powershell
$env:PYTHONPATH = "$PWD\apps\api"
.\.venv\Scripts\python.exe -m uvicorn detour_lab.api.main:app --app-dir apps\api --port 8077
```

Useful endpoints (synthetic seeded dataset, persisted in `var/detour_lab.sqlite3`):

| Method + path | Purpose |
|---|---|
| `GET /api/v1/health` | Engine/rulepack identity, schema version, row counts |
| `GET /api/v1/projects` · `POST /api/v1/projects` | List / create projects |
| `POST /api/v1/projects/{id}/imports` | Validate and ingest a dataset atomically |
| `GET /api/v1/projects/{id}/graph` | Graph version, basis, directed edges, evidence, unlinked crossings |
| `POST /api/v1/projects/{id}/scenarios` · `PATCH /api/v1/scenarios/{id}` | Create a scenario / append validated edits (optimistic concurrency) |
| `GET /api/v1/scenarios/{id}/revisions` | Immutable revision history with content hashes |
| `POST /api/v1/scenarios/{id}/evaluate` | Deterministic evaluation; returns a stored run |
| `GET /api/v1/runs/{id}` · `GET /api/v1/runs/{id}/manifest` | Run result / canonical JSON manifest |
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
  apps/api/tests/ 270 backend tests
  packages/contracts/ generated openapi.json, types.ts, domain-schema.json
  apps/web/       (Gate 3) React + TypeScript + Vite
  data/demo/      synthetic seeded dataset
  docs/           traceability, test plan, postmortems, assumptions
  scripts/        setup + verify (PowerShell and shell)
  DECISIONS.md    why each choice was made
  FLOW.md         resume point and gate status
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

## Licence

Apache License 2.0 — see `LICENSE`. Third-party licences are listed in
`docs/RESEARCH_AND_SOURCES.md`.