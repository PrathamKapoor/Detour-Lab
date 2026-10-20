"""Automated pytest test suite for Gate 7 research baselines and benchmarks.

Verifies:
1. Deterministic fixture catalog construction across all 20 fixtures (F01..F20).
2. Baseline A unconstrained routing detecting false-safe paths.
3. Baseline B static routing detecting phase-blindness.
4. Baseline C rule checklist detecting disconnection-blindness.
5. Baseline D greedy optimizer vs authoritative optimization.
6. Baseline E decision-blocking priority queue efficiency.
7. Scalability grid generator and latency profiling integrity.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from detour_lab.api.main import seed_demo
from detour_lab.benchmarks.baselines import (
    run_baseline_a_shortest_path,
    run_baseline_b_static_routing,
    run_baseline_c_rule_checklist,
    run_baseline_d_greedy_optimizer,
    run_baseline_e_inspection_ordering,
)
from detour_lab.benchmarks.fixtures import (
    ALL_FIXTURES,
    BENCHMARK_AS_OF,
    build_fixture_catalog,
    get_fixture,
)
from detour_lab.benchmarks.scalability import (
    generate_synthetic_grid_graph,
    run_scalability_suite,
)
from detour_lab.optimization import load_intervention_library
from detour_lab.persistence.db import Database
from detour_lab.persistence.repository import Repository
from detour_lab.rules.profiles import DEMO_PROFILES, profile_by_id


class TestBenchmarkFixtures:
    """Fixture catalog construction and ground-truth validation."""

    def test_catalog_contains_all_20_fixtures(self, rulepack):
        catalog = build_fixture_catalog(rulepack, DEMO_PROFILES)
        assert len(catalog) == 20
        for fid in ALL_FIXTURES:
            assert fid in catalog, f"Missing fixture {fid}"
            fix = catalog[fid]
            assert fix.id == fid
            assert fix.base_graph is not None
            assert fix.scenario is not None
            assert len(fix.target_od) == 2
            assert fix.target_phase_id != ""

    def test_get_fixture_accessor(self, rulepack):
        f01 = get_fixture("F01", rulepack, DEMO_PROFILES)
        assert f01.id == "F01"
        assert f01.category == "connected_network"

        with pytest.raises(KeyError, match="Unknown benchmark fixture"):
            get_fixture("F99", rulepack, DEMO_PROFILES)


class TestBaselineEvaluations:
    """Comparative scientific evaluation of Baselines A through E."""

    @pytest.fixture()
    def wheelchair_profile(self):
        return profile_by_id("DEMO_PROFILE_MANUAL_WHEELCHAIR")

    @pytest.fixture()
    def walker_profile(self):
        return profile_by_id("DEMO_PROFILE_LIMITED_MOBILITY_WALKER")

    @pytest.fixture()
    def seeded_repo(self, tmp_path):
        db_path = tmp_path / "test_repo.sqlite3"
        db = Database(db_path)
        db.migrate()
        repo = Repository(db)
        seed_demo(repo)
        return repo

    def test_baseline_a_false_safe_on_steep_grade(self, rulepack, wheelchair_profile):
        """Baseline A reports connected, but DETOUR LAB flags grade violation (False-Safe)."""
        fix = get_fixture("F03", rulepack, DEMO_PROFILES)
        orig, dest = fix.target_od
        res = run_baseline_a_shortest_path(
            graph=fix.base_graph,
            origin_id=orig,
            destination_id=dest,
            profile=wheelchair_profile,
            rulepack=rulepack,
            as_of=BENCHMARK_AS_OF,
        )
        assert res.path_found is True
        # Path found by Baseline A is the 60m steep edge E_STEEP (grade 14%)
        assert res.has_modeled_violation is True
        assert "E_STEEP" in res.failing_edge_ids
        assert res.is_false_safe is True
        # DETOUR LAB authoritative engine finds the longer 90m gentle edge
        assert res.detour_lab_confirmed is True

    def test_baseline_b_phase_blindness_on_closure(self, rulepack, wheelchair_profile):
        """Baseline B is blind to phase closures (Phase-invalidation)."""
        fix = get_fixture("F04", rulepack, DEMO_PROFILES)
        orig, dest = fix.target_od
        res = run_baseline_b_static_routing(
            base_graph=fix.base_graph,
            scenario=fix.scenario,
            target_phase_id=fix.target_phase_id,
            origin_id=orig,
            destination_id=dest,
            profile=wheelchair_profile,
            rulepack=rulepack,
            as_of=BENCHMARK_AS_OF,
        )
        assert res.static_confirmed is True
        assert res.phased_confirmed is False
        assert res.is_false_safe_closure is True

    def test_baseline_b_phase_blindness_on_temporary_detour(self, rulepack, wheelchair_profile):
        """Baseline B misses temporary bypass detours active only in Phase 2."""
        fix = get_fixture("F10", rulepack, DEMO_PROFILES)
        orig, dest = fix.target_od
        res = run_baseline_b_static_routing(
            base_graph=fix.base_graph,
            scenario=fix.scenario,
            target_phase_id="p2",
            origin_id=orig,
            destination_id=dest,
            profile=wheelchair_profile,
            rulepack=rulepack,
            as_of=BENCHMARK_AS_OF,
        )
        # Static base graph has E_AB open (so static is confirmed)
        # But in Phase 2, E_AB is closed and temporary detour E_TEMP_AC is active
        assert res.phased_confirmed is True
        assert res.phased_distance_m == 110.0

    def test_baseline_c_disconnection_blindness_on_missing_junction(self, rulepack, wheelchair_profile):
        """Baseline C passes 100% of individual segments but network is disconnected."""
        fix = get_fixture("F02", rulepack, DEMO_PROFILES)
        orig, dest = fix.target_od
        res = run_baseline_c_rule_checklist(
            graph=fix.base_graph,
            origin_id=orig,
            destination_id=dest,
            profile=wheelchair_profile,
            rulepack=rulepack,
            as_of=BENCHMARK_AS_OF,
        )
        assert res.total_edges == 2
        assert res.pass_edges == 2
        assert res.segment_compliance_rate == 1.0
        assert res.end_to_end_connected is False
        assert res.is_disconnection_blind is True

    def test_baseline_d_evaluates_cleanly(self, seeded_repo, rulepack, wheelchair_profile):
        """Baseline D runs greedy single-step optimization and compares against authoritative search."""
        lib_path = Path(__file__).resolve().parents[3] / "data" / "demo" / "interventions.demo.json"
        library = load_intervention_library(lib_path)

        res = run_baseline_d_greedy_optimizer(
            repository=seeded_repo,
            library=library,
            scenario_id="scn-demo-baseline",
            phase_id="phase-1",
            profile_ids=[wheelchair_profile.id],
            evaluation_instant=BENCHMARK_AS_OF,
            max_steps=2,
        )
        assert res.detour_lab_winner_intervention_ids is not None

    def test_baseline_e_inspection_ordering_gain(self, seeded_repo, rulepack):
        """Baseline E prioritizes decision-blocking unverified attributes over natural/random order."""
        scn = seeded_repo.get_scenario("scn-demo-baseline")
        assert scn is not None
        graph = seeded_repo.get_graph_version(scn.base_graph_version_id)
        assert graph is not None

        res = run_baseline_e_inspection_ordering(
            base_graph=graph,
            scenario=scn,
            phase_id="phase-1",
            profile_ids=["DEMO_PROFILE_MANUAL_WHEELCHAIR"],
            target_od=("OD-E", "OD-LIB"),
            rulepack=rulepack,
            as_of=BENCHMARK_AS_OF,
            random_trials=30,
        )
        assert res.detour_lab_inspections == 1
        assert res.naive_first_listed_inspections >= res.detour_lab_inspections
        assert res.efficiency_gain_over_naive > 0.0
        assert res.efficiency_gain_over_random > 0.0


class TestScalabilityGrid:
    """Synthetic grid generator and scalability profiling tests."""

    def test_generate_synthetic_grid_structure(self):
        graph, (orig, dest) = generate_synthetic_grid_graph(4, 4, spacing_m=20.0, version_id="test-grid-4x4")
        assert len(graph.nodes) == 16
        # In a 4x4 grid:
        # Horizontal edges: 4 rows * 3 segments * 2 directions = 24
        # Vertical edges: 3 rows * 4 segments * 2 directions = 24
        # Total = 48 directed edges
        assert len(graph.edges) == 48
        assert orig == "N_0_0"
        assert dest == "N_3_3"

    def test_run_small_scalability_suite(self, rulepack):
        profile = profile_by_id("DEMO_PROFILE_MANUAL_WHEELCHAIR")
        res = run_scalability_suite(
            rulepack=rulepack,
            profile=profile,
            iterations=1,
        )
        assert len(res.routing_timings) == 4
        assert res.routing_timings[0].node_count == 16
        assert res.routing_timings[0].p50_ms < 50.0
        assert len(res.rule_eval_timings) == 4
        assert len(res.queue_timings) == 3  # small, medium, large
