# REQUIREMENTS_TRACEABILITY.md

Legend — **Status**: `NOT IMPLEMENTED` · `PARTIALLY IMPLEMENTED` · `IMPLEMENTED AND TESTED` ·
`IMPLEMENTED BUT NOT VERIFIED` · `BLOCKED` · `DEFERRED`.
A row may only read `IMPLEMENTED AND TESTED` when a named test exists **and was executed**, with
the result recorded in `FLOW.md`.

Source: `DETOUR_LAB_Final_PRD.md` §5 (FR-001..FR-016), §6 (FR-101..FR-111), §5.1 (INV-01..INV-08),
`MASTER_PROMPT.md` §12 (behaviours B1..B32).

Last updated: **19 October 2026, after Gate 5** — 373 backend tests, 127 frontend tests and 68
Playwright tests pass; ruff/tsc/eslint/build clean; `scripts/verify.ps1` → VERIFICATION PASSED
(`var/verify-gate5-final.log`). Gate 5 adds FR-102..FR-106, B18..B24 and the Gate 5 traceability
section; Gate 3/4 sections remain as verified then.

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
| FR-014 | Accessible UI: keyboard + text/table alternatives | `src/features/network/EntityTable.tsx`, `src/components/Dialog.tsx` (focus trap), `src/App.tsx` (skip link), `src/styles/*` | E2E-04, E2E-15b, E2E-15 (axe, 3 views), `components.test.tsx` keyboard cases | IMPLEMENTED AND TESTED (automated checks only; no manual AT audit) |
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
| INV-08 | No approval/certification language | `TestInv08NoCertificationLanguage` (3); UI copy audited in `src/lib/status.ts` + `tests/presentation.test.ts` | IMPLEMENTED AND TESTED |

## P1 differentiators (PRD §6)

| ID | Feature | Status |
|---|---|---|
| FR-101 | Construction phase timeline, phase-specific recomputation | `features/phases/PhaseExplorer.tsx`, `Scenario.ordered_phases()` | `test_phase_reads.py::TestTimelineOrdering`, E2E-G4-01/03 | IMPLEMENTED AND TESTED |
| FR-102 | Bounded candidate intervention library | `optimization/library.py`, `data/demo/interventions.demo.json` | `test_bundled_library_loads_with_unique_validated_entries`, `test_library_rejects_*` (7), E2E-G5-01/02 | IMPLEMENTED AND TESTED |
| FR-103 | Fix This Plan: enumerate + re-verify every output | `optimization/{generator,verify,service}.py`, `features/optimization/` | `test_demo_phase_one_semantics`, `test_joint_restoration_and_dependency_reporting`, E2E-G5-04/05/08/22 | IMPLEMENTED AND TESTED |
| FR-104 | Cost-aware comparison with provenance | `optimization/verify.py` cost summary; library cost lines with `demo_only` provenance | `test_unknown_cost_is_never_treated_as_zero_or_fitting`, `test_conservative_max_basis_uses_the_upper_bound`, E2E-G5-03 | IMPLEMENTED AND TESTED |
| FR-105 | Multi-objective comparison + non-dominated frontier | `optimization/rank.py`, `RankingPolicy`, `CandidateEvaluation.pareto_optimal` | `test_pareto_domination_removes_dominated_candidates`, `test_restoration_counts_and_tie_groups`, E2E-G5-23 | IMPLEMENTED AND TESTED |
| FR-106 | Honest solver status semantics | `optimization/rank.py`, `SearchStatus` (`limits_hit`, `truncated_by`, `notes`, `scope_note`) | `test_candidate_limit_truncation_never_claims_optimality`, `test_duration_limit_truncation_is_incomplete_not_empty`, `test_truncated_with_certified_never_claims_optimality`, E2E-G5-22 | IMPLEMENTED AND TESTED |
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
| B18 | optimiser candidate needs two interventions | `test_requires_closure_expands_singletons_and_reports_oversized`, `test_joint_restoration_and_dependency_reporting`; E2E-G5-17 (branch re-search) | IMPLEMENTED AND TESTED |
| B19 | invalid candidate precondition rejected | `test_phase_filter_selects_the_right_interventions`, `test_precondition_fails_closed_when_field_is_already_known`, `test_ineligible_requirement_blocks_dependent` | IMPLEMENTED AND TESTED |
| B20 | no candidate restores mandatory OD | `test_b20_partial_restoration_is_reported_never_as_full`, `test_zero_candidates_when_everything_is_excluded` | IMPLEMENTED AND TESTED |
| B21 | budget less than every viable option | `test_zero_budget_rejects_every_candidate_with_stated_reasons`, `test_zero_budget_rejects_every_candidate_and_says_why`; E2E-G5-12 | IMPLEMENTED AND TESTED |
| B22 | absent cost does not become zero | `test_unknown_cost_is_never_treated_as_zero_or_fitting`, `test_lists_library_with_eligibility_reasons_and_cost_discipline`; E2E-G5-03/07 | IMPLEMENTED AND TESTED |
| B23 | enumeration detects objective tie | `test_restoration_counts_and_tie_groups` | IMPLEMENTED AND TESTED |
| B24 | incomplete search does not report optimal | `test_candidate_limit_truncation_never_claims_optimality`, `test_duration_limit_truncation_is_incomplete_not_empty`, `test_truncated_with_certified_never_claims_optimality`; E2E-G5-22 | IMPLEMENTED AND TESTED |
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
## Gate 3 frontend traceability (R0)

| Capability | Implementation | API dependency | Tests | Verified status |
|---|---|---|---|---|
| Project dashboard | `src/features/projects/ProjectDashboard.tsx` | `GET /api/v1/projects`, `GET /projects/{id}/graph`, `GET /rulesets` | E2E-01; `tests/components.test.tsx` | VERIFIED |
| Offline SVG network studio | `src/features/network/GraphCanvas.tsx`, `src/lib/geometry.ts` | `GET /projects/{id}/graph` | `geometry.test.ts` (25), E2E-02, E2E-06b | VERIFIED |
| Edge/node inspector with evidence | `src/features/network/GraphInspector.tsx` | graph `evidence[]`, `result.verdicts[]` | `components.test.tsx` | VERIFIED |
| Keyboard-equivalent graph control | `src/features/network/EntityTable.tsx` | graph `nodes[]`/`edges[]` | E2E-04, E2E-15b | VERIFIED |
| Scenario editor (closure, measurement) | `src/features/scenario/ScenarioEditor.tsx`, `src/app/workspace.tsx` | `GET /scenarios/{id}`, `PATCH /scenarios/{id}` | E2E-09, E2E-10, E2E-12b | VERIFIED |
| Reopen a closure (branch) | `createBranch` in `src/app/workspace.tsx` | `POST /projects/{id}/scenarios` | backend `test_creating_a_branch_appears_in_the_list` | VERIFIED |
| Concurrency conflict handling | `saveEdits` / `conflict` in `src/app/workspace.tsx` | HTTP 409 envelope | E2E-12, E2E-12b | VERIFIED |
| Mobility profile + phase analysis | `src/features/analysis/AnalysisWorkspace.tsx` | `POST /scenarios/{id}/evaluate` | E2E-05, E2E-06, E2E-08 | VERIFIED |
| Four-valued results preserved | `src/lib/status.ts`, `StatusBadge` | `AnalysisResult.verdicts[].state` | `presentation.test.ts` | VERIFIED |
| Confirmed vs possible-only routes | `AnalysisWorkspace` OD table, `REACHABILITY_META` | `od_results[]` | E2E-08, E2E-06b | VERIFIED |
| Before/after comparison | `src/features/analysis/ComparisonView.tsx` | two stored runs | E2E-11 | VERIFIED |
| Evidence centre | `src/features/evidence/EvidenceCentre.tsx` | graph `evidence[]`, `verdicts[].inputs[]` | E2E-08 | VERIFIED |
| Canonical manifest + export | `src/features/reports/ReportsPanel.tsx` | `GET /runs/{id}/manifest` | E2E-14 | VERIFIED |
| Error handling (offline, 4xx, 409, malformed) | `src/api/client.ts`, `useResource` | flat error envelope | `api-client.test.ts` (22), E2E-13 | VERIFIED |
| Responsive layout | `src/styles/app.css` | - | E2E-16 desktop + mobile | VERIFIED |

**Not claimed:** no manual screen-reader or keyboard-only audit with real assistive technology has
been performed; axe findings are reported, not conformance (FR-014 status above).
## Gate 4 traceability (construction phase intelligence)

| ID | Requirement | Implementation | API dependency | Tests | Status |
|---|---|---|---|---|---|
| G4-01 | Construction phase explorer in authoritative order | `features/phases/PhaseExplorer.tsx`, `Scenario.ordered_phases()` | `GET /scenarios/{id}/timeline` | `test_phase_reads.py::TestTimelineOrdering`, E2E-G4-01/03 | VERIFIED |
| G4-02 | Phase-specific graph visualisation | `features/network/GraphCanvas.tsx` fed by `PhaseGraphResponse` | `GET /scenarios/{id}/phases/{phase_id}/graph` | `TestPhaseGraph` (9), E2E-G4-02 | VERIFIED |
| G4-03 | Phase-aware scenario editing | `features/scenario/ScenarioEditor.tsx` | `PATCH /scenarios/{id}` with `close_edge(phases=[…])` | E2E-G4-10/14/15 | VERIFIED |
| G4-04 | Full phase replay (first/prev/next/last) | `PhaseExplorer` phase rail + navigation buttons | timeline + phase graph | E2E-G4-03 | VERIFIED |
| G4-05 | Evaluate every phase | `workspace.evaluateAllPhases()` (`Promise.allSettled`, per-phase identity) | N × `POST /evaluate` | E2E-G4-05/16 | VERIFIED |
| G4-06 | Phase transition impact analysis | `lib/temporal.ts::computeImpacts` | two stored results | `temporal.test.ts` (9 transition cases) | VERIFIED |
| G4-07 | Cross-phase continuity | `lib/temporal.ts::computeContinuity`, continuity matrix | stored results | `temporal.test.ts` (4 continuity cases), E2E-G4-06/07 | VERIFIED |
| G4-08 | First problematic phase | `lib/temporal.ts::firstProblematicPhase` / `explainFirstProblem` | stored results | `temporal.test.ts`, E2E-G4-08 | VERIFIED |
| G4-09 | Persisted scenario branches | `features/branches/BranchExplorer.tsx`, `ApiClient.createBranchFrom` | `POST /projects/{id}/scenarios` | E2E-G4-09/10 | VERIFIED |
| G4-10 | Branch comparison | `BranchExplorer` branch table + scorecard | scenario list, evaluate | E2E-G4-11 | VERIFIED |
| G4-11 | Phase-aware scorecard | `BranchExplorer.buildScorecard` | stored result counts | E2E-G4-11 | VERIFIED |
| INV-11 | `Phase.order` is the ordering authority | `Scenario.ordered_phases()` | - | `test_non_contiguous_and_reordered_phases_sort_by_order_not_id`, ordering unit tests | VERIFIED |
| INV-12 | An unevaluated phase is never "verified" | `NOT_ANALYSED` state in the timeline | timeline | `test_fresh_scenario_reports_not_analysed`, `test_not_analysed_is_not_a_verdict` | VERIFIED |
| INV-04 (G4) | Distinct phase states get distinct hashes | `build_phase_graph` content hash | timeline + phase graph | `test_different_phase_states_have_different_graph_hashes` | VERIFIED |
| INV-02 (G4) | Phase editing cannot rewrite the source | branch creation reads the source | `POST /projects/{id}/scenarios` | `E2E-G4-10` (source revision + hash unchanged) | VERIFIED |

**Not claimed:** no phase-level accessibility audit has been performed with real assistive
technology; axe runs on the primary views only. Cross-phase continuity is a modelling summary over
reachability and does not establish legal compliance.

## Gate 5 traceability (Fix This Plan - bounded optimisation)

| ID | Requirement | Implementation | API dependency | Tests | Status |
|---|---|---|---|---|---|
| G5-01 | Validated, versioned intervention library | `optimization/library.py`, `data/demo/interventions.demo.json` | `GET /scenarios/{id}/optimization/interventions` | `test_bundled_library_loads_with_unique_validated_entries`, 7 × `test_library_rejects_*`, E2E-G5-01/02/03 | VERIFIED |
| G5-02 | Eligibility with recorded reasons (disabled, excluded, wrong phase, failed precondition) | `optimization/generator.py` | interventions endpoint | `test_phase_filter_selects_the_right_interventions`, `test_client_exclusion_is_reported_with_reason`, `test_precondition_fails_closed_when_field_is_already_known`, E2E-G5-02/17 | VERIFIED |
| G5-03 | Bounded enumeration with declared, echoed limits | `optimization/generator.py`, `optimization/service.py` | `POST /scenarios/{id}/optimization/search` | `test_candidate_limit_truncation_never_claims_optimality`, `test_duration_limit_truncation_is_incomplete_not_empty`, E2E-G5-04/22 | VERIFIED |
| G5-04 | Every candidate re-verified by the unmodified analysis pipeline | `optimization/verify.py` -> `build_phase_graph` + `run_analysis` | search | `test_demo_phase_one_semantics`, `test_search_never_mutates_the_source_scenario`, E2E-G5-08 | VERIFIED |
| G5-05 | Hard constraints reject; introduced UNKNOWNs are never certified | `optimization/verify.py`, `optimization/model.py` | search | `test_demo_phase_one_semantics`, `test_requires_verification_candidate_is_promotable_and_labelled`, E2E-G5-05/06/07 | VERIFIED |
| G5-06 | Cost provenance; unknown cost is null and never zero | `optimization/verify.py` cost summary; library cost lines | search | `test_unknown_cost_is_never_treated_as_zero_or_fitting`, `test_lists_library_with_eligibility_reasons_and_cost_discipline`, E2E-G5-03/07 | VERIFIED |
| G5-07 | Budget as a hard filter on a stated basis; no currency conversion | `optimization/verify.py::check_budget`, `optimization/service.py` | search | `test_zero_budget_rejects_every_candidate_and_says_why`, `test_budget_currency_mismatch_is_invalid_input`, E2E-G5-12/13 | VERIFIED |
| G5-08 | Documented lexicographic ranking, tie groups, Pareto; monetary off by default | `optimization/rank.py`, `RankingPolicy` | search | `test_classification_group_then_restoration_decides`, `test_restoration_counts_and_tie_groups`, `test_monetary_objective_off_ignores_cost_known_before_unknown`, `test_pareto_domination_removes_dominated_candidates`, E2E-G5-23 | VERIFIED |
| G5-09 | Persisted searches with deterministic replay | migration `bounded_optimization_runs`, repository store/get/list | `GET /scenarios/{id}/optimization/searches`, `GET /optimization/searches/{id}` | `test_search_persists_and_replays_identically`, `test_two_searches_both_persisted_with_distinct_execution_ids`, `test_restart_replay_reads_back_the_identical_payload`, E2E-G5-10/11/25 | VERIFIED |
| G5-10 | Transactional apply-to-branch with post-persist re-verification | `optimization/promotion.py`, repository `promote_scenario` | `POST /optimization/promote` | `test_happy_path_reverifies_and_never_touches_the_source`, `test_stale_expected_revision_writes_nothing`, `test_duplicate_branch_id_is_409_and_writes_nothing`, `test_rejected_candidate_is_409_with_reasons`, E2E-G5-15..20 | VERIFIED |
| G5-11 | Promotion preserves the full source plan, including its edits | `optimization/promotion.py` clone-with-edits | promote | `test_source_edits_phases_and_declarations_survive_promotion`, E2E-G5-24 | VERIFIED |
| G5-12 | Single-phase scope is explicit; truncated searches never claim optimality | `SearchStatus.scope_note/limits_hit`, UI honesty strip | search | `test_truncated_with_certified_never_claims_optimality`, E2E-G5-15/22 | VERIFIED |
| INV-02 (G5) | Promotion never mutates the source | clone + one transaction | promote | `test_search_never_mutates_the_source_scenario`, `test_happy_path_reverifies_and_never_touches_the_source`, E2E-G5-24 (revision + content hash unchanged) | VERIFIED |
| INV-06 (G5) | An unverified element never becomes a pass | introduced-UNKNOWN rule | search | `test_demo_phase_one_semantics` (introduced unknowns ⇒ `requires_verification`), E2E-G5-07 | VERIFIED |
| INV-07 (G5) | Promotion writes a new scenario; the source is untouched | `promote_scenario` inserts a branch | promote | `test_happy_path_reverifies_and_never_touches_the_source`, `test_branch_id_equal_to_source_is_400`, E2E-G5-24 | VERIFIED |

**Not claimed:** candidate classification is performance against the demo rulepack model only; no
legal, engineering or constructibility certification is expressed or implied. Costs are synthetic
demo figures with no market meaning. A single-phase improvement is not whole-project continuity.
Gate 6/7 capabilities (evidence queue, Failure Lab, PDF packet, real-world calibration) are not
part of this section.