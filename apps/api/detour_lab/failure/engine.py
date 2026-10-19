"""Isolated fault execution against the authoritative pipeline (G6-07/G6-08).

The isolation contract
----------------------
An experiment never touches the source. Concretely, running one cannot change:

* the persisted scenario, its revision or its content hash;
* the persisted evidence records;
* the persisted phase definitions;
* any stored analysis run;
* any stored optimisation run or canonical manifest.

That is achieved structurally rather than by convention: every mutation happens
in **new objects**. The isolated graph is a fresh ``BaseGraphVersion`` whose
``evidence`` list is a new list; the isolated scenario is a fresh ``Scenario``
validated from a detached JSON payload. The source objects are read-only inputs
to those constructions. There is no mutation API on either type to call by
accident - ``BaseGraphVersion`` and ``Scenario`` are pydantic models whose
fields this module never assigns to.

The one deliberate difference from the source is the *version id* of the
isolated graph, which is suffixed with the experiment's own key so a faulted
graph can never be mistaken for - or collide with - a persisted graph version.

No second verdict engine
------------------------
There is no code here that turns PASS into FAIL or a confirmed route into a
possible-only route. The only mutation primitives are a phase closure, a
declared phase-set change, and an evidence-registry difference - each of which
the ordinary :func:`detour_lab.analysis.run.run_analysis` pipeline already
consumes. The resulting verdicts, feasibility graphs and routes are whatever
the unmodified engine computes.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from detour_lab import ENGINE_VERSION
from detour_lab.analysis.run import run_analysis
from detour_lab.domain.contracts import (
    AnalysisResult,
    BaseGraphVersion,
    EvidenceRecord,
    GraphEdit,
    MobilityProfile,
    RulePack,
    Scenario,
)
from detour_lab.domain.enums import ProvenanceClass, VerdictState
from detour_lab.domain.hashing import semantic_hash
from detour_lab.domain.units import parse_timestamp
from detour_lab.failure.faults import FaultValidationError, validate_faults
from detour_lab.failure.model import (
    ANALYSIS_UNAVAILABLE_NOTE,
    EVIDENCE_MUTATION_KINDS,
    ElementStateChange,
    EngineeringObservation,
    ExecutionError,
    ExperimentLimits,
    ExperimentOutcome,
    ExperimentSource,
    ExperimentStatus,
    FaultDefinition,
    FaultKind,
    PairTransition,
    PhaseProfileOutcome,
)
from detour_lab.graph.model import PedestrianGraph
from detour_lab.persistence.repository import RunRecord

__all__ = [
    "EXPERIMENT_LIMITATIONS",
    "IsolatedState",
    "build_isolated_state",
    "execute_experiment",
    "pair_observation",
]

EXPERIMENT_LIMITATIONS = (
    "An experiment reports how DETOUR LAB's authoritative model behaves when an explicitly modelled "
    "input changes. It is not a prediction of a real-world failure and not a physical safety claim.",
    "A surviving experiment means the modelled conclusion held under that one modelled condition. "
    "It is not evidence that the real route is safe.",
    "An experiment that could not be executed is reported as a software outcome. It is never "
    "reported as the network failing.",
    "All injected observations are explicitly synthetic and carry no field provenance.",
)


# --------------------------------------------------------------------------- isolation


@dataclass(frozen=True, slots=True)
class IsolatedState:
    """The proposed state an experiment evaluates. Never the source."""

    graph: PedestrianGraph
    scenario: Scenario
    evaluation_instant: datetime
    evidence_change_log: tuple[dict[str, Any], ...] = ()
    graph_change_log: tuple[dict[str, Any], ...] = ()

    @property
    def scenario_hash(self) -> str:
        return self.scenario.content_hash

    @property
    def graph_hash(self) -> str:
        return self.graph.version.content_hash


def build_isolated_state(
    *,
    graph: PedestrianGraph,
    scenario: Scenario,
    faults: Sequence[FaultDefinition],
    experiment_key: str,
    base_instant: datetime,
) -> IsolatedState:
    """Apply every fault through supported domain operations, in memory.

    Ordering is canonical (by fault semantic hash) so the same fault set always
    produces the same isolated state, whatever order the caller listed them in.
    """
    ordered = sorted(faults, key=lambda f: f.semantic_hash)

    isolated_version_id = f"{graph.version.id}~failure-lab:{experiment_key}"
    evidence_log: list[dict[str, Any]] = []
    graph_log: list[dict[str, Any]] = []
    instant = base_instant

    # -- evidence mutations (applied to a copy of the record list) -------------
    records = list(graph.version.evidence)
    for fault in ordered:
        observation = fault.observation
        if fault.kind is FaultKind.EVIDENCE_REMOVAL:
            assert observation is not None  # guaranteed by validate_faults
            removed: list[str] = []
            kept: list[EvidenceRecord] = []
            for record in records:
                hit = record.element_id in fault.target_ids and record.field == observation.field
                if hit:
                    removed.append(record.id)
                else:
                    kept.append(record)
            records = kept
            evidence_log.append(
                {
                    "fault_id": fault.fault_id,
                    "kind": fault.kind.value,
                    "action": "masked",
                    "element_ids": fault.target_ids,
                    "field": observation.field,
                    "masked_evidence_ids": sorted(removed),
                }
            )
        elif fault.kind in EVIDENCE_MUTATION_KINDS:
            assert observation is not None  # guaranteed by validate_faults
            for element_id in fault.target_ids:
                injected = EvidenceRecord(
                    # Deterministic id: the same fault always names the same record.
                    id=f"__FL__::{experiment_key}::{fault.fault_id}::{element_id}::{observation.field}",
                    element_id=element_id,
                    field=observation.field,
                    value=observation.value,
                    unit=observation.unit,
                    method=observation.method,
                    source=observation.source,
                    verification_status=observation.verification_status,
                    quality=observation.quality,
                    provenance_class=ProvenanceClass(observation.provenance_class),
                    synthetic=True,
                    note=observation.note,
                )
                records = [r for r in records if r.id != injected.id]
                records.append(injected)
                evidence_log.append(
                    {
                        "fault_id": fault.fault_id,
                        "kind": fault.kind.value,
                        "action": "injected",
                        "element_ids": [element_id],
                        "field": observation.field,
                        "injected_evidence_id": injected.id,
                        "value": injected.value,
                        "unit": injected.unit,
                    }
                )
        elif fault.kind is FaultKind.EVIDENCE_EXPIRATION:
            instant = parse_timestamp(str(fault.evaluation_instant), field="evaluation_instant").astimezone(UTC)
            evidence_log.append(
                {
                    "fault_id": fault.fault_id,
                    "kind": fault.kind.value,
                    "action": "evaluation_instant_moved",
                    "from": base_instant.isoformat(),
                    "to": instant.isoformat(),
                    "note": (
                        "Recorded observation timestamps are unchanged. Only the instant at which the "
                        "rulepack's freshness policy is judged is moved."
                    ),
                }
            )

    isolated_graph = graph
    if evidence_log:
        payload = graph.version.model_dump(mode="json")
        payload["id"] = isolated_version_id
        payload["evidence"] = sorted(
            (r.model_dump(mode="json") for r in records), key=lambda r: r["id"]
        )
        payload["content_hash"] = ""  # force the content-addressed validator to recompute
        isolated_graph = PedestrianGraph.from_version(BaseGraphVersion.model_validate(payload))

    # -- graph mutations (phase closures and declared phase-set changes) -------
    new_edits: list[GraphEdit] = []
    phase_overrides: dict[str, dict[str, list[str]]] = {}

    for fault in ordered:
        if fault.kind in (FaultKind.EDGE_CLOSURE, FaultKind.PATH_OBSTRUCTION):
            label = (
                "Explicitly modelled obstruction. The domain represents path unavailability only; no "
                "physical obstruction geometry, footprint or severity is simulated."
                if fault.kind is FaultKind.PATH_OBSTRUCTION
                else "Modelled additional route closure introduced by the Failure Lab."
            )
            for edge_id in fault.target_ids:
                new_edits.append(
                    GraphEdit(
                        op="close_edge",
                        target_id=edge_id,
                        params={
                            "phases": fault.phase_ids,
                            "failure_lab": fault.fault_id,
                            "failure_lab_kind": fault.kind.value,
                            "note": f"{label} Fault {fault.fault_id} ({fault.semantic_hash}).",
                        },
                        reason=f"Failure Lab fault {fault.fault_id}: {fault.kind.value}",
                    )
                )
            graph_log.append(
                {
                    "fault_id": fault.fault_id,
                    "kind": fault.kind.value,
                    "action": "close_edges",
                    "edge_ids": sorted(fault.target_ids),
                    "phase_ids": fault.phase_ids,
                }
            )
        elif fault.kind is FaultKind.TEMPORARY_CONNECTION_LOSS:
            for phase_id in fault.phase_ids:
                current = phase_overrides.setdefault(
                    phase_id, {"temporary_edge_ids": None, "closed_edge_ids": None}
                )
                declared = (
                    current["temporary_edge_ids"]
                    if current["temporary_edge_ids"] is not None
                    else list(scenario.phase_by_id(phase_id).temporary_edge_ids)  # type: ignore[union-attr]
                )
                current["temporary_edge_ids"] = sorted(
                    t for t in declared if t not in set(fault.target_ids)
                )
            graph_log.append(
                {
                    "fault_id": fault.fault_id,
                    "kind": fault.kind.value,
                    "action": "deactivate_temporary_connections",
                    "temporary_edge_ids": sorted(fault.target_ids),
                    "phase_ids": fault.phase_ids,
                }
            )

    isolated_scenario = scenario
    if new_edits or phase_overrides or isolated_graph.version.id != scenario.base_graph_version_id:
        payload = scenario.model_dump(mode="json")
        if new_edits:
            payload["edits"] = [
                *payload["edits"],
                *(e.model_dump(mode="json") for e in new_edits),
            ]
        if phase_overrides:
            phases: list[dict[str, Any]] = []
            for phase_payload in payload["phases"]:
                override = phase_overrides.get(phase_payload["id"])
                if override and override["temporary_edge_ids"] is not None:
                    phase_payload["temporary_edge_ids"] = override["temporary_edge_ids"]
                phases.append(phase_payload)
            payload["phases"] = phases
        if isolated_graph.version.id != scenario.base_graph_version_id:
            # The isolated graph is a new content-addressed version, so the
            # isolated scenario must name it explicitly. ``build_phase_graph``
            # refuses a scenario paired with the wrong graph version, and that
            # guard is correct: the experiment state must be internally
            # coherent rather than quietly borrowing the source graph identity.
            payload["base_graph_version_id"] = isolated_graph.version.id
        payload["content_hash"] = ""  # a new scenario content hash is part of the experiment identity
        isolated_scenario = Scenario.model_validate(payload)

    return IsolatedState(
        graph=isolated_graph,
        scenario=isolated_scenario,
        evaluation_instant=instant,
        evidence_change_log=tuple(evidence_log),
        graph_change_log=tuple(graph_log),
    )


# --------------------------------------------------------------------------- comparison


def pair_observation(
    *,
    before_confirmed: bool,
    before_possible: bool,
    after_confirmed: bool,
    after_possible: bool,
    new_fail_verdicts: Sequence[str],
    new_unknown_verdicts: Sequence[str],
) -> EngineeringObservation:
    """Classify one pair's transition. Pure, and free of physical claims.

    Precedence is deliberate and mirrors how a reviewer reads a diff: the
    strongest connectivity loss first, then a newly appearing known violation,
    then a newly appearing unresolved condition, then "nothing relevant".
    """
    if before_confirmed and not after_confirmed:
        if after_possible:
            return EngineeringObservation.CONFIRMED_ROUTE_BECAME_POSSIBLE_ONLY
        return EngineeringObservation.CONFIRMED_CONNECTIVITY_LOST
    if before_possible and not after_possible:
        return EngineeringObservation.POSSIBLE_ONLY_ROUTE_BECAME_DISCONNECTED
    if not before_confirmed and after_confirmed:
        return EngineeringObservation.CONFIRMED_CONNECTIVITY_GAINED
    if new_fail_verdicts:
        return EngineeringObservation.NEW_KNOWN_RULE_VIOLATION
    if new_unknown_verdicts:
        return EngineeringObservation.NEW_UNRESOLVED_EVIDENCE_CONDITION
    if before_confirmed and after_confirmed:
        return EngineeringObservation.CONFIRMED_CONNECTIVITY_PRESERVED
    return EngineeringObservation.NO_RELEVANT_MODELLED_CHANGE


_EXPLANATIONS = {
    EngineeringObservation.CONFIRMED_CONNECTIVITY_PRESERVED: (
        "A model-confirmed route exists after the injected condition, exactly as it did before it. "
        "The modelled conclusion held under this condition."
    ),
    EngineeringObservation.CONFIRMED_CONNECTIVITY_GAINED: (
        "The pair had no model-confirmed route before the injected condition and has one after it. "
        "Reported explicitly so it is not mistaken for 'nothing changed'. A passing fault experiment "
        "is never presented as evidence of improved real-world safety."
    ),
    EngineeringObservation.CONFIRMED_CONNECTIVITY_LOST: (
        "The origin-destination pair had a model-confirmed route before the injected condition and has "
        "none after it. This is a modelled disconnection under an explicitly modelled condition, not "
        "an observation about the physical network."
    ),
    EngineeringObservation.CONFIRMED_ROUTE_BECAME_POSSIBLE_ONLY: (
        "The pair lost its model-confirmed route but a route still exists in the possible graph, which "
        "assumes unresolved edges are usable. This is NOT confirmed accessibility."
    ),
    EngineeringObservation.POSSIBLE_ONLY_ROUTE_BECAME_DISCONNECTED: (
        "The pair previously had a hypothetical route that assumed unknown edges were usable and now "
        "has none, in either graph."
    ),
    EngineeringObservation.NEW_KNOWN_RULE_VIOLATION: (
        "The injected condition introduced a rule violation that the rulepack can actually decide. It "
        "is a known modelled failure, distinct from any unresolved condition."
    ),
    EngineeringObservation.NEW_UNRESOLVED_EVIDENCE_CONDITION: (
        "The injected condition introduced an attribute the rulepack cannot resolve. The condition is "
        "UNKNOWN: missing information, not a passing or failing result."
    ),
    EngineeringObservation.NO_RELEVANT_MODELLED_CHANGE: (
        "The injected condition did not change this pair's connectivity or any rule verdict for it."
    ),
    EngineeringObservation.ANALYSIS_UNAVAILABLE: ANALYSIS_UNAVAILABLE_NOTE,
}


def _verdict_index(result: AnalysisResult | None) -> dict[tuple[str, str], VerdictState]:
    if result is None:
        return {}
    return {(v.rule_id, v.element_id): v.state for v in result.verdicts}


def _finding_elements(result: AnalysisResult) -> dict[str, str]:
    return {f.id: f.element_id for e in result.edge_evaluations for f in e.findings}


def _pair_elements(result: AnalysisResult, od) -> set[str]:
    """Elements the engine itself associated with one origin-destination pair.

    Built from the pair's own demonstrated blockers, its relevant findings and
    both of its routes, so an experiment's explanation names only elements that
    pair is actually connected to. Endpoint nodes are intentionally not
    expanded: ``AnalysisResult`` carries edge states, not geometry, and
    inventing endpoint identities here would be a guess.
    """
    mapping = _finding_elements(result)
    elements = {
        mapping[fid] for fid in (*od.blocking_finding_ids, *od.relevant_finding_ids) if fid in mapping
    }
    elements.update(od.confirmed_path_edge_ids)
    elements.update(od.possible_path_edge_ids)
    elements.add(od.origin_node_id)
    elements.add(od.destination_node_id)
    return elements


def _compare_pair(
    *,
    before: AnalysisResult,
    after: AnalysisResult,
) -> list[PairTransition]:
    """Compare one pair, attributing new verdicts to that pair only.

    Attribution matters: a new unknown on an element that has nothing to do with
    a pair must not be reported as a change *for that pair*. The element set is
    the one the engine itself produced for the pair.
    """
    after_by_pair = {f"{o.origin_id}->{o.destination_id}": o for o in after.od_results}
    before_by_pair = {f"{o.origin_id}->{o.destination_id}": o for o in before.od_results}
    previous = _verdict_index(before)
    all_new_fails = sorted(
        f"{element_id}::{rule_id}"
        for (rule_id, element_id), value in _verdict_index(after).items()
        if value is VerdictState.FAIL and previous.get((rule_id, element_id)) is not VerdictState.FAIL
    )
    all_new_unknowns = sorted(
        f"{element_id}::{rule_id}"
        for (rule_id, element_id), value in _verdict_index(after).items()
        if value is VerdictState.UNKNOWN and previous.get((rule_id, element_id)) is not VerdictState.UNKNOWN
    )

    transitions: list[PairTransition] = []
    for pair_id, before_od in sorted(before_by_pair.items()):
        after_od = after_by_pair.get(pair_id)
        if after_od is None:  # pragma: no cover - the same OD set is evaluated on both sides
            continue
        elements = _pair_elements(after, after_od)
        new_fails = [v for v in all_new_fails if v.split("::")[0] in elements]
        new_unknowns = [v for v in all_new_unknowns if v.split("::")[0] in elements]
        observation = pair_observation(
            before_confirmed=before_od.confirmed_reachable,
            before_possible=before_od.possibly_reachable,
            after_confirmed=after_od.confirmed_reachable,
            after_possible=after_od.possibly_reachable,
            new_fail_verdicts=new_fails,
            new_unknown_verdicts=new_unknowns,
        )
        comparable = before_od.confirmed_distance_m is not None and after_od.confirmed_distance_m is not None
        transitions.append(
            PairTransition(
                pair_id=pair_id,
                origin_id=before_od.origin_id,
                destination_id=before_od.destination_id,
                profile_id=after.profile_id,
                phase_id=after.phase_id,
                before_confirmed=before_od.confirmed_reachable,
                before_possible=before_od.possibly_reachable,
                before_distance_m=before_od.confirmed_distance_m,
                after_confirmed=after_od.confirmed_reachable,
                after_possible=after_od.possibly_reachable,
                after_distance_m=after_od.confirmed_distance_m,
                distance_delta_m=(
                    round(after_od.confirmed_distance_m - before_od.confirmed_distance_m, 6)
                    if comparable
                    else None
                ),
                observation=observation,
                explanation=_EXPLANATIONS[observation],
                new_fail_verdicts=new_fails,
                new_unknown_verdicts=new_unknowns,
                reference_route_comparison=comparable,
            )
        )
    return transitions


def _element_changes(
    *,
    before: AnalysisResult,
    after: AnalysisResult,
    before_graph: PedestrianGraph,
    after_graph: PedestrianGraph,
) -> list[ElementStateChange]:
    changes: list[ElementStateChange] = []
    before_edges = {e.id for e in before_graph.edges}
    after_edges = {e.id for e in after_graph.edges}
    before_states = {e.edge_id: e for e in before.edge_evaluations}
    after_states = {e.edge_id: e for e in after.edge_evaluations}

    for edge_id in sorted(after_edges - before_edges):
        state = after_states.get(edge_id)
        changes.append(
            ElementStateChange(
                change="element_added",
                element_id=edge_id,
                element_kind="edge",
                phase_id=after.phase_id,
                after_state=state.state if state else None,
                detail="Edge exists only in the faulted state (for example a temporary connection).",
            )
        )
    for edge_id in sorted(before_edges - after_edges):
        state = before_states.get(edge_id)
        changes.append(
            ElementStateChange(
                change="element_removed",
                element_id=edge_id,
                element_kind="edge",
                phase_id=after.phase_id,
                before_state=state.state if state else None,
                detail="Edge is absent from the faulted state.",
            )
        )
    for edge_id in sorted(before_edges & after_edges):
        before_state = before_states.get(edge_id)
        after_state = after_states.get(edge_id)
        if before_state is None or after_state is None:  # pragma: no cover - both sides evaluate every edge
            continue
        if before_state.state is after_state.state and before_state.reason_codes == after_state.reason_codes:
            continue
        changes.append(
            ElementStateChange(
                change="state_changed",
                element_id=edge_id,
                element_kind="edge",
                phase_id=after.phase_id,
                before_state=before_state.state,
                after_state=after_state.state,
                before_reason_codes=list(before_state.reason_codes),
                after_reason_codes=list(after_state.reason_codes),
                detail=_describe_transition(before_state.state, after_state.state),
            )
        )
    return changes


_TRANSITION_WORDING = {
    (VerdictState.PASS, VerdictState.UNKNOWN): (
        "Model-confirmed in the baseline, UNKNOWN under the injected condition. The route is no "
        "longer confirmed; it has not been shown to fail."
    ),
    (VerdictState.PASS, VerdictState.FAIL): (
        "Model-confirmed in the baseline, a known modelled failure under the injected condition."
    ),
    (VerdictState.UNKNOWN, VerdictState.FAIL): (
        "Unresolved in the baseline and a known modelled failure under the injected condition."
    ),
    (VerdictState.UNKNOWN, VerdictState.PASS): (
        "Unresolved in the baseline and model-confirmed under the injected condition."
    ),
    (VerdictState.FAIL, VerdictState.UNKNOWN): (
        "A known modelled failure in the baseline is unresolved under the injected condition. The "
        "failure is not silently converted into a pass."
    ),
    (VerdictState.FAIL, VerdictState.PASS): (
        "A known modelled failure in the baseline is model-confirmed under the injected condition."
    ),
}


def _describe_transition(before: VerdictState, after: VerdictState) -> str:
    if before is after:
        return "Verdict unchanged; the reason codes attached to it changed."
    return _TRANSITION_WORDING.get(
        (before, after),
        f"Modelled state changed from {before.value} to {after.value}.",
    )


# --------------------------------------------------------------------------- execution


def execute_experiment(
    *,
    project_id: str,
    graph: PedestrianGraph,
    scenario: Scenario,
    rulepack: RulePack,
    profiles: dict[str, MobilityProfile],
    faults: Sequence[FaultDefinition],
    phase_ids: Sequence[str],
    profile_ids: Sequence[str],
    evaluation_instant: datetime,
    limits: ExperimentLimits,
    baseline_run_records: Sequence[RunRecord] = (),
    suite_id: str | None = None,
    clock: Callable[[], float] = time.perf_counter,
) -> ExperimentOutcome:
    """Run one experiment and return its complete, replayable record.

    ``faults`` are applied together to a single isolated state, so a suite that
    injects several conditions at once is evaluated as one condition - never as
    an ordered sequence whose earlier results leak into later ones.
    """
    started = clock()
    experiment_id = f"fxp-{uuid.uuid4().hex[:12]}"

    if len(graph.edges) > limits.max_graph_elements:
        raise FaultValidationError(
            f"graph version {graph.version.id!r} has {len(graph.edges)} edges, above the Failure Lab "
            f"bound of {limits.max_graph_elements}",
            code="FAULT_LIMIT_EXCEEDED",
            details={"edge_count": len(graph.edges), "max_graph_elements": limits.max_graph_elements},
        )

    experiment_key = semantic_hash(
        {
            "scenario": scenario.content_hash,
            "graph": graph.version.content_hash,
            "rulepack": rulepack.content_hash,
            "phase_ids": sorted(phase_ids),
            "profile_ids": sorted(profile_ids),
            "instant": evaluation_instant.isoformat(),
            "faults": sorted(f.semantic_hash for f in faults),
        }
    ).split(":")[-1][:12]

    validated = validate_faults(
        faults=faults,
        graph=graph,
        scenario=scenario,
        rulepack=rulepack,
        default_phases=phase_ids,
        max_faults=limits.max_faults_per_request,
        max_targets=limits.max_target_ids_per_fault,
    )

    # Every phase an experiment reports on: the selected ones plus whatever the
    # faults actually target, so a multi-phase fault's blast radius is visible.
    effective_phases = sorted({*phase_ids, *(p for f in validated for p in f.phase_ids)})

    source = ExperimentSource(
        project_id=project_id,
        scenario_id=scenario.id,
        scenario_revision=scenario.revision,
        scenario_content_hash=scenario.content_hash,
        base_graph_version_id=graph.version.id,
        base_graph_hash=graph.version.content_hash,
        rulepack_id=rulepack.id,
        rulepack_version=rulepack.version,
        rulepack_hash=rulepack.content_hash,
        phase_ids=list(effective_phases),
        profile_ids=sorted(profile_ids),
        evaluation_instant=evaluation_instant.isoformat(),
    )

    isolated = build_isolated_state(
        graph=graph,
        scenario=scenario,
        faults=validated,
        experiment_key=experiment_key,
        base_instant=evaluation_instant,
    )

    def _finalise(
        *,
        status: ExperimentStatus,
        baseline: list[PhaseProfileOutcome],
        faulted: list[PhaseProfileOutcome],
        transitions: list[PairTransition],
        element_changes: list[ElementStateChange],
        error: ExecutionError | None = None,
        source_override: ExperimentSource | None = None,
    ) -> ExperimentOutcome:
        outcome = ExperimentOutcome(
            engine_version=ENGINE_VERSION,
            experiment_id=experiment_id,
            created_at=datetime.now(UTC).isoformat(),
            duration_ms=round((clock() - started) * 1000, 3),
            limits=limits,
            status=status,
            source=source_override or source,
            faults=validated,
            isolated_scenario_hash=isolated.scenario_hash,
            isolated_graph_hash=isolated.graph_hash,
            isolated_graph_version_id=isolated.graph.version.id,
            faulted_evaluation_instant=isolated.evaluation_instant.isoformat(),
            baseline=baseline,
            faulted=faulted,
            transitions=transitions,
            element_changes=element_changes,
            observations=_aggregate_observations(transitions),
            evidence_change_log=[dict(e) for e in isolated.evidence_change_log],
            error=error,
            suite_id=suite_id,
            limitations=list(EXPERIMENT_LIMITATIONS),
        )
        input_hash = semantic_hash(
            {
                "source_scenario_hash": outcome.source.scenario_content_hash,
                "source_graph_hash": outcome.source.base_graph_hash,
                "rulepack_hash": outcome.source.rulepack_hash,
                "phase_ids": outcome.source.phase_ids,
                "profile_ids": outcome.source.profile_ids,
                "evaluation_instant": outcome.source.evaluation_instant,
                "faulted_evaluation_instant": outcome.faulted_evaluation_instant,
                "fault_semantic_hashes": sorted(f.semantic_hash for f in validated),
                "engine_version": ENGINE_VERSION,
            }
        )
        outcome = outcome.model_copy(
            update={"input_hash": input_hash, "semantic_hash": semantic_hash(outcome.semantic_body())}
        )
        return outcome

    # -- baseline: recomputed with the same engine at the same instant --------
    baseline_rows: list[PhaseProfileOutcome] = []
    baseline_results: dict[tuple[str, str], AnalysisResult] = {}
    for phase_id in effective_phases:
        for profile_id in sorted(profile_ids):
            try:
                result = run_analysis(
                    base_graph=graph,
                    scenario=scenario,
                    phase_id=phase_id,
                    profile_id=profile_id,
                    rulepack=rulepack,
                    profile=profiles[profile_id],
                    as_of=evaluation_instant,
                )
            except Exception as exc:
                return _finalise(
                    status=ExperimentStatus.EXECUTION_FAILED,
                    baseline=baseline_rows,
                    faulted=[],
                    transitions=[],
                    element_changes=[],
                    error=ExecutionError(
                        stage="baseline_analysis",
                        code="ANALYSIS_FAILED",
                        message=(
                            "The authoritative engine could not produce a baseline analysis for "
                            f"phase {phase_id!r} / profile {profile_id!r}: {type(exc).__name__}: {exc}"
                        ),
                        details={
                            "phase_id": phase_id,
                            "profile_id": profile_id,
                            "exception_type": type(exc).__name__,
                            "message": str(exc),
                        },
                    ),
                )
            baseline_results[(phase_id, profile_id)] = result
            baseline_rows.append(_outcome_row(result))

    source = _link_verified_runs(source, baseline_results, baseline_run_records)

    # -- faulted analysis ------------------------------------------------------
    faulted_rows: list[PhaseProfileOutcome] = []
    faulted_results: dict[tuple[str, str], AnalysisResult] = {}
    faults_caught: list[dict[str, Any]] = []
    for phase_id in effective_phases:
        for profile_id in sorted(profile_ids):
            try:
                result = run_analysis(
                    base_graph=isolated.graph,
                    scenario=isolated.scenario,
                    phase_id=phase_id,
                    profile_id=profile_id,
                    rulepack=rulepack,
                    profile=profiles[profile_id],
                    as_of=isolated.evaluation_instant,
                )
            except Exception as exc:
                # A software failure. It is recorded as unavailable and is never
                # turned into a modelled result for this (phase, profile). The
                # exception text is preserved verbatim: a swallowed cause would
                # make a genuine defect indistinguishable from a valid result.
                faults_caught.append(
                    {
                        "phase_id": phase_id,
                        "profile_id": profile_id,
                        "exception_type": type(exc).__name__,
                        "message": str(exc),
                    }
                )
                faulted_rows.append(
                    PhaseProfileOutcome(
                        phase_id=phase_id,
                        profile_id=profile_id,
                        available=False,
                        unavailable_reason=(
                            f"{ANALYSIS_UNAVAILABLE_NOTE} Engine detail: {type(exc).__name__}: {exc}"
                        ),
                    )
                )
                continue
            faulted_results[(phase_id, profile_id)] = result
            faulted_rows.append(_outcome_row(result))

    if not faulted_results:
        return _finalise(
            status=ExperimentStatus.EXECUTION_FAILED,
            baseline=baseline_rows,
            faulted=faulted_rows,
            transitions=[],
            element_changes=[],
            error=ExecutionError(
                stage="faulted_analysis",
                code="ANALYSIS_UNAVAILABLE",
                message=(
                    "The authoritative engine returned no analysis for any selected phase and profile "
                    "under the injected condition. No modelled conclusion is reported: a software "
                    "failure is not a network failure."
                ),
                details={
                    "phase_ids": effective_phases,
                    "profile_ids": sorted(profile_ids),
                    "engine_errors": faults_caught,
                },
            ),
        )

    transitions: list[PairTransition] = []
    element_changes: list[ElementStateChange] = []
    for key, after_result in sorted(faulted_results.items()):
        before_result = baseline_results.get(key)
        if before_result is None:  # pragma: no cover - the baseline loop covers every key
            continue
        transitions.extend(_compare_pair(before=before_result, after=after_result))
        before_graph = _phase_graph(graph, scenario, key[0])
        after_graph = _phase_graph(isolated.graph, isolated.scenario, key[0])
        if before_graph is not None and after_graph is not None:
            element_changes.extend(
                _element_changes(
                    before=before_result,
                    after=after_result,
                    before_graph=before_graph,
                    after_graph=after_graph,
                )
            )
    transitions.sort(key=lambda t: (t.phase_id, t.profile_id, t.pair_id))
    element_changes.sort(key=lambda c: (c.phase_id, c.element_kind, c.element_id))

    complete = len(faulted_results) == len(baseline_results)
    return _finalise(
        status=ExperimentStatus.COMPLETED if complete else ExperimentStatus.PARTIALLY_COMPLETED,
        baseline=baseline_rows,
        faulted=faulted_rows,
        transitions=transitions,
        element_changes=element_changes,
        source_override=source,
        error=(
            None
            if complete
            else ExecutionError(
                stage="faulted_analysis",
                code="PARTIAL_ANALYSIS",
                message=(
                    f"{len(faulted_results)} of {len(baseline_results)} phase/profile analyses completed "
                    "under the injected condition. The unavailable ones are reported as unavailable; "
                    "no modelled conclusion is inferred for them, and they are excluded from the "
                    "robustness counts."
                ),
                details={"engine_errors": faults_caught},
            )
        ),
    )


def _outcome_row(result: AnalysisResult) -> PhaseProfileOutcome:
    return PhaseProfileOutcome(
        phase_id=result.phase_id,
        profile_id=result.profile_id,
        available=True,
        phase_graph_id=result.phase_graph_id,
        phase_graph_hash=result.phase_graph_hash,
        analysis_semantic_hash=semantic_hash(result.model_dump(mode="json")),
        counts=dict(result.counts),
    )


def _phase_graph(graph: PedestrianGraph, scenario: Scenario, phase_id: str) -> PedestrianGraph | None:
    from detour_lab.scenarios.apply import build_phase_graph

    try:
        return build_phase_graph(graph, scenario, phase_id).graph
    except Exception:  # pragma: no cover - phase validity is checked upstream
        return None


def _link_verified_runs(
    source: ExperimentSource,
    baseline_results: dict[tuple[str, str], AnalysisResult],
    records: Sequence[RunRecord],
) -> ExperimentSource:
    """Prove, when possible, that a stored run *is* this experiment's baseline.

    The comparison is strict on purpose: same scenario id, same revision, same
    phase, same profile, same evaluation instant, and an identical semantic
    hash. Anything else is reported as "not linked" with the reason, never
    quietly claimed as a match.
    """
    if not records:
        return source
    linked: list[str] = []
    notes: list[str] = []
    for record in records:
        result = baseline_results.get((record.phase_id, record.profile_id))
        if result is None:
            notes.append(f"{record.run_id}: no baseline was computed for this phase/profile pair")
            continue
        if record.scenario_id != source.scenario_id:
            notes.append(f"{record.run_id}: belongs to scenario {record.scenario_id!r}, not the source")
            continue
        if record.scenario_revision != source.scenario_revision:
            notes.append(f"{record.run_id}: recorded at revision {record.scenario_revision}, not {source.scenario_revision}")
            continue
        if record.evaluation_instant != source.evaluation_instant:
            notes.append(
                f"{record.run_id}: evaluated at {record.evaluation_instant}, which is a different "
                "instant from this experiment, so it is not the same comparison"
            )
            continue
        recomputed = semantic_hash(result.model_dump(mode="json"))
        if recomputed != record.semantic_hash:
            notes.append(
                f"{record.run_id}: stored semantic hash does not match the recomputed baseline; the "
                "stored run is not linked"
            )
            continue
        linked.append(record.run_id)
    return source.model_copy(
        update={
            "verified_baseline_run_ids": sorted(linked),
            "baseline_link_note": (
                f"Baseline run(s) {', '.join(sorted(linked))} were proven identical to the recomputed "
                "baseline by scenario, revision, phase, profile, evaluation instant and semantic hash."
                if linked
                else "No stored run matched this experiment exactly. " + " ".join(notes)
            ),
        }
    )


def _aggregate_observations(transitions: Sequence[PairTransition]) -> list[EngineeringObservation]:
    """Distinct observations across the experiment, in a fixed documented order."""
    order = [
        EngineeringObservation.CONFIRMED_CONNECTIVITY_LOST,
        EngineeringObservation.CONFIRMED_ROUTE_BECAME_POSSIBLE_ONLY,
        EngineeringObservation.POSSIBLE_ONLY_ROUTE_BECAME_DISCONNECTED,
        EngineeringObservation.NEW_KNOWN_RULE_VIOLATION,
        EngineeringObservation.NEW_UNRESOLVED_EVIDENCE_CONDITION,
        EngineeringObservation.CONFIRMED_CONNECTIVITY_GAINED,
        EngineeringObservation.CONFIRMED_CONNECTIVITY_PRESERVED,
        EngineeringObservation.NO_RELEVANT_MODELLED_CHANGE,
        EngineeringObservation.ANALYSIS_UNAVAILABLE,
    ]
    present = {t.observation for t in transitions}
    return [o for o in order if o in present]