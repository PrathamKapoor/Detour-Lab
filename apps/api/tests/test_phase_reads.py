"""Gate 4 phase reads: timeline ordering and the materialised phase graph.

The behaviours asserted here are the ones Gate 4 depends on and that Gate 0-3
never covered:

* ``Phase.order`` is the ordering authority (never id, label or array index);
* a phase graph is served by the backend so no client reconstructs closures;
* equivalent phase states share a hash, different ones do not;
* an unanalysed phase reports NOT_ANALYSED, which is not a verdict;
* an unknown phase id is rejected rather than treated as "no closures".
"""

from __future__ import annotations

import pytest
from detour_lab.api.main import create_app
from fastapi.testclient import TestClient

DEMO_SCENARIO = "scn-demo-baseline"
DEMO_PROJECT = "demo-project-synthetic"
INSTANT = "2026-03-01T00:00:00Z"


@pytest.fixture()
def client(tmp_path):
    with TestClient(create_app(tmp_path / "gate4-phases.sqlite3")) as test_client:
        yield test_client


def _run(client, phase_id, profile="DEMO_PROFILE_MANUAL_WHEELCHAIR"):
    return client.post(
        f"/api/v1/scenarios/{DEMO_SCENARIO}/evaluate",
        json={"profile_id": profile, "phase_id": phase_id, "evaluation_instant": INSTANT},
    )


class TestTimelineOrdering:
    def test_phases_are_returned_in_phase_order(self, client):
        body = client.get(f"/api/v1/scenarios/{DEMO_SCENARIO}/timeline").json()
        assert body["ordering"] == "phase_order"
        orders = [phase["order"] for phase in body["phases"]]
        assert orders == sorted(orders)
        assert [phase["phase_id"] for phase in body["phases"]] == ["phase-1", "phase-2"]

    def test_timeline_reports_declared_modifications_and_identities(self, client):
        phases = {
            p["phase_id"]: p
            for p in client.get(f"/api/v1/scenarios/{DEMO_SCENARIO}/timeline").json()["phases"]
        }
        assert phases["phase-1"]["closed_edge_ids"] == ["E_ME"]
        assert phases["phase-1"]["temporary_edge_ids"] == []
        assert phases["phase-2"]["closed_edge_ids"] == ["E_ES1", "E_ME"]
        assert phases["phase-2"]["temporary_edge_ids"] == ["TMP-EAST-BYPASS"]
        assert all(p["phase_graph_hash"].startswith("sha256:") for p in phases.values())
        assert phases["phase-1"]["boundary_convention"] == "logical_ordinal"

    def test_different_phase_states_have_different_graph_hashes(self, client):
        phases = client.get(f"/api/v1/scenarios/{DEMO_SCENARIO}/timeline").json()["phases"]
        hashes = {phase["phase_graph_hash"] for phase in phases}
        assert len(hashes) == len(phases), "distinct phase states must not share a graph hash"

    def test_non_contiguous_and_reordered_phases_sort_by_order_not_id(self, client):
        """Ordering must not fall back to ids, labels or array position."""
        from detour_lab.domain.contracts import Scenario

        scenario = Scenario.model_validate(client.get(f"/api/v1/scenarios/{DEMO_SCENARIO}").json())
        base = scenario.phases[0]
        third = base.model_copy(update={"id": "phase-0", "order": 0, "label": "Phase 0 - earlier work"})
        # Declared in a deliberately misleading order: array position says otherwise.
        declared = Scenario.model_validate(
            {**scenario.model_dump(mode="json"), "phases": [scenario.phases[1], third, base]}
        )
        ordered = [phase.id for phase in declared.ordered_phases()]
        assert ordered == ["phase-0", "phase-1", "phase-2"]

    def test_duplicate_phase_order_is_rejected_by_the_domain(self):
        from detour_lab.domain.contracts import Scenario
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="phase orders must be unique"):
            Scenario.model_validate(
                {
                    "id": "scn-x",
                    "base_graph_version_id": "g",
                    "rulepack_id": "r",
                    "rulepack_hash": "h",
                    "profile_ids": ["p"],
                    "phases": [
                        {"id": "a", "order": 1},
                        {"id": "b", "order": 1},
                    ],
                }
            )

    def test_unknown_scenario_timeline_is_a_flat_404(self, client):
        response = client.get("/api/v1/scenarios/ghost/timeline")
        assert response.status_code == 404
        assert response.json()["code"] == "NOT_FOUND"


class TestAnalysisState:
    def test_fresh_scenario_reports_not_analysed(self, client):
        phases = client.get(f"/api/v1/scenarios/{DEMO_SCENARIO}/timeline").json()["phases"]
        assert all(phase["analysis"]["state"] == "NOT_ANALYSED" for phase in phases)
        assert all(phase["analysis"]["analysed"] is False for phase in phases)

    def test_not_analysed_is_not_a_verdict(self, client):
        state = client.get(f"/api/v1/scenarios/{DEMO_SCENARIO}/timeline").json()["phases"][0]["analysis"]
        # NOT_ANALYSED is about evidence of a result, not about accessibility.
        assert state["state"] not in {"PASS", "FAIL", "UNKNOWN", "NOT_APPLICABLE"}
        assert state["semantic_hash"] is None
        assert state["run_id"] is None

    def test_running_a_phase_marks_only_that_phase(self, client):
        _run(client, "phase-1")
        phases = {
            p["phase_id"]: p["analysis"]
            for p in client.get(f"/api/v1/scenarios/{DEMO_SCENARIO}/timeline").json()["phases"]
        }
        assert phases["phase-1"]["state"] == "analysed"
        assert phases["phase-1"]["semantic_hash"].startswith("sha256:")
        assert phases["phase-2"]["state"] == "NOT_ANALYSED"

    def test_history_for_an_old_revision_is_marked_stale_not_current(self, client):
        _run(client, "phase-1")
        client.patch(
            f"/api/v1/scenarios/{DEMO_SCENARIO}",
            json={
                "expected_revision": 1,
                "edits": [
                    {
                        "op": "update_attribute",
                        "target_id": "E_SSE",
                        "params": {
                            "field": "surface",
                            "value": "asphalt",
                            "unit": None,
                            "method": "manual_entry",
                            "source": "gate 4 test",
                            "provenance_class": "assumed",
                            "synthetic": False,
                            "observed_at": "2026-02-01T10:00:00Z",
                        },
                    }
                ],
            },
        )
        analysis = client.get(f"/api/v1/scenarios/{DEMO_SCENARIO}/timeline").json()["phases"][0]["analysis"]
        assert analysis["state"] == "NOT_ANALYSED"
        assert analysis["stale"] is True
        assert analysis["historical_run_count"] >= 1


class TestPhaseGraph:
    def test_phase_graph_reports_authoritative_closures_and_temporaries(self, client):
        body = client.get(f"/api/v1/scenarios/{DEMO_SCENARIO}/phases/phase-2/graph").json()
        assert body["phase_id"] == "phase-2"
        assert body["phase_order"] == 2
        assert body["closed_edge_ids"] == ["E_ES1", "E_ME"]
        assert body["active_temporary_edge_ids"] == ["TMP-EAST-BYPASS"]
        closed = {edge["id"] for edge in body["edges"] if edge["closed"]}
        assert closed == {"E_ES1", "E_ME"}
        # The materialised temporary edge is namespaced and flagged as temporary.
        temporary = {edge["id"] for edge in body["edges"] if edge["temporary"]}
        assert len(temporary) == 1
        assert next(iter(temporary)).startswith("TMP::")

    def test_a_closed_edge_is_still_present_but_marked_inactive(self, client):
        """Visibility must never imply traversability."""
        edges = client.get(f"/api/v1/scenarios/{DEMO_SCENARIO}/phases/phase-2/graph").json()["edges"]
        closed = next(edge for edge in edges if edge["id"] == "E_ES1")
        assert closed["closed"] is True
        assert closed["inactive"] is True
        assert closed["length_m"] > 0

    def test_phase_one_has_no_temporary_edge(self, client):
        body = client.get(f"/api/v1/scenarios/{DEMO_SCENARIO}/phases/phase-1/graph").json()
        assert body["active_temporary_edge_ids"] == []
        assert [edge for edge in body["edges"] if edge["temporary"]] == []

    def test_phase_graphs_differ_between_phases(self, client):
        one = client.get(f"/api/v1/scenarios/{DEMO_SCENARIO}/phases/phase-1/graph").json()
        two = client.get(f"/api/v1/scenarios/{DEMO_SCENARIO}/phases/phase-2/graph").json()
        assert one["phase_graph_hash"] != two["phase_graph_hash"]
        assert one["phase_graph_id"] != two["phase_graph_id"]
        assert len(two["edges"]) == len(one["edges"]) + 1  # phase 2 materialises the bypass

    def test_equivalent_phase_state_reproduces_the_same_hash(self, client):
        first = client.get(f"/api/v1/scenarios/{DEMO_SCENARIO}/phases/phase-1/graph").json()
        second = client.get(f"/api/v1/scenarios/{DEMO_SCENARIO}/phases/phase-1/graph").json()
        assert first["phase_graph_hash"] == second["phase_graph_hash"]

    def test_crossings_are_reported_without_implying_connectivity(self, client):
        body = client.get(f"/api/v1/scenarios/{DEMO_SCENARIO}/phases/phase-1/graph").json()
        assert body["crossings"], "the seeded network has geometric crossings"
        assert any(crossing["connected_via_shared_node"] is False for crossing in body["crossings"])

    def test_unknown_phase_is_rejected_not_treated_as_empty(self, client):
        response = client.get(f"/api/v1/scenarios/{DEMO_SCENARIO}/phases/phase-99/graph")
        assert response.status_code == 422
        assert response.json()["code"] == "INVALID_INPUT"

    def test_phase_graph_belongs_to_the_scenario_revision(self, client):
        body = client.get(f"/api/v1/scenarios/{DEMO_SCENARIO}/phases/phase-1/graph").json()
        assert body["scenario_id"] == DEMO_SCENARIO
        assert body["scenario_revision"] == 1
        assert body["phase_id"] in body["phase_graph_id"]


def test_openapi_documents_the_phase_routes(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/scenarios/{scenario_id}/timeline" in paths
    assert "/api/v1/scenarios/{scenario_id}/phases/{phase_id}/graph" in paths