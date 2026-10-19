"""Gate 5 HTTP contract tests: the Fix This Plan endpoints against a real app.

The app runs on a temporary database with the seeded synthetic demo project.
Nothing is mocked: searches go through the real engine and promotions through
the real transaction.
"""

from __future__ import annotations

import pytest
from detour_lab.api.main import create_app
from detour_lab.api.state import DEMO_PROJECT_ID, DEMO_SCENARIO_ID
from detour_lab.domain.contracts import GraphEdit, Scenario
from fastapi.testclient import TestClient

EVAL = "2026-03-01T00:00:00Z"
INTERVENTIONS_PATH = f"/api/v1/scenarios/{DEMO_SCENARIO_ID}/optimization/interventions"
SEARCH_PATH = f"/api/v1/scenarios/{DEMO_SCENARIO_ID}/optimization/search"
SEARCHES_PATH = f"/api/v1/scenarios/{DEMO_SCENARIO_ID}/optimization/searches"
PROMOTE_PATH = "/api/v1/optimization/promote"

E_LIB = "OD-E->OD-LIB"
W_LIB = "OD-W->OD-LIB"

DEFAULT_CONFIG = {"max_interventions": 2, "max_candidates": 60, "max_duration_ms": 120_000}


@pytest.fixture()
def api(tmp_path):
    app = create_app(tmp_path / "api.sqlite3")
    with TestClient(app) as client:
        yield client, app.state.repository


def _run_search(client: TestClient, **overrides: object) -> dict:
    payload: dict = {"phase_id": "phase-1", "evaluation_instant": EVAL, "config": dict(DEFAULT_CONFIG)}
    payload.update(overrides)
    response = client.post(SEARCH_PATH, json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def _candidate(body: dict, intervention_ids: list[str]) -> dict:
    for candidate in body["candidates"]:
        if candidate["intervention_ids"] == sorted(intervention_ids):
            return candidate
    raise AssertionError(f"candidate {intervention_ids} not present in search result")


class TestInterventionsEndpoint:
    def test_lists_library_with_eligibility_reasons_and_cost_discipline(self, api):
        client, _ = api
        response = client.get(INTERVENTIONS_PATH, params={"phase_id": "phase-1"})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["library"]["id"] == "DEMO_INTERVENTIONS_NOT_ENGINEERED"
        assert "synthetic" in body["library"]["notice"].lower()
        assert body["scenario_revision"] == 1
        assert body["phase_id"] == "phase-1"
        assert body["declared_phases"] == ["phase-1", "phase-2"]

        entries = {item["id"]: item for item in body["interventions"]}
        assert len(entries) == 5
        assert entries["INT-MODEL-CURB-N_EK"]["applicable"] is True
        reopen = entries["INT-REOPEN-E_ES1-P2"]
        assert reopen["applicable"] is False
        assert any("phase" in reason for reason in reopen["eligibility_reasons"])
        assert set(body["eligible_intervention_ids"]) == {
            "INT-BYPASS-IN-PHASE-1",
            "INT-MODEL-CURB-N_EK",
            "INT-REMEASURE-ALT-TRACK",
            "INT-TEMP-BACKLANE-TRACK",
        }

        # Unknown cost is carried as unknown, never substituted with zero.
        backlane_cost = entries["INT-TEMP-BACKLANE-TRACK"]["costs"][0]
        assert backlane_cost["unit_price_nominal"] is None
        assert backlane_cost["unit_price_max"] is None
        curb_cost = entries["INT-MODEL-CURB-N_EK"]["costs"][0]
        assert curb_cost["unit_price_nominal"] == 18000.0

    def test_defaults_to_first_declared_phase(self, api):
        client, _ = api
        body = client.get(INTERVENTIONS_PATH).json()
        assert body["phase_id"] == "phase-1"

    def test_unknown_phase_is_400_with_declared_phases(self, api):
        client, _ = api
        response = client.get(INTERVENTIONS_PATH, params={"phase_id": "ghost"})
        assert response.status_code == 400
        body = response.json()
        assert body["code"] == "INVALID_INPUT"
        assert body["details"]["declared_phases"] == ["phase-1", "phase-2"]

    def test_unknown_scenario_is_404(self, api):
        client, _ = api
        response = client.get("/api/v1/scenarios/scn-ghost/optimization/interventions")
        assert response.status_code == 404


class TestSearchEndpoint:
    def test_search_persists_and_replays_identically(self, api):
        client, _ = api
        first = _run_search(client)
        assert first["search_id"].startswith("opt-")
        assert first["status"]["solver_status"] == "OPTIMAL_IN_ENUMERATED_DOMAIN"
        assert first["semantic_hash"]

        replay = client.get(f"/api/v1/optimization/searches/{first['search_id']}")
        assert replay.status_code == 200
        assert replay.json() == first, "the stored payload must be served byte-for-byte"

        listing = client.get(SEARCHES_PATH).json()
        assert listing["scenario_id"] == DEMO_SCENARIO_ID
        assert len(listing["searches"]) == 1
        summary = listing["searches"][0]
        assert summary["search_id"] == first["search_id"]
        assert summary["scenario_revision"] == 1
        assert summary["phase_id"] == "phase-1"
        assert summary["solver_status"] == "OPTIMAL_IN_ENUMERATED_DOMAIN"
        assert summary["candidate_count"] == len(first["candidates"])
        assert summary["semantic_hash"] == first["semantic_hash"]

        second = _run_search(client)
        assert second["search_id"] != first["search_id"]
        assert second["semantic_hash"] == first["semantic_hash"]
        assert len(client.get(SEARCHES_PATH).json()["searches"]) == 2

    def test_unknown_search_id_is_404(self, api):
        client, _ = api
        response = client.get("/api/v1/optimization/searches/opt-doesnotexist")
        assert response.status_code == 404

    def test_request_validation_uses_the_flat_envelope(self, api):
        client, _ = api
        response = client.post(SEARCH_PATH, json={"config": DEFAULT_CONFIG})
        assert response.status_code == 422
        body = response.json()
        assert body["code"] == "REQUEST_VALIDATION_ERROR"
        assert any("phase_id" in field["location"] for field in body["details"]["fields"])

        too_many = client.post(
            SEARCH_PATH,
            json={"phase_id": "phase-1", "config": {**DEFAULT_CONFIG, "max_interventions": 99}},
        )
        assert too_many.status_code == 422

    def test_domain_validation_errors_are_400_with_details(self, api):
        client, _ = api
        bad_instant = client.post(
            SEARCH_PATH, json={"phase_id": "phase-1", "evaluation_instant": "yesterday"}
        )
        assert bad_instant.status_code == 400
        assert bad_instant.json()["code"] == "INVALID_INPUT"

        naive = client.post(
            SEARCH_PATH, json={"phase_id": "phase-1", "evaluation_instant": "2026-03-01T00:00:00"}
        )
        assert naive.status_code == 400
        assert "timezone" in naive.json()["message"]

        ghost_phase = client.post(SEARCH_PATH, json={"phase_id": "ghost", "evaluation_instant": EVAL})
        assert ghost_phase.status_code == 400
        assert ghost_phase.json()["details"]["declared_phases"] == ["phase-1", "phase-2"]

        ghost_profile = client.post(
            SEARCH_PATH,
            json={"phase_id": "phase-1", "evaluation_instant": EVAL, "profile_ids": ["GHOST"]},
        )
        assert ghost_profile.status_code == 400

        unknown_scenario = client.post(
            "/api/v1/scenarios/scn-ghost/optimization/search",
            json={"phase_id": "phase-1", "evaluation_instant": EVAL},
        )
        assert unknown_scenario.status_code == 404

        bad_currency = client.post(
            SEARCH_PATH,
            json={
                "phase_id": "phase-1",
                "evaluation_instant": EVAL,
                "config": {**DEFAULT_CONFIG, "budget": {"amount": 1000, "currency": "USD"}},
            },
        )
        assert bad_currency.status_code == 400
        assert bad_currency.json()["code"] == "INVALID_BUDGET_CURRENCY"

    def test_zero_budget_rejects_every_candidate_and_says_why(self, api):
        client, _ = api
        body = _run_search(
            client,
            config={**DEFAULT_CONFIG, "budget": {"amount": 0, "currency": "INR", "basis": "nominal"}},
        )
        assert body["status"]["solver_status"] == "NO_FEASIBLE_IN_ENUMERATED_DOMAIN"
        assert body["candidates"], "candidates are still evaluated and reported"
        curb = _candidate(body, ["INT-MODEL-CURB-N_EK"])
        assert curb["classification"] == "rejected"
        assert any("budget" in reason for reason in curb["proposal"]["rejection_reasons"])
        assert body["config"]["budget"]["amount"] == 0


class TestPromoteEndpoint:
    def test_happy_path_reverifies_and_never_touches_the_source(self, api):
        client, repository = api
        search = _run_search(client)
        curb = _candidate(search, ["INT-MODEL-CURB-N_EK"])
        assert curb["classification"] == "certified"

        response = client.post(
            PROMOTE_PATH,
            json={
                "search_id": search["search_id"],
                "proposal_id": curb["proposal"]["proposal_id"],
                "new_scenario_id": "scn-demo-curb-fix",
                "new_scenario_name": "Demo fix: flush crossing transition",
                "expected_source_revision": 1,
            },
        )
        assert response.status_code == 201, response.text
        body = response.json()

        assert body["source"]["scenario_id"] == DEMO_SCENARIO_ID
        assert body["source"]["revision"] == 1
        assert body["source"]["unchanged"] is True
        assert body["branch"]["scenario_id"] == "scn-demo-curb-fix"
        assert body["branch"]["parent_scenario_id"] == DEMO_SCENARIO_ID
        assert body["branch"]["revision"] == 1
        assert body["branch"]["content_hash"] == curb["preview_scenario_hash"], (
            "the persisted branch must reproduce the previewed content hash"
        )
        assert body["branch"]["intervention_ids"] == ["INT-MODEL-CURB-N_EK"]
        assert body["verification"]["content_hash_match"] is True
        assert body["verification"]["all_match"] is True
        for row in body["verification"]["per_profile"]:
            assert row["match"] is True
            assert row["preview_semantic_hash"] == row["persisted_semantic_hash"]
        assert body["od_summary"]["restored_all_profiles"] == [E_LIB, W_LIB]
        assert body["classification"] == "certified"
        assert any("not field-verified" in line for line in body["disclaimers"])
        assert any("single-phase" in line for line in body["disclaimers"])

        # The branch exists and the source is byte-identical.
        branch = client.get("/api/v1/scenarios/scn-demo-curb-fix")
        assert branch.status_code == 200
        source = client.get(f"/api/v1/scenarios/{DEMO_SCENARIO_ID}").json()
        assert source["revision"] == 1

        # Re-running the search suggestion on the branch flags the already
        # modelled intervention instead of suggesting it again.
        branch_interventions = client.get(
            "/api/v1/scenarios/scn-demo-curb-fix/optimization/interventions",
            params={"phase_id": "phase-1"},
        ).json()
        entries = {item["id"]: item for item in branch_interventions["interventions"]}
        assert entries["INT-MODEL-CURB-N_EK"]["applicable"] is False
        assert any(
            "known=True" in reason for reason in entries["INT-MODEL-CURB-N_EK"]["eligibility_reasons"]
        )
        assert repository.get_scenario("scn-demo-curb-fix").revision == 1

    def test_requires_verification_candidate_is_promotable_and_labelled(self, api):
        client, _ = api
        search = _run_search(client)
        backlane = _candidate(search, ["INT-TEMP-BACKLANE-TRACK"])
        assert backlane["classification"] == "requires_verification"
        response = client.post(
            PROMOTE_PATH,
            json={
                "search_id": search["search_id"],
                "proposal_id": backlane["proposal"]["proposal_id"],
                "new_scenario_id": "scn-demo-backlane",
                "new_scenario_name": "Demo fix: back lane (width unmeasured)",
                "expected_source_revision": 1,
            },
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["classification"] == "requires_verification"
        assert body["branch"]["content_hash"] == backlane["preview_scenario_hash"]

    def test_stale_expected_revision_writes_nothing(self, api):
        client, _ = api
        search = _run_search(client)
        curb = _candidate(search, ["INT-MODEL-CURB-N_EK"])
        response = client.post(
            PROMOTE_PATH,
            json={
                "search_id": search["search_id"],
                "proposal_id": curb["proposal"]["proposal_id"],
                "new_scenario_id": "scn-stale",
                "new_scenario_name": "Stale attempt",
                "expected_source_revision": 2,
            },
        )
        assert response.status_code == 409
        assert response.json()["code"] == "STALE_REVISION"
        assert client.get("/api/v1/scenarios/scn-stale").status_code == 404

    def test_duplicate_branch_id_is_409_and_writes_nothing(self, api):
        client, _ = api
        search = _run_search(client)
        curb = _candidate(search, ["INT-MODEL-CURB-N_EK"])
        payload = {
            "search_id": search["search_id"],
            "proposal_id": curb["proposal"]["proposal_id"],
            "new_scenario_id": "scn-taken",
            "new_scenario_name": "First",
            "expected_source_revision": 1,
        }
        assert client.post(PROMOTE_PATH, json=payload).status_code == 201
        second = client.post(PROMOTE_PATH, json={**payload, "new_scenario_name": "Second"})
        assert second.status_code == 409
        assert second.json()["code"] == "SCENARIO_ID_EXISTS"
        assert client.get("/api/v1/scenarios/scn-taken").json()["name"] == "First"

    def test_rejected_candidate_is_409_with_reasons(self, api):
        client, _ = api
        search = _run_search(client)
        bypass = _candidate(search, ["INT-BYPASS-IN-PHASE-1"])
        assert bypass["classification"] == "rejected"
        response = client.post(
            PROMOTE_PATH,
            json={
                "search_id": search["search_id"],
                "proposal_id": bypass["proposal"]["proposal_id"],
                "new_scenario_id": "scn-should-not-exist",
                "new_scenario_name": "Rejected attempt",
                "expected_source_revision": 1,
            },
        )
        assert response.status_code == 409
        body = response.json()
        assert body["code"] == "CANDIDATE_REJECTED"
        assert body["details"]["rejection_reasons"]
        assert client.get("/api/v1/scenarios/scn-should-not-exist").status_code == 404

    def test_unknown_search_and_proposal_are_404(self, api):
        client, _ = api
        search = _run_search(client)
        missing_search = client.post(
            PROMOTE_PATH,
            json={
                "search_id": "opt-missing",
                "proposal_id": "cand-x",
                "new_scenario_id": "scn-x",
                "new_scenario_name": "X",
                "expected_source_revision": 1,
            },
        )
        assert missing_search.status_code == 404
        assert missing_search.json()["code"] == "SEARCH_NOT_FOUND"

        missing_proposal = client.post(
            PROMOTE_PATH,
            json={
                "search_id": search["search_id"],
                "proposal_id": "cand-missing",
                "new_scenario_id": "scn-x",
                "new_scenario_name": "X",
                "expected_source_revision": 1,
            },
        )
        assert missing_proposal.status_code == 404
        assert missing_proposal.json()["code"] == "PROPOSAL_NOT_FOUND"

    def test_branch_id_equal_to_source_is_400(self, api):
        client, _ = api
        search = _run_search(client)
        curb = _candidate(search, ["INT-MODEL-CURB-N_EK"])
        response = client.post(
            PROMOTE_PATH,
            json={
                "search_id": search["search_id"],
                "proposal_id": curb["proposal"]["proposal_id"],
                "new_scenario_id": DEMO_SCENARIO_ID,
                "new_scenario_name": "Overwrite attempt",
                "expected_source_revision": 1,
            },
        )
        assert response.status_code == 400
        assert response.json()["code"] == "INVALID_INPUT"

    def test_edit_to_the_source_after_the_search_is_stale(self, api):
        client, repository = api
        search = _run_search(client)
        curb = _candidate(search, ["INT-MODEL-CURB-N_EK"])
        repository.apply_scenario_edit(
            scenario_id=DEMO_SCENARIO_ID,
            expected_revision=1,
            edit=GraphEdit(
                op="update_attribute",
                target_id="E_ES2",
                params={
                    "field": "slope_percent",
                    "value": 1.0,
                    "unit": "%",
                    "method": "test_fixture",
                    "source": "test",
                    "provenance_class": "assumed",
                    "synthetic": True,
                },
                reason="test: move the source past the search",
            ),
            note="test edit",
        )
        response = client.post(
            PROMOTE_PATH,
            json={
                "search_id": search["search_id"],
                "proposal_id": curb["proposal"]["proposal_id"],
                "new_scenario_id": "scn-after-edit",
                "new_scenario_name": "Stale search",
                "expected_source_revision": 2,
            },
        )
        assert response.status_code == 409
        assert response.json()["code"] == "STALE_SEARCH"
        assert client.get("/api/v1/scenarios/scn-after-edit").status_code == 404


class TestPromotionPreservesSourcePlan:
    """D-025: promotion clones the source's *declared plan and edits*, then appends."""

    def test_source_edits_phases_and_declarations_survive_promotion(self, api):
        client, repository = api
        demo = repository.get_scenario(DEMO_SCENARIO_ID)
        payload = demo.model_dump(mode="json")
        payload.update(
            {
                "id": "scn-edit-source",
                "name": "Source with its own edit",
                "revision": 1,
                "parent_scenario_id": demo.id,
                "content_hash": "",
            }
        )
        source = repository.create_scenario(Scenario.model_validate(payload), project_id=DEMO_PROJECT_ID)
        repository.apply_scenario_edit(
            scenario_id=source.id,
            expected_revision=1,
            edit=GraphEdit(
                op="update_attribute",
                target_id="E_ES2",
                params={
                    "field": "slope_percent",
                    "value": 1.0,
                    "unit": "%",
                    "method": "test_fixture",
                    "source": "test",
                    "provenance_class": "assumed",
                    "synthetic": True,
                },
                reason="source-owned edit that must survive promotion",
            ),
            note="source-owned",
        )
        source = repository.get_scenario(source.id)
        assert source.revision == 2 and len(source.edits) == 1

        search_response = client.post(
            f"/api/v1/scenarios/{source.id}/optimization/search",
            json={"phase_id": "phase-1", "evaluation_instant": EVAL, "config": dict(DEFAULT_CONFIG)},
        )
        assert search_response.status_code == 200, search_response.text
        search = search_response.json()
        curb = _candidate(search, ["INT-MODEL-CURB-N_EK"])
        assert curb["classification"] != "rejected"

        promoted = client.post(
            PROMOTE_PATH,
            json={
                "search_id": search["search_id"],
                "proposal_id": curb["proposal"]["proposal_id"],
                "new_scenario_id": "scn-edit-branch",
                "new_scenario_name": "Branch of an edited source",
                "expected_source_revision": 2,
            },
        )
        assert promoted.status_code == 201, promoted.text

        branch = repository.get_scenario("scn-edit-branch")
        assert branch.parent_scenario_id == source.id
        assert [edit.target_id for edit in branch.edits] == ["E_ES2", "N_EK"], (
            "the branch must keep the source's own edits and append the candidate's"
        )
        assert [edit.op for edit in branch.edits] == ["update_attribute", "update_attribute"]
        assert branch.intervention_ids == ["INT-MODEL-CURB-N_EK"]
        # The declared plan (phases, closures, temporary edges, ODs) is carried over.
        assert branch.phases == source.phases
        assert branch.temporary_edges == source.temporary_edges
        assert branch.origins_destinations == source.origins_destinations
        # And the source itself is untouched.
        assert repository.get_scenario(source.id).model_dump(mode="json") == source.model_dump(
            mode="json"
        )
