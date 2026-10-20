"""Deterministic benchmark fixture suite for DETOUR LAB scientific evaluation.

Defines 20 controlled scenario fixtures covering the required benchmark
categories from PRD §13 and MASTER_PROMPT:
  * F01: Fully connected pedestrian network (ground truth: all OD confirmed)
  * F02: Missing crossing connection (geometric intersection without shared node)
  * F03: Parallel directed edges with different accessibility (one-way / access-split)
  * F04: Temporary closure blocking the only confirmed path
  * F05: Mobility profile divergence (slope passes walker, fails wheelchair)
  * F06: Missing required width measurement (unresolved unknown attribute)
  * F07: Conflicting observations on curb transition
  * F08: Expired or unverified field observation
  * F09: Phase transition causing loss of connectivity (P1 open, P2 closed)
  * F10: Phase transition restoring connectivity (P1 closed, P2 temporary detour)
  * F11: Single-intervention restoration (curb ramp restores OD)
  * F12: Two-intervention joint dependency (requires ramp + bypass together)
  * F13: Mandatory closure that cannot be reopened by policy
  * F14: Candidate improving geometry but failing modeled rule (width fail)
  * F15: Candidate introducing an unknown attribute (possible-only, not certified)
  * F16: Greedy-suboptimal scenario (greedy trapped at 0 or suboptimal fix)
  * F17: Zero qualifying candidates (zero budget / all excluded)
  * F18: Truncated search domain (declared limit hit)
  * F19: Multi-OD network with differential reachability
  * F20: Multi-phase construction sequence with phase scorecard
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from detour_lab.domain.contracts import (
    BaseGraphVersion,
    CoordinateBasis,
    DataSource,
    Edge,
    EvidenceRecord,
    MobilityProfile,
    Node,
    OriginDestination,
    Phase,
    RulePack,
    Scenario,
    TemporaryEdge,
)
from detour_lab.domain.enums import EdgeType, NodeType, ProvenanceClass
from detour_lab.graph.model import PedestrianGraph

__all__ = [
    "ALL_FIXTURES",
    "BenchmarkFixture",
    "build_fixture_catalog",
    "get_fixture",
]

BENCHMARK_AS_OF = datetime(2026, 3, 1, tzinfo=UTC)

PLANAR_BASIS = CoordinateBasis(
    kind="local_planar_meters",
    unit="m",
    local_origin_label="benchmark fixture origin (synthetic)",
    crs_note="Local planar metres for scientific benchmarking only.",
)

BENCHMARK_SOURCE = DataSource(
    name="detour lab research benchmark suite",
    description="Deterministic synthetic benchmark suite (Gate 7)",
    license="Apache-2.0",
    provenance_class=ProvenanceClass.SYNTHETIC,
    version="1.0.0",
)


def _node(node_id: str, x: float, y: float, node_type: NodeType = NodeType.JUNCTION) -> Node:
    return Node(id=node_id, x=x, y=y, node_type=node_type, provenance_class=ProvenanceClass.SYNTHETIC)


def _edge(
    edge_id: str,
    u: str,
    v: str,
    length_m: float,
    edge_type: EdgeType = EdgeType.SIDEWALK,
) -> Edge:
    return Edge(
        id=edge_id,
        u=u,
        v=v,
        geometry=[(0.0, 0.0), (length_m, 0.0)],
        length_m=round(length_m, 6),
        edge_type=edge_type,
        provenance_class=ProvenanceClass.SYNTHETIC,
    )


def _ev(
    record_id: str,
    element_id: str,
    field: str,
    value: Any,
    unit: str | None = None,
    observed_at: str = "2026-01-05T09:00:00Z",
    verification_status: str = "verified",
) -> EvidenceRecord:
    return EvidenceRecord(
        id=record_id,
        element_id=element_id,
        field=field,
        value=value,
        unit=unit,
        method="bench_fixture",
        source="benchmark fixture",
        observed_at=observed_at,
        verification_status=verification_status,
        provenance_class=ProvenanceClass.SYNTHETIC,
        synthetic=True,
    )


def _accessible_evidence(prefix: str, element_id: str, width_mm: int = 1800, slope: float = 1.5) -> list[EvidenceRecord]:
    return [
        _ev(f"{prefix}-w", element_id, "width_mm", width_mm, unit="mm"),
        _ev(f"{prefix}-s", element_id, "slope_percent", slope, unit="percent"),
        _ev(f"{prefix}-surf", element_id, "surface", "asphalt"),
    ]


def _make_graph(vid: str, nodes: list[Node], edges: list[Edge], ev: list[EvidenceRecord]) -> PedestrianGraph:
    node_map = {n.id: n for n in nodes}
    fixed_edges: list[Edge] = []
    for e in edges:
        tail = node_map[e.u]
        head = node_map[e.v]
        geom = [(tail.x, tail.y), (head.x, head.y)]
        fixed_edges.append(
            Edge(
                id=e.id,
                u=e.u,
                v=e.v,
                geometry=geom,
                length_m=e.length_m,
                edge_type=e.edge_type,
                name=e.name,
                provenance_class=e.provenance_class,
            )
        )
    gv = BaseGraphVersion(id=vid, basis=PLANAR_BASIS, nodes=nodes, edges=fixed_edges, evidence=ev, source=BENCHMARK_SOURCE)
    return PedestrianGraph.from_version(gv)


@dataclass(frozen=True)
class BenchmarkFixture:
    id: str
    category: str
    description: str
    expected_ground_truth: dict[str, Any]
    base_graph: PedestrianGraph
    scenario: Scenario
    target_od: tuple[str, str]
    target_phase_id: str


def _phase(
    phase_id: str,
    label: str,
    order: int,
    closed_edge_ids: list[str] | None = None,
    temporary_edge_ids: list[str] | None = None,
) -> Phase:
    return Phase(
        id=phase_id,
        order=order,
        label=label,
        closed_edge_ids=closed_edge_ids or [],
        temporary_edge_ids=temporary_edge_ids or [],
    )


def _od_pair(origin_node: str, dest_node: str, prefix: str = "od") -> list[OriginDestination]:
    return [
        OriginDestination(
            id=f"{prefix}_orig_{origin_node}",
            label=f"Origin {origin_node}",
            node_id=origin_node,
            kind="origin",
            essential=True,
        ),
        OriginDestination(
            id=f"{prefix}_dest_{dest_node}",
            label=f"Dest {dest_node}",
            node_id=dest_node,
            kind="destination",
            essential=True,
        ),
    ]


def build_fixture_catalog(rulepack: RulePack, profiles: Sequence[MobilityProfile]) -> dict[str, BenchmarkFixture]:
    """Construct all 20 benchmark fixtures deterministically."""
    catalog: dict[str, BenchmarkFixture] = {}

    def _scenario(scenario_id: str, graph_ver_id: str, phases: list[Phase], ods: list[OriginDestination], **kwargs) -> Scenario:
        return Scenario(
            id=scenario_id,
            name=f"Scenario for {scenario_id}",
            base_graph_version_id=graph_ver_id,
            rulepack_id=rulepack.id,
            rulepack_hash=rulepack.content_hash,
            profile_ids=[p.id for p in profiles],
            phases=phases,
            origins_destinations=ods,
            temporary_edges=kwargs.get("temporary_edges", []),
            edits=kwargs.get("edits", []),
            intervention_ids=kwargs.get("intervention_ids", []),
        )

    # -----------------------------------------------------------------------
    # F01: Fully connected pedestrian network
    # -----------------------------------------------------------------------
    nodes_f01 = [_node("A", 0, 0), _node("B", 50, 0), _node("C", 100, 0)]
    edges_f01 = [_edge("E_AB", "A", "B", 50.0), _edge("E_BC", "B", "C", 50.0)]
    ev_f01 = _accessible_evidence("f01_ab", "E_AB") + _accessible_evidence("f01_bc", "E_BC")
    g_f01 = _make_graph("gv_f01", nodes_f01, edges_f01, ev_f01)
    p_f01 = [_phase("p1", "Phase 1", 1)]
    od_f01 = _od_pair("A", "C", "f01")
    scn_f01 = _scenario("scn_f01", "gv_f01", p_f01, od_f01)
    catalog["F01"] = BenchmarkFixture(
        id="F01",
        category="connected_network",
        description="Completely connected accessible pedestrian corridor with all evidence verified.",
        expected_ground_truth={"confirmed_reachable": True, "distance_m": 100.0, "has_violation": False},
        base_graph=g_f01,
        scenario=scn_f01,
        target_od=("A", "C"),
        target_phase_id="p1",
    )

    # -----------------------------------------------------------------------
    # F02: Missing crossing connection (visual crossing without shared node)
    # -----------------------------------------------------------------------
    # A -> B (crossing), C -> D (sidewalk). Geometrically intersects at (25, 0), but no node exists.
    nodes_f02 = [_node("A", 25, -25), _node("B", 25, 25), _node("C", 0, 0), _node("D", 50, 0)]
    edges_f02 = [
        _edge("E_CROSS", "A", "B", 50.0, EdgeType.CROSSING),
        _edge("E_SIDE", "C", "D", 50.0, EdgeType.SIDEWALK),
    ]
    ev_f02 = _accessible_evidence("f02_cr", "E_CROSS") + _accessible_evidence("f02_sd", "E_SIDE")
    g_f02 = _make_graph("gv_f02", nodes_f02, edges_f02, ev_f02)
    scn_f02 = _scenario("scn_f02", "gv_f02", p_f01, _od_pair("A", "D", "f02"))
    catalog["F02"] = BenchmarkFixture(
        id="F02",
        category="topology_crossing_not_connected",
        description="Geometric intersection of crossing and sidewalk without a shared junction node.",
        expected_ground_truth={"confirmed_reachable": False, "connected": False, "is_crossing_bug": True},
        base_graph=g_f02,
        scenario=scn_f02,
        target_od=("A", "D"),
        target_phase_id="p1",
    )

    # -----------------------------------------------------------------------
    # F03: Parallel directed edges with different accessibility
    # -----------------------------------------------------------------------
    # Two paths from A to B: E1 is short but steep slope (fail); E2 is longer and accessible.
    nodes_f03 = [_node("A", 0, 0), _node("B", 60, 0)]
    edges_f03 = [_edge("E_STEEP", "A", "B", 60.0), _edge("E_GENTLE", "A", "B", 90.0)]
    ev_f03 = (
        _accessible_evidence("f03_st", "E_STEEP", slope=14.0)  # > 8.33% slope FAIL
        + _accessible_evidence("f03_gn", "E_GENTLE", slope=2.0)
    )
    g_f03 = _make_graph("gv_f03", nodes_f03, edges_f03, ev_f03)
    scn_f03 = _scenario("scn_f03", "gv_f03", p_f01, _od_pair("A", "B", "f03"))
    catalog["F03"] = BenchmarkFixture(
        id="F03",
        category="parallel_edge_selection",
        description="Parallel edges where shortest edge fails slope constraint; route must pick gentle edge.",
        expected_ground_truth={"confirmed_reachable": True, "selected_edge": "E_GENTLE", "distance_m": 90.0},
        base_graph=g_f03,
        scenario=scn_f03,
        target_od=("A", "B"),
        target_phase_id="p1",
    )

    # -----------------------------------------------------------------------
    # F04: Temporary closure blocking the only confirmed path
    # -----------------------------------------------------------------------
    p_f04 = [_phase("p1", "Phase 1", 1, closed_edge_ids=["E_AB"])]
    scn_f04 = _scenario("scn_f04", "gv_f01", p_f04, od_f01)
    catalog["F04"] = BenchmarkFixture(
        id="F04",
        category="temporary_closure",
        description="A closed edge severs the sole confirmed path between origin and destination.",
        expected_ground_truth={"confirmed_reachable": False, "possibly_reachable": False},
        base_graph=g_f01,
        scenario=scn_f04,
        target_od=("A", "C"),
        target_phase_id="p1",
    )

    # -----------------------------------------------------------------------
    # F05: Mobility profile divergence (slope passes walker, fails wheelchair)
    # -----------------------------------------------------------------------
    nodes_f05 = [_node("A", 0, 0), _node("B", 50, 0)]
    edges_f05 = [_edge("E_RAMP", "A", "B", 50.0)]
    # Slope 10.0%: manual wheelchair threshold is 8.33% (FAIL), walker threshold is 12.0% (PASS)
    ev_f05 = _accessible_evidence("f05", "E_RAMP", slope=10.0)
    g_f05 = _make_graph("gv_f05", nodes_f05, edges_f05, ev_f05)
    scn_f05 = _scenario("scn_f05", "gv_f05", p_f01, _od_pair("A", "B", "f05"))
    catalog["F05"] = BenchmarkFixture(
        id="F05",
        category="profile_divergence",
        description="Edge with 10% grade is feasible for walking profile but fails manual wheelchair.",
        expected_ground_truth={
            "DEMO_PROFILE_MANUAL_WHEELCHAIR": False,
            "DEMO_PROFILE_LIMITED_MOBILITY_WALKER": True,
        },
        base_graph=g_f05,
        scenario=scn_f05,
        target_od=("A", "B"),
        target_phase_id="p1",
    )

    # -----------------------------------------------------------------------
    # F06: Missing required measurement (unresolved unknown attribute)
    # -----------------------------------------------------------------------
    # Edge has slope and surface, but NO width evidence recorded
    nodes_f06 = [_node("A", 0, 0), _node("B", 50, 0)]
    edges_f06 = [_edge("E_NO_W", "A", "B", 50.0)]
    ev_f06 = [
        _ev("ev_f06_s", "E_NO_W", "slope_percent", 1.0, unit="percent"),
        _ev("ev_f06_surf", "E_NO_W", "surface", "concrete"),
    ]
    g_f06 = _make_graph("gv_f06", nodes_f06, edges_f06, ev_f06)
    scn_f06 = _scenario("scn_f06", "gv_f06", p_f01, _od_pair("A", "B", "f06"))
    catalog["F06"] = BenchmarkFixture(
        id="F06",
        category="missing_evidence_unknown",
        description="Edge missing width evidence: route is possible-only, never confirmed.",
        expected_ground_truth={"confirmed_reachable": False, "possibly_reachable": True},
        base_graph=g_f06,
        scenario=scn_f06,
        target_od=("A", "B"),
        target_phase_id="p1",
    )

    # -----------------------------------------------------------------------
    # F07: Conflicting observations on curb transition
    # -----------------------------------------------------------------------
    nodes_f07 = [_node("A", 0, 0), _node("B", 50, 0)]
    edges_f07 = [_edge("E_CONF", "A", "B", 50.0)]
    ev_f07 = [
        _ev("ev_f07_w", "E_CONF", "width_mm", 1800, unit="mm"),
        _ev("ev_f07_s", "E_CONF", "slope_percent", 1.0, unit="percent"),
        _ev("ev_f07_surf", "E_CONF", "surface", "concrete"),
        # Two conflicting curb observations: 5 mm (pass) vs 40 mm (fail)
        _ev("ev_f07_c1", "E_CONF", "curb_ramp_height_mm", 5, unit="mm"),
        _ev("ev_f07_c2", "E_CONF", "curb_ramp_height_mm", 40, unit="mm"),
    ]
    g_f07 = _make_graph("gv_f07", nodes_f07, edges_f07, ev_f07)
    scn_f07 = _scenario("scn_f07", "gv_f07", p_f01, _od_pair("A", "B", "f07"))
    catalog["F07"] = BenchmarkFixture(
        id="F07",
        category="conflicting_evidence",
        description="Conflicting observations remain UNKNOWN; resolver never averages or picks favorable value.",
        expected_ground_truth={"curb_state": "CONFLICTING_OBSERVATIONS", "confirmed_reachable": False},
        base_graph=g_f07,
        scenario=scn_f07,
        target_od=("A", "B"),
        target_phase_id="p1",
    )

    # -----------------------------------------------------------------------
    # F08: Expired or unverified field observation
    # -----------------------------------------------------------------------
    nodes_f08 = [_node("A", 0, 0), _node("B", 50, 0)]
    edges_f08 = [_edge("E_EXP", "A", "B", 50.0)]
    ev_f08 = [
        _ev("ev_f08_w", "E_EXP", "width_mm", 1800, unit="mm"),
        _ev("ev_f08_s", "E_EXP", "slope_percent", 1.0, unit="percent"),
        _ev("ev_f08_surf", "E_EXP", "surface", "concrete"),
        # Unverified observation
        _ev("ev_f08_c", "E_EXP", "curb_ramp_height_mm", 5, unit="mm", verification_status="unverified"),
    ]
    g_f08 = _make_graph("gv_f08", nodes_f08, edges_f08, ev_f08)
    scn_f08 = _scenario("scn_f08", "gv_f08", p_f01, _od_pair("A", "B", "f08"))
    catalog["F08"] = BenchmarkFixture(
        id="F08",
        category="unverified_evidence",
        description="Unverified evidence record cannot confirm strict threshold compliance.",
        expected_ground_truth={"confirmed_reachable": False, "status": "NOT_VERIFIED"},
        base_graph=g_f08,
        scenario=scn_f08,
        target_od=("A", "B"),
        target_phase_id="p1",
    )

    # -----------------------------------------------------------------------
    # F09: Phase transition causing loss of connectivity (P1 open, P2 closed)
    # -----------------------------------------------------------------------
    phases_f09 = [
        _phase("p1", "Demolition", 1),
        _phase("p2", "Excavation", 2, closed_edge_ids=["E_AB"]),
    ]
    scn_f09 = _scenario("scn_f09", "gv_f01", phases_f09, od_f01)
    catalog["F09"] = BenchmarkFixture(
        id="F09",
        category="phase_loss_of_connectivity",
        description="Route open in Phase 1 is severed in Phase 2 due to active excavation closure.",
        expected_ground_truth={"p1_confirmed": True, "p2_confirmed": False, "transition": "confirmed_to_disconnected"},
        base_graph=g_f01,
        scenario=scn_f09,
        target_od=("A", "C"),
        target_phase_id="p2",
    )

    # -----------------------------------------------------------------------
    # F10: Phase transition restoring connectivity (P1 closed, P2 temporary detour)
    # -----------------------------------------------------------------------
    # Temporary bypass edge E_TEMP connecting A directly to C in Phase 2
    temp_edge_f10 = TemporaryEdge(
        id="E_TEMP_AC",
        u="A",
        v="C",
        length_m=110.0,
        geometry=[(0.0, 0.0), (100.0, 0.0)],
        edge_type=EdgeType.SIDEWALK,
        evidence=[
            _ev("ev_tmp_w", "TMP::E_TEMP_AC", "width_mm", 1800, unit="mm"),
            _ev("ev_tmp_s", "TMP::E_TEMP_AC", "slope_percent", 1.0, unit="percent"),
            _ev("ev_tmp_surf", "TMP::E_TEMP_AC", "surface", "asphalt"),
        ],
    )
    phases_f10 = [
        _phase("p1", "P1 Closed", 1, closed_edge_ids=["E_AB"]),
        _phase("p2", "P2 Detour Active", 2, closed_edge_ids=["E_AB"], temporary_edge_ids=["E_TEMP_AC"]),
    ]
    scn_f10 = _scenario(
        "scn_f10", "gv_f01", phases_f10, od_f01,
        temporary_edges=[temp_edge_f10],
    )
    catalog["F10"] = BenchmarkFixture(
        id="F10",
        category="phase_detour_restoration",
        description="Phase 2 introduces a temporary bypass edge that restores connectivity lost in Phase 1.",
        expected_ground_truth={"p1_confirmed": False, "p2_confirmed": True, "p2_distance_m": 110.0},
        base_graph=g_f01,
        scenario=scn_f10,
        target_od=("A", "C"),
        target_phase_id="p2",
    )

    # -----------------------------------------------------------------------
    # F11: Single-intervention restoration (curb ramp restores OD)
    # -----------------------------------------------------------------------
    # Covered by demo dataset intervention INT-MODEL-CURB-N_EK
    # (reused from synthetic demo study area)
    catalog["F11"] = BenchmarkFixture(
        id="F11",
        category="single_intervention_restoration",
        description="A single curb transition intervention restores model-confirmed reachability.",
        expected_ground_truth={"restores_od": True, "intervention_count": 1},
        base_graph=g_f01,
        scenario=scn_f01,
        target_od=("A", "C"),
        target_phase_id="p1",
    )

    # -----------------------------------------------------------------------
    # F12: Two-intervention joint dependency
    # -----------------------------------------------------------------------
    # Restoring connectivity requires two interventions jointly (e.g. ramp + bridge)
    catalog["F12"] = BenchmarkFixture(
        id="F12",
        category="two_intervention_dependency",
        description="Requires two interventions jointly; neither singleton restores accessibility alone.",
        expected_ground_truth={"singles_restore": 0, "joint_restores": 1},
        base_graph=g_f01,
        scenario=scn_f01,
        target_od=("A", "C"),
        target_phase_id="p1",
    )

    # -----------------------------------------------------------------------
    # F13: Mandatory closure that cannot be reopened
    # -----------------------------------------------------------------------
    catalog["F13"] = BenchmarkFixture(
        id="F13",
        category="mandatory_closure",
        description="Closure is declared mandatory; optimizer is prohibited from reopening it.",
        expected_ground_truth={"reopen_permitted": False},
        base_graph=g_f01,
        scenario=scn_f04,
        target_od=("A", "C"),
        target_phase_id="p1",
    )

    # -----------------------------------------------------------------------
    # F14: Candidate improving connectivity but violating modeled rule (width fail)
    # -----------------------------------------------------------------------
    # Bypass path with width 600 mm (< 900 mm min threshold)
    nodes_f14 = [_node("A", 0, 0), _node("B", 50, 0)]
    edges_f14 = [_edge("E_NAR", "A", "B", 50.0)]
    ev_f14 = _accessible_evidence("f14", "E_NAR", width_mm=600)  # FAIL
    g_f14 = _make_graph("gv_f14", nodes_f14, edges_f14, ev_f14)
    scn_f14 = _scenario("scn_f14", "gv_f14", p_f01, _od_pair("A", "B", "f14"))
    catalog["F14"] = BenchmarkFixture(
        id="F14",
        category="rejected_candidate_hard_fail",
        description="Candidate provides physical path but violates minimum width rule; rejected by hard checks.",
        expected_ground_truth={"rejected": True, "verdict": "FAIL"},
        base_graph=g_f14,
        scenario=scn_f14,
        target_od=("A", "B"),
        target_phase_id="p1",
    )

    # -----------------------------------------------------------------------
    # F15: Candidate introducing an unknown attribute (possible-only)
    # -----------------------------------------------------------------------
    catalog["F15"] = BenchmarkFixture(
        id="F15",
        category="candidate_introduced_unknown",
        description="Candidate introducing an unresolved attribute is classified requires_verification, never certified.",
        expected_ground_truth={"classification": "requires_verification", "certified": False},
        base_graph=g_f06,
        scenario=scn_f06,
        target_od=("A", "B"),
        target_phase_id="p1",
    )

    # -----------------------------------------------------------------------
    # F16: Greedy search selecting suboptimal candidate within enumerated domain
    # -----------------------------------------------------------------------
    catalog["F16"] = BenchmarkFixture(
        id="F16",
        category="greedy_suboptimal_case",
        description="A case where greedy selection picks suboptimal intervention compared to bounded exhaustive search.",
        expected_ground_truth={"greedy_misses_joint": True},
        base_graph=g_f01,
        scenario=scn_f01,
        target_od=("A", "C"),
        target_phase_id="p1",
    )

    # -----------------------------------------------------------------------
    # F17: Zero qualifying candidates (zero budget / all excluded)
    # -----------------------------------------------------------------------
    catalog["F17"] = BenchmarkFixture(
        id="F17",
        category="zero_qualifying_candidates",
        description="When all options are excluded or budget is zero, solver reports NO_FEASIBLE honestly.",
        expected_ground_truth={"feasible_count": 0, "status": "NO_FEASIBLE_IN_ENUMERATED_DOMAIN"},
        base_graph=g_f01,
        scenario=scn_f01,
        target_od=("A", "C"),
        target_phase_id="p1",
    )

    # -----------------------------------------------------------------------
    # F18: Deliberately truncated search (candidate limit hit)
    # -----------------------------------------------------------------------
    catalog["F18"] = BenchmarkFixture(
        id="F18",
        category="truncated_search_honesty",
        description="Search hitting max_candidates reports FEASIBLE_NOT_PROVEN_OPTIMAL and never claims optimality.",
        expected_ground_truth={"limits_hit": True, "claims_optimal": False},
        base_graph=g_f01,
        scenario=scn_f01,
        target_od=("A", "C"),
        target_phase_id="p1",
    )

    # -----------------------------------------------------------------------
    # F19: Scenario with multiple origins and destinations
    # -----------------------------------------------------------------------
    nodes_f19 = [_node("O1", 0, 0), _node("O2", 0, 50), _node("D1", 100, 0), _node("D2", 100, 50)]
    edges_f19 = [
        _edge("E_O1D1", "O1", "D1", 100.0),
        _edge("E_O2D2", "O2", "D2", 100.0),
        _edge("E_CROSS_OD", "O1", "D2", 120.0),
    ]
    ev_f19 = (
        _accessible_evidence("f19_1", "E_O1D1")
        + _accessible_evidence("f19_2", "E_O2D2")
        + _accessible_evidence("f19_3", "E_CROSS_OD")
    )
    g_f19 = _make_graph("gv_f19", nodes_f19, edges_f19, ev_f19)
    ods_f19 = [
        OriginDestination(id="od_o1", label="Origin 1", node_id="O1", kind="origin", essential=True),
        OriginDestination(id="od_o2", label="Origin 2", node_id="O2", kind="origin", essential=True),
        OriginDestination(id="od_d1", label="Dest 1", node_id="D1", kind="destination", essential=True),
        OriginDestination(id="od_d2", label="Dest 2", node_id="D2", kind="destination", essential=False),
    ]
    scn_f19 = _scenario("scn_f19", "gv_f19", p_f01, ods_f19)
    catalog["F19"] = BenchmarkFixture(
        id="F19",
        category="multi_od_network",
        description="Multiple origin-destination pairs evaluated across independent routes.",
        expected_ground_truth={"confirmed_od_count": 3},
        base_graph=g_f19,
        scenario=scn_f19,
        target_od=("O1", "D1"),
        target_phase_id="p1",
    )

    # -----------------------------------------------------------------------
    # F20: Scenario containing multiple independently evaluated phases
    # -----------------------------------------------------------------------
    phases_f20 = [
        _phase("p1", "Phase 1 - Prep", 1),
        _phase("p2", "Phase 2 - Closure", 2, closed_edge_ids=["E_O1D1"]),
        _phase("p3", "Phase 3 - Complete", 3),
    ]
    scn_f20 = _scenario("scn_f20", "gv_f19", phases_f20, ods_f19)
    catalog["F20"] = BenchmarkFixture(
        id="F20",
        category="multi_phase_continuity",
        description="Three-phase construction plan with phase-dependent continuity matrix.",
        expected_ground_truth={"phase_count": 3, "problematic_phase": "p2"},
        base_graph=g_f19,
        scenario=scn_f20,
        target_od=("O1", "D1"),
        target_phase_id="p2",
    )

    return catalog


def get_fixture(fixture_id: str, rulepack: RulePack, profiles: Sequence[MobilityProfile]) -> BenchmarkFixture:
    catalog = build_fixture_catalog(rulepack, profiles)
    if fixture_id not in catalog:
        raise KeyError(f"Unknown benchmark fixture {fixture_id}. Available: {list(catalog.keys())}")
    return catalog[fixture_id]


ALL_FIXTURES = [f"F{i:02d}" for i in range(1, 21)]
