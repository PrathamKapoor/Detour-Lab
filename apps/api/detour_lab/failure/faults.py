"""Fault validation and the closed kind-to-operation mapping (G6-06).

This module is the only place that decides *how* a fault is realised. Every
branch is an explicit ``match`` on :class:`FaultKind`; nothing here interprets a
user-supplied string as code, imports a module by name, or evaluates an
expression.

The mapping is deliberately small. A fault kind exists only when the mutation it
describes can be expressed as an operation the authoritative domain already
performs:

======================  ==========================================================
FaultKind               Realised as
======================  ==========================================================
``EDGE_CLOSURE``        a ``close_edge`` graph edit scoped to the fault's phases
``PATH_OBSTRUCTION``    the same closure, labelled as a modelled obstruction
``TEMPORARY_CONNECTION_`` a declared phase-set change that deactivates the
``LOSS``                temporary edge for the fault's phases only
``EVIDENCE_REMOVAL``    records removed from an isolated evidence registry
``CONFLICTING_``        an explicitly synthetic record appended to that registry
``OBSERVATION``         (the real resolver decides the outcome)
``UNSUPPORTED_UNIT_``   the same, in a unit the rulepack does not accept
``OBSERVATION``
``EVIDENCE_EXPIRATION`` an explicit evaluation instant for freshness judgement
======================  ==========================================================

Not a kind, and why
-------------------
The Gate 6 brief lists ten failure conditions. Two of them are **scopes** of
these kinds rather than new mutation primitives, and the mapping is documented
rather than faked:

* *multi-phase interruption* is the ``phase_ids`` scope of any fault. It needs
  no new operation; it needs the guarantee that a fault touches only its own
  phases, which :mod:`detour_lab.failure.engine` enforces by materialising each
  phase from its own independent snapshot.
* *profile-specific failure* needs no new operation either. An experiment
  always evaluates every selected profile against the same isolated state, so a
  divergence between profiles emerges from the real rulepack rather than being
  manufactured.
* *optimisation-candidate stress test* is the same machinery pointed at a
  promoted branch, which is an ordinary immutable scenario revision.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from detour_lab.domain.contracts import RulePack, Scenario
from detour_lab.domain.units import parse_timestamp
from detour_lab.evidence.resolver import resolve_attribute
from detour_lab.failure.model import EVIDENCE_MUTATION_KINDS, FaultDefinition, FaultKind, FaultObservation
from detour_lab.graph.model import PedestrianGraph
from detour_lab.scenarios.apply import build_phase_graph

__all__ = [
    "FAULT_KIND_DESCRIPTIONS",
    "FAULT_MUTATION_NOTES",
    "FaultValidationError",
    "fault_applicability",
    "validate_faults",
]

#: Temporary edges are materialised with this id prefix by ``build_phase_graph``.
_TEMPORARY_PREFIX = "TMP::"


FAULT_KIND_DESCRIPTIONS: dict[str, str] = {
    FaultKind.EDGE_CLOSURE.value: (
        "Close an existing eligible edge for the fault's phases. The closure is a real phase-graph "
        "operation: the edge stops being traversable and the engine re-evaluates the network."
    ),
    FaultKind.PATH_OBSTRUCTION.value: (
        "Represent a modelled obstruction on a path. The domain models edge availability only, so "
        "this is applied as a closure carrying an obstruction label. No physical obstruction is "
        "simulated and no claim is made about its nature or severity."
    ),
    FaultKind.TEMPORARY_CONNECTION_LOSS.value: (
        "Deactivate a scenario-declared temporary connection in the fault's phases. This is a real "
        "graph change: the temporary edge does not exist in the affected phase graphs."
    ),
    FaultKind.EVIDENCE_REMOVAL.value: (
        "Mask existing observations inside the experiment's isolated evidence context only. The "
        "source evidence store is never modified and nothing is deleted from the project."
    ),
    FaultKind.CONFLICTING_OBSERVATION.value: (
        "Introduce an explicitly synthetic, contradictory observation. The real evidence resolver "
        "decides the resulting condition; nothing forces UNKNOWN for presentation purposes."
    ),
    FaultKind.EVIDENCE_EXPIRATION.value: (
        "Evaluate the isolated analysis at an explicit later instant so the rulepack's own freshness "
        "policy is exercised. Recorded timestamps are never rewritten and the wall clock is never "
        "consulted, so the result is reproducible."
    ),
    FaultKind.UNSUPPORTED_UNIT_OBSERVATION.value: (
        "Introduce an explicitly synthetic observation whose unit the rulepack does not accept for "
        "that attribute, and let the real unit conversion layer reject it."
    ),
}

FAULT_MUTATION_NOTES: dict[str, str] = {
    FaultKind.PATH_OBSTRUCTION.value: (
        "Modelled as edge unavailability. The domain has no representation for a physical "
        "obstruction, its footprint, or its effect on clear width."
    ),
    FaultKind.EVIDENCE_REMOVAL.value: (
        "The masking exists only inside the experiment. The persisted evidence records are "
        "unchanged and a stored experiment can be re-verified against them."
    ),
}


class FaultValidationError(ValueError):
    """A fault cannot be represented safely. Carries a stable machine code."""

    def __init__(self, message: str, *, code: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}


def _declared_temporary_ids(scenario: Scenario) -> set[str]:
    return {t.id for t in scenario.temporary_edges}


def _parse_instant(value: str, *, field: str) -> datetime:
    parsed = parse_timestamp(value, field=field)
    if parsed.tzinfo is None:  # pragma: no cover - parse_timestamp always returns aware values
        raise FaultValidationError(
            f"{field} must include a timezone offset",
            code="INVALID_FAULT",
        )
    return parsed.astimezone(UTC)


def _resolve_phases(fault: FaultDefinition, scenario: Scenario, default_phases: Sequence[str]) -> list[str]:
    """Resolve the fault's phase scope, rejecting unknown phases."""
    if not fault.phase_ids:
        return sorted(default_phases)
    unknown = [p for p in fault.phase_ids if scenario.phase_by_id(p) is None]
    if unknown:
        raise FaultValidationError(
            f"fault {fault.fault_id} references phase(s) {unknown} that scenario "
            f"{scenario.id!r} does not declare",
            code="INVALID_PHASE",
            details={"unknown_phase_ids": unknown, "declared_phase_ids": [p.id for p in scenario.ordered_phases()]},
        )
    return sorted(fault.phase_ids)


def validate_faults(
    *,
    faults: Sequence[FaultDefinition],
    graph: PedestrianGraph,
    scenario: Scenario,
    rulepack: RulePack,
    default_phases: Sequence[str],
    max_faults: int,
    max_targets: int,
) -> list[FaultDefinition]:
    """Validate every fault against the real source state.

    Raises :class:`FaultValidationError` with a precise code on the first fault
    that cannot be represented. Returning early matters: an unrepresentable
    fault must never reach the analysis stage.
    """
    if not faults:
        raise FaultValidationError(
            "at least one fault definition is required",
            code="INVALID_FAULT",
            details={"max_faults_per_request": max_faults},
        )
    if len(faults) > max_faults:
        raise FaultValidationError(
            f"{len(faults)} fault(s) requested but at most {max_faults} are accepted per request",
            code="FAULT_LIMIT_EXCEEDED",
            details={"requested": len(faults), "max_faults_per_request": max_faults},
        )

    seen: set[str] = set()
    declared_temporary = _declared_temporary_ids(scenario)
    graph_edges = {e.id for e in graph.edges}
    graph_nodes = {n.id for n in graph.nodes}

    validated: list[FaultDefinition] = []
    for fault in faults:
        if fault.semantic_hash in seen:
            raise FaultValidationError(
                f"fault {fault.fault_id} duplicates an earlier fault definition "
                f"(semantic hash {fault.semantic_hash})",
                code="DUPLICATE_FAULT",
                details={"semantic_hash": fault.semantic_hash},
            )
        seen.add(fault.semantic_hash)

        if len(fault.target_ids) > max_targets:
            raise FaultValidationError(
                f"fault {fault.fault_id} names {len(fault.target_ids)} targets but at most "
                f"{max_targets} are accepted",
                code="FAULT_LIMIT_EXCEEDED",
                details={"requested": len(fault.target_ids), "max_target_ids_per_fault": max_targets},
            )

        phases = _resolve_phases(fault, scenario, default_phases)
        kind = fault.kind

        # ---- graph mutations -------------------------------------------------
        if kind in (FaultKind.EDGE_CLOSURE, FaultKind.PATH_OBSTRUCTION):
            if not fault.target_ids:
                raise FaultValidationError(
                    f"fault {fault.fault_id} ({kind.value}) must name at least one edge id",
                    code="INVALID_FAULT",
                )
            for edge_id in fault.target_ids:
                if edge_id not in graph_edges:
                    raise FaultValidationError(
                        f"fault {fault.fault_id} targets edge {edge_id!r}, which does not exist in "
                        f"graph version {graph.version.id!r}",
                        code="INVALID_EDGE_REFERENCE",
                        details={"edge_id": edge_id},
                    )
            already_closed = _edges_closed_in(graph, scenario, fault.target_ids, phases)
            if already_closed:
                raise FaultValidationError(
                    f"fault {fault.fault_id} would close edge(s) {already_closed} that are already "
                    "closed in every targeted phase, so the condition is already present and the fault "
                    "would be a no-op",
                    code="NO_OP_FAULT",
                    details={"edge_ids": already_closed, "phase_ids": phases},
                )

        elif kind is FaultKind.TEMPORARY_CONNECTION_LOSS:
            if not fault.target_ids:
                raise FaultValidationError(
                    f"fault {fault.fault_id} must name at least one temporary connection id",
                    code="INVALID_FAULT",
                )
            for temp_id in fault.target_ids:
                if temp_id not in declared_temporary:
                    raise FaultValidationError(
                        f"fault {fault.fault_id} targets temporary connection {temp_id!r}, which "
                        f"scenario {scenario.id!r} does not declare",
                        code="INVALID_EDGE_REFERENCE",
                        details={
                            "temporary_edge_id": temp_id,
                            "declared_temporary_edge_ids": sorted(declared_temporary),
                        },
                    )
            active_any = _temporary_active_in(scenario, fault.target_ids, phases)
            if not active_any:
                raise FaultValidationError(
                    f"fault {fault.fault_id} would deactivate connection(s) {fault.target_ids} that are "
                    f"not active in any targeted phase {phases}, so the fault would be a no-op",
                    code="NO_OP_FAULT",
                    details={"temporary_edge_ids": fault.target_ids, "phase_ids": phases},
                )

        # ---- evidence mutations ----------------------------------------------
        elif kind is FaultKind.EVIDENCE_REMOVAL:
            if not fault.target_ids:
                raise FaultValidationError(
                    f"fault {fault.fault_id} must name at least one element id whose observation is masked",
                    code="INVALID_FAULT",
                )
            observation = _require_observation(fault, kind)
            for element_id in fault.target_ids:
                if element_id not in graph_edges and element_id not in graph_nodes:
                    raise FaultValidationError(
                        f"fault {fault.fault_id} targets element {element_id!r}, which is neither an "
                        "edge nor a node in the source graph",
                        code="INVALID_ELEMENT_REFERENCE",
                        details={"element_id": element_id},
                    )
                if observation.field not in rulepack.attributes:
                    raise FaultValidationError(
                        f"fault {fault.fault_id} masks attribute {observation.field!r}, which the "
                        f"rulepack {rulepack.id!r} does not declare",
                        code="UNKNOWN_ATTRIBUTE",
                        details={"field": observation.field},
                    )
                if not graph.evidence_registry.for_field(element_id, observation.field):
                    raise FaultValidationError(
                        f"fault {fault.fault_id} masks {observation.field!r} on {element_id!r}, which "
                        "has no eligible observation; there is nothing to mask",
                        code="INVALID_ELEMENT_REFERENCE",
                        details={"element_id": element_id, "field": observation.field},
                    )

        elif kind in EVIDENCE_MUTATION_KINDS:
            observation = _require_observation(fault, kind)
            if not fault.target_ids:
                raise FaultValidationError(
                    f"fault {fault.fault_id} must name at least one element id to receive the "
                    "synthetic observation",
                    code="INVALID_FAULT",
                )
            spec = rulepack.attributes.get(observation.field)
            if spec is None:
                raise FaultValidationError(
                    f"fault {fault.fault_id} introduces an observation for {observation.field!r}, "
                    f"which the rulepack {rulepack.id!r} does not declare",
                    code="UNKNOWN_ATTRIBUTE",
                    details={"field": observation.field},
                )
            for element_id in fault.target_ids:
                if element_id not in graph_edges and element_id not in graph_nodes:
                    raise FaultValidationError(
                        f"fault {fault.fault_id} targets element {element_id!r}, which is neither an "
                        "edge nor a node in the source graph",
                        code="INVALID_ELEMENT_REFERENCE",
                        details={"element_id": element_id},
                    )
            if kind is FaultKind.UNSUPPORTED_UNIT_OBSERVATION:
                if observation.unit is None or observation.unit.strip() == "":
                    raise FaultValidationError(
                        f"fault {fault.fault_id} must supply an explicit unit to exercise the "
                        "unsupported-unit path",
                        code="INVALID_FAULT",
                    )
                accepted = {u.strip().lower() for u in spec.accepted_units}
                if observation.unit.strip().lower() in accepted:
                    raise FaultValidationError(
                        f"fault {fault.fault_id} uses unit {observation.unit!r}, which the rulepack "
                        f"already accepts for {observation.field!r}; the unsupported-unit path would "
                        "not be exercised",
                        code="NO_OP_FAULT",
                        details={"field": observation.field, "unit": observation.unit},
                    )
            else:  # CONFLICTING_OBSERVATION
                if observation.value is None:
                    raise FaultValidationError(
                        f"fault {fault.fault_id} must supply an explicit value to create a conflict",
                        code="INVALID_FAULT",
                    )
                _require_genuine_conflict(
                    graph=graph, rulepack=rulepack, target_ids=fault.target_ids, observation=observation
                )

        elif kind is FaultKind.EVIDENCE_EXPIRATION:
            if not fault.evaluation_instant:
                raise FaultValidationError(
                    f"fault {fault.fault_id} must supply an explicit ``evaluation_instant``; the "
                    "resolver judges staleness at a stated time and must never read the wall clock",
                    code="INVALID_FAULT",
                )
            _parse_instant(fault.evaluation_instant, field="evaluation_instant")

        validated.append(
            fault.model_copy(update={"phase_ids": phases, "fault_id": fault.fault_id, "semantic_hash": ""})
        )

    # ``model_copy`` skips validators, so the semantic hash is recomputed here
    # from the resolved phase scope: a fault's identity includes the phases it
    # actually applies to, not just the ones the caller guessed.
    return [f.model_copy(update={"semantic_hash": f.semantic_body_hash()}) for f in validated]


def _require_observation(fault: FaultDefinition, kind: FaultKind) -> FaultObservation:
    if fault.observation is None:
        raise FaultValidationError(
            f"fault {fault.fault_id} ({kind.value}) requires an explicit observation block",
            code="INVALID_FAULT",
        )
    return fault.observation


def _edges_closed_in(
    graph: PedestrianGraph, scenario: Scenario, edge_ids: Sequence[str], phases: Sequence[str]
) -> list[str]:
    """Edges already closed in every targeted phase (so closing them is a no-op)."""
    closed_in_all: list[str] = []
    for edge_id in edge_ids:
        closed_everywhere = True
        for phase_id in phases:
            try:
                phase_graph = build_phase_graph(graph, scenario, phase_id)
            except Exception:  # pragma: no cover - an unbuildable phase is rejected upstream
                closed_everywhere = False
                break
            if edge_id not in phase_graph.closed_edge_ids:
                closed_everywhere = False
                break
        if closed_everywhere:
            closed_in_all.append(edge_id)
    return closed_in_all


def _temporary_active_in(scenario: Scenario, temp_ids: Sequence[str], phases: Sequence[str]) -> list[str]:
    """Temporary connections declared as active in at least one targeted phase."""
    active: list[str] = []
    for temp_id in temp_ids:
        for phase_id in phases:
            phase = scenario.phase_by_id(phase_id)
            if phase is not None and temp_id in phase.temporary_edge_ids:
                active.append(temp_id)
                break
    return active


def _require_genuine_conflict(
    *,
    graph: PedestrianGraph,
    rulepack: RulePack,
    target_ids: Sequence[str],
    observation: FaultObservation,
) -> None:
    """Reject a "conflict" whose value would actually agree with the record.

    A duplicate that happens to match is not a conflict; accepting it would let
    a suite claim it exercised the conflicting path when it did not.
    """
    spec = rulepack.attributes[observation.field]
    for element_id in target_ids:
        existing = list(graph.evidence_registry.for_field(element_id, observation.field))
        if not existing:
            raise FaultValidationError(
                f"fault introduces a conflicting observation for {element_id!r}, which has no existing "
                f"{observation.field!r} observation to disagree with",
                code="NO_OP_FAULT",
                details={"element_id": element_id, "field": observation.field},
            )
        probe = _probe_records(existing, observation, element_id)
        before = resolve_attribute(element_id=element_id, field=observation.field, records=existing, spec=spec)
        after = resolve_attribute(element_id=element_id, field=observation.field, records=probe, spec=spec)
        if before.known and after.known and before.value == after.value:
            raise FaultValidationError(
                f"fault's synthetic value {observation.value!r} does not disagree with the existing "
                f"{observation.field!r} observation on {element_id!r} after canonical conversion, so "
                "the conflicting-evidence path would not be exercised",
                code="NO_OP_FAULT",
                details={
                    "element_id": element_id,
                    "field": observation.field,
                    "existing_canonical_value": before.value,
                },
            )


def _probe_records(existing, observation: FaultObservation, element_id: str):
    """Existing records plus a throwaway copy of the synthetic observation."""
    from detour_lab.domain.contracts import EvidenceRecord
    from detour_lab.domain.enums import ProvenanceClass, VerificationStatus

    injected = EvidenceRecord(
        id="__failure_lab_probe__",
        element_id=element_id,
        field=observation.field,
        value=observation.value,
        unit=observation.unit,
        method=observation.method,
        source=observation.source,
        verification_status=VerificationStatus(observation.verification_status),
        quality=observation.quality,
        provenance_class=ProvenanceClass(observation.provenance_class),
        synthetic=True,
        note=observation.note,
    )
    return [*existing, injected]


def fault_applicability(
    *,
    graph: PedestrianGraph,
    scenario: Scenario,
    faults: Sequence[FaultDefinition],
    default_phases: Sequence[str],
) -> dict[str, list[dict]]:
    """Per-fault readiness for the current source state.

    This is advisory input for the interface, computed with the same
    constructors the engine uses. It never predicts an outcome.
    """
    declared = _declared_temporary_ids(scenario)
    rows: list[dict] = []
    for fault in faults:
        phases = sorted(fault.phase_ids) or sorted(default_phases)
        applicable: list[dict] = []
        for phase_id in phases:
            try:
                phase_graph = build_phase_graph(graph, scenario, phase_id)
            except Exception as exc:  # pragma: no cover - surfaced as an unavailable phase
                rows.append(
                    {
                        "fault_id": fault.fault_id,
                        "kind": fault.kind.value,
                        "phase_id": phase_id,
                        "applicable": False,
                        "reason": str(exc),
                        "target_ids": fault.target_ids,
                    }
                )
                continue
            active_temp = {
                t for t in declared if _TEMPORARY_PREFIX + t in {e.id for e in phase_graph.graph.edges}
            }
            applicable.append(
                {
                    "fault_id": fault.fault_id,
                    "kind": fault.kind.value,
                    "phase_id": phase_id,
                    "applicable": True,
                    "reason": "",
                    "target_ids": fault.target_ids,
                    "phase_edge_count": len(phase_graph.graph.edges),
                    "closed_edge_ids": sorted(phase_graph.closed_edge_ids),
                    "active_temporary_edge_ids": sorted(active_temp),
                }
            )
        rows.extend(applicable)
    return {"faults": rows}