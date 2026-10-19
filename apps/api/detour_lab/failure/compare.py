"""Baseline-versus-fault robustness analysis (G6-09).

Every number here is counted from stored experiment records. Nothing is
estimated, weighted or smoothed.

The one thing this module is most careful about is **not** producing a number a
reader could mistake for a probability of real-world failure. A ratio such as
"9 of 10 modelled faults preserved a confirmed route" is a *test-coverage*
statement about the specific faults that were executed, on the specific graph,
under the specific evaluation instant. It says nothing about how often the real
route would fail, because the faults are synthetic and deliberately chosen, not
sampled from any population of real hazards.

Accordingly:

* every ratio is emitted together with the explicit denominator that produced
  it (:attr:`RobustnessSummary.denominator_note`);
* untested fault kinds are listed, so a partial run can never read as a full one;
* invalid and failed experiments are counted separately and are **excluded**
  from every pass/fail numerator and denominator.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import Field

from detour_lab.domain.contracts import StrictModel
from detour_lab.failure.model import (
    EngineeringObservation,
    ExperimentOutcome,
    ExperimentStatus,
    FaultKind,
)

__all__ = [
    "INTERPRETATION_NOTE",
    "RobustnessSummary",
    "summarise_robustness",
]

INTERPRETATION_NOTE = (
    "These counts describe how DETOUR LAB's model behaved under the specific synthetic conditions "
    "that were executed. A count of experiments that preserved a confirmed route is a test-coverage "
    "result over those chosen conditions. It is NOT a probability that the route is safe in the "
    "field, NOT a failure rate, and NOT a statistical result: the faults are deliberately authored "
    "stress conditions, not a sample drawn from any population of real-world hazards."
)


class ExperimentRollup(StrictModel):
    """Per-experiment contribution to the summary."""

    experiment_id: str
    status: ExperimentStatus
    fault_kinds: list[FaultKind]
    fault_labels: list[str]
    transitions_compared: int
    confirmed_preserved: int
    confirmed_gained: int
    confirmed_lost: int
    became_possible_only: int
    became_disconnected: int
    new_known_violations: int
    new_unknown_conditions: int
    comparable_routes: int
    total_distance_delta_m: float | None = None
    observations: list[EngineeringObservation]
    error_code: str | None = None


class RobustnessSummary(StrictModel):
    """Transparent, fully-denominated comparison of baseline against faults."""

    schema_version: str = "1.0.0"
    scenario_id: str
    scenario_revision: int
    scenario_content_hash: str
    phase_ids: list[str]
    profile_ids: list[str]
    evaluation_instant: str
    rulepack_id: str
    rulepack_hash: str
    base_graph_hash: str

    #: -- execution accounting ------------------------------------------------
    experiments_requested: int
    experiments_completed: int
    experiments_partially_completed: int
    experiments_invalid: int
    experiments_failed: int
    fault_kinds_available: list[FaultKind]
    fault_kinds_tested: list[FaultKind]
    fault_kinds_untested: list[FaultKind]

    #: -- outcome accounting, counted only from COMPLETED experiments ----------
    pairs_evaluated: int
    pairs_retaining_confirmed: int
    pairs_losing_confirmed: int
    pairs_becoming_possible_only: int
    pairs_becoming_disconnected: int
    pairs_with_new_known_violation: int
    pairs_with_new_unknown_condition: int
    pairs_gaining_confirmed: int
    comparable_routes: int
    total_distance_delta_m: float | None = None

    per_experiment: list[ExperimentRollup] = Field(default_factory=list)
    denominator_note: str
    interpretation_note: str = INTERPRETATION_NOTE
    limitations: list[str] = Field(default_factory=list)


def _rollup(outcome: ExperimentOutcome) -> ExperimentRollup:
    transitions = outcome.transitions
    confirmed_preserved = sum(
        1 for t in transitions if t.observation is EngineeringObservation.CONFIRMED_CONNECTIVITY_PRESERVED
    )
    confirmed_lost = sum(
        1 for t in transitions if t.observation is EngineeringObservation.CONFIRMED_CONNECTIVITY_LOST
    )
    became_possible = sum(
        1
        for t in transitions
        if t.observation is EngineeringObservation.CONFIRMED_ROUTE_BECAME_POSSIBLE_ONLY
    )
    became_disconnected = sum(
        1
        for t in transitions
        if t.observation is EngineeringObservation.POSSIBLE_ONLY_ROUTE_BECAME_DISCONNECTED
    )
    new_violation = sum(
        1 for t in transitions if t.observation is EngineeringObservation.NEW_KNOWN_RULE_VIOLATION
    )
    new_unknown = sum(
        1
        for t in transitions
        if t.observation is EngineeringObservation.NEW_UNRESOLVED_EVIDENCE_CONDITION
    )
    gained = sum(
        1 for t in transitions if t.observation is EngineeringObservation.CONFIRMED_CONNECTIVITY_GAINED
    )
    deltas = [t.distance_delta_m for t in transitions if t.distance_delta_m is not None]
    return ExperimentRollup(
        experiment_id=outcome.experiment_id,
        status=outcome.status,
        fault_kinds=[f.kind for f in outcome.faults],
        fault_labels=[f.label or f.kind.value for f in outcome.faults],
        transitions_compared=len(transitions),
        confirmed_preserved=confirmed_preserved,
        confirmed_gained=gained,
        confirmed_lost=confirmed_lost,
        became_possible_only=became_possible,
        became_disconnected=became_disconnected,
        new_known_violations=new_violation,
        new_unknown_conditions=new_unknown,
        comparable_routes=len(deltas),
        total_distance_delta_m=round(sum(deltas), 6) if deltas else None,
        observations=list(outcome.observations),
        error_code=outcome.error.code if outcome.error else None,
    )


def summarise_robustness(
    *,
    outcomes: Sequence[ExperimentOutcome],
    available_kinds: Sequence[FaultKind],
) -> RobustnessSummary:
    """Aggregate completed experiments into one fully-denominated summary."""
    rollups = [_rollup(o) for o in outcomes]

    completed = [o for o in outcomes if o.status is ExperimentStatus.COMPLETED]
    partial = [o for o in outcomes if o.status is ExperimentStatus.PARTIALLY_COMPLETED]
    invalid = [o for o in outcomes if o.status is ExperimentStatus.INVALID_EXPERIMENT]
    failed = [o for o in outcomes if o.status is ExperimentStatus.EXECUTION_FAILED]

    completed_transitions = [t for o in completed for t in o.transitions]
    completed_deltas = [t.distance_delta_m for t in completed_transitions if t.distance_delta_m is not None]

    tested_kinds = sorted({f.kind for o in outcomes for f in o.faults}, key=lambda k: k.value)
    untested = [k for k in available_kinds if k not in set(tested_kinds)]

    reference = outcomes[0].source if outcomes else None
    return RobustnessSummary(
        scenario_id=reference.scenario_id if reference else "",
        scenario_revision=reference.scenario_revision if reference else 0,
        scenario_content_hash=reference.scenario_content_hash if reference else "",
        phase_ids=reference.phase_ids if reference else [],
        profile_ids=reference.profile_ids if reference else [],
        evaluation_instant=reference.evaluation_instant if reference else "",
        rulepack_id=reference.rulepack_id if reference else "",
        rulepack_hash=reference.rulepack_hash if reference else "",
        base_graph_hash=reference.base_graph_hash if reference else "",
        experiments_requested=len(outcomes),
        experiments_completed=len(completed),
        experiments_partially_completed=len(partial),
        experiments_invalid=len(invalid),
        experiments_failed=len(failed),
        fault_kinds_available=list(available_kinds),
        fault_kinds_tested=tested_kinds,
        fault_kinds_untested=untested,
        pairs_evaluated=len(completed_transitions),
        pairs_retaining_confirmed=sum(
            1 for t in completed_transitions if t.observation is EngineeringObservation.CONFIRMED_CONNECTIVITY_PRESERVED
        ),
        pairs_losing_confirmed=sum(
            1 for t in completed_transitions if t.observation is EngineeringObservation.CONFIRMED_CONNECTIVITY_LOST
        ),
        pairs_becoming_possible_only=sum(
            1
            for t in completed_transitions
            if t.observation is EngineeringObservation.CONFIRMED_ROUTE_BECAME_POSSIBLE_ONLY
        ),
        pairs_becoming_disconnected=sum(
            1
            for t in completed_transitions
            if t.observation is EngineeringObservation.POSSIBLE_ONLY_ROUTE_BECAME_DISCONNECTED
        ),
        pairs_with_new_known_violation=sum(
            1
            for t in completed_transitions
            if t.observation is EngineeringObservation.NEW_KNOWN_RULE_VIOLATION
        ),
        pairs_with_new_unknown_condition=sum(
            1
            for t in completed_transitions
            if t.observation is EngineeringObservation.NEW_UNRESOLVED_EVIDENCE_CONDITION
        ),
        pairs_gaining_confirmed=sum(
            1
            for t in completed_transitions
            if t.observation is EngineeringObservation.CONFIRMED_CONNECTIVITY_GAINED
        ),
        comparable_routes=len(completed_deltas),
        total_distance_delta_m=round(sum(completed_deltas), 6) if completed_deltas else None,
        per_experiment=rollups,
        denominator_note=(
            f"pairs_evaluated = {len(completed_transitions)} = "
            f"{len(completed)} completed experiment(s) x the origin-destination pairs x profiles x "
            "phases each experiment actually compared. Only COMPLETED experiments contribute. "
            f"Partially completed: {len(partial)}; invalid: {len(invalid)}; execution failed: "
            f"{len(failed)}. Invalid and failed experiments are excluded from every count above; they "
            "are evidence about the software, not about the plan."
        ),
        limitations=list(outcomes[0].limitations) if outcomes else [],
    )