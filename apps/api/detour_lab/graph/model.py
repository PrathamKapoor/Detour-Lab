"""Explicit directed pedestrian graph.

Topology invariants (MASTER_PROMPT §5.1, PRD FR-002, INV-02)
-------------------------------------------------------------
* Connectivity exists **only** through shared node IDs. Two edge geometries that
  cross in space are *not* connected; :meth:`PedestrianGraph.unlinked_crossings`
  reports those locations so the UI can offer an explicit ``link_crossing`` edit.
* Every edge endpoint must exist in the same graph version.
* Duplicate node/edge IDs are rejected; parallel edges are legal and keep unique IDs.
* Self-loops are rejected: a directed edge that starts and ends at the same node
  has no defined meaning in this model.
* Edge geometry endpoints must coincide with the coordinates of ``u`` and ``v``.

The class is immutable: every transformation returns a new instance and the
baseline version object is never mutated (INV-07).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import networkx as nx

from detour_lab.domain.contracts import BaseGraphVersion, Edge, EvidenceRecord, Node
from detour_lab.evidence.resolver import EvidenceRegistry

__all__ = ["GraphValidationError", "PedestrianGraph"]


class GraphValidationError(ValueError):
    """Raised when a graph violates a topology invariant.

    Carries a machine-readable ``code`` so the API can return a stable reason
    rather than a stack trace.
    """

    def __init__(self, message: str, *, code: str, detail: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.detail = detail or {}


@dataclass(frozen=True, slots=True)
class PedestrianGraph:
    """Immutable, validated, content-addressed pedestrian network."""

    version: BaseGraphVersion
    evidence_registry: EvidenceRegistry = field(compare=False, repr=False)
    _nodes: dict[str, Node] = field(init=False, compare=False, repr=False)
    _edges: dict[str, Edge] = field(init=False, compare=False, repr=False)
    _out: dict[str, tuple[str, ...]] = field(init=False, compare=False, repr=False)
    _in: dict[str, tuple[str, ...]] = field(init=False, compare=False, repr=False)

    def __post_init__(self) -> None:
        nodes: dict[str, Node] = {}
        for node in self.version.nodes:
            if node.id in nodes:
                raise GraphValidationError(
                    f"duplicate node ID {node.id!r}", code="DUPLICATE_ID", detail={"element_id": node.id}
                )
            nodes[node.id] = node

        edges: dict[str, Edge] = {}
        for edge in self.version.edges:
            if edge.id in edges:
                raise GraphValidationError(
                    f"duplicate edge ID {edge.id!r}", code="DUPLICATE_ID", detail={"element_id": edge.id}
                )
            if edge.u == edge.v:
                raise GraphValidationError(
                    f"edge {edge.id!r} is a self-loop ({edge.u})", code="SELF_LOOP", detail={"edge_id": edge.id}
                )
            for endpoint in (edge.u, edge.v):
                if endpoint not in nodes:
                    raise GraphValidationError(
                        f"edge {edge.id!r} references unknown node {endpoint!r}",
                        code="UNKNOWN_NODE_REFERENCE",
                        detail={"edge_id": edge.id, "node_id": endpoint},
                    )
            tail = nodes[edge.u]
            head = nodes[edge.v]
            if edge.geometry[0] != (tail.x, tail.y):
                raise GraphValidationError(
                    f"edge {edge.id!r} geometry does not start at node {edge.u!r}",
                    code="GEOMETRY_ENDPOINT_MISMATCH",
                    detail={"edge_id": edge.id},
                )
            if edge.geometry[-1] != (head.x, head.y):
                raise GraphValidationError(
                    f"edge {edge.id!r} geometry does not end at node {edge.v!r}",
                    code="GEOMETRY_ENDPOINT_MISMATCH",
                    detail={"edge_id": edge.id},
                )
            edges[edge.id] = edge

        unknown_closed = set(self.version.inactive_edge_ids) - edges.keys()
        if unknown_closed:
            raise GraphValidationError(
                f"inactive_edge_ids references unknown edge(s): {sorted(unknown_closed)}",
                code="UNKNOWN_NODE_REFERENCE",
                detail={"edge_ids": sorted(unknown_closed)},
            )

        out: dict[str, list[str]] = defaultdict(list)
        inbound: dict[str, list[str]] = defaultdict(list)
        for edge_id in sorted(edges):
            out[edges[edge_id].u].append(edge_id)
            inbound[edges[edge_id].v].append(edge_id)

        object.__setattr__(self, "_nodes", nodes)
        object.__setattr__(self, "_edges", edges)
        object.__setattr__(self, "_out", {k: tuple(v) for k, v in out.items()})
        object.__setattr__(self, "_in", {k: tuple(v) for k, v in inbound.items()})

    # ------------------------------------------------------------------ identity
    @property
    def id(self) -> str:
        return self.version.id

    @property
    def content_hash(self) -> str:
        return self.version.content_hash

    @property
    def closed_edge_ids(self) -> frozenset[str]:
        """Edges that exist in this version but must not be traversed.

        Read-only and derived from the version, which is part of the content hash,
        so a closure can never disagree with the graph it belongs to.
        """
        return frozenset(self.version.inactive_edge_ids)

    def __len__(self) -> int:
        return len(self._edges)

    # ------------------------------------------------------------------- queries
    @property
    def nodes(self) -> tuple[Node, ...]:
        return tuple(self._nodes[k] for k in sorted(self._nodes))

    @property
    def edges(self) -> tuple[Edge, ...]:
        return tuple(self._edges[k] for k in sorted(self._edges))

    def node(self, node_id: str) -> Node | None:
        return self._nodes.get(node_id)

    def edge(self, edge_id: str) -> Edge | None:
        return self._edges.get(edge_id)

    def has_node(self, node_id: str) -> bool:
        return node_id in self._nodes

    def has_edge(self, edge_id: str) -> bool:
        return edge_id in self._edges

    def outgoing_edge_ids(self, node_id: str) -> tuple[str, ...]:
        """Outgoing edge IDs, canonically sorted for deterministic traversal."""
        return self._out.get(node_id, ())

    def incoming_edge_ids(self, node_id: str) -> tuple[str, ...]:
        return self._in.get(node_id, ())

    def active_edges(self) -> tuple[Edge, ...]:
        return tuple(e for e in self.edges if e.id not in self.closed_edge_ids)

    def evidence_for(self, element_id: str, field_name: str) -> tuple[EvidenceRecord, ...]:
        return self.evidence_registry.for_field(element_id, field_name)

    # ------------------------------------------------------------- interop / QA
    def to_networkx(self) -> nx.MultiDiGraph:
        """Directed multigraph; parallel edges are preserved as distinct keys."""
        g = nx.MultiDiGraph(graph_id=self.version.id)
        for node in self._nodes.values():
            g.add_node(node.id, node_type=node.node_type.value, x=node.x, y=node.y)
        for edge in self._edges.values():
            g.add_edge(
                edge.u,
                edge.v,
                key=edge.id,
                edge_id=edge.id,
                length_m=edge.length_m,
                edge_type=edge.edge_type.value,
                closed=edge.id in self.closed_edge_ids,
            )
        return g

    def unlinked_crossings(self, tolerance: float = 1e-9) -> list[dict[str, Any]]:
        """Report geometric crossings that are **not** graph connections.

        Purely diagnostic (used by the topology QA panel and INV-02 tests): it
        proves that space intersection never implies connectivity.
        """
        results: list[dict[str, Any]] = []
        segments: list[tuple[str, Edge, tuple[tuple[float, float], tuple[float, float]]]] = []
        for edge in self._edges.values():
            for index in range(len(edge.geometry) - 1):
                segments.append((edge.id, edge, (edge.geometry[index], edge.geometry[index + 1])))

        for i, (edge_a_id, edge_a, seg_a) in enumerate(segments):
            for edge_b_id, edge_b, seg_b in segments[i + 1 :]:
                if edge_a_id == edge_b_id:
                    continue
                point = _segment_intersection(seg_a, seg_b, tolerance)
                if point is None:
                    continue
                # A crossing counts as a connection only if a node sits at that
                # point AND that node is an endpoint of both edges.
                endpoints_a = {edge_a.u, edge_a.v}
                endpoints_b = {edge_b.u, edge_b.v}
                shared = sorted(self._nodes_at(point) & endpoints_a & endpoints_b)
                results.append(
                    {
                        "edge_ids": [edge_a_id, edge_b_id],
                        "point": [point[0], point[1]],
                        "connected_via_shared_node": bool(shared),
                        "shared_node_ids": shared,
                    }
                )
        return sorted(results, key=lambda r: (r["edge_ids"], r["point"]))

    def _nodes_at(self, point: tuple[float, float], tolerance: float = 1e-9) -> set[str]:
        return {
            node.id
            for node in self._nodes.values()
            if abs(node.x - point[0]) <= tolerance and abs(node.y - point[1]) <= tolerance
        }

    # --------------------------------------------------------------- iteration
    def __iter__(self) -> Iterator[Edge]:
        return iter(self.edges)

    @classmethod
    def from_version(cls, version: BaseGraphVersion) -> PedestrianGraph:
        return cls(version=version, evidence_registry=EvidenceRegistry(version.evidence))


def _segment_intersection(
    a: tuple[tuple[float, float], tuple[float, float]],
    b: tuple[tuple[float, float], tuple[float, float]],
    tolerance: float,
) -> tuple[float, float] | None:
    """Proper/improper intersection of two 2D segments, ignoring collinear overlaps."""
    (x1, y1), (x2, y2) = a
    (x3, y3), (x4, y4) = b
    denominator = (x2 - x1) * (y4 - y3) - (y2 - y1) * (x4 - x3)
    if abs(denominator) < tolerance:
        return None  # parallel or collinear: not a crossing we want to flag
    t = ((x3 - x1) * (y4 - y3) - (y3 - y1) * (x4 - x3)) / denominator
    u = ((x3 - x1) * (y2 - y1) - (y3 - y1) * (x2 - x1)) / denominator
    if -tolerance <= t <= 1 + tolerance and -tolerance <= u <= 1 + tolerance:
        return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))
    return None