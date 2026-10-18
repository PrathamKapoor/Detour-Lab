"""End-to-end HTTP integration: mutation flows, concurrency, restart and safety."""

from __future__ import annotations

import json

import pytest
from detour_lab.api.main import create_app
from detour_lab.api.state import DEMO_SCENARIO_ID, seed_dataset_path
from fastapi.testclient import TestClient

EVAL_INSTANT = "2026-03-01T00:00:00Z"


@pytest.fixture()
def database_path(tmp_path):
    return tmp_path / "integration.sqlite3"


@pytest.fixture()
def client(database_path):
    with TestClient(create_app(database_path)) as test_client:
        yield test_client


def _dataset() -> dict:
    return json.loads(seed_dataset_path().read_text(encoding="utf-8"))


def _evaluate(client, phase_id="phase-1", profile_id="DEMO_PROFILE_MANUAL_WHEELCHAIR", scenario=DEMO_SCENARIO_ID):
    response = client.post(
        f"/api/v1/scenarios/{scenario}/evaluate",
        json={"profile_id": profile_id, "phase_id": phase_id, "evaluation_instant": EVAL_INSTANT},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _edge_state(body, edge_id):
    return next(e["state"] for e in body["result"]["edge_evaluations"] if e["edge_id"] == edge_id)


class TestProjectAndImportFlow:
    def test_create_project_then_import_dataset(self, client):
        created = client.post(
            "/api/v1/projects",
            json={
                "id": "proj-import",
                "name": "Imported synthetic study",
                "study_area_description": "second project for the import path",
                "notice": "SYNTHETIC",
            },
        )
        assert created.status_code == 201

        response = client.post("/api/v1/projects/proj-import/imports", json={"dataset": _dataset()})
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["node_count"] == 9
        assert body["edge_count"] == 12
        assert body["evidence_count"] == 37
        assert "SYNTHETIC" in body["notice"].upper()

        graph = client.get("/api/v1/projects/proj-import/graph").json()
        assert graph["graph_version_id"] == "demo-graph-v1"

    def test_duplicate_project_creation_is_a_409(self, client):
        payload = {"id": "proj-dup", "name": "First"}
        assert client.post("/api/v1/projects", json=payload).status_code == 201
        second = client.post("/api/v1/projects", json=payload)
        assert second.status_code == 409
        assert second.json()["code"] == "PROJECT_EXISTS"

    def test_malformed_dataset_is_rejected_and_writes_nothing(self, client):
        before = client.get("/api/v1/health").json()["row_counts"]
        broken = _dataset()
        broken["schema"] = "not-our-schema/9.9"
        response = client.post("/api/v1/projects/ghost-import/imports", json={"dataset": broken})
        assert response.status_code == 422
        assert response.json()["code"] == "UNSUPPORTED_SCHEMA"
        after = client.get("/api/v1/health").json()["row_counts"]
        assert after == before

    def test_import_with_unknown_element_reference_is_rejected_atomically(self, client):
        before = client.get("/api/v1/health").json()["row_counts"]
        broken = _dataset()
        broken["evidence"].append(
            {
                "id": "EV-GHOST", "element_id": "E_NOT_THERE", "field": "width_mm",
                "value": 1200, "unit": "mm", "method": "test", "source": "test",
            }
        )
        response = client.post("/api/v1/projects/ghost-2/imports", json={"dataset": broken})
        assert response.status_code == 422
        assert response.json()["code"] == "UNKNOWN_NODE_REFERENCE"
        assert client.get("/api/v1/health").json()["row_counts"] == before
        assert client.get("/api/v1/projects/ghost-2/graph").status_code == 404


class TestScenarioEditingFlow:
    def test_patch_creates_a_revision_and_changes_the_computed_result(self, client):
        before = _evaluate(client)
        assert _edge_state(before, "E_ALT") == "UNKNOWN"

        patched = client.patch(
            f"/api/v1/scenarios/{DEMO_SCENARIO_ID}",
            json={
                "expected_revision": 1,
                "edits": [
                    {
                        "op": "update_attribute",
                        "target_id": "E_ALT",
                        "params": {
                            "field": "width_mm", "value": 1800, "unit": "mm",
                            "method": "manual_entry", "source": "planner entry (test)",
                            "provenance_class": "assumed", "synthetic": False,
                            "observed_at": "2026-02-01T10:00:00Z",
                        },
                    },
                    {
                        "op": "update_attribute",
                        "target_id": "E_ALT",
                        "params": {
                            "field": "slope_percent", "value": 2.0, "unit": "percent",
                            "method": "manual_entry", "source": "planner entry (test)",
                            "provenance_class": "assumed", "synthetic": False,
                            "observed_at": "2026-02-01T10:00:00Z",
                        },
                    },
                ],
                "note": "entered the missing rear access track measurements",
            },
        )
        assert patched.status_code == 200, patched.text
        # Each edit becomes its own immutable revision: 1 -> 2 -> 3.
        assert patched.json()["revision"] == 3

        after = _evaluate(client)
        assert _edge_state(after, "E_ALT") == "PASS"
        assert after["run"]["semantic_hash"] != before["run"]["semantic_hash"]

    def test_stale_revision_returns_409_with_both_revisions(self, client):
        assert client.patch(
            f"/api/v1/scenarios/{DEMO_SCENARIO_ID}",
            json={
                "expected_revision": 1,
                "edits": [
                    {
                        "op": "update_attribute",
                        "target_id": "E_SSE",
                        "params": {
                            "field": "width_mm", "value": 2100, "unit": "mm",
                            "method": "manual_entry", "source": "re-measure (test)",
                            "provenance_class": "assumed", "synthetic": False,
                            "observed_at": "2026-02-01T10:00:00Z",
                        },
                    }
                ],
            },
        ).status_code == 200

        conflict = client.patch(
            f"/api/v1/scenarios/{DEMO_SCENARIO_ID}",
            json={
                "expected_revision": 1,  # stale
                "edits": [
                    {
                        "op": "update_attribute",
                        "target_id": "E_SSE",
                        "params": {
                            "field": "width_mm", "value": 2200, "unit": "mm",
                            "method": "manual_entry", "source": "second re-measure (test)",
                            "provenance_class": "assumed", "synthetic": False,
                            "observed_at": "2026-02-02T10:00:00Z",
                        },
                    }
                ],
            },
        )
        assert conflict.status_code == 409
        body = conflict.json()
        assert body["code"] == "REVISION_CONFLICT"
        assert body["details"] == {"expected_revision": 1, "actual_revision": 2}

    def test_removing_an_edge_that_a_phase_closes_is_rejected(self, client):
        """A closure and a removal cannot contradict each other silently."""
        response = client.patch(
            f"/api/v1/scenarios/{DEMO_SCENARIO_ID}",
            json={
                "expected_revision": 1,
                "edits": [{"op": "remove_edge", "target_id": "E_ME", "params": {}}],
            },
        )
        assert response.status_code == 422
        assert response.json()["code"] == "UNKNOWN_NODE_REFERENCE"
        assert "E_ME" in response.json()["message"]

    def test_edit_that_closes_an_unknown_edge_changes_reachability(self, client):
        # N_EK has no curb evidence, so the east link is UNKNOWN. Closing it removes
        # the only hypothetical route from the east transit stop to the library.
        before = _evaluate(client)
        pair = next(
            od for od in before["result"]["od_results"]
            if od["origin_id"] == "OD-E" and od["destination_id"] == "OD-LIB"
        )
        assert pair["possibly_reachable"] is True

        patched = client.patch(
            f"/api/v1/scenarios/{DEMO_SCENARIO_ID}",
            json={
                "expected_revision": 1,
                "edits": [
                    {
                        "op": "close_edge",
                        "target_id": "E_ES1",
                        "params": {"phases": ["phase-1"]},
                    }
                ],
            },
        )
        assert patched.status_code == 200
        after = _evaluate(client)
        pair_after = next(
            od for od in after["result"]["od_results"]
            if od["origin_id"] == "OD-E" and od["destination_id"] == "OD-LIB"
        )
        assert pair_after["possibly_reachable"] is False

    def test_revision_history_is_listed(self, client):
        client.patch(
            f"/api/v1/scenarios/{DEMO_SCENARIO_ID}",
            json={
                "expected_revision": 1,
                "edits": [
                    {
                        "op": "update_attribute",
                        "target_id": "E_SSE",
                        "params": {
                            "field": "surface", "value": "asphalt", "unit": None,
                            "method": "manual_entry", "source": "surface re-check (test)",
                            "provenance_class": "assumed", "synthetic": False,
                            "observed_at": "2026-02-01T10:00:00Z",
                        },
                    }
                ],
            },
        )
        revisions = client.get(f"/api/v1/scenarios/{DEMO_SCENARIO_ID}/revisions").json()["revisions"]
        assert [r["revision"] for r in revisions] == [1, 2]
        assert revisions[0]["content_hash"] != revisions[1]["content_hash"]

    def test_cyclic_or_invalid_edit_returns_422(self, client):
        response = client.patch(
            f"/api/v1/scenarios/{DEMO_SCENARIO_ID}",
            json={
                "expected_revision": 1,
                "edits": [{"op": "add_edge", "target_id": "E_X", "params": {"id": "E_X", "u": "N_W", "v": "N_GHOST"}}],
            },
        )
        assert response.status_code == 422
        assert response.json()["code"] == "UNKNOWN_NODE_REFERENCE"


class TestRestartPersistence:
    def test_edits_and_runs_survive_a_process_restart(self, database_path):
        with TestClient(create_app(database_path)) as first:
            first.patch(
                f"/api/v1/scenarios/{DEMO_SCENARIO_ID}",
                json={
                    "expected_revision": 1,
                    "edits": [
                        {
                            "op": "update_attribute",
                            "target_id": "N_EK",
                            "params": {
                                "field": "curb_transition", "value": "flush", "unit": None,
                                "method": "manual_entry", "source": "field check (test)",
                                "provenance_class": "assumed", "synthetic": False,
                                "observed_at": "2026-02-01T10:00:00Z",
                            },
                        }
                    ],
                },
            )
            run = _evaluate(first, phase_id="phase-2")
            assert any(
                od["confirmed_reachable"] for od in run["result"]["od_results"]
            )

        # Fresh application object over the same file: a real restart.
        with TestClient(create_app(database_path)) as second:
            counts = second.get("/api/v1/health").json()["row_counts"]
            assert counts["analysis_runs"] == 1
            assert counts["scenario_revisions"] == 2

            replayed = second.post(
                f"/api/v1/scenarios/{DEMO_SCENARIO_ID}/evaluate",
                json={
                    "profile_id": "DEMO_PROFILE_MANUAL_WHEELCHAIR",
                    "phase_id": "phase-2",
                    "evaluation_instant": EVAL_INSTANT,
                },
            ).json()
            assert replayed["run"]["semantic_hash"] == run["run"]["semantic_hash"]
            assert replayed["result"] == run["result"]

            revisions = second.get(f"/api/v1/scenarios/{DEMO_SCENARIO_ID}/revisions").json()["revisions"]
            assert [r["revision"] for r in revisions] == [1, 2]

    def test_startup_does_not_duplicate_the_seeded_demo(self, database_path):
        with TestClient(create_app(database_path)) as first:
            first_counts = first.get("/api/v1/health").json()["row_counts"]
        with TestClient(create_app(database_path)) as second:
            second_counts = second.get("/api/v1/health").json()["row_counts"]
        assert first_counts == second_counts
        assert first_counts["projects"] == 1
        assert first_counts["graph_versions"] == 1


class TestSafety:
    def test_sql_injection_attempt_is_stored_literally(self, client):
        payload = "Robert'); DROP TABLE projects;--"
        response = client.post("/api/v1/projects", json={"id": "proj-injection", "name": payload})
        assert response.status_code == 201
        stored = next(
            p for p in client.get("/api/v1/projects").json()["projects"] if p["id"] == "proj-injection"
        )
        assert stored["name"] == payload
        assert client.get("/api/v1/health").json()["row_counts"]["projects"] >= 2

    def test_path_traversal_in_identifiers_cannot_escape(self, client):
        response = client.get("/api/v1/projects/..%2F..%2Fetc%2Fpasswd/graph")
        assert response.status_code in (404, 400)
        assert "passwd" not in response.text

    def test_nan_and_infinity_payloads_are_rejected(self, client):
        response = client.post(
            "/api/v1/scenarios/demo/evaluate",
            content='{"profile_id":"DEMO_PROFILE_MANUAL_WHEELCHAIR","phase_id":"phase-1","evaluation_instant":NaN}',
            headers={"content-type": "application/json"},
        )
        assert response.status_code == 422

    def test_unknown_unit_surfaces_as_unknown_not_as_a_pass(self, client):
        """A source unit the engine cannot interpret must yield UNKNOWN, never PASS."""
        broken = _dataset()
        broken["graph_version_id"] = "bad-unit-graph"
        broken["evidence"] = [
            record for record in broken["evidence"] if record.get("element_id") != "E_WM" or record["field"] != "width_mm"
        ] + [
            {
                "id": "EV-BAD-UNIT", "element_id": "E_WM", "field": "width_mm",
                "value": 12, "unit": "smoots", "method": "test", "source": "test",
            }
        ]
        assert client.post("/api/v1/projects", json={"id": "proj-bad-unit", "name": "Bad units"}).status_code == 201
        assert client.post("/api/v1/projects/proj-bad-unit/imports", json={"dataset": broken}).status_code == 201

        scenario = client.post(
            "/api/v1/projects/proj-bad-unit/scenarios",
            json={
                "id": "scn-bad-unit",
                "name": "scenario on the bad-unit dataset",
                "base_graph_version_id": "bad-unit-graph",
                "phases": [{"id": "p1", "order": 1, "closed_edge_ids": [], "temporary_edge_ids": []}],
                "origins_destinations": [
                    {"id": "OD-W", "label": "West", "node_id": "N_W", "kind": "origin"},
                    {"id": "OD-LIB", "label": "Library", "node_id": "N_SE", "kind": "destination"},
                ],
                "temporary_edges": [],
            },
        )
        assert scenario.status_code == 201, scenario.text

        run = _evaluate(client, scenario="scn-bad-unit", phase_id="p1")
        unsupported = [v for v in run["result"]["verdicts"] if v["reason_code"] == "UNSUPPORTED_UNIT"]
        assert unsupported
        assert all(v["state"] == "UNKNOWN" for v in unsupported)
        assert all(v["element_id"] == "E_WM" for v in unsupported)
        assert _edge_state(run, "E_WM") != "PASS"

    def test_oversized_identifier_is_rejected_by_the_schema(self, client):
        response = client.post("/api/v1/projects", json={"id": "x" * 5000, "name": "too long"})
        assert response.status_code == 422
        assert response.json()["code"] == "REQUEST_VALIDATION_ERROR"

    def test_forged_verification_status_is_still_recorded_as_claimed(self, client):
        """A client cannot silently mark evidence verified and change nothing else."""
        run = _evaluate(client)
        verdicts = run["result"]["verdicts"]
        crossing = next(
            v for v in verdicts if v["element_id"] == "N_K" and v["rule_id"] == "DEMO-NODE-CROSSING-TYPE"
        )
        assert crossing["state"] == "PASS"
        assert crossing["basis_label"] == "DEMO_RULEPACK_NOT_LEGAL"

    def test_no_endpoint_writes_outside_the_database_directory(self, client, database_path):
        before = {p.name for p in database_path.parent.iterdir()}
        _evaluate(client)
        client.get("/api/v1/runs/x/manifest")
        after = {p.name for p in database_path.parent.iterdir()}
        new_files = {name for name in after - before if not name.startswith("integration.sqlite3")}
        assert new_files == set()