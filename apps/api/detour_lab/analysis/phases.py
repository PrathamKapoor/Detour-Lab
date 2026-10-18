"""Phase timeline reads.

Gate 4 needs two things the API could not previously answer:

* the **materialised** graph of one phase, so a client never has to reconstruct
  closures and temporary connections itself;
* an ordered timeline of the scenario's phases, including which of them have
  already been analysed.

Both are pure reads of state the domain already computes. Nothing here decides
a verdict, and nothing here invents an ordering: the sequence is produced by
``Scenario.ordered_phases()``, which sorts on ``Phase.order``.

The module deliberately contains no analysis logic. Whether a phase "passed" is
answered by the stored runs, not by this file.
"""

from __future__ import annotations

from dataclasses import dataclass

from detour_lab.domain.contracts import BaseGraphVersion, Scenario
from detour_lab.graph.model import PedestrianGraph
from detour_lab.scenarios.apply import PhaseGraph, build_phase_graph

__all__ = ["PhaseTimelineEntry", "build_timeline", "load_phase_graph", "phase_graph_payload"]


@dataclass(frozen=True, slots=True)
class PhaseTimelineEntry:
    """One phase in authoritative order, with its declared modifications."""

    phase_id: str
    order: int
    label: str
    notes: str
    boundary_convention: str
    closed_edge_ids: tuple[str, ...]
    temporary_edge_ids: tuple[str, ...]
    phase_graph_id: str
    phase_graph_hash: str
    warnings: tuple[str, ...]
    analysis: dict[str, object]


def _analysis_state(
    runs: list[dict[str, object]], phase_id: str, revision: int, profile_ids: tuple[str, ...]
) -> dict[str, object]:
    """Summarise the runs already stored for this phase.

    ``available_runs`` is informational. ``current_revision_run`` is the only run
    that may be presented as the result of the scenario's current revision; an
    older run is history, not the present.
    """
    matching = [run for run in runs if run.get("phase_id") == phase_id]
    for profile_id in profile_ids:
        current = [
            run
            for run in matching
            if run.get("scenario_revision") == revision and run.get("profile_id") == profile_id
        ]
        if current:
            latest = max(current, key=lambda run: (str(run.get("created_at") or ""), str(run.get("id"))))
            return {
                "analysed": True,
                "state": "analysed",
                "run_id": latest.get("id"),
                "profile_id": profile_id,
                "semantic_hash": latest.get("semantic_hash"),
                "scenario_revision": latest.get("scenario_revision"),
                "stale": False,
            }
    return {
        "analysed": False,
        # NOT ANALYSED is deliberately not a verdict: it is not Pass, Fail or Unknown.
        "state": "NOT_ANALYSED",
        "run_id": None,
        "profile_id": None,
        "semantic_hash": None,
        "scenario_revision": None,
        "stale": bool(matching),
        "historical_run_count": len(matching),
    }


def build_timeline(
    scenario: Scenario,
    base_graph: PedestrianGraph,
    *,
    runs: list[dict[str, object]] | None = None,
    profile_ids: tuple[str, ...] = (),
) -> list[PhaseTimelineEntry]:
    """Ordered phase timeline for one scenario revision.

    ``Phase.order`` is the only ordering authority; the sequence is not derived
    from phase ids, labels or array position.
    """
    run_rows = runs or []
    entries: list[PhaseTimelineEntry] = []
    for phase in scenario.ordered_phases():
        phase_graph = build_phase_graph(base_graph, scenario, phase.id)
        entries.append(
            PhaseTimelineEntry(
                phase_id=phase.id,
                order=phase.order,
                label=phase.label,
                notes=phase.notes,
                boundary_convention=phase.boundary_convention,
                closed_edge_ids=tuple(sorted(phase_graph.closed_edge_ids)),
                temporary_edge_ids=tuple(sorted(phase_graph.active_temporary_edge_ids)),
                phase_graph_id=phase_graph.phase_graph_id,
                phase_graph_hash=phase_graph.phase_graph_hash,
                warnings=phase_graph.warnings,
                analysis=_analysis_state(run_rows, phase.id, scenario.revision, profile_ids),
            )
        )
    return entries


def load_phase_graph(base_graph: PedestrianGraph, scenario: Scenario, phase_id: str) -> PhaseGraph:
    """Materialise one phase, re-raising the domain error as-is.

    An unknown phase id raises ``GraphEditError(code="INVALID_INPUT")`` which the
    API turns into a flat 422; it is never silently treated as "no closures".
    """
    return build_phase_graph(base_graph, scenario, phase_id)


#: A materialised temporary edge carries a namespaced id (``TMP::`` + the
#: declared :class:`TemporaryEdge` id) so it can never collide with a permanent
#: edge id. ``active_temporary_edge_ids`` holds the *declared* ids, so the two
#: spaces must be reconciled rather than compared directly.
_TEMPORARY_EDGE_PREFIX = "TMP::"


def _is_active_temporary(edge_id: str, active_declared: frozenset[str]) -> bool:
    if edge_id in active_declared:
        return True
    if edge_id.startswith(_TEMPORARY_EDGE_PREFIX):
        return edge_id[len(_TEMPORARY_EDGE_PREFIX) :] in active_declared
    return False


def phase_graph_payload(
    base_graph: PedestrianGraph,
    scenario: Scenario,
    phase_id: str,
) -> dict[str, object]:
    """JSON payload describing the authoritative graph state of one phase.

    Geometry is the base graph's local-planar geometry; the closure and
    temporary-edge sets are the materialised phase's, not a client guess.
    """
    phase_graph = load_phase_graph(base_graph, scenario, phase_id)
    phase = scenario.phase_by_id(phase_id)
    graph = phase_graph.graph

    closed = phase_graph.closed_edge_ids
    temporary = phase_graph.active_temporary_edge_ids
    version: BaseGraphVersion = graph.version

    edges: list[dict[str, object]] = []
    for edge in graph.edges:
        is_temporary = _is_active_temporary(edge.id, temporary)
        edges.append(
            {
                "id": edge.id,
                "u": edge.u,
                "v": edge.v,
                "geometry": [[point[0], point[1]] for point in edge.geometry],
                "length_m": edge.length_m,
                "edge_type": edge.edge_type.value if edge.edge_type is not None else None,
                "name": edge.name,
                "provenance_class": edge.provenance_class.value
                if edge.provenance_class is not None
                else None,
                "evidence_ids": list(edge.evidence_ids),
                "closed": edge.id in closed,
                "temporary": is_temporary,
                "inactive": edge.id in version.inactive_edge_ids,
            }
        )

    return {
        "scenario_id": scenario.id,
        "scenario_revision": scenario.revision,
        "scenario_content_hash": scenario.content_hash,
        "phase_id": phase_id,
        "phase_order": phase.order if phase is not None else None,
        "phase_label": phase.label if phase is not None else "",
        "phase_notes": phase.notes if phase is not None else "",
        "boundary_convention": phase.boundary_convention if phase is not None else "logical_ordinal",
        "phase_graph_id": phase_graph.phase_graph_id,
        "phase_graph_hash": phase_graph.phase_graph_hash,
        "closed_edge_ids": sorted(closed),
        "active_temporary_edge_ids": sorted(temporary),
        "warnings": list(phase_graph.warnings),
        "nodes": [
            {
                "id": node.id,
                "x": node.x,
                "y": node.y,
                "node_type": node.node_type.value if node.node_type is not None else None,
                "name": node.name,
                "provenance_class": node.provenance_class.value
                if node.provenance_class is not None
                else None,
                "evidence_ids": list(node.evidence_ids),
            }
            for node in graph.nodes
        ],
        "edges": edges,
        "crossings": [
            {
                "edge_ids": list(crossing["edge_ids"]),
                "point": [crossing["point"][0], crossing["point"][1]],
                "connected_via_shared_node": crossing["connected_via_shared_node"],
                "shared_node_ids": list(crossing.get("shared_node_ids", [])),
            }
            for crossing in graph.unlinked_crossings()
        ],
    }