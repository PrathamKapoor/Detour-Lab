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

## P-23 - Promotion compared scenario identity, so every re-verification mismatched **(Gate 5)**

- **Symptom:** the post-persist re-verification of a promoted branch reported a mismatch between the
  preview analysis and the persisted branch even though the branch had been rebuilt from the same
  source and the re-materialisation hash gate had passed.
- **Root cause:** the comparison used the full `AnalysisResult` payloads. Three fields legitimately
  differ between the preview scenario and the persisted branch because they embed identity, not
  content: `scenario_id` and `phase_graph_id` contain the scenario id (a branch is a new,
  independently addressable scenario by design), and `scenario_hash` covers the scenario `revision`
  (a branch is revision 1 while the preview carries the source's revision label).
- **Fix:** `analysis_comparison_body()` (`optimization/verify.py`) strips exactly those three fields
  for preview-vs-persisted comparison. Preview reproducibility is still enforced strictly *before*
  persistence by requiring the re-materialised content hash to equal the recorded preview hash, and
  everything content-based (phase-graph hash, verdicts, OD results) must still match exactly. A real
  mismatch is still surfaced, never accepted.
- **Regression test:** `test_happy_path_reverifies_and_never_touches_the_source` (asserts the
  verification rows record a match for every profile and the source is untouched) and E2E-G5-15
  ("Reproduces preview" plus "Yes (revision and hash identical)").
- **Prevention:** when comparing two executions across identities, exclude identity-bearing fields
  explicitly and document the reason for each exclusion; never widen an exclusion just to make a
  comparison pass.

## P-24 - An explicit empty profile selection silently meant "all profiles" **(Gate 5)**

- **Symptom:** a search request with `profile_ids: []` evaluated every profile declared by the
  scenario instead of being refused, so the result covered profiles the caller had explicitly not
  selected.
- **Root cause:** optionality was tested with truthiness (`if profile_ids:`), which treats both
  `None` (not supplied) and `[]` (supplied but empty) as "use the default".
- **Fix:** default only when `profile_ids is None`; an explicitly empty selection raises
  `SearchInputError("at least one mobility profile must be selected")`.
- **Regression test:** `test_invalid_inputs_are_explicit` (asserts the error) with
  `test_per_profile_selection_changes_the_restoration_view` covering the valid selection path.
- **Prevention:** use `is None` for "not supplied" and validate the empty case as its own input
  error; a silent reinterpretation of an explicit input is a correctness bug, not a convenience.

## P-25 - The contract generator lost parentheses around union array items **(Gate 5)**

- **Symptom:** a field typed as `list[Literal["candidate_limit", "duration_limit"]]` would have been
  generated as `"candidate_limit" | "duration_limit"[]`. TypeScript parses that as
  `"candidate_limit" | ("duration_limit"[])`, so the generated frontend contract was wrong while the
  API itself was correct.
- **Root cause:** `_ts_type()` formatted arrays as `f"{item_type}[]"` and no earlier contract had a
  union as an array item, so the latent bug was never exercised.
- **Fix:** item types containing `" | "` are parenthesised before the `[]` suffix; the contracts were
  regenerated.
- **Regression test:** a new `TestTypeScriptMapper` case asserts
  `("candidate_limit" | "duration_limit")[]`, and `test_generation_is_byte_identical_on_a_second_run`
  keeps the artefacts deterministic.
- **Prevention:** the generator must be tested against every shape the contracts actually use; a
  generated artefact is only trustworthy when it is regenerated and diffed, not hand-inspected.

## P-26 - An invalid experiment was reported but never persisted **(Gate 6)**

- **Symptom:** a suite that could not be applied (for example `connection_loss` under phase-1) returned
  `status: "invalid_experiment"` with `error.code: "NO_OP_FAULT"` and zero observations — and then
  vanished, because the persistence path only wrote rows for experiments that had completed.
- **Root cause:** the runner accumulated `outcomes` and returned them, while `service.py` filtered the
  persisted set to successful runs. The refusal was real but ephemeral, so the reviewer could not
  re-read it and the history table silently disagreed with the response it had just been given.
- **Fix:** invalid and failed experiments are persisted exactly like completed ones, carrying their
  status, error code and zero observations.
- **Regression test:** `test_inapplicable_suite_is_recorded_as_invalid_not_silently_skipped`;
  E2E-G6-17 asserts the refusal shape over HTTP.
- **Prevention:** anything returned by an operation must be durably retrievable, including its
  refusals. A response the database cannot reproduce is a response nobody can audit.

## P-27 - Every invalid experiment shared the execution id `fxp-invalid` **(Gate 6)**

- **Symptom:** running two inapplicable suites produced two records with the identical execution id
  `fxp-invalid`, so the second overwrote the first in any id-keyed view.
- **Root cause:** the id was generated only on the success branch; the refusal path passed a
  hard-coded placeholder.
- **Fix:** execution ids are allocated for every outcome. The placeholder is gone; an invalid
  experiment is still an execution and has its own id.
- **Regression test:** covered by `test_experiments_are_persisted_and_listed` and the
  distinct-id assertions in `test_failure_lab.py`.
- **Prevention:** an identifier must be minted at the point the record is created, not at the point
  the record succeeds. Identity is not a success-path concern.

## P-28 - Cross-phase persistence detection skipped attributes with no observation **(Gate 6)**

- **Symptom:** an attribute whose absence persisted into a second phase was not annotated as such,
  because the detection only ran for attributes that had at least one observation to re-resolve.
- **Root cause:** the "does this issue also persist here?" check was expressed as "re-resolve the
  observations", which is a no-op when there are none — precisely the case where a missing record is
  the reason the attribute is unresolved.
- **Fix:** cross-phase detection resolves the attribute independently of how many observations exist.
- **Regression test:** `test_in_scope_issue_is_annotated_with_the_phases_where_it_also_persists`.
- **Prevention:** when a check is phrased in terms of its inputs ("for each observation…"), verify it
  still behaves correctly when there are none. The empty case is where such checks usually hide.

## P-29 - Node findings silently disappeared from the review packet **(Gate 6)**

- **Symptom:** the PDF's accessibility-findings section listed only edge-scoped rule verdicts. Findings
  whose rule targets a node — including `N_EK` lacking `curb_transition` — were absent from an
  audit-ready packet that claimed to enumerate findings.
- **Root cause:** `reporting/service.py` rebuilt the findings list from `result.verdicts` filtered to
  edges, because the first finding observed in development happened to be edge-scoped.
- **Fix:** findings are rebuilt from the complete verdict list, node findings included.
- **Regression test:** `test_experiment_details_correspond_to_real_records`, plus the findings
  coverage in `tests/test_reporting.py`.
- **Prevention:** a report built by *filtering* its source must be tested against a case where the
  filtered-out shape is the interesting one. Deriving from a subset is a silent data loss, not a
  presentation choice.

## P-30 - `ReportAlternativePlan` had no semantic hash **(Gate 6)**

- **Symptom:** alternative plans were serialised without their own hash, so a plan could not be
  compared across packets or verified on its own.
- **Root cause:** `ReportAlternativePlan` was added after `ReviewReport` and the hash field was never
  added to it; the omission was invisible because nothing asserted its absence.
- **Fix:** the model carries `semantic_hash`, and contract regeneration picked it up.
- **Regression test:** the optimisation-inclusion test `test_optimization_search_is_included_when_selected`
  exercises the model end to end.
- **Prevention:** a new nested model is not finished until the properties every sibling has are
  present. Diff the field set against a sibling, don't eyeball it.

## P-31 - An exception's text was swallowed by the failure engine **(Gate 6)**

- **Symptom:** an experiment that raised during execution was recorded as `execution_failed` with an
  empty or generic message, so the cause was unrecoverable after the fact.
- **Root cause:** the `except` block built the error record without interpolating the exception.
- **Fix:** the exception type and message are preserved in the stored error.
- **Regression test:** `test_execution_failure_text_is_preserved` (injects a failure via `monkeypatch`
  and asserts the text survives).
- **Prevention:** an error handler that discards the exception is not handling it. If a failure is
  persisted, the reason must be persisted with it.

## P-32 - The isolated scenario had no `base_graph_version_id`, so no phase graph could build **(Gate 6)**

- **Symptom:** every experiment failed during graph construction rather than executing.
- **Root cause:** `build_isolated_state` constructed the derived scenario without carrying
  `base_graph_version_id`, and `build_phase_graph` correctly refuses to build a phase graph when the
  scenario and graph are not paired.
- **Fix:** the isolated state carries the source's `base_graph_version_id`.
- **Regression test:** `test_experiments_run_against_a_distinct_isolated_state`,
  `test_every_suite_executes`.
- **Prevention:** the guard that caught this was correct and should not have been relaxed. When a
  precondition fails immediately after new code, the new code is usually wrong, not the guard.

## P-33 - `issue_id` changed when the phase or profile selection changed **(Gate 6)**

- **Symptom:** selecting a different phase produced different `issue_id`s for the same unresolved
  attribute, so the row a reviewer inspected could no longer be linked, and the detail deep-link
  broke.
- **Root cause:** the queue's identity hash included `phase_ids` and `profile_ids`, i.e. *how many
  times and where* the issue was seen, rather than *which attribute on which element* it is.
- **Fix:** identity covers the element, the attribute and the resolver status only; the observed scope
  is payload, not identity.
- **Regression test:** `test_queue_identity_is_deterministic` is the test to re-run against this
  change (see `FAILURE_LAB_DESIGN.md` §I — this fix is **not yet re-verified**).
- **Prevention:** identity hashes must cover only what makes the thing *the same thing*. Adding a
  field to an identity because it is nearby in the struct is how ids stop being stable.

## P-34 - Suite readiness ignored the selected phase, offering inapplicable suites as runnable **(Gate 6)**

- **Symptom:** with phase-1 selected, `connection_loss` was offered as a runnable suite even though its
  target `TMP-EAST-BYPASS` is active only in phase-2. Running it produced a refusal, which reads as a
  failure of the plan rather than a suite that never applied.
- **Root cause:** `available_suites` evaluated readiness over the scenario's whole declared plan and
  reported a single boolean, so a suite applicable *somewhere* was presented as applicable *here*.
- **Fix:** readiness is computed per selected phase, and a suite that applies nowhere in the selection
  is reported as unavailable with the reason — never as a passing test, never silently skipped.
- **Regression test:** E2E-G6-08 asserts the suite is listed as unavailable **and** that no runnable
  toggle is rendered. **Not yet re-verified** (`FAILURE_LAB_DESIGN.md` §I).
- **Prevention:** an applicability flag is only meaningful relative to the caller's selection. Where
  the answer depends on the context, the context has to be an argument.

## P-35 - The navigation hint failed WCAG AA contrast **(Gate 6)**

- **Symptom:** the nav hint text (`--text-2xs`, well under 18 px) rendered in `--text-muted` on the nav
  item surfaces, measuring **4.33:1** on `--surface-hover` and **4.03:1** on `--surface-selected` —
  both below the 4.5:1 required for normal-size text.
- **Root cause:** the token was chosen for visual subtlety rather than for legibility, and the ratio
  was never measured.
- **Fix:** `--text-secondary` (#a7b6c7), which measures **7.31:1** on `--surface-hover`, **6.27:1** on
  `--surface-selected` and **9.23:1** on `--surface-canvas`. The hint stays visually subordinate
  because it is smaller and lighter in weight, not because it is illegible.
- **Regression test:** automated axe checking (`E2E-G6-28`, WCAG 2.1 AA tags), plus the measured ratios
  recorded in `app.css`. **Not re-run** against this change — see `FAILURE_LAB_DESIGN.md` §I.
- **Prevention:** measure contrast, do not eyeball it, and record the *resulting* ratio next to the
  fix. The original CSS comment quoted 4.33:1 without saying it was a failure, which is how the
  pre-fix number later got misread as the post-fix number — the same value was briefly mistaken for
  evidence the fix had passed when it was evidence it had failed.

## P-36 - The P-33 regression guard could not fail **(Gate 6)**

- **Symptom:** the fix that dropped `phase_ids` and `profile_ids` from the queue's issue identity
  hash shipped with a test that would still have passed against the pre-fix implementation. The
  defect could have been reintroduced with a green suite.
- **Root cause:** `test_queue_identity_is_deterministic` derives the queue twice with the *same*
  phase and profile selection. Identical inputs trivially produce identical ids, whether or not
  the scope is part of the hash. The test proved determinism, not scope-independence — two
  different properties, and only the second one guards the fix.
- **Fix:** added `test_issue_identity_survives_a_scope_change`, which derives the queue over the
  whole plan and over a narrowed selection and asserts that every issue present in both keeps
  its `issue_id`, and `test_issue_identity_is_independent_of_the_analysis_execution`, which
  re-runs the analysis and asserts the issue identities are unchanged.
- **Regression test:** both new tests. **Present, not yet executed** — see `FAILURE_LAB_DESIGN.md`
  §I.
- **Prevention:** a regression guard for a fix must be checked against the pre-fix behaviour. If
  the new test cannot fail on the old code, it is not a guard; it is a restatement. When a fix
  changes what goes *into* a hash, the test must vary the thing that was removed.

## P-37 - `available_suites` shipped with no unit test at all **(Gate 6)**

- **Symptom:** the per-phase readiness change (P-34) altered the fault-suite catalogue contract —
  which suites are offered as runnable, for which phase, with what reason — and no test exercised
  `available_suites` directly. Its behaviour was only reachable through the API and the browser.
- **Root cause:** the catalogue was reached only through incidental paths, so the function looked
  covered by the surrounding experiment and end-to-end tests while its own contract — per-phase
  derivation, the reason string, the invariant that an applicable suite's targets exist — was
  untested.
- **Fix:** six direct tests were added: per-phase derivation, whole-plan behaviour, an
  understandable reason for every unavailable suite, the target-existence invariant,
  determinism with the source graph unchanged, and no state leaking between phases.
- **Regression test:** the six suite-readiness tests in `tests/test_failure_lab.py`.
  **Present, not yet executed.**
- **Prevention:** a function that owns a contract needs a test that names that contract. "The
  feature is covered end-to-end" is not coverage of the decision function in the middle, and an
  untested decision function is where a "never advertised as passing" guarantee quietly dies.

## P-38 - The Gate 6 browser suite, the probe spec and both design docs were never committed **(Gate 6)**

- **Symptom:** the commit history ends at `ecfdda2` "Add the Gate 6 evidence queue, Failure Lab and
  PDF export UI", but `apps/web/e2e/gate6-evidence-failure-report.spec.ts`,
  `apps/web/e2e/gate6-a11y-probe.spec.ts`, `docs/FAILURE_LAB_DESIGN.md` and
  `docs/REPORTING_DESIGN.md` are **untracked**. The repository therefore contains the Gate 6
  implementation without the Gate 6 browser coverage or the design record that explains it. A
  fresh clone would have no Gate 6 E2E suite at all.
- **Root cause:** the implementation was committed in pieces and the new files were never staged.
  Nothing in the workflow compares the working tree against the set of files the gate is supposed
  to add, so a missing file is invisible until someone tries to run the suite.
- **Fix:** the four files are identified explicitly in `FLOW.md` §5h and
  `docs/FAILURE_LAB_DESIGN.md` §I5, and must be staged explicitly in the Gate 6 commit. **The
  commit itself is still outstanding** — the authoring session had no command runner.
  Because the probe file is untracked, the rename to `gate6-contrast.spec.ts` must use
  `Move-Item`; `git mv` refuses a file that is not under version control.
- **Regression test:** none yet. The check that would have caught it is
  `git status --porcelain` being empty after the gate's commit, and a reviewer confirming that
  every file named in the gate's design document is tracked.
- **Prevention:** at the end of a gate, list the files the gate must add and check each one is
  tracked. A commit message describing work is not evidence that the work is in the commit.

## P-39 - The documentation claimed a passing Gate 6 run that no log supported **(Gate 6)**

- **Symptom:** the Gate 6 design documents, the traceability matrix, the test plan, `FLOW.md` and
  `README.md` all stated that the Gate 6 suite was "verified green at `ecfdda2`" with 128 passing
  backend tests. **No preserved log supports that.** The last recorded collection in `var/`
  (`collect.log`, `collect.txt`) is the 373-test Gate 5 baseline and lists no Gate 6 test file;
  the last preserved verification log (`verify-gate5-final.log`) is the Gate 5
  `VERIFICATION PASSED` run. The claim came from a session summary and was copied forward into
  the documentation without ever being checked against an artifact.
- **Root cause:** a handoff summary was treated as evidence. It is a *claim* about a run, and like
  any claim it is only worth what its artifact is worth — which here was nothing, because the
  summary's own session had no command runner and preserved no log.
- **Fix:** every Gate 6 document now states the position accurately: the code and the test
  functions exist, **no Gate 6 run is preserved**, and §I of `docs/FAILURE_LAB_DESIGN.md` lists
  the preserved artifacts and what each one does and does not prove. No Gate 6 row in the
  traceability matrix is marked VERIFIED.
- **Prevention:** a verification claim is only as good as the log behind it. Before writing "N
  tests passed", find the file that says so; if there is no file, the sentence does not belong in
  the document. The cost of the false claim was that it would have been copied into the final
  release report as fact.

## P-40 - A duplicate scenario id returned 500 instead of 409 **(Gate 6)**

- **Symptom:** `POST /api/v1/projects/{project_id}/scenarios` with an id that already existed
  returned **500** with no error code, instead of the **409 `SCENARIO_ID_EXISTS`** the
  apply-to-branch path has always returned. The Gate 6 browser suite hit this: its
  `createIsolatedScenario` helper had to tolerate an unexpected status, and the previous
  session removed that tolerance and left the underlying 500 in place.
- **Root cause:** the repository has two scenario-insert paths. `promote_scenario` checks the id
  inside its transaction and raises `ScenarioIdExistsError`; `create_scenario` went straight to
  the `INSERT`. The duplicate therefore surfaced as an uncaught `sqlite3.IntegrityError`, which
  no exception handler claimed, so it became an untyped 500. There was no test for creating a
  duplicate id, so nothing caught it.
- **Fix:** `repository.create_scenario` now performs the same clash check as `promote_scenario`
  and raises `ScenarioIdExistsError`; the route converts it to a 409 with the flat envelope
  (`code`, `message`, `details`, `request_id`) and `details.scenario_id`. The check runs inside
  the transaction, so a refused creation writes nothing. The seeding path was verified to be
  unaffected: it is guarded by an existence check and only creates when the scenario is absent.
- **Regression test:** `test_a_duplicate_scenario_id_is_a_409_not_a_500` in
  `tests/test_scenario_read_endpoints.py`, which asserts the 409, the flat envelope, the error
  code, and that the stored scenario and the scenario list are unchanged. E2E-G6-04 now asserts
  the same contract over HTTP in the browser.
- **Prevention:** when a repository has two paths that write the same table, they must share the
  same conflict handling. A unique-constraint violation that reaches the client as an untyped
  500 is a missing contract, not an acceptable error mode — the caller cannot act on it.

## P-41 - Graph inspector selection test ID was missing on edge/node detail cards **(Gate 6)**

- **Symptom:** Playwright test `E2E-G6-02` failed with timeout waiting for locator `page.getByTestId('inspect-E_K1')` to be visible after selecting an issue in the evidence queue.
- **Root cause:** `GraphInspector.tsx` only had `data-testid="graph-inspector"` on the outer container, without per-element testids on the individual edge or node inspector card sections.
- **Fix:** Added `data-testid={`inspect-${edge.id}`}` to the selected edge section and `data-testid={`inspect-${node.id}`}` to the selected node section.
- **Regression test:** `E2E-G6-02 selecting an issue inspects the affected graph element`.
- **Prevention:** When an E2E journey specifies selecting an entity and asserting on its inspector view, provide deterministic testids on the inspect panels rather than asserting solely on broad container text.

## P-42 - Scenario dropdown did not reload after programmatic scenario creation **(Gate 6)**

- **Symptom:** In `E2E-G6-04`, after calling `createIsolatedScenario` via HTTP `POST /api/v1/projects/{project_id}/scenarios`, navigating to the Scenario tab failed when selecting the newly created scenario in `scenario-select`.
- **Root cause:** `ScenarioEditor.tsx` read `scenarios` from `useWorkspace`, which was populated on initial project load and was not automatically re-fetched when the scenario view was focused or mounted.
- **Fix:** Added `useEffect(() => { reloadScenarios() }, [reloadScenarios])` and `onFocus={reloadScenarios}` to `scenario-select` in `ScenarioEditor.tsx`.
- **Regression test:** `E2E-G6-04 conflicting evidence is shown without choosing a value`.
- **Prevention:** Any selector offering entities that can be created out-of-band or via REST endpoints must ensure its options are reloaded on view focus.

## P-43 - TextField test-id applied to outer label instead of inner input element **(Gate 6)**

- **Symptom:** `E2E-G6-06 the evidence queue is operable by keyboard alone` failed because tabbing to `page.getByTestId('queue-element-filter')` focused the wrapper `<label>` instead of the actual `<input>` element.
- **Root cause:** `TextField` in `Field.tsx` applied `data-testid` to `<label className="field">` rather than forwarding `testId` to the underlying `<input>`.
- **Fix:** Added `data-testid={testId}` directly to `<input>` in `TextField`, and passed `testId="queue-element-filter"` from `EvidenceQueue.tsx`.
- **Regression test:** `E2E-G6-06 the evidence queue is operable by keyboard alone`.
- **Prevention:** In form component libraries, testids targeting input controls must attach directly to the interactive form control, not its surrounding label container.

## P-44 - Multi-phase fault suite selection contradicted per-phase readiness rules **(Gate 6)**

- **Symptom:** Test `E2E-G6-16` failed attempting to select `connection_loss` while in Phase 1, throwing element not found because no checkbox was rendered for `connection_loss`.
- **Root cause:** P-34 and P-37 established that `connection_loss` targets `TMP-EAST-BYPASS` which exists only in Phase 2, so the suite is strictly unavailable (and not offered as runnable) in Phase 1. The test specification `E2E-G6-16` had not been aligned with this readiness rule.
- **Fix:** Replaced `connection_loss` with `incidental_closure` in `E2E-G6-16`.
- **Regression test:** `E2E-G6-16 multiple fault results and execution statuses are reported`.
- **Prevention:** When architectural invariants declare a condition inapplicable for a given phase, ensure test fixtures and test suite configurations adhere to the invariant rather than expecting inapplicable suites to run.

## P-45 - Conflicting evidence issue explanation endpoint evaluated base graph instead of phase graph **(Gate 6)**

- **Symptom:** `GET /api/v1/scenarios/{id}/evidence/issues/{issue_id}` returned conflicting evidence values derived from the unphased base graph rather than incorporating scenario phase closures.
- **Root cause:** In `apps/api/detour_lab/api/v1/evidence.py`, `build_phase_graph` was called without passing the target phase context for scenario-declared edges.
- **Fix:** Updated `evidence_issue` endpoint to resolve graph state via `build_phase_graph(graph, scenario, target_phase).graph`.
- **Regression test:** `test_evidence_issue_endpoint` and `E2E-G6-04 conflicting evidence is shown without choosing a value`.
- **Prevention:** All evidence and analysis resolution endpoints in a multi-phase system must evaluate against the phase-materialised graph, never raw unphased versions.

## P-46 - Mutation of `scn-demo-baseline` in `demo-journey.spec.ts` poisoned subsequent Gate 6 tests **(Gate 6)**

- **Symptom:** In sequential whole-suite execution (`npx playwright test`), `E2E-G6-11` and `E2E-G6-12` timed out after 60s waiting for `transition-table` because the injected faults reported "no relevant modelled change", whereas running `gate6-evidence-failure-report.spec.ts` in isolation passed 30/30.
- **Root cause:** `demo-journey.spec.ts` mutates `scn-demo-baseline` (closing `E_WM`) to test saved closures and reload persistence, advancing the scenario from revision 1 to revision 2 in the shared test database. With `E_WM` closed, `OD-W -> OD-GATE` was already disconnected in the baseline prior to fault injection. Therefore, closing `E_K2` (critical closure) or masking `E_K1` (evidence gap) caused no route transition.
- **Fix:** Added `resetDemoBaseline` helper in `helpers.ts` using transactional SQLite rollback to restore `scn-demo-baseline` to revision 1 (deleting revisions > 1); invoked `resetDemoBaseline()` in `demo-journey.spec.ts` `test.afterAll` and `gate6-evidence-failure-report.spec.ts` `test.beforeAll`. Additionally resolved worker-process PID mismatch in `playwright.config.ts` so `DETOUR_LAB_DB_PATH` is inherited identically across runner and worker processes.
- **Regression test:** `demo-journey.spec.ts` followed immediately by `gate6-evidence-failure-report.spec.ts` E2E-G6-11 and E2E-G6-12 in the same database session.
- **Prevention:** In integration suites sharing a persistent database, any test that mutates shared baseline fixtures must clean up via `afterAll`, and downstream suites expecting a clean baseline must defensively assert or restore baseline state in `beforeAll`.