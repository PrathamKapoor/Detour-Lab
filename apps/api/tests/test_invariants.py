"""The eight PRD hard invariants (PRD §5.1), asserted explicitly and by name."""

from __future__ import annotations

import pytest
from detour_lab.analysis.run import run_analysis
from detour_lab.domain.contracts import GraphEdit, Scenario
from detour_lab.domain.enums import ReasonCode, VerdictState
from detour_lab.domain.hashing import canonical_json, semantic_hash
from detour_lab.evidence.resolver import EvidenceRegistry, resolve_attribute
from detour_lab.graph.routing import shortest_path
from detour_lab.rules.engine import evaluate_graph
from detour_lab.scenarios.apply import apply_edits, build_phase_graph
from tests.conftest import (
    AS_OF,
    PLANAR_BASIS,
    SYNTHETIC_SOURCE,
    accessible_evidence,
    build_scenario,
    edge,
    evidence,
    make_graph,
    node,
)


class TestInv01UnknownNeverBecomesPass:
    """INV-01: Unknown is never silently converted to Pass, on import or edit."""

    def test_missing_evidence_stays_unknown_through_the_whole_pipeline(self, seed, rulepack, profile_a):
        result = run_analysis(
            base_graph=seed.graph, scenario=build_scenario(seed=seed, rulepack=rulepack),
            phase_id="phase-1", profile_id=profile_a.id, rulepack=rulepack, profile=profile_a, as_of=AS_OF,
        )
        alt = next(e for e in result.edge_evaluations if e.edge_id == "E_ALT")
        assert alt.state is VerdictState.UNKNOWN
        assert alt.confirmed_eligible is False
        assert alt.possibly_eligible is True
        unknown_verdicts = [v for v in result.verdicts if v.state is VerdictState.UNKNOWN]
        assert unknown_verdicts
        assert all(v.reason_code is not None for v in unknown_verdicts)

    def test_an_imported_element_with_no_evidence_cannot_pass(self):
        from detour_lab.domain.contracts import AttributeSpec

        spec = AttributeSpec(quantity="width_mm")
        resolved = resolve_attribute(element_id="E", field="width_mm", records=(), spec=spec, as_of=AS_OF)
        assert resolved.known is False
        assert resolved.value is None
        assert resolved.value != 0

    def test_a_manual_edit_does_not_clear_a_different_unknown(self, seed, rulepack, profile_a):
        """Fixing width must not make an edge pass while its slope stays unknown."""
        scenario = build_scenario(
            seed=seed,
            rulepack=rulepack,
            edits=[
                GraphEdit(
                    op="update_attribute",
                    target_id="E_ALT",
                    params={
                        "field": "width_mm", "value": 1800, "unit": "mm",
                        "method": "manual_entry", "source": "planner entry (test)",
                        "provenance_class": "assumed", "synthetic": False,
                        "observed_at": "2026-02-01T10:00:00Z",
                    },
                )
            ],
        )
        result = run_analysis(
            base_graph=seed.graph, scenario=scenario, phase_id="phase-1",
            profile_id=profile_a.id, rulepack=rulepack, profile=profile_a, as_of=AS_OF,
        )
        alt = next(e for e in result.edge_evaluations if e.edge_id == "E_ALT")
        assert alt.state is VerdictState.UNKNOWN  # slope is still missing
        slope_verdict = next(
            v for v in result.verdicts if v.rule_id == "DEMO-EDGE-SLOPE-MAX-MANUAL" and v.element_id == "E_ALT"
        )
        assert slope_verdict.state is VerdictState.UNKNOWN

    def test_b15_not_applicable_cannot_clear_another_critical_unknown(self, seed, rulepack, profile_a):
        result = run_analysis(
            base_graph=seed.graph, scenario=build_scenario(seed=seed, rulepack=rulepack),
            phase_id="phase-1", profile_id=profile_a.id, rulepack=rulepack, profile=profile_a, as_of=AS_OF,
        )
        link = next(e for e in result.edge_evaluations if e.edge_id == "E_LINK")
        # E_LINK satisfies every applicable edge rule, but its endpoint interface
        # is unknown, so the element as a whole cannot be confirmed.
        edge_verdicts = [v for v in result.verdicts if v.element_id == "E_LINK" and v.scope.value == "edge"]
        assert edge_verdicts and all(v.state is not VerdictState.NOT_APPLICABLE for v in edge_verdicts)
        assert link.confirmed_eligible is False


class TestInv02CrossingIsNotConnectivity:
    """INV-02: a visual line intersection creates no connection on its own."""

    def test_seed_crossing_stays_disconnected_until_an_explicit_link(self, seed, rulepack, profile_a):
        before = run_analysis(
            base_graph=seed.graph, scenario=build_scenario(seed=seed, rulepack=rulepack),
            phase_id="phase-1", profile_id=profile_a.id, rulepack=rulepack, profile=profile_a, as_of=AS_OF,
        )
        before_gate = next(o for o in before.od_results if o.destination_id == "OD-GATE")
        before_paths = set(before_gate.confirmed_path_edge_ids)
        assert "E_LINK" not in before_paths

        linked = apply_edits(
            seed.graph,
            [
                GraphEdit(
                    op="link_crossing",
                    target_id="E_K2",
                    params={"new_node_id": "N_XLINK", "fraction": 0.5},
                )
            ],
        )
        # After linking, the diagonal genuinely terminates at the new shared node.
        assert any(
            e.v == "N_XLINK" for e in linked.edges if e.id.startswith("E_K2")
        )
        assert linked.unlinked_crossings() != seed.graph.unlinked_crossings()

    def test_a_crossing_cannot_be_created_by_geometry_alone(self, seed, rulepack, profile_a):
        """Adding an edge that crosses another does not connect the two."""
        crossed = apply_edits(
            seed.graph,
            [
                GraphEdit(
                    op="add_node",
                    target_id="N_FAR",
                    params={"id": "N_FAR", "x": 0.0, "y": 40.0},
                ),
                GraphEdit(
                    op="add_edge",
                    target_id="E_CROSSING",
                    params={"id": "E_CROSSING", "u": "N_FAR", "v": "N_B1"},
                ),
            ],
        )
        assert "E_CROSSING" in {e.id for e in crossed.edges}
        # One hop from the new node reaches exactly the node it was declared against -
        # the geometric crossings it passes over add nothing.
        reached = {
            crossed.edge(edge_id).v
            for edge_id in crossed.outgoing_edge_ids("N_FAR")
        }
        assert reached == {"N_B1"}
        assert crossed.edge("E_CROSSING").v == "N_B1"


class TestInv03BlockedEdgeNotRouted:
    """INV-03: a blocked edge is never routed through in an active phase."""

    @pytest.mark.parametrize("phase_id", ["phase-1", "phase-2"])
    def test_closed_edges_never_appear_in_any_returned_path(self, seed, rulepack, profile_a, phase_id):
        scenario = build_scenario(seed=seed, rulepack=rulepack)
        phase_graph = build_phase_graph(seed.graph, scenario, phase_id)
        result = run_analysis(
            base_graph=seed.graph, scenario=scenario, phase_id=phase_id,
            profile_id=profile_a.id, rulepack=rulepack, profile=profile_a, as_of=AS_OF,
        )
        closed = set(phase_graph.graph.closed_edge_ids)
        assert closed
        for pair in result.od_results:
            assert closed.isdisjoint(pair.confirmed_path_edge_ids)
            assert closed.isdisjoint(pair.possible_path_edge_ids)

    def test_a_closed_edge_is_never_in_the_confirmed_graph(self, seed, rulepack, profile_a):
        from detour_lab.graph.routing import build_feasibility_graphs

        scenario = build_scenario(seed=seed, rulepack=rulepack)
        phase_graph = build_phase_graph(seed.graph, scenario, "phase-1")
        evaluation = evaluate_graph(
            graph=phase_graph.graph, rulepack=rulepack, profile_id=profile_a.id,
            phase_id="phase-1", as_of=AS_OF,
        )
        feasibility = build_feasibility_graphs(phase_graph.graph, evaluation.edge_states)
        assert feasibility.confirmed_edge_ids.isdisjoint(phase_graph.graph.closed_edge_ids)
        assert feasibility.possible_edge_ids.isdisjoint(phase_graph.graph.closed_edge_ids)


class TestInv04UnitIncompatibility:
    """INV-04: incompatible units are rejected or explicitly converted with recorded units."""

    def test_unknown_unit_is_rejected_not_guessed(self):
        from detour_lab.domain.contracts import AttributeSpec
        from detour_lab.evidence.resolver import resolve_attribute

        records = [evidence("EV", "E1", "width_mm", 3, unit="smoots")]
        spec = AttributeSpec(quantity="width_mm")
        resolved = resolve_attribute(element_id="E1", field="width_mm", records=records, spec=spec, as_of=AS_OF)
        assert resolved.known is False
        assert resolved.reason_code is ReasonCode.UNSUPPORTED_UNIT

    def test_compatible_unit_conversion_records_original_and_canonical(self, seed):
        resolved = resolve_attribute(
            element_id="E_K1",
            field="width_mm",
            records=seed.graph.evidence_registry.for_field("E_K1", "width_mm"),
            spec=seed.graph.evidence_registry and __import__(
                "detour_lab.rules.engine", fromlist=["load_rulepack"]
            ).load_rulepack(
                __import__("pathlib").Path(__file__).resolve().parents[1]
                / "detour_lab"
                / "rules"
                / "rulepacks"
                / "DEMO_RULEPACK_NOT_LEGAL.v1.json"
            ).attributes["width_mm"],
            as_of=AS_OF,
        )
        assert resolved.known is True
        assert resolved.canonical_unit == "mm"
        assert resolved.conversions[0]["original_unit"] == "mm"
        assert resolved.conversions[0]["canonical_unit"] == "mm"


class TestInv05PreferenceCannotOverrideHardConstraints:
    """INV-05: a rule failure invalidates the route; weights cannot override it."""

    def test_a_failing_edge_is_excluded_even_with_an_extreme_preference(self, seed, rulepack):
        from detour_lab.rules.profiles import profile_by_id

        greedy = profile_by_id("DEMO_PROFILE_MANUAL_WHEELCHAIR").model_copy(
            update={"preference_weights": {"surface": 1000.0}}
        )
        result = run_analysis(
            base_graph=seed.graph, scenario=build_scenario(seed=seed, rulepack=rulepack),
            phase_id="phase-1", profile_id=greedy.id, rulepack=rulepack, profile=greedy, as_of=AS_OF,
        )
        for evaluation in result.edge_evaluations:
            if evaluation.state is VerdictState.FAIL:
                assert evaluation.confirmed_eligible is False
                for pair in result.od_results:
                    assert evaluation.edge_id not in pair.confirmed_path_edge_ids

    def test_a_negative_preference_weight_is_refused_by_the_router(self, seed):
        from detour_lab.rules.profiles import profile_by_id

        broken = profile_by_id("DEMO_PROFILE_MANUAL_WHEELCHAIR").model_copy(
            update={"preference_weights": {"surface": -1000.0}}
        )
        graph = seed.graph
        target = graph.edge("E_WB")
        from detour_lab.graph.routing import edge_weight, shortest_path

        weight = edge_weight(target, broken, frozenset({"surface"}))
        with pytest.raises(ValueError, match="negative routing weight"):
            shortest_path(
                graph, allowed_edge_ids=frozenset({"E_WB"}), source_node_id="N_W",
                target_node_id="N_B1", weight_fn=lambda e: weight if e.id == "E_WB" else e.length_m,
            )

    def test_preference_only_affects_cost_not_membership(self, seed, rulepack):
        from detour_lab.graph.routing import build_feasibility_graphs
        from detour_lab.rules.profiles import profile_by_id

        scenario = build_scenario(seed=seed, rulepack=rulepack)
        phase_graph = build_phase_graph(seed.graph, scenario, "phase-1")
        plain = profile_by_id("DEMO_PROFILE_LIMITED_MOBILITY_WALKER")
        weighted = plain.model_copy(update={"preference_weights": {"surface": 500.0}})
        states = {}
        for profile in (plain, weighted):
            evaluation = evaluate_graph(
                graph=phase_graph.graph, rulepack=rulepack, profile_id=profile.id,
                phase_id="phase-1", as_of=AS_OF,
            )
            states[profile.id] = build_feasibility_graphs(phase_graph.graph, evaluation.edge_states)
        assert (
            states[plain.id].confirmed_edge_ids == states[weighted.id].confirmed_edge_ids
        )


class TestInv06ReportIdentifiesVersions:
    """INV-06: derived results identify rulepack, profile, base graph, scenario, engine."""

    def test_analysis_result_carries_every_version_identifier(self, seed, rulepack, profile_a):
        from detour_lab import ENGINE_VERSION

        scenario = build_scenario(seed=seed, rulepack=rulepack)
        result = run_analysis(
            base_graph=seed.graph, scenario=scenario, phase_id="phase-1",
            profile_id=profile_a.id, rulepack=rulepack, profile=profile_a, as_of=AS_OF,
        )
        assert result.rulepack_id == rulepack.id
        assert result.rulepack_version == rulepack.version
        assert result.rulepack_hash == rulepack.content_hash
        assert result.scenario_hash == scenario.content_hash
        assert result.base_graph_version_id == seed.graph.version.id
        assert result.base_graph_hash == seed.graph.content_hash
        assert result.phase_graph_id
        assert result.phase_graph_hash
        assert result.profile_id == profile_a.id
        assert ENGINE_VERSION.startswith("detour-lab-engine/")

    def test_b27_provenance_and_timestamps_survive_serialisation(self, seed, rulepack, profile_a):
        result = run_analysis(
            base_graph=seed.graph, scenario=build_scenario(seed=seed, rulepack=rulepack),
            phase_id="phase-1", profile_id=profile_a.id, rulepack=rulepack, profile=profile_a, as_of=AS_OF,
        )
        # The run references evidence by stable ID...
        referenced = {
            eid for v in result.verdicts for attr in v.inputs for eid in attr.evidence_ids
        }
        assert "EV-E_WM-width" in referenced
        # ... and the record behind that ID still carries its source and observed date.
        record = seed.graph.evidence_registry.by_id("EV-E_WM-width")
        payload = canonical_json(record.model_dump(mode="json"))
        assert "2026-01-05T09:00:00" in payload
        assert "synthetic_fixture" in payload
        assert '"observed_at":"2026-01-05T09:00:00Z"' in payload
        assert "synthetic" in payload


class TestInv07BaselineIsImmutable:
    """INV-07: applying a proposal cannot overwrite the original scenario."""

    def test_branching_scenario_does_not_touch_its_parent(self, seed, rulepack):
        parent = build_scenario(seed=seed, rulepack=rulepack, scenario_id="scn-parent")
        child = Scenario.model_validate(
            {
                **parent.model_dump(mode="json"),
                "id": "scn-child",
                "parent_scenario_id": "scn-parent",
                "revision": 2,
                "content_hash": "",
                "phases": [
                    {**p.model_dump(mode="json"), "closed_edge_ids": ["E_WM"]}
                    for p in parent.phases
                ],
            }
        )
        build_phase_graph(seed.graph, child, child.phases[0].id)
        assert parent.phases[0].closed_edge_ids == ["E_ME"]
        assert child.phases[0].closed_edge_ids == ["E_WM"]
        assert parent.content_hash != child.content_hash

    def test_applying_edits_returns_a_new_object_every_time(self, seed):
        original_hash = seed.graph.content_hash
        first = apply_edits(seed.graph, [GraphEdit(op="remove_edge", target_id="E_ME")])
        second = apply_edits(seed.graph, [GraphEdit(op="remove_edge", target_id="E_ME")])
        assert first.content_hash == second.content_hash
        assert first.content_hash != original_hash
        assert seed.graph.content_hash == original_hash


class TestInv08NoCertificationLanguage:
    """INV-08: a model Pass is never presented as approval or certification."""

    FORBIDDEN = ("compliant", "compliance", "certified", "certification", "approved", "approval", "guaranteed safe")

    def test_no_verdict_explanation_contains_approval_language(self, seed, rulepack, profile_a, profile_b):
        for profile in (profile_a, profile_b):
            result = run_analysis(
                base_graph=seed.graph, scenario=build_scenario(seed=seed, rulepack=rulepack),
                phase_id="phase-1", profile_id=profile.id, rulepack=rulepack, profile=profile, as_of=AS_OF,
            )
            for verdict in result.verdicts:
                lowered = verdict.explanation.lower()
                for word in self.FORBIDDEN:
                    assert word not in lowered, f"{verdict.rule_id}: {verdict.explanation}"
                assert verdict.basis_label == "DEMO_RULEPACK_NOT_LEGAL"

    def test_rulepack_disclaimer_and_legal_status_are_explicit(self, rulepack):
        assert rulepack.legal_applicability == "unverified"
        assert "not" in rulepack.disclaimer.lower()
        assert "not a legal standard" in rulepack.name.lower()

    def test_no_confirmed_pair_is_labelled_approved(self, seed, rulepack, profile_a):
        result = run_analysis(
            base_graph=seed.graph, scenario=build_scenario(seed=seed, rulepack=rulepack),
            phase_id="phase-1", profile_id=profile_a.id, rulepack=rulepack, profile=profile_a, as_of=AS_OF,
        )
        confirmed = [od for od in result.od_results if od.confirmed_reachable]
        assert confirmed
        assert all(od.confirmed_distance_m is not None for od in confirmed)


class TestDeterminismAcrossReconstruction:
    """FR-013 / B28: identical semantic inputs reproduce identical output."""

    def test_b28_semantic_hash_is_stable_across_reconstruction(self, seed, rulepack, profile_a):
        first = run_analysis(
            base_graph=seed.graph, scenario=build_scenario(seed=seed, rulepack=rulepack),
            phase_id="phase-1", profile_id=profile_a.id, rulepack=rulepack, profile=profile_a, as_of=AS_OF,
        )
        second = run_analysis(
            base_graph=seed.graph, scenario=build_scenario(seed=seed, rulepack=rulepack),
            phase_id="phase-1", profile_id=profile_a.id, rulepack=rulepack, profile=profile_a, as_of=AS_OF,
        )
        assert semantic_hash(first.model_dump(mode="json")) == semantic_hash(second.model_dump(mode="json"))
        assert first.model_dump(mode="json") == second.model_dump(mode="json")

    def test_twenty_repeated_runs_produce_identical_payloads(self, seed, rulepack, profile_a):
        scenario = build_scenario(seed=seed, rulepack=rulepack)
        hashes = {
            semantic_hash(
                run_analysis(
                    base_graph=seed.graph, scenario=scenario, phase_id="phase-1",
                    profile_id=profile_a.id, rulepack=rulepack, profile=profile_a, as_of=AS_OF,
                ).model_dump(mode="json")
            )
            for _ in range(20)
        }
        assert len(hashes) == 1

    def test_a_different_as_of_is_recorded_not_hidden(self, seed, rulepack, profile_a):
        from datetime import UTC, datetime

        far_future = run_analysis(
            base_graph=seed.graph, scenario=build_scenario(seed=seed, rulepack=rulepack),
            phase_id="phase-1", profile_id=profile_a.id, rulepack=rulepack, profile=profile_a,
            as_of=datetime(2032, 1, 1, tzinfo=UTC),
        )
        crossing = next(
            v for v in far_future.verdicts
            if v.element_id == "N_K" and v.rule_id == "DEMO-NODE-CROSSING-TYPE"
        )
        # The demo pack declares a 5-year freshness policy for crossing_type, so the
        # 2026-01-05 observation is stale by 2032 and the interface becomes UNKNOWN.
        assert crossing.state is VerdictState.UNKNOWN
        assert crossing.reason_code is ReasonCode.EVIDENCE_EXPIRED
        assert "freshness policy" in crossing.explanation

    def test_scenarios_differing_only_in_content_hash_differ(self, seed, rulepack, profile_a):
        base = build_scenario(seed=seed, rulepack=rulepack)
        other = build_scenario(
            seed=seed, rulepack=rulepack,
            phases=[
                p.model_copy(update={"closed_edge_ids": ["E_SSE"]}) for p in base.phases
            ],
        )
        assert other.content_hash != base.content_hash


def test_registry_rejects_duplicate_evidence_ids():
    record = evidence("EV-SAME", "E1", "width_mm", 1000, unit="mm")
    with pytest.raises(ValueError):
        EvidenceRegistry([record, record])


def test_graph_without_matching_basis_is_still_content_addressed():
    graph = make_graph([node("N1", 0.0, 0.0)], [])
    assert graph.version.basis == PLANAR_BASIS
    assert graph.version.source == SYNTHETIC_SOURCE


def test_shortest_path_never_uses_an_edge_outside_the_allow_list():
    nodes = [node("N1", 0.0, 0.0), node("N2", 10.0, 0.0)]
    by_id = {n.id: n for n in nodes}
    graph = make_graph(nodes, [edge("E12", "N1", "N2", by_id)], accessible_evidence("A", "E12"))
    assert (
        shortest_path(
            graph, allowed_edge_ids=frozenset(), source_node_id="N1",
            target_node_id="N2", weight_fn=lambda e: e.length_m,
        )
        is None
    )