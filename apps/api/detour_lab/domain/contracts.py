"""Validated domain contracts (MASTER_PROMPT §5).

Design rule enforced here: **an attribute value cannot exist without an evidence
record.** ``Edge`` carries structure only (endpoints, geometry, type); every
safety-relevant quantity (width, slope, surface, curb transition) lives in an
:class:`EvidenceRecord` bound to the element ID and resolved through
``evidence.resolver``. This makes "missing field != Pass" a structural property
rather than a runtime convention.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from detour_lab.domain.enums import (
    CostProvenance,
    EdgeType,
    NodeType,
    Operator,
    ProvenanceClass,
    ReasonCode,
    RuleCriticality,
    RuleKind,
    RuleScope,
    SolverStatus,
    VerdictState,
    VerificationStatus,
)
from detour_lab.domain.hashing import canonical_json, semantic_hash
from detour_lab.domain.units import parse_timestamp

__all__ = [
    "AnalysisResult",
    "AttributeSpec",
    "BaseGraphVersion",
    "CandidateProposal",
    "CoordinateBasis",
    "DataSource",
    "Edge",
    "EdgeEvaluation",
    "EvidenceRecord",
    "Finding",
    "FreshnessPolicy",
    "Intervention",
    "MobilityProfile",
    "Node",
    "ODPairResult",
    "OriginDestination",
    "Phase",
    "Project",
    "ResolvedAttribute",
    "Rule",
    "RuleCheck",
    "RulePack",
    "RuleVerdict",
    "Scenario",
    "StrictModel",
    "TemporaryEdge",
]

#: Declared coordinate bases. Kept as a distinct name from the
#: :class:`CoordinateBasis` model so the string annotation below cannot resolve
#: to the class itself (which would silently reject valid input).
CoordinateBasisKind = Literal["local_planar_meters", "wgs84_degrees"]

#: Text-valued attributes compared by token, never by numeric conversion.
TEXT_FIELDS = frozenset({"surface", "curb_transition", "crossing_type", "obstruction"})


class StrictModel(BaseModel):
    """Base model: unknown fields rejected, enums kept as enums."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True, use_enum_values=False)

    def canonical(self) -> dict[str, Any]:
        """Stable dict used for hashing (excludes non-semantic extras)."""
        return self.model_dump(mode="json")


class DataSource(StrictModel):
    """Where a dataset or rule came from, and what class of truth it is."""

    name: str = Field(min_length=1)
    description: str = ""
    license: str = "unspecified"
    attribution: str = ""
    url: str | None = None
    provenance_class: ProvenanceClass
    version: str | None = None
    retrieved_at: datetime | None = None


class FreshnessPolicy(StrictModel):
    """Explicit per-attribute freshness. If absent, evidence never expires."""

    max_age_days: int | None = Field(default=None, ge=1)
    requires_verified: bool = False


class AttributeSpec(StrictModel):
    """How a named attribute is interpreted by the rulepack."""

    quantity: Literal["length_m", "width_mm", "slope_percent", "text"]
    accepted_units: list[str] = Field(default_factory=list)
    freshness: FreshnessPolicy | None = None
    description: str = ""


class EvidenceRecord(StrictModel):
    """One observation about one field of one element.

    ``value``/``unit`` are exactly what the source reported. Canonicalisation
    happens in the resolver so the conversion stays auditable.
    """

    id: str = Field(min_length=1)
    element_id: str = Field(min_length=1)
    field: str = Field(min_length=1)
    value: float | str | bool | None = None
    unit: str | None = None
    method: str = Field(min_length=1)
    source: str = Field(min_length=1)
    source_url: str | None = None
    observed_at: datetime | None = None
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    quality: Literal["high", "medium", "low"] = "medium"
    reviewer: str | None = None
    invalidated: bool = False
    provenance_class: ProvenanceClass
    synthetic: bool = True
    note: str = ""

    @field_validator("observed_at", mode="before")
    @classmethod
    def _strict_timestamp(cls, value: Any) -> Any:
        """Accept only timezone-aware ISO 8601 and normalise to UTC."""
        if value is None or isinstance(value, datetime):
            return value
        return parse_timestamp(str(value), field="observed_at")


class ResolvedAttribute(StrictModel):
    """Outcome of resolving every eligible record for one (element, field)."""

    element_id: str
    field: str
    known: bool
    value: float | str | bool | None = None
    canonical_unit: str | None = None
    reason_code: ReasonCode | None = None
    explanation: str = ""
    evidence_ids: list[str] = Field(default_factory=list)
    conflicting_values: list[str] = Field(default_factory=list)
    conversions: list[dict[str, Any]] = Field(default_factory=list)
    conversions_explicit: bool = True


class Node(StrictModel):
    id: str = Field(min_length=1)
    x: float
    y: float
    node_type: NodeType = NodeType.JUNCTION
    name: str = ""
    provenance_class: ProvenanceClass = ProvenanceClass.SYNTHETIC
    evidence_ids: list[str] = Field(default_factory=list)


class Edge(StrictModel):
    """Structural edge. Safety attributes live in evidence records."""

    id: str = Field(min_length=1)
    u: str = Field(min_length=1)
    v: str = Field(min_length=1)
    geometry: list[tuple[float, float]] = Field(min_length=2)
    length_m: float = Field(ge=0)
    edge_type: EdgeType = EdgeType.SIDEWALK
    name: str = ""
    provenance_class: ProvenanceClass = ProvenanceClass.SYNTHETIC
    evidence_ids: list[str] = Field(default_factory=list)

    @field_validator("geometry")
    @classmethod
    def _no_duplicate_points(cls, value: list[tuple[float, float]]) -> list[tuple[float, float]]:
        if len(set(value)) != len(value):
            raise ValueError("edge geometry must not repeat a vertex")
        return value

    @model_validator(mode="after")
    def _endpoints_match_geometry(self) -> Self:
        if self.geometry[0] == self.geometry[-1] and len(self.geometry) > 2:
            raise ValueError("edge geometry is closed but the edge is directed u->v")
        return self


class CoordinateBasis(StrictModel):
    """Explicit, recorded coordinate basis. Never assumed silently."""

    kind: CoordinateBasisKind
    unit: Literal["m", "degree"]
    #: Required for ``local_planar_meters`` so the demo cannot be mistaken for a
    #: real georeferenced location (MASTER_PROMPT §4 geographic caution).
    local_origin_label: str | None = None
    crs_note: str = ""
    #: For ``wgs84_degrees``: the projection used for metre-based arithmetic.
    projected_crs: str | None = None


class BaseGraphVersion(StrictModel):
    """Immutable, content-addressed pedestrian network (FR-002, FR-003)."""

    id: str = Field(min_length=1)
    schema_version: str = "1.0.0"
    basis: CoordinateBasis
    nodes: list[Node]
    edges: list[Edge]
    #: Edges that exist in this version but are **not traversable** (construction
    #: closure for this phase). Part of the version's content hash, so a phase
    #: graph can never share a hash with the baseline it is derived from.
    inactive_edge_ids: list[str] = Field(default_factory=list)
    evidence: list[EvidenceRecord] = Field(default_factory=list)
    source: DataSource
    created_at: datetime | None = None
    content_hash: str = ""

    @model_validator(mode="after")
    def _content_addressed(self) -> Self:
        if not self.content_hash:
            expected = semantic_hash(self._semantic_body())
            object.__setattr__(self, "content_hash", expected)
        elif self.content_hash != semantic_hash(self._semantic_body()):
            raise ValueError("content_hash does not match the graph content")
        return self

    def _semantic_body(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "basis": self.basis.model_dump(mode="json"),
            "nodes": sorted((n.model_dump(mode="json") for n in self.nodes), key=lambda n: n["id"]),
            "edges": sorted((e.model_dump(mode="json") for e in self.edges), key=lambda e: e["id"]),
            "inactive_edge_ids": sorted(self.inactive_edge_ids),
            "evidence": sorted((r.model_dump(mode="json") for r in self.evidence), key=lambda r: r["id"]),
            "source": self.source.model_dump(mode="json"),
        }


class Project(StrictModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    study_area_description: str = ""
    basis: CoordinateBasis
    #: Explicitly "unspecified" rather than invented: no jurisdiction is assumed.
    jurisdiction: str = "unspecified"
    owner: str = "unspecified"
    dataset_source: DataSource
    created_at: datetime | None = None


class OriginDestination(StrictModel):
    """OD endpoint bound to a **graph node ID**, never to a nearby coordinate."""

    id: str = Field(min_length=1)
    label: str = ""
    node_id: str = Field(min_length=1)
    kind: Literal["origin", "destination", "both"]
    essential: bool = True
    priority: int = Field(default=1, ge=1, le=5)
    weight_source: str = "demo_assumption"
    weight: float | None = Field(default=None, ge=0)


class RuleCheck(StrictModel):
    """One whitelisted comparison inside a rule."""

    field: str = Field(min_length=1)
    operator: Operator
    threshold: float | None = None
    values: list[str] = Field(default_factory=list)
    description: str = ""

    @model_validator(mode="after")
    def _operator_arguments(self) -> Self:
        if self.operator in (Operator.GTE, Operator.LTE, Operator.GT, Operator.LT):
            if self.threshold is None:
                raise ValueError(f"operator {self.operator} requires a numeric threshold")
        elif self.operator is Operator.ONE_OF and not self.values:
            raise ValueError("operator one_of requires at least one value")
        elif self.operator is Operator.EXISTS and self.values:
            raise ValueError("operator exists takes no values")
        return self


class Rule(StrictModel):
    """Declarative rule. Data only — never executable code (MASTER_PROMPT §5.3)."""

    id: str = Field(min_length=1)
    version: str = "1.0.0"
    scope: RuleScope
    kind: RuleKind = RuleKind.HARD
    criticality: RuleCriticality = RuleCriticality.CRITICAL
    description: str = ""
    applies_to_edge_types: list[EdgeType] = Field(default_factory=list)
    applies_to_node_types: list[NodeType] = Field(default_factory=list)
    #: Profile IDs this rule applies to; ``["*"]`` means every profile.
    profiles: list[str] = Field(default_factory=lambda: ["*"])
    checks: list[RuleCheck] = Field(min_length=1)
    requires_verified_evidence: bool = False
    failure_message: str = ""
    #: Label shown next to the verdict so demo rules are never read as law.
    basis_label: str = "DEMO_RULEPACK_NOT_LEGAL"
    source_reference: str = ""


class RulePack(StrictModel):
    id: str = Field(min_length=1)
    version: str = "1.0.0"
    name: str = ""
    basis: str = ""
    jurisdiction_scope: str = "unspecified"
    legal_applicability: Literal["unverified", "reviewed", "not_applicable"] = "unverified"
    disclaimer: str = ""
    attributes: dict[str, AttributeSpec] = Field(default_factory=dict)
    rules: list[Rule] = Field(min_length=1)
    source: DataSource
    content_hash: str = ""

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        ids = [rule.id for rule in self.rules]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate rule IDs in rulepack")
        for rule in self.rules:
            for check in rule.checks:
                if check.field not in self.attributes:
                    raise ValueError(f"rule {rule.id} references undeclared attribute {check.field}")
        if not self.content_hash:
            object.__setattr__(
                self,
                "content_hash",
                semantic_hash(
                    {
                        "id": self.id,
                        "version": self.version,
                        "attributes": {k: v.model_dump(mode="json") for k, v in sorted(self.attributes.items())},
                        "rules": [r.model_dump(mode="json") for r in sorted(self.rules, key=lambda r: r.id)],
                        "legal_applicability": self.legal_applicability,
                    }
                ),
            )
        return self

    def rule_by_id(self, rule_id: str) -> Rule | None:
        return next((r for r in self.rules if r.id == rule_id), None)


class MobilityProfile(StrictModel):
    """Demonstration mobility profile.

    Hard requirements come from the rulepack; ``preferences`` only weight route
    ranking and can never change a hard verdict (INV-05).
    """

    id: str = Field(min_length=1)
    name: str
    description: str
    is_demo_profile: bool = True
    preference_weights: dict[str, float] = Field(default_factory=dict)
    notes: str = ""


class TemporaryEdge(StrictModel):
    """Ephemeral path that exists only in declared phases."""

    id: str = Field(min_length=1)
    u: str
    v: str
    geometry: list[tuple[float, float]] = Field(min_length=2)
    length_m: float = Field(ge=0)
    edge_type: EdgeType = EdgeType.TEMPORARY_PATH
    name: str = ""
    evidence: list[EvidenceRecord] = Field(default_factory=list)
    constructible_in_field: bool = False
    field_verification_note: str = (
        "Modelled edge only. Field constructibility has not been confirmed by any engineer."
    )


class Phase(StrictModel):
    """Construction phase with an explicit ordering convention.

    Demo phases use logical ordinals. No construction calendar is invented.
    """

    id: str = Field(min_length=1)
    order: int = Field(ge=0)
    label: str = ""
    #: Half-open interval convention ``[start, end)`` documented for adjacent phases.
    boundary_convention: Literal["[start,end)", "logical_ordinal"] = "logical_ordinal"
    start_ordinal: int | None = None
    end_ordinal: int | None = None
    closed_edge_ids: list[str] = Field(default_factory=list)
    temporary_edge_ids: list[str] = Field(default_factory=list)
    notes: str = ""


class GraphEdit(StrictModel):
    """Typed, auditable graph modification applied to a scenario revision."""

    op: Literal[
        "add_node",
        "split_edge",
        "add_edge",
        "remove_edge",
        "set_direction",
        "link_crossing",
        "update_attribute",
        "close_edge",
        "activate_temporary_edge",
    ]
    target_id: str = Field(min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""

    def key(self) -> str:
        """Deterministic identity of the operation for hashing/ordering."""
        from detour_lab.domain.hashing import canonical_json

        return f"{self.op}:{self.target_id}:{canonical_json(self.params)}"


class Scenario(StrictModel):
    """Immutable revision referencing an immutable base graph version."""

    id: str = Field(min_length=1)
    name: str = ""
    parent_scenario_id: str | None = None
    base_graph_version_id: str
    rulepack_id: str
    rulepack_hash: str
    profile_ids: list[str] = Field(min_length=1)
    phases: list[Phase] = Field(min_length=1)
    edits: list[GraphEdit] = Field(default_factory=list)
    origins_destinations: list[OriginDestination] = Field(default_factory=list)
    temporary_edges: list[TemporaryEdge] = Field(default_factory=list)
    intervention_ids: list[str] = Field(default_factory=list)
    note: str = ""
    revision: int = Field(default=1, ge=1)
    created_at: datetime | None = None
    content_hash: str = ""

    @model_validator(mode="after")
    def _validated(self) -> Self:
        if len({p.id for p in self.phases}) != len(self.phases):
            raise ValueError("duplicate phase IDs in scenario")
        orders = [p.order for p in self.phases]
        if len(set(orders)) != len(orders):
            raise ValueError("phase orders must be unique for deterministic ordering")
        if not self.content_hash:
            object.__setattr__(self, "content_hash", semantic_hash(self._semantic_body()))
        return self

    def _semantic_body(self) -> dict[str, Any]:
        return {
            "base_graph_version_id": self.base_graph_version_id,
            "rulepack_id": self.rulepack_id,
            "rulepack_hash": self.rulepack_hash,
            "profile_ids": sorted(self.profile_ids),
            "phases": [p.model_dump(mode="json") for p in sorted(self.phases, key=lambda p: p.order)],
            "edits": sorted(
                (e.model_dump(mode="json") for e in self.edits), key=canonical_json
            ),
            "origins_destinations": sorted(
                (o.model_dump(mode="json") for o in self.origins_destinations), key=lambda o: o["id"]
            ),
            "temporary_edges": sorted(
                (t.model_dump(mode="json") for t in self.temporary_edges), key=lambda t: t["id"]
            ),
            "intervention_ids": sorted(self.intervention_ids),
            "revision": self.revision,
        }

    def phase_by_id(self, phase_id: str) -> Phase | None:
        return next((p for p in self.phases if p.id == phase_id), None)


class RuleVerdict(StrictModel):
    """Result of one rule against one element in one (profile, phase)."""

    rule_id: str
    rule_version: str
    element_id: str
    scope: RuleScope
    state: VerdictState
    reason_code: ReasonCode
    explanation: str
    profile_id: str
    phase_id: str
    inputs: list[ResolvedAttribute] = Field(default_factory=list)
    rule_kind: RuleKind = RuleKind.HARD
    criticality: RuleCriticality = RuleCriticality.CRITICAL
    basis_label: str = "DEMO_RULEPACK_NOT_LEGAL"


class Finding(StrictModel):
    """User-facing explanation derived only from computed data (FR-012)."""

    id: str
    element_id: str
    element_kind: Literal["edge", "node"]
    state: VerdictState
    severity: Literal["critical", "advisory", "info"]
    reason_code: ReasonCode
    rule_id: str | None = None
    profile_id: str
    phase_id: str
    explanation: str
    evidence_ids: list[str] = Field(default_factory=list)
    attributes: list[ResolvedAttribute] = Field(default_factory=list)
    remedy_hint: str = ""


class EdgeEvaluation(StrictModel):
    """Aggregated traversal state for one edge in one (profile, phase)."""

    edge_id: str
    state: VerdictState
    relevant_check_count: int
    confirmed_eligible: bool
    possibly_eligible: bool
    unknown_only: bool = False
    reason_codes: list[ReasonCode] = Field(default_factory=list)
    verdict_ids: list[str] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)


class ODPairResult(StrictModel):
    """Per origin-destination outcome (FR-010). Never conflates the two graphs."""

    origin_id: str
    destination_id: str
    origin_node_id: str
    destination_node_id: str
    confirmed_reachable: bool
    possibly_reachable: bool
    confirmed_path_edge_ids: list[str] = Field(default_factory=list)
    confirmed_distance_m: float | None = None
    possible_path_edge_ids: list[str] = Field(default_factory=list)
    possible_distance_m: float | None = None
    possible_distance_label: str = "hypothetical - assumes unknown edges are usable"
    #: Preference-weighted ranking cost. ``confirmed_distance_m`` always stays the
    #: true physical length so a preference weight can never be mistaken for distance.
    confirmed_route_cost: float | None = None
    possible_route_cost: float | None = None
    route_note: str = ""
    blocking_finding_ids: list[str] = Field(default_factory=list)
    relevant_finding_ids: list[str] = Field(default_factory=list)
    reason_codes: list[ReasonCode] = Field(default_factory=list)


class AnalysisResult(StrictModel):
    """Complete deterministic result for one (scenario, phase, profile, rulepack)."""

    scenario_id: str
    scenario_hash: str
    phase_id: str
    profile_id: str
    rulepack_id: str
    rulepack_version: str
    rulepack_hash: str
    base_graph_version_id: str
    base_graph_hash: str
    phase_graph_id: str
    phase_graph_hash: str
    edge_evaluations: list[EdgeEvaluation]
    verdicts: list[RuleVerdict]
    od_results: list[ODPairResult]
    counts: dict[str, int]
    warnings: list[str] = Field(default_factory=list)


class InterventionCost(StrictModel):
    id: str
    label: str
    provenance: CostProvenance = CostProvenance.DEMO_ONLY
    currency: str = "INR"
    quantity: float = Field(ge=0)
    unit: str = "item"
    unit_price_min: float | None = Field(default=None, ge=0)
    unit_price_nominal: float | None = Field(default=None, ge=0)
    unit_price_max: float | None = Field(default=None, ge=0)
    setup_cost_nominal: float | None = Field(default=None, ge=0)
    removal_cost_nominal: float | None = Field(default=None, ge=0)
    note: str = "Illustrative demonstration value; no market source consulted."

    @property
    def total_nominal(self) -> float | None:
        if self.unit_price_nominal is None:
            return None
        return self.quantity * self.unit_price_nominal + (self.setup_cost_nominal or 0.0) + (
            self.removal_cost_nominal or 0.0
        )

    @property
    def total_max(self) -> float | None:
        if self.unit_price_max is None:
            return None
        return self.quantity * self.unit_price_max + (self.setup_cost_nominal or 0.0) + (
            self.removal_cost_nominal or 0.0
        )


class Intervention(StrictModel):
    """Candidate modification from the bounded, editable library (FR-102)."""

    id: str = Field(min_length=1)
    name: str = ""
    description: str = ""
    enabled: bool = True
    allowed_ops: list[str] = Field(min_length=1)
    target_element_ids: list[str] = Field(default_factory=list)
    phases: list[str] = Field(default_factory=list)
    requires_intervention_ids: list[str] = Field(default_factory=list)
    excludes_intervention_ids: list[str] = Field(default_factory=list)
    precondition_expression: dict[str, Any] | None = None
    active_phase_ids: list[str] = Field(default_factory=list)
    costs: list[InterventionCost] = Field(default_factory=list)
    constructible_in_field: bool = False
    geometry_provided: bool = False


class CandidateProposal(StrictModel):
    """One enumerated intervention subset plus its re-verification outcome (FR-103)."""

    proposal_id: str
    intervention_ids: list[str]
    eligible: bool
    rejection_reasons: list[str] = Field(default_factory=list)
    restored_required_od: bool | None = None
    requires_verification: bool = False
    passed_profiles: list[str] = Field(default_factory=list)
    failed_profiles: list[str] = Field(default_factory=list)
    cost_nominal: float | None = None
    cost_max: float | None = None
    cost_unknown: bool = False
    added_distance_m: float | None = None
    solver_status: SolverStatus = SolverStatus.INCOMPLETE_OR_UNKNOWN