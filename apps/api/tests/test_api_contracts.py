"""HTTP contract tests (real ASGI transport, no mocks)."""

from __future__ import annotations

import pytest
from detour_lab.api.main import app
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_health_reports_provenance_and_disclaimer(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["rulepack_id"] == "DEMO_RULEPACK_NOT_LEGAL"
    assert body["rulepack_hash"].startswith("sha256:")
    assert body["synthetic_data"] is True
    assert body["legal_applicability"] == "unverified"
    assert "not legal compliance" in body["disclaimer"].lower()
    assert body["engine_version"].startswith("detour-lab-engine/")


def test_openapi_is_generated(client):
    schema = client.get("/openapi.json").json()
    assert "/api/v1/health" in schema["paths"]
    assert "/api/v1/projects" in schema["paths"]


def test_seeded_project_is_listed_with_counts(client):
    body = client.get("/api/v1/projects").json()
    project = body["projects"][0]
    assert "SYNTHETIC" in project["name"].upper()
    assert project["node_count"] == 9
    assert project["edge_count"] == 12
    assert project["evidence_count"] == 37
    assert project["graph_content_hash"].startswith("sha256:")
    assert "SYNTHETIC" in project["notice"].upper()


def test_graph_endpoint_returns_topology_and_provenance(client):
    body = client.get("/api/v1/projects/demo-project-synthetic/graph").json()
    assert body["basis"]["kind"] == "local_planar_meters"
    assert body["basis"]["local_origin_label"]
    node_ids = {n["id"] for n in body["nodes"]}
    for e in body["edges"]:
        assert e["u"] in node_ids and e["v"] in node_ids
    unlinked = [c for c in body["unlinked_crossings"] if not c["connected_via_shared_node"]]
    assert unlinked, "the topology QA view must show the unlinked crossing"


def test_unknown_project_returns_a_structured_404(client):
    response = client.get("/api/v1/projects/nope/graph")
    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "PROJECT_NOT_FOUND"
    assert set(body) == {"code", "message", "details", "request_id"}


def test_unknown_profile_returns_a_structured_404(client):
    response = client.post("/api/v1/scenarios/demo/evaluate", json={"profile_id": "GHOST", "phase_id": "phase-1"})
    assert response.status_code == 404
    assert response.json()["code"] == "PROFILE_NOT_FOUND"


def test_evaluation_is_deterministic_across_http_calls(client):
    body = {"profile_id": "DEMO_PROFILE_MANUAL_WHEELCHAIR", "phase_id": "phase-1"}
    first = client.post("/api/v1/scenarios/demo/evaluate", json=body).json()
    second = client.post("/api/v1/scenarios/demo/evaluate", json=body).json()
    first.pop("engine_version")
    second.pop("engine_version")
    assert first == second


def test_the_two_profiles_differ_over_http(client):
    a = client.post(
        "/api/v1/scenarios/demo/evaluate",
        json={"profile_id": "DEMO_PROFILE_MANUAL_WHEELCHAIR", "phase_id": "phase-1"},
    ).json()
    b = client.post(
        "/api/v1/scenarios/demo/evaluate",
        json={"profile_id": "DEMO_PROFILE_LIMITED_MOBILITY_WALKER", "phase_id": "phase-1"},
    ).json()
    assert [od["confirmed_reachable"] for od in a["od_results"]] != [od["confirmed_reachable"] for od in b["od_results"]]
    assert a["profile_id"] != b["profile_id"]


def test_phase_transition_changes_the_computed_result(client):
    one = client.post(
        "/api/v1/scenarios/demo/evaluate",
        json={"profile_id": "DEMO_PROFILE_MANUAL_WHEELCHAIR", "phase_id": "phase-1"},
    ).json()
    two = client.post(
        "/api/v1/scenarios/demo/evaluate",
        json={"profile_id": "DEMO_PROFILE_MANUAL_WHEELCHAIR", "phase_id": "phase-2"},
    ).json()
    assert one["phase_id"] != two["phase_id"]
    assert one["phase_graph_hash"] != two["phase_graph_hash"]
    two_edge_states = {e["edge_id"]: e["state"] for e in two["edge_evaluations"]}
    assert "TMP::TMP-EAST-BYPASS" in two_edge_states


def test_ruleset_endpoint_marks_the_pack_as_not_legal(client):
    body = client.get("/api/v1/rulesets").json()
    pack = body["rulepacks"][0]
    assert pack["legal_applicability"] == "unverified"
    assert all(rule["basis_label"] == "DEMO_RULEPACK_NOT_LEGAL" for rule in pack["rules"])
    assert all(profile["is_demo_profile"] for profile in body["profiles"])


def test_malformed_request_body_is_rejected(client):
    response = client.post("/api/v1/scenarios/demo/evaluate", json={"phase_id": 17})
    assert response.status_code == 422