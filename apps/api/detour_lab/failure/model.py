"""Typed fault-injection contracts for the Failure Lab (Gate 6).

Design rules encoded here
-------------------------
1. **Faults are data, never code.** A fault is a closed-kind enum plus a typed
   parameter block. There is no expression field, no callable and no string that
   is ever evaluated. Every value is interpreted by an explicit ``match`` in
   :mod:`detour_lab.failure.faults`.
2. **Only supported mutations exist.** Each kind maps onto an operation the
   authoritative domain already performs (a phase closure, a declared phase-set
   change, an evidence registry difference). A fault that cannot be expressed
   that way is rejected, not approximated.
3. **Execution status is separate from engineering outcome.** Whether the
   experiment *ran* has nothing to do with whether the modelled plan held.
   :class:`ExperimentStatus` answers the first question,
   :class:`EngineeringObservation` answers the second. A software error is
   never reported as a network failure.
4. **Identity is separated from execution.** ``input_hash`` covers the semantic
   inputs, ``semantic_hash`` covers the semantic result, and ``experiment_id`` is
   a per-execution handle. They are three different things and are stored in
   three different fields.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from detour_lab.domain.contracts import StrictModel
from detour_lab.domain.enums import ReasonCode, VerdictState

__all__ = [
    "ANALYSIS_UNAVAILABLE_NOTE",
    "ExecutionError",
    "ExperimentLimits",
    "ExperimentStatus",
    "FaultKind",
    "FaultObservation",
]


class FaultKind(StrEnum):
    """The supported fault-injection primitives (MASTER_PROMPT §8, Gate 6 G6-06).

    Only a mutation the domain can genuinely represent is listed. Each entry
    maps to one authoritative operation - see ``faults.py`` for the mapping.
    """

    #: F1 - an additional modelled closure of an existing eligible edge.
    EDGE_CLOSURE = "edge_closure"
    #: F2 - loss of a scenario-declared temporary connection in one phase.
    TEMPORARY_CONNECTION_LOSS = "temporary_connection_loss"
    #: F3 - masking an existing observation in the isolated evidence context.
    EVIDENCE_REMOVAL = "evidence_removal"
    #: F4 - adding an explicitly synthetic, contradictory observation.
    CONFLICTING_OBSERVATION = "conflicting_observation"
    #: F5 - evaluating evidence at an explicit later instant so an existing
    #: freshness policy is actually exercised. Timestamps are never rewritten.
    EVIDENCE_EXPIRATION = "evidence_expiration"
    #: F6 - adding an explicitly synthetic observation in a unit the rulepack
    #: does not accept for that attribute.
    UNSUPPORTED_UNIT_OBSERVATION = "unsupported_unit_observation"
    #: F7 - an explicitly modelled obstruction. The domain models edge
    #: availability only, so this is a closure carrying an obstruction label.
    PATH_OBSTRUCTION = "path_obstruction"


#: Kinds whose effect is a synthetic observation rather than a graph change.
EVIDENCE_MUTATION_KINDS = frozenset(
    {FaultKind.CONFLICTING_OBSERVATION, FaultKind.UNSUPPORTED_UNIT_OBSERVATION}
)


class ExperimentStatus(StrEnum):
    """Did the experiment run? Nothing about the plan's modelled behaviour."""

    COMPLETED = "completed"
    PARTIALLY_COMPLETED = "partially_completed"
    INVALID_EXPERIMENT = "invalid_experiment"
    EXECUTION_FAILED = "execution_failed"
    CANCELLED = "cancelled"


class EngineeringObservation(StrEnum):
    """What the authoritative engine actually reported about the plan.

    Every value describes *modelled software behaviour under an explicitly
    modelled condition*. None of them is a statement about the physical world.
    """

    CONFIRMED_CONNECTIVITY_PRESERVED = "confirmed_connectivity_preserved"
    #: Connectivity that did not exist in the baseline exists after the injected
    #: condition. Reported explicitly rather than folded into "unchanged", so an
    #: unexpected gain can never be silently hidden.
    CONFIRMED_CONNECTIVITY_GAINED = "confirmed_connectivity_gained"
    CONFIRMED_CONNECTIVITY_LOST = "confirmed_connectivity_lost"
    CONFIRMED_ROUTE_BECAME_POSSIBLE_ONLY = "confirmed_route_became_possible_only"
    POSSIBLE_ONLY_ROUTE_BECAME_DISCONNECTED = "possible_only_route_became_disconnected"
    NEW_KNOWN_RULE_VIOLATION = "new_known_rule_violation"
    NEW_UNRESOLVED_EVIDENCE_CONDITION = "new_unresolved_evidence_condition"
    NO_RELEVANT_MODELLED_CHANGE = "no_relevant_modelled_change"
    #: The engine could not produce a result. This is a software outcome and is
    #: never counted as a modelled failure of the plan.
    ANALYSIS_UNAVAILABLE = "analysis_unavailable"


ANALYSIS_UNAVAILABLE_NOTE = (
    "The authoritative engine did not return a result for this pair under the injected condition. "
    "That is a software outcome. It is not evidence that the network failed, and it is excluded "
    "from every robustness numerator and denominator."
)


class ExperimentLimits(StrictModel):
    """Defensible, documented bounds. Enforced in ``faults.py`` and ``engine.py``."""

    max_faults_per_request: int = 12
    max_faults_per_suite: int = 12
    max_target_ids_per_fault: int = 32
    max_synthetic_observations_per_fault: int = 4
    max_suite_duration_ms: int = 60_000
    max_graph_elements: int = 5_000
    max_experiments_per_suite: int = 12

    note: str = (
        "Bounds are enforced server-side before any analysis runs. They exist so a fault definition "
        "cannot be used to request unbounded work."
    )


class FaultObservation(StrictModel):
    """An explicitly synthetic observation introduced by a fault.

    ``synthetic`` is forced to ``True`` and the provenance class cannot claim to
    be a field measurement: injected observations are synthetic by construction
    and must never be presented as evidence collected on site (GATE-6 INV-9).
    """

    field: str = Field(min_length=1)
    value: float | str | bool | None = None
    unit: str | None = None
    method: str = "failure_lab_injected_observation"
    source: str = "DETOUR LAB Failure Lab (synthetic adversarial observation)"
    verification_status: Literal["unverified", "verified", "disputed"] = "unverified"
    quality: Literal["high", "medium", "low"] = "low"
    provenance_class: Literal["assumed", "synthetic", "synthetic_fixture"] = "synthetic"
    note: str = (
        "Synthetic observation injected by an explicitly modelled Failure Lab fault. It is not a "
        "field measurement and carries no field provenance."
    )

    @model_validator(mode="after")
    def _always_synthetic(self) -> FaultObservation:
        if self.provenance_class == "measured":  # pragma: no cover - rejected by the Literal type
            raise ValueError("an injected observation can never claim measured provenance")
        return self


class FaultDefinition(StrictModel):
    """One explicitly modelled adversarial condition.

    ``phase_ids`` is the fault's **scope**. An empty list means "every phase in
    the experiment". A multi-entry scope is the multi-phase case (G6-06/F8):
    the fault is applied to exactly those phases and no other, which preserves
    the independent phase-snapshot model.
    """

    fault_id: str = ""
    kind: FaultKind
    label: str = ""
    #: Element ids the fault acts on: edge ids, node ids, temporary-edge ids or
    #: ``(element, field)`` targets depending on ``kind``.
    target_ids: list[str] = Field(default_factory=list)
    phase_ids: list[str] = Field(default_factory=list)
    observation: FaultObservation | None = None
    #: Explicit evaluation instant for the faulted analysis (F5). When present
    #: it replaces the experiment instant for evidence-freshness judgement. It is
    #: a semantically relevant input and is part of ``input_hash``.
    evaluation_instant: str | None = None
    note: str = ""
    semantic_hash: str = ""

    @model_validator(mode="after")
    def _normalised(self) -> FaultDefinition:
        object.__setattr__(self, "target_ids", sorted({t for t in self.target_ids if t}))
        object.__setattr__(self, "phase_ids", sorted({p for p in self.phase_ids if p}))
        if not self.fault_id:
            object.__setattr__(self, "fault_id", "flt-" + self.semantic_body_hash().split(":")[-1][:12])
        object.__setattr__(self, "semantic_hash", self.semantic_body_hash())
        return self

    def semantic_body_hash(self) -> str:
        """Canonical identity of the fault definition alone.

        Excludes the assigned ``fault_id`` so two identical faults defined twice
        are recognisably the same condition.
        """
        from detour_lab.domain.hashing import semantic_hash

        return semantic_hash(
            {
                "kind": self.kind.value,
                "target_ids": self.target_ids,
                "phase_ids": self.phase_ids,
                "observation": self.observation.model_dump(mode="json") if self.observation else None,
                "evaluation_instant": self.evaluation_instant,
            }
        )


class ExecutionError(StrictModel):
    """A structured, non-throwing failure record.

    ``stage`` distinguishes a fault that could not be represented from an
    analysis that could not be executed. Neither is a modelled network result.
    """

    stage: Literal[
        "validation",
        "materialisation",
        "baseline_analysis",
        "faulted_analysis",
        "comparison",
        "persistence",
    ]
    code: str
    message: str
    details: dict = Field(default_factory=dict)


class ElementStateChange(StrictModel):
    """One graph/evidence element that differs between baseline and faulted state."""

    change: Literal["element_added", "element_removed", "state_changed", "evidence_added", "evidence_masked"]
    element_id: str
    element_kind: Literal["edge", "node", "evidence"]
    phase_id: str
    before_state: VerdictState | None = None
    after_state: VerdictState | None = None
    before_reason_codes: list[ReasonCode] = Field(default_factory=list)
    after_reason_codes: list[ReasonCode] = Field(default_factory=list)
    detail: str = ""


class PairTransition(StrictModel):
    """Before/after outcome for one origin-destination pair under one profile."""

    pair_id: str
    origin_id: str
    destination_id: str
    profile_id: str
    phase_id: str
    before_confirmed: bool
    before_possible: bool
    before_distance_m: float | None = None
    after_confirmed: bool
    after_possible: bool
    after_distance_m: float | None = None
    #: Only when both sides have a model-confirmed route. A missing route is
    #: never reported as zero metres (GATE-6 INV-18).
    distance_delta_m: float | None = None
    observation: EngineeringObservation
    explanation: str
    new_fail_verdicts: list[str] = Field(default_factory=list)
    new_unknown_verdicts: list[str] = Field(default_factory=list)
    reference_route_comparison: bool = False


class ExperimentLimitsEcho(StrictModel):
    applied: ExperimentLimits


class PhaseProfileOutcome(StrictModel):
    """Analysis identity for one (phase, profile) on one side of the experiment."""

    phase_id: str
    profile_id: str
    available: bool
    phase_graph_id: str | None = None
    phase_graph_hash: str | None = None
    analysis_semantic_hash: str | None = None
    counts: dict[str, int] = Field(default_factory=dict)
    unavailable_reason: str = ""


class ExperimentSource(StrictModel):
    """Everything about the state an experiment starts from.

    Recorded so a stored experiment can be tied to the exact revision it tested,
    and so a later revision of the same scenario can never silently adopt it.
    """

    project_id: str
    scenario_id: str
    scenario_revision: int
    scenario_content_hash: str
    base_graph_version_id: str
    base_graph_hash: str
    rulepack_id: str
    rulepack_version: str
    rulepack_hash: str
    phase_ids: list[str]
    profile_ids: list[str]
    evaluation_instant: str
    #: Set when a stored run was proven identical to the recomputed baseline.
    verified_baseline_run_ids: list[str] = Field(default_factory=list)
    baseline_link_note: str = (
        "No stored run was linked to this experiment. The baseline was recomputed with the same "
        "authoritative engine at the same explicit evaluation instant, so it is directly comparable."
    )


class ExperimentOutcome(StrictModel):
    """Complete, replayable record of one failure experiment."""

    schema_version: str = "1.0.0"
    engine_version: str
    experiment_id: str
    created_at: str
    duration_ms: float = 0.0
    limits: ExperimentLimits
    status: ExperimentStatus
    source: ExperimentSource
    faults: list[FaultDefinition]
    #: The isolated state actually evaluated.
    isolated_scenario_hash: str = ""
    isolated_graph_hash: str = ""
    isolated_graph_version_id: str = ""
    faulted_evaluation_instant: str = ""
    baseline: list[PhaseProfileOutcome] = Field(default_factory=list)
    faulted: list[PhaseProfileOutcome] = Field(default_factory=list)
    transitions: list[PairTransition] = Field(default_factory=list)
    element_changes: list[ElementStateChange] = Field(default_factory=list)
    observations: list[EngineeringObservation] = Field(default_factory=list)
    evidence_change_log: list[dict] = Field(default_factory=list)
    error: ExecutionError | None = None
    input_hash: str = ""
    semantic_hash: str = ""
    limitations: list[str] = Field(default_factory=list)
    suite_id: str | None = None

    def semantic_body(self) -> dict:
        """Payload whose hash is the experiment's semantic identity.

        ``experiment_id``, ``created_at`` and ``duration_ms`` are excluded: they
        are per-execution metadata, not properties of the modelled condition.
        """
        payload = self.model_dump(mode="json")
        for key in ("experiment_id", "created_at", "duration_ms", "suite_id"):
            payload.pop(key, None)
        return payload


class ExperimentSummary(StrictModel):
    """Compact row used by history lists and robustness roll-ups."""

    experiment_id: str
    scenario_id: str
    scenario_revision: int
    phase_ids: list[str]
    profile_ids: list[str]
    fault_kinds: list[FaultKind]
    fault_labels: list[str]
    status: ExperimentStatus
    observations: list[EngineeringObservation]
    input_hash: str
    semantic_hash: str
    created_at: str
    suite_id: str | None = None
    error_code: str | None = None