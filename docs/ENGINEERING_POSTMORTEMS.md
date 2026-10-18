# ENGINEERING_POSTMORTEMS.md

Genuine failures encountered while building DETOUR LAB, with the observed error, root cause,
correction and the regression test that now prevents recurrence. Nothing here is invented.

---

## P-01 — A class and a type alias with the same name silently broke a Pydantic field

- **Observed:** `CoordinateBasis.model_validate({...})` raised
  `ValidationError: kind — Input should be a valid dictionary or instance of CoordinateBasis`,
  with `input_value='local_planar_meters'` — i.e. the value being rejected was the string that
  the field was supposed to accept.
- **Root cause:** `contracts.py` defined `CoordinateBasis = Literal["local_planar_meters",
  "wgs84_degrees"]` and then `class CoordinateBasis(StrictModel)`. Because of
  `from __future__ import annotations`, the field annotation `kind: CoordinateBasis` was stored as
  the *string* `"CoordinateBasis"` and resolved at validation time against the module globals —
  where the name now referred to the **class**, not the alias.
- **Correction:** renamed the alias to `CoordinateBasisKind`.
- **Regression test:** `tests/test_ingestion.py` and every fixture that loads a coordinate basis.
  The failure is loud at import-of-data time rather than silent.

## P-02 — PowerShell wrote a UTF-8 BOM into a JSON rulepack

- **Observed:** `json.decoder.JSONDecodeError: Unexpected UTF-8 BOM (decode using utf-8-sig)`.
- **Root cause:** `Set-Content -Encoding utf8` under Windows PowerShell 5.1 emits a BOM.
- **Correction:** rewrote the file through Python `pathlib.write_text(..., encoding="utf-8")`
  (no BOM) and verified the first bytes are `{\r\n`.
- **Prevention:** JSON/rulepack files are now only written by Python in this repository.

## P-03 — Two different phase graphs could share one content hash

- **Observed:** `assert phase_graph.content_hash != base_graph.content_hash` failed — a phase graph
  with a closure hashed identically to the open baseline, because `BaseGraphVersion._semantic_body`
  did not include the closure set.
- **Root cause:** closures lived on `PedestrianGraph` as a field *outside* the hashed version body.
- **Correction:** moved closures into `BaseGraphVersion.inactive_edge_ids` and included it in the
  hash; `PedestrianGraph.closed_edge_ids` is now a read-only property derived from the version, so
  the two cannot disagree.
- **Regression test:** `test_inactive_edges_are_part_of_the_version_and_its_hash`,
  `test_phase_graph_has_its_own_content_address`.

## P-04 — Deterministic edit ordering ignored edit dependencies

- **Observed:** `GraphEditError: unknown endpoint node 'N_NEW'` when a scenario added a node and an
  edge that used it. Canonical key ordering sorted `add_edge` before `add_node`.
- **Root cause:** determinism was implemented as "sort by canonical key", which conflicts with
  dependencies (and would also have applied `add_edge:E` before `remove_edge:E`).
- **Correction:** added `order_edits()` — a stable topological sort that repeatedly takes every edit
  whose declared dependencies are satisfied, in canonical key order within each round, and raises
  `CYCLIC_DEPENDENCY` if it stalls.
- **Regression test:** `test_edit_order_does_not_change_the_result`,
  `TestTypedEdits.test_add_edge_with_unknown_endpoint_is_rejected`.

## P-05 — A defaulted "now" invalidated every record under a freshness policy

- **Observed:** every crossing interface evaluated `UNKNOWN`, including one with a perfectly good
  `zebra_marked` observation dated 2026-01-05.
- **Root cause:** `evaluate_graph(as_of=None)` meant "no evaluation time supplied", and the
  resolver treated that as "staleness cannot be excluded" → UNKNOWN for any attribute with a
  freshness policy. Silent, and it would have made results depend on the wall clock.
- **Correction:** `as_of` is now a **required** parameter of `run_analysis` and `evaluate_graph`,
  documented as the instant at which freshness is judged and recorded in the run.
- **Regression test:** `test_a_different_as_of_is_recorded_not_hidden` (2032 evaluation date expires
  the 5-year crossing policy).

## P-06 — Reported route "distance" included preference weights

- **Observed:** `OD-W -> OD-LIB` reported `99.0` metres for a 98-metre route.
- **Root cause:** `shortest_path` returned the preference-weighted cost in its `distance_m` field.
- **Correction:** `PathResult` now carries `distance_m` (sum of physical segment lengths) and
  `cost` (ranking cost) separately; `ODPairResult` exposes `confirmed_route_cost` alongside
  `confirmed_distance_m` with an explicit `route_note`.
- **Regression test:** `test_reported_distance_is_physical_not_preference_weighted`.

## P-07 — The demo rulepack did not cover `temporary_path` edges

- **Observed:** the modelled temporary footway evaluated as `NOT_APPLICABLE` with zero checks and
  generated a "no hard rule applies" warning, so no candidate could ever be confirmed.
- **Root cause:** edge-type applicability lists covered sidewalk/shared-use/crossing/ramp only.
- **Correction:** `temporary_path` added to all eight edge rules. The engine behaviour itself was
  correct — it warned instead of silently passing — which is the behaviour we want.
- **Regression test:** `test_b10_temporary_edge_exists_only_in_its_declared_phase` plus the
  phase-2 assertions in `test_inv03_closed_edge_is_never_routed_through`.

## P-08 — Equal-cost pruning silently broke the documented tie-break

- **Observed:** on a graph with two equal-length routes, the lexicographically smaller edge-ID
  sequence was sometimes not selected.
- **Root cause:** `shortest_path` pruned any candidate whose distance was `>=` the best known
  distance for the target node, so an equal-cost alternative discovered later never entered the
  heap.
- **Correction:** prune only strictly worse candidates (`>` with a 1e-12 tolerance), so equal-cost
  alternatives stay in the heap and the documented `(distance, edge-ID sequence)` order decides.
- **Regression test:** `test_tie_between_equal_length_paths_breaks_lexicographically`,
  `test_tie_break_is_independent_of_construction_order`, plus the Hypothesis permutation test.

## P-09 — A mistyped output path created a stray directory

- **Observed:** a test file was written to `C:\Prathom\DETOUR-LAB\...` (missing "a").
- **Root cause:** manual path transcription.
- **Correction:** file moved to the repository and `C:\Prathom` deleted; verified no sibling
  project directory was touched.
- **Prevention:** repository-relative paths are resolved from the tool's working directory.

---

## P-10 — Two different error shapes from the same API

- **Observed:** `GET /api/v1/runs/unknown` returned `{"code": ...}` at the top level, while a
  Pydantic validation failure returned `{"detail": [...]}`, and a handler-raised `HTTPException`
  returned `{"detail": {"code": ...}}`.
- **Root cause:** Custom exception handlers bypass FastAPI's default `{"detail": ...}` wrapping,
  so each new handler silently introduced another shape.
- **Correction:** Added a `StarletteHTTPException` handler and a `RequestValidationError` handler
  that both emit the same flat `{code, message, details, request_id}` envelope.
- **Regression test:** `test_every_error_uses_the_same_envelope`.

## P-11 — Graph version IDs collided across projects

- **Observed:** `sqlite3.IntegrityError: UNIQUE constraint failed: graph_versions.id` when a second
  project imported the same dataset (both declare `graph_version_id: demo-graph-v1`).
- **Root cause:** `graph_versions.content_hash` was globally `UNIQUE` and the ID was taken as
  globally unique, but identical content legitimately belongs to two projects.
- **Correction:** uniqueness moved to `(project_id, content_hash)`; a colliding ID is deterministically
  suffixed with the content hash rather than mutating or rejecting.
- **Regression test:** `test_create_project_then_import_dataset`,
  `test_duplicate_content_is_not_stored_twice`.

## P-12 — Evidence record IDs were globally unique

- **Observed:** `UNIQUE constraint failed: evidence.record_id` when the same evidence set was stored
  under a second graph version.
- **Root cause:** `record_id` was the sole primary key, but evidence IDs are unique *per graph
  version*, not globally.
- **Correction:** primary key changed to `(graph_version_id, record_id)`.
- **Regression test:** `test_unknown_unit_surfaces_as_unknown_not_as_a_pass` (imports a modified
  dataset into a second project).

## P-13 — Invalid edits were accepted and only failed later

- **Observed:** `PATCH /scenarios/{id}` returned 200 for an edit referencing a non-existent node;
  the failure only surfaced at the next evaluation.
- **Root cause:** the endpoint persisted edits without constructing the phase graph.
- **Correction:** a prospective scenario is validated for every declared phase before anything is
  written; invalid edits return 422 and leave history untouched. This also surfaced a genuine
  modelling rule: removing an edge that a declared phase closes is now an explicit rejection.
- **Regression test:** `test_cyclic_or_invalid_edit_returns_422`,
  `test_removing_an_edge_that_a_phase_closes_is_rejected`.

---

## Not yet encountered / not yet fixed

- `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated; install
  httpx2 instead` — emitted by FastAPI's own test client. Harmless today; the API contract tests
  pass. Revisit when FastAPI/Starlette ship the successor transport.
---

## P-14 - Editing a scenario silently renamed it (Gate 3)

- **Symptom:** after one scenario edit, the frontend's scenario list reported an id of
  `scn-demo-baseline#r2`, and the follow-up fetch of that id returned 404. The planning UI showed
  "No scenario selected" even though the scenario existed.
- **Root cause:** `Repository.apply_scenario_edit` rebuilt the scenario payload and set
  `payload["id"] = f"{scenario_id}#r{revision}"` and `parent_scenario_id = scenario_id`. The row key
  stayed the original id, but the stored payload's own id changed, so `list_scenarios` began
  advertising an id that `get_scenario` could not resolve. Gate 1-2 tests never caught it because
  they asserted on the returned payload rather than on the list-then-fetch round trip.
- **Minimal reproduction:** `PATCH /api/v1/scenarios/scn-demo-baseline` with one edit, then
  `GET /api/v1/projects/demo-project-synthetic/scenarios` and fetch the returned id.
- **Fix:** an edit now changes only `revision`, `content_hash`, `note` and `edits`. Identity is
  stable; branching to a different scenario remains an explicit operation.
- **Regression test:** `test_editing_does_not_rename_the_scenario`, plus the Playwright demo
  journey, which saves an edit and then reloads.
- **Prevention:** any endpoint a client can follow must be round-trip tested through the *list*
  endpoint, not only by direct id.

## P-15 - Degenerate graph bounds produced an infinite view transform (Gate 3)

- **Symptom:** `fitBounds` returned `scale = Infinity` for an empty graph, so the SVG viewBox and
  every projected coordinate became non-finite.
- **Root cause:** `EMPTY_BOUNDS` reported `width: 0, height: 0` and `fitBounds` divided by it
  without a floor.
- **Fix:** the empty bounds carry the same minimum span as a single-point graph, and `fitBounds`
  floors both axes defensively.
- **Regression test:** `fitBounds > never produces an infinite transform for degenerate bounds`
  and `renders an empty graph without crashing`.

## P-16 - One malformed coordinate discarded valid extent on the other axis (Gate 3)

- **Symptom:** a node with `x = NaN` but a valid `y` caused `computeBounds` to drop that node
  entirely, shrinking the fitted view around the wrong data.
- **Root cause:** the coordinate pair was validated as a unit instead of axis by axis.
- **Fix:** each coordinate is checked independently; only non-finite values are dropped.
- **Regression test:** `computeBounds > ignores non-finite coordinates rather than poisoning the
  bounds`.

## P-17 - The E2E helper read results from the previous run (Gate 3)

- **Symptom:** a profile-switching test passed against stale numbers: switching from profile A to
  profile B appeared to change nothing.
- **Root cause:** the helper waited only for the reachability table to be *visible*, which it
  already was, because the previous run's result stays on screen while the next run is in flight.
- **Fix:** the helper now waits for the returned run identity to match the requested profile and
  phase, and asserts that a fresh run id was produced.
- **Prevention:** an assertion on "something is rendered" is not an assertion on "the thing you
  asked for arrived"; wait on the identity of the result.

## P-18 - Panels were clipped and the workspace overflowed the viewport (Gate 3)

- **Symptom:** the run-identity and reachability tables were cut off mid-row, and the document was
  131 px wider than a 390 px viewport.
- **Root cause:** flex and grid children default to `min-width/min-height: auto`, so dense tables
  forced their panels wider than the column and stretched the shell past `100vh`.
- **Fix:** panels are constrained with `min-width: 0`, keep their natural height, and the main
  region scrolls internally.
- **Regression tests:** `E2E-16 the primary journey works at a small viewport` (asserts zero
  document overflow on three screens) and the visual review of the captured screenshots.
## P-19 - Temporary edges were never flagged in the phase graph **(Gate 4)**

- **Symptom:** `GET /scenarios/{id}/phases/phase-2/graph` reported
  `active_temporary_edge_ids: ["TMP-EAST-BYPASS"]` while no edge carried `temporary: true`.
- **Root cause:** the materialised temporary edge is namespaced (`TMP::TMP-EAST-BYPASS`) to avoid
  colliding with permanent ids, while `active_temporary_edge_ids` holds the *declared* id. The two id
  spaces were compared directly.
- **Fix:** `_is_active_temporary()` accepts either form, so the flag always matches the active set.
- **Regression test:** `test_phase_graph_reports_authoritative_closures_and_temporaries`,
  `test_phase_one_has_no_temporary_edge`, and E2E-G4-02 which asserts exactly one temporary edge in
  phase 2 and none in phase 1.
- **Prevention:** whenever a domain id is transformed during materialisation, the read API must
  reconcile both forms rather than assuming one namespace.

## P-20 - Selecting a scenario silently redirected edits to another scenario **(Gate 4)**

- **Symptom:** creating a branch and editing it advanced `scn-demo-baseline` to revision 2 instead
  of the branch. The branch-isolation E2E failed.
- **Root cause:** the workspace adopted `scenarios[0]` whenever the selected id was not in the
  list currently loaded. After `create branch`, the list had not yet refreshed, so the new selection
  looked "unknown" and was replaced by the first scenario.
- **Impact:** a write landed on the wrong scenario. Branch isolation and source preservation were
  both broken until this was found.
- **Fix:** automatic adoption happens only while nothing is selected
  (`if (scenarioEntries.length === 0 || scenarioId !== null) return`).
- **Regression test:** `E2E-G4-10 modifies the branch without changing its source`, which asserts
  the source's revision and content hash are identical before and after editing the child.
- **Prevention:** any "adopt a default when nothing valid is selected" effect must distinguish
  *nothing selected* from *selection not yet in the refreshed list*.

## P-21 - The first-problem explanation invented a preceding phase **(Gate 4)**

- **Symptom:** for a pair already problematic in the earliest declared phase, the UI read
  "OD-E → OD-GATE is not evaluated in the earlier phase and becomes unreachable in Phase 1".
- **Root cause:** the explanation always assumed a predecessor and formatted a missing previous
  phase as "the earlier phase", producing a sentence that was both wrong and self-contradictory.
- **Fix:** when there is no predecessor, the text states that the pair is *already* in that state in
  the earliest declared phase.
- **Regression test:** `temporal.test.ts` explanation cases plus E2E-G4-08, which asserts the text
  matches either `earliest declared phase` or `becomes`.

## P-22 - An unevaluated phase was not treated as a "first problem" **(Gate 4)**

- **Symptom:** `firstProblematicPhase()` returned `null` when a phase had no analysis, so a reviewer
  got no pointer to the gap even though it is the first place action is needed.
- **Root cause:** only `none` and `possible` set the first-problem marker.
- **Fix:** an unevaluated phase sets it too. The continuity **state** stays `incomplete` - an
  unevaluated phase is never converted into a failure, only into a visible gap.
- **Regression test:** `an unevaluated phase is incomplete, never a pass and never a failure` and
  `says so plainly when the first problem is a missing analysis`.