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

## Not yet encountered / not yet fixed

- `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated; install
  httpx2 instead` — emitted by FastAPI's own test client. Harmless today; the API contract tests
  pass. Revisit when FastAPI/Starlette ship the successor transport.