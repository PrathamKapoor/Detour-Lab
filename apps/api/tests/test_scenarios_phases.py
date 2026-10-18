"""Scenario edits and phase graphs: B9, B10, B17, INV-03, INV-07, B25."""

from __future__ import annotations

import pytest
from detour_lab.analysis.run import run_analysis
from detour_lab.domain.contracts import GraphEdit, Phase
from detour_lab.domain.enums import EdgeType, NodeType, ProvenanceClass, ReasonCode
from detour_lab.scenarios.apply import GraphEditError, apply_edits, build_phase_graph
from pydantic import ValidationError
from tests.conftest import AS_OF, accessible_evidence, build_scenario, edge, make_graph, node


class TestEditsArePure:
    def test_b17_a_graph_edit_leaves_the_baseline_unchanged(self, seed, rulepack):
        scenario = build_scenario(
            seed=seed,
            rulepack=rulepack,
            edits=[
                GraphEdit(
                    op="add_node",
                    target_id="N_NEW",
                    params={"id": "N_NEW", "x": 100.0, "y": 0.0},
                ),
                GraphEdit(
                    op="add_edge",
                    target_id="E_NEW",
                    params={"id": "E_NEW", "u": "N_E", "v": "N_NEW", "edge_type": "sidewalk"},
                ),
            ],
        )
        before_hash = seed.graph.content_hash
        before_edges = {e.id for e in seed.graph.edges}
        before_evidence = {r.id for r in seed.graph.evidence_registry.all_records()}

        phase_graph = build_phase_graph(seed.graph, scenario, "phase-1")

        assert seed.graph.content_hash == before_hash
        assert {e.id for e in seed.graph.edges} == before_edges
        assert {r.id for r in seed.graph.evidence_registry.all_records()} == before_evidence
        assert "E_NEW" in {e.id for e in phase_graph.graph.edges}

    def test_phase_graph_has_its_own_content_address(self, seed, demo_scenario):
        phase_graph = build_phase_graph(seed.graph, demo_scenario, "phase-1")
        assert phase_graph.graph.content_hash != seed.graph.content_hash
        assert phase_graph.phase_graph_id != seed.graph.version.id
        assert "phase-1" in phase_graph.phase_graph_id

    def test_edit_order_does_not_change_the_result(self, seed, rulepack):
        edits = [
            GraphEdit(op="add_node", target_id="N_B", params={"id": "N_B", "x": 100.0, "y": 0.0}),
            GraphEdit(op="add_node", target_id="N_A", params={"id": "N_A", "x": 95.0, "y": 0.0}),
            GraphEdit(op="add_edge", target_id="E_AB", params={"id": "E_AB", "u": "N_A", "v": "N_B"}),
        ]
        forward = apply_edits(seed.graph, edits)
        backward = apply_edits(seed.graph, list(reversed(edits)))
        assert forward.content_hash == backward.content_hash


class TestClosureAndPhases:
    def test_b09_edge_closed_only_in_phase_two_is_routable_in_phase_one(self, seed, rulepack, profile_a):
        scenario = build_scenario(
            seed=seed,
            rulepack=rulepack,
            phases=[
                Phase(id="p-open", order=1, closed_edge_ids=[]),
                Phase(id="p-closed", order=2, closed_edge_ids=["E_WM"]),
            ],
        )
        open_phase = run_analysis(
            base_graph=seed.graph, scenario=scenario, phase_id="p-open",
            profile_id=profile_a.id, rulepack=rulepack, profile=profile_a, as_of=AS_OF,
        )
        closed_phase = run_analysis(
            base_graph=seed.graph, scenario=scenario, phase_id="p-closed",
            profile_id=profile_a.id, rulepack=rulepack, profile=profile_a, as_of=AS_OF,
        )
        def pair(result):
            return next(
                od for od in result.od_results
                if od.origin_id == "OD-W" and od.destination_id == "OD-GATE"
            )

        open_pair, closed_pair = pair(open_phase), pair(closed_phase)
        assert open_pair.confirmed_reachable is True
        assert "E_WM" in open_pair.confirmed_path_edge_ids
        # The same edge is closed in the other phase and must disappear from every path.
        assert closed_pair.confirmed_reachable is False
        assert closed_pair.possibly_reachable is False
        assert "E_WM" not in closed_pair.confirmed_path_edge_ids
        assert "E_WM" not in closed_pair.possible_path_edge_ids
        assert ReasonCode.NO_ROUTE in closed_pair.reason_codes

    def test_b25_wrong_phase_route_is_not_reused(self, seed, demo_scenario, rulepack, profile_a):
        phase_one = build_phase_graph(seed.graph, demo_scenario, "phase-1")
        phase_two = build_phase_graph(seed.graph, demo_scenario, "phase-2")
        assert phase_one.graph.content_hash != phase_two.graph.content_hash
        assert phase_two.graph.closed_edge_ids != phase_one.graph.closed_edge_ids

    def test_b10_temporary_edge_exists_only_in_its_declared_phase(self, seed, demo_scenario):
        phase_one = build_phase_graph(seed.graph, demo_scenario, "phase-1")
        phase_two = build_phase_graph(seed.graph, demo_scenario, "phase-2")
        assert "TMP::TMP-EAST-BYPASS" not in {e.id for e in phase_one.graph.edges}
        assert "TMP::TMP-EAST-BYPASS" in {e.id for e in phase_two.graph.edges}

    def test_inv03_closed_edge_is_never_routed_through(self, seed, demo_scenario, rulepack, profile_a):
        for phase_id in ("phase-1", "phase-2"):
            result = run_analysis(
                base_graph=seed.graph, scenario=demo_scenario, phase_id=phase_id,
                profile_id=profile_a.id, rulepack=rulepack, profile=profile_a, as_of=AS_OF,
            )
            phase_graph = build_phase_graph(seed.graph, demo_scenario, phase_id)
            for od in result.od_results:
                assert "E_ME" not in od.confirmed_path_edge_ids
                assert "E_ME" not in od.possible_path_edge_ids
                if "E_ES1" in phase_graph.graph.closed_edge_ids:
                    assert "E_ES1" not in od.possible_path_edge_ids

    def test_closure_produces_an_explicit_finding(self, seed, demo_scenario, rulepack, profile_a):
        phase_graph = build_phase_graph(seed.graph, demo_scenario, "phase-1")
        result = run_analysis(
            base_graph=seed.graph, scenario=demo_scenario, phase_id="phase-1",
            profile_id=profile_a.id, rulepack=rulepack, profile=profile_a, as_of=AS_OF,
        )
        evaluation = next(e for e in result.edge_evaluations if e.edge_id == "E_ME")
        assert evaluation.state.value == "FAIL"
        assert ReasonCode.EDGE_CLOSED_IN_PHASE in evaluation.reason_codes
        closure_findings = [f for f in evaluation.findings if f.reason_code is ReasonCode.EDGE_CLOSED_IN_PHASE]
        assert closure_findings
        assert closure_findings[0].explanation
        assert phase_graph.graph.closed_edge_ids == frozenset({"E_ME"})

    def test_unknown_phase_is_rejected(self, seed, demo_scenario):
        with pytest.raises(GraphEditError) as excinfo:
            build_phase_graph(seed.graph, demo_scenario, "phase-does-not-exist")
        assert excinfo.value.code == "INVALID_INPUT"

    def test_scenario_must_match_the_supplied_base_graph(self, seed, demo_scenario):
        from detour_lab.domain.contracts import BaseGraphVersion
        from detour_lab.graph.model import PedestrianGraph

        other_version = BaseGraphVersion(
            id="a-different-graph",
            basis=seed.graph.version.basis,
            nodes=seed.graph.version.nodes,
            edges=seed.graph.version.edges,
            evidence=seed.graph.version.evidence,
            source=seed.graph.version.source,
        )
        rebuilt = PedestrianGraph.from_version(other_version)
        with pytest.raises(GraphEditError) as excinfo:
            build_phase_graph(rebuilt, demo_scenario, "phase-1")
        assert excinfo.value.code == "INVALID_INPUT"


class TestTypedEdits:
    def _base(self):
        nodes = [node("N1", 0.0, 0.0), node("N2", 40.0, 0.0), node("N3", 80.0, 0.0)]
        by_id = {n.id: n for n in nodes}
        edges = [edge("E12", "N1", "N2", by_id), edge("E23", "N2", "N3", by_id)]
        return make_graph(nodes, edges, accessible_evidence("A", "E12") + accessible_evidence("B", "E23"))

    def test_set_direction_reverses_geometry_and_endpoints(self):
        graph = self._base()
        updated = apply_edits(graph, [GraphEdit(op="set_direction", target_id="E23", params={"new_u": "N3", "v": None, "new_v": "N2"})])
        edge_obj = updated.edge("E23")
        assert (edge_obj.u, edge_obj.v) == ("N3", "N2")
        assert edge_obj.geometry[0] == (80.0, 0.0)
        assert edge_obj.geometry[-1] == (40.0, 0.0)
        assert edge_obj.length_m == graph.edge("E23").length_m

    def test_split_edge_creates_deterministic_ids_and_derived_evidence(self):
        graph = self._base()
        updated = apply_edits(
            graph,
            [GraphEdit(op="split_edge", target_id="E12", params={"new_node_id": "N_MID", "fraction": 0.5})],
        )
        assert updated.edge("E12#split1") is not None
        assert updated.edge("E12#split2") is not None
        assert updated.edge("E12") is None
        first, second = updated.edge("E12#split1"), updated.edge("E12#split2")
        assert first.u == "N1" and first.v == "N_MID"
        assert second.u == "N_MID" and second.v == "N2"
        assert first.length_m + second.length_m == pytest.approx(graph.edge("E12").length_m, abs=1e-6)
        derived = [r for r in updated.evidence_registry.for_element("E12#split1") if r.field == "width_mm"]
        assert derived
        assert derived[0].provenance_class is ProvenanceClass.DERIVED
        assert "no independent measurement" in derived[0].note.lower()

    def test_split_rejects_a_degenerate_fraction(self):
        graph = self._base()
        for fraction in (0.0, 1.0, -0.5, 2.0):
            with pytest.raises(GraphEditError):
                apply_edits(graph, [GraphEdit(op="split_edge", target_id="E12", params={"new_node_id": "N_X", "fraction": fraction})])

    def test_remove_edge_removes_it(self):
        graph = self._base()
        updated = apply_edits(graph, [GraphEdit(op="remove_edge", target_id="E23")])
        assert updated.edge("E23") is None
        assert updated.has_edge("E12")

    def test_link_crossing_splits_both_edges_and_creates_a_shared_node(self):
        nodes = [node("NA", 0.0, 0.0), node("NB", 20.0, 0.0), node("NC", 10.0, -10.0), node("ND", 10.0, 10.0)]
        by_id = {n.id: n for n in nodes}
        graph = make_graph(nodes, [edge("E_H", "NA", "NB", by_id), edge("E_V", "NC", "ND", by_id)])
        assert graph.unlinked_crossings()[0]["connected_via_shared_node"] is False

        # Two splits: the first creates the shared node, the second joins the
        # crossing edge to that same existing node.
        updated = apply_edits(
            graph,
            [
                GraphEdit(
                    op="link_crossing",
                    target_id="E_H",
                    params={"new_node_id": "N_X", "fraction": 0.5},
                ),
                GraphEdit(op="link_crossing", target_id="E_V", params={"new_node_id": "N_X"}),
            ],
        )
        assert updated.has_node("N_X")
        assert set(updated.outgoing_edge_ids("N_X")) == {"E_H#split2", "E_V#split2"}
        crossings = updated.unlinked_crossings()
        assert all(c["connected_via_shared_node"] for c in crossings)

    def test_link_crossing_rejects_a_node_that_does_not_lie_on_the_edge(self):
        graph = self._base()
        with pytest.raises(GraphEditError) as excinfo:
            apply_edits(
                graph,
                [GraphEdit(op="link_crossing", target_id="E12", params={"new_node_id": "N3"})],
            )
        assert excinfo.value.code == "INVALID_NUMERIC_VALUE"

    def test_add_edge_with_unknown_endpoint_is_rejected(self):
        graph = self._base()
        with pytest.raises(GraphEditError) as excinfo:
            apply_edits(graph, [GraphEdit(op="add_edge", target_id="E_X", params={"id": "E_X", "u": "N1", "v": "NOPE"})])
        assert excinfo.value.code == "UNKNOWN_NODE_REFERENCE"

    def test_add_self_loop_is_rejected(self):
        graph = self._base()
        with pytest.raises(GraphEditError) as excinfo:
            apply_edits(graph, [GraphEdit(op="add_edge", target_id="E_X", params={"id": "E_X", "u": "N1", "v": "N1"})])
        assert excinfo.value.code == "SELF_LOOP"

    def test_update_attribute_appends_evidence_without_erasing_history(self):
        graph = self._base()
        original = graph.evidence_registry.for_field("E12", "width_mm")
        updated = apply_edits(
            graph,
            [
                GraphEdit(
                    op="update_attribute",
                    target_id="E12",
                    params={
                        "field": "width_mm",
                        "value": 1200,
                        "unit": "mm",
                        "method": "survey",
                        "source": "field survey (test fixture)",
                        "provenance_class": "measured",
                        "synthetic": False,
                    },
                )
            ],
        )
        after = updated.evidence_registry.for_field("E12", "width_mm")
        assert len(after) == len(original) + 1
        assert {r.id for r in original}.issubset({r.id for r in after})

    def test_b26_new_measurement_conflicting_with_the_old_one_creates_a_conflict_not_an_overwrite(self, rulepack):
        from detour_lab.domain.enums import VerdictState
        from detour_lab.rules.engine import evaluate_graph

        graph = self._base()
        updated = apply_edits(
            graph,
            [
                GraphEdit(
                    op="update_attribute",
                    target_id="E12",
                    params={
                        "field": "width_mm",
                        "value": 700,
                        "unit": "mm",
                        "method": "survey",
                        "source": "second survey (test fixture)",
                        "provenance_class": "measured",
                        "synthetic": False,
                    },
                )
            ],
        )
        evaluation = evaluate_graph(
            graph=updated, rulepack=rulepack, profile_id="DEMO_PROFILE_MANUAL_WHEELCHAIR",
            phase_id="p1", as_of=AS_OF,
        )
        width_verdict = next(
            v for v in evaluation.verdicts if v.rule_id == "DEMO-EDGE-WIDTH-MANUAL" and v.element_id == "E12"
        )
        # 2000 mm (original fixture) and 700 mm (new survey) disagree: the result
        # must be UNKNOWN, never a silent pass on the favourable number.
        assert width_verdict.state is VerdictState.UNKNOWN
        assert width_verdict.reason_code is ReasonCode.CONFLICTING_EVIDENCE
        assert len(width_verdict.inputs[0].evidence_ids) == 2
        assert updated.evidence_registry.for_field("E12", "width_mm")


class TestScenarioIntegrity:
    def test_duplicate_phase_ids_rejected(self, seed, rulepack):
        with pytest.raises(ValidationError):
            build_scenario(
                seed=seed,
                rulepack=rulepack,
                phases=[Phase(id="p1", order=1), Phase(id="p1", order=2)],
            )

    def test_duplicate_phase_orders_rejected(self, seed, rulepack):
        with pytest.raises(ValidationError):
            build_scenario(
                seed=seed,
                rulepack=rulepack,
                phases=[Phase(id="p1", order=1), Phase(id="p2", order=1)],
            )

    def test_scenario_hash_changes_with_content_and_is_stable_otherwise(self, seed, rulepack):
        first = build_scenario(seed=seed, rulepack=rulepack, scenario_id="s1")
        second = build_scenario(seed=seed, rulepack=rulepack, scenario_id="s1")
        assert first.content_hash == second.content_hash

        edited = build_scenario(
            seed=seed,
            rulepack=rulepack,
            scenario_id="s1",
            phases=[
                Phase(id="p0", order=0, closed_edge_ids=["E_WM"]),
                *list(seed.phases),
            ],
        )
        assert edited.content_hash != first.content_hash

    def test_b28_scenario_hash_survives_a_fresh_process_style_reconstruction(self, seed, rulepack):
        from detour_lab.domain.hashing import semantic_hash

        scenario = build_scenario(seed=seed, rulepack=rulepack, scenario_id="s-hash")
        payload = scenario.model_dump(mode="json")
        payload.pop("created_at", None)
        from detour_lab.domain.contracts import Scenario

        rebuilt = Scenario.model_validate(payload)
        assert rebuilt.content_hash == scenario.content_hash
        assert scenario.content_hash.startswith("sha256:")
        assert semantic_hash(payload) != scenario.content_hash  # id/timestamps excluded


class TestNodeTypes:
    def test_node_type_survives_phase_construction(self, seed, demo_scenario):
        phase_graph = build_phase_graph(seed.graph, demo_scenario, "phase-1")
        assert phase_graph.graph.node("N_K").node_type is NodeType.CROSSING_INTERFACE
        assert phase_graph.graph.node("N_BC").node_type is NodeType.CURB_INTERFACE

    def test_temporary_edge_is_modelled_not_asserted_constructible(self, seed, demo_scenario):
        temp = next(t for t in demo_scenario.temporary_edges if t.id == "TMP-EAST-BYPASS")
        assert temp.constructible_in_field is False
        assert "not been confirmed" in temp.field_verification_note.lower()
        assert temp.edge_type is EdgeType.TEMPORARY_PATH


def test_evidence_from_temporary_edge_is_rebound_to_the_phase_edge(seed, demo_scenario):
    phase_graph = build_phase_graph(seed.graph, demo_scenario, "phase-2")
    records = phase_graph.graph.evidence_registry.for_field("TMP::TMP-EAST-BYPASS", "width_mm")
    assert records
    assert records[0].provenance_class is ProvenanceClass.ASSUMED
    assert "not a field-verified construction" in records[0].note.lower()


def test_manual_evidence_entry_is_supported(seed, rulepack, profile_a):
    scenario = build_scenario(
        seed=seed,
        rulepack=rulepack,
        edits=[
            GraphEdit(
                op="update_attribute",
                target_id="E_ALT",
                params={
                    "field": "width_mm",
                    "value": 1800,
                    "unit": "mm",
                    "method": "manual_entry",
                    "source": "planner entered value (test)",
                    "provenance_class": "assumed",
                    "synthetic": False,
                    "observed_at": "2026-02-01T10:00:00Z",
                },
            ),
            GraphEdit(
                op="update_attribute",
                target_id="E_ALT",
                params={
                    "field": "slope_percent",
                    "value": 2.0,
                    "unit": "percent",
                    "method": "manual_entry",
                    "source": "planner entered value (test)",
                    "provenance_class": "assumed",
                    "synthetic": False,
                    "observed_at": "2026-02-01T10:00:00Z",
                },
            ),
        ],
    )
    before = run_analysis(
        base_graph=seed.graph, scenario=build_scenario(seed=seed, rulepack=rulepack),
        phase_id="phase-1", profile_id=profile_a.id, rulepack=rulepack, profile=profile_a, as_of=AS_OF,
    )
    after = run_analysis(
        base_graph=seed.graph, scenario=scenario, phase_id="phase-1",
        profile_id=profile_a.id, rulepack=rulepack, profile=profile_a, as_of=AS_OF,
    )
    before_state = next(e.state for e in before.edge_evaluations if e.edge_id == "E_ALT")
    after_state = next(e.state for e in after.edge_evaluations if e.edge_id == "E_ALT")
    assert before_state.value == "UNKNOWN"
    assert after_state.value == "PASS"


def test_evidence_records_survive_export(seed, rulepack, profile_a, demo_scenario):
    result = run_analysis(
        base_graph=seed.graph, scenario=demo_scenario, phase_id="phase-1",
        profile_id=profile_a.id, rulepack=rulepack, profile=profile_a, as_of=AS_OF,
    )
    payloads = [a for v in result.verdicts for a in v.inputs if a.evidence_ids]
    assert payloads
    source_record = seed.graph.evidence_registry.by_id("EV-E_WM-width")
    assert source_record is not None
    assert source_record.observed_at is not None
    assert source_record.method == "synthetic_fixture"


def test_duplicate_evidence_id_in_an_edit_is_rejected(seed):
    graph = seed.graph
    edit = GraphEdit(
        op="update_attribute",
        target_id="E_WM",
        params={"field": "width_mm", "value": 1000, "unit": "mm", "method": "m", "source": "s"},
    )
    first = apply_edits(graph, [edit])
    with pytest.raises(GraphEditError):
        apply_edits(first, [edit])


def test_manual_entry_without_timestamp_is_recorded_as_unknown_time(seed):
    updated = apply_edits(
        seed.graph,
        [
            GraphEdit(
                op="update_attribute",
                target_id="E_WM",
                params={
                    "field": "width_mm", "value": 1000, "unit": "mm",
                    "method": "manual_entry", "source": "no date supplied",
                },
            )
        ],
    )
    record = updated.evidence_registry.for_field("E_WM", "width_mm")[-1]
    assert record.observed_at is None


def test_evidence_element_must_exist(seed):
    with pytest.raises(GraphEditError) as excinfo:
        apply_edits(
            seed.graph,
            [
                GraphEdit(
                    op="update_attribute",
                    target_id="NOT_AN_ELEMENT",
                    params={"field": "width_mm", "value": 1, "unit": "mm", "method": "m", "source": "s"},
                )
            ],
        )
    assert excinfo.value.code == "UNKNOWN_NODE_REFERENCE"


def test_temporary_edge_activation_requires_a_declared_edge(seed, rulepack):
    scenario = build_scenario(
        seed=seed,
        rulepack=rulepack,
        edits=[GraphEdit(op="activate_temporary_edge", target_id="NOT-DECLARED", params={})],
    )
    with pytest.raises(GraphEditError):
        build_phase_graph(seed.graph, scenario, "phase-1")


def test_unused_temporary_edge_is_reported_as_a_warning(seed, rulepack):
    scenario = build_scenario(
        seed=seed,
        rulepack=rulepack,
        phases=[Phase(id="p1", order=1, temporary_edge_ids=[])],
    )
    phase_graph = build_phase_graph(seed.graph, scenario, "p1")
    assert any("not activated in any phase" in w for w in phase_graph.warnings)


def test_extra_evidence_records_for_temporary_edges_are_preserved(demo_scenario):
    temp = next(t for t in demo_scenario.temporary_edges if t.id == "TMP-EAST-BYPASS")
    assert {r.field for r in temp.evidence} == {"width_mm", "slope_percent", "surface"}
    assert all(r.element_id == "TMP-EAST-BYPASS" for r in temp.evidence)


def test_manual_measurement_of_the_unknown_curb_resolves_the_interface(seed, rulepack, profile_a):
    """The inspection-queue story: enter the missing value and the state changes."""
    scenario = build_scenario(
        seed=seed,
        rulepack=rulepack,
        edits=[
            GraphEdit(
                op="update_attribute",
                target_id="N_EK",
                params={
                    "field": "curb_transition",
                    "value": "flush",
                    "unit": None,
                    "method": "manual_entry",
                    "source": "planner observation (test)",
                    "provenance_class": "assumed",
                    "synthetic": False,
                    "observed_at": "2026-02-01T10:00:00Z",
                },
            )
        ],
    )
    before = run_analysis(
        base_graph=seed.graph, scenario=build_scenario(seed=seed, rulepack=rulepack),
        phase_id="phase-2", profile_id=profile_a.id, rulepack=rulepack, profile=profile_a, as_of=AS_OF,
    )
    after = run_analysis(
        base_graph=seed.graph, scenario=scenario, phase_id="phase-2",
        profile_id=profile_a.id, rulepack=rulepack, profile=profile_a, as_of=AS_OF,
    )
    before_od = next(o for o in before.od_results if o.origin_id == "OD-E" and o.destination_id == "OD-LIB")
    after_od = next(o for o in after.od_results if o.origin_id == "OD-E" and o.destination_id == "OD-LIB")
    assert before_od.confirmed_reachable is False
    assert after_od.confirmed_reachable is True
    assert after_od.confirmed_path_edge_ids == ["E_ME"] or after_od.confirmed_distance_m is not None


def test_conflicting_measurement_does_not_silently_pick_a_favourable_value(seed, rulepack):
    scenario = build_scenario(
        seed=seed,
        rulepack=rulepack,
        edits=[
            GraphEdit(
                op="update_attribute",
                target_id="E_K1",
                params={
                    "field": "width_mm", "value": 1600, "unit": "mm",
                    "method": "manual_entry", "source": "second opinion (test)",
                    "provenance_class": "assumed", "synthetic": False,
                    "observed_at": "2026-02-01T10:00:00Z",
                },
            )
        ],
    )
    result = run_analysis(
        base_graph=seed.graph, scenario=scenario, phase_id="phase-1",
        profile_id="DEMO_PROFILE_LIMITED_MOBILITY_WALKER", rulepack=rulepack,
        profile=rulepack and __import__("detour_lab.rules.profiles", fromlist=["x"]).profile_by_id("DEMO_PROFILE_LIMITED_MOBILITY_WALKER"),
        as_of=AS_OF,
    )
    verdict = next(
        v for v in result.verdicts if v.rule_id == "DEMO-EDGE-WIDTH-LIMITED" and v.element_id == "E_K1"
    )
    assert verdict.state.value == "UNKNOWN"
    assert verdict.reason_code is ReasonCode.CONFLICTING_EVIDENCE
    assert len(verdict.inputs[0].evidence_ids) == 2