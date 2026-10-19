"""Gate 5 baseline evaluation (B1-B4) with a measured report artefact.

Four research-grade baselines are run against the seeded synthetic demo
project using only the real engine:

* **B1 - no intervention**: the source scenario's own analysis (the "do
  nothing" baseline every gain is measured against).
* **B2 - best single intervention**: complete enumeration of size-1 subsets.
* **B3 - greedy extension**: the policy-best candidate of size two that keeps
  B2's winner (extending the cheapest credible fix with its best complement).
* **B4 - bounded exhaustive**: the engine's preferred candidate over the full
  domain (``max_interventions=2``) with the declared lexicographic policy.

The measured numbers are written to ``var/optimization-baseline.json`` as
evidence. They are *measured on this machine for the synthetic demo project*;
they are not published benchmarks and not claims about real locations.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from detour_lab import ENGINE_VERSION
from detour_lab.api.main import seed_demo
from detour_lab.api.state import DEMO_SCENARIO_ID
from detour_lab.optimization import load_intervention_library, run_search
from detour_lab.optimization.model import SearchConfig
from detour_lab.persistence.db import Database
from detour_lab.persistence.repository import Repository
from tests.conftest import AS_OF, REPO_ROOT

LIBRARY_PATH = REPO_ROOT / "data" / "demo" / "interventions.demo.json"
REPORT_PATH = REPO_ROOT / "var" / "optimization-baseline.json"

PHASE = "phase-1"


@pytest.fixture()
def repository(tmp_path) -> Repository:
    database = Database(tmp_path / "baselines.sqlite3")
    database.migrate()
    repo = Repository(database)
    seed_demo(repo)
    return repo


@pytest.fixture()
def library():
    return load_intervention_library(LIBRARY_PATH)


def _search(repository, library, *, max_interventions: int, max_candidates: int = 60):
    return run_search(
        repository=repository,
        library=library,
        scenario_id=DEMO_SCENARIO_ID,
        phase_id=PHASE,
        profile_ids=None,
        evaluation_instant=AS_OF,
        config=SearchConfig(
            max_interventions=max_interventions,
            max_candidates=max_candidates,
            max_duration_ms=120_000,
        ),
    )


def _candidate_row(candidate) -> dict:
    return {
        "classification": candidate.classification,
        "solver_status": candidate.proposal.solver_status.value,
        "proposal_id": candidate.proposal.proposal_id,
        "intervention_ids": list(candidate.intervention_ids),
        "restored_all_profiles": list(candidate.restored_all_profiles),
        "restored_any_profile": list(candidate.restored_any_profile),
        "restored_required_od": candidate.proposal.restored_required_od,
        "regressed_pairs": list(candidate.regressed_pairs),
        "added_distance_m": candidate.proposal.added_distance_m,
        "cost_nominal": candidate.cost.nominal,
        "cost_unknown": candidate.cost.unknown,
        "introduced_fail_verdict_count": candidate.introduced_fail_verdict_count,
        "introduced_unknown_verdict_count": candidate.introduced_unknown_verdict_count,
        "rank": candidate.rank,
        "tie_group": candidate.tie_group,
        "pareto_optimal": candidate.pareto_optimal,
    }


class TestBaselineEvaluation:
    def test_b1_to_b4_are_measured_and_reported(self, repository, library):
        # -- B1: no intervention ------------------------------------------------
        b1 = _search(repository, library, max_interventions=1, max_candidates=1)
        b1_pairs = {}
        for profile in b1.baseline:
            b1_pairs[profile.profile_id] = {
                "semantic_hash": profile.semantic_hash,
                "confirmed_pairs": sum(1 for od in profile.od_results if od.confirmed_reachable),
                "possible_pairs": sum(1 for od in profile.od_results if od.possibly_reachable),
                "confirmed_distances_m": {
                    f"{od.origin_id}->{od.destination_id}": od.confirmed_distance_m
                    for od in profile.od_results
                    if od.confirmed_reachable
                },
            }
        assert b1_pairs, "B1 must contain the source analysis per profile"

        # -- B2: best single intervention (complete singles enumeration) --------
        b2 = _search(repository, library, max_interventions=1)
        assert b2.domain.exhausted is True
        assert b2.domain.evaluated_count == 4, "singles: bypass, curb, remeasure, backlane"
        b2_singles = [c for c in b2.candidates if c.rank == 1]
        assert b2_singles, "a complete singles domain must have a rank-1 row"
        b2_winner = b2_singles[0]
        assert b2_winner.classification == "certified"
        assert b2_winner.intervention_ids == ["INT-MODEL-CURB-N_EK"]

        # -- B3: greedy extension of B2's winner (size-2 subsets containing it) --
        b3 = _search(repository, library, max_interventions=2)
        extensions = [
            c
            for c in b3.candidates
            if len(c.intervention_ids) == 2
            and b2_winner.intervention_ids[0] in c.intervention_ids
            and c.classification != "rejected"
        ]
        # Two non-rejected complements exist (re-measure, back lane); the
        # bypass complement is rejected for the walker's width FAIL, and the
        # policy ranks the certified complement first.
        assert len(extensions) == 2
        b3_winner = extensions[0]
        assert b3_winner.classification == "certified"
        assert b3_winner.intervention_ids == [
            "INT-MODEL-CURB-N_EK",
            "INT-REMEASURE-ALT-TRACK",
        ]

        # -- B4: bounded exhaustive (the engine's preferred candidate) ----------
        b4 = _search(repository, library, max_interventions=2)
        assert b4.status.exhaustive is True
        assert b4.status.solver_status.value == "OPTIMAL_IN_ENUMERATED_DOMAIN"
        b4_winner = b4.candidates[0]
        assert b4_winner.rank == 1

        # B4 and B2/B3 agree on the intervention family and disagree on size:
        # the documented policy prefers one intervention; the Pareto frontier
        # keeps the two-intervention improvement visible.
        assert b4_winner.intervention_ids == b2_winner.intervention_ids
        pareto_ids = {c.proposal.proposal_id for c in b4.candidates if c.pareto_optimal}
        assert b3_winner.proposal.proposal_id in pareto_ids
        assert b4_winner.proposal.proposal_id in pareto_ids

        # -- The measured report -------------------------------------------------
        report = {
            "schema_version": "1.0.0",
            "engine_version": ENGINE_VERSION,
            "generated_by": "apps/api/tests/test_optimization_baselines.py",
            "measured_at": datetime.now(UTC).isoformat(),
            "dataset": {
                "project_id": "demo-project",
                "scenario_id": DEMO_SCENARIO_ID,
                "scenario_revision": b4.scenario_revision,
                "phase_id": PHASE,
                "profile_ids": b4.profile_ids,
                "evaluation_instant": b4.evaluation_instant,
            },
            "note": (
                "Measured on the synthetic demonstration project bundled in this repository. "
                "These are not field measurements and not published benchmarks; every value is a "
                "model output over synthetic data."
            ),
            "baselines": {
                "B1_no_intervention": {
                    "strategy": "source scenario analysis (do nothing)",
                    "profiles": b1_pairs,
                },
                "B2_best_single_intervention": {
                    "strategy": "complete singles enumeration, lexicographic policy",
                    "limits": b2.config.model_dump(mode="json"),
                    "status": b2.status.model_dump(mode="json"),
                    "winner": _candidate_row(b2_winner),
                },
                "B3_greedy_extension": {
                    "strategy": "best size-2 candidate keeping B2's winner",
                    "limits": b3.config.model_dump(mode="json"),
                    "winner": _candidate_row(b3_winner),
                },
                "B4_bounded_exhaustive": {
                    "strategy": "complete domain, lexicographic policy, Pareto frontier",
                    "limits": b4.config.model_dump(mode="json"),
                    "status": b4.status.model_dump(mode="json"),
                    "winner": _candidate_row(b4_winner),
                    "pareto_frontier": [
                        c.proposal.proposal_id for c in b4.candidates if c.pareto_optimal
                    ],
                },
            },
            "comparisons": {
                "b2_and_b4_agree_on_single_curb": True,
                "b3_adds_comparable_distance_improvement_m": b3_winner.proposal.added_distance_m,
                "b4_prefers_fewer_interventions": True,
                "all_winners_restore_same_pairs": (
                    b2_winner.restored_all_profiles
                    == b3_winner.restored_all_profiles
                    == b4_winner.restored_all_profiles
                ),
                "rejected_any": {
                    "bypass_phase1": [
                        c.proposal.proposal_id
                        for c in b4.candidates
                        if c.classification == "rejected"
                    ]
                },
            },
        }
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=False), encoding="utf-8")

        written = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        assert written["baselines"]["B4_bounded_exhaustive"]["winner"]["rank"] == 1
        assert written["comparisons"]["all_winners_restore_same_pairs"] is True
        # The measured report must contain real numbers, never placeholders.
        assert (
            written["baselines"]["B3_greedy_extension"]["winner"]["added_distance_m"]
            == pytest.approx(-14.137, abs=1e-3)
        )
        assert written["comparisons"]["b2_and_b4_agree_on_single_curb"] is True
