# MASTER IMPLEMENTATION PROMPT — DETOUR LAB

> Paste this entire prompt into the coding agent's **initial instruction**. Place `DETOUR_LAB_Final_PRD.md` in the target repository or attach it to the coding session. The agent must treat this prompt as the execution contract and the PRD as the product-requirement baseline. This is an implementation request, not a request to write a plan and stop.

## 0. ROLE, AUTHORIZATION, AND END CONDITION

You are the lead engineer, systems architect, verification engineer, product designer, accessibility-conscious UX engineer, and release manager for **DETOUR LAB**, a pre-construction pedestrian detour planning and model-verification application. Deliver an actual runnable, fully tested product, not mockups, pseudocode, disconnected components, optimistic status messages, or a README describing features that do not exist.

**Project owner / Git attribution, explicitly authorized by the user:**
- Git author name: `PrathamKapoor`
- Git author email: `prathamkapoor027@gmail.com`
- Git committer name and email for commits you create: the same values.
- Product name: `DETOUR LAB`.

Use repository-local Git configuration (`git config --local user.name ...` and `git config --local user.email ...`) if repository context and permission exist, or per-command `git -c user.name=PrathamKapoor -c user.email=prathamkapoor027@gmail.com commit ...`. Do not change global Git identity. Do not impersonate a different existing commit author, rewrite Git history, force-push, overwrite others' work, or claim an external push/deployment occurred without verifying it. Do not add AI-assistant coauthor trailers unless the owner specifically requests them. Preserve third-party copyright notices and licenses. Setting requested Git attribution does not transfer ownership of external code.

**Quality bar:** An exceptionally polished, technically defensible hackathon demonstration, backed by production-minded boundaries, reproducible calculations, a serious automated test suite, meaningful accessibility behavior, error handling, and transparent limitations. The only permitted stopping condition for claiming completion is that the actual acceptance gates pass; token use, convenience, or visual polish alone are not substitutes. If tools, permissions, unavailable input data, or environment restrictions block completion, report the exact blocker and the verified partial implementation without pretending it is finished.

**No unverified assumptions:** Do not invent a city, project location, measured widths, ramps, survey observations, legal compliance thresholds, construction costs, disability requirements, map licenses, Git remote, existing framework, secrets, deployment credentials, third-party terms, or user decisions. There IS permission to make ordinary reversible engineering implementation choices where product behavior is already specified: examine evidence and official docs; choose the smallest reliable option; record the reasoning and consequences in `DECISIONS.md`; do not silently introduce fabricated factual inputs. For truly blocking user decisions, create a concise `BLOCKERS.md` entry and request only the indispensable information. Otherwise continue useful work using explicitly labeled synthetic fixtures or documented defaults, without misrepresenting them as real-world observations or statutory standards.

## 1. READ, RECONCILE, AND LOCK THE SPECIFICATION

Before editing code:
1. Discover the actual working directory, repository, branch, uncommitted changes, runtime versions, available tools, build scripts, existing tests, network constraints, and whether `DETOUR_LAB_Final_PRD.md` is accessible. Never overwrite an existing repository blindly.
2. Read the **entire** PRD, especially FR-001 through FR-016; FR-101 through FR-111; eight invariants INV-01 through INV-08; domain entities; API outline; and release criteria. The PRD is more authoritative about **product scope** than any tempting framework demo. This prompt is more detailed about **execution and quality assurance**. For any actual conflict, document both and resolve using the conservative/safety-preserving interpretation; ask the owner if the conflict cannot be resolved without inventing requirements.
3. Audit the repository before choosing packages. If no code exists, scaffold a maintainable monorepo as described below. If code exists, integrate with what is already stable rather than replacing it simply because you prefer another stack.
4. Read official, current documentation for exact package versions, APIs, licenses and platform compatibility before installing or using packages. Pin resolved compatible dependencies and commit lockfiles. Never paste code using non-existent methods or invented CLI flags.
5. Create `docs/REQUIREMENTS_TRACEABILITY.md`: one line per PRD feature/invariant with requirement ID, implemented modules, validation tests, status and notes. Start all incomplete; update only when tested.
6. Create `DECISIONS.md`, `FLOW.md`, `docs/ASSUMPTIONS_AND_LIMITATIONS.md`, `docs/TEST_PLAN.md`, and `docs/RESEARCH_AND_SOURCES.md`. These documents MUST stay aligned with the code. Record explicit owner input separately from synthetic fixture defaults and reversible technology decisions.
7. Make a baseline commit only when appropriate and authorized, and avoid touching unrelated uncommitted files. Check `git status` at every critical milestone.

**Don't waste time recreating the PRD. Implement against it.** If it is not attached, proceed with the full requirements spelled out in this prompt, flag that authoritative PRD reconciliation is pending, and do not pretend to have read an absent file.

## 2. WHAT THE PRODUCT IS — AND IS NOT

**User story:** A civil/traffic planner loads a pedestrian network, edits a proposed sidewalk closure, selects a construction phase and a mobility profile, and checks which previously reachable destinations become unconfirmed or unreachable. The planner inspects exact failure/evidence traces and tries explicitly specified alternate arrangements. DETOUR LAB recomputes the graph with each intervention, ranks feasible modeled alternatives using transparent costs and route burden, exposes missing measurements, stress-tests assumptions, and exports an auditable review packet.

**Never claim:** legal compliance certification; regulatory permission; engineering sign-off; safe travel guarantee; complete knowledge of sidewalks from OSM roads; real-world wheelchair suitability based on synthetic data; measurements inferred from a single uncalibrated image; guaranteed optimal layouts when search incomplete; deployed public navigation; real outcomes or benchmark scores before collecting them.

**Authoritative computing boundary:** Graph structure + measurement/evidence resolution + rule evaluation + routing + scenario application + candidate verification are deterministic, validated program logic. LLMs and computer vision MAY help explain or suggest annotations at R2, but may NEVER make the authoritative Pass/Fail/Unknown decision or fabricate physical attributes. R0 and R1 do not require any generative model or API key.

**Release commitment:**
- `R0` first: trustworthy full vertical slice, including editable graph, evidence, profiles, phase-specific closure, four rule states, confirmed vs possible routing, comparisons, JSON replay, accessible UI, offline demo.
- `R1` next: multiple phases, Fix This Plan, bounded optimization with honest solution-status semantics, scenario branching, evidence inspection queue, failure injection, side-by-side comparison and a reproducible PDF packet.
- `R2` is **out of scope for the initial release**: ML photo measurement, multi-jurisdiction certification, public wayfinding, mass crowdsourcing, municipal ERP, roles/approvals, global-scale distributed architecture, unrestricted AI layout generation. Add R2 only if R0/R1 pass and explicitly document changed scope.

## 3. ACCEPTANCE STORY: THE ACTUAL END-TO-END DEMO

Implement this sequence against persisted scenario data; no hardcoded "sample result" may be substituted for engine output:

1. Launch locally, including offline/no-external-service mode, and load a documented demo project with an explicit, valid pedestrian graph. Distinguish all synthetic attributes visibly from verified real-world observations.
2. Display nodes, directed pedestrian edges, crossings, destinations, evidence completeness and source/license metadata on a visually clear, keyboard-accessible interface. The base map may be a schematic geospatial canvas when no permitted/offline tile source is available.
3. Select an edge or draw a closure; the UI must translate the drawing/selection to validated graph-edit operations. Specify the active phase and save to a new scenario revision; baseline graph stays immutable.
4. Choose Profile A and Profile B, both clearly described and explicitly named as demonstration configurations rather than universal disability standards. Run the same deterministic evaluator and see visibly different results for a deliberately designed fixture.
5. Show BEFORE vs AFTER confirmed-reachable pairs, potentially-reachable pairs, lost connections, extra route length when known, known failed edges, critical unknowns, and active rulepack ID/version.
6. Inspect a finding: see exact edge/node ID, rule ID, version, input value and unit or missing/conflicting evidence, source record, phase, profile, applicable reason code, and clear explanation. No unexplained "AI says inaccessible."
7. Click **Fix This Plan**: receive multiple physically bounded candidate interventions with clearly labeled synthetic/demo cost assumptions, prerequisites and alternatives. Show validation status, cost, route burden, profile impact, uncertainty, and solver/exhaustiveness status. Apply one to a *new* scenario branch and rerun the authoritative evaluator.
8. Advance construction phase: show a previously valid connection becoming unavailable, a missing temporary transition, or a different route becoming available. Phase transition results must be computed from the data.
9. Inject a predefined Failure Lab fault (e.g., added obstruction, measurement removed, crossing junction disconnected, slope violation, conflicting measurements); rerun automatically or explicitly and show the changed findings. Reset the injection and reproduce the original outcome.
10. Export canonical JSON manifest and a clear PDF planning-review packet. Reopen/replay the saved run and show that the same canonical data produces matching semantic results and hashes. Label PDF **"Planning analysis — not certified"**.

**The entire path from map editing to exported recommendation must work for real clicks, stored data, error paths and refreshes.** Empty buttons, static charts, route lines hand-drawn independently of evaluation, and silent network calls are not acceptable.

## 4. ARCHITECTURE AND SOURCE REPOSITORY

Recommended baseline when starting from an empty repo (change only after an evidence-based `DECISIONS.md` entry):

```text
DETOUR-LAB/
  README.md
  LICENSE                 # only if owner authorizes a new license; otherwise document pending license
  DECISIONS.md
  FLOW.md
  BLOCKERS.md             # create only when needed
  .env.example            # placeholder names only; NEVER include secrets
  .editorconfig
  .gitignore
  package.json            # workspace/task scripts if applicable
  apps/
    web/                  # React + TypeScript + Vite + MapLibre GL JS
      src/
        app/              # routing, shell, error boundaries, feature navigation
        features/
          projects/
          planning/
          verification/
          optimization/
          evidence/
          failure-lab/
          reports/
        components/        # reusable accessible UI primitives
        api/               # typed client and API error handling
        styles/            # responsive design tokens, typography, contrast
      tests/
    api/                  # FastAPI + Pydantic
      detour_lab/
        api/v1/            # versioned HTTP boundary, error contracts
        domain/            # pure dataclasses/types, invariants, models
        ingestion/         # CRS/GeoJSON validation
        evidence/          # canonical observation resolution
        rules/             # declarative deterministic evaluator
        graph/             # directed connectivity, route algorithms
        scenarios/         # immutable overlays and phases
        optimization/      # bounded candidate enumeration and rankings
        reporting/         # canonical manifests + PDF
        persistence/       # SQLite repository & migrations
      tests/
  packages/
    contracts/            # generated/checked API schemas / TypeScript clients
  data/
    fixtures/             # explicitly synthetic deterministic cases
    demo/                 # licensed/attributed source or plainly synthetic
  docs/
    REQUIREMENTS_TRACEABILITY.md
    ASSUMPTIONS_AND_LIMITATIONS.md
    RESEARCH_AND_SOURCES.md
    ARCHITECTURE.md
    DATA_DICTIONARY.md
    API.md
    TEST_PLAN.md
    EVALUATION.md
    SECURITY_AND_PRIVACY.md
    DEMO_SCRIPT.md
    RELEASE_CHECKLIST.md
  scripts/
    setup.*               # clean machine instructions; support Windows PowerShell as practical
    seed.*
    verify.*
  .github/workflows/ci.yml
```

**Separation-of-concerns mandate:** UI never computes its own contradictory route verdict; API orchestration never changes graph mathematics; persistence entities are not substitutes for domain invariants; reports are generated from the canonical results rather than reverse-engineering UI screenshots. Use typed contracts and explicit conversions at module boundaries. Prefer small, testable pure functions for graph, rules and optimization.

**Technology rationale:** React/TypeScript for stateful accessible interfaces; Vite for simple predictable build; MapLibre for vector/GeoJSON geospatial display; FastAPI/Pydantic for typed APIs, validation and OpenAPI; NetworkX for inspectable directed graph algorithms; Shapely/GeoPandas for geometry and projection checks where actually needed; SQLite for portable deterministic local persistence; GeoJSON for explicit geographic exchange; pytest plus hypothesis for invariants; Vitest/Testing Library for UI; Playwright for real browser E2E; Ruff and strict TypeScript for static checks. OR-Tools is optional until finite enumeration is demonstrably insufficient; never introduce Kafka, Redis, Kubernetes or microservices without measured requirements.

**Geographic caution:** RFC 7946 GeoJSON coordinates are WGS 84 longitude/latitude (with documented ordering). NEVER write local Cartesian `x/y` fixture coordinates into an RFC 7946 GeoJSON file and falsely label them valid geospatial coordinates. For the offline schematic, either generate clearly synthetic but correctly formatted lon/lat coordinates and project them for meter-based calculations, OR define a separate explicitly labeled local-planar JSON schema that is NOT claimed to be RFC 7946 GeoJSON. When analyzing meter-based geometric quantities, use a suitable explicitly recorded projected CRS, not Euclidean degree arithmetic. Validate import coordinate basis and transformation metadata instead of silently assigning a CRS. Any graph edits drawn in pixels must be mapped back to and validated against the canonical coordinate system.

**Authoritative implementation references to consult and log in `docs/RESEARCH_AND_SOURCES.md`:**
- PRD: `DETOUR_LAB_Final_PRD.md` (always read full file, not a summary).
- RFC 7946 GeoJSON format: https://www.rfc-editor.org/info/rfc7946/
- NetworkX directed/weighted shortest paths: https://networkx.org/documentation/stable/reference/algorithms/shortest_paths/index.html
- FastAPI response contracts: https://fastapi.tiangolo.com/tutorial/response-model/
- MapLibre GL JS documentation: https://maplibre.org/maplibre-gl-js/docs/
- OR-Tools CP-SAT statuses: https://developers.google.com/optimization/cp/cp_solver
- WCAG 2.2 guideline: https://www.w3.org/TR/WCAG22/
- OSM data attribution and licensing: https://osmfoundation.org/wiki/Licence/Attribution_Guidelines
These URLs establish authoritative starting points, not an excuse to bypass verifying the exact installed version, source license or applicable local regulation. No unspecified jurisdictional regulation is assumed.

**Runtime:** App must run locally with documented commands, pinned versions, no private API keys and a deterministic seed. No base-tile dependency may prevent the graph, map or demo from functioning offline. If using remote tile services in online mode, verify their license/attribution/usage limits and provide a genuine offline fallback. Never embed proprietary maps without rights.

## 5. DOMAIN DATA CONTRACTS — EXPLICIT SEMANTICS

Implement validated Pydantic contracts and matching TypeScript types. The following are REQUIRED conceptually; name refinements are allowed only if documented consistently.

### 5.1 Base network
- `Project`: ID, name, study area/coordinate basis, jurisdiction descriptor **or explicit unspecified**, owner, dataset attribution, created timestamp.
- `BaseGraphVersion`: stable ID, immutable node/edge set, source citation/license, schema version, canonical content hash, ingest timestamp.
- `Node`: stable ID, validated coordinate, node type (`junction`, `crossing_interface`, `curb_interface`, etc.), evidence references where relevant.
- `Edge`: stable ID, `u`, `v`, directed traversability, geometry with endpoints consistent with node coordinates, nonnegative length in meters (measured or explicitly entered with provenance), edge type (`sidewalk`, `crossing`, `temporary_path`, etc.), evidence-linked width/slope/surface/transition attributes. If bidirectional, represent both directions explicitly or use a proven direction-aware representation; do not allow reverse travel by accident.
- `Destination` and `Origin`: stable ID, linked **graph node ID**, human-facing name, priority category, optional weight with source/assumption label. A map coordinate near a footway is not automatically connected.
- `GraphEdit`: typed operations (`add_node`, `split_edge`, `add_edge`, `remove_edge`, `set_direction`, `link_crossing`, `update_attribute`, `close_edge`) with preconditions and immutable audit events.

**Topology invariants:** Shared geometric coordinates alone DO NOT join nodes. Crossing visual intersections must not join edges. Edge endpoints must exist. Duplicate IDs are rejected. An edge cannot silently point outside its graph version. Parallel edges must retain unique IDs. Split-edge behavior preserves provenance/direction and produces explicit deterministic IDs and references. Reject unsupported self-loops/degenerate edges unless a meaningful documented use is implemented. Every geometric edit must run topological validation.

### 5.2 Observation and provenance
- `EvidenceRecord`: ID, element ID, field name, typed value, canonical unit, original value/unit, collection method, source descriptor, observed timestamp **or explicit unknown**, verification status, evidence quality metadata, reviewer when actually present, optional source URL. Never fabricate names/dates.
- `ResolvedAttribute`: selected value OR unknown, explanation, contributing evidence IDs, conflict/staleness indicators and governing freshness policy.
- Multiple contradictory eligible measurements MUST be retained and produce `UNKNOWN` pending review; never silently choose a favorable number.
- Missing field ≠ zero; missing field ≠ Pass. Placeholder data must have explicit `synthetic: true`, documented provenance, and never be shown as independently field-measured.
- Unit conversions must be exact/reproducible at tested precision: width in meters (optionally stored as integer mm for exact comparison), length in meters, gradients expressed in a clearly documented convention (signed longitudinal direction and/or absolute grade percent), timestamps in timezone-aware ISO 8601 UTC with phase-local interpretation documented where applicable. Reject ambiguous units, NaN/Infinity and implausible unvalidated values.
- Evidence can expire only according to an explicit per-attribute freshness policy; if no applicable freshness policy exists, do not invent one. Preserve observed time separately from updated time.

### 5.3 Rules and profiles
- `RulePack`: stable ID, version, author/source, applicability description, jurisdiction disclaimer, rules, content hash. If no professionally reviewed jurisdictional pack exists, ship **DEMO_RULEPACK_NOT_LEGAL** with explicit synthetic thresholds chosen solely to exercise the engine, not represented as Indian/US law.
- `Rule`: ID, scope (`node`,`edge`,`crossing`,`route` where implemented), applicability predicate from a SAFE WHITELIST, required attributes, operator (`gte`,`lte`,`eq`,`one_of`,`exists`, etc.), threshold and canonical unit, source reference or labeled demonstration basis, plain-language message, criticality and version.
- Rules are **data**, never `eval()`, untrusted Python imports, arbitrary JavaScript, user-supplied expression execution or SQL code.
- `MobilityProfile`: two separate named DEMO profiles with independently documented hard requirements and optional preferences. Do not assume a single real wheelchair profile captures all users. Preference weights cannot override hard constraints. Explicitly show which constraints derive from a demo profile versus a rulepack.
- Rule-level verdict: `PASS`, `FAIL`, `UNKNOWN`, `NOT_APPLICABLE`; includes result reason code, element ID, rule ID, profile, phase, input observation IDs, values/units where available. `NOT_APPLICABLE` is only for an individual rule that was proved inapplicable, not an escape hatch for missing evidence. An edge is model-confirmed pass only when all required applicable checks pass, with no unresolved critical checks and a documented nonempty set of relevant checks.
- If a required attribute is missing, conflicting, expired under its applicable freshness rule, unsupported or geometrically inconsistent, rule outcome is `UNKNOWN` unless an independent known fact already proves the same rule fails. Preserve both known failure and unknown findings where they coexist; do not hide unknown issues behind aggregate Fail.
- Tests must show that changing only a profile preference cannot change hard-rule outcomes.

### 5.4 Scenarios and phases
- `Scenario`: immutable parent revision ID, base graph version ID, graph edits/interventions, ruleset version/hash, origin/destination config, named phases, created metadata, canonical hash.
- `Phase`: unique ID, deterministic order, explicit active-period boundary convention (`[start,end)` if timestamps exist), active edge closures/temporary openings, and immutable changes. Handle adjacent boundaries deterministically. The demo may use logical phase numbers where exact dates are not specified; never invent a construction calendar.
- `Intervention`: stable ID, allowed operation(s), target edges/nodes, preconditions, effect, active phases, dependencies/exclusions, cost entries, evidence requirements, review/field-constructibility flag. No fabricated free-form roads, ramps or connections.
- Apply edits as a pure transform `build_graph(base_version, scenario_revision, phase) -> phase_graph`. Baseline is never mutated. Active closures override traversal even if an edge otherwise passes constraints. An explicitly added temporary path exists only in its allowed phase(s).

### 5.5 Analysis and exports
- `AnalysisRun`: run ID, semantic input hash, engine/build version, graph/rulepack/profile/phase IDs and hashes, deterministic results, creation time, compute duration, warnings, algorithm version and provenance.
- `Finding`: stable machine-readable reason code, severity, rule/edge/node link, evidence references and human explanation derived ONLY from actual computed data.
- `ReviewArtifact`: manifest schema version, referenced immutable runs, selected candidate/solver status, unknowns, limitations, source attributions and report hash.
- Distinguish semantic-reproducibility hashes from inherently volatile run metadata (timestamps/durations). Two replay runs with identical semantic inputs should produce the same canonical semantic result hash even if their run IDs/timestamps differ. Use canonical serialization with stable sort/order, numeric normalization and explicit versioning; test hash replay across process restarts.

## 6. AUTHORITATIVE ROUTING AND VERIFICATION ALGORITHMS

Implement, document and test this exact separation:

1. Validate import and topology. A visually crossing line is never a graph link without explicit node linkage.
2. Resolve evidence for each required field; detect absent, conflicted and expired attributes.
3. For selected `(scenario, phase, profile, rulepack)`, build an immutable phase-specific directed graph. Apply closed edges and ephemeral additions with stable IDs.
4. Evaluate applicable node, edge and crossing rules. Every check yields `PASS/FAIL/UNKNOWN/NOT_APPLICABLE` plus trace and explanation. Node-level and crossing-interface constraints must affect traversal, not merely appear in a side panel.
5. Construct **confirmed** feasibility graph: eligible edges/nodes with all relevant mandatory modeled constraints confirmed PASS. Construct **possible** graph: confirmed elements plus elements UNKNOWN solely due to unresolved evidence, while excluding known FAIL, inactive and closed elements. The possible graph must not override an independently known Fail.
6. Perform deterministic directed routing on each graph. Return path as an **ordered list of exact edge IDs** (not only node IDs) and route meters; preserve multigraph parallel-edge distinction. Choose a stable tie-break for equal distances; write a test for it. NetworkX's default treatment of absent weights must not silently give edges length 1: explicitly validate all routing weights and paths before calling graph algorithms.
7. For each selected origin-destination pair report `confirmed_reachable`, `possibly_reachable`, `confirmed_path_edges`, `confirmed_distance_m` only when actually proven, `possible_path_edges` labeled hypothetical, `known_blocking_findings`, `unknown_findings`, and `reason_codes`. Do not claim every failed rule on the map is causally responsible for each unreachable OD pair; only say "blocking" if demonstrated using a reproducible frontier/cut/counterexample analysis. Otherwise label "relevant findings".
8. Compare scenarios/phases/profile-specific OD matrices on identical origin/destination sets and route weight policies. Show lost confirmed links, newly gained links, already-unknown connections, and route-distance deltas only when both comparable routes exist. Explain empty networks, missing origin nodes and invalid graph structure as explicit errors/statuses.
9. The UI receives these structured results. It must not locally invent route feasibility or substitute cached results after graph edits. Mark results stale until reevaluated if an input hash changes.

Suggested pure functions: `validate_graph`, `resolve_attribute`, `evaluate_rule`, `evaluate_traversal`, `build_phase_graph`, `build_feasibility_graphs`, `route_edge_ids`, `evaluate_od_pairs`, `compare_runs`, `canonical_result_hash`.

**Useful test cases:** grade direction reversal; two parallel edges between same nodes, only one accessible; crossing geometry without shared node ID; a known fail plus an unknown on another attribute; N/A on one rule but an unmeasured critical attribute on another; forbidden edge active in phase 2 only; confirmed path absent but possible path present; stale cached evaluation must not appear current.

## 7. FIX THIS PLAN: BOUNDED, HONEST OPTIMIZATION (R1)

Implement a small explicit intervention library keyed by stable IDs, with preconditions, clear effects, applicability phases, mutually exclusive groups, dependencies and user-entered/demo-labeled cost model. Candidate types may include: enable a pre-surveyed alternate connection; add a predetermined temporary path edge with documented geometry and unknown/specified measurements; add a modeled curb transition at a designated permitted location; shift a designated barrier only within an explicitly configured boundary; or change the activation phase of a designated closure. Do NOT synthesize engineering geometry or costs from a language model.

Candidate lifecycle:
1. Read the selected failed/unknown scenario, active phase(s), selected profiles and objectives, immutable candidate library and budget.
2. Validate every intervention precondition; show candidate rejection reasons. Do not assume that a temporary connection is constructible in the field just because it exists in a model.
3. Enumerate valid subsets deterministically when small; detect estimated exponential growth and surface limits. If using an alternate solver, justify model equivalence and support precise statuses. Never silently skip subsets and then claim global optimality.
4. Materialize each candidate subset into a NEW derived scenario version; apply real graph/evidence edits; reevaluate the entire affected network with the same authoritative engine. No candidate may bypass this step.
5. First reject known hard-rule failures for the required OD objective. UNKNOWN candidates are **not certified feasible**: keep them in a separate "requires verification" bucket. Distinguish known infeasibility from not enough evidence and infeasibility over a *bounded candidate set* from proving that no real-world solution exists.
6. Rank model-confirmed candidates under documented lexicographic objectives: preserve required OD access and selected profiles, then connected-destination coverage, then monetary estimate, then additional distance. If the user selects another ordering, present exactly that ordering and keep mandatory conditions fixed. Calculate an actual Pareto/non-dominated set when multiple objectives conflict; do not label a single weighted sum a Pareto frontier.
7. Cost model: currency and user-entered/demo price provenance, quantities, setup/removal costs where modeled, min/nominal/max bands if provided, and treatment of missing prices. Never silently treat missing cost as zero. Budget checking must state whether nominal-only or conservative upper bound; no invented exchange rates or market construction prices.
8. Solver/result status: `OPTIMAL_IN_ENUMERATED_DOMAIN` only after complete exhaustive search of all eligible subsets and correct objective handling; `FEASIBLE_NOT_PROVEN_OPTIMAL`; `NO_FEASIBLE_IN_ENUMERATED_DOMAIN`; `INVALID_INPUT`; `INCOMPLETE_OR_UNKNOWN`. If OR-Tools is used, correctly map its `OPTIMAL`, `FEASIBLE`, `INFEASIBLE`, `MODEL_INVALID`, `UNKNOWN` and explain its domain/termination limits. Include visited candidate count and elapsed time.
9. Apply-to-branch requires explicit user action. Save branch, record old/new input hashes, rerun verification and show changes. Never mutate the reference/baseline scenario on suggestion.

Edge cases to test: zero candidate list; no feasible set; zero budget; identical-cost alternatives; incompatible interventions; dependent pair; a "cheapest" intervention producing an unknown width; unknown cost; timed-out search; two candidates independently insufficient but jointly restoring a connection; a candidate passing one mobility profile while failing the other.

## 8. EVIDENCE CENTER, INSPECTION QUEUE AND FAILURE LAB (R1)

**Evidence Center:** User can inspect, edit and invalidate observations through typed forms; changes must create a revision, not silently overwrite history. Show source/observed date, original units, verification state and uncertainty status. Conflict resolution needs an explicit reviewed decision with provenance, not an arbitrary latest-wins rule.

**Inspection queue:** For each critical UNKNOWN identify the exact element/attribute, the reason the evidence is insufficient, any potentially affected OD pairs, and a priority. Start with a documented deterministic heuristic (e.g., whether the unknown lies on any potentially connecting path to an essential destination); do not call it sophisticated Bayesian value-of-information unless you actually implement and benchmark such a method. Allow entering a new measurement; check that confirmed/possible status changes accordingly. Keep a readable queue even when map rendering is unavailable.

**Failure Lab:** Provide at least five named, deterministic, reversible tests using isolated branches: (1) remove curb transition; (2) close alternate edge in a later phase; (3) remove a critical width observation; (4) introduce conflicting measurements; (5) break crossing topology or add an obstruction. Each injection declares its modified element IDs, initial expectations, rerun results, changed verdicts and reset semantics. Do not make failures animations divorced from the engine. Make the exact scenarios executable as automated regression fixtures too.

**Scenario comparison:** Side-by-side synchronized geographic views when practical, plus always-visible comparable text/tables. Same ruleset/profile/phase context must be made explicit; warn rather than conflate fundamentally different evaluation inputs.

## 9. HTTP API, PERSISTENCE AND ERRORS

Implement versioned routes from PRD, at minimum:

```text
POST  /api/v1/projects
POST  /api/v1/projects/{id}/imports
GET   /api/v1/projects/{id}/graph
POST  /api/v1/projects/{id}/scenarios
PATCH /api/v1/scenarios/{id}
POST  /api/v1/scenarios/{id}/evaluate
GET   /api/v1/runs/{id}
GET   /api/v1/runs/{id}/manifest
POST  /api/v1/scenarios/{id}/candidates         [R1]
POST  /api/v1/scenarios/{id}/fault-tests        [R1]
GET   /api/v1/runs/{id}/report                  [R1]
```

Add necessary read/list endpoints and a documented health endpoint rather than leaving the frontend unable to load resources. Define request/response Pydantic models, generated OpenAPI, stable snake_case or camelCase translation policy, predictable pagination where relevant, and a consistent error envelope: `{code, message, details, request_id}`. Use appropriate 400/404/409/422/500 semantics, including optimistic concurrency checks for scenario edit revisions. Reject invalid JSON, malformed GeoJSON, out-of-range values, nonexistent references, cyclic intervention dependencies, unsupported units and impossible graph edits with actionable field-level messages.

Persist projects, graph versions, scenarios, evidence and runs in SQLite using explicit schema migrations/transactional writes and foreign keys. Persist canonical input/output payloads and hashes; store no secret tokens in fixture data. The demo must preserve edits and branch history across browser refresh/backend restart. Import is transactional: rejected files do not leave half-created graphs. Use parameterized SQL through appropriate library; never interpolate untrusted values into queries. Follow simple request-size and file-size limits and safe upload handling. User-entered geospatial/HTML labels must be escaped. Report generation must not cause arbitrary filesystem reads.

Never mark a stale analysis current after a graph/phase/profile/evidence edit. Include run-version compatibility and a re-evaluate affordance. Validate network geometry and attribute constraints on both frontend and backend; backend is authoritative.

## 10. FRONTEND / UX: HACKATHON-GRADE, NOT A FAKE DASHBOARD

Build a visually strong, cohesive, fast responsive experience with high information density but no misleading decoration. Document design tokens in code: typographic hierarchy, spacing scale, focus rings, restrained primary/neutral/warning/failure/success semantics, map legend, loading states, disabled states, table layouts. Do not use gimmicky particle effects or meaningless "AI intelligence" numbers.

Required screens and interactions:
- **Project Home:** open seeded project; import a network; show exact dataset provenance, graph version, active scenario, ruleset and visible limitations.
- **Planning Studio:** map/canvas with node/edge selection, closure toggle/drawing, temporary edge creation, topology editor, measurements, destination assignment, undo or version rollback. Provide usable list/keyboard alternatives to every core map editing action.
- **Verification:** profile selector, phase selector, side-by-side baseline/current results, confirmed vs possible OD matrix, route highlighting based ONLY on returned path edge IDs, findings list, exact evidence/rule drawer.
- **Fix This Plan:** budget field, candidate library controls, solution status banner, sorted table, cost assumptions, trade-off view, preview diff, explicit apply-to-branch confirmation.
- **Evidence Center:** sources, missing/conflicting attributes, measurements and critical unknown queue.
- **Failure Lab:** named fault cards, run/reset control, changed-result comparisons and explanations.
- **Reports:** run selector, canonical JSON download and generated PDF review packet with obvious disclaimer.

States for every actionable control: initial/empty/loading/success/error/retry; keyboard operability; screen reader labels; accessible error messages; explicit focus order and dialogs; contrast that meets WCAG 2.2 AA target where applicable; maps accompanied by equivalent text and tables; icons never carry the only meaning; reduction-of-motion support. Route colors alone do not encode accessibility status. Demonstrate a complete keyboard-only workflow. Test on multiple viewports (desktop and mobile); mobile can be a simplified but working inspector view, not a desktop design that merely shrinks.

**Offline demo:** If remote tiles fail, the actual graph geometry, routes, labels, legend and interaction must still render from packaged fixture data. Do not make all functionality depend on a MapLibre external style URL. Consider a lightweight fallback SVG/canvas renderer for synthetic local-planar coordinates, but do not duplicate business logic.

No inactive-looking buttons that appear enabled, lorem ipsum, empty chart panels, handwaved "coming soon" inside R0/R1 or mocked verification counters. If truly not implemented, label feature explicitly deferred and keep it out of the release path.

## 11. PDF / JSON REPORTING AND TRACEABILITY

Generate canonical **machine-readable JSON** from computed runs, containing schema version, owner/project, graph/scenario/rulepack/profile/phase hashes, exact evaluated rule results, status counts, complete unknown list, route edge IDs, OD matrices, comparison data, candidate intervention sets, solver status, demo data disclaimers, attributable source URLs/licenses, deterministic semantic hash, execution version and warnings.

Generate an **R1 PDF** from the same structured facts with: cover; explicit "Planning analysis — not certified" warning; study boundary and inputs; baseline and modified overview; per-profile/phase findings; evidence gaps; intervention/cost methodology; alternatives and trade-offs; failure-test outcomes; reviewer action list; limitations and source notices; appendix with reproducibility IDs/hashes. PDF should be readable without the web app, selectable text, sane page breaks, accessible structure as far as the PDF toolchain permits, and no fabricated engineer signatures, official seals or legal approvals.

Two run instances with equal immutable semantic inputs must yield equivalent canonical semantic result JSON/hash; report timestamp, created filenames and execution duration are excluded from the semantic fingerprint. Verify this in tests. If any library's PDF byte stream has nondeterministic metadata, document that rather than claiming byte-for-byte PDF identity; match the canonical manifest instead.

## 12. TESTING: MANDATORY PROOF, NOT OPTIONAL NICE-TO-HAVE

Use layered automated verification and actually execute it:

**Backend unit and property-based tests** (pytest + Hypothesis where available): import schema, CRS/unit conversions, graph endpoints, directed edges, parallel-edge identity, crossing non-connectivity, pure scenario replay, evidence resolution, four-valued rule semantics, note that Fail and Unknown are not collapsed, possible/confirmed graph inclusions, phase activation, route determinism, comparison semantics, candidate prerequisites, solver/exhaustive statuses, manifest hashes. Test negative and malformed inputs.

**Frontend tests** (Vitest + Testing Library): loaded states, zero-data states, buttons, dialog focus, forms, errors, keyboard navigation, accessible names, active selections, route/evidence drill-down, stale-run banners and no fake results.

**End-to-end tests** (Playwright or equivalent real-browser harness): launch API/web, seed project, close an edge, verify changed OD matrix, inspect rule provenance, apply candidate to new branch, move phase, inject and reset fault, export JSON/PDF, reload and verify persistence. Include network-disabled test if possible. Capture actual traces/screenshots on failure.

**Integration/contract tests:** frontend client matches OpenAPI/Pydantic schemas; successful request + validation failure + missing resource + optimistic concurrency conflict + internal failure handling. Test atomic import/rollback and persistent reload.

**Accessibility checks:** automated static checks (e.g., axe-based) plus at least one manual documented keyboard-only end-to-end pass; do not claim full accessibility conformance from automated tests alone.

**Security/safety checks:** malicious rich-text label escaping, rejected uploaded executable content, oversized imports, invalid CRS, unknown unit, cyclic intervention prerequisites, forged evidence statuses, path traversal in report outputs, SQL injection attempt, invalid UTF-8, NaN/Infinity, stale revision update. Document known limitations and data retention.

**Seeded deterministic benchmark:** at least **30 distinct regression cases**, including the following mandatory behaviors:
1. crossing geometries intersect, but lack connecting graph node;
2. directed edge permits forward, forbids reverse;
3. parallel edges differ in accessibility, route uses right edge ID;
4. known curb transition failure;
5. missing curb transition evidence;
6. conflicting width observations;
7. incompatible units rejected/converted explicitly;
8. steep grade in one direction;
9. closed edge only in phase 2;
10. temporary edge exists only in phase 1;
11. unknown path exists but no confirmed path;
12. no path even in possible graph;
13. different mobility profiles give different results;
14. preference cannot override hard fail;
15. N/A cannot clear another critical UNKNOWN;
16. repeated import preserves stable semantics;
17. graph edit leaves baseline unchanged;
18. optimizer candidate needs two interventions jointly;
19. invalid candidate precondition rejected;
20. no candidate restores mandatory OD;
21. budget less than every viable option;
22. absent cost does not become zero;
23. exact enumeration detects objective tie;
24. incomplete search does not report optimal;
25. wrong-phase route not accidentally reused;
26. evidence revision invalidates stale run;
27. source timestamps/attribution survive export;
28. deterministic hash survives process restart;
29. PDF warns not certified;
30. malicious markup does not execute on UI;
31. frontend offline mode still shows graph;
32. route comparisons don't invent distance for unreachable paths.

**Evaluation baselines are mandatory, not optional:** implement transparent comparable baselines on the SAME scenario fixtures: (B1) geometric/ordinary shortest path ignoring accessibility attributes, (B2) static accessibility-aware routing without construction phases, (B3) per-segment rule checks without OD graph connectivity, (B4) greedy one-intervention-at-a-time selection versus the bounded exact candidate search. For critical inspection ordering, compare with naive spatial/first-listed ordering if that feature is evaluated. Run at least one ablation disabling unknown-aware treatment to illustrate why conservative evidence states matter, but NEVER expose that unsafe ablation as a normal production mode. Publish the exact fixture count, data type, objective and denominators; report that these are synthetic-regression findings and not independently verified field safety. If a baseline cannot be implemented rigorously, mark evaluation INCOMPLETE instead of inventing comparison scores.

Measure and publish **actual** results: violation recall on benchmark cases, false-safe count/rate, unknown-state recall, correct OD reachability, candidate feasibility, number of candidate subsets evaluated, p50/p95 analysis latency and scenario sizes. Keep synthetic and field-validated datasets in separate evaluation tables. Never claim an externally validated real-world accuracy percentage unless it was actually measured.

At R0 exit: **zero known false-safe decisions in the predefined known-invalid fixture cases**; all required P0 flows pass; no known critical failures unaddressed. This target concerns the internal fixture suite, not zero error in the real world. At R1 exit: optimization, phases, fault injection, report export and browser demo pass their tests; obvious accessibility blockers are resolved or transparently documented.

## 13. TECHNICAL QUALITY, PERFORMANCE AND REPRODUCIBILITY

Before declaring completion:
- Pin dependency versions and check license compatibility, package integrity and documented setup. Produce lockfile(s) and avoid unnecessary dependencies.
- Expose one clean local startup path and one clean verification command, e.g., project scripts invoking backend/frontend tests, TypeScript check, Python lint/format, API contract checks and benchmark smoke tests. Verify commands on the actual machine rather than assuming they work. Provide equivalent PowerShell directions or platform-neutral scripts where practical.
- Use consistent types and validation at all boundaries; no wildcard `any` or broad exception swallowing hiding invalid scenarios.
- Keep map rendering separate from model truth; ensure a recalculation failure is explicitly surfaced and never displays old results as fresh.
- Use deterministic random seeds if any randomized fixture or testing technique is introduced. Do not seed actual design decisions with random outputs.
- Add structured logs containing action IDs, run IDs and reason codes without leaking private evidence. Avoid logging full uploaded photos or unnecessary personal data.
- Optimize only measured bottlenecks; benchmark at least small/medium/larger synthetic graphs with documented node/edge counts, test machine and methods. Set transparent timeouts to avoid locking the interface; no promise of unlimited runtime or proof after timeout.
- Include concise data dictionary, architectural decision records, system/sequence diagrams when they clarify state and trust boundaries, and a development playbook for a second engineer.
- Record user-relevant failures under `docs/ENGINEERING_POSTMORTEMS.md`: attempted approach, observed error, root cause, exact correction and regression test. This log must contain genuine findings, not invented struggles for a compelling judge pitch.

## 14. DEVELOPMENT ORDER AND HARD GATES

Do NOT build a beautiful shell followed by disconnected stub APIs. Progress only after vertical acceptance checks.

**Gate 0 — Evidence and environment:** inspect repo, PRD, requirements, dependencies, source/data licenses and tools. Update `DECISIONS.md`, traceability, minimal boot commands. Exit: documented runnable skeleton and clear limitations.

**Gate 1 — Domain correctness:** implement validated immutable graph, explicit directions/interfaces, evidence records, conflict resolution, rulepacks/profiles, four-valued rule evaluation, confirmed vs possible graphs, deterministic edge-ID routing, immutable phases and scenario hashing. Exit: comprehensive backend tests for INV-01 through INV-08 and seeded fixtures pass.

**Gate 2 — Persisted R0 workflow:** implement SQLite transactions/versions, API contracts, imports, project/scenario editing, evaluation, reproducible JSON export. Exit: integration tests, process restart persistence and hash replay pass.

**Gate 3 — Real R0 user interface:** implement accessible project, planning, verification and evidence journeys with live map/canvas, keyboard equivalent, actual APIs and state recovery. Exit: end-to-end closure -> evaluate -> inspect -> export works in browser, offline.

**Gate 4 — Phase-aware R1:** add multi-phase timeline, immutable branch/revision comparison, correct phase transitions. Exit: all phase regressions and browser flows pass.

**Gate 5 — Fix This Plan R1:** implement finite intervention library, precondition checks, exhaustive enumeration where manageable, full re-verification, honest domain-specific statuses, objective/Pareto comparisons, budget assumptions and apply-to-branch. Exit: special candidate fixtures and E2E pass.

**Gate 6 — Trust-building R1:** critical evidence queue, five actual fault injections, side-by-side comparisons and final PDF packet. Exit: exported outputs match stored run facts; failure-reset is proven reversible.

**Gate 7 — Engineering polish and audit:** optimize UX and accessibility, CI, harden error paths, verify on clean environment, benchmark and compare baselines, run static checks, write actual research evaluation, create judge demo. Exit: release checklist fully green or clearly flagged red; no undocumented critical gaps.

At each gate: implement -> run targeted tests -> fix -> run broader regression -> record actual results -> update traceability -> inspect Git diff -> commit small logical change under the specified identity. If a tool lacks capacity for continuous multi-file work, checkpoint with sufficient details and continue in a subsequent task/session; never compress away tests to save tokens.

## 15. OPERATING DISCIPLINE FOR A SMALL/FLASH MODEL

You are optimized for stepwise accuracy, not eloquent speculation. Follow this loop strictly:

1. **Observe** actual files, docs, tests, outputs, environment and repository state; never infer them from memory.
2. **Select exactly one coherent vertical slice** from the current gate.
3. **Write a short internal implementation plan** (files touched, interfaces and tests). Do not turn this into a permission request unless a true blocker exists.
4. **Implement the smallest correct slice** with typed contracts, errors and comments explaining non-obvious invariants.
5. **Execute tests or a reproducible manual verification**. Read the actual stderr/stdout; never guess a pass. Fix regressions before starting the next feature.
6. **Review** diff for unrelated changes, missing attribution, hidden mocks, unbounded computations, edge conditions, security and accessibility.
7. **Checkpoint** `FLOW.md` (next exact actions), `DECISIONS.md` (why), traceability (proof), postmortems (only actual failures). Commit if repository permits.
8. **Resume** until the current gate passes, then proceed. Do not stop after drafting files or showing an architecture diagram.

When context becomes large, reload `FLOW.md`, `DECISIONS.md`, `REQUIREMENTS_TRACEABILITY.md`, the PRD and the most relevant code/tests before continuing. Do not rely on a prose recollection if the repository can be inspected. If an action fails three times, stop repeating it blindly: inspect current state, reproduce a minimal error and revisit root cause, preserving existing work.

**Truthfulness protocol:** Distinguish `(IMPLEMENTED AND TESTED)`, `(IMPLEMENTED BUT NOT VERIFIED)`, `(PARTIALLY IMPLEMENTED)`, `(BLOCKED)`, `(DEFERRED)`. Never claim completed milestones because files exist, tests were written but not run, commands were assumed to work, or a screenshot looks plausible. Do not fabricate benchmark results, code coverage, deployed URLs, user research or compliance certificates.

## 16. SECURITY, ATTRIBUTION, AND RIGHTS

- Do not access unrelated files/accounts, push to unknown remotes, expose credentials or upload private material. If access is missing, work locally and report what explicit permission is needed.
- Git commits you create must show author/committer exactly `PrathamKapoor <prathamkapoor027@gmail.com>`, as authorized. Verify via `git log -1 --format=fuller`; do not rewrite historic commits. Local config only.
- Include attribution and licensing for OpenStreetMap data, MapLibre and other third-party libraries/assets in project notices where required; examine each actual license. Do not invent a project open-source license in the owner's name. If no license is authorized, record that release licensing is pending.
- Keep real location survey data and respondent information out of public fixture packages unless ownership, purpose and privacy permissions are documented. Synthetic datasets must be unambiguously labeled as synthetic in UI, API, reports and documentation.
- Follow sound upload validation, safe text rendering, parameterized database access, file path confinement and least-privilege execution.
- Separate "demo rules" from legally applicable rules, and surface the distinction next to verdicts. Avoid medical or legal claims about individuals' mobility without validated source data.

## 17. EXPECTED DOCUMENTS AND FINAL HANDOFF

Deliver a runnable repository with:

1. Working full-stack code, actual user journeys, seeded datasets, persistent scenario revisions and deterministic core engine.
2. `README.md` with prerequisites, fresh install, local launch, tests, seed/reset instructions, online/offline behavior, known limitations and screenshots captured from the actual app when practical.
3. `DECISIONS.md` with the actual choices, alternatives, trade-offs and why; `FLOW.md` with end-to-end system lifecycle and recovery/resumption notes.
4. `docs/REQUIREMENTS_TRACEABILITY.md` connecting every FR/INV to actual code and tests; `docs/ASSUMPTIONS_AND_LIMITATIONS.md` separating facts, synthetic values and missing authority sign-off.
5. `docs/ARCHITECTURE.md`, `docs/DATA_DICTIONARY.md`, `docs/API.md`, `docs/TEST_PLAN.md`, `docs/EVALUATION.md`, `docs/SECURITY_AND_PRIVACY.md` and `docs/ENGINEERING_POSTMORTEMS.md` (genuine failures only).
6. End-to-end seed demo plus script in `docs/DEMO_SCRIPT.md` with audience actions, expected computed behavior, and a backup offline path.
7. CI pipeline that runs actual unit, integration, static and UI checks, with real command names and no fake successful jobs.
8. JSON and PDF examples generated from the working engine (not handcrafted output), clearly labeled example/synthetic.
9. Actual tested commands, exit statuses, test counts, measured benchmarks, unresolved issues, release readiness and Git commit IDs.

**Final response after execution, in this order:**
- What was implemented, grounded in paths and passed tests.
- Actual local run commands (backend, frontend and offline seed).
- Traceability/gate status with honest blockers.
- Test suite commands and measured results; known limitations.
- How to replay the five-minute demo step by step.
- Commit hash(es) and confirmed requested author/committer attribution, if commits were actually created.
- What remains before a field pilot (especially rulepack review, physical surveys, accessibility user testing and constructibility approval).

**Absolute final rule:** Work until the actual code, behavior, tests, reproducibility and design quality support an S-tier hackathon presentation. The score and awards cannot be guaranteed. An honest, strongly engineered implementation beats a large fictional feature checklist. Begin by inspecting the repository and reading the PRD, then immediately implement Gate 0 and Gate 1. Do not respond with another prompt or a strategy essay instead of starting work.
