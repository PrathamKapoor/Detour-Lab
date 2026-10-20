"""Research baseline implementations for DETOUR LAB comparative evaluation.

Implements the five comparative baselines required by PRD §13 and Gate 7:
* **Baseline A — Ordinary shortest-path routing**: Conventional unconstrained
  graph routing ignoring accessibility rules. Measures false-safe rate.
* **Baseline B — Static accessibility routing**: Profile-aware routing without
  construction phases. Measures phase-blindness and closure invalidation.
* **Baseline C — Rule-only checklist**: Per-segment compliance without network
  connectivity. Measures disconnection-blindness.
* **Baseline D — Greedy intervention selection**: Greedy single-step heuristic.
  Measures suboptimality and failure on joint multi-intervention dependencies.
* **Baseline E — Inspection queue comparator (B-5)**: Decision-blocking priority
  ordering vs naive first-listed vs random vs highest-uncertainty ordering.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from detour_lab.analysis.run import run_analysis
from detour_lab.domain.contracts import (
    MobilityProfile,
    RulePack,
    Scenario,
)
from detour_lab.domain.enums import VerdictState
from detour_lab.evidence.model import EvidenceCriticality
from detour_lab.evidence.queue import derive_evidence_queue
from detour_lab.graph.model import PedestrianGraph
from detour_lab.graph.routing import shortest_path
from detour_lab.optimization import run_search
from detour_lab.optimization.library import InterventionLibrary
from detour_lab.optimization.model import SearchConfig
from detour_lab.persistence.repository import Repository
from detour_lab.rules.engine import evaluate_graph
from detour_lab.rules.profiles import profile_by_id
from detour_lab.scenarios.apply import build_phase_graph

__all__ = [
    "BaselineAResult",
    "BaselineBResult",
    "BaselineCResult",
    "BaselineDResult",
    "BaselineEResult",
    "run_baseline_a_shortest_path",
    "run_baseline_b_static_routing",
    "run_baseline_c_rule_checklist",
    "run_baseline_d_greedy_optimizer",
    "run_baseline_e_inspection_ordering",
]


# ---------------------------------------------------------------------------
# Baseline A: Ordinary Shortest-Path Routing
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BaselineAResult:
    origin_id: str
    destination_id: str
    path_found: bool
    path_edge_ids: tuple[str, ...]
    path_distance_m: float
    has_modeled_violation: bool
    has_unknown_evidence: bool
    failing_edge_ids: tuple[str, ...]
    unknown_edge_ids: tuple[str, ...]
    detour_lab_confirmed: bool
    is_false_safe: bool
    explanation: str


def run_baseline_a_shortest_path(
    *,
    graph: PedestrianGraph,
    origin_id: str,
    destination_id: str,
    profile: MobilityProfile,
    rulepack: RulePack,
    as_of: datetime,
) -> BaselineAResult:
    """Conventional Dijkstra shortest-path routing ignoring accessibility constraints.

    Evaluates the resulting path against authoritative rule verdicts to detect
    false-safe routes (PRD §13 H1).
    """
    # Baseline A allows ALL non-closed edges in the network
    all_non_closed = frozenset(e.id for e in graph.edges if e.id not in graph.closed_edge_ids)

    path = shortest_path(
        graph,
        allowed_edge_ids=all_non_closed,
        source_node_id=origin_id,
        target_node_id=destination_id,
        weight_fn=lambda e: float(e.length_m),
    )

    if path is None:
        return BaselineAResult(
            origin_id=origin_id,
            destination_id=destination_id,
            path_found=False,
            path_edge_ids=(),
            path_distance_m=0.0,
            has_modeled_violation=False,
            has_unknown_evidence=False,
            failing_edge_ids=(),
            unknown_edge_ids=(),
            detour_lab_confirmed=False,
            is_false_safe=False,
            explanation="No geometric path exists between origin and destination.",
        )

    # Authoritative evaluation of edges in the graph
    eval_result = evaluate_graph(
        graph=graph,
        rulepack=rulepack,
        profile_id=profile.id,
        phase_id="bench-p1",
        as_of=as_of,
    )
    edge_states = eval_result.edge_states

    failing = [eid for eid in path.edge_ids if edge_states.get(eid) == VerdictState.FAIL]
    unknown = [eid for eid in path.edge_ids if edge_states.get(eid) == VerdictState.UNKNOWN]

    has_violation = len(failing) > 0
    has_unknown = len(unknown) > 0
    # False-safe: Baseline A reports reachable, but route violates modeled accessibility checks
    is_false_safe = has_violation

    # Compare with authoritative confirmed reachability
    confirmed_edges = frozenset(
        eid for eid in all_non_closed if edge_states.get(eid) == VerdictState.PASS
    )
    detour_lab_path = shortest_path(
        graph,
        allowed_edge_ids=confirmed_edges,
        source_node_id=origin_id,
        target_node_id=destination_id,
        weight_fn=lambda e: float(e.length_m),
    )
    detour_lab_confirmed = detour_lab_path is not None

    if is_false_safe:
        explanation = (
            f"Baseline A found an unconstrained path of {path.distance_m:.1f} m, but it crosses "
            f"{len(failing)} edge(s) with modeled accessibility violations ({', '.join(failing)})."
        )
    elif has_unknown:
        explanation = (
            f"Baseline A found a path of {path.distance_m:.1f} m, but it crosses "
            f"{len(unknown)} edge(s) with unresolved evidence ({', '.join(unknown)})."
        )
    else:
        explanation = f"Baseline A path of {path.distance_m:.1f} m satisfies modeled constraints."

    return BaselineAResult(
        origin_id=origin_id,
        destination_id=destination_id,
        path_found=True,
        path_edge_ids=path.edge_ids,
        path_distance_m=path.distance_m,
        has_modeled_violation=has_violation,
        has_unknown_evidence=has_unknown,
        failing_edge_ids=tuple(failing),
        unknown_edge_ids=tuple(unknown),
        detour_lab_confirmed=detour_lab_confirmed,
        is_false_safe=is_false_safe,
        explanation=explanation,
    )


# ---------------------------------------------------------------------------
# Baseline B: Static Accessibility Routing (No Construction Phases)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BaselineBResult:
    origin_id: str
    destination_id: str
    phase_id: str
    static_confirmed: bool
    static_distance_m: float | None
    phased_confirmed: bool
    phased_distance_m: float | None
    is_false_safe_closure: bool
    is_missed_detour: bool
    explanation: str


def run_baseline_b_static_routing(
    *,
    base_graph: PedestrianGraph,
    scenario: Scenario,
    target_phase_id: str,
    origin_id: str,
    destination_id: str,
    profile: MobilityProfile,
    rulepack: RulePack,
    as_of: datetime,
) -> BaselineBResult:
    """Profile-aware routing on the static unphased base graph.

    Compares against authoritative phase-specific analysis to demonstrate
    phase-invalidation errors (closures active in phase; temporary detours).
    """
    # 1. Static evaluation on base graph (ignoring phases & temporary detours)
    static_eval = evaluate_graph(
        graph=base_graph,
        rulepack=rulepack,
        profile_id=profile.id,
        phase_id="static",
        as_of=as_of,
    )
    static_confirmed_edges = frozenset(
        e.id for e in base_graph.edges
        if e.id not in base_graph.closed_edge_ids
        and static_eval.edge_states.get(e.id) == VerdictState.PASS
    )
    static_path = shortest_path(
        base_graph,
        allowed_edge_ids=static_confirmed_edges,
        source_node_id=origin_id,
        target_node_id=destination_id,
        weight_fn=lambda e: float(e.length_m),
    )
    static_confirmed = static_path is not None
    static_dist = static_path.distance_m if static_path else None

    # 2. Authoritative phase-specific analysis
    phase_graph_obj = build_phase_graph(base_graph, scenario, target_phase_id)
    phase_graph = phase_graph_obj.graph
    phased_eval = evaluate_graph(
        graph=phase_graph,
        rulepack=rulepack,
        profile_id=profile.id,
        phase_id=target_phase_id,
        as_of=as_of,
    )
    phased_confirmed_edges = frozenset(
        e.id for e in phase_graph.edges
        if e.id not in phase_graph.closed_edge_ids
        and phased_eval.edge_states.get(e.id) == VerdictState.PASS
    )
    phased_path = shortest_path(
        phase_graph,
        allowed_edge_ids=phased_confirmed_edges,
        source_node_id=origin_id,
        target_node_id=destination_id,
        weight_fn=lambda e: float(e.length_m),
    )
    phased_confirmed = phased_path is not None
    phased_dist = phased_path.distance_m if phased_path else None

    # Error modes:
    # False safe: static says open/confirmed, but construction phase closed it
    is_false_safe_closure = static_confirmed and not phased_confirmed
    # Missed detour: static says disconnected, but phase introduced temporary detour
    is_missed_detour = not static_confirmed and phased_confirmed

    if is_false_safe_closure:
        explanation = (
            f"Baseline B (static) claims {origin_id}->{destination_id} is accessible "
            f"({static_dist:.1f} m), but Phase {target_phase_id} closures sever this path."
        )
    elif is_missed_detour:
        explanation = (
            f"Baseline B (static) claims {origin_id}->{destination_id} is disconnected, "
            f"failing to detect the Phase {target_phase_id} temporary detour ({phased_dist:.1f} m)."
        )
    else:
        explanation = f"Baseline B and phased analysis agree: confirmed={phased_confirmed}."

    return BaselineBResult(
        origin_id=origin_id,
        destination_id=destination_id,
        phase_id=target_phase_id,
        static_confirmed=static_confirmed,
        static_distance_m=static_dist,
        phased_confirmed=phased_confirmed,
        phased_distance_m=phased_dist,
        is_false_safe_closure=is_false_safe_closure,
        is_missed_detour=is_missed_detour,
        explanation=explanation,
    )


# ---------------------------------------------------------------------------
# Baseline C: Rule-Only Checklist (Without Network Connectivity)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BaselineCResult:
    total_edges: int
    pass_edges: int
    fail_edges: int
    unknown_edges: int
    segment_compliance_rate: float
    origin_id: str
    destination_id: str
    end_to_end_connected: bool
    is_disconnection_blind: bool
    explanation: str


def run_baseline_c_rule_checklist(
    *,
    graph: PedestrianGraph,
    origin_id: str,
    destination_id: str,
    profile: MobilityProfile,
    rulepack: RulePack,
    as_of: datetime,
) -> BaselineCResult:
    """Per-segment compliance audit without network graph connectivity.

    Demonstrates disconnection-blindness: high per-segment pass rate masking
    zero end-to-end accessibility between key destinations.
    """
    eval_result = evaluate_graph(
        graph=graph,
        rulepack=rulepack,
        profile_id=profile.id,
        phase_id="checklist",
        as_of=as_of,
    )
    edge_states = eval_result.edge_states

    active_edges = [e for e in graph.edges if e.id not in graph.closed_edge_ids]
    total = len(active_edges)
    passes = sum(1 for e in active_edges if edge_states.get(e.id) == VerdictState.PASS)
    fails = sum(1 for e in active_edges if edge_states.get(e.id) == VerdictState.FAIL)
    unknowns = sum(1 for e in active_edges if edge_states.get(e.id) == VerdictState.UNKNOWN)

    compliance_rate = passes / total if total > 0 else 0.0

    # True end-to-end reachability
    confirmed_edges = frozenset(
        e.id for e in active_edges if edge_states.get(e.id) == VerdictState.PASS
    )
    path = shortest_path(
        graph,
        allowed_edge_ids=confirmed_edges,
        source_node_id=origin_id,
        target_node_id=destination_id,
        weight_fn=lambda e: float(e.length_m),
    )
    end_to_end = path is not None

    # Disconnection blindness: high segment compliance (e.g. >= 70%) but OD disconnected
    is_blind = compliance_rate >= 0.70 and not end_to_end

    if is_blind:
        explanation = (
            f"Baseline C reports high segment compliance ({compliance_rate:.1%}), "
            f"yet {origin_id}->{destination_id} is completely disconnected end-to-end."
        )
    else:
        explanation = (
            f"Segment compliance {compliance_rate:.1%}; end-to-end connected: {end_to_end}."
        )

    return BaselineCResult(
        total_edges=total,
        pass_edges=passes,
        fail_edges=fails,
        unknown_edges=unknowns,
        segment_compliance_rate=round(compliance_rate, 4),
        origin_id=origin_id,
        destination_id=destination_id,
        end_to_end_connected=end_to_end,
        is_disconnection_blind=is_blind,
        explanation=explanation,
    )


# ---------------------------------------------------------------------------
# Baseline D: Greedy Intervention Optimizer
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BaselineDResult:
    strategy: str
    greedy_winner_intervention_ids: tuple[str, ...]
    greedy_restored_od_count: int
    detour_lab_winner_intervention_ids: tuple[str, ...]
    detour_lab_restored_od_count: int
    greedy_suboptimal_or_failed: bool
    explanation: str


def run_baseline_d_greedy_optimizer(
    *,
    repository: Repository,
    library: InterventionLibrary,
    scenario_id: str,
    phase_id: str,
    profile_ids: list[str] | None,
    evaluation_instant: datetime,
    max_steps: int = 2,
) -> BaselineDResult:
    """Greedy single-step intervention optimizer vs DETOUR LAB joint search.

    Demonstrates failure on multi-step dependencies where no single intervention
    restores connectivity alone.
    """
    # 1. DETOUR LAB joint search (max_interventions = max_steps)
    dl_search = run_search(
        repository=repository,
        library=library,
        scenario_id=scenario_id,
        phase_id=phase_id,
        profile_ids=profile_ids,
        evaluation_instant=evaluation_instant,
        config=SearchConfig(
            max_interventions=max_steps,
            max_candidates=100,
            max_duration_ms=60_000,
        ),
    )
    dl_winner = dl_search.candidates[0] if dl_search.candidates else None
    dl_winner_ids = tuple(dl_winner.intervention_ids) if dl_winner else ()
    dl_restored = len(dl_winner.restored_all_profiles) if dl_winner else 0

    # 2. Greedy search: evaluate singletons first
    singles_search = run_search(
        repository=repository,
        library=library,
        scenario_id=scenario_id,
        phase_id=phase_id,
        profile_ids=profile_ids,
        evaluation_instant=evaluation_instant,
        config=SearchConfig(
            max_interventions=1,
            max_candidates=100,
            max_duration_ms=60_000,
        ),
    )
    valid_singles = [
        c for c in singles_search.candidates
        if c.classification != "rejected" and len(c.restored_all_profiles) > 0
    ]

    greedy_ids: list[str] = []
    greedy_restored = 0

    if not valid_singles:
        # Greedy finds no single intervention that restores any OD pair
        # Greedy stops or selects a 0-restoration intervention
        greedy_ids = []
        greedy_restored = 0
    else:
        # Greedy picks the best single intervention
        best_single = valid_singles[0]
        greedy_ids = list(best_single.intervention_ids)
        greedy_restored = len(best_single.restored_all_profiles)

        # If max_steps > 1, evaluate extensions containing the winner
        if max_steps > 1:
            step2_candidates = [
                c for c in dl_search.candidates
                if len(c.intervention_ids) == 2
                and greedy_ids[0] in c.intervention_ids
                and c.classification != "rejected"
            ]
            if step2_candidates:
                best_step2 = step2_candidates[0]
                if len(best_step2.restored_all_profiles) >= greedy_restored:
                    greedy_ids = list(best_step2.intervention_ids)
                    greedy_restored = len(best_step2.restored_all_profiles)

    is_suboptimal = (greedy_restored < dl_restored) or (not greedy_ids and dl_winner_ids)

    if is_suboptimal:
        explanation = (
            f"Greedy optimizer restored {greedy_restored} OD pair(s) (ids: {greedy_ids}), "
            f"while DETOUR LAB joint search restored {dl_restored} OD pair(s) "
            f"(ids: {list(dl_winner_ids)})."
        )
    else:
        explanation = f"Greedy and joint search both achieved {greedy_restored} restorations."

    return BaselineDResult(
        strategy="greedy_single_step_extension",
        greedy_winner_intervention_ids=tuple(greedy_ids),
        greedy_restored_od_count=greedy_restored,
        detour_lab_winner_intervention_ids=dl_winner_ids,
        detour_lab_restored_od_count=dl_restored,
        greedy_suboptimal_or_failed=is_suboptimal,
        explanation=explanation,
    )


# ---------------------------------------------------------------------------
# Baseline E: Inspection Queue Ordering Comparator (B-5)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BaselineEResult:
    detour_lab_inspections: int
    naive_first_listed_inspections: int
    random_average_inspections: float
    highest_uncertainty_inspections: int
    efficiency_gain_over_naive: float
    efficiency_gain_over_random: float
    explanation: str


def run_baseline_e_inspection_ordering(
    *,
    base_graph: PedestrianGraph,
    scenario: Scenario,
    phase_id: str,
    profile_ids: list[str],
    target_od: tuple[str, str],
    rulepack: RulePack,
    as_of: datetime,
    random_trials: int = 25,
) -> BaselineEResult:
    """Benchmark comparing DETOUR LAB's decision-blocking priority queue (B-5)

    Compares against:
    1. Naive first-listed (insertion/natural order)
    2. Random inspection order (averaged over permutations)
    3. Highest-uncertainty (elements with most missing fields first)
    """
    results = {}
    for pid in profile_ids:
        prof = profile_by_id(pid)
        results[(phase_id, pid)] = run_analysis(
            base_graph=base_graph,
            scenario=scenario,
            phase_id=phase_id,
            profile_id=pid,
            rulepack=rulepack,
            profile=prof,
            as_of=as_of,
        )

    queue = derive_evidence_queue(
        graph=base_graph,
        scenario=scenario,
        rulepack=rulepack,
        results_by_phase_profile=results,
        phase_ids=[phase_id],
        profile_ids=list(profile_ids),
        as_of=as_of,
        project_id="bench_project",
    )

    issues = queue.issues
    if not issues:
        return BaselineEResult(0, 0, 0.0, 0, 0.0, 0.0, "Queue has no unresolved issues.")

    # Ground-truth: identify which issue(s) are decision-blocking for target OD
    target_origin, target_dest = target_od
    blocking_issue_ids = {
        issue.issue_id
        for issue in issues
        if issue.criticality == EvidenceCriticality.DECISION_BLOCKING
        and any(
            p.origin_id == target_origin and p.destination_id == target_dest
            for p in issue.od_pairs
        )
    }

    # If no specific blocker identified, fall back to any decision-relevant issue for target
    if not blocking_issue_ids:
        blocking_issue_ids = {
            issue.issue_id
            for issue in issues
            if any(
                p.origin_id == target_origin and p.destination_id == target_dest
                for p in issue.od_pairs
            )
        }
    if not blocking_issue_ids:
        blocking_issue_ids = {issues[0].issue_id}

    def _steps_until_blocking(order: Sequence[str]) -> int:
        for idx, iid in enumerate(order, start=1):
            if iid in blocking_issue_ids:
                return idx
        return len(order)

    # 1. DETOUR LAB order: queue's native ordering
    dl_order = [issue.issue_id for issue in issues]
    dl_steps = _steps_until_blocking(dl_order)

    # 2. Naive first-listed: sorted by element_id and attribute (natural inventory order)
    naive_order = [
        issue.issue_id for issue in sorted(issues, key=lambda i: (i.element_id, i.attribute))
    ]
    naive_steps = _steps_until_blocking(naive_order)

    # 3. Random ordering over trials
    random.seed(42)
    random_steps_total = 0
    all_ids = list(dl_order)
    for _ in range(random_trials):
        shuffled = list(all_ids)
        random.shuffle(shuffled)
        random_steps_total += _steps_until_blocking(shuffled)
    random_avg = random_steps_total / random_trials

    # 4. Highest-uncertainty: sort by count of unresolved attributes per element
    element_counts: dict[str, int] = {}
    for issue in issues:
        element_counts[issue.element_id] = element_counts.get(issue.element_id, 0) + 1
    highest_unc_order = [
        issue.issue_id for issue in sorted(
            issues, key=lambda i: (-element_counts[i.element_id], i.element_id, i.attribute)
        )
    ]
    highest_unc_steps = _steps_until_blocking(highest_unc_order)

    gain_over_naive = (naive_steps - dl_steps) / naive_steps if naive_steps > 0 else 0.0
    gain_over_random = (random_avg - dl_steps) / random_avg if random_avg > 0 else 0.0

    explanation = (
        f"DETOUR LAB prioritized order resolved target reachability in {dl_steps} inspection(s), "
        f"versus {naive_steps} for naive first-listed, {random_avg:.1f} for random, "
        f"and {highest_unc_steps} for highest-uncertainty."
    )

    return BaselineEResult(
        detour_lab_inspections=dl_steps,
        naive_first_listed_inspections=naive_steps,
        random_average_inspections=round(random_avg, 2),
        highest_uncertainty_inspections=highest_unc_steps,
        efficiency_gain_over_naive=round(gain_over_naive, 4),
        efficiency_gain_over_random=round(gain_over_random, 4),
        explanation=explanation,
    )
