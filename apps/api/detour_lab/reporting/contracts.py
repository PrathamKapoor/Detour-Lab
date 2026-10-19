"""Generated API/contract artefacts (MASTER_PROMPT §4 ``packages/contracts``).

Produces, deterministically and with no network access:

``openapi.json``  the FastAPI document, so a client can be checked against it
``types.ts``      TypeScript interfaces derived from the **Pydantic domain models**
                  (the same source of truth the API validates with)
``domain-schema.json``  JSON Schema of those models

The TypeScript mapper is deliberately small and total: anything it cannot map
becomes an explicit ``unknown`` rather than a guessed type, and every mapping
decision is unit-tested. Regenerating twice must produce identical bytes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

__all__ = ["CONTRACT_MODELS", "generate_contracts", "model_to_typescript"]

from detour_lab.domain.contracts import (
    AnalysisResult,
    BaseGraphVersion,
    CandidateProposal,
    CoordinateBasis,
    DataSource,
    Edge,
    EdgeEvaluation,
    EvidenceRecord,
    Finding,
    GraphEdit,
    Intervention,
    InterventionCost,
    InterventionEffect,
    InterventionPhaseChange,
    InterventionPrecondition,
    MobilityProfile,
    Node,
    ODPairResult,
    OriginDestination,
    Phase,
    ResolvedAttribute,
    Rule,
    RulePack,
    RuleVerdict,
    Scenario,
    TemporaryEdge,
)
from detour_lab.optimization.model import (
    BaselineOD,
    BaselineProfile,
    BudgetCheck,
    CandidateAssumption,
    CandidateCostLine,
    CandidateCostSummary,
    CandidateEvaluation,
    CandidateVerification,
    DomainSummary,
    ExcludedIntervention,
    ODTransition,
    RankingPolicy,
    SearchBudget,
    SearchConfig,
    SearchOutcome,
    SearchStatus,
)

#: Domain models exposed to the frontend, in dependency order. The generated
#: TypeScript is derived from exactly these models - the same contracts the API
#: validates every request with.
CONTRACT_MODELS: tuple[type[BaseModel], ...] = (
    CoordinateBasis,
    DataSource,
    Node,
    Edge,
    EvidenceRecord,
    ResolvedAttribute,
    BaseGraphVersion,
    OriginDestination,
    Phase,
    TemporaryEdge,
    Scenario,
    GraphEdit,
    Rule,
    RulePack,
    MobilityProfile,
    RuleVerdict,
    Finding,
    EdgeEvaluation,
    ODPairResult,
    AnalysisResult,
    InterventionCost,
    InterventionPhaseChange,
    InterventionPrecondition,
    InterventionEffect,
    Intervention,
    CandidateProposal,
    SearchBudget,
    SearchConfig,
    ExcludedIntervention,
    DomainSummary,
    BaselineOD,
    BaselineProfile,
    ODTransition,
    CandidateVerification,
    CandidateAssumption,
    CandidateCostLine,
    CandidateCostSummary,
    BudgetCheck,
    CandidateEvaluation,
    RankingPolicy,
    SearchStatus,
    SearchOutcome,
)

_HEADER = """// GENERATED FILE - do not edit by hand.
// Produced by detour_lab.reporting.contracts from the Pydantic domain models,
// which are the same contracts the API validates every request with.
//
// Regenerate with:  powershell -NoProfile -File scripts/generate-contracts.ps1

"""


def _ts_name(model_name: str) -> str:
    return model_name


def _ts_type(schema: dict[str, Any]) -> str:
    """Map a JSON Schema fragment to TypeScript, conservatively."""
    if not isinstance(schema, dict):
        return "unknown"
    if "$ref" in schema:
        return _ts_name(schema["$ref"].rsplit("/", 1)[-1])
    if "anyOf" in schema:
        options = [_ts_type(option) for option in schema["anyOf"]]
        non_null = [o for o in options if o != "null"]
        if len(non_null) == 1:
            return f"{non_null[0]} | null"
        return " | ".join(dict.fromkeys(options))
    if "allOf" in schema and len(schema["allOf"]) == 1:
        return _ts_type(schema["allOf"][0])
    if schema.get("enum"):
        return " | ".join(json.dumps(value) for value in schema["enum"])
    kind = schema.get("type")
    if isinstance(kind, list):
        return " | ".join(dict.fromkeys(_ts_type({**schema, "type": k}) for k in kind))
    match kind:
        case "string":
            return "string"
        case "integer" | "number":
            return "number"
        case "boolean":
            return "boolean"
        case "null":
            return "null"
        case "array":
            item_type = _ts_type(schema.get("items", {}))
            # A union item type must keep its parentheses: without them
            # `"a" | "b"[]` would bind as `"a" | ("b"[])`.
            if " | " in item_type:
                item_type = f"({item_type})"
            return f"{item_type}[]"
        case "object" | None:
            if "additionalProperties" in schema:
                return f"Record<string, {_ts_type(schema['additionalProperties'])}>"
            return "Record<string, unknown>"
    return "unknown"


def _collect_fields(model: BaseModel, seen: set[str], definitions: dict[str, Any]) -> None:
    """Depth-first walk so referenced models are emitted before they are referenced."""
    schema = model.model_json_schema(ref_template="#/$defs/{model}")
    defs = schema.get("$defs", {})
    definitions.update(defs)
    for definition in defs.values():
        name = definition.get("title", "")
        if name and name not in seen:
            seen.add(name)
            _collect_from_definition(definition, seen, definitions)
    if model.__name__ not in seen:
        seen.add(model.__name__)
        definitions[model.__name__] = {
            **schema,
            "$defs": defs,
        }
        for name, definition in defs.items():
            if name not in definitions:
                definitions[name] = definition


def _collect_from_definition(definition: dict[str, Any], seen: set[str], definitions: dict[str, Any]) -> None:
    for ref in _refs_in(definition):
        name = ref.rsplit("/", 1)[-1]
        if name in seen:
            continue
        target = definitions.get(name)
        if target is None:
            continue
        seen.add(name)
        _collect_from_definition(target, seen, definitions)


def _refs_in(node: Any) -> list[str]:
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                found.append(value)
            else:
                found.extend(_refs_in(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_refs_in(item))
    return found


def model_to_typescript(models: tuple[type[BaseModel], ...]) -> str:
    """Render TypeScript interfaces for ``models`` and everything they reference."""
    definitions: dict[str, Any] = {}
    seen: set[str] = set()
    for model in models:
        schema = model.model_json_schema(ref_template="#/$defs/{model}")
        definitions.update(schema.get("$defs", {}))
        if model.__name__ not in seen:
            seen.add(model.__name__)
            definitions[model.__name__] = {k: v for k, v in schema.items() if k != "$defs"}
    for model in models:
        _collect_fields(model, seen, definitions)

    blocks: list[str] = []
    for name in sorted(definitions):
        definition = dict(definitions[name])
        definition.pop("$defs", None)
        blocks.append(_interface(name, definition))
    return _HEADER + "\n\n".join(blocks) + "\n"


def _interface(name: str, definition: dict[str, Any]) -> str:
    title = definition.get("title", name)
    if definition.get("type") == "object" and "properties" in definition:
        required = set(definition.get("required", []))
        lines = [f"export interface {name} {{"]
        for field, schema in definition["properties"].items():
            optional = "" if field in required else "?"
            lines.append(f"  {field}{optional}: {_ts_type(schema)};")
        lines.append("}")
        if title != name:
            lines.append("")
        return "\n".join(lines)
    return f"export type {name} = {_ts_type(definition)};"


def generate_contracts(output_dir: str | Path) -> dict[str, str]:
    """Write contract artefacts and return ``{filename: sha256-ish length info}``."""
    from detour_lab.api.main import create_app

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    with (out / "openapi.json").open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(create_app().openapi(), handle, indent=2, sort_keys=True)
        handle.write("\n")

    typescript = model_to_typescript(CONTRACT_MODELS)
    (out / "types.ts").write_text(typescript, encoding="utf-8", newline="\n")

    schema = {model.__name__: model.model_json_schema(ref_template="#/$defs/{model}") for model in CONTRACT_MODELS}
    with (out / "domain-schema.json").open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(schema, handle, indent=2, sort_keys=True)
        handle.write("\n")

    return {
        "openapi.json": str((out / "openapi.json").stat().st_size),
        "types.ts": str((out / "types.ts").stat().st_size),
        "domain-schema.json": str((out / "domain-schema.json").stat().st_size),
    }