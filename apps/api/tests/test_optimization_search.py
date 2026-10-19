"""Gate 5 service tests: bounded searches against a real seeded database.

Every assertion here is derived from an actual ``run_analysis`` execution on the
synthetic demo project. The expected values encode *demonstration-data* facts
(83.863 m rear-track route, 18 m east approach, the 900 mm/1200 mm width
limits); if the engine's answer changes, these tests fail loudly rather than
being relaxed.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from detour_lab.api.main import seed_demo
from detour_lab.api.state import DEMO_SCENARIO_ID
from detour_lab.optimization import load_intervention_library, run_search
from detour_lab.optimization.model import SearchBudget, SearchConfig, SearchOutcome
from detour_lab.optimization.service import SearchInputError
from detour_lab.persistence.db import Database
from detour_lab.persistence.repository import Repository
from tests.conftest import AS_OF, REPO_ROOT

LIBRARY_PATH = REPO_ROOT / "data" / "demo" / "interventions.demo.json"

E_LIB = "OD-E->OD-LIB"
W_LIB = "OD-W->OD-LIB"
BOTH_PROFILES = ["DEMO_PROFILE_LIMITED_MOBILITY_WALKER", "DEMO_PROFILE_MANUAL_WHEELCHAIR"]


@pytest.fixture()
def repository(tmp_path) -> Repository:
    database = Database(tmp_path / "optimization.sqlite3")
    database.migrate()
    repo = Repository(database)
    report = seed_demo(repo)
    assert report["project"] is True and report["scenario"] is True
    return repo


@pytest.fixture()
def library():
    return load_intervention_library(LIBRARY_PATH)


def _search(
    repository: Repository,
    library,
    *,
    phase_id: str = "phase-1",
    profile_ids: list[str] | None = None,
    config: SearchConfig | None = None,
    evaluation_instant: datetime = AS_OF,
) -> SearchOutcome:
    return run_search(
        repository=repository,
        library=library,
        scenario_id=DEMO_SCENARIO_ID,
        phase_id=phase_id,
        profile_ids=profile_ids,
        evaluation_instant=evaluation_instant,
        config=config
        or SearchConfig(max_interventions=2, max_candidates=60, max_duration_ms=120_000),
    )


def _by_ids(outcome: SearchOutcome) -> dict[tuple[str, ...], object]:
    return {
        tuple(sorted(candidate.intervention_ids)): candidate for candidate in outcome.candidates
    }


class TestPhaseOneSearch:
    def test_demo_phase_one_semantics(self, repository, library):
        outcome = _search(repository, library)
        assert outcome.scenario_revision == 1
        assert set(outcome.profile_ids) == set(BOTH_PROFILES)

        # Domain: four eligible interventions, the phase-2-only one excluded,
        # and the declared mutual exclusion reported instead of evaluated.
        assert set(outcome.domain.eligible_intervention_ids) == {
            "INT-BYPASS-IN-PHASE-1",
            "INT-MODEL-CURB-N_EK",
            "INT-REMEASURE-ALT-TRACK",
            "INT-TEMP-BACKLANE-TRACK",
        }
        excluded = {entry.intervention_id: entry.reasons for entry in outcome.domain.excluded_interventions}
        assert "INT-REOPEN-E_ES1-P2" in excluded
        assert outcome.domain.domain_combination_count == 10
        assert outcome.domain.evaluated_count == 9
        assert outcome.domain.exhausted is True
        assert outcome.domain.truncated_by == []
        assert len(outcome.domain.mutually_exclusive_blocked) == 1
        assert outcome.domain.mutually_exclusive_blocked[0]["intervention_ids"] == [
            "INT-BYPASS-IN-PHASE-1",
            "INT-TEMP-BACKLANE-TRACK",
        ]

        candidates = _by_ids(outcome)

        # INT-MODEL-CURB-N_EK: the single UNKNOWN curb blocked the walker profile
        # on BOTH required OD pairs; modelling it restores both, model-confirmed.
        curb = candidates[("INT-MODEL-CURB-N_EK",)]
        assert curb.classification == "certified"
        assert curb.restored_all_profiles == [E_LIB, W_LIB]
        assert curb.proposal.restored_required_od is True
        assert curb.proposal.passed_profiles == BOTH_PROFILES
        assert curb.proposal.failed_profiles == []
        assert curb.cost.nominal == 18000.0
        assert curb.cost.unknown is False
        assert curb.preview_scenario_hash
        assert curb.preview_scenario_hash != outcome.scenario_content_hash
        assert curb.preview_phase_graph_hash

        # INT-REMEASURE-ALT-TRACK: confirms the 83.863 m rear track for the
        # walker profile and shortens the wheelchair profile's confirmed route
        # by exactly 98 - 83.863 m.
        remeasure = candidates[("INT-REMEASURE-ALT-TRACK",)]
        assert remeasure.classification == "certified"
        assert remeasure.restored_all_profiles == [W_LIB]
        assert remeasure.proposal.added_distance_m == pytest.approx(-14.137, abs=1e-3)
        assert remeasure.cost.nominal == pytest.approx(43.9 * 120, abs=1e-6)

        # TEMP-BACKLANE: gains only exist in the *possible* graph (width not
        # measured); it must not be certified and its cost must stay unknown.
        backlane = candidates[("INT-TEMP-BACKLANE-TRACK",)]
        assert backlane.classification == "requires_verification"
        assert backlane.proposal.requires_verification is True
        assert backlane.cost.unknown is True
        assert backlane.cost.nominal is None
        assert backlane.proposal.cost_nominal is None
        assert backlane.proposal.restored_required_od is False
        assert backlane.introduced_unknown_verdict_count == 2

        # Combining the back lane with a certified fix restores both pairs, but
        # the candidate itself still introduces unverifiable elements: it must
        # require verification rather than be certified (Unknown never passes).
        curb_backlane = candidates[("INT-MODEL-CURB-N_EK", "INT-TEMP-BACKLANE-TRACK")]
        assert curb_backlane.classification == "requires_verification"
        assert curb_backlane.restored_all_profiles == [E_LIB, W_LIB]
        assert curb_backlane.introduced_unknown_verdict_count == 2
        assert curb_backlane.cost.unknown is True

        # Activating the 900 mm bypass in phase 1 introduces a NEW hard
        # model-FAIL for the 1200 mm walker profile: rejected, hard constraints
        # never trade against gains.
        bypass_rows = [
            candidate
            for candidate in outcome.candidates
            if "INT-BYPASS-IN-PHASE-1" in candidate.intervention_ids
        ]
        assert bypass_rows, "the bypass candidates must be evaluated, not skipped"
        for row in bypass_rows:
            assert row.classification == "rejected"
            assert row.proposal.eligible is False
            assert any("model-FAIL" in reason for reason in row.proposal.rejection_reasons)
            assert row.proposal.failed_profiles == ["DEMO_PROFILE_LIMITED_MOBILITY_WALKER"]
            assert row.proposal.passed_profiles == ["DEMO_PROFILE_MANUAL_WHEELCHAIR"]

        # Status: complete enumeration, certified candidates found, rank 1 is
        # the single-cheapest credible fix (fewer interventions before distance).
        assert outcome.status.solver_status.value == "OPTIMAL_IN_ENUMERATED_DOMAIN"
        assert outcome.status.exhaustive is True
        assert outcome.status.limits_hit == []
        assert outcome.status.best_proposal_id == curb.proposal.proposal_id
        assert outcome.candidates[0].proposal.proposal_id == curb.proposal.proposal_id
        assert outcome.candidates[0].rank == 1
        assert outcome.candidates[1].intervention_ids == sorted(
            ["INT-REMEASURE-ALT-TRACK", "INT-MODEL-CURB-N_EK"]
        )

        # Policy and disclaimers are echoed in the payload.
        assert outcome.ranking_policy.id == "DETOUR_LAB_LEXICOGRAPHIC_V1"
        assert any("not legal compliance" in line for line in outcome.disclaimers)
        assert any("synthetic" in line for line in outcome.disclaimers)

    def test_per_profile_selection_changes_the_restoration_view(self, repository, library):
        walker_only = _search(repository, library, profile_ids=["DEMO_PROFILE_LIMITED_MOBILITY_WALKER"])
        curb = _by_ids(walker_only)[("INT-MODEL-CURB-N_EK",)]
        # For the walker alone, both blocked pairs become confirmed.
        assert curb.restored_all_profiles == [E_LIB, W_LIB]
        assert curb.proposal.restored_required_od is True

        wheelchair_only = _search(repository, library, profile_ids=["DEMO_PROFILE_MANUAL_WHEELCHAIR"])
        curb_a = _by_ids(wheelchair_only)[("INT-MODEL-CURB-N_EK",)]
        # The wheelchair profile already had W->LIB confirmed; only E->LIB is a
        # restoration for it, and the payload must say exactly that.
        assert curb_a.restored_all_profiles == [E_LIB]
        assert curb_a.restored_any_profile == [E_LIB]

    def test_search_is_deterministic_across_executions(self, repository, library):
        first = _search(repository, library)
        second = _search(repository, library)
        assert first.search_id != second.search_id, "execution identity must differ"
        assert first.semantic_hash == second.semantic_hash
        assert first.input_hash == second.input_hash
        assert [c.proposal.proposal_id for c in first.candidates] == [
            c.proposal.proposal_id for c in second.candidates
        ]
        assert first.status.solver_status == second.status.solver_status

        # The order in which the client lists profiles must not change the
        # semantic result: the hash covers the *set* of selected profiles.
        reversed_order = _search(
            repository, library, profile_ids=list(reversed(BOTH_PROFILES))
        )
        assert reversed_order.semantic_hash == first.semantic_hash

    def test_search_never_mutates_the_source_scenario(self, repository, library):
        before = repository.get_scenario(DEMO_SCENARIO_ID)
        runs_before = repository.counts()["analysis_runs"]
        _search(repository, library)
        after = repository.get_scenario(DEMO_SCENARIO_ID)
        assert (after.revision, after.content_hash) == (before.revision, before.content_hash)
        assert after.model_dump(mode="json") == before.model_dump(mode="json")
        assert repository.counts()["analysis_runs"] == runs_before
        assert repository.counts()["optimization_runs"] == 1


class TestPhaseTwoSearch:
    def test_joint_restoration_and_dependency_reporting(self, repository, library):
        outcome = _search(repository, library, phase_id="phase-2")
        assert set(outcome.domain.eligible_intervention_ids) == {
            "INT-MODEL-CURB-N_EK",
            "INT-REMEASURE-ALT-TRACK",
            "INT-REOPEN-E_ES1-P2",
        }
        candidates = _by_ids(outcome)

        # The curb alone restores W->LIB for both profiles by confirming the
        # walker's alternative corridor (107.505 m); E->LIB only becomes
        # confirmed for the wheelchair profile while the crossing stays closed.
        curb = candidates[("INT-MODEL-CURB-N_EK",)]
        assert curb.classification == "certified"
        assert curb.restored_all_profiles == [W_LIB]
        assert curb.restored_any_profile == [E_LIB, W_LIB]

        # The reopen candidate is only meaningful together with the curb: its
        # closure is evaluated as one joint candidate that restores both pairs
        # for BOTH profiles (single-phase improvement, not project continuity).
        joint = candidates[("INT-MODEL-CURB-N_EK", "INT-REOPEN-E_ES1-P2")]
        assert joint.classification == "certified"
        assert joint.restored_all_profiles == [E_LIB, W_LIB]
        assert joint.applied_phase_changes
        assert joint.applied_phase_changes[0]["unclosed"] == ["E_ES1"]
        assert ("INT-REOPEN-E_ES1-P2",) not in candidates, (
            "an incomplete requires set must never be evaluated as a candidate"
        )

        # The oversized closure is reported, not silently dropped.
        assert any(
            entry["intervention_ids"] == ["INT-REMEASURE-ALT-TRACK", "INT-REOPEN-E_ES1-P2"]
            for entry in outcome.domain.dependency_blocked
        )
        assert outcome.status.scope_note
        assert "single-phase" in outcome.status.scope_note.lower()


class TestLimitsAndHonesty:
    def test_zero_candidates_when_everything_is_excluded(self, repository, library):
        all_ids = list(library.ids)
        outcome = _search(
            repository,
            library,
            config=SearchConfig(
                max_interventions=2, max_candidates=60, excluded_intervention_ids=all_ids
            ),
        )
        assert outcome.candidates == []
        assert outcome.domain.eligible_intervention_ids == []
        assert outcome.domain.evaluated_count == 0
        assert outcome.status.solver_status.value == "NO_FEASIBLE_IN_ENUMERATED_DOMAIN"
        assert any("No intervention was eligible" in note for note in outcome.status.notes)

    def test_zero_budget_rejects_every_candidate_with_stated_reasons(self, repository, library):
        outcome = _search(
            repository,
            library,
            config=SearchConfig(
                max_interventions=2,
                max_candidates=60,
                budget=SearchBudget(amount=0, currency="INR", basis="nominal"),
            ),
        )
        assert outcome.candidates, "candidates are still enumerated; they are just not affordable"
        curb = _by_ids(outcome)[("INT-MODEL-CURB-N_EK",)]
        assert curb.classification == "rejected"
        assert any("budget" in reason and "exceeds" in reason for reason in curb.proposal.rejection_reasons)
        backlane = _by_ids(outcome)[("INT-TEMP-BACKLANE-TRACK",)]
        assert backlane.classification == "rejected"
        assert any("cannot be certified" in reason for reason in backlane.proposal.rejection_reasons)
        assert outcome.status.solver_status.value == "NO_FEASIBLE_IN_ENUMERATED_DOMAIN"

    def test_budget_currency_mismatch_is_invalid_input(self, repository, library):
        with pytest.raises(SearchInputError) as excinfo:
            _search(
                repository,
                library,
                config=SearchConfig(budget=SearchBudget(amount=1000, currency="USD")),
            )
        assert excinfo.value.code == "INVALID_BUDGET_CURRENCY"
        assert "no exchange rate" in str(excinfo.value)

    def test_candidate_limit_truncation_never_claims_optimality(self, repository, library):
        outcome = _search(
            repository,
            library,
            config=SearchConfig(max_interventions=2, max_candidates=2),
        )
        assert outcome.status.exhaustive is False
        assert "candidate_limit" in outcome.status.limits_hit
        assert outcome.domain.truncated_by == ["candidate_limit"]
        assert outcome.status.solver_status.value == "FEASIBLE_NOT_PROVEN_OPTIMAL"
        for candidate in outcome.candidates:
            assert candidate.proposal.solver_status.value != "OPTIMAL_IN_ENUMERATED_DOMAIN"

    def test_duration_limit_truncation_is_incomplete_not_empty(self, repository, library):
        outcome = _search(
            repository,
            library,
            config=SearchConfig(max_interventions=2, max_candidates=60, max_duration_ms=1),
        )
        assert outcome.status.exhaustive is False
        assert "duration_limit" in outcome.status.limits_hit
        assert outcome.status.solver_status.value == "INCOMPLETE_OR_UNKNOWN"
        assert outcome.status.best_proposal_id is None

    def test_invalid_inputs_are_explicit(self, repository, library):
        with pytest.raises(SearchInputError, match="not declared"):
            _search(repository, library, phase_id="ghost-phase")
        with pytest.raises(SearchInputError, match="unknown profile"):
            _search(repository, library, profile_ids=["GHOST"])
        with pytest.raises(SearchInputError, match="must not repeat"):
            _search(
                repository,
                library,
                profile_ids=["DEMO_PROFILE_MANUAL_WHEELCHAIR", "DEMO_PROFILE_MANUAL_WHEELCHAIR"],
            )
        with pytest.raises(SearchInputError, match="at least one mobility profile"):
            _search(repository, library, profile_ids=[])
        with pytest.raises(SearchInputError, match="unknown id"):
            _search(
                repository,
                library,
                config=SearchConfig(excluded_intervention_ids=["INT-GHOST"]),
            )
        with pytest.raises(SearchInputError, match="timezone-aware"):
            _search(repository, library, evaluation_instant=datetime(2026, 3, 1))


class TestReplay:
    def test_restart_replay_reads_back_the_identical_payload(self, repository, library, tmp_path):
        outcome = _search(repository, library)
        # Simulate a process restart: brand-new Database/Repository over the file.
        reopened = Repository(Database(repository.database.path))
        record = reopened.get_optimization_run(outcome.search_id)
        assert record.semantic_hash == outcome.semantic_hash
        assert record.scenario_revision == outcome.scenario_revision
        replayed = SearchOutcome.model_validate(record.payload)
        assert replayed.semantic_hash == outcome.semantic_hash
        assert replayed.model_dump(mode="json") == outcome.model_dump(mode="json")

        listed = reopened.list_optimization_runs(DEMO_SCENARIO_ID)
        assert [entry.search_id for entry in listed] == [outcome.search_id]

    def test_two_searches_both_persisted_with_distinct_execution_ids(self, repository, library):
        first = _search(repository, library)
        second = _search(repository, library)
        listed = repository.list_optimization_runs(DEMO_SCENARIO_ID)
        assert {entry.search_id for entry in listed} == {first.search_id, second.search_id}
        assert len({entry.semantic_hash for entry in listed}) == 1

    def test_naive_or_bad_evaluation_instants_from_callers_are_reported(self, repository, library):
        # Callers through the API cannot send naive instants, but the service
        # must also refuse one directly rather than evaluating at an unstated time.
        with pytest.raises(SearchInputError):
            _search(repository, library, evaluation_instant=datetime(2026, 3, 1, tzinfo=UTC).replace(tzinfo=None))


class TestRegressionBehaviourB20:
    """B20 (MASTER_PROMPT 12): no candidate restores the mandatory OD pair.

    Phase 2 closes E_ES1, so the east pair needs the modelled curb *and* the
    reopening together. With one intervention allowed, no single candidate can
    restore every required pair: the search must report the partial
    restoration and never present it as the full one.
    """

    def test_b20_partial_restoration_is_reported_never_as_full(self, repository, library):
        singles = _search(
            repository,
            library,
            phase_id="phase-2",
            config=SearchConfig(max_interventions=1, max_candidates=60, max_duration_ms=120_000),
        )
        assert singles.status.solver_status.value == "OPTIMAL_IN_ENUMERATED_DOMAIN"
        for candidate in singles.candidates:
            assert E_LIB not in candidate.restored_all_profiles, (
                "no single phase-2 candidate may claim to restore the east pair"
            )
        curb = _by_ids(singles)[("INT-MODEL-CURB-N_EK",)]
        assert curb.restored_all_profiles == [W_LIB]
        assert singles.status.best_proposal_id == curb.proposal.proposal_id

        # Allowing two interventions finds the joint answer; the dependency
        # expansion is the engine's, not the caller's, to discover.
        joint = _search(
            repository,
            library,
            phase_id="phase-2",
            config=SearchConfig(max_interventions=2, max_candidates=60, max_duration_ms=120_000),
        )
        pair = _by_ids(joint)[("INT-MODEL-CURB-N_EK", "INT-REOPEN-E_ES1-P2")]
        assert pair.restored_all_profiles == [E_LIB, W_LIB]
        assert pair.proposal.restored_required_od is True
