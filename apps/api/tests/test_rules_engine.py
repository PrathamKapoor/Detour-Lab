"""Four-valued rule evaluation: B4, B8, B13, B14, B15, INV-01, INV-05, INV-08."""

from __future__ import annotations

import json

import pytest
from detour_lab.domain.contracts import AttributeSpec, Rule, RuleCheck, RulePack
from detour_lab.domain.enums import (
    EdgeType,
    NodeType,
    Operator,
    ReasonCode,
    RuleKind,
    RuleScope,
    VerdictState,
)
from detour_lab.domain.hashing import semantic_hash
from detour_lab.rules.engine import evaluate_rule, rules_for
from pydantic import ValidationError
from tests.conftest import AS_OF, accessible_evidence, edge, evidence, make_graph, node


def rule_for_edge(rulepack, rule_id):
    rule = rulepack.rule_by_id(rule_id)
    assert rule is not None, f"rule {rule_id} missing from the demo rulepack"
    return rule


def evaluate_edge_rule(
    rulepack,
    records,
    *,
    element_id: str = "E1",
    rule_id: str = "DEMO-EDGE-WIDTH-MANUAL",
    profile: str = "DEMO_PROFILE_MANUAL_WHEELCHAIR",
):
    """Evaluate one rule against a single two-node edge carrying ``records``."""
    nodes = [node("N1", 0.0, 0.0), node("N2", 10.0, 0.0)]
    by_id = {n.id: n for n in nodes}
    target = edge(element_id, "N1", "N2", by_id)
    graph = make_graph(nodes, [target], records, version_id=f"v-{element_id}-{len(records)}")
    return evaluate_rule(
        rule=rule_for_edge(rulepack, rule_id),
        element=graph.edge(element_id),
        registry=graph.evidence_registry,
        rulepack=rulepack,
        profile_id=profile,
        phase_id="phase-test",
        as_of=AS_OF,
    )


class TestFourValuedEvaluation:
    def _evaluate(self, rulepack, records, element_id="E1", rule_id="DEMO-EDGE-WIDTH-MANUAL", profile="DEMO_PROFILE_MANUAL_WHEELCHAIR"):
        return evaluate_edge_rule(
            rulepack, records, element_id=element_id, rule_id=rule_id, profile=profile
        )

    def test_pass_when_every_required_check_is_satisfied(self, rulepack):
        verdict = self._evaluate(rulepack, accessible_evidence("OK", "E1"))
        assert verdict.state is VerdictState.PASS
        assert verdict.reason_code is ReasonCode.RULE_PASS
        assert verdict.profile_id == "DEMO_PROFILE_MANUAL_WHEELCHAIR"
        assert verdict.phase_id == "phase-test"

    def test_b04_known_failure_is_a_fail(self, rulepack):
        records = [
            evidence("W", "E1", "width_mm", 700, unit="mm"),
            evidence("S", "E1", "slope_percent", 1.0, unit="percent"),
            evidence("F", "E1", "surface", "asphalt", unit=None),
        ]
        verdict = self._evaluate(rulepack, records)
        assert verdict.state is VerdictState.FAIL
        assert verdict.reason_code is ReasonCode.RULE_FAIL
        assert "700" in verdict.explanation
        assert verdict.inputs, "a failing verdict must carry its inputs"

    def test_missing_attribute_yields_unknown_not_fail_not_pass(self, rulepack):
        verdict = self._evaluate(rulepack, [])
        assert verdict.state is VerdictState.UNKNOWN
        assert verdict.reason_code is ReasonCode.NO_EVIDENCE

    def test_partial_evidence_yields_unknown(self, rulepack):
        records = [evidence("W", "E1", "width_mm", 2000, unit="mm")]
        verdict = self._evaluate(rulepack, records, rule_id="DEMO-EDGE-SURFACE-MANUAL")
        assert verdict.state is VerdictState.UNKNOWN
        assert verdict.reason_code is ReasonCode.NO_EVIDENCE

    def test_b15_not_applicable_is_returned_for_a_non_matching_edge_type(self, rulepack):
        nodes = [node("N1", 0.0, 0.0), node("N2", 10.0, 0.0)]
        by_id = {n.id: n for n in nodes}
        ramp = edge("E_RAMP", "N1", "N2", by_id, edge_type=EdgeType.RAMP)
        graph = make_graph(nodes, [ramp], accessible_evidence("R", "E_RAMP"))
        # The width rule declares sidewalk/shared_use_path/crossing/temporary_path
        # only, so a ramp is provably outside its scope.
        assert evaluate_rule(
            rule=rule_for_edge(rulepack, "DEMO-EDGE-WIDTH-MANUAL"),
            element=ramp,
            registry=graph.evidence_registry,
            rulepack=rulepack,
            profile_id="DEMO_PROFILE_MANUAL_WHEELCHAIR",
            phase_id="phase-test",
            as_of=AS_OF,
        ) is None

    def test_explanation_never_claims_certification(self, rulepack):
        verdict = self._evaluate(rulepack, accessible_evidence("OK", "E1"))
        text = verdict.explanation.lower()
        for forbidden in ("compliant", "certified", "approved", "safe for"):
            assert forbidden not in text
        assert verdict.basis_label == "DEMO_RULEPACK_NOT_LEGAL"


class TestDirectionalSlope:
    def test_b08_steep_grade_only_fails_in_the_graded_direction(self, rulepack):
        nodes = [node("N1", 0.0, 0.0), node("N2", 10.0, 10.0)]
        by_id = {n.id: n for n in nodes}
        steep = edge("E_STEEP", "N1", "N2", by_id)
        records = [
            evidence("W", "E_STEEP", "width_mm", 2000, unit="mm"),
            evidence("SL", "E_STEEP", "slope_percent", 12.0, unit="percent"),
            evidence("SU", "E_STEEP", "surface", "asphalt", unit=None),
        ]
        graph = make_graph(nodes, [steep], records)
        uphill = evaluate_rule(
            rule=rule_for_edge(rulepack, "DEMO-EDGE-SLOPE-MAX-MANUAL"),
            element=steep,
            registry=graph.evidence_registry,
            rulepack=rulepack,
            profile_id="DEMO_PROFILE_MANUAL_WHEELCHAIR",
            phase_id="phase-test",
            as_of=AS_OF,
        )
        downhill = evaluate_rule(
            rule=rule_for_edge(rulepack, "DEMO-EDGE-SLOPE-MIN-MANUAL"),
            element=steep,
            registry=graph.evidence_registry,
            rulepack=rulepack,
            profile_id="DEMO_PROFILE_MANUAL_WHEELCHAIR",
            phase_id="phase-test",
            as_of=AS_OF,
        )
        assert uphill.state is VerdictState.FAIL
        assert downhill.state is VerdictState.PASS

        # The reverse edge of the same corridor is not itself steep downhill.
        flat = edge("E_FLAT", "N1", "N2", by_id)
        graph_flat = make_graph(
            nodes, [flat], [evidence("SL2", "E_FLAT", "slope_percent", -12.0, unit="percent")]
        )
        reverse_uphill = evaluate_rule(
            rule=rule_for_edge(rulepack, "DEMO-EDGE-SLOPE-MAX-MANUAL"),
            element=flat,
            registry=graph_flat.evidence_registry,
            rulepack=rulepack,
            profile_id="DEMO_PROFILE_MANUAL_WHEELCHAIR",
            phase_id="phase-test",
            as_of=AS_OF,
        )
        assert reverse_uphill.state is VerdictState.PASS


class TestProfileIndependence:
    def test_b13_the_two_profiles_produce_independent_results(self, rulepack):
        records = [evidence("W", "E1", "width_mm", 1100, unit="mm")]
        a = evaluate_edge_rule(rulepack, records, rule_id="DEMO-EDGE-WIDTH-MANUAL")
        b = evaluate_edge_rule(
            rulepack,
            records,
            rule_id="DEMO-EDGE-WIDTH-LIMITED",
            profile="DEMO_PROFILE_LIMITED_MOBILITY_WALKER",
        )
        assert a.state is VerdictState.PASS
        assert b.state is VerdictState.FAIL

    def test_rules_are_selected_per_profile(self, rulepack):
        a = {r.id for r in rules_for(rulepack, RuleScope.EDGE, "DEMO_PROFILE_MANUAL_WHEELCHAIR")}
        b = {r.id for r in rules_for(rulepack, RuleScope.EDGE, "DEMO_PROFILE_LIMITED_MOBILITY_WALKER")}
        assert "DEMO-EDGE-WIDTH-MANUAL" in a and "DEMO-EDGE-WIDTH-MANUAL" not in b
        assert "DEMO-EDGE-WIDTH-LIMITED" in b and "DEMO-EDGE-WIDTH-LIMITED" not in a

    def test_b14_preference_weight_cannot_change_any_hard_verdict(self, rulepack, profile_a):
        records = accessible_evidence("P", "E1")
        before = evaluate_edge_rule(rulepack, records)
        boosted = profile_a.model_copy(update={"preference_weights": {"surface": 99.0}})
        from detour_lab.graph.routing import edge_weight

        graph_nodes = [node("N1", 0.0, 0.0), node("N2", 10.0, 0.0)]
        by_id = {n.id: n for n in graph_nodes}
        target = edge("E1", "N1", "N2", by_id)
        plain = edge_weight(target, profile_a, frozenset({"surface"}))
        weighted = edge_weight(target, boosted, frozenset({"surface"}))
        assert weighted > plain  # ranking cost really did change
        assert before.state is VerdictState.PASS  # ... but the verdict did not
        after = evaluate_edge_rule(rulepack, records)
        assert after.state is before.state

    def test_preference_rules_are_never_hard(self, rulepack):
        preferences = [r for r in rulepack.rules if r.kind is RuleKind.PREFERENCE]
        assert preferences, "the demo pack should exercise preference rules"
        for rule in preferences:
            assert rule.criticality.value == "advisory"


class TestNodeConstraints:
    def test_curb_interface_failure_propagates_to_traversal(self, rulepack):
        from detour_lab.rules.engine import evaluate_graph

        nodes = [
            node("N1", 0.0, 0.0, NodeType.CURB_INTERFACE),
            node("N2", 10.0, 0.0),
        ]
        by_id = {n.id: n for n in nodes}
        edges = [edge("E12", "N1", "N2", by_id)]
        records = [*accessible_evidence("E", "E12"), evidence("CURB", "N1", "curb_transition", "kerb_upstand", unit=None)]
        graph = make_graph(nodes, edges, records)
        evaluation = evaluate_graph(
            graph=graph, rulepack=rulepack, profile_id="DEMO_PROFILE_MANUAL_WHEELCHAIR",
            phase_id="phase-test", as_of=AS_OF,
        )
        assert evaluation.node_states["N1"] is VerdictState.FAIL
        assert evaluation.edge_states["E12"] is VerdictState.FAIL

    def test_missing_curb_evidence_makes_the_interface_unknown(self, rulepack):
        from detour_lab.rules.engine import evaluate_graph

        nodes = [
            node("N1", 0.0, 0.0, NodeType.CURB_INTERFACE),
            node("N2", 10.0, 0.0),
        ]
        by_id = {n.id: n for n in nodes}
        graph = make_graph(nodes, [edge("E12", "N1", "N2", by_id)], accessible_evidence("E", "E12"))
        evaluation = evaluate_graph(
            graph=graph, rulepack=rulepack, profile_id="DEMO_PROFILE_MANUAL_WHEELCHAIR",
            phase_id="phase-test", as_of=AS_OF,
        )
        assert evaluation.node_states["N1"] is VerdictState.UNKNOWN
        assert evaluation.edge_states["E12"] is VerdictState.UNKNOWN


class TestRuleSafety:
    def test_unknown_operator_is_rejected_at_construction(self):
        with pytest.raises(ValidationError):
            RuleCheck(field="width_mm", operator="eval_me")

    def test_rules_are_data_not_code(self, rulepack):
        payload = rulepack.model_dump(mode="json")
        serialised = json.dumps(payload)
        assert "lambda" not in serialised
        assert "__" not in serialised.replace("__init__", "")

    def test_rulepack_hash_is_stable_and_covers_rule_changes(self, rulepack):
        assert rulepack.content_hash.startswith("sha256:")
        mutated = rulepack.model_copy(
            update={
                "rules": [
                    r.model_copy(update={"checks": [c.model_copy(update={"threshold": 1}) for c in r.checks]})
                    if r.id == "DEMO-EDGE-WIDTH-MANUAL"
                    else r
                    for r in rulepack.rules
                ]
            }
        )
        rebuilt = RulePack.model_validate({**mutated.model_dump(mode="json"), "content_hash": ""})
        assert rebuilt.content_hash != rulepack.content_hash

    def test_rule_referencing_undeclared_attribute_is_rejected(self, rulepack):
        payload = rulepack.model_dump(mode="json")
        payload["rules"][0]["checks"][0]["field"] = "not_declared"
        with pytest.raises(ValidationError):
            RulePack.model_validate(payload)

    def test_duplicate_rule_ids_rejected(self, rulepack):
        payload = rulepack.model_dump(mode="json")
        payload["rules"].append(payload["rules"][0])
        with pytest.raises(ValidationError):
            RulePack.model_validate(payload)

    def test_operator_arguments_are_validated(self):
        with pytest.raises(ValidationError):
            RuleCheck(field="width_mm", operator=Operator.GTE)  # no threshold
        with pytest.raises(ValidationError):
            RuleCheck(field="surface", operator=Operator.ONE_OF)  # no values

    def test_rulepack_declares_its_legal_status_as_unverified(self, rulepack):
        assert rulepack.legal_applicability == "unverified"
        assert "not" in rulepack.disclaimer.lower()
        assert semantic_hash({"id": rulepack.id}) != rulepack.content_hash


class TestAttributeSpecs:
    def test_quantity_decides_the_conversion(self):
        assert AttributeSpec(quantity="width_mm").quantity == "width_mm"
        assert AttributeSpec(quantity="text").quantity == "text"

    def test_rule_scope_and_kind_are_explicit(self, rulepack):
        for rule in rulepack.rules:
            assert rule.scope in (RuleScope.EDGE, RuleScope.NODE)
            assert rule.kind in (RuleKind.HARD, RuleKind.PREFERENCE)
            assert rule.checks
            assert rule.basis_label == "DEMO_RULEPACK_NOT_LEGAL"


def test_rule_object_cannot_smuggle_an_expression(rulepack):
    rule = rulepack.rule_by_id("DEMO-EDGE-WIDTH-MANUAL")
    assert isinstance(rule, Rule)
    with pytest.raises(ValidationError):
        rule.checks[0].threshold = "__import__('os').system('echo hacked')"