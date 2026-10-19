"""Deterministic derivation of the evidence-verification queue (Gate 6).

Scope, stated precisely
-----------------------
The queue answers exactly one question:

    *Which attributes can the authoritative resolver not determine for at least
     one rule that is in scope for the selected phase(s) and mobility
     profile(s), and how does each one relate to the selected decision?*

It is derived, never authored. There is no static list, no stored queue, and no
patch operation. Changing the evidence, the rulepack, the scenario revision or
the profile selection changes the queue because the queue is recomputed from the
same authoritative inputs the engine used for the analysis itself.

Everything reported here is read from real objects:

* unresolved status comes from :func:`detour_lab.evidence.resolver.resolve_attribute`
  - the queue never re-implements, approximates or second-guesses the resolver;
* rule linkage comes from the real :class:`RuleVerdict` list of the analysis;
* origin-destination linkage comes from the real :class:`ODPairResult` list,
  including the engine's counterexample-proven ``blocking_finding_ids``.

What it deliberately does **not** do
-------------------------------------
* It does not claim a probability that resolving the attribute would change a
  result, and it does not emit a numeric priority. No Bayesian
  value-of-information is computed, so none is implied.
* It never converts an unresolved attribute into a known value, and it never
  marks an entry verified.
* An unresolved attribute is not a physical defect. Missing evidence means the
  model cannot determine the condition; it is not proof that a kerb, path or
  crossing is unusable, and the queue wording never says so.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Any

from detour_lab import ENGINE_VERSION
from detour_lab.domain.contracts import AnalysisResult, EvidenceRecord, RulePack, Scenario
from detour_lab.domain.enums import ReasonCode, VerdictState
from detour_lab.domain.hashing import semantic_hash
from detour_lab.evidence.model import (
    CONFLICT_EXPLANATIONS,
    CRITICALITY_ORDER,
    EVIDENCE_STATUS_LABELS,
    EvidenceConflictReport,
    EvidenceCriticality,
    EvidenceIssue,
    EvidenceIssuePair,
    EvidenceQueue,
    EvidenceQueueScope,
    ObservationComparison,
)
from detour_lab.evidence.resolver import EvidenceRegistry, resolve_attribute
from detour_lab.graph.model import PedestrianGraph
from detour_lab.scenarios.apply import build_phase_graph

__all__ = [
    "ORDERING_RULE",
    "PRIORITIZATION_METHOD",
    "derive_evidence_queue",
    "explain_attribute",
    "filter_issues",
]

#: Documented, stable ordering. Primary key is the explainable category; the
#: remaining keys are deterministic tie-breakers, never a relevance score.
ORDERING_RULE = (
    "ascending(decision_blocking < decision_relevant < supporting), then descending count of "
    "affected profiles, descending count of affected phases, descending count of connected "
    "origin-destination pairs, ascending element_id, ascending attribute"
)

PRIORITIZATION_METHOD = (
    "Evidence-backed decision relevance. Categories are derived from demonstrated relationships "
    "in the authoritative analysis (demonstrated blocker on a not-confirmed pair, presence on a "
    "confirmed route, breadth across selected profiles and declared phases). No probability, no "
    "expected value and no numeric score is computed, and none should be inferred from the "
    "category ordering."
)

_QUEUE_LIMITATIONS = (
    "Every queue entry describes an attribute the model cannot resolve. It does not assert that the "
    "physical element is unsuitable.",
    "Prioritisation is a deterministic relevance ordering over modelled relationships. It is not a "
    "value of information and carries no probability that a field visit would succeed.",
    "Only the selected phase(s) and profile(s) are analysed. Attributes unresolved only under a "
    "different selection are not listed.",
)


# --------------------------------------------------------------------------- helpers


def _to_comparison(record: EvidenceRecord, conversion: dict[str, Any] | None) -> ObservationComparison:
    """Present one observation with its provenance and any recorded conversion."""
    return ObservationComparison(
        evidence_id=record.id,
        value=record.value,
        unit=record.unit,
        method=record.method,
        source=record.source,
        source_url=record.source_url,
        observed_at=record.observed_at.isoformat() if record.observed_at else None,
        verification_status=record.verification_status.value,
        quality=record.quality,
        reviewer=record.reviewer,
        provenance_class=record.provenance_class.value,
        synthetic=record.synthetic,
        invalidated=record.invalidated,
        note=record.note,
        conversion=conversion,
    )


def _finding_elements(result: AnalysisResult) -> dict[str, str]:
    """Map ``finding_id -> element_id`` from the stored analysis result."""
    mapping: dict[str, str] = {}
    for edge_evaluation in result.edge_evaluations:
        for finding in edge_evaluation.findings:
            mapping[finding.id] = finding.element_id
    return mapping


def _incident_elements(graph: PedestrianGraph, element_id: str) -> set[str]:
    """Elements whose traversal state can be affected by ``element_id``.

    A node attribute propagates to every edge incident to that node (the rule
    engine folds endpoint states into edge eligibility), and an edge attribute
    propagates to its two endpoint nodes. This is a *structural* relationship
    read from the graph, not an inference about causation.
    """
    node = graph.node(element_id)
    if node is not None:
        return {element_id} | set(graph.outgoing_edge_ids(node.id)) | set(graph.incoming_edge_ids(node.id))
    edge = graph.edge(element_id)
    if edge is not None:
        return {element_id, edge.u, edge.v}
    return {element_id}


def _pair_id(origin_id: str, destination_id: str) -> str:
    return f"{origin_id}->{destination_id}"


# --------------------------------------------------------------------------- derivation


def derive_evidence_queue(
    *,
    graph: PedestrianGraph,
    scenario: Scenario,
    rulepack: RulePack,
    results_by_phase_profile: dict[tuple[str, str], AnalysisResult],
    phase_ids: Sequence[str],
    profile_ids: Sequence[str],
    as_of: datetime,
    project_id: str,
    dataset_notice: str = "",
    additional_phases: Sequence[str] = (),
) -> EvidenceQueue:
    """Derive the ordered, deterministic evidence-verification queue.

    ``results_by_phase_profile`` must contain an authoritative
    :class:`AnalysisResult` for every ``(phase_id, profile_id)`` in scope; those
    results are the only source of rule and origin-destination linkage.
    """
    phase_ids = list(phase_ids)
    profile_ids = list(profile_ids)

    # -- 1. Collect every unresolved (element, attribute) the engine actually hit.
    # Only attributes that a rule in scope asked for are in scope: an attribute
    # no rule reads can never change a verdict, so listing it would be noise.
    unresolved: dict[tuple[str, str], dict[str, Any]] = {}
    for phase_id in phase_ids:
        for profile_id in profile_ids:
            result = results_by_phase_profile[(phase_id, profile_id)]
            for verdict in result.verdicts:
                if verdict.state is VerdictState.NOT_APPLICABLE:
                    continue
                for attribute in verdict.inputs:
                    if attribute.known:
                        continue
                    key = (attribute.element_id, attribute.field)
                    entry = unresolved.setdefault(
                        key,
                        {
                            "rule_ids": set(),
                            "profile_ids": set(),
                            "phase_ids": set(),
                            "has_known_failure": False,
                        },
                    )
                    entry["rule_ids"].add(verdict.rule_id)
                    entry["profile_ids"].add(profile_id)
                    entry["phase_ids"].add(phase_id)
                    if verdict.state is VerdictState.FAIL:
                        entry["has_known_failure"] = True

    # -- 2. Resolve each attribute against every selected phase's own graph.
    # Phase graphs are independent snapshots (INV: phase independence), so the
    # same (element, attribute) can be resolved in one phase and not another.
    registries: dict[str, EvidenceRegistry] = {}
    for phase_id in phase_ids:
        registries[phase_id] = build_phase_graph(graph, scenario, phase_id).graph.evidence_registry
    cross_phase_registries: dict[str, EvidenceRegistry] = {}
    for phase_id in additional_phases:
        if phase_id in phase_ids:
            continue
        try:
            cross_phase_registries[phase_id] = build_phase_graph(graph, scenario, phase_id).graph.evidence_registry
        except Exception:  # pragma: no cover - an unbuildable extra phase simply is not inspected
            continue

    issues: list[EvidenceIssue] = []
    for (element_id, attribute_name), entry in sorted(unresolved.items()):
        issue = _build_issue(
            graph=graph,
            rulepack=rulepack,
            element_id=element_id,
            attribute_name=attribute_name,
            registries=registries,
            cross_phase_registries=cross_phase_registries,
            results_by_phase_profile=results_by_phase_profile,
            phase_ids=phase_ids,
            profile_ids=profile_ids,
            as_of=as_of,
            rule_ids=entry["rule_ids"],
            affected_profile_ids=entry["profile_ids"],
            affected_phase_ids=entry["phase_ids"],
            has_known_failure=entry["has_known_failure"],
            scenario=scenario,
            project_id=project_id,
            dataset_notice=dataset_notice,
        )
        issues.append(issue)

    issues = filter_issues(issues, statuses=None, profile_ids=None, phase_ids=None, criticalities=None)
    issues.sort(key=_issue_sort_key)

    counts_by_status: dict[str, int] = {}
    counts_by_criticality: dict[str, int] = {}
    for issue in issues:
        counts_by_status[issue.resolution_status] = counts_by_status.get(issue.resolution_status, 0) + 1
        counts_by_criticality[issue.criticality] = counts_by_criticality.get(issue.criticality, 0) + 1

    return EvidenceQueue(
        engine_version=ENGINE_VERSION,
        scope=EvidenceQueueScope(
            scenario_id=scenario.id,
            scenario_revision=scenario.revision,
            scenario_content_hash=scenario.content_hash,
            project_id=project_id,
            phase_ids=phase_ids,
            profile_ids=profile_ids,
            rulepack_id=rulepack.id,
            rulepack_version=rulepack.version,
            rulepack_hash=rulepack.content_hash,
            evaluation_instant=as_of.isoformat(),
            additional_phases_inspected=sorted(cross_phase_registries),
        ),
        issues=issues,
        counts_by_status=dict(sorted(counts_by_status.items())),
        counts_by_criticality=dict(sorted(counts_by_criticality.items())),
        total_unresolved_attributes_scanned=len(unresolved),
        ordering_rule=ORDERING_RULE,
        prioritization_method=PRIORITIZATION_METHOD,
        limitations=list(_QUEUE_LIMITATIONS),
    )


def _issue_sort_key(issue: EvidenceIssue) -> tuple[Any, ...]:
    return (
        CRITICALITY_ORDER[issue.criticality],
        -len(issue.affected_profile_ids),
        -len(issue.affected_phase_ids),
        -issue.od_pair_count,
        issue.element_id,
        issue.attribute,
    )


def _build_issue(
    *,
    graph: PedestrianGraph,
    rulepack: RulePack,
    element_id: str,
    attribute_name: str,
    registries: dict[str, EvidenceRegistry],
    cross_phase_registries: dict[str, EvidenceRegistry],
    results_by_phase_profile: dict[tuple[str, str], AnalysisResult],
    phase_ids: Sequence[str],
    profile_ids: Sequence[str],
    as_of: datetime,
    rule_ids: set[str],
    affected_profile_ids: set[str],
    affected_phase_ids: set[str],
    has_known_failure: bool,
    scenario: Scenario,
    project_id: str,
    dataset_notice: str,
) -> EvidenceIssue:
    spec = rulepack.attributes.get(attribute_name)
    if spec is None:  # pragma: no cover - a verdict can only reference a declared attribute
        raise KeyError(f"rulepack {rulepack.id!r} does not declare attribute {attribute_name!r}")

    # Authoritative status: re-resolved in *every* selected phase, because phase
    # graphs are independent snapshots and the same attribute can be resolvable
    # in one phase and unresolved in another. The reported status is the first
    # unresolved one in declared phase order, so the value is deterministic and
    # is always one of the five evidence conditions rather than RULE_PASS.
    resolutions: dict[str, Any] = {}
    for phase_id in phase_ids:
        registry = registries[phase_id]
        resolutions[phase_id] = (
            resolve_attribute(
                element_id=element_id,
                field=attribute_name,
                records=registry.for_field(element_id, attribute_name),
                spec=spec,
                as_of=as_of,
            ),
            registry,
        )

    unresolved_phase = next(
        (phase_id for phase_id in phase_ids if not resolutions[phase_id][0].known),
        None,
    )
    if unresolved_phase is None:  # pragma: no cover - entries are built only from unresolved inputs
        unresolved_phase = phase_ids[0]
    resolved, primary_registry = resolutions[unresolved_phase]
    records = list(primary_registry.for_field(element_id, attribute_name))
    affected_phase_ids.update(phase_id for phase_id in phase_ids if not resolutions[phase_id][0].known)

    conversions = {c["evidence_id"]: c for c in resolved.conversions if "evidence_id" in c}
    observations = [_to_comparison(r, conversions.get(r.id)) for r in records]

    # Cross-phase detection re-runs the resolver against the other phase's own
    # snapshot. It deliberately does NOT short-circuit on "no records here":
    # an attribute with no observation at all is unresolved in that phase too,
    # and skipping it would hide exactly the case worth reporting.
    for phase_id, registry in sorted(cross_phase_registries.items()):
        other = resolve_attribute(
            element_id=element_id,
            field=attribute_name,
            records=registry.for_field(element_id, attribute_name),
            spec=spec,
            as_of=as_of,
        )
        if not other.known:
            affected_phase_ids.add(phase_id)

    element_set = _incident_elements(graph, element_id)
    pairs = _connected_pairs(
        results_by_phase_profile=results_by_phase_profile,
        element_set=element_set,
        affected_profiles=set(affected_profile_ids),
    )

    rationale, criticality = _classify(
        pairs=pairs,
        element_set=element_set,
        affected_profiles=set(affected_profile_ids),
        affected_phases=set(affected_phase_ids),
        selected_phase_ids=set(phase_ids),
        has_known_failure=has_known_failure,
    )

    status_value = resolved.reason_code.value if resolved.reason_code else ReasonCode.NO_EVIDENCE.value
    # Identity describes the *problem*, not the context it was observed in. The
    # affected-phase list is derived and can widen as more phases are inspected,
    # so it is deliberately excluded: the same unresolved attribute keeps one
    # stable issue id regardless of how broad the reviewer's selection was.
    issue_id = "EQ-" + semantic_hash(
        {
            "scenario_content_hash": scenario.content_hash,
            "element_id": element_id,
            "attribute": attribute_name,
            "resolution_status": status_value,
            "profile_ids": sorted(affected_profile_ids),
            "evidence_ids": sorted(r.id for r in records),
        }
    ).split(":")[-1][:12]

    edge = graph.edge(element_id)
    node = graph.node(element_id)
    element_name = (edge.name if edge else node.name if node else "") or element_id

    return EvidenceIssue(
        issue_id=issue_id,
        scope=(
            f"phase {', '.join(sorted(affected_phase_ids)) or unresolved_phase} | "
            f"profile(s) {', '.join(sorted(affected_profile_ids)) or ', '.join(sorted(profile_ids))}"
        ),
        resolution_status=ReasonCode(status_value),
        status_label=EVIDENCE_STATUS_LABELS.get(
            status_value, "Unresolved attribute - see the resolver explanation"
        ),
        element_id=element_id,
        element_kind="edge" if edge is not None else "node",
        element_name=element_name,
        attribute=attribute_name,
        edge_u=edge.u if edge else None,
        edge_v=edge.v if edge else None,
        edge_length_m=edge.length_m if edge else None,
        edge_type=edge.edge_type.value if edge else None,
        node_x=node.x if node else None,
        node_y=node.y if node else None,
        node_type=node.node_type.value if node else None,
        rule_ids=sorted(rule_ids),
        affected_profile_ids=sorted(affected_profile_ids),
        affected_phase_ids=sorted(affected_phase_ids),
        observations=observations,
        evidence_record_ids=sorted(r.id for r in records),
        recorded_measurement=resolved.value if resolved.known else None,
        missing_or_conflicting=_missing_or_conflicting(status_value, records),
        investigation_target=_investigation_target(status_value, element_id, element_name, attribute_name),
        od_pairs=pairs,
        od_pair_count=len(pairs),
        criticality=criticality,
        criticality_rationale=rationale,
        element_has_known_failure=has_known_failure,
        dataset_notice=dataset_notice,
    )


def _connected_pairs(
    *,
    results_by_phase_profile: dict[tuple[str, str], AnalysisResult],
    element_set: set[str],
    affected_profiles: set[str],
) -> list[EvidenceIssuePair]:
    """Link the unresolved attribute to real origin-destination outcomes."""
    pairs: list[EvidenceIssuePair] = []
    for (phase_id, profile_id), result in sorted(results_by_phase_profile.items()):
        if profile_id not in affected_profiles:
            continue
        finding_elements = _finding_elements(result)
        for od in result.od_results:
            role: str | None = None
            if any(
                finding_elements.get(fid) in element_set for fid in od.blocking_finding_ids
            ):
                role = "blocking"
            elif od.confirmed_reachable and element_set & set(od.confirmed_path_edge_ids):
                role = "on_confirmed_route"
            elif od.possibly_reachable and element_set & set(od.possible_path_edge_ids):
                role = "on_possible_route"
            elif any(finding_elements.get(fid) in element_set for fid in od.relevant_finding_ids):
                role = "relevant"
            if role is None:
                continue
            pairs.append(
                EvidenceIssuePair(
                    pair_id=_pair_id(od.origin_id, od.destination_id),
                    origin_id=od.origin_id,
                    destination_id=od.destination_id,
                    profile_id=profile_id,
                    role=role,  # type: ignore[arg-type]
                    confirmed_reachable=od.confirmed_reachable,
                    possibly_reachable=od.possibly_reachable,
                    confirmed_distance_m=od.confirmed_distance_m,
                    phase_id=phase_id,
                )
            )
    return sorted(pairs, key=lambda p: (p.phase_id, p.profile_id, p.pair_id, p.role))


def _classify(
    *,
    pairs: list[EvidenceIssuePair],
    element_set: set[str],
    affected_profiles: set[str],
    affected_phases: set[str],
    selected_phase_ids: set[str],
    has_known_failure: bool,
) -> tuple[list[str], EvidenceCriticality]:
    """Assign an explainable category plus the reasons that produced it.

    The decision is made from relationships that already exist in the computed
    analysis. Nothing is estimated.
    """
    rationale: list[str] = []
    blocking_pairs = sorted(
        {p.pair_id for p in pairs if p.role == "blocking" and not p.confirmed_reachable}
    )
    confirmed_route_pairs = sorted({p.pair_id for p in pairs if p.role == "on_confirmed_route"})
    possible_only_pairs = sorted(
        {
            p.pair_id
            for p in pairs
            if p.role == "on_possible_route" and not p.confirmed_reachable
        }
    )
    relevant_pairs = sorted({p.pair_id for p in pairs if p.role == "relevant"})

    if blocking_pairs:
        rationale.append(
            "The current analysis demonstrated this element as a blocking finding for "
            f"{len(blocking_pairs)} origin-destination pair(s) that are NOT model-confirmed reachable "
            f"({', '.join(blocking_pairs[:6])}). Resolving it is the difference between a determined "
            "and an undetermined result for those pairs."
        )
    if confirmed_route_pairs:
        rationale.append(
            "The element lies on a route that is currently model-confirmed for "
            f"{len(confirmed_route_pairs)} origin-destination pair(s) "
            f"({', '.join(confirmed_route_pairs[:6])}); an unresolved attribute there can withdraw "
            "a confirmation the plan currently relies on."
        )
    if possible_only_pairs:
        rationale.append(
            "The element lies on a possible-only (hypothetical) route for "
            f"{len(possible_only_pairs)} pair(s) ({', '.join(possible_only_pairs[:6])}); resolving it "
            "is what would move those pairs from possible-only toward confirmed."
        )
    if len(affected_profiles) > 1:
        rationale.append(
            f"The attribute is unresolved for {len(affected_profiles)} selected mobility profiles "
            f"({', '.join(sorted(affected_profiles))}), so a single observation affects every "
            "profile conclusion drawn from it."
        )
    extra_phases = sorted(affected_phases - selected_phase_ids)
    if extra_phases:
        rationale.append(
            f"The same attribute is also unresolved in declared phase(s) {', '.join(extra_phases)}, "
            "so the gap is not confined to the phase being reviewed."
        )
    if relevant_pairs and not (blocking_pairs or confirmed_route_pairs or possible_only_pairs):
        rationale.append(
            "The element carries a finding relevant to "
            f"{len(relevant_pairs)} origin-destination pair(s) "
            f"({', '.join(relevant_pairs[:6])}). Relevance is structural: the engine has not "
            "demonstrated that this element is the cause of any specific unreachable pair."
        )
    if has_known_failure:
        rationale.append(
            "The same element already carries a known model failure. The known failure does not "
            "resolve this attribute and must not be allowed to hide it; both states stay visible."
        )
    if not rationale:
        rationale.append(
            "The attribute is unresolved for a rule in scope, but no selected origin-destination "
            "outcome is currently linked to it and it affects a single selected profile and phase. "
            "It is still recorded because the rule genuinely cannot return a determined result "
            "without it."
        )

    if blocking_pairs or confirmed_route_pairs or possible_only_pairs or len(affected_profiles) > 1:
        category = (
            EvidenceCriticality.DECISION_BLOCKING if blocking_pairs else EvidenceCriticality.DECISION_RELEVANT
        )
    else:
        category = EvidenceCriticality.SUPPORTING
    _ = element_set  # kept for call-site clarity; pairs already encode the element linkage
    return rationale, category


def _missing_or_conflicting(status_value: str, records: Sequence[EvidenceRecord]) -> str:
    count = len(records)
    if status_value == ReasonCode.NO_EVIDENCE.value:
        return "No eligible observation exists for this attribute."
    if status_value == ReasonCode.CONFLICTING_EVIDENCE.value:
        return f"{count} eligible observation(s) disagree after canonical unit conversion; all are retained."
    if status_value == ReasonCode.UNSUPPORTED_UNIT.value:
        return f"{count} observation(s) recorded; at least one cannot be read in the canonical unit."
    if status_value == ReasonCode.EVIDENCE_EXPIRED.value:
        return f"{count} observation(s) recorded; the applicable freshness policy cannot be satisfied."
    if status_value == ReasonCode.EVIDENCE_NOT_VERIFIED.value:
        return f"{count} observation(s) recorded; the rulepack requires a verified observation."
    return f"{count} observation(s) recorded; the resolver cannot return a determined value."


def _investigation_target(status_value: str, element_id: str, element_name: str, attribute: str) -> str:
    label = element_name if element_name != element_id else element_id
    targets = {
        ReasonCode.NO_EVIDENCE.value: (
            f"Obtain and record one {attribute} observation for {label} ({element_id}) with its unit, "
            "collection method and provenance. Until then the check stays unknown."
        ),
        ReasonCode.CONFLICTING_EVIDENCE.value: (
            f"Have a reviewer resolve the conflicting {attribute} observations for {label} "
            f"({element_id}) with an explicit decision and provenance. No automatic selection is "
            "available."
        ),
        ReasonCode.UNSUPPORTED_UNIT.value: (
            f"Re-observe {attribute} on {label} ({element_id}) in a unit the rulepack declares for "
            "that attribute."
        ),
        ReasonCode.EVIDENCE_EXPIRED.value: (
            f"Re-observe {attribute} on {label} ({element_id}); the recorded observation is outside "
            "the declared freshness policy."
        ),
        ReasonCode.EVIDENCE_NOT_VERIFIED.value: (
            f"Review and verify the recorded {attribute} observation for {label} ({element_id}). "
            "Entering the value again does not verify it."
        ),
    }
    return targets.get(
        status_value,
        f"Resolve the {attribute} evidence for {label} ({element_id}) so the rule can return a "
        "determined result.",
    )


# --------------------------------------------------------------------------- filtering


def filter_issues(
    issues: Iterable[EvidenceIssue],
    *,
    statuses: Iterable[str] | None,
    profile_ids: Iterable[str] | None,
    phase_ids: Iterable[str] | None,
    criticalities: Iterable[str] | None,
) -> list[EvidenceIssue]:
    """Filter without reordering. Applied after the deterministic sort."""
    status_filter = {s.upper() for s in statuses} if statuses else None
    profile_filter = set(profile_ids) if profile_ids else None
    phase_filter = set(phase_ids) if phase_ids else None
    criticality_filter = set(criticalities) if criticalities else None

    result: list[EvidenceIssue] = []
    for issue in issues:
        if status_filter is not None and issue.resolution_status.value not in status_filter:
            continue
        if profile_filter is not None and not (profile_filter & set(issue.affected_profile_ids)):
            continue
        if phase_filter is not None and not (phase_filter & set(issue.affected_phase_ids)):
            continue
        if criticality_filter is not None and issue.criticality not in criticality_filter:
            continue
        result.append(issue)
    return result


# --------------------------------------------------------------------------- G6-04


def explain_attribute(
    *,
    graph: PedestrianGraph,
    rulepack: RulePack,
    element_id: str,
    field: str,
    as_of: datetime,
) -> EvidenceConflictReport:
    """Explain why one attribute is unresolved, without choosing a value."""
    spec = rulepack.attributes.get(field)
    if spec is None:
        raise KeyError(f"rulepack {rulepack.id!r} does not declare attribute {field!r}")
    registry = graph.evidence_registry
    records = list(registry.for_field(element_id, field))
    resolved = resolve_attribute(
        element_id=element_id, field=field, records=records, spec=spec, as_of=as_of
    )
    conversions = {c["evidence_id"]: c for c in resolved.conversions if "evidence_id" in c}
    status_value = resolved.reason_code.value if resolved.reason_code else ReasonCode.NO_EVIDENCE.value
    needs_field_work = status_value in {
        ReasonCode.NO_EVIDENCE.value,
        ReasonCode.CONFLICTING_EVIDENCE.value,
        ReasonCode.UNSUPPORTED_UNIT.value,
        ReasonCode.EVIDENCE_EXPIRED.value,
        ReasonCode.EVIDENCE_NOT_VERIFIED.value,
    }
    return EvidenceConflictReport(
        element_id=element_id,
        attribute=field,
        resolution_status=ReasonCode(status_value),
        resolved=resolved.known,
        canonical_value=resolved.value,
        canonical_unit=resolved.canonical_unit,
        explanation=resolved.explanation or CONFLICT_EXPLANATIONS.get(status_value, ""),
        observations=[_to_comparison(r, conversions.get(r.id)) for r in records],
        distinct_values=list(resolved.conflicting_values),
        resolution_requirement=CONFLICT_EXPLANATIONS.get(status_value, ""),
        can_be_resolved_without_field_work=not needs_field_work,
    )