"""End-to-end deterministic analysis pipeline.

    build_phase_graph -> evaluate rules -> confirmed/possible graphs
                      -> OD reachability -> findings -> counts

This module is the single orchestration point. Nothing else is allowed to derive
verdicts, routes or feasibility (MASTER_PROMPT §4 separation-of-concerns).
"""

from __future__ import annotations

from datetime import datetime

from detour_lab.domain.contracts import (
    AnalysisResult,
    EdgeEvaluation,
    Finding,
    MobilityProfile,
    ODPairResult,
    OriginDestination,
    RulePack,
    Scenario,
)
from detour_lab.domain.enums import ReasonCode, VerdictState
from detour_lab.graph.model import PedestrianGraph
from detour_lab.graph.routing import (
    FeasibilityGraphs,
    build_feasibility_graphs,
    edge_weight,
    shortest_path,
)
from detour_lab.rules.engine import evaluate_graph
from detour_lab.scenarios.apply import build_phase_graph

__all__ = ["MAX_BLOCKER_PROBES", "run_analysis"]

#: Safety valve for the counterexample-based blocker probe. Each probe re-routes a
#: single OD pair, so the cost is linear in the number of known-fail frontier
#: edges. Beyond the cap, findings are reported as *relevant*, never as blocking.
MAX_BLOCKER_PROBES = 60


def _known_fields(graph: PedestrianGraph, element_id: str) -> frozenset[str]:
    fields = {
        record.field
        for record in graph.evidence_registry.for_element(element_id)
        if not record.invalidated
    }
    return frozenset(fields)


def _findings_by_element(findings: list[Finding]) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    for finding in findings:
        mapping.setdefault(finding.element_id, []).append(finding.id)
    return mapping


def run_analysis(
    *,
    base_graph: PedestrianGraph,
    scenario: Scenario,
    phase_id: str,
    profile_id: str,
    rulepack: RulePack,
    profile: MobilityProfile,
    as_of: datetime,
) -> AnalysisResult:
    """Evaluate one (scenario, phase, profile, rulepack) combination.

    ``as_of`` is mandatory, not defaulted: it is the instant at which evidence
    freshness is judged. An unspecified "now" would make verdicts depend on the
    wall clock and would silently invalidate every record carrying a freshness
    policy, so the caller records the value in the run and reuses it on replay.
    """
    phase_graph = build_phase_graph(base_graph, scenario, phase_id)
    graph = phase_graph.graph

    evaluation = evaluate_graph(
        graph=graph,
        rulepack=rulepack,
        profile_id=profile_id,
        phase_id=phase_id,
        as_of=as_of,
    )
    feasibility: FeasibilityGraphs = build_feasibility_graphs(graph, evaluation.edge_states)

    findings_by_element = _findings_by_element(evaluation.findings)

    edge_evaluations: list[EdgeEvaluation] = []
    for edge in graph.edges:
        state = evaluation.edge_states.get(edge.id, VerdictState.UNKNOWN)
        verdicts = [v for v in evaluation.verdicts if v.element_id == edge.id]
        relevant_checks = sum(
            len(v.inputs) for v in verdicts if v.state is not VerdictState.NOT_APPLICABLE
        )
        closed = edge.id in graph.closed_edge_ids
        confirmed_eligible = (not closed) and state is VerdictState.PASS and relevant_checks > 0
        possibly_eligible = (not closed) and state in (VerdictState.PASS, VerdictState.UNKNOWN)
        edge_evaluations.append(
            EdgeEvaluation(
                edge_id=edge.id,
                state=VerdictState.FAIL if closed else state,
                relevant_check_count=relevant_checks,
                confirmed_eligible=confirmed_eligible,
                possibly_eligible=possibly_eligible,
                unknown_only=(state is VerdictState.UNKNOWN and not closed),
                reason_codes=sorted(
                    {v.reason_code for v in verdicts if v.state is not VerdictState.PASS},
                    key=lambda r: r.value,
                )
                + ([ReasonCode.EDGE_CLOSED_IN_PHASE] if closed else []),
                verdict_ids=sorted(f"V-{edge.id}-{v.rule_id}" for v in verdicts),
                findings=[f for f in evaluation.findings if f.element_id == edge.id],
            )
        )

    origins = [od for od in scenario.origins_destinations if od.kind in ("origin", "both")]
    destinations = [od for od in scenario.origins_destinations if od.kind in ("destination", "both")]

    od_results: list[ODPairResult] = []
    for origin in origins:
        for destination in destinations:
            od_results.append(
                _evaluate_pair(
                    graph=graph,
                    feasibility=feasibility,
                    origins=origin,
                    destination=destination,
                    profile=profile,
                    findings_by_element=findings_by_element,
                    fail_edge_ids=frozenset(
                        edge.id
                        for edge in graph.edges
                        if evaluation.edge_states.get(edge.id) is VerdictState.FAIL
                        and edge.id not in graph.closed_edge_ids
                    ),
                )
            )

    counts = _counts(edge_evaluations, evaluation.verdicts, evaluation.findings)
    return AnalysisResult(
        scenario_id=scenario.id,
        scenario_hash=scenario.content_hash,
        phase_id=phase_id,
        profile_id=profile_id,
        rulepack_id=rulepack.id,
        rulepack_version=rulepack.version,
        rulepack_hash=rulepack.content_hash,
        base_graph_version_id=base_graph.version.id,
        base_graph_hash=base_graph.version.content_hash,
        phase_graph_id=phase_graph.phase_graph_id,
        phase_graph_hash=phase_graph.phase_graph_hash,
        edge_evaluations=edge_evaluations,
        verdicts=evaluation.verdicts,
        od_results=od_results,
        counts=counts,
        warnings=list(evaluation.warnings) + list(phase_graph.warnings),
    )


def _weight_fn_factory(graph: PedestrianGraph, profile: MobilityProfile):
    cache: dict[str, frozenset[str]] = {}

    def weight(edge):
        fields = cache.get(edge.id)
        if fields is None:
            fields = _known_fields(graph, edge.id)
            cache[edge.id] = fields
        return edge_weight(edge, profile, fields)

    return weight


def _evaluate_pair(
    *,
    graph: PedestrianGraph,
    feasibility: FeasibilityGraphs,
    origins: OriginDestination,
    destination: OriginDestination,
    profile: MobilityProfile,
    findings_by_element: dict[str, list[str]],
    fail_edge_ids: frozenset[str],
) -> ODPairResult:
    reasons: list[ReasonCode] = []
    blocking: list[str] = []

    origin_ok = graph.has_node(origins.node_id)
    destination_ok = graph.has_node(destination.node_id)
    if not origin_ok:
        reasons.append(ReasonCode.ORIGIN_NODE_MISSING)
    if not destination_ok:
        reasons.append(ReasonCode.DESTINATION_NODE_MISSING)

    confirmed_path = None
    possible_path = None
    if origin_ok and destination_ok:
        weight_fn = _weight_fn_factory(graph, profile)
        confirmed_path = shortest_path(
            graph,
            allowed_edge_ids=feasibility.confirmed_edge_ids,
            source_node_id=origins.node_id,
            target_node_id=destination.node_id,
            weight_fn=weight_fn,
        )
        possible_path = shortest_path(
            graph,
            allowed_edge_ids=feasibility.possible_edge_ids,
            source_node_id=origins.node_id,
            target_node_id=destination.node_id,
            weight_fn=weight_fn,
        )

        if confirmed_path is not None:
            reasons.append(ReasonCode.CONFIRMED_ROUTE_FOUND)
        if possible_path is not None and confirmed_path is None:
            reasons.append(ReasonCode.POSSIBLE_ROUTE_ONLY)
        if possible_path is None:
            reasons.append(ReasonCode.NO_ROUTE)

        if confirmed_path is None:
            blocking = _demonstrated_blockers(
                graph=graph,
                feasibility=feasibility,
                origin_node_id=origins.node_id,
                destination_node_id=destination.node_id,
                weight_fn=weight_fn,
                fail_edge_ids=fail_edge_ids,
                findings_by_element=findings_by_element,
            )

    relevant_elements = _relevant_elements(
        graph, feasibility, origins.node_id, confirmed_path, possible_path
    )
    relevant = sorted(
        {fid for element in relevant_elements for fid in findings_by_element.get(element, [])}
    )

    return ODPairResult(
        origin_id=origins.id,
        destination_id=destination.id,
        origin_node_id=origins.node_id,
        destination_node_id=destination.node_id,
        confirmed_reachable=confirmed_path is not None,
        possibly_reachable=possible_path is not None,
        confirmed_path_edge_ids=list(confirmed_path.edge_ids) if confirmed_path else [],
        confirmed_distance_m=confirmed_path.distance_m if confirmed_path else None,
        possible_path_edge_ids=list(possible_path.edge_ids) if possible_path else [],
        possible_distance_m=possible_path.distance_m if possible_path else None,
        confirmed_route_cost=confirmed_path.cost if confirmed_path else None,
        possible_route_cost=possible_path.cost if possible_path else None,
        route_note=(
            "Reported distance is the physical route length. Ranking cost also applies "
            f"{profile.id} preference weights."
            if profile.preference_weights
            else "Reported distance is the physical route length; this profile declares no preference weights."
        ),
        blocking_finding_ids=blocking,
        relevant_finding_ids=relevant,
        reason_codes=sorted(set(reasons), key=lambda r: r.value),
    )


def _demonstrated_blockers(
    *,
    graph: PedestrianGraph,
    feasibility: FeasibilityGraphs,
    origin_node_id: str,
    destination_node_id: str,
    weight_fn,
    fail_edge_ids: frozenset[str],
    findings_by_element: dict[str, list[str]],
) -> list[str]:
    """Identify blocking findings by **reproducible counterexample**, not guesswork.

    An edge is only called blocking when removing exactly that edge turns an
    unreachable pair into a model-confirmed route. Everything else stays in
    ``relevant_finding_ids`` (MASTER_PROMPT §6.7).
    """
    if confirmed_route_exists(feasibility, origin_node_id, destination_node_id, weight_fn, graph):
        return []
    blocking: list[str] = []
    for probe_index, edge_id in enumerate(sorted(fail_edge_ids)):
        if probe_index >= MAX_BLOCKER_PROBES:
            break
        probe_set = feasibility.possible_edge_ids - {edge_id}
        if confirmed_route_exists(
            feasibility, origin_node_id, destination_node_id, weight_fn, graph, allowed=probe_set
        ):
            blocking.extend(findings_by_element.get(edge_id, []))
    return sorted(set(blocking))


def confirmed_route_exists(
    feasibility: FeasibilityGraphs,
    origin_node_id: str,
    destination_node_id: str,
    weight_fn,
    graph: PedestrianGraph,
    *,
    allowed: frozenset[str] | None = None,
) -> bool:
    path = shortest_path(
        graph,
        allowed_edge_ids=allowed if allowed is not None else feasibility.confirmed_edge_ids,
        source_node_id=origin_node_id,
        target_node_id=destination_node_id,
        weight_fn=weight_fn,
    )
    return path is not None


def _relevant_elements(
    graph: PedestrianGraph,
    feasibility: FeasibilityGraphs,
    origin_node_id: str,
    confirmed_path,
    possible_path,
) -> set[str]:
    """Edges/nodes a reviewer should actually look at for this OD pair.

    Definition (documented, not hand-waved): every edge/node on the confirmed or
    possible route, plus the *frontier*: edges incident to nodes that are
    reachable from the origin in the possible graph and from which the
    destination has not been confirmed. These are the elements where a known
    failure plausibly matters, so they are labelled **relevant**, never
    automatically *blocking*.
    """
    elements: set[str] = set()
    for path in (confirmed_path, possible_path):
        if path is None:
            continue
        for edge_id in path.edge_ids:
            edge = graph.edge(edge_id)
            if edge is not None:
                elements.update({edge_id, edge.u, edge.v})

    reachable = {origin_node_id}
    frontier_nodes: set[str] = set()
    stack = [origin_node_id]
    while stack:
        node_id = stack.pop()
        for edge_id in graph.outgoing_edge_ids(node_id):
            if edge_id not in feasibility.possible_edge_ids:
                continue
            edge = graph.edge(edge_id)
            if edge is None:  # pragma: no cover
                continue
            if edge.v not in reachable:
                reachable.add(edge.v)
                stack.append(edge.v)
            frontier_nodes.add(node_id)
    for node_id in sorted(frontier_nodes):
        for edge_id in graph.outgoing_edge_ids(node_id):
            if edge_id in feasibility.possible_edge_ids:
                elements.add(edge_id)
                elements.add(node_id)
    return elements


def _counts(edge_evaluations, verdicts, findings) -> dict[str, int]:
    counts: dict[str, int] = {}
    for evaluation in edge_evaluations:
        counts[f"edge_state_{evaluation.state.value.lower()}"] = (
            counts.get(f"edge_state_{evaluation.state.value.lower()}", 0) + 1
        )
        if evaluation.confirmed_eligible:
            counts["edge_confirmed_eligible"] = counts.get("edge_confirmed_eligible", 0) + 1
        if evaluation.possibly_eligible:
            counts["edge_possibly_eligible"] = counts.get("edge_possibly_eligible", 0) + 1
    for verdict in verdicts:
        key = f"verdict_{verdict.state.value.lower()}"
        counts[key] = counts.get(key, 0) + 1
    for finding in findings:
        key = f"finding_{finding.state.value.lower()}"
        counts[key] = counts.get(key, 0) + 1
        counts["findings_total"] = counts.get("findings_total", 0) + 1
    return dict(sorted(counts.items()))