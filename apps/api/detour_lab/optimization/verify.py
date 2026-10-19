"""Authoritative candidate verification (MASTER_PROMPT §7.4, "one engine").

Every candidate is materialised as a **derived in-memory scenario** - the
source plan plus the intervention effects - and then verified by the real,
unmodified pipeline:

    materialised scenario -> run_analysis -> before/after deltas

Nothing in this module computes a verdict, a route or a feasibility state of
its own. It compares two real :class:`AnalysisResult` objects per profile and
classifies the candidate against the documented objective.

Honesty rules implemented here:

* a candidate that regresses a confirmed *or possible* OD pair is rejected;
* a candidate that introduces a new hard model-FAIL verdict for any selected
  profile is rejected (hard constraints never trade against gains);
* modelled state a candidate introduces is surfaced in ``assumptions`` with
  its provenance class, never silently absorbed;
* a missing route on either side is never turned into 0 m;
* unknown cost is ``None`` + ``unknown=True``, never 0 and never "estimated".
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from detour_lab.analysis.run import run_analysis
from detour_lab.domain.contracts import (
    AnalysisResult,
    CandidateProposal,
    Intervention,
    RulePack,
    Scenario,
)
from detour_lab.domain.enums import CostProvenance, RuleKind, SolverStatus, VerdictState
from detour_lab.domain.hashing import semantic_hash
from detour_lab.graph.model import PedestrianGraph
from detour_lab.optimization.model import (
    BudgetCheck,
    CandidateAssumption,
    CandidateCostLine,
    CandidateCostSummary,
    CandidateVerification,
    ODTransition,
    SearchBudget,
)
from detour_lab.scenarios.apply import GraphEditError

__all__ = [
    "CandidateError",
    "CandidateMaterialisation",
    "VerificationOutcome",
    "analysis_comparison_body",
    "check_budget",
    "materialise_candidate",
    "verify_candidate",
]

#: Verdict-transition lists are capped for size; counts are always exact.
_VERDICT_LIST_CAP = 100


class CandidateError(ValueError):
    """A candidate cannot be materialised or verified. Reasons are user-facing."""

    def __init__(self, reasons: list[str], *, code: str = "INVALID_CANDIDATE") -> None:
        super().__init__("; ".join(reasons) if reasons else code)
        self.reasons = reasons
        self.code = code


@dataclass(slots=True)
class CandidateMaterialisation:
    scenario: Scenario
    selected_intervention_ids: list[str]
    assumptions: list[CandidateAssumption]
    cost_lines: list[CandidateCostLine]
    cost_summary: CandidateCostSummary
    applied_phase_changes: list[dict[str, Any]]


@dataclass(slots=True)
class VerificationOutcome:
    proposal: CandidateProposal
    classification: str
    verifications: list[CandidateVerification]
    restored_all_profiles: list[str]
    restored_any_profile: list[str]
    regressed_pairs: list[str]
    gained_possible_pairs: list[str]
    introduced_fail_verdict_count: int
    introduced_unknown_verdict_count: int
    added_distance_m: float | None


def _display_value(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def analysis_comparison_body(result: AnalysisResult) -> dict[str, Any]:
    """Canonical body for preview-vs-persisted verification.

    Three fields are excluded, each for a precise reason:

    * ``scenario_id`` / ``phase_graph_id`` embed the scenario id, and promoting
      a candidate creates a new, independently addressable scenario by design;
    * ``scenario_hash`` is the scenario's own content hash, and that hash
      covers the scenario ``revision`` (immutable revisions, Gate 2). A
      promoted branch is revision 1 by definition while the preview carries the
      source's revision label, so this *label* may legitimately differ.

    Preview reproducibility is assured separately and still strictly: the
    candidate's re-materialised content hash must equal the recorded preview
    hash before anything is persisted. Everything content-based here
    (phase-graph hash, verdicts, OD results) must match exactly.
    """
    body = result.model_dump(mode="json")
    body.pop("scenario_id", None)
    body.pop("scenario_hash", None)
    body.pop("phase_graph_id", None)
    return body


def _pair_id(origin_id: str, destination_id: str) -> str:
    return f"{origin_id}->{destination_id}"


def materialise_candidate(
    source: Scenario,
    selected: list[Intervention],
) -> CandidateMaterialisation:
    """Build the derived scenario for one intervention subset.

    Raises :class:`CandidateError` with explicit reasons when the declared
    effects cannot be applied to this source plan.
    """
    ordered = sorted(selected, key=lambda i: i.id)
    reasons: list[str] = []

    # -- collect edits -----------------------------------------------------
    combined_edits: list[Any] = list(source.edits)
    assumptions: list[CandidateAssumption] = []
    for intervention in ordered:
        effect = intervention.effect
        if effect is None:  # pragma: no cover - library loader rejects enabled effectless entries
            reasons.append(f"{intervention.id}: no effect declared")
            continue
        combined_edits.extend(effect.edits)
        for edit in effect.edits:
            if edit.op == "update_attribute":
                params = edit.params
                verification_status = str(params.get("verification_status", "unverified"))
                assumptions.append(
                    CandidateAssumption(
                        intervention_id=intervention.id,
                        element_id=edit.target_id,
                        field=str(params.get("field", "")),
                        value_display=_display_value(params.get("value")),
                        unit=params.get("unit"),
                        provenance_class=str(params.get("provenance_class", "assumed")),
                        verification_status=verification_status,
                        note=str(params.get("note", "")),
                        requires_field_verification=verification_status != "verified",
                    )
                )

    # -- collect temporary edges -------------------------------------------
    combined_temporary: list[Any] = list(source.temporary_edges)
    existing_temp_ids = {t.id for t in source.temporary_edges}
    for intervention in ordered:
        effect = intervention.effect
        if effect is None:
            continue
        for temp in effect.temporary_edges:
            if temp.id in existing_temp_ids:
                reasons.append(
                    f"{intervention.id}: temporary edge {temp.id!r} is already declared by the source plan"
                )
                continue
            existing_temp_ids.add(temp.id)
            combined_temporary.append(temp)
            for record in temp.evidence:
                assumptions.append(
                    CandidateAssumption(
                        intervention_id=intervention.id,
                        element_id=temp.id,
                        field=record.field,
                        value_display=_display_value(record.value),
                        unit=record.unit,
                        provenance_class=record.provenance_class.value,
                        verification_status=record.verification_status.value,
                        note=record.note,
                        requires_field_verification=record.verification_status.value != "verified",
                    )
                )

    declared_temp_ids = {t.id for t in combined_temporary}

    # -- apply phase changes -------------------------------------------------
    phases_payload = {p.id: p.model_dump(mode="json") for p in source.phases}
    applied_phase_changes: list[dict[str, Any]] = []
    for intervention in ordered:
        effect = intervention.effect
        if effect is None:
            continue
        for change in effect.phase_changes:
            payload = phases_payload.get(change.phase_id)
            if payload is None:
                reasons.append(f"{intervention.id}: phase {change.phase_id!r} is not declared by the source plan")
                continue
            closed: list[str] = list(payload["closed_edge_ids"])
            active: list[str] = list(payload["temporary_edge_ids"])
            for edge_id in change.close_edge_ids:
                if edge_id in closed:
                    reasons.append(f"{intervention.id}: edge {edge_id!r} is already closed in {change.phase_id!r}")
                    continue
                closed.append(edge_id)
            for edge_id in change.unclose_edge_ids:
                if edge_id not in closed:
                    reasons.append(f"{intervention.id}: edge {edge_id!r} is not closed in {change.phase_id!r}")
                    continue
                closed.remove(edge_id)
            for temp_id in change.activate_temporary_edge_ids:
                if temp_id not in declared_temp_ids:
                    reasons.append(
                        f"{intervention.id}: temporary edge {temp_id!r} is not declared by the scenario "
                        "(before or after this candidate's effects)"
                    )
                    continue
                if temp_id in active:
                    reasons.append(
                        f"{intervention.id}: temporary edge {temp_id!r} is already active in {change.phase_id!r}"
                    )
                    continue
                active.append(temp_id)
            for temp_id in change.deactivate_temporary_edge_ids:
                if temp_id not in active:
                    reasons.append(
                        f"{intervention.id}: temporary edge {temp_id!r} is not active in {change.phase_id!r}"
                    )
                    continue
                active.remove(temp_id)
            payload["closed_edge_ids"] = sorted(closed)
            payload["temporary_edge_ids"] = sorted(active)
            applied_phase_changes.append(
                {
                    "intervention_id": intervention.id,
                    "phase_id": change.phase_id,
                    "closed": sorted(change.close_edge_ids),
                    "unclosed": sorted(change.unclose_edge_ids),
                    "activated": sorted(change.activate_temporary_edge_ids),
                    "deactivated": sorted(change.deactivate_temporary_edge_ids),
                }
            )

    if reasons:
        raise CandidateError(reasons)

    # -- derived scenario ----------------------------------------------------
    payload = source.model_dump(mode="json")
    payload["edits"] = [e.model_dump(mode="json") for e in combined_edits]
    payload["temporary_edges"] = [t.model_dump(mode="json") for t in combined_temporary]
    payload["phases"] = [phases_payload[p.id] for p in source.ordered_phases()]
    payload["intervention_ids"] = sorted({*source.intervention_ids, *(i.id for i in ordered)})
    payload["parent_scenario_id"] = source.id
    payload["content_hash"] = ""
    try:
        candidate = Scenario.model_validate(payload)
    except Exception as exc:  # pragma: no cover - defensive: contract errors are candidate defects
        raise CandidateError([f"derived scenario failed validation: {exc}"]) from exc

    # -- costs ---------------------------------------------------------------
    cost_lines: list[CandidateCostLine] = []
    for intervention in ordered:
        for cost in intervention.costs:
            cost_lines.append(
                CandidateCostLine(
                    intervention_id=intervention.id,
                    cost_id=cost.id,
                    label=cost.label,
                    provenance=cost.provenance,
                    currency=cost.currency,
                    quantity=cost.quantity,
                    unit=cost.unit,
                    total_nominal=cost.total_nominal,
                    total_max=cost.total_max,
                    note=cost.note,
                )
            )

    currencies = {line.currency for line in cost_lines}
    mixed_currency = len(currencies) > 1
    nominal_known = bool(cost_lines) and all(line.total_nominal is not None for line in cost_lines)
    max_known = bool(cost_lines) and all(line.total_max is not None for line in cost_lines)
    provenance_notes: list[str] = []
    for line in cost_lines:
        if line.provenance == CostProvenance.DEMO_ONLY and line.note and line.note not in provenance_notes:
            provenance_notes.append(line.note)
    if mixed_currency:
        provenance_notes.append(
            "Declared cost lines use more than one currency and no exchange rate exists; no single total is computed."
        )
    if not cost_lines:
        provenance_notes.append("No cost line is declared for this candidate; cost is not estimated.")

    summary = CandidateCostSummary(
        currency=next(iter(currencies)) if len(currencies) == 1 else None,
        nominal=(
            None
            if (mixed_currency or not nominal_known)
            else round(sum(line.total_nominal or 0.0 for line in cost_lines), 6)
        ),
        maximum=(
            None
            if (mixed_currency or not max_known)
            else round(sum(line.total_max or 0.0 for line in cost_lines), 6)
        ),
        unknown=not nominal_known or mixed_currency,
        mixed_currency=mixed_currency,
        provenance_notes=provenance_notes,
        lines=cost_lines,
    )

    assumptions.sort(key=lambda a: (a.element_id, a.field, a.intervention_id, a.value_display))
    return CandidateMaterialisation(
        scenario=candidate,
        selected_intervention_ids=[i.id for i in ordered],
        assumptions=assumptions,
        cost_lines=cost_lines,
        cost_summary=summary,
        applied_phase_changes=applied_phase_changes,
    )


def check_budget(budget: SearchBudget | None, cost: CandidateCostSummary) -> BudgetCheck:
    """Compare declared figures against the user's budget, stating the basis.

    A candidate whose cost cannot be certified is **never** silently treated as
    zero or as fitting: the check reports ``cannot_certify_unknown_cost``.
    """
    if budget is None:
        return BudgetCheck(status="not_requested")
    figure = cost.nominal if budget.basis == "nominal" else cost.maximum
    if figure is None:
        return BudgetCheck(
            status="cannot_certify_unknown_cost",
            budget_amount=budget.amount,
            budget_currency=budget.currency,
            basis=budget.basis,
            detail=(
                "No declared price exists for every line of this candidate, so a "
                f"{budget.basis} comparison cannot be certified."
            ),
        )
    if figure <= budget.amount:
        return BudgetCheck(
            status="within",
            budget_amount=budget.amount,
            budget_currency=budget.currency,
            basis=budget.basis,
            detail=f"{budget.basis} total {figure} {cost.currency} is within the budget.",
        )
    return BudgetCheck(
        status="exceeds",
        budget_amount=budget.amount,
        budget_currency=budget.currency,
        basis=budget.basis,
        detail=f"{budget.basis} total {figure} {cost.currency} exceeds the budget.",
    )


def _verdict_index(result: AnalysisResult) -> dict[tuple[str, str], Any]:
    return {(verdict.rule_id, verdict.element_id): verdict for verdict in result.verdicts}


def verify_candidate(
    *,
    source: Scenario,
    materialisation: CandidateMaterialisation,
    base_graph: PedestrianGraph,
    rulepack: RulePack,
    profile_ids: list[str],
    profiles: dict[str, Any],
    source_results: dict[str, AnalysisResult],
    phase_id: str,
    as_of: datetime,
) -> VerificationOutcome:
    """Run the real engine on the derived scenario and compute the deltas."""
    candidate_scenario = materialisation.scenario
    candidate_results: dict[str, AnalysisResult] = {}
    for profile_id in profile_ids:
        try:
            candidate_results[profile_id] = run_analysis(
                base_graph=base_graph,
                scenario=candidate_scenario,
                phase_id=phase_id,
                profile_id=profile_id,
                rulepack=rulepack,
                profile=profiles[profile_id],
                as_of=as_of,
            )
        except GraphEditError as exc:
            raise CandidateError([f"{exc.code}: {exc}"], code=exc.code) from exc

    # Pair ids are ``OD origin id -> OD destination id`` (the ids the OD results
    # report), so essentiality is checked against OD ids, not node ids.
    essential_ids = {od.id for od in source.origins_destinations if od.essential}
    essential_pairs_fallback = not essential_ids

    def pair_essential(pair_id: str) -> bool:
        if essential_pairs_fallback:
            return True
        origin, _, destination = pair_id.partition("->")
        return origin in essential_ids or destination in essential_ids

    verifications: list[CandidateVerification] = []
    restored_any: list[str] = []
    restored_everywhere: list[str] = []
    gained_possible: list[str] = []
    regressed: list[str] = []
    fail_counter: Counter[tuple[str, str, str]] = Counter()
    unknown_counter: Counter[tuple[str, str, str]] = Counter()
    total_added_distance = 0.0
    comparable_routes = 0
    per_profile_restored: dict[str, set[str]] = {}

    for profile_id in profile_ids:
        before = source_results[profile_id]
        after = candidate_results[profile_id]
        before_pairs = {_pair_id(r.origin_id, r.destination_id): r for r in before.od_results}
        after_pairs = {_pair_id(r.origin_id, r.destination_id): r for r in after.od_results}

        transitions: list[ODTransition] = []
        restored_here: set[str] = set()
        gained_here: set[str] = set()
        regressed_here: set[str] = set()
        added_here = 0.0
        comparable_here = 0

        for pair_key in sorted(set(before_pairs) | set(after_pairs)):
            b = before_pairs.get(pair_key)
            a = after_pairs.get(pair_key)
            b_conf = bool(b and b.confirmed_reachable)
            a_conf = bool(a and a.confirmed_reachable)
            b_poss = bool(b and b.possibly_reachable)
            a_poss = bool(a and a.possibly_reachable)
            b_dist = b.confirmed_distance_m if b else None
            a_dist = a.confirmed_distance_m if a else None
            added = None
            if b_dist is not None and a_dist is not None:
                added = round(a_dist - b_dist, 6)
                added_here += added
                comparable_here += 1
            if not b_conf and a_conf:
                restored_here.add(pair_key)
            elif not b_poss and a_poss and not a_conf:
                gained_here.add(pair_key)
            if (b_conf and not a_conf) or (b_poss and not a_poss):
                regressed_here.add(pair_key)
            origin_id, _, destination_id = pair_key.partition("->")
            transitions.append(
                ODTransition(
                    origin_id=origin_id,
                    destination_id=destination_id,
                    before_confirmed=b_conf,
                    before_possible=b_poss,
                    after_confirmed=a_conf,
                    after_possible=a_poss,
                    before_distance_m=b_dist,
                    after_distance_m=a_dist,
                    added_distance_m=added,
                )
            )

        # New FAIL / UNKNOWN verdicts relative to the source run.
        before_verdicts = _verdict_index(before)
        new_fails: list[dict[str, str]] = []
        new_unknowns: list[dict[str, str]] = []
        for key, verdict in _verdict_index(after).items():
            previous = before_verdicts.get(key)
            if verdict.state == VerdictState.FAIL and (previous is None or previous.state != VerdictState.FAIL):
                new_fails.append(
                    {
                        "element_id": verdict.element_id,
                        "rule_id": verdict.rule_id,
                        "profile_id": profile_id,
                        "rule_kind": verdict.rule_kind.value,
                        "criticality": verdict.criticality.value,
                    }
                )
                if verdict.rule_kind == RuleKind.HARD:
                    fail_counter[(verdict.rule_id, verdict.element_id, profile_id)] += 1
            if verdict.state == VerdictState.UNKNOWN and (
                previous is None or previous.state != VerdictState.UNKNOWN
            ):
                new_unknowns.append(
                    {
                        "element_id": verdict.element_id,
                        "rule_id": verdict.rule_id,
                        "profile_id": profile_id,
                    }
                )
                unknown_counter[(verdict.rule_id, verdict.element_id, profile_id)] += 1

        per_profile_restored[profile_id] = restored_here
        restored_any.extend(sorted(p for p in restored_here if p not in restored_any))
        gained_possible.extend(sorted(p for p in gained_here if p not in gained_possible))
        regressed.extend(sorted(p for p in regressed_here if p not in regressed))
        total_added_distance += added_here
        comparable_routes += comparable_here

        verifications.append(
            CandidateVerification(
                profile_id=profile_id,
                source_semantic_hash=semantic_hash(analysis_comparison_body(before)),
                candidate_semantic_hash=semantic_hash(analysis_comparison_body(after)),
                candidate_phase_graph_id=after.phase_graph_id,
                candidate_phase_graph_hash=after.phase_graph_hash,
                od_transitions=transitions,
                restored_pairs=sorted(restored_here),
                gained_possible_pairs=sorted(gained_here),
                regressed_pairs=sorted(regressed_here),
                new_fail_verdicts=new_fails[:_VERDICT_LIST_CAP],
                new_unknown_verdicts=new_unknowns[:_VERDICT_LIST_CAP],
                added_distance_m=round(added_here, 6) if comparable_here else None,
                comparable_route_count=comparable_here,
            )
        )

    # Cross-profile restoration view: a pair counts as restored across all
    # selected profiles when the candidate confirms it for *every* selected
    # profile and the source did not.
    candidate_confirmed_everywhere: dict[str, bool] = {}
    before_confirmed_everywhere: dict[str, bool] = {}
    for profile_id in profile_ids:
        before_map = {_pair_id(r.origin_id, r.destination_id): r for r in source_results[profile_id].od_results}
        after_map = {_pair_id(r.origin_id, r.destination_id): r for r in candidate_results[profile_id].od_results}
        for pair_key, result in after_map.items():
            candidate_confirmed_everywhere[pair_key] = candidate_confirmed_everywhere.get(
                pair_key, True
            ) and bool(result.confirmed_reachable)
        for pair_key, result in before_map.items():
            before_confirmed_everywhere[pair_key] = before_confirmed_everywhere.get(
                pair_key, True
            ) and bool(result.confirmed_reachable)
    for pair_key in sorted(candidate_confirmed_everywhere):
        if candidate_confirmed_everywhere[pair_key] and not before_confirmed_everywhere.get(pair_key, False):
            restored_everywhere.append(pair_key)

    added_distance: float | None = round(total_added_distance, 6) if comparable_routes else None
    hard_fail_count = sum(fail_counter.values())
    unknown_count = sum(unknown_counter.values())

    proposal_id = "cand-" + semantic_hash(
        {
            "candidate_scenario_hash": candidate_scenario.content_hash,
            "phase_id": phase_id,
            "intervention_ids": materialisation.selected_intervention_ids,
        }
    ).split(":")[-1][:12]

    rejection_reasons: list[str] = []
    if regressed:
        rejection_reasons.append(
            "regresses OD pair(s) " + ", ".join(regressed[:10]) + " vs the source plan"
        )
    if hard_fail_count:
        samples = ", ".join(
            f"{element}::{rule} ({profile})"
            for (rule, element, profile) in sorted(fail_counter)[:5]
        )
        rejection_reasons.append(
            f"introduces {hard_fail_count} new hard model-FAIL verdict(s), e.g. {samples}"
        )

    classification: str
    if rejection_reasons:
        classification = "rejected"
    elif unknown_count:
        # The candidate itself introduces elements whose verdicts are UNKNOWN.
        # Any confirmed restorations may still be real, but the candidate as a
        # whole cannot be certified: an unverified element never becomes a pass
        # (FR-009). It is reported as needing verification, with the count.
        classification = "requires_verification"
    elif restored_everywhere or restored_any or (added_distance is not None and added_distance < -1e-9):
        classification = "certified"
    elif gained_possible:
        classification = "requires_verification"
    else:
        classification = "no_improvement"

    failed_profiles = sorted({v.profile_id for v in verifications if v.regressed_pairs or v.new_fail_verdicts})
    passed_profiles = sorted(pid for pid in profile_ids if pid not in failed_profiles)

    proposal = CandidateProposal(
        proposal_id=proposal_id,
        intervention_ids=materialisation.selected_intervention_ids,
        eligible=classification != "rejected",
        rejection_reasons=rejection_reasons,
        restored_required_od=any(pair_essential(p) for p in restored_everywhere),
        requires_verification=classification == "requires_verification",
        passed_profiles=passed_profiles,
        failed_profiles=failed_profiles,
        cost_nominal=materialisation.cost_summary.nominal,
        cost_max=materialisation.cost_summary.maximum,
        cost_unknown=materialisation.cost_summary.unknown,
        added_distance_m=added_distance,
        solver_status=(
            SolverStatus.INVALID_INPUT
            if classification == "rejected"
            else SolverStatus.INCOMPLETE_OR_UNKNOWN
            if classification == "requires_verification"
            else SolverStatus.FEASIBLE_NOT_PROVEN_OPTIMAL
        ),
    )

    return VerificationOutcome(
        proposal=proposal,
        classification=classification,
        verifications=verifications,
        restored_all_profiles=restored_everywhere,
        restored_any_profile=restored_any,
        regressed_pairs=regressed,
        gained_possible_pairs=gained_possible,
        introduced_fail_verdict_count=hard_fail_count,
        introduced_unknown_verdict_count=unknown_count,
        added_distance_m=added_distance,
    )
