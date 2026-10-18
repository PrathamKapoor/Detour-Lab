"""Confirmed vs possible feasibility graphs and deterministic routing.

Two graphs are always produced (PRD FR-009/FR-010):

``confirmed``  every element with a non-empty set of applicable hard checks, all
               satisfied. A route here is *model-confirmed*.
``possible``   confirmed elements plus elements that are UNKNOWN **solely**
               because evidence is unresolved. A route here is hypothetical and
               is always labelled as such. An independently known FAIL is never
               rescued by an unknown elsewhere.

Routing returns the **ordered list of exact edge IDs**, not just node IDs, so a
multigraph's parallel edges stay distinguishable all the way to the UI.

Determinism: candidate paths are ordered by ``(distance_m, lexicographic edge-ID
sequence)``. Ties are therefore broken by an explicit rule, not by dictionary or
insertion order, and a test pins the behaviour.
"""

from __future__ import annotations

import heapq
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal

from detour_lab.domain.contracts import Edge, MobilityProfile
from detour_lab.domain.enums import VerdictState
from detour_lab.graph.model import PedestrianGraph

__all__ = [
    "FeasibilityGraphs",
    "PathResult",
    "build_feasibility_graphs",
    "edge_weight",
    "shortest_path",
]

EdgeWeightFn = Callable[[Edge], float]


@dataclass(frozen=True, slots=True)
class FeasibilityGraphs:
    confirmed_edge_ids: frozenset[str]
    possible_edge_ids: frozenset[str]
    states: Mapping[str, VerdictState]

    def describe(self) -> dict[str, list[str]]:
        return {
            "confirmed": sorted(self.confirmed_edge_ids),
            "possible": sorted(self.possible_edge_ids),
        }


def build_feasibility_graphs(
    graph: PedestrianGraph, edge_states: Mapping[str, VerdictState]
) -> FeasibilityGraphs:
    """Split edges into confirmed/possible sets using evaluated states only.

    An edge with **no applicable hard check** (``NOT_APPLICABLE``) is in neither
    set: the rulepack does not cover it, so passage cannot be confirmed. Silently
    treating uncovered types as "fine" is exactly the false-safe failure the PRD
    forbids.
    """
    confirmed: set[str] = set()
    possible: set[str] = set()
    for edge in graph.edges:
        if edge.id in graph.closed_edge_ids:
            continue
        state = edge_states.get(edge.id, VerdictState.UNKNOWN)
        if state is VerdictState.PASS:
            confirmed.add(edge.id)
            possible.add(edge.id)
        elif state is VerdictState.UNKNOWN:
            possible.add(edge.id)
    return FeasibilityGraphs(frozenset(confirmed), frozenset(possible), dict(edge_states))


def edge_weight(edge: Edge, profile: MobilityProfile, known_fields: frozenset[str] | None = None) -> float:
    """Route cost in metres.

    Length is the only structural term. Profile *preferences* may add a small
    additive metre-equivalent penalty, which can change **which** feasible route
    is selected but can never resurrect an excluded edge or change a verdict
    (INV-05). Unknown/pending weighting is handled by the caller, which passes
    the fields it could resolve.
    """
    weight = float(edge.length_m)
    if known_fields is not None:
        for field, penalty in sorted(profile.preference_weights.items()):
            if field in known_fields:
                weight += float(penalty)
    return weight


@dataclass(frozen=True, slots=True)
class PathResult:
    node_ids: tuple[str, ...]
    edge_ids: tuple[str, ...]
    distance_m: float
    cost: float
    kind: Literal["confirmed", "possible"]

    @property
    def has_preference_adjustment(self) -> bool:
        return abs(self.distance_m - self.cost) > 1e-9


def shortest_path(
    graph: PedestrianGraph,
    *,
    allowed_edge_ids: frozenset[str],
    source_node_id: str,
    target_node_id: str,
    weight_fn: EdgeWeightFn,
) -> PathResult | None:
    """Deterministic Dijkstra over an explicit allow-list of edge IDs.

    ``allowed_edge_ids`` is mandatory: routing never inspects the whole graph, so
    a closed or failing edge cannot be traversed by accident (INV-03).
    """
    if not graph.has_node(source_node_id) or not graph.has_node(target_node_id):
        return None
    if source_node_id == target_node_id:
        return PathResult((source_node_id,), (), 0.0, 0.0, "confirmed")

    settled: set[str] = set()
    # Heap entries: (rounded distance for stable ordering, path edge-ID tuple, node)
    heap: list[tuple[float, tuple[str, ...], str]] = [(0.0, (), source_node_id)]
    best_distance: dict[str, float] = {source_node_id: 0.0}

    while heap:
        distance, edge_path, node_id = heapq.heappop(heap)
        if node_id in settled:
            continue
        settled.add(node_id)

        if node_id == target_node_id:
            node_path = _node_path(graph, edge_path, source_node_id)
            physical = 0.0
            for edge_id in edge_path:
                edge = graph.edge(edge_id)
                if edge is None:  # pragma: no cover
                    raise ValueError(f"routing returned unknown edge {edge_id}")
                physical += float(edge.length_m)
            return PathResult(node_path, edge_path, round(physical, 6), round(distance, 6), "confirmed")

        for edge_id in graph.outgoing_edge_ids(node_id):
            if edge_id not in allowed_edge_ids:
                continue
            edge = graph.edge(edge_id)
            if edge is None:  # pragma: no cover - allow-list comes from this graph
                continue
            weight = float(weight_fn(edge))
            if weight != weight or weight in (float("inf"), float("-inf")) or weight < 0:
                raise ValueError(f"edge {edge.id} produced a non-finite or negative routing weight {weight}")
            if weight == 0 and edge.length_m > 0:
                # A zero weight on a non-zero-length edge means an absent weight
                # silently became a free hop; refuse it rather than trusting it.
                raise ValueError(f"edge {edge.id} produced a zero routing weight for a {edge.length_m} m segment")
            candidate = distance + weight
            current = best_distance.get(edge.v)
            # Only strictly worse routes are pruned. Equal-cost alternatives must
            # stay in the heap so the documented lexicographic tie-break can pick
            # between them deterministically.
            if current is not None and candidate > current + 1e-12:
                continue
            best_distance[edge.v] = candidate
            heapq.heappush(heap, (round(candidate, 9), (*edge_path, edge_id), edge.v))

    return None


def _node_path(graph: PedestrianGraph, edge_path: tuple[str, ...], source: str) -> tuple[str, ...]:
    nodes = [source]
    current = source
    for edge_id in edge_path:
        edge = graph.edge(edge_id)
        if edge is None:  # pragma: no cover
            raise ValueError(f"routing returned unknown edge {edge_id}")
        current = edge.v
        nodes.append(current)
    return tuple(nodes)