"""Read endpoints added for the Gate 3 planning UI.

Each one is a pure read of already-stored state; no new domain behaviour is
introduced. Covered here: the routes themselves, their 404 behaviour and the
revision/run metadata the UI needs to compose an edit safely.
"""

from __future__ import annotations

import pytest
from detour_lab.api.main import create_app
from detour_lab.api.state import DEMO_PROJECT_ID, DEMO_SCENARIO_ID
from fastapi.testclient import TestClient

EVAL_INSTANT = "2026-03-01T00:00:00Z"


@pytest.fixture()
def client(tmp_path):
    with TestClient(create_app(tmp_path / "gate3-reads.sqlite3")) as test_client:
        yield test_client


class TestScenarioReads:
    def test_get_scenario_returns_the_full_payload(self, client):
        body = client.get(f"/api/v1/scenarios/{DEMO_SCENARIO_ID}").json()
        assert body["id"] == DEMO_SCENARIO_ID
        assert body["revision"] == 1
        assert body["base_graph_version_id"] == "demo-graph-v1"
        assert [p["id"] for p in body["phases"]] == ["phase-1", "phase-2"]
        assert body["phases"][0]["closed_edge_ids"] == ["E_ME"]
        assert [od["id"] for od in body["origins_destinations"]] == ["OD-W", "OD-E", "OD-GATE", "OD-LIB"]
        assert body["content_hash"].startswith("sha256:")

    def test_get_scenario_unknown_is_a_flat_404(self, client):
        response = client.get("/api/v1/scenarios/ghost")
        assert response.status_code == 404
        body = response.json()
        assert body["code"] == "NOT_FOUND"
        assert set(body) == {"code", "message", "details", "request_id"}

    def test_scenario_read_reflects_a_new_revision(self, client):
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
        body = client.get(f"/api/v1/scenarios/{DEMO_SCENARIO_ID}").json()
        assert body["revision"] == 2
        assert len(body["edits"]) == 1
        assert body["edits"][0]["target_id"] == "E_SSE"

    def test_editing_does_not_rename_the_scenario(self, client):
        """Regression: an edit must not change the scenario's identity.

        The list endpoint is what a client follows to pick a scenario; if an edit
        renamed it, the next fetch would 404.
        """
        client.patch(
            f"/api/v1/scenarios/{DEMO_SCENARIO_ID}",
            json={
                "expected_revision": 1,
                "edits": [
                    {"op": "close_edge", "target_id": "E_WM", "params": {"phases": ["phase-1"]}}
                ],
            },
        )
        listed = client.get(f"/api/v1/projects/{DEMO_PROJECT_ID}/scenarios").json()["scenarios"]
        assert [entry["id"] for entry in listed] == [DEMO_SCENARIO_ID]
        assert listed[0]["revision"] == 2

        reread = client.get(f"/api/v1/scenarios/{DEMO_SCENARIO_ID}")
        assert reread.status_code == 200
        assert reread.json()["id"] == DEMO_SCENARIO_ID


class TestProjectScenarioList:
    def test_scenarios_are_listed_for_a_project(self, client):
        body = client.get(f"/api/v1/projects/{DEMO_PROJECT_ID}/scenarios").json()
        assert body["project_id"] == DEMO_PROJECT_ID
        assert len(body["scenarios"]) == 1
        entry = body["scenarios"][0]
        assert entry["id"] == DEMO_SCENARIO_ID
        assert entry["revision"] == 1
        assert entry["phase_count"] == 2
        assert entry["content_hash"].startswith("sha256:")

    def test_unknown_project_is_a_flat_404(self, client):
        response = client.get("/api/v1/projects/ghost/scenarios")
        assert response.status_code == 404
        assert response.json()["code"] == "NOT_FOUND"

    def test_creating_a_branch_appears_in_the_list(self, client):
        parent = client.get(f"/api/v1/scenarios/{DEMO_SCENARIO_ID}").json()
        created = client.post(
            f"/api/v1/projects/{DEMO_PROJECT_ID}/scenarios",
            json={
                "id": "scn-branch-1",
                "name": "branch",
                "parent_scenario_id": DEMO_SCENARIO_ID,
                "base_graph_version_id": parent["base_graph_version_id"],
                "phases": parent["phases"],
                "origins_destinations": parent["origins_destinations"],
                "temporary_edges": parent["temporary_edges"],
            },
        )
        assert created.status_code == 201
        body = client.get(f"/api/v1/projects/{DEMO_PROJECT_ID}/scenarios").json()
        assert {s["id"] for s in body["scenarios"]} == {DEMO_SCENARIO_ID, "scn-branch-1"}

    def test_a_duplicate_scenario_id_is_a_409_not_a_500(self, client):
        """A taken id is a conflict the caller can act on.

        Regression: the create path inserted without checking, so a duplicate
        id reached the INSERT and escaped as an uncaught ``sqlite3.IntegrityError``
        - a 500 with no error code. The apply-to-branch path already returned
        409 ``SCENARIO_ID_EXISTS``; creation now behaves the same way.
        """
        parent = client.get(f"/api/v1/scenarios/{DEMO_SCENARIO_ID}").json()
        payload = {
            "id": "scn-branch-dup",
            "name": "branch",
            "parent_scenario_id": DEMO_SCENARIO_ID,
            "base_graph_version_id": parent["base_graph_version_id"],
            "phases": parent["phases"],
            "origins_destinations": parent["origins_destinations"],
            "temporary_edges": parent["temporary_edges"],
        }
        first = client.post(f"/api/v1/projects/{DEMO_PROJECT_ID}/scenarios", json=payload)
        assert first.status_code == 201
        before = client.get("/api/v1/scenarios/scn-branch-dup").json()

        second = client.post(f"/api/v1/projects/{DEMO_PROJECT_ID}/scenarios", json=payload)
        assert second.status_code == 409
        body = second.json()
        assert body["code"] == "SCENARIO_ID_EXISTS"
        assert set(body) == {"code", "message", "details", "request_id"}
        assert body["details"]["scenario_id"] == "scn-branch-dup"

        # The refusal wrote nothing: the stored scenario is untouched and no
        # extra revision appeared.
        after = client.get("/api/v1/scenarios/scn-branch-dup").json()
        assert after["revision"] == before["revision"]
        assert after["content_hash"] == before["content_hash"]
        listed = client.get(f"/api/v1/projects/{DEMO_PROJECT_ID}/scenarios").json()
        assert {s["id"] for s in listed["scenarios"]} == {DEMO_SCENARIO_ID, "scn-branch-dup"}


class TestRunList:
    def test_no_runs_initially(self, client):
        body = client.get(f"/api/v1/scenarios/{DEMO_SCENARIO_ID}/runs").json()
        assert body["runs"] == []

    def test_runs_are_listed_newest_first_with_revision_and_hashes(self, client):
        first = client.post(
            f"/api/v1/scenarios/{DEMO_SCENARIO_ID}/evaluate",
            json={"phase_id": "phase-1", "evaluation_instant": EVAL_INSTANT},
        ).json()
        client.post(
            f"/api/v1/scenarios/{DEMO_SCENARIO_ID}/evaluate",
            json={"phase_id": "phase-2", "evaluation_instant": EVAL_INSTANT},
        )
        body = client.get(f"/api/v1/scenarios/{DEMO_SCENARIO_ID}/runs").json()
        assert len(body["runs"]) == 2
        assert body["runs"][0]["phase_id"] == "phase-2"  # newest first
        assert {r["id"] for r in body["runs"]} >= {first["run"]["id"]}
        assert all(r["semantic_hash"].startswith("sha256:") for r in body["runs"])
        assert all(r["input_hash"].startswith("sha256:") for r in body["runs"])

    def test_equivalent_runs_share_a_semantic_hash(self, client):
        client.post(
            f"/api/v1/scenarios/{DEMO_SCENARIO_ID}/evaluate",
            json={"phase_id": "phase-1", "evaluation_instant": EVAL_INSTANT},
        )
        client.post(
            f"/api/v1/scenarios/{DEMO_SCENARIO_ID}/evaluate",
            json={"phase_id": "phase-1", "evaluation_instant": EVAL_INSTANT},
        )
        runs = client.get(f"/api/v1/scenarios/{DEMO_SCENARIO_ID}/runs").json()["runs"]
        assert len({r["id"] for r in runs}) == 2
        assert len({r["semantic_hash"] for r in runs}) == 1

    def test_unknown_scenario_is_a_404(self, client):
        assert client.get("/api/v1/scenarios/ghost/runs").status_code == 404


def test_openapi_documents_the_new_read_routes(client):
    paths = client.get("/openapi.json").json()["paths"]
    for route in (
        "/api/v1/scenarios/{scenario_id}",
        "/api/v1/scenarios/{scenario_id}/runs",
        "/api/v1/projects/{project_id}/scenarios",
    ):
        assert route in paths, route