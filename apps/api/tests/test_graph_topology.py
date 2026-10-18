"""Graph topology invariants: B1, B2, B3, INV-02, plus negative cases."""

from __future__ import annotations

import pytest
from detour_lab.domain.contracts import BaseGraphVersion, Edge
from detour_lab.domain.enums import EdgeType
from detour_lab.graph.model import GraphValidationError, PedestrianGraph
from tests.conftest import (
    PLANAR_BASIS,
    SYNTHETIC_SOURCE,
    accessible_evidence,
    edge,
    evidence,
    make_graph,
    node,
)


def _version(nodes, edges, records=None) -> BaseGraphVersion:
    return BaseGraphVersion(
        id="g", basis=PLANAR_BASIS, nodes=nodes, edges=edges, evidence=records or [], source=SYNTHETIC_SOURCE
    )


class TestCrossingIsNotConnectivity:
    def test_b01_crossing_geometry_without_shared_node_is_not_connected(self):
        """Two edges that physically cross must remain disconnected without a node."""
        nodes = [
            node("NA", 0.0, 0.0),
            node("NB", 20.0, 0.0),
            node("NC", 10.0, -10.0),
            node("ND", 10.0, 10.0),
        ]
        by_id = {n.id: n for n in nodes}
        edges = [
            edge("E_HORIZONTAL", "NA", "NB", by_id),
            edge("E_VERTICAL", "NC", "ND", by_id),
        ]
        graph = make_graph(nodes, edges)

        assert graph.outgoing_edge_ids("NA") == ("E_HORIZONTAL",)
        assert graph.outgoing_edge_ids("NB") == ()
        assert graph.outgoing_edge_ids("NC") == ("E_VERTICAL",)

        crossings = [c for c in graph.unlinked_crossings() if not c["connected_via_shared_node"]]
        assert crossings, "the crossing should be detected as unlinked"
        assert {tuple(c["edge_ids"]) for c in crossings} == {("E_HORIZONTAL", "E_VERTICAL")}

        # Reachability must respect nodes only, never geometry.
        from detour_lab.graph.routing import shortest_path

        path = shortest_path(
            graph,
            allowed_edge_ids=frozenset(e.id for e in graph.edges),
            source_node_id="NA",
            target_node_id="NC",
            weight_fn=lambda e: e.length_m,
        )
        assert path is None

    def test_shared_node_at_same_point_is_connected(self):
        nodes = [
            node("NA", 0.0, 0.0),
            node("MID", 10.0, 0.0),
            node("NB", 20.0, 0.0),
            node("NC", 10.0, -10.0),
            node("ND", 10.0, 10.0),
        ]
        by_id = {n.id: n for n in nodes}
        edges = [
            edge("E_A", "NA", "MID", by_id),
            edge("E_B", "MID", "NB", by_id),
            edge("E_C", "NC", "MID", by_id),
            edge("E_D", "MID", "ND", by_id),
        ]
        graph = make_graph(nodes, edges)
        assert set(graph.outgoing_edge_ids("MID")) == {"E_B", "E_D"}
        unlinked = [c for c in graph.unlinked_crossings() if not c["connected_via_shared_node"]]
        assert unlinked == []


class TestDirection:
    def test_b02_directed_edge_allows_forward_only(self):
        nodes = [node("N1", 0.0, 0.0), node("N2", 10.0, 0.0)]
        by_id = {n.id: n for n in nodes}
        graph = make_graph(nodes, [edge("E12", "N1", "N2", by_id)])

        assert graph.outgoing_edge_ids("N1") == ("E12",)
        assert graph.outgoing_edge_ids("N2") == ()
        assert graph.incoming_edge_ids("N2") == ("E12",)

    def test_parallel_reverse_edges_keep_distinct_ids(self):
        nodes = [node("N1", 0.0, 0.0), node("N2", 10.0, 0.0)]
        by_id = {n.id: n for n in nodes}
        forward = edge("E_FORWARD", "N1", "N2", by_id)
        reverse = edge("E_REVERSE", "N2", "N1", by_id)
        graph = make_graph(nodes, [forward, reverse])

        assert graph.outgoing_edge_ids("N1") == ("E_FORWARD",)
        assert graph.outgoing_edge_ids("N2") == ("E_REVERSE",)

        multigraph = graph.to_networkx()
        assert multigraph.number_of_edges("N1", "N2") == 1
        assert multigraph.number_of_edges("N2", "N1") == 1
        assert sorted(multigraph["N1"]["N2"]) == ["E_FORWARD"]


class TestParallelEdges:
    def test_b03_parallel_edges_with_different_accessibility(self):
        """Two edges share endpoints but only one is usable; routing must use that one."""
        nodes = [node("N1", 0.0, 0.0), node("N2", 10.0, 0.0), node("N3", 20.0, 0.0)]
        by_id = {n.id: n for n in nodes}
        good = edge("E_GOOD", "N1", "N2", by_id)
        bad = Edge(
            id="E_BAD",
            u="N1",
            v="N2",
            geometry=[(0.0, 0.0), (10.0, 0.0)],
            length_m=10.0,
            edge_type=EdgeType.SIDEWALK,
        )
        records = [*accessible_evidence("GOOD", "E_GOOD"), evidence("BAD-width", "E_BAD", "width_mm", 500, unit="mm")]
        graph = make_graph(nodes, [good, bad, edge("E23", "N2", "N3", by_id)], records)

        from detour_lab.graph.routing import shortest_path

        path = shortest_path(
            graph,
            allowed_edge_ids=frozenset({"E_GOOD", "E23"}),
            source_node_id="N1",
            target_node_id="N3",
            weight_fn=lambda e: e.length_m,
        )
        assert path is not None
        assert path.edge_ids == ("E_GOOD", "E23")
        assert "E_BAD" not in path.edge_ids

    def test_multigraph_preserves_both_parallel_edges(self):
        nodes = [node("N1", 0.0, 0.0), node("N2", 10.0, 0.0)]
        by_id = {n.id: n for n in nodes}
        graph = make_graph(nodes, [edge("E_A", "N1", "N2", by_id), edge("E_B", "N1", "N2", by_id)])
        assert graph.to_networkx().number_of_edges("N1", "N2") == 2
        assert graph.outgoing_edge_ids("N1") == ("E_A", "E_B")


class TestValidationRejections:
    def test_duplicate_edge_id_rejected(self):
        nodes = [node("N1", 0.0, 0.0), node("N2", 10.0, 0.0)]
        by_id = {n.id: n for n in nodes}
        with pytest.raises(Exception) as excinfo:
            make_graph(nodes, [edge("E_DUP", "N1", "N2", by_id), edge("E_DUP", "N1", "N2", by_id)])
        assert "duplicate edge ID" in str(excinfo.value)

    def test_duplicate_node_id_rejected(self):
        with pytest.raises(Exception) as excinfo:
            make_graph([node("N1", 0.0, 0.0), node("N1", 1.0, 1.0)], [])
        assert "duplicate node ID" in str(excinfo.value)

    def test_unknown_endpoint_rejected_with_reason_code(self):
        nodes = [node("N1", 0.0, 0.0)]
        bad_edge = Edge(id="E_BAD", u="N1", v="MISSING", geometry=[(0.0, 0.0), (1.0, 1.0)], length_m=1.0)
        with pytest.raises(GraphValidationError) as excinfo:
            PedestrianGraph.from_version(_version(nodes, [bad_edge]))
        assert excinfo.value.code == "UNKNOWN_NODE_REFERENCE"

    def test_self_loop_rejected(self):
        nodes = [node("N1", 0.0, 0.0)]
        loop = Edge(id="E_LOOP", u="N1", v="N1", geometry=[(0.0, 0.0), (1.0, 0.0)], length_m=1.0)
        with pytest.raises(GraphValidationError) as excinfo:
            PedestrianGraph.from_version(_version(nodes, [loop]))
        assert excinfo.value.code == "SELF_LOOP"

    def test_geometry_endpoint_mismatch_rejected(self):
        nodes = [node("N1", 0.0, 0.0), node("N2", 10.0, 0.0)]
        bad = Edge(id="E_BAD", u="N1", v="N2", geometry=[(0.5, 0.0), (10.0, 0.0)], length_m=9.5)
        with pytest.raises(GraphValidationError) as excinfo:
            PedestrianGraph.from_version(_version(nodes, [bad]))
        assert excinfo.value.code == "GEOMETRY_ENDPOINT_MISMATCH"

    def test_closure_of_unknown_edge_rejected(self):
        nodes = [node("N1", 0.0, 0.0), node("N2", 10.0, 0.0)]
        by_id = {n.id: n for n in nodes}
        version = BaseGraphVersion(
            id="g",
            basis=PLANAR_BASIS,
            nodes=nodes,
            edges=[edge("E12", "N1", "N2", by_id)],
            inactive_edge_ids=["NOPE"],
            evidence=[],
            source=SYNTHETIC_SOURCE,
        )
        with pytest.raises(GraphValidationError):
            PedestrianGraph.from_version(version)

    def test_inactive_edges_are_part_of_the_version_and_its_hash(self):
        nodes = [node("N1", 0.0, 0.0), node("N2", 10.0, 0.0)]
        by_id = {n.id: n for n in nodes}
        open_version = BaseGraphVersion(
            id="g", basis=PLANAR_BASIS, nodes=nodes, edges=[edge("E12", "N1", "N2", by_id)],
            inactive_edge_ids=[], evidence=[], source=SYNTHETIC_SOURCE,
        )
        closed_version = BaseGraphVersion(
            id="g", basis=PLANAR_BASIS, nodes=nodes, edges=[edge("E12", "N1", "N2", by_id)],
            inactive_edge_ids=["E12"], evidence=[], source=SYNTHETIC_SOURCE,
        )
        assert open_version.content_hash != closed_version.content_hash
        assert PedestrianGraph.from_version(closed_version).closed_edge_ids == frozenset({"E12"})


class TestContentAddressing:
    def test_content_hash_is_stable_across_identical_construction(self):
        nodes = [node("N1", 0.0, 0.0), node("N2", 10.0, 0.0)]
        by_id = {n.id: n for n in nodes}
        first = make_graph(nodes, [edge("E12", "N1", "N2", by_id)], version_id="v1")
        second = make_graph(list(nodes), [edge("E12", "N1", "N2", by_id)], version_id="v1")
        assert first.content_hash == second.content_hash

    def test_different_content_produces_different_hash(self):
        nodes = [node("N1", 0.0, 0.0), node("N2", 10.0, 0.0)]
        by_id = {n.id: n for n in nodes}
        base = make_graph(nodes, [edge("E12", "N1", "N2", by_id)], version_id="v1")
        with_evidence = make_graph(
            nodes, [edge("E12", "N1", "N2", by_id)], accessible_evidence("X", "E12"), version_id="v1"
        )
        assert base.content_hash != with_evidence.content_hash

    def test_tampered_hash_is_rejected(self):
        nodes = [node("N1", 0.0, 0.0), node("N2", 10.0, 0.0)]
        by_id = {n.id: n for n in nodes}
        version = BaseGraphVersion(
            id="v1",
            basis=PLANAR_BASIS,
            nodes=nodes,
            edges=[edge("E12", "N1", "N2", by_id)],
            evidence=[],
            source=SYNTHETIC_SOURCE,
        )
        with pytest.raises(ValueError):
            BaseGraphVersion(
                id="v1",
                basis=PLANAR_BASIS,
                nodes=nodes,
                edges=[edge("E12", "N1", "N2", by_id)],
                evidence=accessible_evidence("X", "E12"),
                source=SYNTHETIC_SOURCE,
                content_hash=version.content_hash,
            )

    def test_b16_repeated_import_preserves_stable_semantics(self, seed):
        from detour_lab.ingestion.schema import load_local_planar_dataset
        from tests.conftest import SEED_PATH

        reimported = load_local_planar_dataset(SEED_PATH)
        assert reimported.graph.content_hash == seed.graph.content_hash
        assert [n.id for n in reimported.graph.nodes] == [n.id for n in seed.graph.nodes]


class TestDemoFixtureTopology:
    def test_seed_fixture_has_an_unlinked_crossing_for_the_invariant_demo(self, seed):
        unlinked = [c for c in seed.graph.unlinked_crossings() if not c["connected_via_shared_node"]]
        assert unlinked, "the seeded fixture must contain a crossing that is NOT a connection"
        assert any(
            set(c["edge_ids"]) == {"E_K2", "E_LINK"} for c in unlinked
        ), "E_LINK visually meets the main crossing but shares no node with it"

    def test_seed_edges_reference_existing_nodes(self, seed):
        node_ids = {n.id for n in seed.graph.nodes}
        for e in seed.graph.edges:
            assert e.u in node_ids
            assert e.v in node_ids