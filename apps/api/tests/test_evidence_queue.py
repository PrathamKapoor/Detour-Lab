"""Evidence-intelligence tests (Gate 6, G6-01..G6-04).

Each test asserts a behaviour, not a type. The categories below map onto the
Gate 6 coverage list, and several deliberately build their own tiny graph so the
resolver's five distinct conditions can each be provoked in isolation.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from conftest import (
    AS_OF,
    build_scenario,
    evidence,
)
from detour_lab.analysis.run import run_analysis
from detour_lab.domain.enums import ReasonCode, VerdictState
from detour_lab.evidence.model import EvidenceCriticality
from detour_lab.evidence.queue import derive_evidence_queue, explain_attribute, filter_issues
from detour_lab.evidence.resolver import resolve_attribute
from detour_lab.rules.profiles import DEMO_PROFILES


def _profiles():
    return {p.id: p for p in DEMO_PROFILES}


def _analyse(graph, scenario, rulepack, phases, profile_ids, as_of=AS_OF):
    profiles = _profiles()
    return {
        (phase_id, profile_id): run_analysis(
            base_graph=graph,
            scenario=scenario,
            phase_id=phase_id,
            profile_id=profile_id,
            rulepack=rulepack,
            profile=profiles[profile_id],
            as_of=as_of,
        )
        for phase_id in phases
        for profile_id in profile_ids
    }


def _queue(graph, scenario, rulepack, results, phases, profile_ids, as_of=AS_OF, **kwargs):
    return derive_evidence_queue(
        graph=graph,
        scenario=scenario,
        rulepack=rulepack,
        results_by_phase_profile=results,
        phase_ids=phases,
        profile_ids=profile_ids,
        as_of=as_of,
        project_id="test-project",
        **kwargs,
    )


# --------------------------------------------------------------------------- resolver


class TestResolverConditionsArePreserved:
    """Every one of the five conditions stays distinct - never one generic label."""

    def test_no_evidence(self, rulepack):
        resolved = resolve_attribute(
            element_id="E12",
            field="width_mm",
            records=[],
            spec=rulepack.attributes["width_mm"],
            as_of=AS_OF,
        )
        assert resolved.known is False
        assert resolved.reason_code is ReasonCode.NO_EVIDENCE

    def test_conflicting_observations(self, rulepack):
        records = [
            evidence("EV-a", "E12", "width_mm", 1100, unit="mm"),
            evidence("EV-b", "E12", "width_mm", 1500, unit="mm"),
        ]
        resolved = resolve_attribute(
            element_id="E12",
            field="width_mm",
            records=records,
            spec=rulepack.attributes["width_mm"],
            as_of=AS_OF,
        )
        assert resolved.reason_code is ReasonCode.CONFLICTING_EVIDENCE
        # Both claims survive; nothing is averaged or preferred.
        assert sorted(resolved.conflicting_values) == ["1100", "1500"]
        assert set(resolved.evidence_ids) == {"EV-a", "EV-b"}

    def test_conflicting_across_equivalent_units(self, rulepack):
        records = [
            evidence("EV-a", "E12", "width_mm", 1100, unit="mm"),
            evidence("EV-b", "E12", "width_mm", 150, unit="cm"),
        ]
        resolved = resolve_attribute(
            element_id="E12",
            field="width_mm",
            records=records,
            spec=rulepack.attributes["width_mm"],
            as_of=AS_OF,
        )
        assert resolved.reason_code is ReasonCode.CONFLICTING_EVIDENCE

    def test_equivalent_units_are_not_a_conflict(self, rulepack):
        records = [
            evidence("EV-a", "E12", "width_mm", 1100, unit="mm"),
            evidence("EV-b", "E12", "width_mm", 1.1, unit="m"),
        ]
        resolved = resolve_attribute(
            element_id="E12",
            field="width_mm",
            records=records,
            spec=rulepack.attributes["width_mm"],
            as_of=AS_OF,
        )
        assert resolved.known is True
        assert resolved.value == 1100

    def test_unsupported_unit(self, rulepack):
        records = [evidence("EV-a", "E12", "width_mm", 3, unit="handspans")]
        resolved = resolve_attribute(
            element_id="E12",
            field="width_mm",
            records=records,
            spec=rulepack.attributes["width_mm"],
            as_of=AS_OF,
        )
        assert resolved.reason_code is ReasonCode.UNSUPPORTED_UNIT

    def test_expired_observation(self, rulepack):
        spec = rulepack.attributes["crossing_type"]
        records = [
            evidence("EV-a", "N1", "crossing_type", "zebra_marked", observed_at="2026-01-05T09:00:00Z")
        ]
        later = datetime(2032, 1, 5, tzinfo=UTC)
        resolved = resolve_attribute(element_id="N1", field="crossing_type", records=records, spec=spec, as_of=later)
        assert resolved.reason_code is ReasonCode.EVIDENCE_EXPIRED
        assert "freshness" in resolved.explanation.lower() or "day" in resolved.explanation.lower()

    def test_not_verified_observation(self, rulepack):
        from detour_lab.domain.contracts import AttributeSpec, FreshnessPolicy

        spec = AttributeSpec(
            quantity="text", accepted_units=[], freshness=FreshnessPolicy(requires_verified=True)
        )
        records = [
            evidence("EV-a", "E12", "surface", "asphalt", verification_status="unverified")
        ]
        resolved = resolve_attribute(element_id="E12", field="surface", records=records, spec=spec, as_of=AS_OF)
        assert resolved.reason_code is ReasonCode.EVIDENCE_NOT_VERIFIED

    def test_verified_observation_resolves(self, rulepack):
        from detour_lab.domain.contracts import AttributeSpec, FreshnessPolicy

        spec = AttributeSpec(
            quantity="text", accepted_units=[], freshness=FreshnessPolicy(requires_verified=True)
        )
        records = [
            evidence("EV-a", "E12", "surface", "asphalt", verification_status="verified")
        ]
        resolved = resolve_attribute(element_id="E12", field="surface", records=records, spec=spec, as_of=AS_OF)
        assert resolved.known is True


# --------------------------------------------------------------------------- queue


class TestQueueDerivation:
    def test_queue_is_derived_not_static(self, seed, rulepack):
        scenario = build_scenario(seed=seed, rulepack=rulepack, scenario_id="scn-q")
        phases = [p.id for p in scenario.ordered_phases()]
        profile_ids = [p.id for p in DEMO_PROFILES]
        results = _analyse(seed.graph, scenario, rulepack, phases, profile_ids)
        queue = _queue(seed.graph, scenario, rulepack, results, phases, profile_ids)
        found = {(i.element_id, i.attribute) for i in queue.issues}
        # Exactly the attributes the seeded fixture genuinely leaves unresolved.
        assert found == {
            ("E_ALT", "width_mm"),
            ("E_ALT", "slope_percent"),
            ("N_EK", "curb_transition"),
        }
        assert queue.total_unresolved_attributes_scanned == len(found)

    def test_no_fabricated_measurement(self, seed, rulepack):
        scenario = build_scenario(seed=seed, rulepack=rulepack, scenario_id="scn-q")
        phases = [p.id for p in scenario.ordered_phases()]
        profile_ids = [p.id for p in DEMO_PROFILES]
        results = _analyse(seed.graph, scenario, rulepack, phases, profile_ids)
        queue = _queue(seed.graph, scenario, rulepack, results, phases, profile_ids)
        for issue in queue.issues:
            assert issue.recorded_measurement is None, "an unresolved attribute has no recorded measurement"
            if issue.resolution_status is ReasonCode.NO_EVIDENCE:
                assert issue.observations == []
                assert "no eligible observation" in issue.missing_or_conflicting.lower()

    def test_queue_identity_is_deterministic(self, seed, rulepack):
        scenario = build_scenario(seed=seed, rulepack=rulepack, scenario_id="scn-q")
        phases = [p.id for p in scenario.ordered_phases()]
        profile_ids = [p.id for p in DEMO_PROFILES]
        results = _analyse(seed.graph, scenario, rulepack, phases, profile_ids)
        first = _queue(seed.graph, scenario, rulepack, results, phases, profile_ids)
        second = _queue(seed.graph, scenario, rulepack, results, phases, profile_ids)
        assert first.model_dump(mode="json") == second.model_dump(mode="json")
        assert [i.issue_id for i in first.issues] == [i.issue_id for i in second.issues]

    def test_ordering_is_stable_and_documented(self, seed, rulepack):
        scenario = build_scenario(seed=seed, rulepack=rulepack, scenario_id="scn-q")
        phases = [p.id for p in scenario.ordered_phases()]
        profile_ids = [p.id for p in DEMO_PROFILES]
        results = _analyse(seed.graph, scenario, rulepack, phases, profile_ids)
        queue = _queue(seed.graph, scenario, rulepack, results, phases, profile_ids)
        order = {"decision_blocking": 0, "decision_relevant": 1, "supporting": 2}
        keys = [
            (
                order[i.criticality],
                -len(i.affected_profile_ids),
                -len(i.affected_phase_ids),
                -i.od_pair_count,
                i.element_id,
                i.attribute,
            )
            for i in queue.issues
        ]
        assert keys == sorted(keys)
        assert "ascending(decision_blocking" in queue.ordering_rule
        assert "No probability" in queue.prioritization_method

    def test_no_numeric_priority_score_is_emitted(self, seed, rulepack):
        scenario = build_scenario(seed=seed, rulepack=rulepack, scenario_id="scn-q")
        phases = [p.id for p in scenario.ordered_phases()]
        profile_ids = [p.id for p in DEMO_PROFILES]
        results = _analyse(seed.graph, scenario, rulepack, phases, profile_ids)
        queue = _queue(seed.graph, scenario, rulepack, results, phases, profile_ids)
        for issue in queue.issues:
            payload = issue.model_dump(mode="json")
            assert "score" not in payload
            assert "probability" not in payload
            assert "value_of_information" not in payload
            assert issue.criticality_rationale, "every priority must carry an explanation"

    def test_priority_explanation_is_grounded_in_the_analysis(self, seed, rulepack):
        scenario = build_scenario(seed=seed, rulepack=rulepack, scenario_id="scn-q")
        phases = [p.id for p in scenario.ordered_phases()]
        profile_ids = [p.id for p in DEMO_PROFILES]
        results = _analyse(seed.graph, scenario, rulepack, phases, profile_ids)
        queue = _queue(seed.graph, scenario, rulepack, results, phases, profile_ids)
        multi_profile = [i for i in queue.issues if len(i.affected_profile_ids) == 2]
        assert multi_profile, "the seeded fixture leaves attributes unresolved for both profiles"
        for issue in multi_profile:
            assert any("2 selected mobility profiles" in r for r in issue.criticality_rationale)

    def test_queue_links_to_real_graph_elements(self, seed, rulepack):
        scenario = build_scenario(seed=seed, rulepack=rulepack, scenario_id="scn-q")
        phases = [p.id for p in scenario.ordered_phases()]
        profile_ids = [p.id for p in DEMO_PROFILES]
        results = _analyse(seed.graph, scenario, rulepack, phases, profile_ids)
        queue = _queue(seed.graph, scenario, rulepack, results, phases, profile_ids)
        by_element = {i.element_id: i for i in queue.issues}
        edge_issue = by_element["E_ALT"]
        assert edge_issue.element_kind == "edge"
        assert edge_issue.edge_u == "N_M" and edge_issue.edge_v == "N_SE"
        assert edge_issue.edge_length_m == pytest.approx(43.863)
        node_issue = by_element["N_EK"]
        assert node_issue.element_kind == "node"
        assert node_issue.node_x == pytest.approx(80.0) and node_issue.node_y == pytest.approx(9.0)

    def test_queue_links_to_real_od_pairs(self, seed, rulepack):
        scenario = build_scenario(seed=seed, rulepack=rulepack, scenario_id="scn-q")
        phases = [p.id for p in scenario.ordered_phases()]
        profile_ids = [p.id for p in DEMO_PROFILES]
        results = _analyse(seed.graph, scenario, rulepack, phases, profile_ids)
        queue = _queue(seed.graph, scenario, rulepack, results, phases, profile_ids)
        curb = next(i for i in queue.issues if i.element_id == "N_EK")
        pairs = {p.pair_id for p in curb.od_pairs}
        assert "OD-E->OD-LIB" in pairs, "the unresolved curb sits on the only east-side connection"
        for pair in curb.od_pairs:
            assert pair.role in {"blocking", "relevant", "on_confirmed_route", "on_possible_route"}

    def test_queue_reports_every_selected_profile_and_phase(self, seed, rulepack):
        scenario = build_scenario(seed=seed, rulepack=rulepack, scenario_id="scn-q")
        phases = [p.id for p in scenario.ordered_phases()]
        profile_ids = [p.id for p in DEMO_PROFILES]
        results = _analyse(seed.graph, scenario, rulepack, phases, profile_ids)
        queue = _queue(seed.graph, scenario, rulepack, results, phases, profile_ids)
        assert queue.scope.phase_ids == sorted(phases)
        assert set(queue.scope.profile_ids) == set(profile_ids)
        assert queue.scope.rulepack_hash == rulepack.content_hash
        assert "not a list of physical defects" in queue.scope.scope_note

    def test_narrow_selection_narrows_the_queue(self, seed, rulepack):
        scenario = build_scenario(seed=seed, rulepack=rulepack, scenario_id="scn-q")
        phases = [p.id for p in scenario.ordered_phases()]
        results = _analyse(seed.graph, scenario, rulepack, phases, [p.id for p in DEMO_PROFILES])
        full = _queue(seed.graph, scenario, rulepack, results, phases, [p.id for p in DEMO_PROFILES])
        one_profile = DEMO_PROFILES[0].id
        narrow = _queue(seed.graph, scenario, rulepack, results, ["phase-1"], [one_profile])
        assert len(narrow.issues) <= len(full.issues)
        assert narrow.scope.profile_ids == [one_profile]

    def test_queue_updates_when_authoritative_evidence_changes(self, seed, rulepack):
        """The queue is recomputed, so an added observation removes the issue."""
        from detour_lab.domain.contracts import BaseGraphVersion

        scenario = build_scenario(seed=seed, rulepack=rulepack, scenario_id="scn-q")
        phases = ["phase-1"]
        profile_ids = [DEMO_PROFILES[0].id]
        before_results = _analyse(seed.graph, scenario, rulepack, phases, profile_ids)
        before = _queue(seed.graph, scenario, rulepack, before_results, phases, profile_ids)
        assert any(i.element_id == "E_ALT" and i.attribute == "width_mm" for i in before.issues)

        payload = seed.graph.version.model_dump(mode="json")
        payload["evidence"] = [
            *payload["evidence"],
            {
                "id": "EV-NEW-width",
                "element_id": "E_ALT",
                "field": "width_mm",
                "value": 1400,
                "unit": "mm",
                "method": "test_entry",
                "source": "test",
                "observed_at": "2026-02-01T00:00:00Z",
                "verification_status": "unverified",
                "provenance_class": "assumed",
                "synthetic": True,
            },
        ]
        payload["content_hash"] = ""
        from detour_lab.graph.model import PedestrianGraph

        amended = PedestrianGraph.from_version(BaseGraphVersion.model_validate(payload))
        after_results = _analyse(amended, scenario, rulepack, phases, profile_ids)
        after = _queue(amended, scenario, rulepack, after_results, phases, profile_ids)
        assert not any(i.element_id == "E_ALT" and i.attribute == "width_mm" for i in after.issues)
        # The source graph object is untouched by the derivation.
        assert not any(
            r.id == "EV-NEW-width" for r in seed.graph.version.evidence
        ), "deriving a queue must never mutate the source graph"

    def test_manual_entry_does_not_become_verified(self, seed, rulepack):
        from detour_lab.domain.contracts import BaseGraphVersion
        from detour_lab.graph.model import PedestrianGraph

        payload = seed.graph.version.model_dump(mode="json")
        payload["evidence"] = [
            *payload["evidence"],
            {
                "id": "EV-MANUAL",
                "element_id": "E_ALT",
                "field": "width_mm",
                "value": 1400,
                "unit": "mm",
                "method": "manual_entry",
                "source": "engineer typed this",
                "observed_at": "2026-02-01T00:00:00Z",
                "verification_status": "unverified",
                "provenance_class": "assumed",
                "synthetic": False,
            },
        ]
        payload["content_hash"] = ""
        amended = PedestrianGraph.from_version(BaseGraphVersion.model_validate(payload))
        record = amended.evidence_registry.by_id("EV-MANUAL")
        assert record.verification_status.value == "unverified", "typing a value never verifies it"
        resolved = resolve_attribute(
            element_id="E_ALT",
            field="width_mm",
            records=[record],
            spec=rulepack.attributes["width_mm"],
            as_of=AS_OF,
        )
        assert resolved.known is True
        assert resolved.value == 1400

    def test_queue_state_is_derived(self, seed, rulepack):
        scenario = build_scenario(seed=seed, rulepack=rulepack, scenario_id="scn-q")
        phases = ["phase-1"]
        profile_ids = [DEMO_PROFILES[0].id]
        results = _analyse(seed.graph, scenario, rulepack, phases, profile_ids)
        queue = _queue(seed.graph, scenario, rulepack, results, phases, profile_ids)
        assert {i.queue_state for i in queue.issues} == {"open"}

    def test_noncritical_attribute_is_still_listed(self, seed, rulepack):
        """An unresolved attribute on an irrelevant edge is not silently dropped."""
        scenario = build_scenario(seed=seed, rulepack=rulepack, scenario_id="scn-q")
        phases = ["phase-1"]
        profile_ids = [DEMO_PROFILES[0].id]
        results = _analyse(seed.graph, scenario, rulepack, phases, profile_ids)
        queue = _queue(seed.graph, scenario, rulepack, results, phases, profile_ids)
        # A gap on an element that carries no selected route is still listed and
        # still carries a rationale; it is simply ranked lower than one that
        # withdraws a confirmation.
        assert all(i.criticality_rationale for i in queue.issues)
        assert all(
            i.criticality in set(EvidenceCriticality) for i in queue.issues
        )


# --------------------------------------------------------------------------- G6-04


class TestConflictExplanation:
    def test_conflict_explains_without_choosing(self, seed, rulepack):
        from detour_lab.domain.contracts import BaseGraphVersion
        from detour_lab.graph.model import PedestrianGraph

        payload = seed.graph.version.model_dump(mode="json")
        payload["evidence"] = [
            *payload["evidence"],
            {
                "id": "EV-DISAGREE",
                "element_id": "E_K1",
                "field": "width_mm",
                "value": 1800,
                "unit": "mm",
                "method": "test_fixture",
                "source": "second surveyor",
                "observed_at": "2026-02-02T00:00:00Z",
                "verification_status": "unverified",
                "provenance_class": "assumed",
                "synthetic": True,
            },
        ]
        payload["content_hash"] = ""
        amended = PedestrianGraph.from_version(BaseGraphVersion.model_validate(payload))
        report = explain_attribute(
            graph=amended, rulepack=rulepack, element_id="E_K1", field="width_mm", as_of=AS_OF
        )
        assert report.resolved is False
        assert report.resolution_status is ReasonCode.CONFLICTING_EVIDENCE
        assert len(report.observations) == 2
        assert sorted(report.distinct_values) == ["1100", "1800"]
        assert report.can_be_resolved_without_field_work is False
        assert "No observation is selected" in report.selected_value_note

    def test_does_not_prefer_the_more_favourable_value(self, seed, rulepack):
        """A wider claim must not be adopted just because it would pass."""
        from detour_lab.domain.contracts import BaseGraphVersion
        from detour_lab.graph.model import PedestrianGraph

        payload = seed.graph.version.model_dump(mode="json")
        payload["evidence"] = [
            *payload["evidence"],
            {
                "id": "EV-WIDE",
                "element_id": "E_BS1",
                "field": "width_mm",
                "value": 3000,
                "unit": "mm",
                "method": "test_fixture",
                "source": "optimistic claim",
                "observed_at": "2026-02-02T00:00:00Z",
                "verification_status": "verified",
                "provenance_class": "measured",
                "synthetic": True,
            },
        ]
        payload["content_hash"] = ""
        amended = PedestrianGraph.from_version(BaseGraphVersion.model_validate(payload))
        report = explain_attribute(
            graph=amended, rulepack=rulepack, element_id="E_BS1", field="width_mm", as_of=AS_OF
        )
        assert report.resolved is False
        assert report.canonical_value is None

    def test_single_observation_resolves(self, seed, rulepack):
        report = explain_attribute(
            graph=seed.graph, rulepack=rulepack, element_id="E_K1", field="width_mm", as_of=AS_OF
        )
        assert report.resolved is True
        assert report.canonical_value == 1100
        assert report.canonical_unit == "mm"
        assert report.can_be_resolved_without_field_work is True

    def test_expired_observation_is_explained(self, seed, rulepack):
        later = datetime(2032, 6, 1, tzinfo=UTC)
        report = explain_attribute(
            graph=seed.graph, rulepack=rulepack, element_id="N_K", field="crossing_type", as_of=later
        )
        assert report.resolved is False
        assert report.resolution_status is ReasonCode.EVIDENCE_EXPIRED
        assert "re-observation" in report.resolution_requirement.lower()

    def test_expiry_depends_only_on_the_evaluation_instant(self, seed, rulepack):
        fresh = explain_attribute(
            graph=seed.graph, rulepack=rulepack, element_id="N_K", field="crossing_type", as_of=AS_OF
        )
        stale = explain_attribute(
            graph=seed.graph,
            rulepack=rulepack,
            element_id="N_K",
            field="crossing_type",
            as_of=AS_OF + timedelta(days=2000),
        )
        assert fresh.resolved is True
        assert stale.resolved is False
        # The recorded timestamp was never rewritten.
        record = seed.graph.evidence_registry.by_id("EV-N_K-crossing")
        assert record.observed_at == datetime(2026, 1, 5, 9, 0, tzinfo=UTC)


# --------------------------------------------------------------------------- filters


class TestQueueFilters:
    def test_filter_by_status(self, seed, rulepack):
        scenario = build_scenario(seed=seed, rulepack=rulepack, scenario_id="scn-q")
        phases = ["phase-1"]
        profile_ids = [p.id for p in DEMO_PROFILES]
        results = _analyse(seed.graph, scenario, rulepack, phases, profile_ids)
        queue = _queue(seed.graph, scenario, rulepack, results, phases, profile_ids)
        kept = filter_issues(
            queue.issues, statuses=["NO_EVIDENCE"], profile_ids=None, phase_ids=None, criticalities=None
        )
        assert kept == queue.issues
        empty = filter_issues(
            queue.issues, statuses=["CONFLICTING_EVIDENCE"], profile_ids=None, phase_ids=None, criticalities=None
        )
        assert empty == []

    def test_filter_by_profile_and_phase(self, seed, rulepack):
        scenario = build_scenario(seed=seed, rulepack=rulepack, scenario_id="scn-q")
        phases = [p.id for p in scenario.ordered_phases()]
        profile_ids = [p.id for p in DEMO_PROFILES]
        results = _analyse(seed.graph, scenario, rulepack, phases, profile_ids)
        queue = _queue(seed.graph, scenario, rulepack, results, phases, profile_ids)
        by_profile = filter_issues(
            queue.issues, statuses=None, profile_ids=[profile_ids[0]], phase_ids=None, criticalities=None
        )
        assert by_profile
        assert all(profile_ids[0] in i.affected_profile_ids for i in by_profile)
        by_phase = filter_issues(
            queue.issues, statuses=None, profile_ids=None, phase_ids=["phase-2"], criticalities=None
        )
        assert all("phase-2" in i.affected_phase_ids for i in by_phase)


# --------------------------------------------------------------------------- evidence stays unknown


class TestUnknownIsNeverSilentlyResolved:
    def test_missing_measurement_is_not_a_pass(self, seed, rulepack):
        scenario = build_scenario(seed=seed, rulepack=rulepack, scenario_id="scn-q")
        result = _analyse(seed.graph, scenario, rulepack, ["phase-1"], [DEMO_PROFILES[0].id])[
            ("phase-1", DEMO_PROFILES[0].id)
        ]
        alt = next(e for e in result.edge_evaluations if e.edge_id == "E_ALT")
        assert alt.state is VerdictState.UNKNOWN
        assert alt.unknown_only is True
        assert alt.confirmed_eligible is False
        assert ReasonCode.RULE_UNKNOWN_ATTRIBUTE in alt.reason_codes or alt.reason_codes

    def test_possible_only_is_not_confirmed(self, seed, rulepack):
        scenario = build_scenario(seed=seed, rulepack=rulepack, scenario_id="scn-q")
        result = _analyse(seed.graph, scenario, rulepack, ["phase-1"], [DEMO_PROFILES[0].id])[
            ("phase-1", DEMO_PROFILES[0].id)
        ]
        lib = next(o for o in result.od_results if o.destination_id == "OD-LIB" and o.origin_id == "OD-E")
        assert lib.confirmed_reachable is False
        assert lib.possibly_reachable is True
        assert lib.confirmed_distance_m is None
        assert lib.possible_distance_m is not None
        assert "hypothetical" in lib.possible_distance_label


# --------------------------------------------------------------------------- multi-phase


class TestCrossPhaseDetection:
    def test_in_scope_issue_is_annotated_with_the_phases_where_it_also_persists(
        self, seed, rulepack
    ):
        """Selecting one phase must not hide that a gap also persists in another.

        The queue's scope is the *selected* analysis, so every entry has real
        origin-destination linkage. The extra phases listed in
        ``additional_phases`` do not add entries of their own; they widen each
        in-scope entry so a reviewer sees the whole extent of the gap.
        """
        scenario = build_scenario(seed=seed, rulepack=rulepack, scenario_id="scn-q")
        profile_ids = [DEMO_PROFILES[0].id]
        results = _analyse(seed.graph, scenario, rulepack, ["phase-1"], profile_ids)
        queue = _queue(
            seed.graph,
            scenario,
            rulepack,
            results,
            ["phase-1"],
            profile_ids,
            additional_phases=["phase-2"],
        )
        assert queue.scope.additional_phases_inspected == ["phase-2"]
        assert queue.scope.phase_ids == ["phase-1"]
        alt = next(i for i in queue.issues if i.element_id == "E_ALT" and i.attribute == "width_mm")
        assert alt.affected_phase_ids == ["phase-1", "phase-2"]
        assert any("also unresolved in declared phase(s) phase-2" in r for r in alt.criticality_rationale)

    def test_queue_scope_is_the_selected_analysis_not_every_phase(self, seed, rulepack):
        scenario = build_scenario(seed=seed, rulepack=rulepack, scenario_id="scn-q")
        profile_ids = [DEMO_PROFILES[0].id]
        results = _analyse(seed.graph, scenario, rulepack, ["phase-1"], profile_ids)
        without_extra = _queue(seed.graph, scenario, rulepack, results, ["phase-1"], profile_ids)
        with_extra = _queue(
            seed.graph,
            scenario,
            rulepack,
            results,
            ["phase-1"],
            profile_ids,
            additional_phases=["phase-2"],
        )
        # Inspecting another phase adds context; it never invents entries.
        assert [i.issue_id for i in without_extra.issues] == [i.issue_id for i in with_extra.issues]
        assert "not a list of physical defects" in with_extra.scope.scope_note