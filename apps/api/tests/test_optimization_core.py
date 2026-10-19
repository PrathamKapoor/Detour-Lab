"""Gate 5 unit tests: library, generator, ranking, budget and materialisation.

These tests use the real bundled library and demo seed where possible, and
purpose-built minimal libraries where a behaviour needs isolation. Nothing here
weakens a check to make a fixture pass: a failing assertion means the engine
behaves differently than the documented policy.
"""

from __future__ import annotations

import json

import pytest
from detour_lab.domain.contracts import CandidateProposal, Intervention
from detour_lab.domain.enums import SolverStatus
from detour_lab.optimization.generator import assess_eligibility, plan_domain
from detour_lab.optimization.library import LibraryError, load_intervention_library
from detour_lab.optimization.model import (
    BudgetCheck,
    CandidateCostSummary,
    CandidateEvaluation,
    SearchBudget,
    SearchConfig,
)
from detour_lab.optimization.rank import determine_status, rank_candidates
from detour_lab.optimization.verify import CandidateError, check_budget, materialise_candidate
from detour_lab.scenarios.apply import build_phase_graph
from tests.conftest import AS_OF

BUNDLED_LIBRARY = load_intervention_library(
    __import__("pathlib").Path(__file__).resolve().parents[3] / "data" / "demo" / "interventions.demo.json"
)


def _intervention(intervention_id: str, **overrides) -> dict:
    payload = {
        "id": intervention_id,
        "name": intervention_id,
        "description": "",
        "enabled": True,
        "allowed_ops": ["update_attribute"],
        "target_element_ids": ["E_X"],
        "phases": [],
        "requires_intervention_ids": [],
        "excludes_intervention_ids": [],
        "preconditions": [],
        "effect": {
            "edits": [
                {
                    "op": "update_attribute",
                    "target_id": "E_X",
                    "params": {"field": "width_mm", "value": 1500, "unit": "mm"},
                    "reason": "test",
                }
            ],
            "temporary_edges": [],
            "phase_changes": [],
        },
        "costs": [],
        "constructible_in_field": False,
        "geometry_provided": False,
        "note": "",
    }
    payload.update(overrides)
    return payload


def _write_library(tmp_path, interventions: list[dict], **overrides):
    payload = {
        "schema_version": "1.0.0",
        "library_id": "TEST_LIBRARY",
        "version": "0.0.1",
        "notice": "test fixture",
        "interventions": interventions,
    }
    payload.update(overrides)
    path = tmp_path / "library.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _evaluation(
    *,
    ids: list[str],
    classification: str,
    restored_all: list[str] | None = None,
    restored_any: list[str] | None = None,
    fails: int = 0,
    unknowns: int = 0,
    regressed: list[str] | None = None,
    cost: float | None = None,
    distance: float | None = None,
    proposal_id: str | None = None,
) -> CandidateEvaluation:
    restored_all = restored_all or []
    restored_any = restored_any or []
    regressed = regressed or []
    summary = CandidateCostSummary(
        currency=None,
        nominal=cost,
        maximum=None,
        unknown=cost is None,
        provenance_notes=[],
        lines=[],
    )
    return CandidateEvaluation(
        proposal=CandidateProposal(
            proposal_id=proposal_id or "cand-" + "-".join(ids),
            intervention_ids=list(ids),
            eligible=classification != "rejected",
            rejection_reasons=[],
            restored_required_od=bool(restored_all),
            requires_verification=classification == "requires_verification",
            passed_profiles=[],
            failed_profiles=[],
            cost_nominal=cost,
            cost_max=None,
            cost_unknown=cost is None,
            added_distance_m=distance,
            solver_status=SolverStatus.FEASIBLE_NOT_PROVEN_OPTIMAL,
        ),
        classification=classification,
        intervention_ids=list(ids),
        intervention_count=len(ids),
        restored_all_profiles=list(restored_all),
        restored_any_profile=list(restored_any),
        regressed_pairs=list(regressed),
        verifications=[],
        assumptions=[],
        applied_phase_changes=[],
        introduced_fail_verdict_count=fails,
        introduced_unknown_verdict_count=unknowns,
        cost=summary,
        budget=BudgetCheck(status="not_requested"),
        preview_scenario_hash="sha256:preview",
        preview_phase_graph_hash="sha256:phase",
    )


class TestLibraryLoading:
    def test_bundled_library_loads_with_unique_validated_entries(self):
        assert BUNDLED_LIBRARY.id == "DEMO_INTERVENTIONS_NOT_ENGINEERED"
        ids = [intervention.id for intervention in BUNDLED_LIBRARY.interventions]
        assert len(ids) == len(set(ids)) == 5
        assert "not a field survey" in BUNDLED_LIBRARY.notice
        # Unknown cost is declared as unknown, never 0.
        backlane = BUNDLED_LIBRARY.by_id("INT-TEMP-BACKLANE-TRACK")
        assert backlane is not None
        assert backlane.costs[0].total_nominal is None
        assert backlane.costs[0].total_max is None

    def test_library_rejects_duplicate_ids(self, tmp_path):
        path = _write_library(tmp_path, [_intervention("A"), _intervention("A")])
        with pytest.raises(LibraryError, match=r"[Dd]uplicate"):
            load_intervention_library(path)

    def test_library_rejects_dangling_requires(self, tmp_path):
        path = _write_library(tmp_path, [_intervention("A", requires_intervention_ids=["GHOST"])])
        with pytest.raises(LibraryError, match="GHOST"):
            load_intervention_library(path)

    def test_library_rejects_requires_cycles(self, tmp_path):
        path = _write_library(
            tmp_path,
            [
                _intervention("A", requires_intervention_ids=["B"]),
                _intervention("B", requires_intervention_ids=["A"]),
            ],
        )
        with pytest.raises(LibraryError, match="cycle"):
            load_intervention_library(path)

    def test_library_rejects_effect_op_outside_allowed_ops(self, tmp_path):
        payload = _intervention("A")
        payload["allowed_ops"] = ["close_edge"]
        path = _write_library(tmp_path, [payload])
        with pytest.raises(LibraryError, match="allowed_ops"):
            load_intervention_library(path)

    def test_library_rejects_unknown_top_level_keys(self, tmp_path):
        path = _write_library(tmp_path, [_intervention("A")], surprise="ignored?")
        with pytest.raises(LibraryError, match="unknown top-level"):
            load_intervention_library(path)

    def test_library_rejects_enabled_intervention_without_effect(self, tmp_path):
        path = _write_library(tmp_path, [_intervention("A", effect=None)])
        with pytest.raises(LibraryError, match="effect"):
            load_intervention_library(path)

    def test_library_rejects_effect_target_not_declared(self, tmp_path):
        payload = _intervention("A")
        payload["target_element_ids"] = ["SOMETHING_ELSE"]
        path = _write_library(tmp_path, [payload])
        with pytest.raises(LibraryError, match="target_element_ids"):
            load_intervention_library(path)


class TestEligibility:
    def test_phase_filter_selects_the_right_interventions(self, seed, demo_scenario, rulepack):
        for phase_id, expected in (
            ("phase-1", {
                "INT-BYPASS-IN-PHASE-1",
                "INT-MODEL-CURB-N_EK",
                "INT-REMEASURE-ALT-TRACK",
                "INT-TEMP-BACKLANE-TRACK",
            }),
            ("phase-2", {
                "INT-MODEL-CURB-N_EK",
                "INT-REMEASURE-ALT-TRACK",
                "INT-REOPEN-E_ES1-P2",
            }),
        ):
            phase_graph = build_phase_graph(seed.graph, demo_scenario, phase_id)
            result = assess_eligibility(
                library_interventions=BUNDLED_LIBRARY.interventions,
                scenario=demo_scenario,
                base_graph=seed.graph,
                phase_graph=phase_graph,
                rulepack=rulepack,
                phase_id=phase_id,
                excluded_ids=set(),
                as_of=AS_OF,
            )
            assert {i.id for i in result.eligible} == expected
            if phase_id == "phase-1":
                excluded = {entry.intervention_id: entry.reasons for entry in result.excluded}
                assert "INT-REOPEN-E_ES1-P2" in excluded
                assert any("phase" in reason for reason in excluded["INT-REOPEN-E_ES1-P2"])

    def test_precondition_fails_closed_when_field_is_already_known(self, seed, demo_scenario, rulepack):
        # The source plan already models N_EK's curb transition, so the
        # "model a flush transition" intervention must be precondition-rejected
        # instead of being applied twice.
        payload = demo_scenario.model_dump(mode="json")
        payload["edits"] = [
            *payload["edits"],
            {
                "op": "update_attribute",
                "target_id": "N_EK",
                "params": {
                    "field": "curb_transition",
                    "value": "bevelled",
                    "method": "test_fixture",
                    "source": "test",
                    "provenance_class": "assumed",
                    "synthetic": True,
                },
                "reason": "test: pre-existing modelled curb",
            },
        ]
        payload["content_hash"] = ""
        modelled = demo_scenario.__class__.model_validate(payload)
        phase_graph = build_phase_graph(seed.graph, modelled, "phase-1")
        result = assess_eligibility(
            library_interventions=BUNDLED_LIBRARY.interventions,
            scenario=modelled,
            base_graph=seed.graph,
            phase_graph=phase_graph,
            rulepack=rulepack,
            phase_id="phase-1",
            excluded_ids=set(),
            as_of=AS_OF,
        )
        rejected = {entry["intervention_id"]: entry["reasons"] for entry in result.precondition_rejected}
        assert "INT-MODEL-CURB-N_EK" in rejected
        assert any("known=True" in reason for reason in rejected["INT-MODEL-CURB-N_EK"])
        assert "INT-MODEL-CURB-N_EK" not in {i.id for i in result.eligible}

    def test_client_exclusion_is_reported_with_reason(self, seed, demo_scenario, rulepack):
        phase_graph = build_phase_graph(seed.graph, demo_scenario, "phase-1")
        result = assess_eligibility(
            library_interventions=BUNDLED_LIBRARY.interventions,
            scenario=demo_scenario,
            base_graph=seed.graph,
            phase_graph=phase_graph,
            rulepack=rulepack,
            phase_id="phase-1",
            excluded_ids={"INT-REMEASURE-ALT-TRACK"},
            as_of=AS_OF,
        )
        excluded = {entry.intervention_id: entry.reasons for entry in result.excluded}
        assert "INT-REMEASURE-ALT-TRACK" in excluded
        assert any("excluded" in reason for reason in excluded["INT-REMEASURE-ALT-TRACK"])


class TestDomainPlanning:
    def test_requires_closure_expands_singletons_and_reports_oversized(self, seed, demo_scenario, rulepack):
        phase_graph = build_phase_graph(seed.graph, demo_scenario, "phase-2")
        eligibility = assess_eligibility(
            library_interventions=BUNDLED_LIBRARY.interventions,
            scenario=demo_scenario,
            base_graph=seed.graph,
            phase_graph=phase_graph,
            rulepack=rulepack,
            phase_id="phase-2",
            excluded_ids=set(),
            as_of=AS_OF,
        )
        plan = plan_domain(
            eligibility=eligibility,
            config=SearchConfig(max_interventions=2, max_candidates=60),
            ineligible_reasons=eligibility.ineligible_reasons,
        )
        assert ("INT-REOPEN-E_ES1-P2",) not in plan.subsets, "an incomplete requires set must never be evaluated"
        assert ("INT-MODEL-CURB-N_EK", "INT-REOPEN-E_ES1-P2") in plan.subsets
        assert plan.enumeration_complete is True
        blocked = plan.dependency_blocked
        assert any(
            entry["intervention_ids"] == ["INT-REMEASURE-ALT-TRACK", "INT-REOPEN-E_ES1-P2"]
            for entry in blocked
        ), "a dependency expansion beyond the slot limit must be reported, not silently dropped"

    def test_mutual_exclusions_are_blocked_and_visible(self, seed, demo_scenario, rulepack):
        phase_graph = build_phase_graph(seed.graph, demo_scenario, "phase-1")
        eligibility = assess_eligibility(
            library_interventions=BUNDLED_LIBRARY.interventions,
            scenario=demo_scenario,
            base_graph=seed.graph,
            phase_graph=phase_graph,
            rulepack=rulepack,
            phase_id="phase-1",
            excluded_ids=set(),
            as_of=AS_OF,
        )
        plan = plan_domain(
            eligibility=eligibility,
            config=SearchConfig(max_interventions=2, max_candidates=60),
            ineligible_reasons=eligibility.ineligible_reasons,
        )
        pair = ("INT-BYPASS-IN-PHASE-1", "INT-TEMP-BACKLANE-TRACK")
        assert pair not in plan.subsets
        assert any(entry["intervention_ids"] == list(pair) for entry in plan.mutually_exclusive_blocked)

    def test_candidate_budget_caps_enumeration_and_reports_incompleteness(self, seed, demo_scenario, rulepack):
        phase_graph = build_phase_graph(seed.graph, demo_scenario, "phase-1")
        eligibility = assess_eligibility(
            library_interventions=BUNDLED_LIBRARY.interventions,
            scenario=demo_scenario,
            base_graph=seed.graph,
            phase_graph=phase_graph,
            rulepack=rulepack,
            phase_id="phase-1",
            excluded_ids=set(),
            as_of=AS_OF,
        )
        plan = plan_domain(
            eligibility=eligibility,
            config=SearchConfig(max_interventions=2, max_candidates=2),
            ineligible_reasons=eligibility.ineligible_reasons,
        )
        assert len(plan.subsets) == 2
        assert plan.enumeration_complete is False

    def test_ineligible_requirement_blocks_dependent(self, seed, demo_scenario, rulepack):
        dependent = Intervention.model_validate(_intervention("A", requires_intervention_ids=["B"]))
        disabled = Intervention.model_validate(_intervention("B", enabled=False, effect=None))
        phase_graph = build_phase_graph(seed.graph, demo_scenario, "phase-1")
        result = assess_eligibility(
            library_interventions=(dependent, disabled),
            scenario=demo_scenario,
            base_graph=seed.graph,
            phase_graph=phase_graph,
            rulepack=rulepack,
            phase_id="phase-1",
            excluded_ids=set(),
            as_of=AS_OF,
        )
        assert [i.id for i in result.eligible] == ["A"]
        plan = plan_domain(
            eligibility=result,
            config=SearchConfig(max_interventions=2, max_candidates=10),
            ineligible_reasons=result.ineligible_reasons,
        )
        assert plan.subsets == []
        assert plan.dependency_blocked[0]["missing_or_ineligible"][0]["intervention_id"] == "B"


class TestRanking:
    def test_classification_group_then_restoration_decides(self):
        certified = _evaluation(ids=["A"], classification="certified", restored_all=["OD-E->OD-LIB"])
        verify = _evaluation(ids=["B"], classification="requires_verification")
        none = _evaluation(ids=["C"], classification="no_improvement")
        rejected = _evaluation(ids=["D"], classification="rejected")
        result = rank_candidates(
            [rejected, none, verify, certified], monetary=False, exhaustive=True
        )
        assert [e.proposal.proposal_id for e in result.ranked] == [
            "cand-A",
            "cand-B",
            "cand-C",
            "cand-D",
        ]
        assert [e.rank for e in result.ranked] == [1, 2, 3, 4]

    def test_restoration_counts_and_tie_groups(self):
        two = _evaluation(
            ids=["A"], classification="certified",
            restored_all=["OD-E->OD-LIB", "OD-W->OD-LIB"],
        )
        one = _evaluation(ids=["B"], classification="certified", restored_all=["OD-E->OD-LIB"])
        any_only = _evaluation(ids=["C"], classification="certified", restored_any=["OD-E->OD-LIB"])
        result = rank_candidates([any_only, one, two], monetary=False, exhaustive=True)
        assert [e.proposal.proposal_id for e in result.ranked] == ["cand-A", "cand-B", "cand-C"]
        # Identical keys must land in one tie group, not be ordered arbitrarily.
        tied_a = _evaluation(ids=["X"], classification="certified", restored_all=["P"], proposal_id="cand-X")
        tied_b = _evaluation(ids=["Y"], classification="certified", restored_all=["P"], proposal_id="cand-Y")
        tied = rank_candidates([tied_b, tied_a], monetary=False, exhaustive=True)
        assert tied.ranked[0].tie_group == tied.ranked[1].tie_group

    def test_intervention_count_beats_distance_by_policy(self):
        # Documented policy: fewer interventions before distance improvement.
        small = _evaluation(ids=["A"], classification="certified", restored_all=["P"])
        bigger = _evaluation(
            ids=["A", "B"], classification="certified", restored_all=["P"], distance=-25.0
        )
        result = rank_candidates([bigger, small], monetary=False, exhaustive=True)
        assert [e.proposal.proposal_id for e in result.ranked] == ["cand-A", "cand-A-B"]
        # Both are non-dominated: the Pareto set communicates the trade-off.
        assert set(result.pareto_frontier) == {"cand-A", "cand-A-B"}

    def test_monetary_objective_off_ignores_cost_known_before_unknown(self):
        expensive = _evaluation(ids=["A"], classification="certified", restored_all=["P"], cost=1000.0)
        cheap = _evaluation(ids=["B"], classification="certified", restored_all=["P"], cost=10.0)
        unknown = _evaluation(ids=["C"], classification="certified", restored_all=["P"], cost=None)
        off = rank_candidates([expensive, cheap, unknown], monetary=False, exhaustive=True)
        # Monetary off: cost is not compared at all; only the proposal id remains.
        assert [e.proposal.proposal_id for e in off.ranked] == ["cand-A", "cand-B", "cand-C"]
        on = rank_candidates([expensive, cheap, unknown], monetary=True, exhaustive=True)
        assert [e.proposal.proposal_id for e in on.ranked] == ["cand-B", "cand-A", "cand-C"]

    def test_distance_known_before_unknown(self):
        improved = _evaluation(ids=["A"], classification="certified", restored_all=["P"], distance=-4.2)
        unknown = _evaluation(ids=["B"], classification="certified", restored_all=["P"], distance=None)
        result = rank_candidates([unknown, improved], monetary=False, exhaustive=True)
        assert [e.proposal.proposal_id for e in result.ranked] == ["cand-A", "cand-B"]

    def test_pareto_domination_removes_dominated_candidates(self):
        better = _evaluation(
            ids=["A"], classification="certified",
            restored_all=["P", "Q"], cost=500.0, distance=-10.0,
        )
        worse = _evaluation(
            ids=["B"], classification="certified",
            restored_all=["P"], cost=900.0, distance=None,
        )
        result = rank_candidates([worse, better], monetary=False, exhaustive=True)
        assert result.pareto_frontier == ["cand-A"]
        assert result.ranked[0].pareto_optimal is True
        worse_row = next(e for e in result.ranked if e.proposal.proposal_id == "cand-B")
        assert worse_row.pareto_optimal is False

    def test_optimal_upgrade_requires_exhaustive_enumeration(self):
        certified = _evaluation(ids=["A"], classification="certified", restored_all=["P"])
        result = rank_candidates([certified], monetary=False, exhaustive=True)
        assert result.ranked[0].proposal.solver_status == SolverStatus.OPTIMAL_IN_ENUMERATED_DOMAIN
        again = _evaluation(ids=["A"], classification="certified", restored_all=["P"])
        truncated = rank_candidates([again], monetary=False, exhaustive=False)
        assert truncated.ranked[0].proposal.solver_status == SolverStatus.FEASIBLE_NOT_PROVEN_OPTIMAL


class TestStatusMapping:
    def test_empty_domain_is_no_feasible_with_note(self):
        status = determine_status(
            ranked=[], exhaustive=True, limits_hit=[], evaluation_failures=0, eligible_count=0
        )
        assert status.solver_status == SolverStatus.NO_FEASIBLE_IN_ENUMERATED_DOMAIN
        assert status.best_proposal_id is None
        assert any("no intervention was eligible" in note.lower() for note in status.notes)

    def test_complete_domain_with_certified_is_optimal(self):
        certified = _evaluation(ids=["A"], classification="certified", restored_all=["P"])
        result = rank_candidates([certified], monetary=False, exhaustive=True)
        status = determine_status(
            ranked=result.ranked, exhaustive=True, limits_hit=[], evaluation_failures=0, eligible_count=2
        )
        assert status.solver_status == SolverStatus.OPTIMAL_IN_ENUMERATED_DOMAIN
        assert status.best_proposal_id == "cand-A"

    def test_truncated_with_certified_never_claims_optimality(self):
        certified = _evaluation(ids=["A"], classification="certified", restored_all=["P"])
        result = rank_candidates([certified], monetary=False, exhaustive=False)
        status = determine_status(
            ranked=result.ranked,
            exhaustive=False,
            limits_hit=["candidate_limit"],
            evaluation_failures=0,
            eligible_count=5,
        )
        assert status.solver_status == SolverStatus.FEASIBLE_NOT_PROVEN_OPTIMAL
        assert any("truncated" in note for note in status.notes)

    def test_truncated_without_certified_is_incomplete(self):
        none = _evaluation(ids=["A"], classification="no_improvement")
        result = rank_candidates([none], monetary=False, exhaustive=False)
        status = determine_status(
            ranked=result.ranked,
            exhaustive=False,
            limits_hit=["duration_limit"],
            evaluation_failures=0,
            eligible_count=5,
        )
        assert status.solver_status == SolverStatus.INCOMPLETE_OR_UNKNOWN
        assert status.best_proposal_id is None

    def test_complete_domain_without_certified_is_no_feasible(self):
        none = _evaluation(ids=["A"], classification="no_improvement")
        requires = _evaluation(ids=["B"], classification="requires_verification")
        result = rank_candidates([none, requires], monetary=False, exhaustive=True)
        status = determine_status(
            ranked=result.ranked, exhaustive=True, limits_hit=[], evaluation_failures=0, eligible_count=2
        )
        assert status.solver_status == SolverStatus.NO_FEASIBLE_IN_ENUMERATED_DOMAIN
        assert any("requires-verification" in note for note in status.notes)

    def test_evaluation_failures_force_incomplete(self):
        none = _evaluation(ids=["A"], classification="no_improvement")
        result = rank_candidates([none], monetary=False, exhaustive=True)
        status = determine_status(
            ranked=result.ranked, exhaustive=True, limits_hit=[], evaluation_failures=1, eligible_count=2
        )
        assert status.solver_status == SolverStatus.INCOMPLETE_OR_UNKNOWN


class TestBudgetChecks:
    def test_not_requested(self):
        check = check_budget(None, CandidateCostSummary(unknown=True))
        assert check.status == "not_requested"
        assert check.basis is None

    def test_unknown_cost_is_never_treated_as_zero_or_fitting(self):
        summary = CandidateCostSummary(currency="INR", nominal=None, maximum=None, unknown=True)
        check = check_budget(SearchBudget(amount=100), summary)
        assert check.status == "cannot_certify_unknown_cost"
        assert "cannot be certified" in check.detail

    def test_zero_budget_rejects_any_known_cost(self):
        summary = CandidateCostSummary(currency="INR", nominal=1.0, maximum=1.0, unknown=False)
        check = check_budget(SearchBudget(amount=0), summary)
        assert check.status == "exceeds"

    def test_conservative_max_basis_uses_the_upper_bound(self):
        summary = CandidateCostSummary(currency="INR", nominal=900.0, maximum=2500.0, unknown=False)
        within_nominal = check_budget(SearchBudget(amount=1000, basis="nominal"), summary)
        over_max = check_budget(SearchBudget(amount=1000, basis="conservative_max"), summary)
        assert within_nominal.status == "within"
        assert over_max.status == "exceeds"
        assert over_max.basis == "conservative_max"

    def test_unknown_upper_bound_fails_conservative_basis(self):
        summary = CandidateCostSummary(currency="INR", nominal=100.0, maximum=None, unknown=False)
        check = check_budget(SearchBudget(amount=10_000, basis="conservative_max"), summary)
        assert check.status == "cannot_certify_unknown_cost"


class TestMaterialisation:
    def _materialise(self, seed, demo_scenario, intervention_ids: list[str]):
        selected = [BUNDLED_LIBRARY.by_id(i) for i in intervention_ids]
        assert all(selected)
        return materialise_candidate(demo_scenario, selected)

    def test_remeasure_is_deterministic_and_surfaces_assumptions(self, seed, demo_scenario):
        first = self._materialise(seed, demo_scenario, ["INT-REMEASURE-ALT-TRACK"])
        second = self._materialise(seed, demo_scenario, ["INT-REMEASURE-ALT-TRACK"])
        assert first.scenario.content_hash == second.scenario.content_hash
        assert first.scenario.content_hash != demo_scenario.content_hash
        # The source scenario itself is untouched.
        assert demo_scenario.content_hash != first.scenario.content_hash
        fields = {(a.element_id, a.field) for a in first.assumptions}
        assert ("E_ALT", "width_mm") in fields
        assert ("E_ALT", "slope_percent") in fields
        assert all(a.requires_field_verification for a in first.assumptions)
        assert first.scenario.intervention_ids == ["INT-REMEASURE-ALT-TRACK"]

    def test_reopen_changes_the_phase_and_records_the_change(self, seed, demo_scenario):
        materialisation = self._materialise(
            seed, demo_scenario, ["INT-MODEL-CURB-N_EK", "INT-REOPEN-E_ES1-P2"]
        )
        phase_two = materialisation.scenario.phase_by_id("phase-2")
        assert phase_two is not None
        assert "E_ES1" not in phase_two.closed_edge_ids
        change = materialisation.applied_phase_changes[0]
        assert change["phase_id"] == "phase-2"
        assert change["unclosed"] == ["E_ES1"]

    def test_duplicate_temporary_edge_is_rejected_with_a_reason(self, seed, demo_scenario):
        backlane = BUNDLED_LIBRARY.by_id("INT-TEMP-BACKLANE-TRACK")
        assert backlane is not None
        first = materialise_candidate(demo_scenario, [backlane])
        with pytest.raises(CandidateError) as excinfo:
            materialise_candidate(first.scenario, [backlane])
        assert any("already declared" in reason for reason in excinfo.value.reasons)

    def test_unknown_phase_change_is_rejected_not_ignored(self, seed, demo_scenario):
        payload = _intervention("A")
        payload["allowed_ops"] = ["activate_temporary_edge"]
        payload["target_element_ids"] = ["TMP-X"]
        payload["effect"] = {
            "edits": [],
            "temporary_edges": [],
            "phase_changes": [
                {
                    "phase_id": "ghost-phase",
                    "activate_temporary_edge_ids": ["TMP-X"],
                }
            ],
        }
        intervention = Intervention.model_validate(payload)
        with pytest.raises(CandidateError) as excinfo:
            materialise_candidate(demo_scenario, [intervention])
        assert any("ghost-phase" in reason for reason in excinfo.value.reasons)
