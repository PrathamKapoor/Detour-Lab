"""Deterministic candidate generation over the bounded library (MASTER_PROMPT §7.2-7.3).

Responsibilities, and nothing else:

* decide which interventions are **eligible for this search** and say why not
  for the rest (disabled, client-excluded, wrong phase, precondition failed);
* enumerate closed candidate subsets in a documented, deterministic order
  (size classes ascending, lexicographic within a class), where "closed" means
  the ``requires_intervention_ids`` closure is contained in the subset;
* record subsets rejected by *static* constraints (dependency expansion beyond
  the slot limit, mutual exclusions) so the response can show them;
* never touch the network, the database or the analysis engine. Verification
  of a subset happens in :mod:`detour_lab.optimization.verify`.

An unknown precondition kind cannot occur (the contract whitelists them), and
a check that cannot be evaluated fails closed: the intervention is rejected
with the reason attached, never silently kept or dropped.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from detour_lab.domain.contracts import Intervention, InterventionPrecondition, RulePack, Scenario
from detour_lab.evidence.resolver import resolve_attribute
from detour_lab.graph.model import PedestrianGraph
from detour_lab.optimization.model import ExcludedIntervention, SearchConfig
from detour_lab.scenarios.apply import PhaseGraph

__all__ = [
    "DomainPlan",
    "EligibilityResult",
    "assess_eligibility",
    "plan_domain",
]

#: Side lists (blocked subsets, exclusions) are capped so a pathological
#: library cannot balloon the response; the cap is reported when it bites.
SIDE_LIST_CAP = 50


@dataclass(frozen=True, slots=True)
class EligibilityResult:
    eligible: tuple[Intervention, ...]
    excluded: tuple[ExcludedIntervention, ...]
    precondition_rejected: tuple[dict[str, Any], ...]
    ineligible_reasons: dict[str, list[str]]


@dataclass(slots=True)
class DomainPlan:
    """The enumerable domain of this search, honestly bounded."""

    #: Closed subsets in evaluation order.
    subsets: list[tuple[str, ...]] = field(default_factory=list)
    #: Mathematically possible combinations of size 1..max over eligible ids.
    domain_combination_count: int = 0
    dependency_blocked: list[dict[str, Any]] = field(default_factory=list)
    mutually_exclusive_blocked: list[dict[str, Any]] = field(default_factory=list)
    side_lists_capped: bool = False
    #: True when the generator produced every closed subset of the domain.
    enumeration_complete: bool = True


def _declared_phase_state(scenario: Scenario, ref_phase_id: str) -> tuple[set[str], set[str]] | None:
    """The declared closures/temporary set of a phase **other than** the evaluated one.

    For the evaluated phase the materialised phase graph is authoritative; for
    any other phase only the declared plan (phases + ``close_edge`` /
    ``activate_temporary_edge`` edits bound to that phase) can be read without
    materialising it. Returns ``None`` when the phase is not declared.
    """
    ref_phase = scenario.phase_by_id(ref_phase_id)
    if ref_phase is None:
        return None
    closed = set(ref_phase.closed_edge_ids)
    temporary = set(ref_phase.temporary_edge_ids)
    for edit in scenario.edits:
        phases = edit.params.get("phases")
        applies = not phases or ref_phase_id in phases
        if not applies:
            continue
        if edit.op == "close_edge":
            closed.add(edit.target_id)
        if edit.op == "activate_temporary_edge":
            temporary.add(edit.target_id)
    return closed, temporary


def _check_precondition(
    precondition: InterventionPrecondition,
    *,
    scenario: Scenario,
    phase_graph: PhaseGraph,
    rulepack: RulePack,
    phase_id: str,
    as_of: datetime,
) -> tuple[bool, str]:
    """Evaluate one whitelisted check. Returns ``(passed, detail)``."""
    check = precondition.check
    target = precondition.target_id
    graph = phase_graph.graph

    if check == "edge_exists":
        return (graph.has_edge(target), f"edge {target!r} present in the selected phase graph")
    if check == "node_exists":
        return (graph.has_node(target), f"node {target!r} present in the selected phase graph")
    if check == "phase_exists":
        return (scenario.phase_by_id(target) is not None, f"phase {target!r} declared in the scenario")
    if check == "edge_closed_in_phase":
        ref = precondition.phase_id or phase_id
        if ref == phase_id:
            closed = target in phase_graph.closed_edge_ids or f"TMP::{target}" in phase_graph.closed_edge_ids
            return (closed, f"edge {target!r} closed in the selected phase")
        state = _declared_phase_state(scenario, ref)
        if state is None:
            return (False, f"phase {ref!r} is not declared by the scenario")
        return (target in state[0], f"edge {target!r} closed in phase {ref!r} (declared plan)")
    if check == "edge_open_in_phase":
        ref = precondition.phase_id or phase_id
        if ref == phase_id:
            open_now = graph.has_edge(target) and target not in phase_graph.closed_edge_ids
            return (open_now, f"edge {target!r} present and open in the selected phase")
        state = _declared_phase_state(scenario, ref)
        if state is None:
            return (False, f"phase {ref!r} is not declared by the scenario")
        return (target not in state[0], f"edge {target!r} not closed in phase {ref!r} (declared plan)")
    if check == "temporary_edge_active_in_phase":
        ref = precondition.phase_id or phase_id
        if ref == phase_id:
            active = target in phase_graph.active_temporary_edge_ids
            return (active, f"temporary edge {target!r} active in the selected phase")
        state = _declared_phase_state(scenario, ref)
        if state is None:
            return (False, f"phase {ref!r} is not declared by the scenario")
        return (target in state[1], f"temporary edge {target!r} active in phase {ref!r} (declared plan)")
    if check in {"field_known", "field_unknown"}:
        field_name = precondition.field or ""
        spec = rulepack.attributes.get(field_name)
        if spec is None:
            # Fail closed: a precondition about an attribute the rulepack does
            # not interpret cannot be verified.
            return (False, f"field {field_name!r} is not declared by rulepack {rulepack.id!r}")
        # Temporary edges are namespaced ``TMP::`` in materialised graphs; the
        # declared id is accepted for readability of library entries.
        element_id = target
        if not graph.has_edge(element_id) and not graph.has_node(element_id):
            if graph.has_edge(f"TMP::{target}"):
                element_id = f"TMP::{target}"
            else:
                return (False, f"element {target!r} is not present in the selected phase graph")
        resolved = resolve_attribute(
            element_id=element_id,
            field=field_name,
            records=graph.evidence_for(element_id, field_name),
            spec=spec,
            as_of=as_of,
        )
        if check == "field_known":
            return (resolved.known, f"field {field_name!r} on {target!r}: known={resolved.known}")
        return (not resolved.known, f"field {field_name!r} on {target!r}: known={resolved.known}")
    # Unreachable: the contract whitelists checks. Fail closed anyway.
    return (False, f"unevaluable precondition kind {check!r}")


def assess_eligibility(
    *,
    library_interventions: tuple[Intervention, ...],
    scenario: Scenario,
    base_graph: PedestrianGraph,
    phase_graph: PhaseGraph,
    rulepack: RulePack,
    phase_id: str,
    excluded_ids: set[str],
    as_of: datetime,
) -> EligibilityResult:
    """Split the library into eligible and ineligible, with reasons."""
    del base_graph  # kept for symmetry with future checks; phase graph is authoritative here
    eligible: list[Intervention] = []
    excluded: list[ExcludedIntervention] = []
    precondition_rejected: list[dict[str, Any]] = []
    reasons_by_id: dict[str, list[str]] = {}

    for intervention in sorted(library_interventions, key=lambda i: i.id):
        reasons: list[str] = []
        if not intervention.enabled:
            reasons.append("disabled in the bundled library")
        if intervention.id in excluded_ids:
            reasons.append("excluded from this search by the request")
        if intervention.phases and phase_id not in intervention.phases:
            reasons.append(
                f"declared for phase(s) {sorted(intervention.phases)}; not applicable to {phase_id!r}"
            )
        if reasons:
            excluded.append(ExcludedIntervention(intervention_id=intervention.id, reasons=reasons))
            reasons_by_id[intervention.id] = reasons
            continue

        failed: list[str] = []
        for precondition in intervention.preconditions:
            passed, detail = _check_precondition(
                precondition,
                scenario=scenario,
                phase_graph=phase_graph,
                rulepack=rulepack,
                phase_id=phase_id,
                as_of=as_of,
            )
            if not passed:
                failed.append(f"{precondition.description or precondition.check} ({detail})")
        if failed:
            reasons_by_id[intervention.id] = failed
            precondition_rejected.append({"intervention_id": intervention.id, "reasons": failed})
            continue
        eligible.append(intervention)

    return EligibilityResult(
        eligible=tuple(eligible),
        excluded=tuple(excluded),
        precondition_rejected=tuple(precondition_rejected),
        ineligible_reasons=reasons_by_id,
    )


def _closure(
    subset: tuple[str, ...],
    requires_by_id: dict[str, tuple[str, ...]],
) -> tuple[frozenset[str], list[str]]:
    """Transitive requires-closure. Returns ``(closure, missing_ids)``."""
    closure: set[str] = set()
    missing: set[str] = set()
    stack = list(subset)
    while stack:
        current = stack.pop()
        if current in closure:
            continue
        closure.add(current)
        for required in requires_by_id.get(current, ()):
            if required not in requires_by_id:
                missing.add(required)
            elif required not in closure:
                stack.append(required)
    return frozenset(closure), sorted(missing)


def _excluded_pairs(
    closure: frozenset[str],
    excludes_by_id: dict[str, tuple[str, ...]],
) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for member in sorted(closure):
        for excluded in excludes_by_id.get(member, ()):
            if excluded in closure:
                pair = (member, excluded) if member < excluded else (excluded, member)
                if pair not in pairs:
                    pairs.append(pair)
    return pairs


def plan_domain(
    *,
    eligibility: EligibilityResult,
    config: SearchConfig,
    ineligible_reasons: dict[str, list[str]],
) -> DomainPlan:
    """Enumerate the bounded domain of closed subsets, deterministically."""
    interventions = sorted(eligibility.eligible, key=lambda i: i.id)
    ids = [intervention.id for intervention in interventions]
    requires_by_id = {i.id: tuple(sorted(i.requires_intervention_ids)) for i in interventions}
    excludes_by_id = {i.id: tuple(sorted(i.excludes_intervention_ids)) for i in interventions}

    plan = DomainPlan()
    n = len(ids)
    k_max = config.max_interventions
    plan.domain_combination_count = sum(
        _comb(n, k) for k in range(1, k_max + 1)
    )

    def _record(entry_list: list[dict[str, Any]], entry: dict[str, Any]) -> None:
        if len(entry_list) < SIDE_LIST_CAP:
            entry_list.append(entry)
        else:
            plan.side_lists_capped = True

    # Enumerating beyond the evaluation budget is wasted work: the service can
    # never verify more than ``max_candidates`` subsets. When enumeration is cut
    # off, completeness is reported as False so no status can claim optimality.
    plan_budget = config.max_candidates

    for size in range(1, k_max + 1):
        for subset in itertools.combinations(ids, size):
            if len(plan.subsets) >= plan_budget:
                plan.enumeration_complete = False
                return plan
            closure, missing = _closure(subset, requires_by_id)
            if missing:
                _record(
                    plan.dependency_blocked,
                    {
                        "intervention_ids": sorted(subset),
                        "reason": "requires intervention(s) that are not eligible in this search",
                        "missing_or_ineligible": [
                            {"intervention_id": mid, "reasons": ineligible_reasons.get(mid, ["not in library"])}
                            for mid in missing
                        ],
                    },
                )
                continue
            if len(closure) > size:
                if len(closure) > k_max:
                    _record(
                        plan.dependency_blocked,
                        {
                            "intervention_ids": sorted(subset),
                            "reason": (
                                f"dependency expansion needs {len(closure)} interventions, which exceeds "
                                f"max_interventions={k_max}"
                            ),
                            "expanded_to": sorted(closure),
                        },
                    )
                # Otherwise the closure itself will be enumerated at its own size;
                # evaluating the incomplete subset would duplicate it.
                continue
            pairs = _excluded_pairs(closure, excludes_by_id)
            if pairs:
                _record(
                    plan.mutually_exclusive_blocked,
                    {
                        "intervention_ids": sorted(closure),
                        "pairs": [list(pair) for pair in pairs],
                        "reason": "mutually exclusive interventions in one candidate",
                    },
                )
                continue
            plan.subsets.append(tuple(sorted(closure)))

    return plan


def _comb(n: int, k: int) -> int:
    if k < 0 or k > n:
        return 0
    result = 1
    for i in range(1, k + 1):
        result = result * (n - k + i) // i
    return result
