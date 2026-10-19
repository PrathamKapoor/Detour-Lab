# Gate 5 — Fix This Plan: implemented optimisation design

Status: **implemented and verified** (Gate 5). This document describes what the
repository actually does, with the test that proves each claim. It replaces the
pre-implementation draft that described intent.

Scope sources: `DETOUR_LAB_Final_PRD.md` §6 (FR-102..FR-106),
`MASTER_PROMPT.md` §7/§10/§12 and the Gate 5 definition.

## A. What this gate delivers

For a selected scenario, phase and profile set, Fix This Plan answers: *which
combinations from the bundled intervention library improve model-confirmed
pedestrian coverage, and what exactly does each combination change?* Every
candidate is a derived in-memory scenario re-verified through the **unmodified
analysis pipeline**; nothing is computed by the browser and nothing is claimed
beyond what the model run shows.

| Surface | Path |
|---|---|
| Library + eligibility | `GET /api/v1/scenarios/{id}/optimization/interventions?phase_id=…` |
| One bounded search (persisted) | `POST /api/v1/scenarios/{id}/optimization/search` |
| Search history | `GET /api/v1/scenarios/{id}/optimization/searches` |
| Stored payload (replay) | `GET /api/v1/optimization/searches/{search_id}` |
| Transactional apply-to-branch | `POST /api/v1/optimization/promote` |

Engine: `apps/api/detour_lab/optimization/{model,library,generator,verify,rank,service,promotion}.py`.
Library data: `data/demo/interventions.demo.json` (`DEMO_INVENTIONS_NOT_ENGINEERED`,
version `1.0.0`). Studio: `apps/web/src/features/optimization/` (panels A–G).
Persistence: migration `bounded_optimization_runs` → table `optimization_runs`.

## B. One engine, no second mutation path

A candidate is materialised as a **derived in-memory `Scenario`** — the source's
declared plan *and* its existing edits, plus the intervention effects — and then
goes through the same `build_phase_graph` → `run_analysis` pipeline every other
analysis uses. The optimizer never evaluates a rule, never builds a route and
never invents a verdict.

### B1. Intervention library (immutable, validated)

The bundled library is a versioned JSON data file, loaded and validated on every
use (`optimization/library.py`). Validation rejects, with a named test each:

- duplicate ids, unknown top-level keys, unknown intervention keys;
- `requires_intervention_ids` that dangle, and `requires` cycles;
- effect ops outside `allowed_ops` and targets outside `target_element_ids`;
- an enabled intervention with no effect.

All five demo interventions are `constructible_in_field: false`, geometry- and
price-carrying fields are labelled `demo_only`/synthetic, and the file's `notice`
states that it is authored demo data. Each entry exercises one contract feature:
a modelled attribute (CURB), a pre-survey measurement entry (REMEASURE), a
phase change (BYPASS), a temporary edge with deliberately missing width
(BACKLANE), and a declared dependency with an exclusion (REOPEN requires CURB;
BYPASS excludes BACKLANE).

### B2. Eligibility and domain construction (`generator.py`)

Order of exclusions, each recorded with its reason (never silently dropped):

1. disabled in the library;
2. excluded by the request (`excluded_intervention_ids`) — also listed in the
   domain summary as `excluded_interventions`;
3. declared phases do not cover the selected phase
   (`declared for phase(s) […]; not applicable to 'phase-1'`);
4. failed preconditions (`node_exists`, `edge_exists`,
   `edge_closed_in_phase`, `edge_not_closed_in_phase`,
   `temporary_edge_active_in_phase`, `field_known`, `field_unknown`).
   A precondition about a field the rulepack does not declare **fails closed**.
   Other-phase closure checks read the *declared* plan, not the evaluated
   phase (no cross-phase inference).

Combinations are enumerated over eligible interventions up to
`max_interventions`, with `requires` closures expanded (an oversized closure is
reported as `dependency_blocked`), declared mutual exclusions reported as
`mutually_exclusive_blocked`, and the empty subset kept out of the candidate
list. Limits (`max_candidates`, `max_duration_ms`) stop enumeration and are
echoed in `domain.truncated_by` and `status.limits_hit`.

### B3. Verification (`verify.py`)

For each combination and each selected profile:

- a derived scenario is built and run through `run_analysis` on the real
  `build_phase_graph` output;
- per-OD-pair transitions (before/after confirmed, possible, distances) are
  recorded — `added_distance_m` is present only when both sides have a
  **confirmed** route; a missing route is never counted as 0 m;
- verdict transitions are compared index-wise: **new hard model-FAIL** and
  **new UNKNOWN** verdicts are counted per element/rule/profile;
- a regression of an OD pair that was confirmed *or possible* in the source is
  a hard rejection;
- the candidate's own modelled imports (assumptions) are listed with their
  provenance class and a `requires_field_verification` flag;
- preview hashes (`scenario`, `phase_graph`) are recorded for later comparison.

`proposal_id = "cand-" + semantic_hash({candidate_scenario_hash, phase_id,
intervention_ids})[:12]` for candidates that reached verification, and
`"cand-" + semantic_hash({subset, reasons})[:12]` for combinations rejected
before materialisation — deterministic across executions (test:
`test_search_is_deterministic_across_executions`).

### B4. Classification (vocabulary = performance against the objective)

| Class | Exact condition |
|---|---|
| `rejected` | Any rejection reason: regression of a confirmed/possible pair; a new hard model-FAIL; budget failure (see §E); invalid effect. Hard constraints are never traded against gains. |
| `requires_verification` | No regression, no new hard FAIL, but the candidate introduces elements whose model verdicts are UNKNOWN, or every benefit exists only in the *possible* graph. An unverified element never becomes a pass. |
| `certified` | No regression, no new hard FAIL, no introduced UNKNOWN, and at least one model-confirmed restoration or a comparable confirmed-route shortening. Restoration may hold for a subset of selected profiles; the ranking prefers all-profile restoration. |
| `no_improvement` | Evaluated against the real engine and measurably changed nothing the objective rewards. Not a failure. |

Note the demonstrated case: `{CURB, BACKLANE}` restores both pairs but carries
`introduced_unknown_verdict_count == 2`, so it is `requires_verification`, not
certified (`test_demo_phase_one_semantics`).

## C. Ranking (`rank.py`) — documented, deterministic, weight-free

`DETOUR_LAB_LEXICOGRAPHIC_V1` v1.0.0, applied in order; the first difference
decides (echoed verbatim in every response):

1. classification group (certified → requires_verification → no_improvement → rejected)
2. restored_all_profiles (descending)
3. restored_any_profile (descending)
4. new_hard_fail_verdict_count (ascending)
5. introduced_unknown_verdict_count (ascending)
6. regressed_pair_count (ascending)
7. intervention_count (ascending)
8. monetary_estimate (ascending; **only when** `monetary_objective=nominal`; unknown after known, never 0)
9. comparable_added_distance_m (ascending; routes on both sides only; unknown after known)
10. proposal_id (ascending, byte order)

`rank` is the position in this order; `tie_group` groups candidates equal on
every *measured* axis (the proposal id orders them within the group and is
excluded from the tie key). A **Pareto frontier** is computed over three axes
only — restoration, intervention count, comparable added distance — and is never
presented as a weighted score; cost is never a Pareto axis, and monetary ranking
is off by default (`RankingPolicy.monetary_default = "off"`).

## D. Honest solver statuses

`SolverStatus` semantics, as implemented and tested:

- `OPTIMAL_IN_ENUMERATED_DOMAIN` — only after the **complete** declared domain
  was enumerated (``exhaustive: true``) and a non-rejected candidate exists;
- `FEASIBLE_NOT_PROVEN_OPTIMAL` — enumeration hit a declared limit with at
  least one ranked candidate; never phrased as optimal;
- `NO_FEASIBLE_IN_ENUMERATED_DOMAIN` — the complete domain contains no
  non-rejected candidate (e.g. zero budget);
- `INCOMPLETE_OR_UNKNOWN` — the search did not complete (duration limit,
  evaluation error);
- `INVALID_INPUT` — a rejected candidate's own status.

`status.limits_hit` names what stopped the search; `status.notes` explains
empty or partial outcomes; `status.scope_note` states that results apply to the
selected phase and profile set of this revision and that **a single-phase
improvement is not whole-project continuity**.

## E. Costs, budget and the no-fabrication rule

- Unknown cost is `null` with `cost_unknown: true`; the UI renders
  “Not estimated”. It is never treated as 0 and never estimated by the engine.
- Cost summaries carry per-line provenance (`demo_only` in this repository),
  currency, quantity/unit and nominal/max values only where declared.
- A budget (`amount`, `currency`, `basis` ∈ {`nominal`, `conservative_max`}) is
  a **hard filter**: `exceeds` rejects with `budget: … exceeds the budget.`;
  `cannot_certify_unknown_cost` rejects with “cost cannot be certified (no
  declared price for every line); not treated as fitting and not treated as
  zero”. A zero budget therefore rejects every candidate that has any declared
  cost (E2E-G5-12; `test_zero_budget_rejects_every_candidate_and_says_why`).
- A budget in a currency no demo cost declares is `400
  INVALID_BUDGET_CURRENCY`; **no exchange rate is invented** (E2E-G5-13).

## F. Persistence, identity and replay

- Each search is persisted in `optimization_runs` with its canonical payload,
  `semantic_hash`, `input_hash`, `created_at` and duration (HTTP the same
  service call). Execution identity is `opt-<uuid12>` — **distinct per run**;
  semantic identity is the content hash — **equal for equal inputs**
  (`test_two_searches_both_persisted_with_distinct_execution_ids`).
- Replay serves the stored payload verbatim; over a fresh process over the same
  database it is byte-identical (`test_restart_replay_reads_back_the_identical_payload`;
  E2E-G5-10/25).
- The canonical payload sorts `profile_ids` and sorting decisions are made once,
  in the engine.

## G. Apply-to-branch (`promotion.py`) — transactional, re-verified

- **Clone-with-edits (D-032):** the branch copies the source's declared plan
  *and its existing edits*, appends the intervention effects, records
  `parent_scenario_id`, starts at revision 1 and is written in one transaction.
  This is the Fix-This-Plan path; the user-facing branch creation (D-025) still
  copies the declared plan only.
- **Ordered refusals** (all with the flat error envelope): missing search → 404
  `SEARCH_NOT_FOUND`; source moved since the search → 409 `STALE_SEARCH`;
  source moved since the caller's view → 409 `STALE_REVISION`; unknown proposal
  → 404 `PROPOSAL_NOT_FOUND`; rejected candidate → 409 `CANDIDATE_REJECTED`
  with its reasons; changed library → 409 `LIBRARY_CHANGED`; branch id equal to
  source → 400 `INVALID_INPUT`; branch id taken → 409 `SCENARIO_ID_EXISTS`.
- **Re-materialisation gate:** before anything is persisted, the candidate is
  rebuilt from the current source and its content hash must equal the recorded
  preview hash, else 409 `STALE_SEARCH`. Preview reproducibility is thus
  checked on content, strictly.
- **Post-persist re-verification:** the branch is re-read and re-analysed per
  profile; the persisted semantic hash must equal the preview's. The comparison
  uses `analysis_comparison_body()` (`verify.py`), which excludes exactly three
  fields, each for a precise reason (D-032, P-23): `scenario_id` and
  `phase_graph_id` embed the scenario id (a branch is a new, independently
  addressable scenario by design), and `scenario_hash` covers the scenario
  `revision`, where a branch is revision 1 while the preview carries the
  source's revision label. Everything content-based (phase-graph hash,
  verdicts, OD results) must match exactly; a mismatch is surfaced, never
  accepted.
- **Source immutability** is asserted by the API tests and E2E-G5-24
  (revision *and* content hash unchanged after promotion).
- The response carries the re-verification rows, the OD summary and the
  disclaimers (demo values not field-verified; single-phase scope).

## H. Measured baselines over the synthetic demo project

Reference report: `var/optimization-baseline.json`, produced by
`apps/api/tests/test_optimization_baselines.py` on the seeded demo data
(wheelchair + walker profiles, phase 1, instant `2026-03-01T00:00:00Z`).

| Baseline | Result (measured) |
|---|---|
| B1 — do nothing | Wheelchair: 2 confirmed pairs (58.0 m gate, 98.0 m library), 3 possible. Walker: 0 confirmed, 2 possible. |
| B2 — best single intervention | `cand-ea348b4321ea` = `INT-MODEL-CURB-N_EK`, certified, restores both pairs for both profiles, 0.0 m added, nominal 18 000 INR (demo figure), complete singles enumeration. |
| B3 — greedy extension of B2 | `cand-36541e220a17` = `{CURB, REMEASURE}`, certified, restores both pairs, comparable added distance **−14.137 m** (98.0 → 83.863 m), nominal 23 268 INR. |
| B4 — bounded exhaustive | Rank 1 identical to B2 (`OPTIMAL_IN_ENUMERATED_DOMAIN`); Pareto frontier has 3 candidates; every winner restores the same pairs. |

The −14.137 m is exactly the stored difference of the two confirmed library
routes (98.0 − 83.863). These are **model outputs over synthetic demo data —
not field measurements and not benchmarks**; the report says so in its own
`note`.

## I. Evidence map

- Engine/unit: `tests/test_optimization_core.py` (37) — library validation,
  eligibility, closure, mutual exclusion, budget core, ranking, Pareto,
  statuses, materialisation.
- Service: `tests/test_optimization_search.py` (15) — phase-1 semantics,
  per-profile selection, determinism, source immutability, joint restoration,
  truncation honesty, replay, B20.
- API: `tests/test_optimization_api.py` (18) — envelopes, zero budget,
  currency refusal, promotion + re-verification, 409/404 matrix, D-025 proof.
- Baselines: `tests/test_optimization_baselines.py` (1, writes the report).
- Browser: `apps/web/e2e/gate5-optimization.spec.ts` — G5-01..G5-25 (studio,
  eligibility reasons, cost discipline, ranking, rejection, verification
  needs, transitions, assumptions, replay, determinism, budget, exclusions,
  promotion, branch open, `known=True` re-eligibility, stale revision,
  duplicate id, rejected promotion, keyboard, truncation, monetary-free
  default, source immutability, cross-view replay).
- Component/unit (frontend): `apps/web/tests/optimization-ui.test.tsx` (10)
  and `apps/web/tests/api-client.test.ts` route-parity + method tests.

## J. Explicit non-claims

- No real price or cost estimate exists in this repository; demo figures are
  labelled and get no legal, engineering or market meaning.
- No legal compliance, certification or approval is expressed anywhere;
  candidates are “model-certified” strictly against the demo rulepack.
- No construction calendar, duration or scheduling is modelled (D-023 stays).
- A single-phase improvement is not whole-project continuity; gates 6/7
  (evidence queue, Failure Lab, PDF packet, polish/benchmarks) are out of scope.
- Browsers are automated (Playwright) but no manual assistive-technology audit
  has been performed.
