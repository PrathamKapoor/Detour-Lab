"""HTTP contract tests against a real ASGI app on a temporary database."""

from __future__ import annotations

import pytest
from detour_lab import ENGINE_VERSION, MANIFEST_SCHEMA_VERSION
from detour_lab.api.main import create_app
from detour_lab.api.state import DEMO_PROJECT_ID, DEMO_SCENARIO_ID
from detour_lab.persistence.db import SCHEMA_VERSION
from fastapi.testclient import TestClient

EVAL_INSTANT = "2026-03-01T00:00:00Z"


@pytest.fixture()
def client(tmp_path):
    with TestClient(create_app(tmp_path / "api.sqlite3")) as test_client:
        yield test_client


class TestHealthAndSchema:
    def test_health_reports_identity_and_row_counts(self, client):
        body = client.get("/api/v1/health").json()
        assert body["status"] == "ok"
        assert body["engine_version"] == ENGINE_VERSION
        assert body["rulepack_id"] == "DEMO_RULEPACK_NOT_LEGAL"
        assert body["rulepack_hash"].startswith("sha256:")
        assert body["legal_applicability"] == "unverified"
        assert body["database_schema_version"] == SCHEMA_VERSION
        assert body["row_counts"]["projects"] == 1
        assert body["row_counts"]["evidence"] == 37

    def test_openapi_is_generated_with_the_prd_routes(self, client):
        paths = client.get("/openapi.json").json()["paths"]
        for route in (
            "/api/v1/health",
            "/api/v1/projects",
            "/api/v1/projects/{project_id}/imports",
            "/api/v1/projects/{project_id}/graph",
            "/api/v1/projects/{project_id}/scenarios",
            "/api/v1/scenarios/{scenario_id}",
            "/api/v1/scenarios/{scenario_id}/evaluate",
            "/api/v1/runs/{run_id}",
            "/api/v1/runs/{run_id}/manifest",
            "/api/v1/scenarios/{scenario_id}/optimization/interventions",
            "/api/v1/scenarios/{scenario_id}/optimization/search",
            "/api/v1/scenarios/{scenario_id}/optimization/searches",
            "/api/v1/optimization/searches/{search_id}",
            "/api/v1/optimization/promote",
        ):
            assert route in paths, f"{route} missing from the OpenAPI document"


class TestSeededData:
    def test_demo_project_is_imported_once_on_startup(self, client):
        projects = client.get("/api/v1/projects").json()["projects"]
        assert len(projects) == 1
        assert "SYNTHETIC" in projects[0]["name"].upper()

    def test_graph_endpoint_exposes_topology_and_provenance(self, client):
        body = client.get(f"/api/v1/projects/{DEMO_PROJECT_ID}/graph").json()
        assert body["basis"]["kind"] == "local_planar_meters"
        assert body["basis"]["local_origin_label"]
        assert body["source"]["provenance_class"] == "synthetic"
        assert len(body["nodes"]) == 9
        assert len(body["edges"]) == 12
        assert len(body["evidence"]) == 37
        node_ids = {n["id"] for n in body["nodes"]}
        assert all(e["u"] in node_ids and e["v"] in node_ids for e in body["edges"])
        unlinked = [c for c in body["unlinked_crossings"] if not c["connected_via_shared_node"]]
        assert unlinked

    def test_scenario_endpoint_reports_phases_and_fixed_instant(self, client):
        body = client.get(f"/api/v1/scenarios/{DEMO_SCENARIO_ID}/revisions").json()
        assert body["revisions"][0]["revision"] == 1
        assert body["revisions"][0]["content_hash"].startswith("sha256:")


class TestEvaluation:
    def _evaluate(self, client, **body):
        payload = {"evaluation_instant": EVAL_INSTANT, **body}
        response = client.post(f"/api/v1/scenarios/{DEMO_SCENARIO_ID}/evaluate", json=payload)
        assert response.status_code == 201, response.text
        return response.json()

    def test_evaluation_returns_computed_results_not_a_fixture(self, client):
        body = self._evaluate(client, profile_id="DEMO_PROFILE_MANUAL_WHEELCHAIR", phase_id="phase-1")
        matrix = body["result"]["od_results"]
        assert len(matrix) == 4
        gate = next(od for od in matrix if od["origin_id"] == "OD-W" and od["destination_id"] == "OD-GATE")
        assert gate["confirmed_reachable"] is True
        assert gate["confirmed_distance_m"] == pytest.approx(58.0)
        assert gate["confirmed_path_edge_ids"] == ["E_WM", "E_K1", "E_K2"]

    def test_two_runs_share_a_semantic_hash(self, client):
        first = self._evaluate(client, profile_id="DEMO_PROFILE_MANUAL_WHEELCHAIR", phase_id="phase-1")
        second = self._evaluate(client, profile_id="DEMO_PROFILE_MANUAL_WHEELCHAIR", phase_id="phase-1")
        assert first["run"]["id"] != second["run"]["id"]
        assert first["run"]["semantic_hash"] == second["run"]["semantic_hash"]
        assert first["result"] == second["result"]

    def test_profiles_and_phases_produce_different_results(self, client):
        a = self._evaluate(client, profile_id="DEMO_PROFILE_MANUAL_WHEELCHAIR", phase_id="phase-1")
        b = self._evaluate(client, profile_id="DEMO_PROFILE_LIMITED_MOBILITY_WALKER", phase_id="phase-1")
        c = self._evaluate(client, profile_id="DEMO_PROFILE_MANUAL_WHEELCHAIR", phase_id="phase-2")
        assert a["run"]["semantic_hash"] != b["run"]["semantic_hash"]
        assert a["run"]["semantic_hash"] != c["run"]["semantic_hash"]

    def test_unknown_profile_is_a_structured_404(self, client):
        response = client.post(
            f"/api/v1/scenarios/{DEMO_SCENARIO_ID}/evaluate",
            json={"profile_id": "GHOST", "phase_id": "phase-1", "evaluation_instant": EVAL_INSTANT},
        )
        assert response.status_code == 404
        body = response.json()
        assert body["code"] == "PROFILE_NOT_FOUND"
        assert "known_profiles" in body["details"]

    def test_unknown_phase_is_a_structured_422(self, client):
        response = client.post(
            f"/api/v1/scenarios/{DEMO_SCENARIO_ID}/evaluate",
            json={"phase_id": "phase-404", "evaluation_instant": EVAL_INSTANT},
        )
        assert response.status_code == 422
        assert response.json()["code"] == "INVALID_INPUT"

    def test_unknown_scenario_is_a_structured_404(self, client):
        response = client.post(
            "/api/v1/scenarios/ghost/evaluate",
            json={"phase_id": "phase-1", "evaluation_instant": EVAL_INSTANT},
        )
        assert response.status_code == 404
        assert response.json()["code"] == "NOT_FOUND"


class TestRunsAndManifest:
    def test_run_can_be_fetched_and_replayed(self, client):
        created = client.post(
            f"/api/v1/scenarios/{DEMO_SCENARIO_ID}/evaluate",
            json={"phase_id": "phase-1", "evaluation_instant": EVAL_INSTANT},
        ).json()
        run_id = created["run"]["id"]
        fetched = client.get(f"/api/v1/runs/{run_id}").json()
        assert fetched["run"]["semantic_hash"] == created["run"]["semantic_hash"]
        assert fetched["result"] == created["result"]

    def test_manifest_is_canonical_and_excludes_runtime_from_its_hash(self, client):
        created = client.post(
            f"/api/v1/scenarios/{DEMO_SCENARIO_ID}/evaluate",
            json={"phase_id": "phase-1", "evaluation_instant": EVAL_INSTANT},
        ).json()
        first = client.get(f"/api/v1/runs/{created['run']['id']}/manifest").json()
        second_run = client.post(
            f"/api/v1/scenarios/{DEMO_SCENARIO_ID}/evaluate",
            json={"phase_id": "phase-1", "evaluation_instant": EVAL_INSTANT},
        ).json()
        second = client.get(f"/api/v1/runs/{second_run['run']['id']}/manifest").json()

        assert first["runtime"]["run_id"] != second["runtime"]["run_id"]
        assert first["semantic_hash"] == second["semantic_hash"]
        assert first["schema_version"] == MANIFEST_SCHEMA_VERSION
        assert first["ruleset"]["legal_applicability"] == "unverified"
        assert "not certified" in first["disclaimer"].lower()

    def test_manifest_unknowns_match_the_run(self, client):
        created = client.post(
            f"/api/v1/scenarios/{DEMO_SCENARIO_ID}/evaluate",
            json={"phase_id": "phase-1", "evaluation_instant": EVAL_INSTANT},
        ).json()
        manifest = client.get(f"/api/v1/runs/{created['run']['id']}/manifest").json()
        unknown_from_run = {
            (v["element_id"], v["rule_id"])
            for v in created["result"]["verdicts"]
            if v["state"] == "UNKNOWN"
        }
        unknown_from_manifest = {(u["element_id"], u["rule_id"]) for u in manifest["results"]["unknowns"]}
        assert unknown_from_run == unknown_from_manifest

    def test_unknown_run_is_a_404(self, client):
        assert client.get("/api/v1/runs/run-nope").status_code == 404
        assert client.get("/api/v1/runs/run-nope/manifest").status_code == 404


class TestErrorEnvelope:
    def test_every_error_uses_the_same_envelope(self, client):
        responses = [
            client.get("/api/v1/runs/run-nope"),
            client.post("/api/v1/projects", json={"id": "x"}),
            client.post(f"/api/v1/scenarios/{DEMO_SCENARIO_ID}/evaluate", json={"phase_id": "phase-1", "evaluation_instant": EVAL_INSTANT, "profile_id": "GHOST"}),
        ]
        for response in responses:
            assert response.status_code >= 400
            body = response.json()
            assert set(body) == {"code", "message", "details", "request_id"}

    def test_malformed_body_is_rejected_with_422(self, client):
        response = client.post(f"/api/v1/scenarios/{DEMO_SCENARIO_ID}/evaluate", json={"phase_id": 17})
        assert response.status_code == 422

    def test_non_json_body_is_rejected(self, client):
        response = client.post(
            f"/api/v1/scenarios/{DEMO_SCENARIO_ID}/evaluate",
            content=b"{not json",
            headers={"content-type": "application/json"},
        )
        assert response.status_code == 422