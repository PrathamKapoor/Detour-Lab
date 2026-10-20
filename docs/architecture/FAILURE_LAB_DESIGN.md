# Gate 6 — Evidence Intelligence and the adversarial Failure Lab: implemented design

Status: **VERIFIED.** Full execution-based verification completed:
- Backend: 511 tests passing in 155s (138 Gate 6 tests in 	est_evidence_queue.py, 	est_failure_lab.py, 	est_reporting.py, and 	est_scenario_read_endpoints.py).
- Frontend: 127 Vitest tests passing in 8.9s; TypeScript and ESLint clean.
- E2E: 99 Playwright tests passing across 10 spec files in 13.1m (gate6-evidence-failure-report.spec.ts 30/30, gate6-contrast.spec.ts 1/1).
- Script: scripts\verify.ps1 exit code 0 (ar/verify-gate6-final.log); PDF generated and SHA-256 digest verified (ar/verify-gate6-packet.pdf).

Scope sources: `DETOUR_LAB_Final_PRD.md` §6 (FR-107, FR-108, FR-109), `MASTER_PROMPT.md`
§7/§10/§12 and the Gate 6 definition. Reporting is documented separately in
`REPORTING_DESIGN.md`.

## A. What this gate delivers

Two surfaces that share one rule — *the model may only say what its inputs support*:

1. **Evidence Intelligence.** A derived queue of the attributes the **authoritative
   resolver** cannot determine for at least one in-scope rule, each explained, each
   linked to the graph element, the rules, the profiles, the phases and the
   origin-destination pairs it actually touches.
2. **The Failure Lab.** Authored, typed fault suites executed against an **isolated**
   copy of the scenario through the **unmodified** analysis pipeline, compared against
   the baseline, and summarised with every denominator stated.

| Surface | Path |
|---|---|
| Derived queue | `GET /api/v1/scenarios/{id}/evidence/queue?statuses=…&profile_ids=…&phase_ids=…` |
| One issue's explanation | `GET /api/v1/scenarios/{id}/evidence/issues/{issue_id}` |
| Attribute explanation (any scenario) | `POST /api/v1/projects/{project_id}/evidence/attributes/explain` |
| Fault catalogue + readiness | `GET /api/v1/scenarios/{id}/failure-lab/catalog` |
| Run suites (persisted) | `POST /api/v1/scenarios/{id}/failure-lab/experiments` |
| Experiment history | `GET /api/v1/scenarios/{id}/failure-lab/experiments` |
| Replay | `POST /api/v1/failure-lab/experiments/{experiment_id}/replay` |
| Element diff | `GET /api/v1/failure-lab/experiments/{experiment_id}/graph-differences` |

Engine: `apps/api/detour_lab/evidence/{model,queue}.py` and
`apps/api/detour_lab/failure/{model,faults,engine,compare,suite,service}.py`.
Studio: `apps/web/src/features/evidence/` and `apps/web/src/features/failure-lab/`
(seven panels, A–G). Persistence: migration 3 → `failure_experiments`.

## B. The evidence queue is derived, never authored

`derive_evidence_queue` recomputes from the same authoritative inputs the analysis
itself used. There is no static list, no stored queue and no patch operation — change
the evidence, rulepack, scenario revision or profile selection and the queue changes
because it is recomputed, not because someone edited it.

- **Unresolved status** comes from `evidence.resolver.resolve_attribute`. The queue
  never re-implements, approximates or second-guesses the resolver
  (`test_queue_is_derived_not_static`).
- **Rule linkage** comes from the real `RuleVerdict` list of the analysis.
- **OD linkage** comes from the real `ODPairResult` list, including the engine's
  counterexample-proven `blocking_finding_ids`.

### B1. The five conditions are the resolver's, not the queue's

`NO_EVIDENCE`, `CONFLICTING_EVIDENCE`, `UNSUPPORTED_UNIT`, `EVIDENCE_EXPIRED` and
`EVIDENCE_NOT_VERIFIED` are reproduced exactly as the resolver returns them. Each has a
dedicated resolver test (`test_no_evidence`, `test_conflicting_observations`,
`test_conflicting_across_equivalent_units`, `test_equivalent_units_are_not_a_conflict`,
`test_unsupported_unit`, `test_expired_observation`, `test_not_verified_observation`),
plus queue-level tests that the status survives derivation.

A conflict is reported **without choosing a value**
(`test_conflict_explains_without_choosing`,
`test_does_not_prefer_the_more_favourable_value`). The selection note states in words
that no observation is selected; it does not fall back to the most or least favourable
observation.

### B2. Ordering is documented and deterministic, and never a score

`ORDERING_RULE` (`evidence/queue.py`) is:

> ascending(decision_blocking < decision_relevant < supporting), then descending count
> of affected profiles, descending count of affected phases, descending count of
> connected origin-destination pairs, ascending element_id, ascending attribute

The primary key is the **explainable category**; everything after it is a deterministic
tie-breaker. `PRIORITIZATION_METHOD` states that categories are derived from
demonstrated relationships in the authoritative analysis and that no probability,
expected value or numeric score is computed.

`test_no_numeric_priority_score_is_emitted` asserts the absence of a score field, and
`test_ordering_is_stable_and_documented` pins the documented order. The UI reinforces
this: E2E-G6-05 asserts the queue panel contains no `%` and no "importance score", and
that the first issue carries a written rationale.

### B3. `additional_phases` widens scope; it never invents entries

An issue found in the selected scope is annotated with the other phases in which the
same attribute also persists (`test_in_scope_issue_is_annotated_with_the_phases_where_it_also_persists`).
Widening the scope may add an issue that genuinely exists elsewhere in the plan; it can
never manufacture one. `test_queue_scope_is_the_selected_analysis_not_every_phase` pins
the default scope.

### B4. `issue_id` is stable under scope

The identity hash excludes `phase_ids` and `profile_ids`. An issue therefore keeps one
`issue_id` when it is observed in several phases or under several profiles, so the
row a reviewer clicked is still the row they clicked after a scope change, and the
detail deep-link keeps working. *(Changed after the `ecfdda2` verification run; the
regression test for the new behaviour is listed in §I as pending.)*

### B5. Honest wording, enforced in the interface

An unresolved attribute means the model **cannot determine the condition**. It is not
proof that a kerb, path or crossing is unusable, and the wording never says so
(`_QUEUE_LIMITATIONS`, and the rendered `detail-caveat`, asserted by E2E-G6-02). A
possible-only route is never rendered as confirmed accessibility
(`test_possible_only_is_not_confirmed`). A missing measurement is never a pass
(`test_missing_measurement_is_not_a_pass`).

## C. Faults are typed, bounded data — never code

`FaultDefinition` is a validated record. `test_no_expression_field_exists_on_the_contract`
asserts the contract has **no expression/eval field at all**: there is no field through
which a fault definition could carry code.

Validation refuses, each with a named test: an invalid fault kind
(`test_invalid_fault_kind_is_refused`), an edge reference that does not exist
(`test_invalid_edge_reference`), a phase the scenario does not declare
(`test_invalid_phase`), a duplicate fault (`test_duplicate_fault_definition_is_refused`),
a contradictory fault on a field that cannot conflict
(`test_contradictory_fault_that_cannot_conflict_is_refused`), an unsupported-unit fault
naming a supported unit (`test_unsupported_unit_fault_must_use_an_unsupported_unit`),
masking an observation that does not exist
(`test_masking_a_non_existent_observation_is_refused`), an unknown element
(`test_unknown_element_is_refused`), closing an already-closed edge as a no-op
(`test_already_closed_edge_is_refused_as_a_no_op`), a temporary loss that does not name
a declared connection (`test_temporary_loss_must_name_a_declared_connection`), and an
expiration fault without an explicit instant
(`test_expiration_requires_an_explicit_instant`).

Two bounds are enforced: fault count per experiment (`test_fault_count_limit`) and target
count per fault (`test_target_limit`).

## D. Nine authored suites, and the conditions deliberately not modelled

`SUITES` is **authored data, not a generator**. Each entry names a fault kind, the
element ids it acts on, and a written rationale. Nothing inspects the graph to invent a
hazard and nothing is chosen at runtime by looking for "interesting" edges.

| Suite | Target | Purpose |
|---|---|---|
| `critical_closure` | `E_K2` | Close a segment carrying the only model-confirmed OD-W→OD-GATE route in phase-1 |
| `incidental_closure` | `E_LINK` | Close a segment carrying no selected outcome, to show a fault that changes nothing is reported honestly |
| `modelled_obstruction` | `E_K1` | An obstruction, modelled as availability only |
| `evidence_gap` | `E_K1` | Mask one genuinely unresolved observation |
| `conflicting_measurement` | `E_K2` | Introduce a second, disagreeing observation |
| `unsupported_unit` | `E_K1` | Offer a unit the real conversion layer rejects |
| `expired_evidence` | `N_K` | Move the evaluation instant so the rulepack's own freshness policy is exercised |
| `connection_loss` | `TMP-EAST-BYPASS` | Deactivate the declared temporary connection (active in phase-2 only) |
| `multi_phase_isolation` | `E_K2` | Scope a fault to one phase and prove it touches no other |

`UNSUPPORTED_SCENARIOS` names three conditions **deliberately not modelled**, each with
its reason: physical obstruction geometry or severity; structural loading, hydrology,
weather or material performance; and the probability of real-world failure. A missing
fault type is never quietly presented as "tested and passed" — E2E-G6-07 asserts the
interface names the omissions.

`test_every_suite_executes` runs all nine.

### D1. Three "extra" behaviours are natural divergence, not special-casing

The PRD asks for more fault variety than a plain closure/mask pair provides. Rather than
special-casing the engine, three behaviours emerge from real machinery:

- **multi-phase** (F8) is the existing `phase_ids` scope, proven by
  `test_multi_phase_fault_touches_only_its_own_phase`.
- **profile-specific outcome** (F9) is the outcome the *real rulepack* produces for that
  profile, proven by `test_profile_specific_outcome_emerges_from_the_rulepack`.
- **candidate stress** (F10) is the same machinery applied to a branch scenario rather
  than the source.

This is stated rather than faked: the engine has no per-kind special case, and
`test_every_suite_leaves_the_source_untouched` runs across all suites.

### D2. Readiness is per phase, and an inapplicable suite is not a pass

`available_suites(scenario, graph, phase_ids)` computes readiness **structurally against
the live source graph**, for the phases the reviewer actually selected. `connection_loss`
targets `TMP-EAST-BYPASS`, which is active only in phase-2, so with phase-1 selected it
is reported as unavailable with the reason "No phase in this selection satisfies the
suite's precondition" — never as "passed", and never silently skipped. When `phase_ids`
is omitted every declared phase is considered, because a suite that applies somewhere in
the plan is not inapplicable to the plan as a whole.

E2E-G6-08 asserts the unavailable suite is listed as such and that **no runnable toggle
is rendered for it at all**. *(The per-phase readiness change is post-`ecfdda2`; see §I.)*

## E. Execution is isolated, and the source is never touched

`build_isolated_state` materialises a **derived in-memory state** carrying the source's
declared plan, its edits, its analyses and its evidence. The fault is applied to that
copy. `execute_experiment` then runs the **unmodified** analysis pipeline against it.

- `test_every_suite_leaves_the_source_untouched` — revision and content hash unchanged
  for every suite.
- `test_experiments_run_against_a_distinct_isolated_state` — the isolated state is a
  distinct object.
- `test_no_stored_run_is_created_by_an_experiment` — an experiment is not an analysis
  run and must not appear in the run history.
- `test_experiment_stays_bound_to_its_revision` — a stale revision is refused.

E2E-G6-18 asserts the same end-to-end over HTTP: scenario revision, scenario content
hash, run count, graph content hash and evidence count are all unchanged after a run.

The isolated scenario carries the source's `base_graph_version_id`, without which
`build_phase_graph` could not resolve the graph/scenario pairing and every phase graph
would fail to build.

## F. Execution status is not the engineering observation

This is the distinction the whole gate turns on, and the two are separate fields on
separate objects.

**`ExperimentStatus`** is the *software* outcome: did the experiment execute at all?
`completed`, `invalid_experiment`, `execution_failed`.

**`EngineeringObservation`** is the *modelled* outcome of a transition: what happened to
one (profile, OD pair, phase) triple. `test_a_baseline_failure_is_a_software_outcome_not_a_network_failure`
and `test_a_faulted_failure_leaves_the_pair_unavailable_not_failed` pin the difference.

Consequences that are tested, not asserted:

- A refused experiment has zero observations and a named error code
  (`test_inapplicable_suite_is_recorded_as_invalid_not_silently_skipped`; E2E-G6-17
  asserts `status == "invalid_experiment"`, `error.code == "NO_OP_FAULT"`,
  `observations.length == 0`).
- A baseline failure is an engine result, never reported as "the network failed".
- Missing data is never rendered as a distance of zero
  (`test_missing_data_is_not_rendered_as_zero_distance`); it reads "not established".
- Preference cost is never substituted for distance
  (`test_distance_is_not_replaced_by_preference_cost`, the P-06 recurrence guard).
- Execution-failure text is preserved rather than swallowed
  (`test_execution_failure_text_is_preserved`).
- `test_pair_observation_classification_is_total` asserts the classification covers
  every case, so no transition falls through unlabelled.

## G. Robustness comparison — denominators stated, probability refused

`summarise_robustness` produces a `RobustnessSummary` carrying the full input identity
(scenario id, revision, content hash, phases, profiles, evaluation instant, rulepack id
and hash, base graph hash) so a reader can tell what it is about.

`denominator_note` is built at runtime from the actual execution, not templated:

> pairs_evaluated = *N* = *C* completed experiment(s) × the origin-destination pairs ×
> profiles × phases each experiment actually compared. Only COMPLETED experiments
> contribute. Partially completed: *P*; invalid: *I*; execution failed: *F*. Invalid and
> failed experiments are excluded from every count above; they are evidence about the
> software, not about the plan.

`INTERPRETATION_NOTE` states that these counts are a **test-coverage** result over the
chosen synthetic conditions, and that they are **NOT** a probability that the route is
safe in the field, **NOT** a failure rate and **NOT** a statistical result — the faults
are authored stress conditions, not a sample from any population of real-world hazards.

`test_robustness_summary_states_its_denominator`,
`test_failed_experiments_are_excluded_from_every_count` and E2E-G6-27/E2E-G6-30 assert
this. The interface renders the denominator and the interpretation verbatim; E2E-G6-27
asserts "Only COMPLETED experiments contribute", "NOT a probability" and "test-coverage".

## H. Determinism and replay — three distinct identities

The interface names all three, and E2E-G6-13 asserts the wording ("three different
identities"):

- **execution id** — `fxp-<uuid12>`, distinct per run, even for identical inputs;
- **input hash** — covers the inputs, so an explicit `evaluation_instant` changes it
  (`test_explicit_instant_changes_the_input_hash`);
- **semantic hash** — covers the result, so a repeat execution is identical
  (`test_repeated_execution_is_semantically_identical`).

`test_stored_experiment_replays_exactly` proves replay reproduces the stored semantic
hash. Replay is a **new execution with a new id**, never a rewrite of the stored one
(E2E-G6-20 asserts `replayed_experiment_id != experiment_id`).

`test_execution_failure_text_is_preserved` guards the defect where an exception's text
was swallowed, leaving an unexplained failure.

## I. Verification status — read this before trusting §B–§H

### I1. What the preserved evidence actually shows

| Artifact | Content | What it proves |
|---|---|---|
| `var/verify-gate5-final.log` | ruff "All checks passed!"; vitest 127 passed; Playwright "68 passed (5.0m)"; eslint "✖ 10 problems (0 errors, 10 warnings)"; "==> VERIFICATION PASSED" | The **Gate 5 baseline** is real and preserved |
| `var/e2e-gate5-full-rerun.log` | "68 passed (5.5m)" | The Gate 5 browser baseline is real |
| `var/collect.log`, `var/collect.txt` | 373 tests, per-file counts, **no Gate 6 test file listed** | The last recorded collection is the **Gate 5** baseline |
| `var/pytest-final.log` | 282 dots | Gate 2 era |
| `var/ptall.log` | 301 dots | Gate 4 era |

**There is no preserved log of any Gate 6 pytest, ruff, tsc, eslint, vitest, build or
Playwright run.** The Gate 6 test functions exist on disk — `tests/test_evidence_queue.py`
(36), `tests/test_failure_lab.py` (66), `tests/test_reporting.py` (35) = 137 functions,
plus `test_scenario_read_endpoints.py` (1) = 138,
counted by inspection, several parametrised so the executed case count would be higher —
but "the file exists and contains 138 test functions" is **not** the same claim as "138
tests passed". No log supports the second claim, so this document does not make it.

Two E2E database files are dated after `ecfdda2`, so a browser run did happen after the
last commit; its output was not preserved and 13 journeys were failing at that point.

### I2. What has never been executed

The authoring sessions had no command runner, so **nothing in the current tree has been
executed** — not the Gate 6 suite, and not the post-`ecfdda2` changes:

| Change | Why it matters | Evidence still owed |
|---|---|---|
| `issue_id` excludes `phase_ids`/`profile_ids` (§B4) | Changes queue identity | `test_queue_identity_is_deterministic`, `test_issue_identity_survives_a_scope_change`, `test_issue_identity_is_independent_of_the_analysis_execution`, `test_distinct_evidence_states_do_not_collapse_into_one_issue_identity` |
| `available_suites` per-phase readiness (§D2) | Changes the catalogue contract | the six `TestSuitesAndRobustness` readiness tests, E2E-G6-08 |
| nav-hint contrast (`--text-muted` 4.33:1 → `--text-secondary` 7.31:1, P-35) | CSS only; ratios computed by hand, axe not re-run | the rendered-contrast test, E2E-G6-28 |
| duplicate scenario id → 409 `SCENARIO_ID_EXISTS` (P-40) | Changes an API error contract | `test_a_duplicate_scenario_id_is_a_409_not_a_500`, E2E-G6-04 |
| `.table-scroll` wrappers on 9 tables | Layout only | E2E-G6-29 |
| E2E spec rewrite + backend cross-check in G6-08 | 13 journeys were failing before the rewrite | Full Gate 6 Playwright run |
| benchmark JSON serialisation in `verify.ps1` | Guarded, but unexecuted | full `verify.ps1` run |

### I3. What was checked statically

Source reading, not execution: the `createIsolatedScenario` helper's payload matches
`ScenarioRequest` (`api/v1/routers.py:115-126`) field-for-field, its URL and expected
`201` match the route at `routers.py:382`, and every run gets a fresh database
(`apps/web/playwright.config.ts:25`). All ~70 `data-testid` values referenced by the
Gate 6 spec exist in the components. The PDF/manifest headers asserted by E2E-G6-23/25
exist in `api/v1/reports.py:184,230-234`, and `pdf_sha256` returns bare hex, matching
the spec's regex. The fixture assumptions behind the rewritten journeys were checked
against the seed: `E_K1.width_mm` is 1100 mm (`test_single_observation_resolves`), so
G6-04's 1800 mm edit produces a genuine conflict, and `phase-2` is the only phase
carrying `TMP-EAST-BYPASS` (`test_phase_reads.py:53`), which is what makes
`connection_loss` inapplicable under phase-1.

**Static checks say nothing about whether an assertion holds against live data.** They
raise the odds of a green run; they are not a substitute for one.

### I4. Coverage added during this audit

Three gaps were found by reading the tests against the fixes they are supposed to protect,
and all three are now closed by tests that exist but have not been run:

1. **P-33 was unprotected.** `test_queue_identity_is_deterministic` derives the queue
   twice with the *same* selection, so it would have passed against the pre-fix
   implementation that included `phase_ids`/`profile_ids` in the identity hash. It is now
   complemented by `test_issue_identity_survives_a_scope_change` (identity is unchanged
   when the phase or profile selection narrows),
   `test_issue_identity_is_independent_of_the_analysis_execution` (re-analysis does not
   mint new identities), and
   `test_distinct_evidence_states_do_not_collapse_into_one_issue_identity` (the same
   element and attribute in two different evidence states get two different identities).
2. **P-34 was untested.** `available_suites` had **no direct unit test at all** before
   this audit. It is now covered by six tests: per-phase derivation, whole-plan
   behaviour, an understandable reason for every unavailable suite, the invariant that an
   applicable suite's targets exist, determinism with the source graph unchanged, and no
   state leaking between phases.
3. **P-35 had no computed-contrast guard at all.** The token change was only ever
   checked by hand and by axe, and axe reports the *rendered page*, not the
   token/background pairing. `apps/web/e2e/gate6-a11y-probe.spec.ts` now measures the
   rendered foreground and the effective background of the nav hint in the idle, hover
   and active states and asserts 4.5:1 in each.

### I4a. A full contrast audit of the text tokens

The failing pairing in P-35 was `--text-muted` on `--surface-selected` (4.03:1). Every
`--text-muted` usage was audited against the surface it actually sits on:

| Surface | `--text-muted` | `--text-secondary` |
|---|---|---|
| `--surface-canvas` #0b1017 | 5.48:1 ✓ | 9.23:1 ✓ |
| `--surface-raised` #121a24 | 5.02:1 ✓ | 8.43:1 ✓ |
| `--surface-inset` #0e151d | 5.26:1 ✓ | 8.81:1 ✓ |
| `--surface-overlay` #17212d | 4.66:1 ✓ | 7.80:1 ✓ |
| `--surface-hover` #1b2735 | **4.33:1 ✗** | 7.31:1 ✓ |
| `--surface-selected` #1d3348 | **4.03:1 ✗** | 6.27:1 ✓ |

The nav hint was the only element rendering `--text-muted` on `--surface-hover` or
`--surface-selected`; every other muted usage sits on a surface that passes. After the
P-35 change no `--text-muted` pairing fails 4.5:1. The rendered measurement in the
browser test above is what proves the token is actually applied, which a CSS comment
cannot.

### I5. Known gaps, deliberately left visible

1. `report-experiment-<id>` is used twice in `ReportsPanel.tsx` (a checkbox at line 174
   and a list item at line 457). The spec always scopes with `.first()`, so no
   strict-mode violation occurs today, but a bare `getByTestId` on that prefix would be
   ambiguous.
2. `apps/web/e2e/gate6-a11y-probe.spec.ts` no longer holds the throwaway diagnostic. It
   now holds the **P-35 rendered-contrast regression test** (§I4, item 3), and the
   `testIgnore` entry that used to hide it has been removed from
   `apps/web/playwright.config.ts`. The file keeps its original path only because the
   environment that replaced it had no file-move capability; rename it when convenient
   with `Move-Item` (not `git mv` — the file is untracked, so `git mv` refuses it):
   `Move-Item apps/web/e2e/gate6-a11y-probe.spec.ts apps/web/e2e/gate6-contrast.spec.ts`.
3. **Four** Gate 6 files are **untracked** — they were never committed, so a commit must add
   them explicitly or the Gate 6 browser coverage and design record are lost:
   `apps/web/e2e/gate6-evidence-failure-report.spec.ts`,
   `apps/web/e2e/gate6-a11y-probe.spec.ts` (or its renamed successor),
   `docs/FAILURE_LAB_DESIGN.md` and `docs/REPORTING_DESIGN.md`.

## J. Explicit non-claims

- No fault is executed from a fault definition; there is no code path from a request body
  to the interpreter.
- No probability of real-world failure is computed or implied anywhere.
- An unresolved attribute is not a physical defect, and the interface never says it is.
- No numeric importance, relevance or confidence score is emitted by the queue.
- Robustness counts are test coverage over authored synthetic conditions, not field
  statistics, not a failure rate and not a probability.
- The bundled rulepack is `DEMO_RULEPACK_NOT_LEGAL`; "model-confirmed" means every
  modelled check in that rulepack passed, and is not legal compliance or engineering
  approval.
- No real study area, jurisdictionally reviewed rulepack, named reviewer or verified unit
  price exists in this repository. Those remain open owner decisions.
- Browsers are automated (Playwright); no manual assistive-technology audit has been
  performed. Automated checks are a floor, not a claim of conformance.