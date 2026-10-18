# REQUIREMENTS_TRACEABILITY.md

Legend — **Status**: `NOT IMPLEMENTED` · `PARTIALLY IMPLEMENTED` · `IMPLEMENTED AND TESTED` ·
`IMPLEMENTED BUT NOT VERIFIED` · `BLOCKED` · `DEFERRED`.
A row may only read `IMPLEMENTED AND TESTED` when a named test exists **and was executed**, with
the result recorded in `FLOW.md`.

Source: `DETOUR_LAB_Final_PRD.md` §5 (FR-001..FR-016), §6 (FR-101..FR-111), §5.1 (INV-01..INV-08),
`MASTER_PROMPT.md` §12 (behaviours B1..B32).

Last updated: **18 October 2026, after Gate 2** — 270 backend tests pass, ruff clean, restart
replay verified (`test_persistence.py`, `test_api_contracts.py`, `test_api_integration.py`,
`test_contracts_generation.py`).

---

## P0 functional requirements (PRD §5)

| ID | Requirement (abbrev.) | Implemented modules | Tests | Status |
|---|---|---|---|---|
| FR-001 | Create/import study area, validated network with IDs/CRS/origin/licence | `ingestion/schema.py`, `POST /projects/{id}/imports` | `test_ingestion.py`, `TestProjectAndImportFlow` | IMPLEMENTED AND TESTED |
| FR-002 | Explicit topology: shared validated node IDs only | `graph/model.py` | `test_b01_*`, `TestCrossingIsNotConnectivity` | IMPLEMENTED AND TESTED |
| FR-003 | Graph correction (add/split/link/direction/attribute edits) | `scenarios/apply.py` (`order_edits`, `_apply_one`) | `TestTypedEdits` (9 cases) | IMPLEMENTED AND TESTED |
| FR-004 | Evidence recording: value, units, source, date, verification | `domain/contracts.py::EvidenceRecord`, `evidence/resolver.py` | `test_evidence_resolution.py` (19 cases) | IMPLEMENTED AND TESTED |
| FR-005 | Scenario editor: closures + temporary edges per phase; immutable baseline | `scenarios/apply.py::build_phase_graph` | `TestClosureAndPhases`, `test_b10_*` | IMPLEMENTED AND TESTED |
| FR-006 | Two documented mobility profiles evaluated independently | `rules/profiles.py` | `TestProfileIndependence`, `test_b13_*` | IMPLEMENTED AND TESTED |
| FR-007 | Machine-readable rule registry | `rules/rulepacks/DEMO_RULEPACK_NOT_LEGAL.v1.json`, `domain/contracts.py::Rule` | `TestRuleSafety`, `test_rulepack_hash_is_stable_*` | IMPLEMENTED AND TESTED |
| FR-008 | Verdict engine Pass/Fail/Unknown/N-A | `rules/engine.py` | `TestFourValuedEvaluation` (6 cases) | IMPLEMENTED AND TESTED |
| FR-009 | Feasibility graphs by profile + phase | `graph/routing.py::build_feasibility_graphs` | `TestFeasibilityGraphs` (4 cases) | IMPLEMENTED AND TESTED |
| FR-010 | Confirmed vs possible reachability, never conflated | `graph/routing.py`, `analysis/run.py` | `test_b11_*`, `test_b12_*` | IMPLEMENTED AND TESTED |
| FR-011 | Differential before/after view incl. lost OD pairs | phase graphs + `AnalysisResult.od_results` | `test_b09_*`, `test_b25_*` | PARTIALLY IMPLEMENTED — per-phase results exist; the before/after **comparison view** is Gate 3/4 work |
| FR-012 | Explainability: edge/rule/inputs/evidence/remedy per finding | `rules/engine.py::_finding_from` | `test_explanation_never_claims_certification`, `test_b04_*` | IMPLEMENTED AND TESTED |
| FR-013 | Deterministic replay | `domain/hashing.py` | `test_b28_*`, 20-run loop, HTTP replay in `verify.ps1` | IMPLEMENTED AND TESTED |
| FR-014 | Accessible UI: keyboard + text/table alternatives | — | — | NOT IMPLEMENTED (Gate 3) |
| FR-015 | Offline demo with documented synthetic/verified labels | `data/demo/…localplanar.json`, `ingestion/schema.py` | `TestLocalPlanarDataset` | IMPLEMENTED AND TESTED (backend); UI delivery at Gate 3 |
| FR-016 | Structured JSON export incl. unknowns + attribution | `reporting/manifest.py`, `GET /api/v1/runs/{id}/manifest` | `TestManifest` (6 cases), `test_b27_*` | IMPLEMENTED AND TESTED |

## P0 hard acceptance invariants (PRD §5.1)

| ID | Invariant | Test class | Status |
|---|---|---|---|
| INV-01 | Unknown never silently becomes Pass | `TestInv01UnknownNeverBecomesPass` (4) | IMPLEMENTED AND TESTED |
| INV-02 | Visual intersection ≠ connection | `TestInv02CrossingIsNotConnectivity` (2) | IMPLEMENTED AND TESTED |
| INV-03 | Blocked edge never routed | `TestInv03BlockedEdgeNotRouted` (3) | IMPLEMENTED AND TESTED |
| INV-04 | Incompatible units rejected / explicitly converted | `TestInv04UnitIncompatibility` (2) | IMPLEMENTED AND TESTED |
| INV-05 | Rule failure invalidates route; weights cannot override | `TestInv05PreferenceCannotOverrideHardConstraints` (3) | IMPLEMENTED AND TESTED |
| INV-06 | Results identify rulepack/profile/graph/scenario/engine | `TestInv06ReportIdentifiesVersions` (2) | IMPLEMENTED AND TESTED |
| INV-07 | Proposal cannot overwrite the original scenario | `TestInv07BaselineIsImmutable` (2) | IMPLEMENTED AND TESTED |
| INV-08 | No approval/certification language | `TestInv08NoCertificationLanguage` (3) | IMPLEMENTED AND TESTED (backend surfaces; UI copy audit at Gate 3) |

## P1 differentiators (PRD §6)

| ID | Feature | Status |
|---|---|---|
| FR-101 | Construction phase timeline, phase-specific recomputation | PARTIALLY IMPLEMENTED — phase model + per-phase evaluation exist; timeline UI is Gate 4 |
| FR-102 | Bounded candidate intervention library | NOT IMPLEMENTED (Gate 5) — `domain/contracts.py::Intervention` type exists, unused |
| FR-103 | Fix This Plan: enumerate + re-verify every output | NOT IMPLEMENTED (Gate 5) |
| FR-104 | Cost-aware comparison with provenance | NOT IMPLEMENTED (Gate 5) — `InterventionCost` contract exists, unused |
| FR-105 | Multi-objective comparison + non-dominated frontier | NOT IMPLEMENTED (Gate 5) |
| FR-106 | Honest solver status semantics | NOT IMPLEMENTED (Gate 5) — `SolverStatus` enum defined, not yet produced |
| FR-107 | Evidence inspection queue | NOT IMPLEMENTED (Gate 6) |
| FR-108 | Failure Lab: ≥5 reproducible faults | NOT IMPLEMENTED (Gate 6) |
| FR-109 | Side-by-side scenario comparison | NOT IMPLEMENTED (Gate 6) |
| FR-110 | Watermarked "Planning analysis — not certified" PDF | NOT IMPLEMENTED (Gate 6) |
| FR-111 | Revision/branch history with input-hash diffs | `scenario_revisions` table, `GET /scenarios/{id}/revisions` | `TestScenarioRevisions`, `test_revision_history_is_listed` | IMPLEMENTED AND TESTED |

## P2 future requirements (PRD §7)

FR-201..FR-210 — **DEFERRED**, deliberately out of R0/R1 scope.

## Mandatory regression behaviours (MASTER_PROMPT §12)

| # | Behaviour | Test | Status |
|---|---|---|---|
| B1 | crossing geometry without connecting node | `test_b01_crossing_geometry_without_shared_node_is_not_connected` | VERIFIED |
| B2 | directed edge forward only | `test_b02_directed_edge_allows_forward_only` | VERIFIED |
| B3 | parallel edges, route uses right edge ID | `test_b03_parallel_edges_with_different_accessibility` | VERIFIED |
| B4 | known curb-transition failure | `test_curb_interface_failure_propagates_to_traversal` | VERIFIED |
| B5 | missing curb-transition evidence | `test_missing_curb_evidence_makes_the_interface_unknown` | VERIFIED |
| B6 | conflicting width observations | `test_b06_conflicting_measurements_stay_unknown_and_keep_both` | VERIFIED |
| B7 | incompatible units rejected/converted | `TestUnitHandling` (4) + `test_same_physical_width_converts_to_the_same_canonical_value` | VERIFIED |
| B8 | steep grade in one direction | `test_b08_steep_grade_only_fails_in_the_graded_direction` | VERIFIED |
| B9 | closed edge only in phase 2 | `test_b09_edge_closed_only_in_phase_two_is_routable_in_phase_one` | VERIFIED |
| B10 | temporary edge only in phase 1 | `test_b10_temporary_edge_exists_only_in_its_declared_phase` | VERIFIED |
| B11 | unknown path, no confirmed path | `test_b11_unknown_path_exists_without_a_confirmed_path` | VERIFIED |
| B12 | no path even in possible graph | `test_b12_no_route_at_all_in_either_graph` | VERIFIED |
| B13 | profiles give different results | `test_b13_the_two_profiles_produce_independent_results` | VERIFIED |
| B14 | preference cannot override hard fail | `test_b14_preference_weight_cannot_change_any_hard_verdict` | VERIFIED |
| B15 | N/A cannot clear another critical UNKNOWN | `test_b15_not_applicable_cannot_clear_another_critical_unknown` | VERIFIED |
| B16 | repeated import preserves semantics | `test_b16_repeated_import_preserves_stable_semantics` | VERIFIED |
| B17 | graph edit leaves baseline unchanged | `test_b17_a_graph_edit_leaves_the_baseline_unchanged` | VERIFIED |
| B18 | optimiser candidate needs two interventions | — | PENDING (Gate 5) |
| B19 | invalid candidate precondition rejected | — | PENDING (Gate 5) |
| B20 | no candidate restores mandatory OD | — | PENDING (Gate 5) |
| B21 | budget less than every viable option | — | PENDING (Gate 5) |
| B22 | absent cost does not become zero | — | PENDING (Gate 5) |
| B23 | enumeration detects objective tie | — | PENDING (Gate 5) |
| B24 | incomplete search does not report optimal | — | PENDING (Gate 5) |
| B25 | wrong-phase route not reused | `test_b25_wrong_phase_route_is_not_reused` | VERIFIED |
| B26 | evidence revision invalidates a stale run | `test_b26_new_measurement_conflicting_with_the_old_one_creates_a_conflict_not_an_overwrite` | VERIFIED |
| B27 | timestamps/attribution survive export | `test_b27_provenance_and_timestamps_survive_serialisation` | VERIFIED (record-level; export at Gate 2) |
| B28 | deterministic hash across reconstruction | `test_b28_semantic_hash_is_stable_across_reconstruction` + 20-run loop | VERIFIED |
| B29 | PDF warns "not certified" | — | PENDING (Gate 6) |
| B30 | malicious markup does not execute on UI | — | PENDING (Gate 3) |
| B31 | frontend offline mode still shows graph | — | PENDING (Gate 3) |
| B32 | no invented distance for unreachable paths | `test_b32_unreachable_routes_never_invent_a_distance` | VERIFIED |

**24 of 32 verified.** The remaining 8 depend on features that do not exist yet and are marked
PENDING rather than claimed.

## Evaluation baselines (MASTER_PROMPT §12)

| Baseline | Definition | Status |
|---|---|---|
| B-1 | Shortest path ignoring accessibility attributes | NOT IMPLEMENTED (Gate 7) |
| B-2 | Static accessibility-aware routing without phases | NOT IMPLEMENTED (Gate 7) |
| B-3 | Per-segment rule checks without OD connectivity | NOT IMPLEMENTED (Gate 7) |
| B-4 | Greedy single-intervention selection vs exact enumeration | NOT IMPLEMENTED (Gate 5/7) |
| B-5 | Naive first-listed inspection ordering | NOT IMPLEMENTED (Gate 6/7) |

## Performance targets (PRD §12)

Not yet benchmarked. `scripts/verify.ps1` reports wall-clock only for the verification run itself.
Graph sizes stay far below the ≤1 000 node / ≤3 000 edge target (seed: 9 nodes, 12 edges).
Measured p50/p95 latency belongs to Gate 7 and must be reported as measured, not estimated.