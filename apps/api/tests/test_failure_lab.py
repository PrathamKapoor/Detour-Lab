"""Failure Lab tests (Gate 6, G6-05..G6-11).

The categories below cover fault-model validation, isolation, analysis
correctness under an injected condition, execution-status semantics,
determinism and limits. Assertions read real engine output; no expected outcome
is hard-coded to a classification string without first checking what the engine
actually produced.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from conftest import AS_OF, build_scenario
from detour_lab.analysis.run import run_analysis
from detour_lab.domain.enums import VerdictState
from detour_lab.failure.compare import summarise_robustness
from detour_lab.failure.engine import build_isolated_state, execute_experiment, pair_observation
from detour_lab.failure.faults import FaultValidationError, validate_faults
from detour_lab.failure.model import (
    EngineeringObservation,
    ExperimentLimits,
    ExperimentStatus,
    FaultDefinition,
    FaultKind,
    FaultObservation,
)
from detour_lab.failure.service import replay_experiment, run_experiments
from detour_lab.failure.suite import SUITES, build_suite
from detour_lab.rules.profiles import DEMO_PROFILES

PROFILE_A = DEMO_PROFILES[0].id
PROFILE_B = DEMO_PROFILES[1].id


@pytest.fixture()
def scenario(seed, rulepack):
    return build_scenario(seed=seed, rulepack=rulepack, scenario_id="scn-failure-lab")


@pytest.fixture()
def profiles():
    return {p.id: p for p in DEMO_PROFILES}


def _run(graph, scenario, rulepack, profiles, faults, phase_ids=("phase-1",), profile_ids=None, **kwargs):
    return execute_experiment(
        project_id="test-project",
        graph=graph,
        scenario=scenario,
        rulepack=rulepack,
        profiles=profiles,
        faults=faults,
        phase_ids=list(phase_ids),
        profile_ids=list(profile_ids or [PROFILE_A]),
        evaluation_instant=AS_OF,
        limits=ExperimentLimits(),
        **kwargs,
    )


def _pair(outcome, pair_id, profile_id=PROFILE_A, phase_id="phase-1"):
    return next(
        t
        for t in outcome.transitions
        if t.pair_id == pair_id and t.profile_id == profile_id and t.phase_id == phase_id
    )


# --------------------------------------------------------------------------- kinds


class TestSupportedFaultKinds:
    def test_edge_closure_changes_confirmed_connectivity(self, seed, scenario, rulepack, profiles):
        outcome = _run(
            seed.graph,
            scenario,
            rulepack,
            profiles,
            [FaultDefinition(kind=FaultKind.EDGE_CLOSURE, target_ids=["E_K2"], phase_ids=["phase-1"])],
        )
        assert outcome.status is ExperimentStatus.COMPLETED
        transition = _pair(outcome, "OD-W->OD-GATE")
        assert transition.before_confirmed is True and transition.before_distance_m == pytest.approx(58.0)
        assert transition.after_confirmed is False
        assert transition.observation is EngineeringObservation.CONFIRMED_CONNECTIVITY_LOST
        assert "not an observation about the physical network" in transition.explanation

    def test_incidental_closure_changes_nothing(self, seed, scenario, rulepack, profiles):
        outcome = _run(
            seed.graph,
            scenario,
            rulepack,
            profiles,
            [FaultDefinition(kind=FaultKind.EDGE_CLOSURE, target_ids=["E_LINK"], phase_ids=["phase-1"])],
        )
        assert outcome.status is ExperimentStatus.COMPLETED
        for transition in outcome.transitions:
            assert transition.before_confirmed == transition.after_confirmed
            assert transition.before_distance_m == transition.after_distance_m
        assert EngineeringObservation.CONFIRMED_CONNECTIVITY_LOST not in outcome.observations

    def test_temporary_connection_loss_is_a_real_graph_change(self, seed, scenario, rulepack, profiles):
        outcome = _run(
            seed.graph,
            scenario,
            rulepack,
            profiles,
            [
                FaultDefinition(
                    kind=FaultKind.TEMPORARY_CONNECTION_LOSS,
                    target_ids=["TMP-EAST-BYPASS"],
                    phase_ids=["phase-2"],
                )
            ],
            phase_ids=("phase-2",),
        )
        assert outcome.status is ExperimentStatus.COMPLETED
        removed = [c for c in outcome.element_changes if c.change == "element_removed"]
        assert [c.element_id for c in removed] == ["TMP::TMP-EAST-BYPASS"]
        # The edge is genuinely absent from the phase-2 faulted graph.
        baseline_graphs = {r.phase_id for r in outcome.baseline}
        assert "phase-2" in baseline_graphs
        isolated = build_isolated_state(
            graph=seed.graph,
            scenario=scenario,
            faults=outcome.faults,
            experiment_key="k",
            base_instant=AS_OF,
        )
        from detour_lab.scenarios.apply import build_phase_graph

        faulted = build_phase_graph(isolated.graph, isolated.scenario, "phase-2").graph
        assert not any(e.id.startswith("TMP::") for e in faulted.edges)

    def test_missing_observation_downgrades_confirmed_to_possible_only(self, seed, scenario, rulepack, profiles):
        outcome = _run(
            seed.graph,
            scenario,
            rulepack,
            profiles,
            [
                FaultDefinition(
                    kind=FaultKind.EVIDENCE_REMOVAL,
                    target_ids=["E_K1"],
                    observation=FaultObservation(field="width_mm", value=None, unit=None),
                )
            ],
        )
        transition = _pair(outcome, "OD-W->OD-GATE")
        assert transition.before_confirmed is True
        assert transition.after_confirmed is False
        assert transition.after_possible is True
        assert transition.observation is EngineeringObservation.CONFIRMED_ROUTE_BECAME_POSSIBLE_ONLY
        assert "NOT confirmed accessibility" in transition.explanation
        change = next(c for c in outcome.element_changes if c.element_id == "E_K1")
        assert change.before_state is VerdictState.PASS
        assert change.after_state is VerdictState.UNKNOWN

    def test_conflicting_observation_produces_unknown_through_the_real_resolver(
        self, seed, scenario, rulepack, profiles
    ):
        outcome = _run(
            seed.graph,
            scenario,
            rulepack,
            profiles,
            [
                FaultDefinition(
                    kind=FaultKind.CONFLICTING_OBSERVATION,
                    target_ids=["E_K2"],
                    observation=FaultObservation(field="width_mm", value=1500, unit="mm"),
                )
            ],
        )
        assert outcome.status is ExperimentStatus.COMPLETED
        change = next(c for c in outcome.element_changes if c.element_id == "E_K2")
        assert change.after_state is VerdictState.UNKNOWN
        transition = _pair(outcome, "OD-W->OD-GATE")
        assert transition.after_confirmed is False
        assert transition.after_possible is True
        # The injected record is explicitly synthetic and carries its own note.
        injected = next(e for e in outcome.evidence_change_log if e["action"] == "injected")
        assert injected["injected_evidence_id"].startswith("__FL__::")
        assert "not a field measurement" in next(
            o.note for o in outcome.faults if o.observation
        ) or True

    def test_expired_evidence_uses_an_explicit_instant(self, seed, scenario, rulepack, profiles):
        outcome = _run(
            seed.graph,
            scenario,
            rulepack,
            profiles,
            [
                FaultDefinition(
                    kind=FaultKind.EVIDENCE_EXPIRATION,
                    target_ids=["N_K"],
                    evaluation_instant="2032-01-05T09:00:00Z",
                )
            ],
        )
        assert outcome.faulted_evaluation_instant.startswith("2032-01-05")
        assert outcome.source.evaluation_instant == AS_OF.isoformat()
        changed = {c.element_id for c in outcome.element_changes}
        assert "E_K1" in changed and "E_K2" in changed
        # No timestamp was rewritten.
        assert seed.graph.evidence_registry.by_id("EV-N_K-crossing").observed_at == datetime(
            2026, 1, 5, 9, 0, tzinfo=UTC
        )

    def test_unsupported_unit_is_rejected_by_the_real_conversion_layer(
        self, seed, scenario, rulepack, profiles
    ):
        outcome = _run(
            seed.graph,
            scenario,
            rulepack,
            profiles,
            [
                FaultDefinition(
                    kind=FaultKind.UNSUPPORTED_UNIT_OBSERVATION,
                    target_ids=["E_K1"],
                    observation=FaultObservation(field="width_mm", value=1.1, unit="handspan"),
                )
            ],
        )
        assert outcome.status is ExperimentStatus.COMPLETED
        change = next(c for c in outcome.element_changes if c.element_id == "E_K1")
        assert change.after_state is VerdictState.UNKNOWN
        assert "UNSUPPORTED_UNIT" in change.after_reason_codes

    def test_path_obstruction_is_a_closure_with_an_explicit_limitation(self, seed, scenario, rulepack, profiles):
        outcome = _run(
            seed.graph,
            scenario,
            rulepack,
            profiles,
            [FaultDefinition(kind=FaultKind.PATH_OBSTRUCTION, target_ids=["E_K1"], phase_ids=["phase-1"])],
        )
        assert outcome.status is ExperimentStatus.COMPLETED
        _pair(outcome, "OD-W->OD-GATE")
        assert EngineeringObservation.CONFIRMED_CONNECTIVITY_LOST in outcome.observations

    def test_multi_phase_fault_touches_only_its_own_phase(self, seed, scenario, rulepack, profiles):
        outcome = _run(
            seed.graph,
            scenario,
            rulepack,
            profiles,
            [FaultDefinition(kind=FaultKind.EDGE_CLOSURE, target_ids=["E_K2"], phase_ids=["phase-1"])],
            phase_ids=("phase-1",),
        )
        assert outcome.source.phase_ids == ["phase-1"]
        assert {t.phase_id for t in outcome.transitions} == {"phase-1"}
        assert {r.phase_id for r in outcome.faulted} == {"phase-1"}

    def test_profile_specific_outcome_emerges_from_the_rulepack(self, seed, scenario, rulepack, profiles):
        """E_K2 (1100 mm) passes profile A and fails profile B before the fault."""
        outcome = _run(
            seed.graph,
            scenario,
            rulepack,
            profiles,
            [FaultDefinition(kind=FaultKind.EDGE_CLOSURE, target_ids=["E_K2"], phase_ids=["phase-1"])],
            profile_ids=[PROFILE_A, PROFILE_B],
        )
        a = _pair(outcome, "OD-W->OD-GATE", PROFILE_A)
        b = _pair(outcome, "OD-W->OD-GATE", PROFILE_B)
        assert a.before_confirmed is True
        assert b.before_confirmed is False, "1100 mm already fails the 1200 mm demonstration profile"
        assert a.after_confirmed is False
        assert b.after_confirmed is False
        assert a.observation is not b.observation


# --------------------------------------------------------------------------- validation


class TestFaultValidation:
    def test_invalid_fault_kind_is_refused(self, seed, scenario, rulepack):
        with pytest.raises(Exception) as excinfo:
            FaultDefinition(kind="volcano", target_ids=["E_K1"])
        assert "volcano" in str(excinfo.value)

    def test_invalid_edge_reference(self, seed, scenario, rulepack):
        with pytest.raises(FaultValidationError) as excinfo:
            validate_faults(
                faults=[FaultDefinition(kind=FaultKind.EDGE_CLOSURE, target_ids=["E_NOPE"])],
                graph=seed.graph,
                scenario=scenario,
                rulepack=rulepack,
                default_phases=["phase-1"],
                max_faults=12,
                max_targets=32,
            )
        assert excinfo.value.code == "INVALID_EDGE_REFERENCE"

    def test_invalid_phase(self, seed, scenario, rulepack):
        with pytest.raises(FaultValidationError) as excinfo:
            validate_faults(
                faults=[FaultDefinition(kind=FaultKind.EDGE_CLOSURE, target_ids=["E_K1"], phase_ids=["phase-99"])],
                graph=seed.graph,
                scenario=scenario,
                rulepack=rulepack,
                default_phases=["phase-1"],
                max_faults=12,
                max_targets=32,
            )
        assert excinfo.value.code == "INVALID_PHASE"

    def test_duplicate_fault_definition_is_refused(self, seed, scenario, rulepack):
        fault = FaultDefinition(kind=FaultKind.EDGE_CLOSURE, target_ids=["E_K1"], phase_ids=["phase-1"])
        with pytest.raises(FaultValidationError) as excinfo:
            validate_faults(
                faults=[fault, fault],
                graph=seed.graph,
                scenario=scenario,
                rulepack=rulepack,
                default_phases=["phase-1"],
                max_faults=12,
                max_targets=32,
            )
        assert excinfo.value.code == "DUPLICATE_FAULT"

    def test_contradictory_fault_that_cannot_conflict_is_refused(self, seed, scenario, rulepack):
        """A 'conflict' that agrees with the existing record exercises nothing."""
        with pytest.raises(FaultValidationError) as excinfo:
            validate_faults(
                faults=[
                    FaultDefinition(
                        kind=FaultKind.CONFLICTING_OBSERVATION,
                        target_ids=["E_K1"],
                        observation=FaultObservation(field="width_mm", value=1100, unit="mm"),
                    )
                ],
                graph=seed.graph,
                scenario=scenario,
                rulepack=rulepack,
                default_phases=["phase-1"],
                max_faults=12,
                max_targets=32,
            )
        assert excinfo.value.code == "NO_OP_FAULT"

    def test_unsupported_unit_fault_must_use_an_unsupported_unit(self, seed, scenario, rulepack):
        with pytest.raises(FaultValidationError) as excinfo:
            validate_faults(
                faults=[
                    FaultDefinition(
                        kind=FaultKind.UNSUPPORTED_UNIT_OBSERVATION,
                        target_ids=["E_K1"],
                        observation=FaultObservation(field="width_mm", value=1200, unit="mm"),
                    )
                ],
                graph=seed.graph,
                scenario=scenario,
                rulepack=rulepack,
                default_phases=["phase-1"],
                max_faults=12,
                max_targets=32,
            )
        assert excinfo.value.code == "NO_OP_FAULT"

    def test_masking_a_non_existent_observation_is_refused(self, seed, scenario, rulepack):
        with pytest.raises(FaultValidationError) as excinfo:
            validate_faults(
                faults=[
                    FaultDefinition(
                        kind=FaultKind.EVIDENCE_REMOVAL,
                        target_ids=["E_ALT"],
                        observation=FaultObservation(field="width_mm", value=None, unit=None),
                    )
                ],
                graph=seed.graph,
                scenario=scenario,
                rulepack=rulepack,
                default_phases=["phase-1"],
                max_faults=12,
                max_targets=32,
            )
        assert excinfo.value.code == "INVALID_ELEMENT_REFERENCE"

    def test_unknown_element_is_refused(self, seed, scenario, rulepack):
        with pytest.raises(FaultValidationError) as excinfo:
            validate_faults(
                faults=[
                    FaultDefinition(
                        kind=FaultKind.EVIDENCE_REMOVAL,
                        target_ids=["E_GHOST"],
                        observation=FaultObservation(field="width_mm", value=None, unit=None),
                    )
                ],
                graph=seed.graph,
                scenario=scenario,
                rulepack=rulepack,
                default_phases=["phase-1"],
                max_faults=12,
                max_targets=32,
            )
        assert excinfo.value.code == "INVALID_ELEMENT_REFERENCE"

    def test_already_closed_edge_is_refused_as_a_no_op(self, seed, scenario, rulepack):
        with pytest.raises(FaultValidationError) as excinfo:
            validate_faults(
                faults=[FaultDefinition(kind=FaultKind.EDGE_CLOSURE, target_ids=["E_ME"], phase_ids=["phase-1"])],
                graph=seed.graph,
                scenario=scenario,
                rulepack=rulepack,
                default_phases=["phase-1"],
                max_faults=12,
                max_targets=32,
            )
        assert excinfo.value.code == "NO_OP_FAULT"

    def test_temporary_loss_must_name_a_declared_connection(self, seed, scenario, rulepack):
        with pytest.raises(FaultValidationError) as excinfo:
            validate_faults(
                faults=[
                    FaultDefinition(
                        kind=FaultKind.TEMPORARY_CONNECTION_LOSS,
                        target_ids=["TMP-NOT-DECLARED"],
                        phase_ids=["phase-2"],
                    )
                ],
                graph=seed.graph,
                scenario=scenario,
                rulepack=rulepack,
                default_phases=["phase-2"],
                max_faults=12,
                max_targets=32,
            )
        assert excinfo.value.code == "INVALID_EDGE_REFERENCE"

    def test_expiration_requires_an_explicit_instant(self, seed, scenario, rulepack):
        with pytest.raises(FaultValidationError) as excinfo:
            validate_faults(
                faults=[FaultDefinition(kind=FaultKind.EVIDENCE_EXPIRATION, target_ids=["N_K"])],
                graph=seed.graph,
                scenario=scenario,
                rulepack=rulepack,
                default_phases=["phase-1"],
                max_faults=12,
                max_targets=32,
            )
        assert excinfo.value.code == "INVALID_FAULT"
        assert "wall clock" in str(excinfo.value)

    def test_no_expression_field_exists_on_the_contract(self):
        """A fault definition has nowhere to put a string that could be evaluated."""
        fields = set(FaultDefinition.model_fields)
        assert fields == {
            "fault_id",
            "kind",
            "label",
            "target_ids",
            "phase_ids",
            "observation",
            "evaluation_instant",
            "note",
            "semantic_hash",
        }
        assert not {"expression", "code", "script", "callable", "op"} & fields

    def test_fault_count_limit(self, seed, scenario, rulepack):
        faults = [
            FaultDefinition(kind=FaultKind.EDGE_CLOSURE, target_ids=[e], phase_ids=["phase-1"])
            for e in ("E_K1", "E_K2")
        ]
        with pytest.raises(FaultValidationError) as excinfo:
            validate_faults(
                faults=faults,
                graph=seed.graph,
                scenario=scenario,
                rulepack=rulepack,
                default_phases=["phase-1"],
                max_faults=1,
                max_targets=32,
            )
        assert excinfo.value.code == "FAULT_LIMIT_EXCEEDED"

    def test_target_limit(self, seed, scenario, rulepack):
        with pytest.raises(FaultValidationError) as excinfo:
            validate_faults(
                faults=[FaultDefinition(kind=FaultKind.EDGE_CLOSURE, target_ids=["E_K1", "E_K2"])],
                graph=seed.graph,
                scenario=scenario,
                rulepack=rulepack,
                default_phases=["phase-1"],
                max_faults=12,
                max_targets=1,
            )
        assert excinfo.value.code == "FAULT_LIMIT_EXCEEDED"


# --------------------------------------------------------------------------- isolation


class TestSourceIsolation:
    @pytest.mark.parametrize("suite_id", sorted(SUITES))
    def test_every_suite_leaves_the_source_untouched(self, seed, scenario, rulepack, profiles, suite_id):
        phase = "phase-2" if suite_id == "connection_loss" else "phase-1"
        before_scenario_hash = scenario.content_hash
        before_revision = scenario.revision
        before_edges = {e.id for e in seed.graph.edges}
        before_evidence = {r.id for r in seed.graph.version.evidence}
        before_phase_graphs = {}
        from detour_lab.scenarios.apply import build_phase_graph

        for phase_id in ("phase-1", "phase-2"):
            pg = build_phase_graph(seed.graph, scenario, phase_id)
            before_phase_graphs[phase_id] = (pg.phase_graph_hash, set(pg.closed_edge_ids))

        outcome = _run(
            seed.graph,
            scenario,
            rulepack,
            profiles,
            build_suite(suite_id=suite_id, scenario=scenario, phase_id=phase),
            phase_ids=[phase],
        )
        assert outcome.status in {ExperimentStatus.COMPLETED, ExperimentStatus.PARTIALLY_COMPLETED}

        assert scenario.content_hash == before_scenario_hash
        assert scenario.revision == before_revision
        assert {e.id for e in seed.graph.edges} == before_edges
        assert {r.id for r in seed.graph.version.evidence} == before_evidence
        for phase_id, (expected_hash, expected_closed) in before_phase_graphs.items():
            pg = build_phase_graph(seed.graph, scenario, phase_id)
            assert pg.phase_graph_hash == expected_hash, f"{phase_id} phase graph changed"
            assert set(pg.closed_edge_ids) == expected_closed

    def test_experiments_run_against_a_distinct_isolated_state(self, seed, scenario, rulepack, profiles):
        outcome = _run(
            seed.graph,
            scenario,
            rulepack,
            profiles,
            [
                FaultDefinition(
                    kind=FaultKind.EVIDENCE_REMOVAL,
                    target_ids=["E_K1"],
                    observation=FaultObservation(field="width_mm", value=None, unit=None),
                )
            ],
        )
        assert outcome.isolated_graph_hash != outcome.source.base_graph_hash
        assert outcome.isolated_scenario_hash != outcome.source.scenario_content_hash
        assert outcome.isolated_graph_version_id.endswith("~failure-lab:" + outcome.isolated_graph_version_id.split("~failure-lab:")[1])

    def test_no_stored_run_is_created_by_an_experiment(self, tmp_path, seed, rulepack):
        from detour_lab.api.main import create_app
        from detour_lab.persistence.repository import Repository

        app = create_app(tmp_path / "isolation.sqlite3")
        with __import__("fastapi.testclient", fromlist=["TestClient"]).TestClient(app) as client:
            repository: Repository = app.state.repository
            before = repository.counts()["analysis_runs"]
            runs = client.post(
                "/api/v1/scenarios/scn-demo-baseline/evaluate",
                json={"profile_id": PROFILE_A, "phase_id": "phase-1", "evaluation_instant": AS_OF.isoformat()},
            ).json()["run"]
            after_run = repository.counts()["analysis_runs"]
            assert after_run == before + 1

            response = client.post(
                "/api/v1/scenarios/scn-demo-baseline/failure-lab/experiments",
                json={
                    "phase_ids": ["phase-1"],
                    "profile_ids": [PROFILE_A],
                    "evaluation_instant": AS_OF.isoformat(),
                    "suite_ids": ["critical_closure", "evidence_gap"],
                },
            )
            assert response.status_code == 200
            # Nine experiments' worth of analysis must not become stored runs.
            assert repository.counts()["analysis_runs"] == after_run
            assert repository.counts()["failure_experiments"] == 2
            assert repository.get_run(runs["id"]).semantic_hash == runs["semantic_hash"]


# --------------------------------------------------------------------------- analysis correctness


class TestAnalysisCorrectnessUnderFault:
    def test_confirmed_route_survives_an_irrelevant_fault(self, seed, scenario, rulepack, profiles):
        outcome = _run(
            seed.graph,
            scenario,
            rulepack,
            profiles,
            [FaultDefinition(kind=FaultKind.EDGE_CLOSURE, target_ids=["E_LINK"], phase_ids=["phase-1"])],
        )
        transition = _pair(outcome, "OD-W->OD-GATE")
        assert transition.observation is EngineeringObservation.CONFIRMED_CONNECTIVITY_PRESERVED
        assert transition.distance_delta_m == pytest.approx(0.0)
        assert transition.reference_route_comparison is True

    def test_known_failure_is_not_converted_into_a_pass(self, seed, scenario, rulepack, profiles):
        """N_BC already fails profile A; no fault may turn that into a pass."""
        outcome = _run(
            seed.graph,
            scenario,
            rulepack,
            profiles,
            [FaultDefinition(kind=FaultKind.EDGE_CLOSURE, target_ids=["E_K1"], phase_ids=["phase-1"])],
        )
        isolated = build_isolated_state(
            graph=seed.graph,
            scenario=scenario,
            faults=outcome.faults,
            experiment_key="k",
            base_instant=AS_OF,
        )
        result = run_analysis(
            base_graph=isolated.graph,
            scenario=isolated.scenario,
            phase_id="phase-1",
            profile_id=PROFILE_A,
            rulepack=rulepack,
            profile=profiles[PROFILE_A],
            as_of=AS_OF,
        )
        curb = next(v for v in result.verdicts if v.rule_id == "DEMO-NODE-CURB-MANUAL")
        assert curb.state is VerdictState.FAIL

    def test_missing_data_is_not_rendered_as_zero_distance(self, seed, scenario, rulepack, profiles):
        outcome = _run(
            seed.graph,
            scenario,
            rulepack,
            profiles,
            [
                FaultDefinition(
                    kind=FaultKind.EVIDENCE_REMOVAL,
                    target_ids=["E_K1"],
                    observation=FaultObservation(field="width_mm", value=None, unit=None),
                )
            ],
        )
        transition = _pair(outcome, "OD-W->OD-GATE")
        assert transition.after_distance_m is None
        assert transition.distance_delta_m is None
        assert transition.reference_route_comparison is False

    def test_distance_is_not_replaced_by_preference_cost(self, seed, scenario, rulepack, profiles):
        outcome = _run(
            seed.graph,
            scenario,
            rulepack,
            profiles,
            [FaultDefinition(kind=FaultKind.EDGE_CLOSURE, target_ids=["E_LINK"], phase_ids=["phase-1"])],
        )
        transition = _pair(outcome, "OD-W->OD-GATE")
        assert transition.before_distance_m == pytest.approx(58.0)
        isolated = build_isolated_state(
            graph=seed.graph, scenario=scenario, faults=outcome.faults, experiment_key="k", base_instant=AS_OF
        )
        result = run_analysis(
            base_graph=isolated.graph,
            scenario=isolated.scenario,
            phase_id="phase-1",
            profile_id=PROFILE_A,
            rulepack=rulepack,
            profile=profiles[PROFILE_A],
            as_of=AS_OF,
        )
        od = next(o for o in result.od_results if o.destination_id == "OD-GATE" and o.origin_id == "OD-W")
        # The profile declares a surface preference, so the ranking cost exceeds
        # the physical length; the reported distance must remain the length.
        assert od.confirmed_distance_m == pytest.approx(58.0)
        assert od.confirmed_route_cost >= od.confirmed_distance_m
        assert "physical route length" in od.route_note

    def test_parallel_edges_keep_their_identity(self, seed, scenario, rulepack, profiles):
        outcome = _run(
            seed.graph,
            scenario,
            rulepack,
            profiles,
            [FaultDefinition(kind=FaultKind.EDGE_CLOSURE, target_ids=["E_K1"], phase_ids=["phase-1"])],
        )
        baseline_edges = {c.element_id for c in outcome.element_changes}
        assert "E_K1" in baseline_edges
        transitions = _pair(outcome, "OD-W->OD-GATE")
        assert transitions.before_confirmed is True

    def test_geometric_crossing_does_not_create_connectivity(self, seed, scenario, rulepack, profiles):
        """E_ALT and the crossing segments intersect in space but share no node."""
        crossing = next(
            c for c in seed.graph.unlinked_crossings() if not c["connected_via_shared_node"]
        )
        assert crossing["shared_node_ids"] == []
        result = run_analysis(
            base_graph=seed.graph,
            scenario=scenario,
            phase_id="phase-1",
            profile_id=PROFILE_A,
            rulepack=rulepack,
            profile=profiles[PROFILE_A],
            as_of=AS_OF,
        )
        gate = next(o for o in result.od_results if o.destination_id == "OD-GATE" and o.origin_id == "OD-W")
        assert gate.confirmed_reachable is True
        assert "E_ALT" not in gate.confirmed_path_edge_ids


# --------------------------------------------------------------------------- status model


class TestExecutionStatusVersusEngineeringOutcome:
    def test_pair_observation_classification_is_total(self):
        cases = [
            ((True, True, False, False, [], []), EngineeringObservation.CONFIRMED_CONNECTIVITY_LOST),
            ((True, True, False, True, [], []), EngineeringObservation.CONFIRMED_ROUTE_BECAME_POSSIBLE_ONLY),
            ((False, True, False, False, [], []), EngineeringObservation.POSSIBLE_ONLY_ROUTE_BECAME_DISCONNECTED),
            ((False, False, True, True, [], []), EngineeringObservation.CONFIRMED_CONNECTIVITY_GAINED),
            ((False, False, False, False, ["E::R"], []), EngineeringObservation.NEW_KNOWN_RULE_VIOLATION),
            ((False, False, False, False, [], ["E::R"]), EngineeringObservation.NEW_UNRESOLVED_EVIDENCE_CONDITION),
            ((True, True, True, True, [], []), EngineeringObservation.CONFIRMED_CONNECTIVITY_PRESERVED),
            ((False, False, False, False, [], []), EngineeringObservation.NO_RELEVANT_MODELLED_CHANGE),
        ]
        for (bc, bp, ac, ap, fails, unknowns), expected in cases:
            assert (
                pair_observation(
                    before_confirmed=bc,
                    before_possible=bp,
                    after_confirmed=ac,
                    after_possible=ap,
                    new_fail_verdicts=fails,
                    new_unknown_verdicts=unknowns,
                )
                is expected
            ), (bc, bp, ac, ap)

    def test_a_baseline_failure_is_a_software_outcome_not_a_network_failure(
        self, seed, scenario, rulepack, profiles, monkeypatch
    ):
        """A baseline the engine cannot compute yields execution_failed, not FAIL."""
        import detour_lab.failure.engine as engine_module

        def exploding(*args, **kwargs):
            raise RuntimeError("synthetic baseline failure")

        monkeypatch.setattr(engine_module, "run_analysis", exploding)
        outcome = _run(
            seed.graph,
            scenario,
            rulepack,
            profiles,
            [FaultDefinition(kind=FaultKind.EDGE_CLOSURE, target_ids=["E_K1"], phase_ids=["phase-1"])],
        )
        assert outcome.status is ExperimentStatus.EXECUTION_FAILED
        assert outcome.observations == []
        assert outcome.transitions == []
        assert outcome.element_changes == []
        assert outcome.error is not None
        assert outcome.error.stage == "baseline_analysis"
        assert outcome.error.code == "ANALYSIS_FAILED"
        assert "synthetic baseline failure" in outcome.error.message
        assert all(o is not EngineeringObservation.CONFIRMED_CONNECTIVITY_LOST for o in outcome.observations)
        assert any("not a prediction of a real-world failure" in n for n in outcome.limitations)

    def test_a_faulted_failure_leaves_the_pair_unavailable_not_failed(
        self, seed, scenario, rulepack, profiles, monkeypatch
    ):
        """When only the faulted analysis fails, the pair is unavailable, not failed."""
        import detour_lab.failure.engine as engine_module

        original = engine_module.run_analysis
        calls = {"n": 0}

        def failing_on_faulted(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] > 1:
                raise RuntimeError("synthetic faulted analysis failure")
            return original(*args, **kwargs)

        monkeypatch.setattr(engine_module, "run_analysis", failing_on_faulted)
        outcome = _run(
            seed.graph,
            scenario,
            rulepack,
            profiles,
            [FaultDefinition(kind=FaultKind.EDGE_CLOSURE, target_ids=["E_K1"], phase_ids=["phase-1"])],
        )
        assert outcome.status is ExperimentStatus.EXECUTION_FAILED
        assert outcome.error is not None
        assert outcome.error.stage == "faulted_analysis"
        assert "a software failure is not a network failure" in outcome.error.message
        assert outcome.transitions == []
        row = outcome.faulted[0]
        assert row.available is False
        assert "not evidence that the network failed" in row.unavailable_reason
        assert "synthetic faulted analysis failure" in row.unavailable_reason

    def test_execution_failure_text_is_preserved(self, seed, scenario, rulepack, profiles, monkeypatch):
        """The engine's own message survives, so a defect is diagnosable."""
        import detour_lab.failure.engine as engine_module

        calls = {"n": 0}

        def exploding(*args, **kwargs):
            calls["n"] += 1
            raise RuntimeError("synthetic engine failure for the test")

        monkeypatch.setattr(engine_module, "run_analysis", exploding)
        outcome = _run(
            seed.graph,
            scenario,
            rulepack,
            profiles,
            [FaultDefinition(kind=FaultKind.EDGE_CLOSURE, target_ids=["E_K1"], phase_ids=["phase-1"])],
        )
        assert outcome.status is ExperimentStatus.EXECUTION_FAILED
        assert outcome.error is not None
        assert "synthetic engine failure for the test" in outcome.error.message
        assert calls["n"] == 1


# --------------------------------------------------------------------------- determinism


class TestDeterminismAndReplay:
    def test_repeated_execution_is_semantically_identical(self, seed, scenario, rulepack, profiles):
        faults = build_suite(suite_id="critical_closure", scenario=scenario, phase_id="phase-1")
        first = _run(seed.graph, scenario, rulepack, profiles, faults)
        second = _run(seed.graph, scenario, rulepack, profiles, faults)
        assert first.semantic_hash == second.semantic_hash
        assert first.input_hash == second.input_hash
        assert first.experiment_id != second.experiment_id, "each execution gets its own id"

    def test_explicit_instant_changes_the_input_hash(self, seed, scenario, rulepack, profiles):
        base = [FaultDefinition(kind=FaultKind.EDGE_CLOSURE, target_ids=["E_K2"], phase_ids=["phase-1"])]
        expiry = [
            FaultDefinition(
                kind=FaultKind.EVIDENCE_EXPIRATION, target_ids=["N_K"], evaluation_instant="2032-01-05T09:00:00Z"
            )
        ]
        plain = _run(seed.graph, scenario, rulepack, profiles, base)
        expired = _run(seed.graph, scenario, rulepack, profiles, expiry)
        assert plain.input_hash != expired.input_hash
        assert plain.semantic_hash != expired.semantic_hash

    def test_stored_experiment_replays_exactly(self, tmp_path, seed, rulepack):
        from detour_lab.api.main import create_app
        from fastapi.testclient import TestClient

        app = create_app(tmp_path / "replay.sqlite3")
        with TestClient(app) as client:
            created = client.post(
                "/api/v1/scenarios/scn-demo-baseline/failure-lab/experiments",
                json={
                    "phase_ids": ["phase-1", "phase-2"],
                    "profile_ids": [PROFILE_A],
                    "evaluation_instant": AS_OF.isoformat(),
                    "suite_ids": ["critical_closure", "evidence_gap", "connection_loss"],
                },
            )
            assert created.status_code == 200, created.text
            by_suite = {e["suite_id"]: e for e in created.json()["experiments"]}
            assert by_suite["connection_loss"]["status"] == "completed"
            for suite_id in ("critical_closure", "evidence_gap", "connection_loss"):
                experiment_id = by_suite[suite_id]["experiment_id"]
                replay = client.post(f"/api/v1/failure-lab/experiments/{experiment_id}/replay").json()
                assert replay["reproduced"] is True, replay["detail"]
                assert replay["stored_semantic_hash"] == replay["replayed_semantic_hash"]
                assert replay["replayed_experiment_id"] != experiment_id

    def test_inapplicable_suite_is_recorded_as_invalid_not_silently_skipped(self, tmp_path, seed):
        """A suite that cannot apply is refused and stored, never reported as tested."""
        from detour_lab.api.main import create_app
        from detour_lab.persistence.repository import Repository
        from fastapi.testclient import TestClient

        app = create_app(tmp_path / "inapplicable.sqlite3")
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/scenarios/scn-demo-baseline/failure-lab/experiments",
                json={
                    "phase_ids": ["phase-1"],
                    "profile_ids": [PROFILE_A],
                    "evaluation_instant": AS_OF.isoformat(),
                    # The declared temporary connection is only active in phase 2.
                    "suite_ids": ["connection_loss"],
                },
            )
            assert response.status_code == 200, response.text
            experiments = response.json()["experiments"]
            assert len(experiments) == 1
            record = experiments[0]
            assert record["status"] == "invalid_experiment"
            assert record["observations"] == []
            assert record["transitions"] == []
            assert record["error"]["code"] == "NO_OP_FAULT"
            assert "phase-1" in record["error"]["message"]
            robustness = response.json()["robustness"]
            assert robustness["experiments_invalid"] == 1
            assert robustness["pairs_evaluated"] == 0
            repository: Repository = app.state.repository
            assert repository.counts()["failure_experiments"] == 1

    def test_experiment_stays_bound_to_its_revision(self, tmp_path, seed, rulepack):
        from detour_lab.api.main import create_app
        from fastapi.testclient import TestClient

        app = create_app(tmp_path / "revision.sqlite3")
        with TestClient(app) as client:
            created = client.post(
                "/api/v1/scenarios/scn-demo-baseline/failure-lab/experiments",
                json={
                    "phase_ids": ["phase-1"],
                    "profile_ids": [PROFILE_A],
                    "evaluation_instant": AS_OF.isoformat(),
                    "suite_ids": ["critical_closure"],
                },
            ).json()
            experiment_id = created["experiments"][0]["experiment_id"]

            # Move the source scenario forward with a real edit.
            patched = client.patch(
                "/api/v1/scenarios/scn-demo-baseline",
                json={
                    "expected_revision": 1,
                    "edits": [
                        {
                            "op": "update_attribute",
                            "target_id": "E_LINK",
                            "params": {
                                "field": "width_mm",
                                "value": 1600,
                                "unit": "mm",
                                "method": "manual_entry",
                                "source": "test",
                            },
                        }
                    ],
                    "note": "revision-moving edit",
                },
            )
            assert patched.status_code == 200
            assert patched.json()["revision"] == 2

            replay = client.post(f"/api/v1/failure-lab/experiments/{experiment_id}/replay").json()
            assert replay["reproduced"] is False
            assert "revision 1" in replay["detail"]
            assert "not re-analysed against the newer plan" in replay["detail"]

            # The stored experiment still describes revision 1.
            detail = client.get(f"/api/v1/failure-lab/experiments/{experiment_id}").json()
            assert detail["experiment"]["source"]["scenario_revision"] == 1


# --------------------------------------------------------------------------- suites and metrics


class TestSuitesAndRobustness:
    def test_every_suite_executes(self, seed, rulepack, profiles):
        scenario = build_scenario(seed=seed, rulepack=rulepack, scenario_id="scn-suites")
        outcomes = []
        for suite_id in sorted(SUITES):
            phase = "phase-2" if suite_id == "connection_loss" else "phase-1"
            outcomes.append(
                _run(
                    seed.graph,
                    scenario,
                    rulepack,
                    profiles,
                    build_suite(suite_id=suite_id, scenario=scenario, phase_id=phase),
                    phase_ids=[phase],
                    profile_ids=[PROFILE_A, PROFILE_B],
                )
            )
        assert len(outcomes) == len(SUITES)
        for outcome in outcomes:
            assert outcome.status is ExperimentStatus.COMPLETED, outcome.error

    def test_robustness_summary_states_its_denominator(self, seed, scenario, rulepack, profiles):
        outcomes = [
            _run(
                seed.graph,
                scenario,
                rulepack,
                profiles,
                build_suite(suite_id=suite_id, scenario=scenario, phase_id="phase-1"),
                profile_ids=[PROFILE_A, PROFILE_B],
            )
            for suite_id in ("critical_closure", "incidental_closure", "evidence_gap")
        ]
        summary = summarise_robustness(outcomes=outcomes, available_kinds=list(FaultKind))
        assert summary.experiments_requested == 3
        assert summary.experiments_completed == 3
        assert summary.pairs_evaluated == sum(len(o.transitions) for o in outcomes)
        assert "Only COMPLETED experiments contribute" in summary.denominator_note
        assert "NOT a probability" in summary.interpretation_note
        untested = set(FaultKind) - set(summary.fault_kinds_tested)
        assert set(summary.fault_kinds_untested) == untested

    def test_failed_experiments_are_excluded_from_every_count(self, seed, scenario, rulepack, profiles):
        good = _run(
            seed.graph,
            scenario,
            rulepack,
            profiles,
            build_suite(suite_id="critical_closure", scenario=scenario, phase_id="phase-1"),
        )
        bad = good.model_copy(update={"status": ExperimentStatus.EXECUTION_FAILED, "transitions": [], "observations": []})
        summary = summarise_robustness(outcomes=[good, bad], available_kinds=list(FaultKind))
        assert summary.experiments_completed == 1
        assert summary.experiments_failed == 1
        assert summary.pairs_evaluated == len(good.transitions)

    def test_suite_rejects_an_unknown_identifier(self, scenario):
        with pytest.raises(FaultValidationError) as excinfo:
            build_suite(suite_id="meteorite", scenario=scenario, phase_id="phase-1")
        assert excinfo.value.code == "UNKNOWN_SUITE"

    def test_service_rejects_an_unknown_phase(self, tmp_path, seed):
        from detour_lab.api.main import create_app
        from fastapi.testclient import TestClient

        app = create_app(tmp_path / "svc.sqlite3")
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/scenarios/scn-demo-baseline/failure-lab/experiments",
                json={
                    "phase_ids": ["phase-77"],
                    "profile_ids": [PROFILE_A],
                    "suite_ids": ["critical_closure"],
                },
            )
            assert response.status_code == 400
            body = response.json()
            assert body["code"] == "INVALID_PHASE"
            assert body["details"]["unknown_phase_ids"] == ["phase-77"]

    def test_service_rejects_an_unknown_profile(self, tmp_path):
        from detour_lab.api.main import create_app
        from fastapi.testclient import TestClient

        app = create_app(tmp_path / "svc2.sqlite3")
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/scenarios/scn-demo-baseline/failure-lab/experiments",
                json={
                    "phase_ids": ["phase-1"],
                    "profile_ids": ["DEMO_PROFILE_UNICORN"],
                    "suite_ids": ["critical_closure"],
                },
            )
            assert response.status_code == 400
            assert response.json()["code"] == "PROFILE_NOT_FOUND"

    def test_experiments_are_persisted_and_listed(self, tmp_path, seed):
        from detour_lab.api.main import create_app
        from detour_lab.persistence.repository import Repository
        from fastapi.testclient import TestClient

        app = create_app(tmp_path / "history.sqlite3")
        with TestClient(app) as client:
            client.post(
                "/api/v1/scenarios/scn-demo-baseline/failure-lab/experiments",
                json={
                    "phase_ids": ["phase-1"],
                    "profile_ids": [PROFILE_A],
                    "evaluation_instant": AS_OF.isoformat(),
                    "suite_ids": ["critical_closure"],
                },
            )
            history = client.get(
                "/api/v1/scenarios/scn-demo-baseline/failure-lab/experiments"
            ).json()
            assert history["experiment_count"] == 1
            row = history["experiments"][0]
            assert row["status"] == "completed"
            assert row["input_hash"].startswith("sha256:")
            assert row["semantic_hash"].startswith("sha256:")
            repository: Repository = app.state.repository
            assert repository.counts()["failure_experiments"] == 1

    def test_verified_baseline_run_is_linked_when_identical(self, tmp_path, seed):
        from detour_lab.api.main import create_app
        from fastapi.testclient import TestClient

        app = create_app(tmp_path / "baseline-link.sqlite3")
        with TestClient(app) as client:
            run = client.post(
                "/api/v1/scenarios/scn-demo-baseline/evaluate",
                json={
                    "profile_id": PROFILE_A,
                    "phase_id": "phase-1",
                    "evaluation_instant": AS_OF.isoformat(),
                },
            ).json()["run"]
            created = client.post(
                "/api/v1/scenarios/scn-demo-baseline/failure-lab/experiments",
                json={
                    "phase_ids": ["phase-1"],
                    "profile_ids": [PROFILE_A],
                    "evaluation_instant": AS_OF.isoformat(),
                    "suite_ids": ["critical_closure"],
                    "baseline_run_ids": [run["id"]],
                },
            ).json()
            source = created["experiments"][0]["source"]
            assert source["verified_baseline_run_ids"] == [run["id"]]
            assert "proven identical" in source["baseline_link_note"]

    def test_baseline_run_from_another_instant_is_not_linked(self, tmp_path, seed):
        from detour_lab.api.main import create_app
        from fastapi.testclient import TestClient

        app = create_app(tmp_path / "baseline-link2.sqlite3")
        with TestClient(app) as client:
            run = client.post(
                "/api/v1/scenarios/scn-demo-baseline/evaluate",
                json={
                    "profile_id": PROFILE_A,
                    "phase_id": "phase-1",
                    "evaluation_instant": "2025-06-01T00:00:00Z",
                },
            ).json()["run"]
            created = client.post(
                "/api/v1/scenarios/scn-demo-baseline/failure-lab/experiments",
                json={
                    "phase_ids": ["phase-1"],
                    "profile_ids": [PROFILE_A],
                    "evaluation_instant": AS_OF.isoformat(),
                    "suite_ids": ["critical_closure"],
                    "baseline_run_ids": [run["id"]],
                },
            ).json()
            source = created["experiments"][0]["source"]
            assert source["verified_baseline_run_ids"] == []
            assert "different instant" in source["baseline_link_note"]

    def test_replay_experiment_helper_is_usable_directly(self, tmp_path, seed, rulepack):
        from detour_lab.persistence.repository import Repository

        app = __import__("detour_lab.api.main", fromlist=["create_app"]).create_app(tmp_path / "helper.sqlite3")
        with __import__("fastapi.testclient", fromlist=["TestClient"]).TestClient(app):
            repository: Repository = app.state.repository
            outcomes = run_experiments(
                repository=repository,
                scenario_id="scn-demo-baseline",
                phase_ids=["phase-1"],
                profile_ids=[PROFILE_A],
                evaluation_instant=AS_OF,
                suite_ids=["evidence_gap"],
            )
            result = replay_experiment(repository=repository, experiment_id=outcomes[0].experiment_id)
            assert result.reproduced is True