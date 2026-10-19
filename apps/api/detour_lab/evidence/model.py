"""Evidence-intelligence contracts (Gate 6, G6-01/G6-02/G6-04).

These are the **derived**, not authored, structures of the verification queue.
Nothing here stores a measurement, a verdict or a probability. Every field is
computed from the authoritative resolver, the authoritative analysis result and
the immutable graph, so a queue entry can always be traced back to the evidence
records and findings that produced it.

Two rules are structural rather than conventional:

* a queue entry carries the **exact** ``ReasonCode`` the resolver returned. The
  five evidence conditions (``NO_EVIDENCE``, ``CONFLICTING_EVIDENCE``,
  ``UNSUPPORTED_UNIT``, ``EVIDENCE_EXPIRED``, ``EVIDENCE_NOT_VERIFIED``) are
  never collapsed into one generic "unresolved" label, because they call for
  different field work;
* :class:`EvidenceIssue` carries **no numeric priority score**. Priority is an
  explainable category plus a deterministic ordering (see
  :mod:`detour_lab.evidence.queue`). A number here would be a fabricated
  precision, not a measurement.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field

from detour_lab.domain.contracts import StrictModel
from detour_lab.domain.enums import ReasonCode

__all__ = [
    "CONFLICT_EXPLANATIONS",
    "CRITICALITY_ORDER",
    "EVIDENCE_STATUS_LABELS",
    "EvidenceCriticality",
    "EvidenceIssue",
    "EvidenceIssuePair",
    "EvidenceQueue",
    "EvidenceQueueScope",
    "ObservationComparison",
    "QueueState",
]


class EvidenceCriticality(StrEnum):
    """Explainable decision-relevance category. **Not** a probability or a score.

    The names describe what the *modelled decision* is waiting on, not how
    likely a field visit is to succeed. No value-of-information semantics are
    claimed because none is computed (MASTER_PROMPT §8).
    """

    DECISION_BLOCKING = "decision_blocking"
    DECISION_RELEVANT = "decision_relevant"
    SUPPORTING = "supporting"


class QueueState(StrEnum):
    """Lifecycle of a derived queue entry.

    The queue is *derived*, so it carries no reviewer workflow state: an entry
    exists while the authoritative resolver still reports the attribute
    unresolved, and it disappears when the resolver stops reporting it. Reviewer
    actions (recording an observation, invalidating one) change the evidence, and
    the queue is recomputed - it is never patched.
    """

    OPEN = "open"


#: Deterministic ranking used for ordering. Lower sorts first.
CRITICALITY_ORDER: dict[str, int] = {value: index for index, value in enumerate(EvidenceCriticality)}


#: Readable wording per machine-readable status. The machine value is always
#: carried separately in ``resolution_status``; this mapping is display only and
#: never replaces the code.
EVIDENCE_STATUS_LABELS: dict[str, str] = {
    ReasonCode.NO_EVIDENCE.value: "No observation recorded",
    ReasonCode.CONFLICTING_EVIDENCE.value: "Observations disagree",
    ReasonCode.UNSUPPORTED_UNIT.value: "Unsupported unit",
    ReasonCode.EVIDENCE_EXPIRED.value: "Observation stale under its freshness policy",
    ReasonCode.EVIDENCE_NOT_VERIFIED.value: "Observation not verified",
    ReasonCode.INVALID_NUMERIC_VALUE.value: "Observation value not interpretable",
}


#: What an engineer would actually have to do, per unresolved condition.
CONFLICT_EXPLANATIONS: dict[str, str] = {
    ReasonCode.NO_EVIDENCE.value: (
        "No eligible observation exists for this attribute, so the modelled check cannot return a "
        "known result. A field measurement or a reviewed entry is required before the check can be "
        "resolved. Absence of evidence is not evidence that the element is unsuitable."
    ),
    ReasonCode.CONFLICTING_EVIDENCE.value: (
        "Two or more eligible observations disagree after canonical unit conversion. Every claim is "
        "retained; no value is selected, averaged, or preferred because it produces a more "
        "favourable result. Resolution requires an explicit reviewed decision with provenance."
    ),
    ReasonCode.UNSUPPORTED_UNIT.value: (
        "At least one observation cannot be interpreted in the canonical unit declared by the "
        "rulepack. The attribute is unknown - never zero and never passing. A re-observation with a "
        "declared unit is required."
    ),
    ReasonCode.EVIDENCE_EXPIRED.value: (
        "The observation is older than the freshness policy the rulepack declares for this "
        "attribute, or its age cannot be established. Re-observation is required."
    ),
    ReasonCode.EVIDENCE_NOT_VERIFIED.value: (
        "The rulepack requires verified evidence for this attribute and the eligible observation is "
        "not verified. Recording a value does not make it verified; a reviewer must change its "
        "verification state with provenance."
    ),
}


class EvidenceQueueScope(StrictModel):
    """Exactly which analysis inputs the returned queue was derived from.

    Echoed on every response so a reviewer can never mistake a narrow queue for
    a whole-project finding.
    """

    scenario_id: str
    scenario_revision: int
    scenario_content_hash: str
    project_id: str
    phase_ids: list[str]
    profile_ids: list[str]
    rulepack_id: str
    rulepack_version: str
    rulepack_hash: str
    evaluation_instant: str
    #: Extra phases inspected for cross-phase relevance. These do **not** add
    #: entries of their own: the queue's scope is the selected analysis, so every
    #: entry carries real origin-destination linkage. Listing them here says
    #: only that each in-scope issue was also checked against these phases, so a
    #: gap that persists elsewhere is visible on the entry it belongs to.
    additional_phases_inspected: list[str] = Field(default_factory=list)
    scope_note: str = (
        "The queue lists attributes that the authoritative resolver cannot resolve for at least one "
        "rule in scope for the selected phase(s) and mobility profile(s). It is not a list of "
        "physical defects: an unresolved attribute means the model cannot determine the condition, "
        "not that the element is unsuitable."
    )


class ObservationComparison(StrictModel):
    """One observation behind an unresolved attribute, with full provenance.

    ``value`` and ``unit`` are exactly what the source reported. Canonical
    conversion, where one happened, is reported separately so the original
    record is never overwritten.
    """

    evidence_id: str
    value: float | str | bool | None = None
    unit: str | None = None
    method: str
    source: str
    source_url: str | None = None
    observed_at: str | None = None
    verification_status: str
    quality: str
    reviewer: str | None = None
    provenance_class: str
    synthetic: bool
    invalidated: bool
    note: str = ""
    #: Populated only when the resolver actually converted the unit.
    conversion: dict | None = None


class EvidenceIssuePair(StrictModel):
    """One origin-destination pair this unresolved attribute is connected to.

    ``role`` is deliberately explicit. ``blocking`` means the existing analysis
    *demonstrated* this element blocks the pair by counterexample; anything else
    is ``relevant``, and "relevant" never implies causation.
    """

    pair_id: str
    origin_id: str
    destination_id: str
    profile_id: str
    role: Literal["blocking", "relevant", "on_confirmed_route", "on_possible_route"]
    confirmed_reachable: bool
    possibly_reachable: bool
    confirmed_distance_m: float | None = None
    phase_id: str


class EvidenceIssue(StrictModel):
    """One unresolved ``(element, attribute)`` pair with its decision context."""

    issue_id: str
    scope: str
    #: The **exact** machine-readable resolver status. Never collapsed into a
    #: generic "unresolved" label; ``status_label`` is display wording only.
    resolution_status: ReasonCode
    status_label: str
    element_id: str
    element_kind: Literal["edge", "node"]
    element_name: str
    attribute: str
    edge_u: str | None = None
    edge_v: str | None = None
    edge_length_m: float | None = None
    edge_type: str | None = None
    node_x: float | None = None
    node_y: float | None = None
    node_type: str | None = None
    rule_ids: list[str] = Field(default_factory=list)
    affected_profile_ids: list[str] = Field(default_factory=list)
    affected_phase_ids: list[str] = Field(default_factory=list)
    observations: list[ObservationComparison] = Field(default_factory=list)
    evidence_record_ids: list[str] = Field(default_factory=list)
    recorded_measurement: str | None = None
    missing_or_conflicting: str
    investigation_target: str
    od_pairs: list[EvidenceIssuePair] = Field(default_factory=list)
    od_pair_count: int = 0
    criticality: EvidenceCriticality
    criticality_rationale: list[str] = Field(default_factory=list)
    #: True when the same element already carries a *known* model failure. An
    #: unknown attribute on an already-failing element must still be shown:
    #: the known failure does not resolve it and must not hide it.
    element_has_known_failure: bool = False
    queue_state: QueueState = QueueState.OPEN
    dataset_notice: str = ""


class EvidenceQueue(StrictModel):
    """Ordered, deterministic queue of unresolved attributes."""

    schema_version: str = "1.0.0"
    engine_version: str
    scope: EvidenceQueueScope
    issues: list[EvidenceIssue] = Field(default_factory=list)
    counts_by_status: dict[str, int] = Field(default_factory=dict)
    counts_by_criticality: dict[str, int] = Field(default_factory=dict)
    total_unresolved_attributes_scanned: int = 0
    ordering_rule: str
    prioritization_method: str
    limitations: list[str] = Field(default_factory=list)


class EvidenceConflictReport(StrictModel):
    """Structured answer to "why is this attribute unresolved?" (G6-04).

    Reports every observation and the resolver's own reason. It never picks a
    winner, never averages, and never infers reliability from a source name.
    """

    element_id: str
    attribute: str
    resolution_status: ReasonCode
    resolved: bool
    canonical_value: float | str | bool | None = None
    canonical_unit: str | None = None
    explanation: str
    observations: list[ObservationComparison] = Field(default_factory=list)
    distinct_values: list[str] = Field(default_factory=list)
    resolution_requirement: str
    can_be_resolved_without_field_work: bool
    selected_value_note: str = (
        "No observation is selected as the answer. Selecting the most favourable claim, or the most "
        "recent one, would silently change the accessibility result and is not done."
    )