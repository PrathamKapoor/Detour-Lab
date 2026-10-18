"""Contract-generation tests (Gate 2: frontend/backend contract parity)."""

from __future__ import annotations

import json

import pytest
from detour_lab.reporting.contracts import (
    CONTRACT_MODELS,
    _ts_type,
    generate_contracts,
    model_to_typescript,
)


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    out = tmp_path_factory.mktemp("contracts")
    sizes = generate_contracts(out)
    return out, sizes


def test_all_three_artefacts_are_written(generated):
    out, sizes = generated
    for name in ("openapi.json", "types.ts", "domain-schema.json"):
        assert (out / name).exists(), name
        assert int(sizes[name]) > 0


def test_openapi_contains_every_prd_route(generated):
    out, _ = generated
    document = json.loads((out / "openapi.json").read_text(encoding="utf-8"))
    paths = document["paths"]
    for route in (
        "/api/v1/projects",
        "/api/v1/projects/{project_id}/imports",
        "/api/v1/projects/{project_id}/graph",
        "/api/v1/projects/{project_id}/scenarios",
        "/api/v1/scenarios/{scenario_id}",
        "/api/v1/scenarios/{scenario_id}/evaluate",
        "/api/v1/runs/{run_id}",
        "/api/v1/runs/{run_id}/manifest",
        "/api/v1/rulesets",
    ):
        assert route in paths, route


def test_typescript_declares_the_frontend_facing_models(generated):
    out, _ = generated
    typescript = (out / "types.ts").read_text(encoding="utf-8")
    for model in ("Node", "Edge", "EvidenceRecord", "RulePack", "Scenario", "AnalysisResult", "ODPairResult"):
        assert f"export interface {model}" in typescript, model
    assert "GENERATED FILE" in typescript


def test_generation_is_byte_identical_on_a_second_run(tmp_path):
    first = generate_contracts(tmp_path / "a")
    second = generate_contracts(tmp_path / "b")
    assert first == second
    for name in ("openapi.json", "types.ts", "domain-schema.json"):
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes()


def test_domain_schema_matches_the_pydantic_models(generated):
    out, _ = generated
    schema = json.loads((out / "domain-schema.json").read_text(encoding="utf-8"))
    assert set(schema) == {model.__name__ for model in CONTRACT_MODELS}
    assert schema["Edge"]["required"]
    assert "geometry" in schema["Edge"]["properties"]


class TestTypeScriptMapper:
    @pytest.mark.parametrize(
        ("schema", "expected"),
        [
            ({"type": "string"}, "string"),
            ({"type": "integer"}, "number"),
            ({"type": "boolean"}, "boolean"),
            ({"type": "array", "items": {"type": "string"}}, "string[]"),
            ({"$ref": "#/$defs/Node"}, "Node"),
            ({"anyOf": [{"type": "string"}, {"type": "null"}]}, "string | null"),
            ({"enum": ["PASS", "FAIL"]}, '"PASS" | "FAIL"'),
            ({"type": "object", "additionalProperties": {"type": "number"}}, "Record<string, number>"),
            ({}, "Record<string, unknown>"),
        ],
    )
    def test_known_mappings(self, schema, expected):
        assert _ts_type(schema) == expected

    def test_unknown_shapes_do_not_guess(self):
        assert _ts_type({"type": "weird"}) == "unknown"
        assert _ts_type("not a dict") == "unknown"

    def test_generated_typescript_is_stable(self):
        first = model_to_typescript(CONTRACT_MODELS)
        second = model_to_typescript(CONTRACT_MODELS)
        assert first == second
        assert first.count("export interface") >= len(CONTRACT_MODELS)