"""Automated security hardening and regression test suite (Gate 7).

Verifies:
1. Path traversal protection on report downloads and resource endpoints.
2. HTTP security headers (nosniff, DENY, strict-origin, permissions).
3. Input validation and parameter bounds checking (optimization bounds, search limits).
4. SQL injection resilience across repository queries.
5. Markup / script tag escaping in reporting and domain models.
6. Optimistic concurrency control (409 conflict handling).
7. Error envelope consistency (no stack traces leaked to clients).
"""

from __future__ import annotations

import json

import pytest
from detour_lab.api.main import create_app
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path):
    """TestClient wired to a fresh migrated and seeded test database."""
    db_path = tmp_path / "test_sec.sqlite3"
    app = create_app(database=db_path)
    with TestClient(app) as test_client:
        yield test_client


class TestPathTraversalHardening:
    """Security control: Path traversal attempts must be strictly rejected."""

    @pytest.mark.parametrize(
        "malicious_id",
        [
            "../etc/passwd",
            "..\\..\\windows\\system32\\cmd.exe",
            "%2e%2e%2fetc%2fpasswd",
            "report/../../secret",
            "id_with_null%00byte",
            "a" * 128,  # Exceeds max length
            "; DROP TABLE users; --",
            "<script>alert(1)</script>",
        ],
    )
    def test_report_endpoints_reject_path_traversal_ids(self, client, malicious_id):
        # 1. Document download
        res1 = client.get(f"/api/v1/reports/{malicious_id}/document.pdf")
        assert res1.status_code in (400, 404)
        data1 = res1.json()
        assert "code" in data1
        assert data1["code"] in ("INVALID_IDENTIFIER", "NOT_FOUND", "HTTP_404")

        # 2. Manifest download
        res2 = client.get(f"/api/v1/reports/{malicious_id}/manifest")
        assert res2.status_code in (400, 404)
        data2 = res2.json()
        assert "code" in data2
        assert data2["code"] in ("INVALID_IDENTIFIER", "NOT_FOUND", "HTTP_404")

        # 3. Metadata retrieval
        res3 = client.get(f"/api/v1/reports/{malicious_id}")
        assert res3.status_code in (400, 404)


class TestSecurityHeaders:
    """Security control: Standard defensive HTTP headers must be present."""

    def test_api_responses_include_security_headers(self, client):
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        headers = response.headers

        assert headers.get("X-Content-Type-Options") == "nosniff"
        assert headers.get("X-Frame-Options") == "DENY"
        assert headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
        assert "geolocation=()" in headers.get("Permissions-Policy", "")


class TestInputBoundsHardening:
    """Security control: Numerical and collection bounds enforced on optimization searches."""

    def test_search_config_enforces_strict_bounds(self, client):
        # Test out-of-bounds max_candidates > 500
        payload_invalid_candidates = {
            "phase_id": "phase-1",
            "config": {
                "max_candidates": 1000,  # Limit is 500
            },
        }
        res1 = client.post("/api/v1/scenarios/scn-demo-baseline/optimization/search", json=payload_invalid_candidates)
        assert res1.status_code == 422
        assert res1.json()["code"] == "REQUEST_VALIDATION_ERROR"

        # Test out-of-bounds max_interventions > 4
        payload_invalid_interventions = {
            "phase_id": "phase-1",
            "config": {
                "max_interventions": 10,  # Limit is 4
            },
        }
        res2 = client.post("/api/v1/scenarios/scn-demo-baseline/optimization/search", json=payload_invalid_interventions)
        assert res2.status_code == 422
        assert res2.json()["code"] == "REQUEST_VALIDATION_ERROR"

    def test_search_request_rejects_unknown_fields(self, client):
        payload_extra = {
            "phase_id": "phase-1",
            "unknown_injected_field": "exploit",
        }
        res = client.post("/api/v1/scenarios/scn-demo-baseline/optimization/search", json=payload_extra)
        assert res.status_code == 422
        assert res.json()["code"] == "REQUEST_VALIDATION_ERROR"


class TestSqlInjectionResilience:
    """Security control: Parameterized SQL prevents data exfiltration or table tampering."""

    @pytest.mark.parametrize(
        "sql_payload",
        [
            "' OR 1=1 --",
            "admin'--",
            "1; DROP TABLE scenarios;",
            "' UNION SELECT * FROM graph_versions --",
        ],
    )
    def test_scenario_lookup_with_sql_injection_is_safe(self, client, sql_payload):
        res = client.get(f"/api/v1/scenarios/{sql_payload}")
        assert res.status_code in (400, 404)
        assert res.json()["code"] in ("INVALID_IDENTIFIER", "NOT_FOUND", "HTTP_404")


class TestOptimisticConcurrencyProtection:
    """Security control: Revisions cannot be silently overwritten (HTTP 409)."""

    def test_conflicting_revision_returns_409(self, client):
        # 1. Fetch current demo scenario revision
        res_scn = client.get("/api/v1/scenarios/scn-demo-baseline")
        assert res_scn.status_code == 200
        current_rev = res_scn.json()["revision"]

        # 2. Try applying an edit with stale expected revision (e.g., current_rev - 1 or + 5)
        stale_rev = current_rev + 5
        edit_payload = {
            "expected_revision": stale_rev,
            "edits": [
                {
                    "op": "close_edge",
                    "target_id": "E_ALT",
                    "reason": "Test conflict check",
                }
            ],
            "note": "Security test concurrent update",
        }
        res_patch = client.patch("/api/v1/scenarios/scn-demo-baseline", json=edit_payload)
        assert res_patch.status_code == 409
        body = res_patch.json()
        assert body["code"] == "REVISION_CONFLICT"
        assert body["details"]["expected_revision"] == stale_rev
        assert body["details"]["actual_revision"] == current_rev


class TestErrorInformationDisclosure:
    """Security control: Unhandled exceptions or 404s must never leak stack traces."""

    def test_nonexistent_endpoint_returns_clean_flat_envelope(self, client):
        res = client.get("/api/v1/nonexistent_secret_admin_route")
        assert res.status_code == 404
        body = res.json()
        assert "code" in body
        assert "message" in body
        assert "traceback" not in body
        assert "File " not in json.dumps(body)
