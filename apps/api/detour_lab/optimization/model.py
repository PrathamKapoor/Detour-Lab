"""Typed models for the bounded optimisation search (MASTER_PROMPT §7).

These models are the **contract** of the Fix This Plan feature:

* :class:`SearchConfig` - explicit, echoed search limits and options. A client
  never gets an unbounded search and always sees the limits that were applied.
* :class:`CandidateEvaluation` - one enumerated intervention subset and its
  re-verification through the real engine, plus its cost lines, budget check,
  assumption list and classification.
* :class:`SearchOutcome` - the persisted result of one search: baseline,
  candidates, ranking policy, honest status, limits hit and disclaimers.

The outcome carries two identities, deliberately distinct:

* ``search_id`` - execution identity (one per search execution);
* ``semantic_hash`` - identity of the semantic inputs + outcome. Two searches
  with equal inputs must reproduce it; ``id`` and timestamps are excluded
  (same rule as analysis runs, DECISIONS.md D-012/D-013).

Nothing in this module computes verdicts, routes or feasibility. Every
verification field is filled from real ``run_analysis`` output by
``optimization.verify``.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from detour_lab.domain.contracts import CandidateProposal, StrictModel
from detour_lab.domain.enums import CostProvenance, SolverStatus

__all__ = [
    "BaselineOD",
    "BaselineProfile",
    "BudgetCheck",
    "CandidateAssumption",
    "CandidateCostLine",
    "CandidateCostSummary",
    "CandidateEvaluation",
    "CandidateVerification",
    "DomainSummary",
    "ExcludedIntervention",
    "ODTransition",
    "RankingPolicy",
    "SearchBudget",
    "SearchConfig",
    "SearchOutcome",
    "SearchStatus",
]

#: Classification vocabulary. These describe the **performance of a candidate
#: against the objective**, not a legal or safety status:
#:
#: * ``certified`` - no regression, no new model-FAIL, and at least one
#:   model-confirmed restoration or a comparable confirmed-route shortening.
#:   The restoration may hold for a subset of the selected profiles; the
#:   ranking policy prefers improvements that hold for every profile.
#: * ``requires_verification`` - no regression and no new model-FAIL, but
#:   either the candidate introduces elements whose model verdicts are
#:   UNKNOWN, or every benefit exists only in the *possible* graph (unresolved
#:   evidence). An unverified element never becomes a pass, so the candidate is
#:   not certified under the model.
#: * ``no_improvement`` - evaluated against the real engine and measurably
#:   changed nothing that the objective rewards (not a failure: an honest
#:   "this suggestion does not help here").
#: * ``rejected`` - violates a hard constraint (regression, new model-FAIL,
#:   invalid precondition/effect, or an evaluation error).
CandidateClassification = Literal["certified", "requires_verification", "no_improvement", "rejected"]


class SearchBudget(StrictModel):
    """User-entered budget. No exchange rates are ever invented."""

    amount: float = Field(ge=0)
    currency: str = Field(default="INR", min_length=1, max_length=12)
    #: ``nominal`` sums nominal demo prices; ``conservative_max`` sums the
    #: declared upper bounds. The response always states which basis was used.
    basis: Literal["nominal", "conservative_max"] = "nominal"


class SearchConfig(StrictModel):
    """Explicit, auditable search limits (MASTER_PROMPT §7.3)."""

    max_interventions: int = Field(default=2, ge=1, le=4)
    max_candidates: int = Field(default=60, ge=1, le=500)
    max_duration_ms: int = Field(default=30_000, ge=1, le=600_000)
    excluded_intervention_ids: list[str] = Field(default_factory=list)
    budget: SearchBudget | None = None
    #: Monetary ranking is **off by default**: no verified price data exists in
    #: this repository, so the documented objective is monetary-free. When set
    #: to ``nominal`` the demo cost is used as a labelled tie-break only.
    monetary_objective: Literal["off", "nominal"] = "off"


class ExcludedIntervention(StrictModel):
    """Why an intervention is not in the eligible set, stated explicitly."""

    intervention_id: str
    reasons: list[str]


class DomainSummary(StrictModel):
    """Size and completeness of the enumerated domain, stated honestly."""

    eligible_intervention_ids: list[str]
    excluded_interventions: list[ExcludedIntervention]
    #: Combinations of size 1..max_interventions over the eligible set.
    domain_combination_count: int
    #: Subsets the engine actually attempted to evaluate.
    evaluated_count: int = 0
    truncated_by: list[Literal["candidate_limit", "duration_limit"]] = Field(default_factory=list)
    exhausted: bool = False
    dependency_blocked: list[dict[str, Any]] = Field(default_factory=list)
    mutually_exclusive_blocked: list[dict[str, Any]] = Field(default_factory=list)
    precondition_rejected: list[dict[str, Any]] = Field(default_factory=list)


class BaselineOD(StrictModel):
    origin_id: str
    destination_id: str
    confirmed_reachable: bool
    possibly_reachable: bool
    confirmed_distance_m: float | None = None
    possible_distance_m: float | None = None


class BaselineProfile(StrictModel):
    """The source scenario's own analysis, per selected profile (the "before")."""

    profile_id: str
    semantic_hash: str
    phase_graph_id: str
    phase_graph_hash: str
    od_results: list[BaselineOD]


class ODTransition(StrictModel):
    """One OD pair, one profile: before vs after, both from real runs."""

    origin_id: str
    destination_id: str
    before_confirmed: bool
    before_possible: bool
    after_confirmed: bool
    after_possible: bool
    before_distance_m: float | None = None
    after_distance_m: float | None = None
    #: Only set when both sides have a confirmed route; otherwise ``None``.
    #: A missing route is never treated as 0 metres.
    added_distance_m: float | None = None


class CandidateVerification(StrictModel):
    """Per-profile verification of one candidate against the source revision."""

    profile_id: str
    source_semantic_hash: str
    candidate_semantic_hash: str
    candidate_phase_graph_id: str
    candidate_phase_graph_hash: str
    od_transitions: list[ODTransition]
    #: Pair ids ``origin->destination`` confirmed after but not before, for this
    #: profile. Note per-profile restorations; the cross-profile view is on
    #: :class:`CandidateEvaluation`.
    restored_pairs: list[str]
    gained_possible_pairs: list[str]
    regressed_pairs: list[str]
    new_fail_verdicts: list[dict[str, str]]
    new_unknown_verdicts: list[dict[str, str]]
    added_distance_m: float | None = None
    comparable_route_count: int = 0


class CandidateAssumption(StrictModel):
    """A modelled state a candidate introduces (never silently absorbed)."""

    intervention_id: str
    element_id: str
    field: str
    value_display: str
    unit: str | None = None
    provenance_class: str
    verification_status: str
    note: str
    requires_field_verification: bool = True


class CandidateCostLine(StrictModel):
    intervention_id: str
    cost_id: str
    label: str
    provenance: CostProvenance
    currency: str
    quantity: float
    unit: str
    total_nominal: float | None = None
    total_max: float | None = None
    note: str = ""


class CandidateCostSummary(StrictModel):
    currency: str | None = None
    nominal: float | None = None
    maximum: float | None = None
    #: True when at least one line has no nominal/upper price, or currencies
    #: are mixed. A rendered "Not estimated" comes from this flag; the value is
    #: never fabricated into a number, and never 0.
    unknown: bool = True
    mixed_currency: bool = False
    provenance_notes: list[str] = Field(default_factory=list)
    lines: list[CandidateCostLine] = Field(default_factory=list)


class BudgetCheck(StrictModel):
    status: Literal[
        "not_requested",
        "within",
        "exceeds",
        "cannot_certify_unknown_cost",
    ]
    budget_amount: float | None = None
    budget_currency: str | None = None
    #: Which figure was compared: ``nominal`` or ``conservative_max``.
    basis: str | None = None
    detail: str = ""


class CandidateEvaluation(StrictModel):
    """One enumerated subset plus everything needed to judge and rank it."""

    proposal: CandidateProposal
    classification: CandidateClassification
    intervention_ids: list[str]
    intervention_count: int
    #: Cross-profile restoration views. Pair id format ``origin->destination``.
    restored_all_profiles: list[str] = Field(default_factory=list)
    restored_any_profile: list[str] = Field(default_factory=list)
    regressed_pairs: list[str] = Field(default_factory=list)
    verifications: list[CandidateVerification]
    assumptions: list[CandidateAssumption] = Field(default_factory=list)
    applied_phase_changes: list[dict[str, Any]] = Field(default_factory=list)
    #: Counts used by the ranking policy (kept denormalised so the persisted
    #: payload is self-describing without re-deriving from lists).
    introduced_fail_verdict_count: int = 0
    introduced_unknown_verdict_count: int = 0
    cost: CandidateCostSummary
    budget: BudgetCheck
    #: Semantic identity of the derived candidate scenario (preview, not
    #: persisted) and of its materialised phase graph.
    preview_scenario_hash: str
    preview_phase_graph_hash: str
    #: Assigned by the ranking pass; 1 is the engine's preferred candidate.
    rank: int | None = None
    pareto_optimal: bool = False
    #: Candidates equal on every *measured* ranking axis share a tie group; the
    #: proposal id still orders them deterministically within the group.
    tie_group: int | None = None
    #: Set when the candidate could not be evaluated because of an unexpected
    #: error (as opposed to a deterministic candidate-invalid rejection).
    evaluation_failure: dict[str, Any] | None = None


class RankingPolicy(StrictModel):
    """The documented, deterministic ordering. Weights: none."""

    id: str = "DETOUR_LAB_LEXICOGRAPHIC_V1"
    version: str = "1.0.0"
    monetary_default: Literal["off"] = "off"
    #: Applied in order; the first difference decides. Documented because a
    #: hidden weight would make results unauditable (MASTER_PROMPT §7.6).
    order: list[str] = Field(
        default_factory=lambda: [
            "classification_group (certified before requires_verification before no_improvement before rejected)",
            "restored_all_profiles (descending)",
            "restored_any_profile (descending)",
            "new_hard_fail_verdict_count (ascending)",
            "introduced_unknown_verdict_count (ascending)",
            "regressed_pair_count (ascending)",
            "intervention_count (ascending)",
            "monetary_estimate (ascending; only when monetary_objective=nominal; unknown after known, never 0)",
            "comparable_added_distance_m (ascending; only when routes exist on both sides; unknown after known)",
            "proposal_id (ascending, byte order)",
        ]
    )
    description: str = (
        "Lexicographic comparison over measured, model-confirmed quantities only. "
        "No weighted sum is computed and no objective can override a hard constraint: "
        "candidates that regress a confirmed/possible OD pair or add a model-FAIL verdict "
        "are rejected before ranking."
    )


class SearchStatus(StrictModel):
    solver_status: SolverStatus
    exhaustive: bool
    limits_hit: list[str] = Field(default_factory=list)
    best_proposal_id: str | None = None
    #: A phase-scoped improvement is not evidence of whole-project continuity.
    scope_note: str = (
        "Results apply to the selected phase and profile set of this scenario revision only. "
        "A single-phase improvement is not whole-project continuity."
    )
    notes: list[str] = Field(default_factory=list)


class SearchOutcome(StrictModel):
    """The persisted result of one bounded search."""

    schema_version: str = "1.0.0"
    engine_version: str
    search_id: str
    created_at: str
    duration_ms: float
    scenario_id: str
    scenario_revision: int
    scenario_content_hash: str
    base_graph_version_id: str
    base_graph_hash: str
    rulepack_id: str
    rulepack_hash: str
    phase_id: str
    profile_ids: list[str]
    evaluation_instant: str
    config: SearchConfig
    domain: DomainSummary
    baseline: list[BaselineProfile]
    candidates: list[CandidateEvaluation]
    ranking_policy: RankingPolicy
    status: SearchStatus
    input_hash: str = ""
    semantic_hash: str = ""
    disclaimers: list[str] = Field(default_factory=list)

    def semantic_body(self) -> dict[str, Any]:
        """Deterministic payload used for the semantic hash.

        Runtime metadata (execution id, wall clock, duration) is excluded, the
        same rule analysis runs use (DECISIONS.md D-012/D-013).
        """
        payload = self.model_dump(mode="json")
        for key in ("search_id", "created_at", "duration_ms"):
            payload.pop(key, None)
        return payload
