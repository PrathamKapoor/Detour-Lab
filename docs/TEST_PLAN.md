# TEST_PLAN.md

Scope, layers and gates for DETOUR LAB. Layer counts are **measured**, not estimated:
`270 passed` on Windows/Python 3.12.10 in ~29 s at the Gate 2 checkpoint.

## Layers

| Layer | Tool | Location | Gate | Count |
|---|---|---|---|---:|
| Domain unit + property-based | pytest + Hypothesis | `apps/api/tests/` | 1 | 217 |
| HTTP contract + integration | pytest + `TestClient` | `test_api_contracts.py`, `test_api_integration.py`, `test_persistence.py`, `test_contracts_generation.py` | 2 | 53 |
| Frontend unit | Vitest + Testing Library | `apps/web/tests/` | 3 | not built |
| End-to-end browser | Playwright | `apps/web/e2e/` | 3+ | not built |
| Static analysis | ruff | `apps/api/` | 0 | all files |
| Live smoke | uvicorn + HTTP | `scripts/verify.ps1` | 0 | 1 |

## Commands that actually run

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify.ps1 -SkipFrontend
.\.venv\Scripts\python.exe -m pytest apps\api\tests -q
.\.venv\Scripts\python.exe -m ruff check apps\api --config apps\api\pyproject.toml
```

## Coverage of the mandatory behaviour list (MASTER_PROMPT §12)

Each item below names the test that proves it. `VERIFIED` means the test exists **and passed**.

| # | Behaviour | Test | Status |
|---|---|---|---|
| 1 | crossing geometry without shared node | `test_b01_crossing_geometry_without_shared_node_is_not_connected` | VERIFIED |
| 2 | directed edge forward only | `test_b02_directed_edge_allows_forward_only` | VERIFIED |
| 3 | parallel edges, route uses the right ID | `test_b03_parallel_edges_with_different_accessibility` | VERIFIED |
| 4 | known curb-transition failure | `test_curb_interface_failure_propagates_to_traversal` | VERIFIED |
| 5 | missing curb-transition evidence | `test_missing_curb_evidence_makes_the_interface_unknown` | VERIFIED |
| 6 | conflicting width observations | `test_b06_conflicting_measurements_stay_unknown_and_keep_both` | VERIFIED |
| 7 | incompatible units rejected / converted | `TestUnitHandling`, `test_incompatible_unit_is_rejected` | VERIFIED |
| 8 | steep grade in one direction | `test_b08_steep_grade_only_fails_in_the_graded_direction` | VERIFIED |
| 9 | closure active in phase 2 only | `test_b09_edge_closed_only_in_phase_two_is_routable_in_phase_one` | VERIFIED |
| 10 | temporary edge only in phase 1 | `test_b10_temporary_edge_exists_only_in_its_declared_phase` | VERIFIED |
| 11 | unknown path, no confirmed path | `test_b11_unknown_path_exists_without_a_confirmed_path` | VERIFIED |
| 12 | no path even in the possible graph | `test_b12_no_route_at_all_in_either_graph` | VERIFIED |
| 13 | profiles give different results | `test_b13_the_two_profiles_produce_independent_results` | VERIFIED |
| 14 | preference cannot override hard fail | `test_b14_preference_weight_cannot_change_any_hard_verdict` | VERIFIED |
| 15 | N/A cannot clear another UNKNOWN | `test_b15_not_applicable_cannot_clear_another_critical_unknown` | VERIFIED |
| 16 | repeated import stable | `test_b16_repeated_import_preserves_stable_semantics` | VERIFIED |
| 17 | edit leaves baseline unchanged | `test_b17_a_graph_edit_leaves_the_baseline_unchanged` | VERIFIED |
| 18 | optimiser needs two interventions jointly | — | PENDING (Gate 5) |
| 19 | invalid candidate precondition | — | PENDING (Gate 5) |
| 20 | no candidate restores the OD | — | PENDING (Gate 5) |
| 21 | budget below every option | — | PENDING (Gate 5) |
| 22 | absent cost is not zero | — | PENDING (Gate 5) |
| 23 | enumeration detects an objective tie | — | PENDING (Gate 5) |
| 24 | incomplete search is not "optimal" | — | PENDING (Gate 5) |
| 25 | wrong-phase route not reused | `test_b25_wrong_phase_route_is_not_reused` | VERIFIED |
| 26 | evidence revision invalidates a stale run | `test_b26_new_measurement_conflicting_with_the_old_one_creates_a_conflict_not_an_overwrite` | VERIFIED |
| 27 | timestamps/attribution survive export | `test_b27_provenance_and_timestamps_survive_serialisation` | VERIFIED (export at Gate 2) |
| 28 | deterministic hash across reconstruction | `test_b28_semantic_hash_is_stable_across_reconstruction`, 20-run loop | VERIFIED |
| 29 | PDF warns not certified | — | PENDING (Gate 6) |
| 30 | malicious markup does not execute | — | PENDING (Gate 3, UI render) |
| 31 | frontend offline still shows the graph | — | PENDING (Gate 3) |
| 32 | no invented distance for unreachable | `test_b32_unreachable_routes_never_invent_a_distance` | VERIFIED |

24 of 32 verified at the Gate 1 checkpoint; the remaining 8 are gated behind features that do not
exist yet and are marked PENDING rather than claimed.

## Invariant gates (PRD §5.1)

`tests/test_invariants.py` contains one class per invariant, each with several cases:
INV-01 (4), INV-02 (2), INV-03 (3), INV-04 (2), INV-05 (3), INV-06 (2), INV-07 (2), INV-08 (3).

## Property-based tests

| Property | Test |
|---|---|
| Unit conversion of the same physical width is unit-independent | `test_same_physical_width_converts_to_the_same_canonical_value` (200 examples) |
| Hashing is repeatable for arbitrary float payloads | `test_hashing_is_repeatable_for_arbitrary_payloads` (100 examples) |
| Route choice is stable under edge-list permutation | `test_route_is_stable_under_edge_list_permutation` (50 examples) |

## Determinism protocol

1. The evaluation instant (`as_of`) is an explicit, recorded input — never `datetime.now()`.
2. All ordering is canonical: sorted IDs, canonical JSON, stable tie-breaks.
3. `scripts/verify.ps1` asserts two identical HTTP evaluations return byte-identical payloads.
4. Floats are normalised to 6 decimals before hashing; `-0.0` normalises to `0.0`.

## What is NOT verified here

- Real-world accessibility accuracy — no field data exists.
- Performance targets from PRD §12 (p95 < 2 s) — not yet benchmarked; scheduled for Gate 7.
- Optimiser correctness — not implemented.
- Accessibility conformance — automated checks plus one documented keyboard pass come at Gate 3;
  even then, conformance must not be claimed from automated tests alone.
## Gate 3 layers (added)

| Layer | Tool | Count | Command |
|---|---|---|---|
| Frontend unit / component | Vitest + Testing Library | 82 | `npm run test` (in `apps/web`) |
| — geometry | Vitest | 25 | bounds, fit, transform, parallel edges, degenerate cases |
| — API client | Vitest | 22 | envelope, 400/404/409/422/500, timeout, abort, malformed, OpenAPI parity |
| — presentation | Vitest | 17 | units, signed grades, verdict/evidence vocabulary, reachability |
| — components | Vitest + Testing Library | 18 | canvas, entity table, inspector, badges, error panel |
| Types / lint / build | tsc, ESLint, Vite | - | `npm run typecheck`, `npm run lint`, `npm run build` |
| Browser E2E | Playwright + Chromium | 25 | `npm run e2e` |

E2E coverage: E2E-01..E2E-18 are implemented as real assertions against the live backend; E2E-13
simulates an unreachable service by aborting the request; E2E-12 reproduces a real 409.

Each run uses its own SQLite database (`var/e2e-<timestamp>.sqlite3`), seeded by the backend, so no
spec inherits state from a previous run. Specs are still written to be order-independent within a run.