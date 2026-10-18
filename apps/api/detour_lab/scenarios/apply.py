"""Scenario application: typed edits and immutable phase graphs.

``build_phase_graph`` is a **pure transform**:

    build_phase_graph(base_version, scenario_revision, phase) -> phase_graph

The baseline graph version is never mutated (PRD FR-005, INV-07). Every edit is
audited through its declared operation, preconditions are validated, and the
resulting graph is a new content-addressed version.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from detour_lab.domain.contracts import (
    BaseGraphVersion,
    Edge,
    EvidenceRecord,
    GraphEdit,
    Node,
    Phase,
    Scenario,
    TemporaryEdge,
)
from detour_lab.domain.enums import EdgeType, NodeType, ProvenanceClass
from detour_lab.graph.model import PedestrianGraph

__all__ = [
    "GraphEditError",
    "PhaseGraph",
    "apply_edits",
    "build_phase_graph",
    "cumulative_lengths",
    "order_edits",
]


class GraphEditError(ValueError):
    """An edit violated its precondition; carries a stable machine reason code."""

    def __init__(self, message: str, *, code: str, edit: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.edit = edit


@dataclass(slots=True)
class _Working:
    """Mutable scratch state used only while applying a scenario's edits."""

    nodes: dict[str, Node] = field(default_factory=dict)
    edges: dict[str, Edge] = field(default_factory=dict)
    evidence: dict[str, EvidenceRecord] = field(default_factory=dict)
    #: Deterministic counter per (element, field) so replayed edits get stable IDs.
    evidence_seq: dict[tuple[str, str], int] = field(default_factory=dict)

    def add_evidence(self, record: EvidenceRecord) -> None:
        if record.id in self.evidence:
            raise GraphEditError(
                f"evidence record {record.id!r} already exists",
                code="DUPLICATE_ID",
            )
        self.evidence[record.id] = record

    def next_evidence_id(self, element_id: str, field_name: str) -> str:
        key = (element_id, field_name)
        seq = self.evidence_seq.get(key, 0) + 1
        self.evidence_seq[key] = seq
        return f"{element_id}::{field_name}::{seq}"


def cumulative_lengths(geometry: list[tuple[float, float]]) -> list[float]:
    totals = [0.0]
    for start, end in itertools.pairwise(geometry):
        totals.append(totals[-1] + math.dist(start, end))
    return totals


def _interpolate(geometry: list[tuple[float, float]], distance_m: float) -> tuple[float, float]:
    totals = cumulative_lengths(geometry)
    total = totals[-1]
    if total <= 0:
        return geometry[0]
    target = min(max(distance_m, 0.0), total)
    for index in range(len(totals) - 1):
        if target <= totals[index + 1] or index == len(totals) - 2:
            span = totals[index + 1] - totals[index]
            ratio = 0.0 if span == 0 else (target - totals[index]) / span
            (x1, y1), (x2, y2) = geometry[index], geometry[index + 1]
            return (x1 + ratio * (x2 - x1), y1 + ratio * (y2 - y1))
    return geometry[-1]  # pragma: no cover


def _rebind_evidence(
    working: _Working, old_element_id: str, new_element_ids: list[str], note: str
) -> None:
    """Re-attribute a split segment's evidence to each part as *derived* records.

    Derived (not silently copied) because no independent measurement exists for
    the parts; the reviewer can see exactly where each number came from.
    """
    for record in list(working.evidence.values()):
        if record.element_id != old_element_id:
            continue
        for new_id in new_element_ids:
            new_record = record.model_copy(
                update={
                    "id": working.next_evidence_id(new_id, record.field),
                    "element_id": new_id,
                    "provenance_class": ProvenanceClass.DERIVED,
                    "synthetic": record.synthetic,
                    "note": f"{note} Inherited from {old_element_id} record {record.id}; no independent "
                    f"measurement of this segment exists.",
                }
            )
            working.add_evidence(new_record)


def _closest_point_on_edge(edge: Edge, point: tuple[float, float], tolerance: float = 1e-6) -> tuple[float, float] | None:
    """Return the point of ``edge`` that coincides with ``point``, or ``None``.

    Used by ``link_crossing`` to prove that an existing node really lies on the
    edge before creating a connection between them.
    """
    for index in range(len(edge.geometry) - 1):
        start, end = edge.geometry[index], edge.geometry[index + 1]
        span = math.dist(start, end)
        if span == 0:
            continue
        ratio = ((point[0] - start[0]) * (end[0] - start[0]) + (point[1] - start[1]) * (end[1] - start[1])) / (span**2)
        ratio = min(max(ratio, 0.0), 1.0)
        candidate = (start[0] + ratio * (end[0] - start[0]), start[1] + ratio * (end[1] - start[1]))
        if math.dist(candidate, point) <= tolerance:
            return candidate
    return None


def _split_edge(
    working: _Working, edge: Edge, split_node: Node, new_ids: tuple[str, str]
) -> tuple[Edge, Edge]:
    """Split ``edge`` at ``split_node`` preserving direction and provenance."""
    point = (split_node.x, split_node.y)
    total = cumulative_lengths(edge.geometry)[-1]
    offset = math.dist(edge.geometry[0], point)
    index = _index_of(edge.geometry, point, offset, total)
    head_points = [*edge.geometry[: index + 1], point]
    tail_points = [point, *edge.geometry[index + 1 :]]
    first = Edge(
        id=new_ids[0],
        u=edge.u,
        v=split_node.id,
        geometry=head_points,
        length_m=round(offset, 6),
        edge_type=edge.edge_type,
        name=edge.name,
        provenance_class=edge.provenance_class,
    )
    second = Edge(
        id=new_ids[1],
        u=split_node.id,
        v=edge.v,
        geometry=tail_points,
        length_m=round(max(total - offset, 0.0), 6),
        edge_type=edge.edge_type,
        name=edge.name,
        provenance_class=edge.provenance_class,
    )
    return first, second


def _index_of(
    geometry: list[tuple[float, float]], point: tuple[float, float], offset: float, total: float
) -> int:
    """Index of the geometry vertex at/just before ``point``."""
    running = 0.0
    for index in range(len(geometry) - 1):
        span = math.dist(geometry[index], geometry[index + 1])
        if running + span >= offset - 1e-9:
            return index
        running += span
    return max(len(geometry) - 2, 0)


def _apply_one(working: _Working, edit: GraphEdit) -> None:
    op = edit.op
    params: dict[str, Any] = edit.params

    if op == "add_node":
        node_id = str(params["id"])
        if node_id in working.nodes:
            raise GraphEditError(f"node {node_id!r} already exists", code="DUPLICATE_ID", edit=edit.key())
        working.nodes[node_id] = Node(
            id=node_id,
            x=float(params["x"]),
            y=float(params["y"]),
            node_type=NodeType(params.get("node_type", NodeType.JUNCTION.value)),
            name=str(params.get("name", "")),
            provenance_class=ProvenanceClass(params.get("provenance_class", ProvenanceClass.SYNTHETIC.value)),
        )
        return

    if op == "add_edge":
        edge_id = str(params["id"])
        if edge_id in working.edges:
            raise GraphEditError(f"edge {edge_id!r} already exists", code="DUPLICATE_ID", edit=edit.key())
        u, v = str(params["u"]), str(params["v"])
        if u == v:
            raise GraphEditError("self-loops are not supported", code="SELF_LOOP", edit=edit.key())
        for endpoint in (u, v):
            if endpoint not in working.nodes:
                raise GraphEditError(
                    f"unknown endpoint node {endpoint!r}", code="UNKNOWN_NODE_REFERENCE", edit=edit.key()
                )
        geometry = [tuple(p) for p in params["geometry"]] if params.get("geometry") else [
            (working.nodes[u].x, working.nodes[u].y),
            (working.nodes[v].x, working.nodes[v].y),
        ]
        length = float(params["length_m"]) if params.get("length_m") is not None else round(
            math.dist(geometry[0], geometry[-1]), 6
        )
        working.edges[edge_id] = Edge(
            id=edge_id,
            u=u,
            v=v,
            geometry=geometry,
            length_m=length,
            edge_type=EdgeType(params.get("edge_type", EdgeType.TEMPORARY_PATH.value)),
            name=str(params.get("name", "")),
            provenance_class=ProvenanceClass(params.get("provenance_class", ProvenanceClass.SYNTHETIC.value)),
        )
        return

    if op == "remove_edge":
        edge_id = edit.target_id
        if edge_id not in working.edges:
            raise GraphEditError(f"edge {edge_id!r} does not exist", code="UNKNOWN_NODE_REFERENCE", edit=edit.key())
        del working.edges[edge_id]
        return

    if op == "set_direction":
        edge_id = edit.target_id
        edge = working.edges.get(edge_id)
        if edge is None:
            raise GraphEditError(f"edge {edge_id!r} does not exist", code="UNKNOWN_NODE_REFERENCE", edit=edit.key())
        new_u, new_v = str(params["new_u"]), str(params["new_v"])
        for endpoint in (new_u, new_v):
            if endpoint not in working.nodes:
                raise GraphEditError(
                    f"unknown endpoint node {endpoint!r}", code="UNKNOWN_NODE_REFERENCE", edit=edit.key()
                )
        if new_u == new_v:
            raise GraphEditError("self-loops are not supported", code="SELF_LOOP", edit=edit.key())
        working.edges[edge_id] = edge.model_copy(
            update={
                "u": new_u,
                "v": new_v,
                "geometry": list(reversed(edge.geometry)),
                "length_m": edge.length_m,
            }
        )
        return

    if op in {"split_edge", "link_crossing"}:
        edge_id = edit.target_id
        edge = working.edges.get(edge_id)
        if edge is None:
            raise GraphEditError(f"edge {edge_id!r} does not exist", code="UNKNOWN_NODE_REFERENCE", edit=edit.key())
        split_node_id = str(params["new_node_id"])
        if split_node_id in working.nodes:
            # ``link_crossing`` semantics: the reviewer is explicitly joining this
            # edge to a node that already exists, so the node must lie on the edge.
            existing = working.nodes[split_node_id]
            point = _closest_point_on_edge(edge, (existing.x, existing.y))
            if point is None:
                raise GraphEditError(
                    f"node {split_node_id!r} does not lie on edge {edge_id!r}, so it cannot be linked to it",
                    code="INVALID_NUMERIC_VALUE",
                    edit=edit.key(),
                )
        else:
            fraction = float(params.get("fraction", 0.5))
            if not 0.0 < fraction < 1.0:
                raise GraphEditError(
                    "split fraction must be strictly between 0 and 1",
                    code="INVALID_NUMERIC_VALUE",
                    edit=edit.key(),
                )
            total = cumulative_lengths(edge.geometry)[-1]
            point = _interpolate(edge.geometry, total * fraction)
            working.nodes[split_node_id] = Node(
                id=split_node_id,
                x=point[0],
                y=point[1],
                node_type=NodeType(params.get("node_type", NodeType.JUNCTION.value)),
                name=str(params.get("name", "")),
                provenance_class=ProvenanceClass(params.get("provenance_class", ProvenanceClass.SYNTHETIC.value)),
        )
        suffix = params.get("suffix", "split")
        first, second = _split_edge(
            working,
            edge,
            working.nodes[split_node_id],
            (str(params.get("first_id", f"{edge_id}#{suffix}1")), str(params.get("second_id", f"{edge_id}#{suffix}2"))),
        )
        del working.edges[edge_id]
        working.edges[first.id] = first
        working.edges[second.id] = second
        _rebind_evidence(working, edge_id, [first.id, second.id], f"Split from {edge_id} at {split_node_id}.")
        return

    if op == "update_attribute":
        element_id = edit.target_id
        if element_id not in working.nodes and element_id not in working.edges:
            raise GraphEditError(
                f"unknown element {element_id!r}", code="UNKNOWN_NODE_REFERENCE", edit=edit.key()
            )
        field_name = str(params["field"])
        record = EvidenceRecord(
            id=working.next_evidence_id(element_id, field_name),
            element_id=element_id,
            field=field_name,
            value=params.get("value"),
            unit=params.get("unit"),
            method=str(params.get("method", "manual_entry")),
            source=str(params.get("source", "user_entered")),
            source_url=params.get("source_url"),
            observed_at=_parse_optional_timestamp(params.get("observed_at")),
            verification_status=params.get("verification_status", "unverified"),
            quality=params.get("quality", "medium"),
            reviewer=params.get("reviewer"),
            provenance_class=ProvenanceClass(params.get("provenance_class", ProvenanceClass.ASSUMED.value)),
            synthetic=bool(params.get("synthetic", False)),
            note=str(params.get("note", "")),
        )
        working.add_evidence(record)
        return

    if op in {"close_edge", "activate_temporary_edge"}:
        # Phase-scoped operations are resolved by build_phase_graph, not here.
        return

    raise GraphEditError(f"unsupported graph edit operation {op!r}", code="INVALID_INPUT", edit=edit.key())


def _parse_optional_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    from detour_lab.domain.units import parse_timestamp

    return parse_timestamp(str(value), field="observed_at")


def _edit_dependencies(edit: GraphEdit, all_edits: list[GraphEdit]) -> set[str]:
    """Edits that must be applied before ``edit``.

    Edits arrive in canonical key order, which is deterministic but ignores
    dependencies: ``add_edge`` sorts before ``add_node`` even though it needs the
    node. A stable topological sort keeps determinism *and* correctness.
    """
    params = edit.params
    deps: set[str] = set()
    if edit.op == "add_edge":
        for endpoint in (str(params.get("u")), str(params.get("v"))):
            deps |= {
                other.key()
                for other in all_edits
                if (other.op == "add_node" and str(other.params.get("id")) == endpoint)
                or (other.op == "remove_edge" and other.target_id == str(params.get("id")))
            }
    elif edit.op in {"split_edge", "link_crossing"}:
        new_node = str(params.get("new_node_id"))
        deps |= {
            other.key()
            for other in all_edits
            if other.op == "add_node" and str(other.params.get("id")) == new_node
        }
    elif edit.op == "update_attribute":
        target = edit.target_id
        deps |= {
            other.key()
            for other in all_edits
            if other.op in {"add_node", "add_edge"} and str(other.params.get("id")) == target
        }
    return deps


def order_edits(edits: list[GraphEdit]) -> list[GraphEdit]:
    """Stable, deterministic topological ordering of scenario edits."""
    by_key = {edit.key(): edit for edit in edits}
    if len(by_key) != len(edits):
        raise GraphEditError(
            "duplicate graph edit operations in the same scenario",
            code="DUPLICATE_ID",
        )
    dependencies = {key: _edit_dependencies(edit, edits) for key, edit in by_key.items()}
    remaining = sorted(by_key)
    ordered: list[GraphEdit] = []
    applied: set[str] = set()

    while remaining:
        ready = sorted(key for key in remaining if dependencies[key] <= applied)
        if not ready:
            unresolved = sorted(set().union(*(dependencies[key] for key in remaining)) - applied)
            raise GraphEditError(
                "cyclic or unsatisfiable graph edit dependencies",
                code="CYCLIC_DEPENDENCY",
                detail={"blocked_edits": remaining, "waiting_on": unresolved},
            )
        for key in ready:
            ordered.append(by_key[key])
            applied.add(key)
            remaining.remove(key)
    return ordered


def apply_edits(graph: PedestrianGraph, edits: list[GraphEdit]) -> PedestrianGraph:
    """Apply typed edits deterministically, returning a **new** graph."""
    working = _Working(
        nodes={node.id: node for node in graph.nodes},
        edges={edge.id: edge for edge in graph.edges},
        evidence={record.id: record for record in graph.evidence_registry.all_records()},
    )
    for edit in order_edits(edits):
        _apply_one(working, edit)
    return _materialise(graph, working, closed_edge_ids=graph.closed_edge_ids)


def _materialise(
    base: PedestrianGraph, working: _Working, *, closed_edge_ids: frozenset[str], version_id: str | None = None
) -> PedestrianGraph:
    version = BaseGraphVersion(
        id=version_id or base.version.id,
        schema_version=base.version.schema_version,
        basis=base.version.basis,
        nodes=sorted(working.nodes.values(), key=lambda n: n.id),
        edges=sorted(working.edges.values(), key=lambda e: e.id),
        inactive_edge_ids=sorted(closed_edge_ids),
        evidence=sorted(working.evidence.values(), key=lambda r: r.id),
        source=base.version.source,
        created_at=base.version.created_at,
    )
    return PedestrianGraph.from_version(version)


@dataclass(frozen=True, slots=True)
class PhaseGraph:
    """Result of applying a scenario to one phase."""

    graph: PedestrianGraph
    phase_id: str
    closed_edge_ids: frozenset[str]
    active_temporary_edge_ids: frozenset[str]
    warnings: tuple[str, ...] = ()

    @property
    def phase_graph_id(self) -> str:
        return self.graph.version.id

    @property
    def phase_graph_hash(self) -> str:
        return self.graph.version.content_hash


def build_phase_graph(
    base_graph: PedestrianGraph,
    scenario: Scenario,
    phase_id: str,
    *,
    temporary_edges: list[TemporaryEdge] | None = None,
) -> PhaseGraph:
    """Pure ``build_phase_graph(base_version, scenario_revision, phase)``."""
    phase: Phase | None = scenario.phase_by_id(phase_id)
    if phase is None:
        raise GraphEditError(
            f"phase {phase_id!r} is not declared in scenario {scenario.id!r}",
            code="INVALID_INPUT",
        )
    if scenario.base_graph_version_id != base_graph.version.id:
        raise GraphEditError(
            f"scenario {scenario.id!r} targets base graph {scenario.base_graph_version_id!r}, "
            f"but the supplied graph is {base_graph.version.id!r}",
            code="INVALID_INPUT",
        )

    warnings: list[str] = []

    # 1. Structural edits (phases are applied after, never inside, a scenario edit list).
    phase_graph = apply_edits(base_graph, [e for e in scenario.edits if e.op not in {"close_edge", "activate_temporary_edge"}])

    # 2. Temporary edges exist only in the phases that declare them.
    declared = {t.id: t for t in (temporary_edges if temporary_edges is not None else scenario.temporary_edges)}
    to_activate = set(phase.temporary_edge_ids)
    for edit in scenario.edits:
        if edit.op == "activate_temporary_edge" and (
            not edit.params.get("phases") or phase_id in edit.params["phases"]
        ):
            to_activate.add(edit.target_id)

    working = _Working(
        nodes={node.id: node for node in phase_graph.nodes},
        edges={edge.id: edge for edge in phase_graph.edges},
        evidence={record.id: record for record in phase_graph.evidence_registry.all_records()},
    )
    for temp_id in sorted(to_activate):
        temp = declared.get(temp_id)
        if temp is None:
            raise GraphEditError(
                f"temporary edge {temp_id!r} is not declared by the scenario", code="INVALID_INPUT"
            )
        _insert_temporary_edge(working, temp)
    for temp_id in sorted(set(declared) - {p for phase_scenario in scenario.phases for p in phase_scenario.temporary_edge_ids}):
        warnings.append(
            f"Temporary edge {temp_id!r} is declared but not activated in any phase of scenario {scenario.id!r}; "
            "it will not exist in any phase graph."
        )

    # 3. Closures.
    closed = set(phase.closed_edge_ids)
    for edit in scenario.edits:
        if edit.op == "close_edge" and (not edit.params.get("phases") or phase_id in edit.params["phases"]):
            closed.add(edit.target_id)
    missing = sorted(closed - working.edges.keys())
    if missing:
        raise GraphEditError(
            f"closure references unknown edge(s) {missing} in phase {phase_id!r}",
            code="UNKNOWN_NODE_REFERENCE",
        )

    graph = _materialise(
        base_graph,
        working,
        closed_edge_ids=frozenset(closed),
        version_id=f"{base_graph.version.id}~scenario:{scenario.id}~phase:{phase_id}",
    )
    return PhaseGraph(
        graph=graph,
        phase_id=phase_id,
        closed_edge_ids=graph.closed_edge_ids,
        active_temporary_edge_ids=frozenset(sorted(to_activate)),
        warnings=tuple(warnings),
    )


def _insert_temporary_edge(working: _Working, temp: TemporaryEdge) -> None:
    for endpoint in (temp.u, temp.v):
        if endpoint not in working.nodes:
            raise GraphEditError(
                f"temporary edge {temp.id!r} references unknown node {endpoint!r}",
                code="UNKNOWN_NODE_REFERENCE",
            )
    edge_id = f"TMP::{temp.id}"
    if edge_id in working.edges:
        raise GraphEditError(f"temporary edge {edge_id!r} already exists", code="DUPLICATE_ID")
    working.edges[edge_id] = Edge(
        id=edge_id,
        u=temp.u,
        v=temp.v,
        geometry=list(temp.geometry),
        length_m=temp.length_m,
        edge_type=temp.edge_type,
        name=temp.name or f"Modelled temporary path {temp.id}",
        provenance_class=ProvenanceClass.ASSUMED,
    )
    for record in temp.evidence:
        rebound = record.model_copy(
            update={
                "id": f"{edge_id}::{record.field}::1",
                "element_id": edge_id,
                "note": f"{record.note} Modelled temporary path; not a field-verified construction.".strip(),
            }
        )
        working.add_evidence(rebound)