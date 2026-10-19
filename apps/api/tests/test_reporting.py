"""Review-packet tests (Gate 6, G6-13..G6-16).

The PDF assertions are deliberately structural rather than visual: the packet is
checked for a valid signature, for the presence of the authoritative identities
and disclosures, for deterministic semantic content, and for correct handling of
unavailable sections. A test that only asserted "a file was produced" would pass
even if every section were empty, so each one names the fact it protects.
"""

from __future__ import annotations

import base64
import json
import re
import zlib
from datetime import datetime

import pytest
from conftest import AS_OF
from detour_lab.api.main import create_app
from detour_lab.reporting.pdf import render_report_pdf, rendered_page_count
from detour_lab.reporting.report import ReportDataError, ReviewReport, validate_report_sources
from detour_lab.reporting.service import generate_report

PROFILE_A = "DEMO_PROFILE_MANUAL_WHEELCHAIR"
PROFILE_B = "DEMO_PROFILE_LIMITED_MOBILITY_WALKER"
SCENARIO = "scn-demo-baseline"


@pytest.fixture()
def client(tmp_path):
    from fastapi.testclient import TestClient

    app = create_app(tmp_path / "reports.sqlite3")
    with TestClient(app) as test_client:
        yield test_client, app


def _pdf_text(pdf_bytes: bytes) -> str:
    """Extract the drawn text from a ReportLab PDF without a second PDF library.

    ReportLab encodes page content as ASCII85 + Flate. Decompressing and
    collecting the literal strings of the text-showing operators recovers
    exactly what a reader would select and copy.
    """
    parts: list[str] = []
    for stream in re.findall(rb"stream\r?\n(.*?)endstream", pdf_bytes, re.S):
        body = stream.strip(b"\r\n")
        try:
            decoded = zlib.decompress(base64.a85decode(body, adobe=True))
        except Exception:
            continue
        if b"Tj" not in decoded and b"TJ" not in decoded:
            continue
        for literal in re.findall(rb"\((?:\\.|[^\\()])*\)", decoded):
            text = literal[1:-1].decode("latin-1")
            parts.append(text.replace("\\(", "(").replace("\\)", ")").replace("\\\\", "\\"))
    return "\n".join(parts)


def _pdf_compact_text(pdf_bytes: bytes) -> str:
    """Whitespace-free form of the drawn text.

    A table cell is laid out across as many text-showing operations as it needs
    lines, so a token like ``OD-W->OD-GATE`` is legitimately split in the
    content stream. Removing whitespace reconstructs it without weakening the
    assertion.
    """
    return re.sub(r"\s+", "", _pdf_text(pdf_bytes))


def _make_run(client, phase="phase-1", profile=PROFILE_A, instant=None):
    test_client, _app = client
    response = test_client.post(
        f"/api/v1/scenarios/{SCENARIO}/evaluate",
        json={
            "profile_id": profile,
            "phase_id": phase,
            "evaluation_instant": instant or AS_OF.isoformat(),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["run"]


# --------------------------------------------------------------------------- validation


class TestReportValidation:
    def test_a_report_without_a_run_is_refused(self):
        with pytest.raises(ReportDataError) as excinfo:
            validate_report_sources(
                scenario_id=SCENARIO, run_ids=[], search_ids=[], experiment_ids=[]
            )
        assert excinfo.value.code == "NO_SOURCE_RUN"

    def test_duplicate_selection_is_refused(self):
        with pytest.raises(ReportDataError) as excinfo:
            validate_report_sources(
                scenario_id=SCENARIO, run_ids=["run-a", "run-a"], search_ids=[], experiment_ids=[]
            )
        assert excinfo.value.code == "DUPLICATE_SELECTION"

    def test_run_from_another_scenario_is_refused(self, client):
        """A run belonging elsewhere is refused rather than silently included."""
        _test_client, app = client
        run = _make_run(client)
        repository = app.state.repository

        # A second scenario on the same graph, with its own real run.
        from detour_lab.api.state import rulepack_path
        from detour_lab.rules.engine import load_rulepack

        source = repository.get_scenario(SCENARIO)
        rulepack = load_rulepack(rulepack_path())
        other = source.model_copy(
            update={"id": "scn-other", "name": "other", "content_hash": "", "parent_scenario_id": SCENARIO}
        )
        repository.create_scenario(other, project_id="demo-project-synthetic")
        other_run = repository.evaluate_and_store(
            scenario_id="scn-other",
            phase_id="phase-1",
            profile=__import__("detour_lab.rules.profiles", fromlist=["DEMO_PROFILES"]).DEMO_PROFILES[0],
            rulepack=rulepack,
            evaluation_instant=AS_OF,
        )
        assert other_run.run_id != run["id"]
        with pytest.raises(ReportDataError) as excinfo:
            generate_report(
                repository=repository, scenario_id=SCENARIO, run_ids=[other_run.run_id]
            )
        assert excinfo.value.code == "RUN_SCENARIO_MISMATCH"
        assert excinfo.value.details["run_scenario_id"] == "scn-other"

    def test_experiment_from_another_scenario_is_refused(self, client):
        _test_client, app = client
        run = _make_run(client)
        repository = app.state.repository
        source = repository.get_scenario(SCENARIO)
        other = source.model_copy(
            update={"id": "scn-other2", "name": "other", "content_hash": "", "parent_scenario_id": SCENARIO}
        )
        repository.create_scenario(other, project_id="demo-project-synthetic")
        repository.store_failure_experiment(
            experiment_id="fxp-foreign",
            scenario_id="scn-other2",
            scenario_revision=other.revision,
            phase_id="phase-1",
            profile_id=PROFILE_A,
            engine_version="test",
            status="completed",
            input_hash="sha256:a",
            semantic_hash="sha256:b",
            duration_ms=0.0,
            payload={"experiment_id": "fxp-foreign"},
            created_at="2026-03-01T00:00:00+00:00",
        )
        with pytest.raises(Exception) as excinfo:
            generate_report(
                repository=repository,
                scenario_id=SCENARIO,
                run_ids=[run["id"]],
                experiment_ids=["fxp-foreign"],
            )
        assert "scn-other2" in str(excinfo.value)

    def test_missing_run_is_refused(self, client):
        _test_client, app = client
        with pytest.raises(Exception) as excinfo:
            generate_report(
                repository=app.state.repository, scenario_id=SCENARIO, run_ids=["run-does-not-exist"]
            )
        assert "run-does-not-exist" in str(excinfo.value)


# --------------------------------------------------------------------------- PDF structure


class TestPdfStructure:
    def test_pdf_is_valid_and_parseable(self, client):
        _test_client, app = client
        run = _make_run(client)
        generated = generate_report(repository=app.state.repository, scenario_id=SCENARIO, run_ids=[run["id"]])
        assert generated.pdf_bytes.startswith(b"%PDF-")
        assert generated.pdf_bytes.rstrip().endswith(b"%%EOF")
        assert rendered_page_count(generated.pdf_bytes) == generated.page_count
        assert generated.page_count >= 8, "a review packet must actually contain its sections"

    def test_text_is_selectable_on_every_page(self, client):
        _test_client, app = client
        run = _make_run(client)
        generated = generate_report(repository=app.state.repository, scenario_id=SCENARIO, run_ids=[run["id"]])
        text = _pdf_text(generated.pdf_bytes)
        assert len(text) > 4000, "the packet must carry real extractable text, not a bitmap"
        for heading in (
            "Report identification",
            "Executive summary",
            "Study scope",
            "Network overview",
            "Construction modifications",
            "Accessibility findings",
            "Evidence provenance",
            "Alternative-plan analysis",
            "Failure Lab experiments",
            "Assumptions and limitations",
            "Reproducibility manifest",
            "Human review",
        ):
            assert heading in text, f"section {heading!r} missing from the rendered packet"

    def test_identity_is_correct(self, client):
        _test_client, app = client
        run = _make_run(client)
        scenario = app.state.repository.get_scenario(SCENARIO)
        generated = generate_report(repository=app.state.repository, scenario_id=SCENARIO, run_ids=[run["id"]])
        text = _pdf_text(generated.pdf_bytes)
        assert SCENARIO in text
        assert f"revision {scenario.revision}" in text
        assert scenario.content_hash in text
        assert generated.payload.identity.scenario_revision == scenario.revision
        assert generated.payload.identity.project_id == "demo-project-synthetic"

    def test_run_identities_are_preserved(self, client):
        _test_client, app = client
        run = _make_run(client)
        generated = generate_report(repository=app.state.repository, scenario_id=SCENARIO, run_ids=[run["id"]])
        assert generated.payload.reproducibility.selected_run_ids == [run["id"]]
        assert run["semantic_hash"] in generated.payload.reproducibility.selected_run_semantic_hashes
        assert run["input_hash"] in generated.payload.reproducibility.selected_run_input_hashes
        assert run["id"] in _pdf_text(generated.pdf_bytes)

    def test_phase_and_ruleset_identity(self, client):
        _test_client, app = client
        run = _make_run(client)
        generated = generate_report(repository=app.state.repository, scenario_id=SCENARIO, run_ids=[run["id"]])
        assert generated.payload.reproducibility.rulepack_id == "DEMO_RULEPACK_NOT_LEGAL"
        assert generated.payload.reproducibility.rulepack_version == "1.0.0"
        assert generated.payload.reproducibility.rulepack_hash.startswith("sha256:")
        assert "phase-1" in _pdf_text(generated.pdf_bytes)

    def test_measurement_units_are_preserved(self, client):
        _test_client, app = client
        run = _make_run(client)
        generated = generate_report(repository=app.state.repository, scenario_id=SCENARIO, run_ids=[run["id"]])
        width = next(r for r in generated.payload.evidence_rows if r.evidence_id == "EV-E_K1-width")
        assert width.unit == "mm"
        assert width.value == 1100
        slope = next(r for r in generated.payload.evidence_rows if r.evidence_id == "EV-E_K1-slope")
        assert slope.unit == "percent"
        assert slope.value == pytest.approx(1.0)
        assert "mm" in _pdf_text(generated.pdf_bytes)

    def test_unknown_conditions_are_preserved(self, client):
        _test_client, app = client
        run = _make_run(client)
        generated = generate_report(repository=app.state.repository, scenario_id=SCENARIO, run_ids=[run["id"]])
        assert any(r.resolution_status == "NO_EVIDENCE" for r in generated.payload.evidence_issues)
        assert generated.payload.scope.rulepack_legal_applicability == "unverified"

    def test_possible_only_is_described_honestly(self, client):
        _test_client, app = client
        run = _make_run(client)
        generated = generate_report(repository=app.state.repository, scenario_id=SCENARIO, run_ids=[run["id"]])
        possible = [r for r in generated.payload.od_rows if r.possibly_reachable and not r.confirmed_reachable]
        assert possible, "the seeded fixture has possible-only pairs"
        for row in possible:
            assert row.confirmed_distance_m is None, "a possible-only pair has no confirmed distance"
        text = _pdf_text(generated.pdf_bytes)
        assert "possible-only" in text
        assert "NOT confirmed accessibility" in text

    def test_synthetic_and_demo_rulepack_disclosures(self, client):
        _test_client, app = client
        run = _make_run(client)
        generated = generate_report(repository=app.state.repository, scenario_id=SCENARIO, run_ids=[run["id"]])
        text = _pdf_text(generated.pdf_bytes)
        assert "PLANNING ANALYSIS - NOT CERTIFIED" in text
        assert "SYNTHETIC" in text
        assert "DEMO_RULEPACK_NOT_LEGAL" in text
        assert "legal_applicability" not in text or "unverified" in text
        assert generated.payload.scope.synthetic_dataset is True
        assert generated.payload.limitations.rules_are_demonstration_only is True

    def test_no_cost_is_invented(self, client):
        _test_client, app = client
        run = _make_run(client)
        generated = generate_report(repository=app.state.repository, scenario_id=SCENARIO, run_ids=[run["id"]])
        assert generated.payload.alternative_plans == []
        assert generated.payload.scope.rulepack_legal_applicability == "unverified"
        assert "NO REVIEW RECORDED" in _pdf_text(generated.pdf_bytes)

    def test_no_reviewer_or_approval_is_invented(self, client):
        _test_client, app = client
        run = _make_run(client)
        generated = generate_report(repository=app.state.repository, scenario_id=SCENARIO, run_ids=[run["id"]])
        review = generated.payload.human_review
        assert review.review_recorded is False
        assert review.reviewer is None
        assert "NO REVIEW RECORDED" in review.approval_status
        text = _pdf_text(generated.pdf_bytes)
        assert "No human review has been recorded" in text

    def test_evidence_references_are_included(self, client):
        _test_client, app = client
        run = _make_run(client)
        generated = generate_report(repository=app.state.repository, scenario_id=SCENARIO, run_ids=[run["id"]])
        assert generated.payload.evidence_rows
        assert generated.payload.evidence_issues
        referenced = {eid for f in generated.payload.findings for eid in f.evidence_ids}
        assert referenced, "findings must cite the evidence records they used"
        assert referenced <= {r.evidence_id for r in generated.payload.evidence_rows}


# --------------------------------------------------------------------------- determinism


class TestReportDeterminism:
    def test_semantic_payload_is_deterministic(self, client):
        _test_client, app = client
        run = _make_run(client)
        first = generate_report(repository=app.state.repository, scenario_id=SCENARIO, run_ids=[run["id"]])
        second = generate_report(repository=app.state.repository, scenario_id=SCENARIO, run_ids=[run["id"]])
        assert first.semantic_hash == second.semantic_hash
        assert first.payload.semantic_body() == second.payload.semantic_body()
        assert first.payload.od_rows == second.payload.od_rows
        assert first.payload.findings == second.payload.findings
        assert first.payload.evidence_rows == second.payload.evidence_rows

    def test_regenerating_a_stored_report_reproduces_identical_bytes(self, client):
        _test_client, app = client
        run = _make_run(client)
        generated = generate_report(repository=app.state.repository, scenario_id=SCENARIO, run_ids=[run["id"]])
        stored = app.state.repository.get_review_report(generated.record_id)
        replayed = ReviewReport.model_validate(stored.payload)
        assert render_report_pdf(replayed) == generated.pdf_bytes, (
            "ReportLab runs in invariant mode, so a stored payload must render to identical bytes"
        )

    def test_download_endpoint_returns_the_recorded_bytes(self, client):
        test_client, app = client
        run = _make_run(client)
        generated = generate_report(repository=app.state.repository, scenario_id=SCENARIO, run_ids=[run["id"]])
        response = test_client.get(f"/api/v1/reports/{generated.record_id}/document.pdf")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert response.content == generated.pdf_bytes
        assert response.headers["x-detour-lab-pdf-sha256"] == generated.pdf_digest
        assert response.headers["x-detour-lab-not-certified"] == "true"

    def test_canonical_manifest_matches_the_stored_payload(self, client):
        test_client, app = client
        run = _make_run(client)
        generated = generate_report(repository=app.state.repository, scenario_id=SCENARIO, run_ids=[run["id"]])
        response = test_client.get(f"/api/v1/reports/{generated.record_id}/manifest")
        assert response.status_code == 200
        body = json.loads(response.content)
        assert body["identity"]["report_id"] == generated.record_id
        assert response.headers["x-detour-lab-semantic-hash"] == generated.semantic_hash

    def test_equivalent_regeneration_preserves_semantic_identity(self, client):
        """A report stays bound to the historical revision it described."""
        test_client, app = client
        run = _make_run(client)
        generated = generate_report(repository=app.state.repository, scenario_id=SCENARIO, run_ids=[run["id"]])

        patched = test_client.patch(
            f"/api/v1/scenarios/{SCENARIO}",
            json={
                "expected_revision": 1,
                "edits": [
                    {
                        "op": "update_attribute",
                        "target_id": "E_LINK",
                        "params": {
                            "field": "width_mm",
                            "value": 1600,
                            "unit": "mm",
                            "method": "manual_entry",
                            "source": "test",
                        },
                    }
                ],
            },
        )
        assert patched.status_code == 200

        detail = test_client.get(f"/api/v1/reports/{generated.record_id}").json()
        assert detail["scenario_revision"] == 1
        assert detail["current_scenario_revision"] == 2
        assert detail["describes_current_revision"] is False
        assert detail["payload"]["identity"]["scenario_revision"] == 1
        assert generated.record_id in _pdf_text(
            test_client.get(f"/api/v1/reports/{generated.record_id}/document.pdf").content
        )

    def test_report_id_is_not_part_of_the_semantic_hash(self, client):
        _test_client, app = client
        run = _make_run(client)
        first = generate_report(repository=app.state.repository, scenario_id=SCENARIO, run_ids=[run["id"]])
        second = generate_report(repository=app.state.repository, scenario_id=SCENARIO, run_ids=[run["id"]])
        assert first.record_id != second.record_id
        assert first.semantic_hash == second.semantic_hash
        assert first.pdf_bytes != second.pdf_bytes, (
            "the covers name different identifiers, so the byte streams differ; only the semantic "
            "payload is identical"
        )


# --------------------------------------------------------------------------- experiments in the packet


class TestExperimentsInReport:
    def test_experiment_details_correspond_to_real_records(self, client):
        test_client, app = client
        run = _make_run(client)
        created = test_client.post(
            f"/api/v1/scenarios/{SCENARIO}/failure-lab/experiments",
            json={
                "phase_ids": ["phase-1"],
                "profile_ids": [PROFILE_A],
                "evaluation_instant": AS_OF.isoformat(),
                "suite_ids": ["critical_closure", "evidence_gap"],
            },
        )
        assert created.status_code == 200
        ids = [e["experiment_id"] for e in created.json()["experiments"]]

        generated = generate_report(
            repository=app.state.repository,
            scenario_id=SCENARIO,
            run_ids=[run["id"]],
            experiment_ids=ids,
        )
        assert [e.experiment_id for e in generated.payload.experiments] == ids
        for stored, reported in zip(ids, generated.payload.experiments, strict=True):
            record = app.state.repository.get_failure_experiment(stored)
            assert reported.semantic_hash == record.semantic_hash
            assert reported.input_hash == record.input_hash
            assert reported.status == record.status
        text = _pdf_text(generated.pdf_bytes)
        for experiment_id in ids:
            assert experiment_id in text

    def test_robustness_summary_is_included_with_its_denominator(self, client):
        test_client, app = client
        run = _make_run(client)
        created = test_client.post(
            f"/api/v1/scenarios/{SCENARIO}/failure-lab/experiments",
            json={
                "phase_ids": ["phase-1"],
                "profile_ids": [PROFILE_A],
                "evaluation_instant": AS_OF.isoformat(),
                "suite_ids": ["critical_closure", "incidental_closure"],
            },
        ).json()
        ids = [e["experiment_id"] for e in created["experiments"]]
        generated = generate_report(
            repository=app.state.repository,
            scenario_id=SCENARIO,
            run_ids=[run["id"]],
            experiment_ids=ids,
        )
        assert generated.payload.robustness is not None
        assert generated.payload.robustness["experiments_completed"] == 2
        assert "Only COMPLETED experiments contribute" in generated.payload.robustness["denominator_note"]
        text = _pdf_text(generated.pdf_bytes)
        assert "Robustness summary" in text
        assert "NOT a probability" in text

    def test_unselected_sections_are_marked_unavailable_not_empty(self, client):
        _test_client, app = client
        run = _make_run(client)
        generated = generate_report(repository=app.state.repository, scenario_id=SCENARIO, run_ids=[run["id"]])
        assert generated.payload.section_availability["alternative_plans"].status == "not_selected"
        assert generated.payload.section_availability["experiments"].status == "not_selected"
        text = _pdf_text(generated.pdf_bytes)
        assert "Section not selected: No optimisation search was selected" in text
        assert "No Failure Lab experiment was selected" in text


# --------------------------------------------------------------------------- robustness and safety


class TestReportRobustnessAndSafety:
    def test_large_tables_paginate_without_losing_rows(self, client):
        _test_client, app = client
        # One run per phase and profile keeps the OD and findings tables long.
        run_ids = [
            _make_run(client, phase="phase-1", profile=PROFILE_A)["id"],
            _make_run(client, phase="phase-1", profile=PROFILE_B)["id"],
            _make_run(client, phase="phase-2", profile=PROFILE_A)["id"],
            _make_run(client, phase="phase-2", profile=PROFILE_B)["id"],
        ]
        generated = generate_report(repository=app.state.repository, scenario_id=SCENARIO, run_ids=run_ids)
        assert len(generated.payload.od_rows) == 16, "4 runs x 4 origin-destination pairs"
        compact = _pdf_compact_text(generated.pdf_bytes)
        for row in generated.payload.od_rows:
            assert row.pair_id in compact, f"{row.pair_id} was lost from the rendered table"
            assert row.profile_id in compact
        assert generated.page_count >= 8

    def test_long_identifiers_remain_readable(self, client):
        _test_client, app = client
        run = _make_run(client)
        generated = generate_report(repository=app.state.repository, scenario_id=SCENARIO, run_ids=[run["id"]])
        text = _pdf_text(generated.pdf_bytes)
        for identifier in (
            generated.payload.reproducibility.base_graph_hash,
            generated.payload.reproducibility.scenario_content_hash,
            generated.payload.reproducibility.rulepack_hash,
        ):
            assert identifier in text, "a full content hash must survive into the rendered packet"

    def test_untrusted_text_cannot_execute_or_break_the_document(self, client, tmp_path):
        """Stored markup is escaped, and the document still renders."""
        test_client, app = client
        repository = app.state.repository
        scenario = repository.get_scenario(SCENARIO)
        before_hash = scenario.content_hash
        patched = test_client.patch(
            f"/api/v1/scenarios/{SCENARIO}",
            json={
                "expected_revision": scenario.revision,
                "edits": [
                    {
                        "op": "update_attribute",
                        "target_id": "E_LINK",
                        "params": {
                            "field": "surface",
                            "value": "asphalt <script>alert('x')</script> & more",
                            "method": "manual_entry",
                            "source": "hostile label",
                        },
                    }
                ],
                "note": "hostile text",
            },
        )
        assert patched.status_code == 200
        run = _make_run(client)
        generated = generate_report(repository=repository, scenario_id=SCENARIO, run_ids=[run["id"]])
        assert generated.pdf_bytes.startswith(b"%PDF-")
        assert generated.pdf_bytes.rstrip().endswith(b"%%EOF")
        text = _pdf_text(generated.pdf_bytes)
        assert "<script>" not in text.replace("\\", "")
        del before_hash

    def test_unicode_text_renders(self, client):
        _test_client, app = client
        run = _make_run(client)
        generated = generate_report(repository=app.state.repository, scenario_id=SCENARIO, run_ids=[run["id"]])
        text = _pdf_text(generated.pdf_bytes)
        assert "METRE" in text.upper() or "metre" in text.lower() or "Length" in text

    def test_error_handling_is_clean(self, client):
        test_client, _app = client
        missing = test_client.get("/api/v1/reports/rpt-nope/document.pdf")
        assert missing.status_code == 404
        body = missing.json()
        assert set(body) == {"code", "message", "details", "request_id"}
        assert body["code"] == "NOT_FOUND"

        invalid = test_client.post(
            f"/api/v1/scenarios/{SCENARIO}/reports", json={"run_ids": []}
        )
        assert invalid.status_code == 422
        # Rejected by the typed request contract before any work is attempted.
        assert invalid.json()["code"] == "REQUEST_VALIDATION_ERROR"

        unknown_run = test_client.post(
            f"/api/v1/scenarios/{SCENARIO}/reports", json={"run_ids": ["run-nope"]}
        )
        assert unknown_run.status_code == 404
        assert unknown_run.json()["code"] == "NOT_FOUND"

    def test_download_uses_a_server_generated_filename(self, client):
        test_client, app = client
        run = _make_run(client)
        generated = generate_report(repository=app.state.repository, scenario_id=SCENARIO, run_ids=[run["id"]])
        response = test_client.get(f"/api/v1/reports/{generated.record_id}/document.pdf")
        disposition = response.headers["content-disposition"]
        assert disposition == f'attachment; filename="detour-lab-review-{generated.record_id}.pdf"'
        assert "\\" not in disposition and "/" not in disposition

    def test_stored_report_listing_marks_historical_reports(self, client):
        test_client, app = client
        run = _make_run(client)
        generate_report(repository=app.state.repository, scenario_id=SCENARIO, run_ids=[run["id"]])
        listing = test_client.get(f"/api/v1/scenarios/{SCENARIO}/reports").json()
        assert listing["report_count"] == 1
        entry = listing["reports"][0]
        assert entry["describes_current_revision"] is True
        assert entry["selected_run_ids"] == [run["id"]]
        assert "never relabelled" in listing["historical_note"]

    def test_optimization_search_is_included_when_selected(self, client):
        test_client, app = client
        run = _make_run(client)
        search = test_client.post(
            f"/api/v1/scenarios/{SCENARIO}/optimization/search",
            json={"phase_id": "phase-1", "profile_ids": [PROFILE_A]},
        )
        assert search.status_code == 200, search.text
        search_id = search.json()["search_id"]
        generated = generate_report(
            repository=app.state.repository,
            scenario_id=SCENARIO,
            run_ids=[run["id"]],
            search_ids=[search_id],
        )
        assert len(generated.payload.alternative_plans) == 1
        plan = generated.payload.alternative_plans[0]
        assert plan.search_id == search_id
        assert plan.solver_status
        assert "NOT ESTIMATED" in _pdf_text(generated.pdf_bytes) or plan.selected_candidates

    def test_generation_time_is_excluded_from_the_semantic_payload(self, client):
        _test_client, app = client
        run = _make_run(client)
        generated = generate_report(repository=app.state.repository, scenario_id=SCENARIO, run_ids=[run["id"]])
        body = generated.payload.semantic_body()
        assert "report_id" not in body["identity"]
        assert "created_at" not in body
        runtime = generated.runtime_block()
        assert runtime["report_id"] == generated.record_id
        assert runtime["pdf_sha256"] == generated.pdf_digest
        assert datetime.fromisoformat(runtime["generated_at"]).tzinfo is not None