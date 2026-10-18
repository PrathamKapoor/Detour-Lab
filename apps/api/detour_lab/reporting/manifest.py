"""Canonical JSON manifest (FR-016, INV-06, PRD §11).

The manifest is the **only** machine-readable record of a review. It is built from
stored run facts, never from UI screenshots, and its semantic hash is stable
across runs, processes and machines:

* volatile run metadata (run id, wall-clock timestamps, durations, generated file
  names) is kept in a clearly separated ``runtime`` block that is **excluded**
  from the semantic fingerprint;
* everything else — versions, hashes, verdicts, route edge IDs, OD matrices,
  unknowns, source attributions and limitations — is part of it.

The PDF packet is rendered from this same structure (Gate 6), never from the UI.
"""

from __future__ import annotations

from typing import Any

from detour_lab import ENGINE_VERSION, MANIFEST_SCHEMA_VERSION
from detour_lab.domain.contracts import AnalysisResult, MobilityProfile, RulePack
from detour_lab.domain.enums import ReasonCode, VerdictState
from detour_lab.domain.hashing import canonical_json, semantic_hash
from detour_lab.graph.model import PedestrianGraph
from detour_lab.persistence.repository import RunRecord

__all__ = ["MANIFEST_DISCLAIMER", "build_manifest", "manifest_semantic_hash"]

MANIFEST_DISCLAIMER = (
    "Planning analysis - not certified. Verdicts describe checks modelled by "
    "DEMO_RULEPACK_NOT_LEGAL against the evidence available at the evaluation instant. "
    "They are not a legal compliance statement, professional approval, engineering sign-off, "
    "or a guarantee that any person can travel a route. All bundled data is synthetic."
)

#: Keys deliberately excluded from the semantic fingerprint because they differ
#: between otherwise identical runs.
VOLATILE_KEYS = frozenset({"run_id", "created_at", "duration_ms", "evaluation_instant", "generated_at"})


def build_manifest(
    *,
    record: RunRecord,
    graph: PedestrianGraph,
    rulepack: RulePack,
    profile: MobilityProfile,
    scenario,
    dataset_notice: str,
) -> dict[str, Any]:
    """Build the canonical manifest for one analysis run."""
    result: AnalysisResult = record.result

    unknowns = [
        {
            "element_id": verdict.element_id,
            "rule_id": verdict.rule_id,
            "reason_code": verdict.reason_code.value,
            "explanation": verdict.explanation,
            "evidence_ids": sorted({eid for a in verdict.inputs for eid in a.evidence_ids}),
        }
        for verdict in result.verdicts
        if verdict.state is VerdictState.UNKNOWN
    ]
    failures = [
        {
            "element_id": verdict.element_id,
            "rule_id": verdict.rule_id,
            "reason_code": verdict.reason_code.value,
            "explanation": verdict.explanation,
            "evidence_ids": sorted({eid for a in verdict.inputs for eid in a.evidence_ids}),
        }
        for verdict in result.verdicts
        if verdict.state is VerdictState.FAIL
    ]

    semantic_body = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "engine_version": ENGINE_VERSION,
        "project": {
            "id": "persisted-project",
            "notice": dataset_notice,
        },
        "inputs": {
            "base_graph_version_id": result.base_graph_version_id,
            "base_graph_hash": result.base_graph_hash,
            "base_graph_basis": graph.version.basis.model_dump(mode="json"),
            "dataset_source": graph.version.source.model_dump(mode="json"),
            "node_count": len(graph.nodes),
            "edge_count": len(graph.edges),
            "evidence_count": len(graph.evidence_registry.all_records()),
            "run_input_hash": record.input_hash,
        },
        "scenario": {
            "id": result.scenario_id,
            "content_hash": result.scenario_hash,
            "revision": scenario.revision,
            "phase_id": result.phase_id,
            "phase_graph_id": result.phase_graph_id,
            "phase_graph_hash": result.phase_graph_hash,
            "phases": [
                {
                    "id": phase.id,
                    "order": phase.order,
                    "label": phase.label,
                    "boundary_convention": phase.boundary_convention,
                    "closed_edge_ids": phase.closed_edge_ids,
                    "temporary_edge_ids": phase.temporary_edge_ids,
                }
                for phase in sorted(scenario.phases, key=lambda p: p.order)
            ],
        },
        "ruleset": {
            "id": rulepack.id,
            "version": rulepack.version,
            "content_hash": rulepack.content_hash,
            "legal_applicability": rulepack.legal_applicability,
            "disclaimer": rulepack.disclaimer,
            "rules": [
                {"id": r.id, "version": r.version, "scope": r.scope.value, "kind": r.kind.value}
                for r in sorted(rulepack.rules, key=lambda r: r.id)
            ],
        },
        "profile": {
            **profile.model_dump(mode="json"),
            "is_demo_profile": profile.is_demo_profile,
        },
        "results": {
            "counts": result.counts,
            "edge_evaluations": [e.model_dump(mode="json") for e in result.edge_evaluations],
            "verdicts": [v.model_dump(mode="json") for v in result.verdicts],
            "origin_destination_matrix": [od.model_dump(mode="json") for od in result.od_results],
            "unknowns": unknowns,
            "known_failures": failures,
            "warnings": result.warnings,
        },
        "limitations": [
            "Modelled checks only; the rulepack has not been reviewed by an accessibility professional.",
            "All bundled geometry and measurements are synthetic and are not field observations.",
            "A confirmed route means every modelled check passed for the evidence available at the"
            " evaluation instant; it does not guarantee physical safety.",
            "Evidence freshness was judged at the recorded evaluation instant.",
        ],
        "attributions": [
            {
                "name": graph.version.source.name,
                "license": graph.version.source.license,
                "attribution": graph.version.source.attribution,
                "url": graph.version.source.url,
                "provenance_class": graph.version.source.provenance_class.value,
            }
        ],
        "disclaimer": MANIFEST_DISCLAIMER,
    }

    return {
        **semantic_body,
        "runtime": {
            "run_id": record.run_id,
            "created_at": record.created_at,
            "duration_ms": record.duration_ms,
            "evaluation_instant": record.evaluation_instant,
            "engine_version": record.engine_version,
        },
        "semantic_hash": semantic_hash(semantic_body),
        "canonical_json_bytes": len(canonical_json(semantic_body).encode("utf-8")),
    }


def manifest_semantic_hash(manifest: dict[str, Any]) -> str:
    """Recompute the semantic fingerprint, ignoring the volatile runtime block."""
    body = {k: v for k, v in manifest.items() if k not in {"runtime", "semantic_hash", "canonical_json_bytes"}}
    return semantic_hash(body)


def open_unknown_summary(result: AnalysisResult) -> list[dict[str, Any]]:
    """Critical unknowns ordered deterministically for the inspection queue."""
    records = [
        {
            "element_id": verdict.element_id,
            "rule_id": verdict.rule_id,
            "reason_code": verdict.reason_code.value,
            "severity": verdict.criticality.value,
        }
        for verdict in result.verdicts
        if verdict.state is VerdictState.UNKNOWN
    ]
    order = {code.value: index for index, code in enumerate(sorted(ReasonCode, key=lambda c: c.value))}
    return sorted(records, key=lambda r: (r["severity"], order.get(r["reason_code"], 99), r["element_id"]))