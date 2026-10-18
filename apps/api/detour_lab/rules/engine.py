"""Declarative, deterministic rule evaluation.

Four-valued verdicts (PRD FR-008, MASTER_PROMPT §5.3):

``PASS``              every required check of an applicable rule passed
``FAIL``              at least one independently known value violates the rule
``UNKNOWN``           no known violation, but a required attribute is unresolved
``NOT_APPLICABLE``    the rule was *proved* inapplicable to this element

The FAIL-before-UNKNOWN ordering is deliberate: a known violation must stay
visible even when another attribute of the same rule is unknown, and unknown
findings are never hidden behind an aggregate Fail.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from detour_lab.domain.contracts import (
    Edge,
    Finding,
    Node,
    ResolvedAttribute,
    Rule,
    RuleCheck,
    RulePack,
    RuleVerdict,
)
from detour_lab.domain.enums import (
    Operator,
    ReasonCode,
    RuleKind,
    RuleScope,
    VerdictState,
)
from detour_lab.evidence.resolver import EvidenceRegistry, resolve_attribute
from detour_lab.graph.model import PedestrianGraph

__all__ = [
    "TraversalEvaluation",
    "evaluate_graph",
    "evaluate_rule",
    "load_rulepack",
    "rule_applies_to_edge",
    "rule_applies_to_node",
    "rules_for",
]


def load_rulepack(path: str | Path) -> RulePack:
    """Load a declarative rulepack from JSON. No code is executed from the file."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return RulePack.model_validate(payload)


def rules_for(rulepack: RulePack, scope: RuleScope, profile_id: str) -> list[Rule]:
    """Rules in canonical order for one scope/profile pair."""
    selected = [
        rule
        for rule in rulepack.rules
        if rule.scope is scope and ("*" in rule.profiles or profile_id in rule.profiles)
    ]
    return sorted(selected, key=lambda r: r.id)


def rule_applies_to_edge(rule: Rule, edge: Edge) -> bool:
    if rule.scope is not RuleScope.EDGE:
        return False
    return not rule.applies_to_edge_types or edge.edge_type in rule.applies_to_edge_types


def rule_applies_to_node(rule: Rule, node: Node) -> bool:
    if rule.scope is not RuleScope.NODE:
        return False
    return not rule.applies_to_node_types or node.node_type in rule.applies_to_node_types


def _compare(check: RuleCheck, resolved: ResolvedAttribute) -> bool:
    """Apply one whitelisted operator. Callers guarantee ``resolved.known``."""
    value = resolved.value
    match check.operator:
        case Operator.EXISTS:
            return value is not None
        case Operator.ONE_OF:
            options = {str(v).strip().lower() for v in check.values}
            return str(value).strip().lower() in options
        case Operator.EQ | Operator.GTE | Operator.GT | Operator.LTE | Operator.LT:
            if not isinstance(value, int | float):
                return False
            threshold = check.threshold
            assert threshold is not None  # guaranteed by RuleCheck validation
            match check.operator:
                case Operator.EQ:
                    return float(value) == threshold
                case Operator.GTE:
                    return float(value) >= threshold
                case Operator.GT:
                    return float(value) > threshold
                case Operator.LTE:
                    return float(value) <= threshold
                case _:
                    return float(value) < threshold
    return False  # pragma: no cover - Operator is exhaustive above


def evaluate_rule(
    *,
    rule: Rule,
    element: Edge | Node,
    registry: EvidenceRegistry,
    rulepack: RulePack,
    profile_id: str,
    phase_id: str,
    as_of: datetime | None = None,
) -> RuleVerdict | None:
    """Evaluate one rule against one element.

    Returns ``None`` when the rule does not apply at all, so callers can
    distinguish "no verdict" from a genuine ``NOT_APPLICABLE`` verdict.
    """
    element_id = element.id
    applies = rule_applies_to_edge(rule, element) if isinstance(element, Edge) else rule_applies_to_node(rule, element)
    if not applies:
        return None

    resolved_by_field: dict[str, ResolvedAttribute] = {}
    for field_name in sorted({check.field for check in rule.checks}):
        spec = rulepack.attributes[field_name]
        resolved = resolve_attribute(
            element_id=element_id,
            field=field_name,
            records=registry.for_field(element_id, field_name),
            spec=spec,
            as_of=as_of,
        )
        if rule.requires_verified_evidence and resolved.known:
            records = registry.for_field(element_id, field_name)
            eligible = [r for r in records if not r.invalidated]
            if eligible and any(r.verification_status.value != "verified" for r in eligible):
                resolved = ResolvedAttribute(
                    element_id=element_id,
                    field=field_name,
                    known=False,
                    reason_code=ReasonCode.EVIDENCE_NOT_VERIFIED,
                    explanation=(
                        f"Rule {rule.id} requires verified evidence for {field_name!r}; "
                        f"{len(eligible)} record(s) are not verified."
                    ),
                    evidence_ids=[r.id for r in eligible],
                    conversions=resolved.conversions,
                )
        resolved_by_field[field_name] = resolved

    inputs = [resolved_by_field[f] for f in sorted(resolved_by_field)]
    unknown_inputs = [r for r in inputs if not r.known]
    failing: list[tuple[RuleCheck, ResolvedAttribute]] = []
    passing: list[tuple[RuleCheck, ResolvedAttribute]] = []

    for check in sorted(rule.checks, key=lambda c: (c.field, c.operator.value)):
        resolved = resolved_by_field[check.field]
        if not resolved.known:
            continue
        (passing if _compare(check, resolved) else failing).append((check, resolved))

    if failing:
        check, resolved = failing[0]
        detail = "; ".join(
            f"{c.field} = {r.value}{r.canonical_unit or ''} (requires {c.operator.value} "
            f"{c.threshold if c.threshold is not None else c.values})"
            for c, r in failing
        )
        return RuleVerdict(
            rule_id=rule.id,
            rule_version=rule.version,
            element_id=element_id,
            scope=rule.scope,
            state=VerdictState.FAIL,
            reason_code=ReasonCode.RULE_FAIL,
            explanation=f"{rule.failure_message or rule.description} Measured: {detail}.",
            profile_id=profile_id,
            phase_id=phase_id,
            inputs=inputs,
            rule_kind=rule.kind,
            criticality=rule.criticality,
            basis_label=rule.basis_label,
        )

    if unknown_inputs:
        first = unknown_inputs[0]
        return RuleVerdict(
            rule_id=rule.id,
            rule_version=rule.version,
            element_id=element_id,
            scope=rule.scope,
            state=VerdictState.UNKNOWN,
            reason_code=first.reason_code or ReasonCode.RULE_UNKNOWN_ATTRIBUTE,
            explanation=(
                f"{rule.description or rule.id}: no known failure, but a required attribute is unresolved. "
                f"{first.explanation}"
            ),
            profile_id=profile_id,
            phase_id=phase_id,
            inputs=inputs,
            rule_kind=rule.kind,
            criticality=rule.criticality,
            basis_label=rule.basis_label,
        )

    return RuleVerdict(
        rule_id=rule.id,
        rule_version=rule.version,
        element_id=element_id,
        scope=rule.scope,
        state=VerdictState.PASS,
        reason_code=ReasonCode.RULE_PASS,
        explanation=(
            f"{rule.description or rule.id}: all {len(rule.checks)} check(s) satisfied. "
            f"{'; '.join(f'{c.field}={r.value}{r.canonical_unit or chr(32)}' for c, r in passing)}"
        ),
        profile_id=profile_id,
        phase_id=phase_id,
        inputs=inputs,
        rule_kind=rule.kind,
        criticality=rule.criticality,
        basis_label=rule.basis_label,
    )


class TraversalEvaluation:
    """Per-element verdicts plus aggregated traversal states for one profile/phase."""

    __slots__ = ("edge_states", "findings", "node_states", "verdicts", "warnings")

    def __init__(self) -> None:
        self.verdicts: list[RuleVerdict] = []
        self.edge_states: dict[str, VerdictState] = {}
        self.node_states: dict[str, VerdictState] = {}
        self.findings: list[Finding] = []
        self.warnings: list[str] = []

    def hard_verdicts_for(self, element_id: str) -> list[RuleVerdict]:
        return [v for v in self.verdicts if v.element_id == element_id and v.rule_kind is RuleKind.HARD]


def _aggregate(verdicts: Iterable[RuleVerdict]) -> tuple[VerdictState, int, bool]:
    """Return ``(state, relevant_check_count, unknown_only)`` for hard verdicts."""
    hard = [v for v in verdicts if v.rule_kind is RuleKind.HARD]
    checks = sum(len(v.inputs) for v in hard if v.state is not VerdictState.NOT_APPLICABLE)
    if any(v.state is VerdictState.FAIL for v in hard):
        return VerdictState.FAIL, checks, False
    if any(v.state is VerdictState.UNKNOWN for v in hard):
        return VerdictState.UNKNOWN, checks, True
    if checks == 0:
        return VerdictState.NOT_APPLICABLE, 0, False
    return VerdictState.PASS, checks, False


def _finding_from(verdict: RuleVerdict, element_kind: str, remedy: str = "") -> Finding:
    severity = "advisory" if verdict.criticality.value == "advisory" else "critical"
    return Finding(
        id=f"F-{verdict.element_id}-{verdict.rule_id}",
        element_id=verdict.element_id,
        element_kind=element_kind,  # type: ignore[arg-type]
        state=verdict.state,
        severity=severity,  # type: ignore[arg-type]
        reason_code=verdict.reason_code,
        rule_id=verdict.rule_id,
        profile_id=verdict.profile_id,
        phase_id=verdict.phase_id,
        explanation=verdict.explanation,
        evidence_ids=sorted({eid for attr in verdict.inputs for eid in attr.evidence_ids}),
        attributes=verdict.inputs,
        remedy_hint=remedy,
    )


def evaluate_graph(
    *,
    graph: PedestrianGraph,
    rulepack: RulePack,
    profile_id: str,
    phase_id: str,
    as_of: datetime,
) -> TraversalEvaluation:
    """Evaluate every applicable node/edge rule and aggregate traversal states.

    Node-level and crossing-interface constraints genuinely affect traversal
    here: an edge is only confirmed-eligible when its endpoints are too.
    """
    evaluation = TraversalEvaluation()
    edge_rules = rules_for(rulepack, RuleScope.EDGE, profile_id)
    node_rules = rules_for(rulepack, RuleScope.NODE, profile_id)

    # --- nodes (including crossing/curb interfaces)
    for node in graph.nodes:
        node_verdicts: list[RuleVerdict] = []
        for rule in node_rules:
            verdict = evaluate_rule(
                rule=rule,
                element=node,
                registry=graph.evidence_registry,
                rulepack=rulepack,
                profile_id=profile_id,
                phase_id=phase_id,
                as_of=as_of,
            )
            if verdict is not None:
                node_verdicts.append(verdict)
        evaluation.verdicts.extend(node_verdicts)
        state, _checks, _unknown_only = _aggregate(node_verdicts)
        evaluation.node_states[node.id] = state
        for verdict in node_verdicts:
            if verdict.state in (VerdictState.FAIL, VerdictState.UNKNOWN):
                evaluation.findings.append(
                    _finding_from(
                        verdict,
                        "node",
                        remedy="Check the node/interface evidence, or add an explicit topology link.",
                    )
                )

    # --- edges
    for edge in graph.edges:
        edge_verdicts: list[RuleVerdict] = []
        for rule in edge_rules:
            verdict = evaluate_rule(
                rule=rule,
                element=edge,
                registry=graph.evidence_registry,
                rulepack=rulepack,
                profile_id=profile_id,
                phase_id=phase_id,
                as_of=as_of,
            )
            if verdict is None:
                continue
            if verdict.state is VerdictState.NOT_APPLICABLE:
                continue  # inapplicable rules never crowd the aggregate state
            edge_verdicts.append(verdict)

        tail_state = evaluation.node_states.get(edge.u, VerdictState.NOT_APPLICABLE)
        head_state = evaluation.node_states.get(edge.v, VerdictState.NOT_APPLICABLE)

        state, _checks, _unknown_only = _aggregate(edge_verdicts)
        if state is VerdictState.NOT_APPLICABLE:
            evaluation.warnings.append(
                f"Edge {edge.id}: no hard rule in {rulepack.id} applies to {edge.edge_type.value} edges, "
                "so model-confirmed passage cannot be established for it."
            )
        elif state is VerdictState.PASS and VerdictState.FAIL in (tail_state, head_state):
            state = VerdictState.FAIL
        elif state is VerdictState.PASS and VerdictState.UNKNOWN in (tail_state, head_state):
            state = VerdictState.UNKNOWN

        evaluation.verdicts.extend(edge_verdicts)
        evaluation.edge_states[edge.id] = state
        for verdict in edge_verdicts:
            if verdict.state in (VerdictState.FAIL, VerdictState.UNKNOWN):
                evaluation.findings.append(_finding_from(verdict, "edge", remedy="See Fix This Plan options."))

        if edge.id in graph.closed_edge_ids:
            evaluation.findings.append(
                Finding(
                    id=f"F-{edge.id}-CLOSED",
                    element_id=edge.id,
                    element_kind="edge",
                    state=VerdictState.FAIL,
                    severity="critical",
                    reason_code=ReasonCode.EDGE_CLOSED_IN_PHASE,
                    rule_id=None,
                    profile_id=profile_id,
                    phase_id=phase_id,
                    explanation=(
                        f"Edge {edge.id} is closed for construction in phase {phase_id!r}. "
                        "A closure overrides constraint results: this edge cannot be routed."
                    ),
                    remedy_hint="Open the closure in another phase, or select a modelled alternative.",
                )
            )

    evaluation.verdicts.sort(key=lambda v: (v.element_id, v.rule_id))
    evaluation.findings.sort(key=lambda f: (f.element_id, f.rule_id or "", f.id))
    return evaluation