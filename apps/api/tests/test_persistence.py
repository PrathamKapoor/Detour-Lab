"""Persistence, replay and transactional-integrity tests (Gate 2)."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime

import pytest
from detour_lab.api.state import DEMO_PROJECT_ID, DEMO_SCENARIO_ID, seed_dataset_path
from detour_lab.domain.contracts import GraphEdit, Scenario
from detour_lab.domain.hashing import semantic_hash
from detour_lab.ingestion.schema import load_local_planar_dataset
from detour_lab.persistence.db import SCHEMA_VERSION, Database
from detour_lab.persistence.repository import NotFoundError, OptimisticConflictError, Repository
from detour_lab.reporting.manifest import build_manifest, manifest_semantic_hash
from detour_lab.rules.engine import load_rulepack
from detour_lab.rules.profiles import DEMO_PROFILES, profile_by_id
from tests.conftest import RULEPACK_PATH

EVAL_INSTANT = datetime(2026, 3, 1, tzinfo=UTC)


@pytest.fixture()
def db_path(tmp_path):
    return tmp_path / "detour_lab.sqlite3"


@pytest.fixture()
def repository(db_path) -> Repository:
    database = Database(db_path)
    database.migrate()
    repo = Repository(database)
    bundle = load_local_planar_dataset(seed_dataset_path())
    repo.import_dataset(
        project_id=DEMO_PROJECT_ID,
        project_name=bundle.project.name,
        graph=bundle.graph,
        origins_destinations=list(bundle.origins_destinations),
        phases=list(bundle.phases),
        temporary_edges=list(bundle.temporary_edges),
        notice=bundle.notice,
    )
    rulepack = load_rulepack(RULEPACK_PATH)
    repo.create_scenario(
        Scenario(
            id=DEMO_SCENARIO_ID,
            base_graph_version_id=bundle.graph.version.id,
            rulepack_id=rulepack.id,
            rulepack_hash=rulepack.content_hash,
            profile_ids=[p.id for p in DEMO_PROFILES],
            phases=list(bundle.phases),
            origins_destinations=list(bundle.origins_destinations),
            temporary_edges=list(bundle.temporary_edges),
        ),
        project_id=DEMO_PROJECT_ID,
    )
    return repo


class TestMigrations:
    def test_migrations_are_idempotent(self, db_path):
        database = Database(db_path)
        first = database.migrate()
        assert first
        assert database.migrate() == []
        assert database.applied_version() == SCHEMA_VERSION

    def test_foreign_keys_are_enforced(self, db_path):
        database = Database(db_path)
        database.migrate()
        with pytest.raises(sqlite3.IntegrityError), database.transaction() as connection:
            connection.execute(
                "INSERT INTO scenarios (id, project_id, parent_scenario_id, base_graph_version_id,"
                " rulepack_id, rulepack_hash, revision, content_hash, payload_json, created_at)"
                " VALUES ('s', 'ghost-project', NULL, 'ghost-graph', 'rp', 'h', 1, 'h', '{}', 'now')"
            )

    def test_edge_endpoints_are_foreign_keyed_to_nodes(self, db_path, repository):
        with pytest.raises(sqlite3.IntegrityError), repository.database.transaction() as connection:
            connection.execute(
                "INSERT INTO edges (graph_version_id, edge_id, u_id, v_id, edge_type, length_m, payload_json)"
                " VALUES ('demo-graph-v1', 'E_BAD', 'N_W', 'N_GHOST', 'sidewalk', 1.0, '{}')"
            )

    def test_rolled_back_transaction_leaves_nothing_behind(self, db_path, repository):
        before = repository.counts()
        with pytest.raises(RuntimeError):
            with repository.database.transaction() as connection:
                connection.execute(
                    "INSERT INTO projects (id, name, study_area_description, basis_json, jurisdiction,"
                    " owner, source_json, notice, created_at) VALUES ('p2', 'n', '', '{}', 'u', 'u', '{}', '', 'now')"
                )
                raise RuntimeError("simulated failure after the insert")
        assert repository.counts() == before
        with pytest.raises(NotFoundError):
            repository.get_project("p2")


class TestGraphRoundTrip:
    def test_stored_graph_rebuilds_to_the_same_content_hash(self, repository):
        original = load_local_planar_dataset(seed_dataset_path()).graph
        rebuilt = repository.get_graph_version(original.version.id)
        assert rebuilt.content_hash == original.content_hash
        assert [n.id for n in rebuilt.nodes] == [n.id for n in original.nodes]
        assert [e.id for e in rebuilt.edges] == [e.id for e in original.edges]
        assert rebuilt.evidence_registry.all_records() == original.evidence_registry.all_records()

    def test_duplicate_content_is_not_stored_twice(self, repository):
        graph = load_local_planar_dataset(seed_dataset_path()).graph
        before = repository.counts()["graph_versions"]
        repository.save_graph_version(DEMO_PROJECT_ID, graph)
        assert repository.counts()["graph_versions"] == before

    def test_unknown_graph_version_is_a_not_found(self, repository):
        with pytest.raises(NotFoundError):
            repository.get_graph_version("no-such-graph")


class TestAtomicImport:
    def test_rejected_dataset_creates_no_project_and_no_rows(self, db_path):
        database = Database(db_path)
        database.migrate()
        repo = Repository(database)
        payload = json.loads(seed_dataset_path().read_text(encoding="utf-8"))
        payload["evidence"].append(
            {
                "id": "EV-GHOST", "element_id": "E_GHOST", "field": "width_mm",
                "value": 1000, "unit": "mm", "method": "test", "source": "test",
            }
        )
        import tempfile
        from pathlib import Path

        from detour_lab.ingestion.schema import IngestionError

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with pytest.raises(IngestionError):
                load_local_planar_dataset(path)

        counts = repo.counts()
        assert counts["projects"] == 0
        assert counts["graph_versions"] == 0
        assert counts["nodes"] == 0

    def test_importing_the_same_content_twice_is_idempotent(self, repository):
        bundle = load_local_planar_dataset(seed_dataset_path())
        repository.import_dataset(
            project_id=DEMO_PROJECT_ID,
            project_name=bundle.project.name,
            graph=bundle.graph,
            origins_destinations=list(bundle.origins_destinations),
            phases=list(bundle.phases),
            temporary_edges=list(bundle.temporary_edges),
            notice=bundle.notice,
        )
        counts = repository.counts()
        assert counts["projects"] == 1
        assert counts["graph_versions"] == 1
        assert counts["evidence"] == 37


class TestScenarioRevisions:
    def test_edit_creates_a_new_revision_and_keeps_history(self, repository):
        before = repository.get_scenario(DEMO_SCENARIO_ID)
        updated = repository.apply_scenario_edit(
            scenario_id=DEMO_SCENARIO_ID,
            expected_revision=before.revision,
            edit=GraphEdit(
                op="update_attribute",
                target_id="E_ALT",
                params={
                    "field": "width_mm", "value": 1800, "unit": "mm",
                    "method": "manual_entry", "source": "planner (test)",
                    "provenance_class": "assumed", "synthetic": False,
                    "observed_at": "2026-02-01T10:00:00Z",
                },
            ),
            note="measured the rear access track width",
        )
        assert updated.revision == before.revision + 1
        assert updated.content_hash != before.content_hash
        assert updated.note == "measured the rear access track width"

        history = repository.scenario_revisions(DEMO_SCENARIO_ID)
        assert [r["revision"] for r in history] == [1, 2]
        assert history[0]["content_hash"] == before.content_hash
        assert repository.get_scenario(DEMO_SCENARIO_ID).content_hash == updated.content_hash

    def test_stale_revision_is_rejected_with_a_conflict(self, repository):
        current = repository.get_scenario(DEMO_SCENARIO_ID)
        repository.apply_scenario_edit(
            scenario_id=DEMO_SCENARIO_ID,
            expected_revision=current.revision,
            edit=GraphEdit(op="remove_edge", target_id="E_ME", params={}),
        )
        with pytest.raises(OptimisticConflictError) as excinfo:
            repository.apply_scenario_edit(
                scenario_id=DEMO_SCENARIO_ID,
                expected_revision=current.revision,  # stale
                edit=GraphEdit(op="remove_edge", target_id="E_SSE", params={}),
            )
        assert excinfo.value.actual == current.revision + 1
        assert excinfo.value.code == "REVISION_CONFLICT"
        assert repository.get_scenario(DEMO_SCENARIO_ID).revision == current.revision + 1

    def test_unknown_scenario_edit_is_a_not_found(self, repository):
        with pytest.raises(NotFoundError):
            repository.apply_scenario_edit(
                scenario_id="ghost", expected_revision=1,
                edit=GraphEdit(op="remove_edge", target_id="E_ME", params={}),
            )


class TestRunsAndReplay:
    def _evaluate(self, repository):
        return repository.evaluate_and_store(
            scenario_id=DEMO_SCENARIO_ID,
            phase_id="phase-1",
            profile=profile_by_id("DEMO_PROFILE_MANUAL_WHEELCHAIR"),
            rulepack=load_rulepack(RULEPACK_PATH),
            evaluation_instant=EVAL_INSTANT,
        )

    def test_two_runs_with_identical_inputs_share_a_semantic_hash(self, repository):
        first = self._evaluate(repository)
        second = self._evaluate(repository)
        assert first.run_id != second.run_id
        assert first.semantic_hash == second.semantic_hash
        assert first.input_hash == second.input_hash
        assert first.result.model_dump(mode="json") == second.result.model_dump(mode="json")

    def test_twenty_runs_produce_one_distinct_semantic_hash(self, repository):
        hashes = {self._evaluate(repository).semantic_hash for _ in range(20)}
        assert len(hashes) == 1
        assert repository.counts()["analysis_runs"] == 20

    def test_different_phase_produces_a_different_hash(self, repository):
        assert self._evaluate(repository).semantic_hash != repository.evaluate_and_store(
            scenario_id=DEMO_SCENARIO_ID,
            phase_id="phase-2",
            profile=profile_by_id("DEMO_PROFILE_MANUAL_WHEELCHAIR"),
            rulepack=load_rulepack(RULEPACK_PATH),
            evaluation_instant=EVAL_INSTANT,
        ).semantic_hash

    def test_unknown_run_is_a_not_found(self, repository):
        with pytest.raises(NotFoundError):
            repository.get_run("run-does-not-exist")

    def test_run_payload_is_stored_and_reloadable(self, repository):
        record = self._evaluate(repository)
        loaded = repository.get_run(record.run_id)
        assert loaded.semantic_hash == record.semantic_hash
        assert loaded.evaluation_instant == EVAL_INSTANT.isoformat()
        assert loaded.result.model_dump(mode="json") == record.result.model_dump(mode="json")


class TestRestartPersistence:
    def test_a_new_process_reads_back_runs_scenarios_and_graph(self, db_path, repository):
        record = repository.evaluate_and_store(
            scenario_id=DEMO_SCENARIO_ID,
            phase_id="phase-1",
            profile=profile_by_id("DEMO_PROFILE_LIMITED_MOBILITY_WALKER"),
            rulepack=load_rulepack(RULEPACK_PATH),
            evaluation_instant=EVAL_INSTANT,
        )
        repository.apply_scenario_edit(
            scenario_id=DEMO_SCENARIO_ID,
            expected_revision=1,
            edit=GraphEdit(
                op="update_attribute",
                target_id="E_ALT",
                params={
                    "field": "width_mm", "value": 1800, "unit": "mm",
                    "method": "manual_entry", "source": "planner (restart test)",
                    "provenance_class": "assumed", "synthetic": False,
                    "observed_at": "2026-02-01T10:00:00Z",
                },
            ),
        )

        # Simulate a restart: brand-new Database/Repository objects over the same file.
        reopened = Repository(Database(db_path))
        assert reopened.database.applied_version() == SCHEMA_VERSION
        assert reopened.counts()["analysis_runs"] == 1

        reloaded_run = reopened.get_run(record.run_id)
        assert reloaded_run.semantic_hash == record.semantic_hash

        reloaded_scenario = reopened.get_scenario(DEMO_SCENARIO_ID)
        assert reloaded_scenario.revision == 2
        last_edit = reloaded_scenario.edits[-1]
        assert last_edit.op == "update_attribute"
        assert last_edit.params["field"] == "width_mm"
        assert last_edit.params["value"] == 1800
        assert [r["revision"] for r in reopened.scenario_revisions(DEMO_SCENARIO_ID)] == [1, 2]

    def test_replay_after_restart_reproduces_the_same_hash(self, db_path, repository):
        record = repository.evaluate_and_store(
            scenario_id=DEMO_SCENARIO_ID,
            phase_id="phase-1",
            profile=profile_by_id("DEMO_PROFILE_MANUAL_WHEELCHAIR"),
            rulepack=load_rulepack(RULEPACK_PATH),
            evaluation_instant=EVAL_INSTANT,
        )
        reopened = Repository(Database(db_path))
        replayed = reopened.evaluate_and_store(
            scenario_id=DEMO_SCENARIO_ID,
            phase_id="phase-1",
            profile=profile_by_id("DEMO_PROFILE_MANUAL_WHEELCHAIR"),
            rulepack=load_rulepack(RULEPACK_PATH),
            evaluation_instant=EVAL_INSTANT,
        )
        assert replayed.semantic_hash == record.semantic_hash
        assert replayed.result.model_dump(mode="json") == record.result.model_dump(mode="json")


class TestManifest:
    def _manifest(self, repository, phase_id="phase-1", profile_id="DEMO_PROFILE_MANUAL_WHEELCHAIR"):
        record = repository.evaluate_and_store(
            scenario_id=DEMO_SCENARIO_ID,
            phase_id=phase_id,
            profile=profile_by_id(profile_id),
            rulepack=load_rulepack(RULEPACK_PATH),
            evaluation_instant=EVAL_INSTANT,
        )
        return build_manifest(
            record=record,
            graph=repository.get_graph_version("demo-graph-v1"),
            rulepack=load_rulepack(RULEPACK_PATH),
            profile=profile_by_id(profile_id),
            scenario=repository.get_scenario(DEMO_SCENARIO_ID),
            dataset_notice="SYNTHETIC SCHEMATIC DATASET - NOT A REAL PLACE",
        )

    def test_manifest_identifies_every_required_version(self, repository):
        manifest = self._manifest(repository)
        assert manifest["engine_version"]
        assert manifest["ruleset"]["id"] == "DEMO_RULEPACK_NOT_LEGAL"
        assert manifest["ruleset"]["content_hash"].startswith("sha256:")
        assert manifest["ruleset"]["legal_applicability"] == "unverified"
        assert manifest["inputs"]["base_graph_hash"].startswith("sha256:")
        assert manifest["inputs"]["run_input_hash"].startswith("sha256:")
        assert manifest["scenario"]["content_hash"].startswith("sha256:")
        assert manifest["profile"]["is_demo_profile"] is True
        assert manifest["schema_version"]

    def test_manifest_lists_every_unknown_and_failure(self, repository):
        manifest = self._manifest(repository)
        assert manifest["results"]["unknowns"]
        assert manifest["results"]["known_failures"]
        assert all({"element_id", "rule_id", "reason_code", "explanation"} <= set(u) for u in manifest["results"]["unknowns"])

    def test_manifest_carries_od_matrix_and_route_edge_ids(self, repository):
        manifest = self._manifest(repository)
        matrix = manifest["results"]["origin_destination_matrix"]
        assert matrix
        confirmed = [od for od in matrix if od["confirmed_reachable"]]
        assert confirmed
        assert all(od["confirmed_path_edge_ids"] for od in confirmed)
        unreachable = [od for od in matrix if not od["possibly_reachable"]]
        assert all(od["confirmed_distance_m"] is None for od in unreachable)

    def test_runtime_block_is_excluded_from_the_semantic_hash(self, repository):
        first = self._manifest(repository)
        second = self._manifest(repository)
        assert first["runtime"]["run_id"] != second["runtime"]["run_id"]
        assert first["semantic_hash"] == second["semantic_hash"]
        assert manifest_semantic_hash(first) == first["semantic_hash"]

    def test_manifest_states_it_is_not_certified(self, repository):
        manifest = self._manifest(repository)
        assert "not certified" in manifest["disclaimer"].lower()
        assert manifest["limitations"]
        assert manifest["attributions"][0]["license"]

    def test_manifest_never_contains_approval_language(self, repository):
        manifest = self._manifest(repository)
        text = json.dumps(manifest).lower()
        assert "legally compliant" not in text
        assert "certified by" not in text
        assert manifest["ruleset"]["legal_applicability"] == "unverified"


def test_semantic_hash_is_stable_for_the_same_payload(repository):
    manifest = TestManifest()._manifest(repository)
    assert semantic_hash({k: v for k, v in manifest.items() if k not in {"runtime"}}) == semantic_hash(
        {k: v for k, v in manifest.items() if k not in {"runtime"}}
    )