"""Feasibility graphs and deterministic routing: B11, B12, B32, tie-breaking."""

from __future__ import annotations

import pytest
from detour_lab.analysis.run import run_analysis
from detour_lab.domain.enums import ReasonCode, VerdictState
from detour_lab.graph.routing import build_feasibility_graphs, shortest_path
from hypothesis import given, settings
from hypothesis import strategies as st
from tests.conftest import (
    AS_OF,
    accessible_evidence,
    build_scenario,
    edge,
    make_graph,
    node,
    simple_line_graph,
)


class TestFeasibilityGraphs:
    def test_confirmed_and_possible_partition_states(self):
        graph = simple_line_graph()
        states = {"E12": VerdictState.PASS, "E23": VerdictState.UNKNOWN, "E99": VerdictState.FAIL}
        feasibility = build_feasibility_graphs(graph, states)
        assert feasibility.confirmed_edge_ids == frozenset({"E12"})
        assert feasibility.possible_edge_ids == frozenset({"E12", "E23"})
        assert "E23" not in feasibility.confirmed_edge_ids

    def test_closed_edges_are_in_neither_graph(self):
        nodes = [node("N1", 0.0, 0.0), node("N2", 10.0, 0.0)]
        by_id = {n.id: n for n in nodes}
        version_nodes = nodes
        from detour_lab.domain.contracts import BaseGraphVersion
        from tests.conftest import PLANAR_BASIS, SYNTHETIC_SOURCE

        version = BaseGraphVersion(
            id="g",
            basis=PLANAR_BASIS,
            nodes=version_nodes,
            edges=[edge("E12", "N1", "N2", by_id)],
            inactive_edge_ids=["E12"],
            evidence=accessible_evidence("A", "E12"),
            source=SYNTHETIC_SOURCE,
        )
        from detour_lab.graph.model import PedestrianGraph

        graph = PedestrianGraph.from_version(version)
        feasibility = build_feasibility_graphs(graph, {"E12": VerdictState.PASS})
        assert feasibility.confirmed_edge_ids == frozenset()
        assert feasibility.possible_edge_ids == frozenset()

    def test_not_applicable_edges_are_not_confirmed(self):
        """A rulepack that covers nothing cannot silently clear an edge."""
        graph = simple_line_graph()
        feasibility = build_feasibility_graphs(graph, {"E12": VerdictState.NOT_APPLICABLE, "E23": VerdictState.PASS})
        assert "E12" not in feasibility.confirmed_edge_ids
        assert "E12" not in feasibility.possible_edge_ids


class TestDeterministicRouting:
    def test_tie_between_equal_length_paths_breaks_lexicographically(self):
        """Two 20 m routes; the documented rule picks the lower edge-ID sequence."""
        nodes = [node("S", 0.0, 0.0), node("T", 20.0, 0.0)]
        by_id = {n.id: n for n in nodes}
        edges = [
            edge("E_ALPHA", "S", "T", by_id, mid=(10.0, 0.0)),  # two collinear segments
            edge("E_BETA", "S", "T", by_id),  # one straight segment
        ]
        assert edges[0].length_m == edges[1].length_m == 20.0
        graph = make_graph(nodes, edges, accessible_evidence("A", "E_ALPHA") + accessible_evidence("B", "E_BETA"))
        allowed = frozenset(e.id for e in graph.edges)

        first = shortest_path(
            graph, allowed_edge_ids=allowed, source_node_id="S", target_node_id="T",
            weight_fn=lambda e: e.length_m,
        )
        second = shortest_path(
            graph, allowed_edge_ids=allowed, source_node_id="S", target_node_id="T",
            weight_fn=lambda e: e.length_m,
        )
        assert first.edge_ids == second.edge_ids
        assert first.edge_ids == ("E_ALPHA",)

    def test_tie_break_is_independent_of_construction_order(self):
        nodes = [node("S", 0.0, 0.0), node("T", 20.0, 0.0)]
        by_id = {n.id: n for n in nodes}
        edges = [edge("E_Z", "S", "T", by_id), edge("E_A", "S", "T", by_id)]
        records = accessible_evidence("Z", "E_Z") + accessible_evidence("A", "E_A")
        forward = make_graph(nodes, edges, records, version_id="v")
        backward = make_graph(nodes, list(reversed(edges)), records, version_id="v")
        allowed = frozenset(e.id for e in forward.edges)
        p1 = shortest_path(forward, allowed_edge_ids=allowed, source_node_id="S", target_node_id="T", weight_fn=lambda e: e.length_m)
        p2 = shortest_path(backward, allowed_edge_ids=allowed, source_node_id="S", target_node_id="T", weight_fn=lambda e: e.length_m)
        assert p1.edge_ids == p2.edge_ids == ("E_A",)

    def test_missing_origin_node_returns_no_path(self):
        graph = simple_line_graph()
        assert (
            shortest_path(
                graph, allowed_edge_ids=frozenset({"E12"}), source_node_id="GHOST",
                target_node_id="N2", weight_fn=lambda e: e.length_m,
            )
            is None
        )

    def test_zero_length_edge_is_allowed_but_zero_weight_on_a_real_segment_is_refused(self):
        nodes = [node("N1", 0.0, 0.0), node("N2", 10.0, 0.0)]
        by_id = {n.id: n for n in nodes}
        graph = make_graph(nodes, [edge("E12", "N1", "N2", by_id)])
        with pytest.raises(ValueError, match="zero routing weight"):
            shortest_path(
                graph, allowed_edge_ids=frozenset({"E12"}), source_node_id="N1",
                target_node_id="N2", weight_fn=lambda e: 0.0,
            )

    def test_negative_weight_is_refused(self):
        nodes = [node("N1", 0.0, 0.0), node("N2", 10.0, 0.0)]
        by_id = {n.id: n for n in nodes}
        graph = make_graph(nodes, [edge("E12", "N1", "N2", by_id)])
        with pytest.raises(ValueError, match="negative routing weight"):
            shortest_path(
                graph, allowed_edge_ids=frozenset({"E12"}), source_node_id="N1",
                target_node_id="N2", weight_fn=lambda e: -5.0,
            )

    def test_same_node_origin_and_destination_is_a_zero_length_route(self):
        graph = simple_line_graph()
        result = shortest_path(
            graph, allowed_edge_ids=frozenset(), source_node_id="N1", target_node_id="N1",
            weight_fn=lambda e: e.length_m,
        )
        assert result.edge_ids == ()
        assert result.distance_m == 0.0

    @settings(max_examples=50, deadline=None)
    @given(st.permutations(["E_A", "E_B", "E_C"]))
    def test_route_is_stable_under_edge_list_permutation(self, order):
        nodes = [node("S", 0.0, 0.0), node("T", 10.0, 0.0)]
        by_id = {n.id: n for n in nodes}
        edges = [edge(edge_id, "S", "T", by_id) for edge_id in order]
        graph = make_graph(nodes, edges, [], version_id="perm")
        allowed = frozenset(e.id for e in edges)
        result = shortest_path(
            graph, allowed_edge_ids=allowed, source_node_id="S", target_node_id="T",
            weight_fn=lambda e: e.length_m,
        )
        assert result.edge_ids == (min(order),)


class TestReachabilitySemantics:
    def _analysis(self, seed, rulepack, profile, phase_id="phase-1", scenario=None):
        return run_analysis(
            base_graph=seed.graph,
            scenario=scenario or build_scenario(seed=seed, rulepack=rulepack),
            phase_id=phase_id,
            profile_id=profile.id,
            rulepack=rulepack,
            profile=profile,
            as_of=AS_OF,
        )

    def test_b11_unknown_path_exists_without_a_confirmed_path(self, seed, rulepack, profile_a):
        result = self._analysis(seed, rulepack, profile_a)
        pair = next(
            od for od in result.od_results if od.origin_id == "OD-E" and od.destination_id == "OD-LIB"
        )
        assert pair.confirmed_reachable is False
        assert pair.possibly_reachable is True
        assert pair.confirmed_distance_m is None
        assert pair.confirmed_path_edge_ids == []
        assert pair.possible_path_edge_ids, "a hypothetical path must still be returned, labelled"
        assert "hypothetical" in pair.possible_distance_label.lower()
        assert ReasonCode.POSSIBLE_ROUTE_ONLY in pair.reason_codes

    def test_b12_no_route_at_all_in_either_graph(self, seed, rulepack, profile_b):
        result = self._analysis(seed, rulepack, profile_b)
        pair = next(
            od for od in result.od_results if od.origin_id == "OD-W" and od.destination_id == "OD-GATE"
        )
        assert pair.confirmed_reachable is False
        assert pair.possibly_reachable is False
        assert pair.confirmed_distance_m is None
        assert pair.possible_distance_m is None
        assert ReasonCode.NO_ROUTE in pair.reason_codes

    def test_b32_unreachable_routes_never_invent_a_distance(self, seed, rulepack, profile_b):
        result = self._analysis(seed, rulepack, profile_b)
        for pair in result.od_results:
            if not pair.confirmed_reachable:
                assert pair.confirmed_distance_m is None
            else:
                assert pair.confirmed_distance_m is not None and pair.confirmed_distance_m > 0
            if not pair.possibly_reachable:
                assert pair.possible_distance_m is None

    def test_reported_distance_is_physical_not_preference_weighted(self, seed, rulepack, profile_a):
        result = self._analysis(seed, rulepack, profile_a)
        pair = next(
            od for od in result.od_results if od.origin_id == "OD-W" and od.destination_id == "OD-GATE"
        )
        expected = sum(
            seed.graph.edge(edge_id).length_m for edge_id in pair.confirmed_path_edge_ids
        )
        assert pair.confirmed_distance_m == pytest.approx(expected, abs=1e-6)
        assert pair.confirmed_route_cost > pair.confirmed_distance_m  # preference applied
        assert "physical route length" in pair.route_note

    def test_blocking_findings_are_demonstrated_not_asserted(self, seed, rulepack, profile_b):
        result = self._analysis(seed, rulepack, profile_b)
        pair = next(
            od for od in result.od_results if od.origin_id == "OD-W" and od.destination_id == "OD-LIB"
        )
        assert pair.confirmed_reachable is False
        # Every reported blocker must correspond to a real finding in the result.
        known_findings: set[str] = set()
        for od in result.od_results:
            known_findings |= set(od.relevant_finding_ids)
        for finding in result.edge_evaluations:
            known_findings |= {f.id for f in finding.findings}
        assert set(pair.blocking_finding_ids) <= known_findings
        assert pair.blocking_finding_ids, "the narrow back-lane failure should be provable"
        assert pair.relevant_finding_ids

    def test_confirmed_pairs_are_always_a_subset_of_possible_pairs(self, seed, rulepack, profile_a, profile_b):
        for profile in (profile_a, profile_b):
            for pair in self._analysis(seed, rulepack, profile).od_results:
                if pair.confirmed_reachable:
                    assert pair.possibly_reachable is True

    def test_profile_b_reports_a_blocking_failure_where_profile_a_does_not(self, seed, rulepack, profile_a, profile_b):
        a_states = {e.edge_id: e.state for e in self._analysis(seed, rulepack, profile_a).edge_evaluations}
        b_states = {e.edge_id: e.state for e in self._analysis(seed, rulepack, profile_b).edge_evaluations}
        assert a_states["E_K1"] is VerdictState.PASS
        assert b_states["E_K1"] is VerdictState.FAIL