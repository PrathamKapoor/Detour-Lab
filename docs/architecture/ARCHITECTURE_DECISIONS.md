# DECISIONS.md — DETOUR LAB

Format per entry: **Decision** → **Alternatives considered** → **Why** → **Consequence / revisit trigger**.
Status labels used throughout: `(IMPLEMENTED AND TESTED)`, `(IMPLEMENTED BUT NOT VERIFIED)`,
`(PARTIALLY IMPLEMENTED)`, `(BLOCKED)`, `(DEFERRED)`.

Owner decisions are marked **[OWNER DECISION]**. Synthetic fixture defaults are marked
**[SYNTHETIC DEFAULT]**. Ordinary reversible engineering choices are marked
**[ENGINEERING CHOICE]**. Nothing in this file is a legal, safety or accessibility approval.

---

## D-001 — Repository location **[OWNER DECISION]**

- **Decision:** Repository lives at `C:\Pratham\DETOUR-LAB`, freshly initialised as a Git repo
  on branch `main`. No pre-existing project in `C:\Pratham` was modified.
- **Alternatives:** reuse one of the six existing sibling projects (`AegisCPG`, `freeflow`,
  `mental.ai`, `MORPH`, `sofa-problem`, `VeriKernel`); place the repo elsewhere on disk.
- **Why:** Owner selected a dedicated, isolated repository. Sibling folders were inspected only
  for existence/count; they were not opened, read or modified.
- **Consequence:** `C:\Pratham` itself is not a Git repository; the new repo is nested inside it.

## D-002 — Licence **[OWNER DECISION]**

- **Decision:** Apache License 2.0. Canonical licence text fetched from
  `https://www.apache.org/licenses/LICENSE-2.0.txt` (11 358 bytes) and stored as `LICENSE`
  with the appendix copyright line set to `Copyright 2026 PrathamKapoor`.
- **Alternatives:** MIT; All-rights-reserved; leave licensing pending.
- **Why:** Owner answered "apache" when asked. The licence text was downloaded rather than
  retyped so the wording is verbatim upstream.
- **Consequence:** Third-party dependency licences must still be tracked separately
  (`docs/RESEARCH_AND_SOURCES.md`). Apache-2.0 is permissive but includes a patent grant;
  re-ask the owner if the intended product posture is different.

## D-003 — Git identity scope **[ENGINEERING CHOICE, per MASTER_PROMPT §0]**

- **Decision:** `git config --local user.name PrathamKapoor` /
  `user.email prathamkapoor027@gmail.com` inside `C:\Pratham\DETOUR-LAB` only.
- **Observed:** global `user.name` and `user.email` are both **unset** on this machine and were
  not modified. Local config verified via `git config --local --list`.
- **Consequence:** Commits made here are attributable to the owner without touching machine-wide
  configuration. No remote is configured; nothing is pushed.

## D-004 — Rulepack is a DEMO pack, never a legal standard **[ENGINEERING CHOICE, PRD §11.2]**

- **Decision:** Ship `DEMO_RULEPACK_NOT_LEGAL` v1.0.0 with thresholds chosen only to exercise the
  engine. `legal_applicability = "unverified"` on every run manifest and every verdict surface.
- **Alternatives:** encode Harmonised Guidelines 2021 (IN) or PROWAG (US) as enforceable rules.
- **Why:** PRD §11.2 and MASTER_PROMPT §5.3 forbid claiming statutory compliance without
  professional review, and no qualified reviewer has reviewed this project.
- **Consequence:** No screen, report or manifest may contain "compliant", "certified" or
  "approved". Revisit only after a named domain expert signs off (see `docs/ASSUMPTIONS_AND_LIMITATIONS.md`).

## D-005 — Coordinate basis for the seeded demo **[ENGINEERING CHOICE, MASTER_PROMPT §4]**

- **Decision:** The canonical seeded dataset uses an **explicitly labelled local-planar metre
  schema** (`coordinate_basis: "local_planar_meters"`) and is *not* claimed to be RFC 7946
  GeoJSON. The importer additionally accepts genuine RFC 7946 WGS 84 GeoJSON and converts
  metres using an explicitly recorded local projection; metre arithmetic is never done on degrees.
- **Alternatives:** (a) fake "real-looking" lon/lat for a made-up city — rejected, invents a place;
  (b) bundle real OSM extract — rejected, no data rights/permissions verified yet;
  (c) MapLibre raster/vector basemap tiles — rejected as a hard dependency (offline requirement).
- **Why:** MASTER_PROMPT §4 "Geographic caution" explicitly permits a separate labelled local-planar
  schema. This keeps the offline demo honest and fully self-contained.
- **Consequence:** Geometry lengths/widths are real metres in the planar basis. Displayed
  coordinates are schematic and must always be labelled synthetic. Any future real-area study
  requires a licensed dataset plus a recorded CRS before it can replace this fixture.

## D-006 — Rendering: offline vector canvas, no basemap dependency **[ENGINEERING CHOICE]**

- **Decision:** The map surface is a deterministic SVG renderer fed by canonical graph geometry
  returned by the API. The UI never computes verdicts, paths or feasibility.
- **Alternatives:** MapLibre GL JS with remote style/tile URL (breaks the offline demo and adds
  third-party usage/licence conditions); raster tiles from OSM public servers (explicitly not
  unrestricted infrastructure, PRD §11.1).
- **Why:** PRD FR-015 "Offline demo" and MASTER_PROMPT §4 "Runtime" forbid a basemap dependency.
- **Consequence:** MapLibre may still be introduced later for real-area WGS 84 studies under
  documented tile-provider terms; the renderer abstraction must not leak business logic into the UI.
- **Status:** `(DEFERRED)` — renderer not built yet at this checkpoint.

## D-007 — Optimisation starts with exact finite enumeration, not OR-Tools **[ENGINEERING CHOICE, PRD §8.3]**

- **Decision:** "Fix This Plan" enumerates all eligible subsets of a bounded intervention library
  and labels results `OPTIMAL_IN_ENUMERATED_DOMAIN` only when the enumeration is provably
  exhaustive. OR-Tools CP-SAT is introduced only if a benchmark shows enumeration is insufficient.
- **Consequence:** No claim of global optimality over the real world, only over the enumerated
  candidate domain. Revisit trigger: >20 eligible interventions or >10 s enumeration on reference hardware.

## D-008 — Persistence: SQLite + canonical JSON payloads **[ENGINEERING CHOICE, PRD §10]**

- **Decision:** SQLite with explicit migrations and foreign keys stores entities *and* the canonical
  input/output payloads plus hashes for every run. PostGIS is out of scope until measured need.
- **Consequence:** Replay after process restart is verifiable by re-hashing stored canonical payloads.

## D-009 — Backend runtime and dependencies **(observed, Gate 0)**

- **Decision:** Python 3.12.10 virtual environment at `.venv` inside the repo; FastAPI + Pydantic v2
  + NetworkX + Shapely + ReportLab; dev deps pytest, httpx, hypothesis, ruff.
- **Observed resolved versions** (actual `pip install` output on 18 Oct 2026):
  fastapi 0.143.3, pydantic 2.14.1, networkx 3.7, shapely 2.2.0, reportlab 5.0.1,
  uvicorn 0.54.0, pytest 9.1.1, httpx 0.28.1, hypothesis 6.170.1, ruff 0.17.1,
  starlette 1.8.0, numpy 2.5.4, pillow 13.0.0.
- **Why:** Pinned versions recorded after an actual resolver run rather than guessed.
- **Consequence:** `apps/api/requirements.txt` pins direct deps; `requirements-lock.txt` records
  the full resolved set. ReportLab 5.x is a major-version change and its import surface is
  verified by tests, not assumed.

## D-010 — No invented jurisdiction, measurements or user research **[ENGINEERING CHOICE]**

- **Decision:** The study area is a schematic synthetic fixture with zero claims about a real place.
  Every attribute carries `provenance_class` ∈ {`synthetic`, `assumed`, `external_source`, `measured`, `derived`}.
- **Consequence:** Benchmark numbers may only ever be described as *synthetic-regression* results
  (PRD §13.1). Field validation remains an open, owner-dependent prerequisite.

## D-011 — Evidence handling is conflict-preserving **[ENGINEERING CHOICE, PRD §8.4]**

- **Decision:** Contradictory eligible observations for one attribute produce `UNKNOWN` and retain
  every contributing record. No "latest wins" or "most convenient wins" resolution without an
  explicit reviewed human decision with provenance.
- **Consequence:** Directly implements INV-01 and the "unknown never silently passes" requirement.

---

## D-012 — The evaluation instant is an explicit, stored input **(Gate 2)**

- **Decision:** `run_analysis` / `evaluate_graph` require an `as_of` timestamp. It is stored with
  the run and reused verbatim on replay.
- **Why:** Defaulting to `datetime.now()` would make verdicts depend on the wall clock and would
  silently invalidate every attribute governed by a freshness policy (real failure P-05).
- **Consequence:** Two evaluations with the same `as_of` and inputs produce identical semantic
  hashes; the HTTP API accepts `evaluation_instant` explicitly.

## D-013 — Volatile metadata is excluded from the semantic fingerprint **(Gate 2)**

- **Decision:** The manifest carries a `runtime` block (run id, created_at, duration, evaluation
  instant) that is deliberately **excluded** from `semantic_hash`. Everything else is included.
- **Why:** MASTER_PROMPT §5.5 requires two replay runs with equal semantic inputs to yield the
  same canonical hash while run metadata legitimately differs.
- **Consequence:** `verify.ps1` asserts identical *result payloads* and identical *semantic hashes*
  across two HTTP calls, plus a different run id — a stricter check than comparing whole responses.

## D-014 — Errors use one flat envelope **(Gate 2)**

- **Decision:** Every failure returns `{"code", "message", "details", "request_id"}` at the top
  level, including Pydantic validation failures and unknown routes.
- **Why:** FastAPI nests handler-raised errors under `detail` while custom handlers return a flat
  body; a client should not have to know which produced the response (real failure P-10).
- **Consequence:** `packages/contracts` consumers have exactly one error shape to handle.

## D-015 — Scenario edits are validated before they are stored **(Gate 2)**

- **Decision:** `PATCH /scenarios/{id}` builds a *prospective* scenario, constructs the phase graph
  for every declared phase, and only then writes a revision.
- **Why:** Storing an edit that cannot be applied would leave a scenario that only fails later, at
  evaluation time, which is exactly the "silent success" the pack forbids.
- **Consequence:** Invalid edits return 422 and leave revision history untouched; removing an edge
  that a declared phase closes is rejected with a precise reason code.

---

## Open items awaiting the owner (not blocking current work)

| # | Question | Why it matters | Current substitute |
|---|---|---|---|
| O-1 | GitHub remote / push permission | No commits can be shared yet | Local repo only; nothing pushed |
| O-2 | Real study area + map-data rights | Required for a non-synthetic demonstration | Schematic synthetic fixture |
| O-3 | Jurisdictionally reviewed rulepack | Required for any legal-facing claim | `DEMO_RULEPACK_NOT_LEGAL`, `legal_applicability=unverified` |
| O-4 | Named accessibility/domain reviewers | PRD §16 "External validation required" | Unmet; documented as a limitation |
| O-5 | Verified local unit prices | Cost model currently demonstration-only | Explicitly labelled illustrative ranges |
---

## D-016 - Three read endpoints were added before any frontend code **(Gate 3)**

- **Problem:** the Gate 2 API could create, patch, evaluate and export, but a client could not
  *load* a scenario at all, could not list the scenarios of a project, and could not list the runs
  of a scenario. A planning UI therefore could not know which revision it must submit, which
  phases exist, or what the previous run was.
- **Options:** (a) build the UI against those gaps; (b) add the three reads.
- **Decision:** add `GET /projects/{id}/scenarios`, `GET /scenarios/{id}` and
  `GET /scenarios/{id}/runs`. They are pure reads of already-stored state - no new domain
  behaviour, no schema change, backward compatible.
- **Trade-off:** the API surface grows by three routes. Accepted: without them the R0 journey is
  not implementable honestly.
- **Evaluation:** `apps/api/tests/test_scenario_read_endpoints.py` (11 tests) plus the OpenAPI
  route assertion.

## D-017 - No router, query library or state framework **(Gate 3)**

- **Problem:** a single workspace needs ~8 resources, explicit cancellation and strict stale-data
  rules. React Router, TanStack Query and Zustand would each have solved part of that.
- **Options:** adopt the libraries; or write a ~90-line `useResource` hook plus a context store.
- **Decision:** a small `useResource` hook (abort on dependency change, clear data when the key
  changes, never show a stale payload) and one `WorkspaceProvider`.
- **Why:** the hard requirements are *correctness under staleness*, not caching. A cache library's
  value is mostly cache invalidation, which this app must not do aggressively - after any save the
  affected resources are re-read from the server.
- **Trade-off:** no request deduplication; the workspace issues a handful of requests per
  navigation. Measured as negligible against a local 9-node graph.
- **Evaluation:** if the resource count grows past ~20 or request volume becomes measurable, adopt
  a query library.

## D-018 - Reopening a closure creates an immutable branch **(Gate 3)**

- **Problem:** the R0 API appends edits but never rewrites a phase declaration, so there is no
  "reopen" edit. The baseline must stay immutable (FR-005, INV-07).
- **Options:** (a) hide reopening; (b) add a mutating "reopen" operation; (c) create a branch
  scenario whose phase omits that closure.
- **Decision:** (c). The editor states this explicitly and offers "Reopen via branch".
- **Why:** it matches how the engine already treats proposals - as a new immutable object - rather
  than adding a mutation that would break content addressing.
- **Trade-off:** the user gets a second scenario rather than an edited one. Honest and reviewable.

## D-019 - A hand-written `useResource` plus a boundary normaliser, not schema codegen **(Gate 3)**

- **Problem:** the generated `packages/contracts/types.ts` covers domain models but not HTTP
  envelopes, and marks defaulted list fields optional (correctly - Pydantic declares
  `default_factory`).
- **Decision:** import generated types unmodified; declare only the response envelopes by hand
  (documented in `src/api/types.ts`); normalise results once at the client boundary
  (`src/api/normalize.ts`) so components never read `undefined.length`.
- **Why:** the alternative - regenerating schemas - would have required changing the backend
  generator that Gate 2 already verifies for determinism.
- **Evaluation:** `tests/api-client.test.ts` asserts the client's routes against the generated
  `openapi.json`, so hand-written envelopes cannot drift silently.
---

## D-020 - The backend serves the materialised phase graph **(Gate 4)**

- **Problem:** `GET /projects/{id}/graph` returns the **base** graph. Gate 3 clients therefore
  reconstructed a phase by toggling closures from `Phase.closed_edge_ids` in the browser. Gate 4
  forbids that: graph state must come from the authoritative phase graph.
- **Options:** (a) keep client-side toggling; (b) add `GET /scenarios/{id}/phases/{phase_id}/graph`.
- **Decision:** (b). The endpoint materialises the phase with the existing
  `build_phase_graph()` and returns its edges, closures, active temporary edges, crossings and
  both the phase-graph id and its content hash.
- **Why:** one source of truth. It also makes the phase-graph *identity* visible to the client,
  which is what lets the timeline assert that two different phases really are different graphs.
- **Trade-off:** one more request per phase switch, mitigated by the resource hook's abort.
- **Evidence:** `apps/api/tests/test_phase_reads.py::TestPhaseGraph` (9 cases).

## D-021 - A timeline read instead of N+1 client requests **(Gate 4)**

- **Problem:** phase identity, order, closures and "has this phase been analysed?" all needed
  separate reads; a client would have to load the scenario, the run list and then N phase graphs.
- **Decision:** `GET /scenarios/{id}/timeline` returns the ordered phases with their declared
  modifications, phase-graph identity and per-phase analysis state in one payload.
- **Key rule:** the state for an unanalysed phase is the literal `NOT_ANALYSED`, which is *not* a
  verdict. A phase whose only runs belong to an older revision reports `stale: true` rather than
  pretending to be current.
- **Trade-off:** the timeline must materialise every phase graph to report its hash. For the seeded
  9-node graph that is negligible; for a very large graph the endpoint would want caching later.

## D-022 - Temporal analysis is presentation logic, not rule logic **(Gate 4)**

- **Problem:** "when does accessibility get lost" needs cross-phase comparison, but the browser
  must never produce authoritative verdicts.
- **Decision:** `src/lib/temporal.ts` compares **already-computed** `AnalysisResult` payloads and
  classifies the difference. It never evaluates a rule and never invents a route.
- **Explicit non-claims:** a changed edge beside a changed route is reported as a *relevant
  change*, not a unique root cause - a route may depend on several edges at once. Distances are
  reported only when the backend proved a route on both sides; no distance is aggregated across
  phases.
- **Why:** keeps invariant 6 (the frontend never produces verdicts) intact while still giving the
  reviewer a cross-phase answer.
- **Evidence:** `apps/web/tests/temporal.test.ts` (32 cases, incl. every transition pair).

## D-023 - `Phase.order` is the only temporal authority **(Gate 4)**

- **Decision:** ordering comes from `Phase.order` everywhere - the timeline, the impacts, the
  continuity matrix and the first-problematic-phase search. A new `Scenario.ordered_phases()`
  makes this explicit in the domain so no caller re-implements it.
- **Why:** `docs/PHASE_MODEL_AUDIT.md` established that orders are unique but **not necessarily
  contiguous**, so `order == index` and any lexicographic sort of ids or labels would be wrong.
- **No calendar:** no start dates, durations or scheduling exist in the domain and none were
  invented. The explorer is an ordered sequence, not a Gantt chart.
- **Evidence:** `test_non_contiguous_and_reordered_phases_sort_by_order_not_id`,
  and the frontend tests for ordering by `order`.

## D-024 - Scenario selection is never silently overridden **(Gate 4)**

- **Problem (found by E2E-G4-10):** the workspace adopted the first scenario whenever the current
  selection was not present in the just-refreshed list. Creating a branch and selecting it
  immediately therefore reverted the selection to `scn-demo-baseline`, and the next edit was applied
  to the **source** scenario - silently breaking branch isolation.
- **Decision:** a scenario is adopted automatically only while nothing is selected. An explicit
  selection is never overridden by a list that has not caught up.
- **Why:** a wrong write to the wrong scenario is the most damaging class of bug in this product.
- **Prevention:** branch-isolation E2E tests assert the source's revision *and* content hash are
  unchanged after editing the child.

## D-025 - Branch creation copies the declared plan, not the edits **(Gate 4)**

- **Decision:** `POST /projects/{id}/scenarios` from an existing scenario copies phases,
  origins/destinations and temporary edges, and records `parent_scenario_id`. It does **not** copy
  `edits`.
- **Why:** a branch is "an alternative plan", i.e. a different arrangement from the same declared
  sequence. Copying accumulated edits would make it impossible to model "what if we had done this
  differently from the start".
- **Trade-off:** to continue from a specific edit, the engineer applies that edit to the new branch.
- **Evidence:** `E2E-G4-09`, `E2E-G4-10`, and the backend branch tests from Gate 3.

## D-026 - The intervention library is immutable versioned data, validated on load **(Gate 5)**

- **Problem:** an intervention catalogue embedded in code could drift from the contract, and an
  effect the contract forbids could be applied silently.
- **Decision:** `data/demo/interventions.demo.json` (`DEMO_INTERVENTIONS_NOT_ENGINEERED`, version
  `1.0.0`) is loaded and validated on every use: unique ids, no dangling `requires`, no cycles, no
  unknown keys, every effect op inside `allowed_ops`, every target inside `target_element_ids`, and
  no enabled intervention without an effect.
- **Key rule:** the library is demo fixture data (`constructible_in_field: false`, costs
  `demo_only`); it never claims field constructibility. Eligibility is a backend decision the
  browser only displays.
- **Trade-off:** each request re-reads and re-validates a small file - negligible at this size, and
  it makes the data self-checking.
- **Evidence:** `test_bundled_library_loads_with_unique_validated_entries` plus the seven
  `test_library_rejects_*` tests; `test_lists_library_with_eligibility_reasons_and_cost_discipline`;
  E2E-G5-01/02/03.

## D-027 - A candidate is a derived in-memory scenario verified by the unmodified pipeline **(Gate 5)**

- **Problem:** an optimiser that scored candidates with its own logic would be a second, unaudited
  source of verdicts.
- **Decision:** for each combination the engine materialises a derived `Scenario` (source declared
  plan + source edits + intervention effects) and runs the real `build_phase_graph` ->
  `run_analysis` for every selected profile. Before/after analyses are compared; the optimisation
  package never evaluates a rule or builds a route itself.
- **Key rule:** no cached or synthetic result is ever substituted for an analysis run; per-profile
  semantic hashes of the comparison body are recorded for later re-verification.
- **Trade-off:** each candidate costs a full analysis run (~10 combinations x 2 profiles is about a
  second on the demo graph); that is the price of not having a second verdict engine.
- **Evidence:** `test_demo_phase_one_semantics`, `test_search_never_mutates_the_source_scenario`,
  `test_happy_path_reverifies_and_never_touches_the_source`, E2E-G5-08.

## D-028 - Hard constraints reject; introduced UNKNOWNs are never certified **(Gate 5)**

- **Problem:** "best" must not be able to buy a hard-constraint violation with a benefit, and an
  unresolved element must never be reported as a pass.
- **Decision:** `rejected` on any regression of a confirmed **or possible** pair, any new hard
  model-FAIL, an invalid effect, an evaluation error or a budget refusal. `requires_verification`
  when the candidate introduces elements whose verdicts are UNKNOWN, or when every benefit exists
  only in the possible graph. `certified` only with no regression, no new hard FAIL, no introduced
  UNKNOWN and at least one confirmed restoration or comparable shortening. Otherwise
  `no_improvement`.
- **Key rule:** `certified` describes performance against the model objective in this revision,
  never legal or engineering approval. Restoration may hold for a subset of profiles; the ranking
  prefers improvements that hold for every selected profile.
- **Trade-off:** fewer certified candidates - e.g. `{CURB, BACKLANE}` restores both pairs but
  introduces two UNKNOWN verdicts, so it is `requires_verification`.
- **Evidence:** `test_demo_phase_one_semantics`,
  `test_requires_verification_candidate_is_promotable_and_labelled`, E2E-G5-05/06/07.

## D-029 - Ranking is lexicographic and weight-free; monetary ranking is off by default **(Gate 5)**

- **Problem:** a hidden weight makes the result unauditable, and a weighted score would mix demo
  prices into decisions they must not silently drive.
- **Decision:** `DETOUR_LAB_LEXICOGRAPHIC_V1` applies the documented order (classification group ->
  all-profile restorations -> any-profile restorations -> new hard FAILs -> introduced UNKNOWNs ->
  regressions -> intervention count -> optional nominal cost -> comparable added distance ->
  `proposal_id`) and returns that order verbatim in every response.
- **Key rules:** cost participates only when `monetary_objective = "nominal"` is explicitly
  requested; unknown values sort after known ones and are never treated as zero; `tie_group` groups
  candidates equal on every measured axis and excludes the `proposal_id`; the Pareto frontier uses
  only restoration, intervention count and comparable distance.
- **Trade-off:** lexicographic order is opinionated (classification first); it is documented and
  replayable instead of tunable.
- **Evidence:** `test_classification_group_then_restoration_decides`,
  `test_restoration_counts_and_tie_groups`, `test_intervention_count_beats_distance_by_policy`,
  `test_pareto_domination_removes_dominated_candidates`, E2E-G5-04/14/23.

## D-030 - Budget is a hard filter on a stated basis; unknown cost is never zero and never converted **(Gate 5)**

- **Decision:** declared cost lines produce a nominal and a conservative-maximum figure only where
  a price is declared; unknown cost is `null` with `cost_unknown: true`. A budget (`nominal` or
  `conservative_max`) filters candidates: `exceeds` rejects with the figure and basis stated;
  `cannot_certify_unknown_cost` rejects with an explicit reason. A budget in a currency no declared
  cost uses is `400 INVALID_BUDGET_CURRENCY` - no exchange rate is invented.
- **Key rule:** a zero budget rejects every candidate that declares any cost; no request can make
  an unpriced candidate "fit".
- **Evidence:** `test_unknown_cost_is_never_treated_as_zero_or_fitting`,
  `test_zero_budget_rejects_any_known_cost`,
  `test_zero_budget_rejects_every_candidate_and_says_why`,
  `test_budget_currency_mismatch_is_invalid_input`, E2E-G5-12/13.

## D-031 - Searches persist an execution id and a semantic hash; replay is the stored payload **(Gate 5)**

- **Decision:** every accepted search is written to `optimization_runs` (migration 2) with its
  canonical payload, `input_hash`, `semantic_hash`, evaluation instant and duration. The execution
  id `opt-<uuid12>` is distinct per request; the semantic hash is equal for equal inputs.
- **Key rule:** `GET /optimization/searches/{search_id}` serves the stored row verbatim - replay
  never re-runs the engine, and promotion reads the stored outcome rather than recomputing it.
- **Trade-off:** payloads duplicate derived data; storage is small here and replay becomes
  observable and testable.
- **Evidence:** `test_search_persists_and_replays_identically`,
  `test_two_searches_both_persisted_with_distinct_execution_ids`,
  `test_restart_replay_reads_back_the_identical_payload`, E2E-G5-10/11/25.

## D-032 - Promotion applies a re-verified clone with edits, never the source **(Gate 5)**

- **Problem:** promoting a candidate must not mutate the scenario under discussion, must preserve
  what the source already contains, and must not accept a stale or unreproducible preview.
- **Decision:** `POST /optimization/promote` re-materialises the candidate from the current source,
  requires its content hash to equal the recorded preview hash, writes a new scenario (source
  declared plan + **source `edits`** + intervention effects, `parent_scenario_id`, revision 1) in
  one transaction, then re-analyses the persisted branch for every selected profile.
- **Key rules:** source moved since the search -> `STALE_SEARCH`; moved since the caller's view ->
  `STALE_REVISION`; id taken -> `SCENARIO_ID_EXISTS`; rejected candidate -> `CANDIDATE_REJECTED`;
  the source revision and content hash are unchanged afterwards. Preview-vs-persisted comparison
  excludes exactly `scenario_id`, `phase_graph_id` and `scenario_hash` (scenario identity/revision
  labels) while everything content-based must match exactly (P-23).
- **Distinction:** this is the Fix-This-Plan path and preserves the source's edits; ordinary branch
  creation intentionally copies the declared plan without edits (D-025).
- **Evidence:** `test_happy_path_reverifies_and_never_touches_the_source`,
  `test_requires_verification_candidate_is_promotable_and_labelled`,
  `test_stale_expected_revision_writes_nothing`, `test_duplicate_branch_id_is_409_and_writes_nothing`,
  `test_rejected_candidate_is_409_with_reasons`,
  `test_source_edits_phases_and_declarations_survive_promotion`, E2E-G5-15..20/24.

## D-033 - Search limits are echoed, and a truncated search never claims optimality **(Gate 5)**

- **Decision:** `SolverStatus` is derived from coverage, not optimism.
  `OPTIMAL_IN_ENUMERATED_DOMAIN` only after the complete declared domain was enumerated;
  a hit limit yields `FEASIBLE_NOT_PROVEN_OPTIMAL` (or `NO_FEASIBLE_IN_ENUMERATED_DOMAIN` when
  nothing passes); duration exhaustion or evaluation errors yield `INCOMPLETE_OR_UNKNOWN`.
  `limits_hit`, `domain.truncated_by`, `status.notes` and `scope_note` (single phase, selected
  profiles, this revision; a single-phase improvement is not whole-project continuity) are returned
  and rendered.
- **Why:** a bounded search that hides its bound is an unbounded claim.
- **Evidence:** `test_candidate_limit_truncation_never_claims_optimality`,
  `test_duration_limit_truncation_is_incomplete_not_empty`,
  `test_optimal_upgrade_requires_exhaustive_enumeration`, E2E-G5-22.

## D-034 - The evidence queue is derived from the resolver and carries no score **(Gate 6)**

- **Problem:** reviewers need to know which missing measurements actually block decisions. The tempting
  answer — a numeric importance score — implies a value of information the system cannot compute.
- **Decision:** `derive_evidence_queue` recomputes from the same authoritative inputs the analysis used.
  Unresolved status comes from `resolve_attribute`; the queue never re-implements the resolver.
  Ordering is `ORDERING_RULE`: ascending explainable category
  (`decision_blocking < decision_relevant < supporting`), then descending affected profiles, phases
  and connected OD pairs, then ascending element id and attribute.
- **Key rules:** no probability, expected value or numeric score is emitted or implied. A conflict is
  explained **without choosing a value**. An unresolved attribute is never rendered as a physical
  defect. `additional_phases` widens scope but never invents entries.
- **Trade-off:** a reviewer cannot rank by a single number. In exchange the ordering is reproducible,
  explainable and does not pretend to know the value of a field visit.
- **Evidence:** `test_queue_is_derived_not_static`, `test_no_numeric_priority_score_is_emitted`,
  `test_ordering_is_stable_and_documented`, `test_conflict_explains_without_choosing`,
  E2E-G6-03/04/05.

## D-035 - A queue issue keeps one identity across scopes **(Gate 6)**

- **Problem:** with `phase_ids` and `profile_ids` inside the identity hash, the same unresolved
  attribute got a different `issue_id` for every scope, so an inspected row could not be linked back
  to and a deep link broke.
- **Decision:** identity covers element, attribute and resolver status only. Where and how often the
  issue persists is payload, not identity.
- **Why:** an identifier must mean "the same thing". Scope is how you are looking at it.
- **Status:** implemented **after** the last commit and **never executed**; see
  `FAILURE_LAB_DESIGN.md` §I and P-33. The regression guard
  `test_issue_identity_survives_a_scope_change` was added during this audit because the
  pre-existing `test_queue_identity_is_deterministic` derives the queue twice with the
  *same* selection and would have passed against the pre-fix implementation too.

## D-036 - Faults are typed bounded data; there is no code path from a definition to execution **(Gate 6)**

- **Problem:** a "try to break my plan" feature invites an extensible fault language, which is the
  shortest route to arbitrary code execution from a request body.
- **Decision:** `FaultDefinition` is a validated record with a closed `FaultKind`. The contract has
  **no expression field at all**, so no definition can carry code. Validation refuses unknown kinds,
  non-existent targets, undeclared phases, duplicate and contradictory faults, masking a
  non-existent observation, already-closed edges and expiration without an explicit instant, each
  with a named test. Bounds: fault count per experiment, target count per fault.
- **Trade-off:** the fault vocabulary is closed, so adding a fault kind is a code change. That is the
  intended cost of "nothing here executes anything you wrote".
- **Evidence:** `test_no_expression_field_exists_on_the_contract`, `test_fault_count_limit`,
  `test_target_limit`, 12 × refusal tests.

## D-037 - Suites are authored data, and inapplicable is not the same as passing **(Gate 6)**

- **Decision:** `SUITES` is nine hand-written entries naming a fault kind, its target ids and a written
  rationale. Nothing inspects the graph to invent a hazard. Three conditions are declared
  **deliberately not modelled** in `UNSUPPORTED_SCENARIOS` with reasons.
- **Key rule:** `available_suites` computes readiness **structurally against the live graph, per
  selected phase**. A suite that applies nowhere in the selection is reported as unavailable with a
  reason and is **not rendered as a runnable toggle**. When `phase_ids` is omitted every declared
  phase is considered, because a suite that applies somewhere in the plan is not inapplicable to the
  plan.
- **Why:** the failure mode this gate exists to avoid is a panel that shows nine green ticks because
  nine suites ran, when in fact one refused and eight never applied.
- **Trade-off:** fewer suites are offerable at a time. That is the honest number.
- **Status:** per-phase readiness implemented **after** the last commit and **never executed**
  (P-34). `available_suites` had **no unit test at all** until this audit added six readiness
  tests; E2E-G6-08 now also cross-checks the backend catalogue rather than only the rendering.

## D-038 - Three extra fault behaviours are natural divergence, not special cases **(Gate 6)**

- **Problem:** the PRD asks for more fault variety than a closure/mask pair provides, and the
  tempting move is a per-kind branch in the engine.
- **Decision:** no such branch exists. Multi-phase behaviour is the existing `phase_ids` scope;
  profile-specific outcomes are whatever the **real rulepack** produces for that profile; candidate
  stress is the same machinery applied to a branch rather than the source.
- **Why:** divergence that comes from real machinery is evidence the pipeline works; divergence
  special-cased per kind is evidence the special case was written. The limitation is documented rather
  than papered over.
- **Evidence:** `test_multi_phase_fault_touches_only_its_own_phase`,
  `test_profile_specific_outcome_emerges_from_the_rulepack`,
  `test_every_suite_leaves_the_source_untouched`.

## D-039 - Execution status and engineering observation are separate fields **(Gate 6)**

- **Problem:** collapsing "the software ran" and "the network is fine" produces reports that call a
  resolver bug a network failure.
- **Decision:** `ExperimentStatus` (`completed` / `invalid_experiment` / `execution_failed`) is the
  software outcome. `EngineeringObservation` is the modelled outcome of one (profile, OD pair, phase)
  transition. A refused experiment carries zero observations and a named error code. A baseline failure
  is an engine result, never a network failure. Missing data renders as "not established", never 0 m.
- **Key rule:** robustness counts include **only** completed experiments; invalid and failed ones are
  excluded from every count because they are evidence about the software, not about the plan.
- **Evidence:** `test_a_baseline_failure_is_a_software_outcome_not_a_network_failure`,
  `test_a_faulted_failure_leaves_the_pair_unavailable_not_failed`,
  `test_pair_observation_classification_is_total`,
  `test_inapplicable_suite_is_recorded_as_invalid_not_silently_skipped`, E2E-G6-17.

## D-040 - Robustness ratios state their denominator and are never probabilities **(Gate 6)**

- **Decision:** `denominator_note` is built at runtime from the actual execution
  (`pairs_evaluated = N = C completed experiments × OD pairs × profiles × phases`). `INTERPRETATION_NOTE`
  states the counts are a **test-coverage** result over the chosen synthetic conditions and are NOT a
  probability, NOT a failure rate, NOT a statistical result.
- **Why:** "7 of 9 experiments preserved the route" reads as a 78% survival probability unless the
  denominator and the sampling basis are on the same screen.
- **Evidence:** `test_robustness_summary_states_its_denominator`,
  `test_failed_experiments_are_excluded_from_every_count`, E2E-G6-27/30.

## D-041 - ReportLab is used as an existing pinned dependency; no new PDF library **(Gate 6)**

- **Decision:** ReportLab 5.0.1 was already pinned, so the gate adds no dependency. Rendering sets
  `rl_config.invariant = 1` so a stored payload renders byte-identically. Modules split
  `report.py` (model) → `layout.py` (primitives) → `pdf.py` (12-section assembly) → `service.py`
  (collection from stored runs), dependencies one way, with no business logic in `layout.py`.
- **Why:** a renderer that assembles content can invent content by assembling it. Keeping collection
  in `service.py` means the PDF can only draw what the model holds.
- **Trade-off:** the section set is fixed at twelve. A new section is a renderer change.
- **Evidence:** `test_pdf_is_valid_and_parseable`, `test_large_tables_paginate_without_losing_rows`,
  `test_untrusted_text_cannot_execute_or_break_the_document`.

## D-042 - `report_id` is excluded from the semantic payload **(Gate 6)**

- **Decision:** `report_id` (`rpt-<uuid12>`) is the execution identity and is **not** part of
  `ReviewReport.semantic_body()`. Two packets built from the same data share one semantic hash; their
  PDFs differ only in the cover identifier. `schema_version` and `generator_version` are separate
  fields so a stored packet cannot be confused with one from a later renderer.
- **Why:** hashing the id would make every regeneration "a different report", which defeats an audit
  trail whose purpose is to show that the same data yields the same conclusion.
- **Trade-off:** two packets are content-identical by hash and must be told apart by `report_id`. The
  UI labels a packet whose scenario has moved on as a historical revision.
- **Evidence:** `test_report_id_is_not_part_of_the_semantic_hash`,
  `test_equivalent_regeneration_preserves_semantic_identity`,
  `test_generation_time_is_excluded_from_the_semantic_payload`.

## D-043 - The PDF download endpoint re-renders from the stored payload and verifies the digest **(Gate 6)**

- **Decision:** `GET /reports/{id}/document.pdf` reloads the stored **payload**, re-renders it,
  recomputes the digest and compares it with the recorded `pdf_sha256`. A mismatch is a 500
  `PDF_RENDER_FAILED` naming both digests — never a silent re-issue. Responses carry
  `X-Detour-Lab-Pdf-Sha256`, `X-Detour-Lab-Pdf-Pages`, `X-Detour-Lab-Semantic-Hash`,
  `X-Detour-Lab-Scenario-Revision` and `X-Detour-Lab-Not-Certified: true`.
- **Why:** serving a stored blob proves only that the blob still exists. Re-rendering proves the
  renderer is still deterministic, and the digest check makes a drift visible instead of invisible.
- **Evidence:** `test_download_endpoint_returns_the_recorded_bytes`,
  `test_regenerating_a_stored_report_reproduces_identical_bytes`, E2E-G6-23.

## D-044 - An unselected report section is marked unavailable, never rendered empty **(Gate 6)**

- **Decision:** `section_availability` carries `available` / `unavailable` / `not_selected` with a
  reason per section, and the PDF prints the reason in place of the section body.
- **Why:** an empty section reads as "there is nothing to report". A reviewer must be able to tell
  "not selected" from "selected and empty", because only the first is a coverage gap in the packet.
- **Evidence:** `test_unselected_sections_are_marked_unavailable_not_empty`, E2E-G6-24.

## D-045 - A taken scenario id is a 409 conflict, never a 500 **(Gate 6)**

- **Problem:** `POST /projects/{id}/scenarios` inserted without checking the id, so a duplicate
  reached the `INSERT` and escaped as an uncaught `sqlite3.IntegrityError` — a 500 with no error
  code, in a repository whose sibling path (`promote_scenario`) had always returned a typed 409
  `SCENARIO_ID_EXISTS` for the same condition.
- **Decision:** `repository.create_scenario` performs the same in-transaction clash check as
  `promote_scenario` and raises `ScenarioIdExistsError`; the route converts it to **409
  `SCENARIO_ID_EXISTS`** with the standard flat envelope and `details.scenario_id`. The check
  runs inside the transaction, so a refused creation writes nothing.
- **Why:** a unique-constraint violation is a fact about the request, not a server fault. A
  caller can act on "that id is taken" — pick another id, or open the existing scenario — but
  cannot act on an untyped 500. A typed error is also the only kind a client can display
  honestly.
- **Key rule:** the *conflict* is reported; the *fact* is not invented. The refused request
  changes nothing, and the existing scenario keeps its revision and content hash.
- **Evidence:** `test_a_duplicate_scenario_id_is_a_409_not_a_500`; E2E-G6-04 asserts the same
  contract over HTTP. **Not yet executed** — see `FAILURE_LAB_DESIGN.md` §I.
- **Prevention:** two repository paths that write the same table must share their conflict
  handling. The gap existed because only one of them had a test.