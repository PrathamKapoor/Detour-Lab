"""Versioned HTTP boundary for DETOUR LAB (PRD §10.2).

Gate 0 scope: a real, booting application with typed contracts, a consistent
error envelope and read-only access to the seeded demonstration dataset.
Persistence, scenario mutation and optimisation endpoints are later gates and are
**not** stubbed here - an unimplemented route is absent rather than fake.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from detour_lab import ENGINE_VERSION, MANIFEST_SCHEMA_VERSION, __version__
from detour_lab.analysis.run import run_analysis
from detour_lab.domain.contracts import Scenario
from detour_lab.ingestion.schema import IngestionError, load_local_planar_dataset
from detour_lab.rules.engine import load_rulepack
from detour_lab.rules.profiles import DEMO_PROFILES
from detour_lab.scenarios.apply import GraphEditError
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

REPO_ROOT = Path(__file__).resolve().parents[4]
SEED_PATH = REPO_ROOT / "data" / "demo" / "synthetic_study_area.localplanar.json"
RULEPACK_PATH = (
    REPO_ROOT / "apps" / "api" / "detour_lab" / "rules" / "rulepacks" / "DEMO_RULEPACK_NOT_LEGAL.v1.json"
)

#: The evaluation instant is fixed for the seeded demo so results are reproducible.
#: Real runs record their own timestamp; the demo must replay identically.
DEMO_EVALUATION_INSTANT = datetime(2026, 3, 1, tzinfo=UTC)

app = FastAPI(
    title="DETOUR LAB API",
    version=__version__,
    description=(
        "Pre-construction pedestrian detour decision support and model verification. "
        "Verdicts are 'Pass in modeled checks' / 'Fail' / 'Unknown' / 'Not applicable' and are "
        "never a legal, regulatory or safety certification. The bundled dataset is synthetic."
    ),
)


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict = Field(default_factory=dict)
    request_id: str


class HealthResponse(BaseModel):
    status: str
    engine_version: str
    manifest_schema_version: str
    rulepack_id: str
    rulepack_hash: str
    dataset_id: str
    dataset_provenance: str
    synthetic_data: bool
    legal_applicability: str
    disclaimer: str


class EvaluateRequest(BaseModel):
    profile_id: str = Field(default="DEMO_PROFILE_MANUAL_WHEELCHAIR")
    phase_id: str = Field(default="phase-1")


def _bundle():
    return load_local_planar_dataset(SEED_PATH)


def _rulepack():
    return load_rulepack(RULEPACK_PATH)


def _demo_scenario(bundle, rulepack) -> Scenario:
    return Scenario(
        id="scn-demo-baseline",
        name="Seeded demonstration scenario (synthetic data)",
        base_graph_version_id=bundle.graph.version.id,
        rulepack_id=rulepack.id,
        rulepack_hash=rulepack.content_hash,
        profile_ids=[profile.id for profile in DEMO_PROFILES],
        phases=list(bundle.phases),
        origins_destinations=list(bundle.origins_destinations),
        temporary_edges=list(bundle.temporary_edges),
        note="Seeded scenario. All attributes are synthetic demonstration values.",
    )


@app.exception_handler(IngestionError)
async def _ingestion_error(_request: Request, exc: IngestionError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"code": exc.code, "message": str(exc), "details": exc.detail, "request_id": "n/a"})


@app.exception_handler(GraphEditError)
async def _edit_error(_request: Request, exc: GraphEditError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"code": exc.code, "message": str(exc), "details": {}, "request_id": "n/a"})


@app.get("/api/v1/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    """Liveness plus the identifiers a reviewer needs to trust the response."""
    bundle = _bundle()
    rulepack = _rulepack()
    return HealthResponse(
        status="ok",
        engine_version=ENGINE_VERSION,
        manifest_schema_version=MANIFEST_SCHEMA_VERSION,
        rulepack_id=rulepack.id,
        rulepack_hash=rulepack.content_hash,
        dataset_id=bundle.graph.version.id,
        dataset_provenance=bundle.graph.version.source.provenance_class.value,
        synthetic_data=bundle.graph.version.source.provenance_class.value
        in {"synthetic", "synthetic_fixture"},
        legal_applicability=rulepack.legal_applicability,
        disclaimer=rulepack.disclaimer,
    )


@app.get("/api/v1/projects", tags=["projects"])
def list_projects() -> dict:
    """The seeded demonstration project only. No other project is persisted yet."""
    bundle = _bundle()
    return {
        "projects": [
            {
                **bundle.project.model_dump(mode="json"),
                "graph_version_id": bundle.graph.version.id,
                "graph_content_hash": bundle.graph.content_hash,
                "node_count": len(bundle.graph.nodes),
                "edge_count": len(bundle.graph.edges),
                "evidence_count": len(bundle.graph.evidence_registry.all_records()),
                "notice": bundle.notice,
            }
        ]
    }


@app.get("/api/v1/projects/{project_id}/graph", tags=["projects"])
def get_graph(project_id: str) -> dict:
    bundle = _bundle()
    if project_id != bundle.project.id:
        return JSONResponse(
            status_code=404,
            content={"code": "PROJECT_NOT_FOUND", "message": f"unknown project {project_id!r}", "details": {}, "request_id": "n/a"},
        )
    return {
        "graph_version_id": bundle.graph.version.id,
        "content_hash": bundle.graph.content_hash,
        "basis": bundle.graph.version.basis.model_dump(mode="json"),
        "source": bundle.graph.version.source.model_dump(mode="json"),
        "nodes": [n.model_dump(mode="json") for n in bundle.graph.nodes],
        "edges": [e.model_dump(mode="json") for e in bundle.graph.edges],
        "evidence": [r.model_dump(mode="json") for r in bundle.graph.evidence_registry.all_records()],
        "unlinked_crossings": bundle.graph.unlinked_crossings(),
    }


@app.get("/api/v1/rulesets", tags=["rules"])
def list_rulesets() -> dict:
    rulepack = _rulepack()
    return {
        "rulepacks": [
            {
                "id": rulepack.id,
                "version": rulepack.version,
                "content_hash": rulepack.content_hash,
                "legal_applicability": rulepack.legal_applicability,
                "disclaimer": rulepack.disclaimer,
                "rules": [r.model_dump(mode="json") for r in rulepack.rules],
            }
        ],
        "profiles": [p.model_dump(mode="json") for p in DEMO_PROFILES],
    }


@app.get("/api/v1/scenarios/demo", tags=["scenarios"])
def get_demo_scenario() -> dict:
    bundle = _bundle()
    rulepack = _rulepack()
    scenario = _demo_scenario(bundle, rulepack)
    return {
        "scenario": scenario.model_dump(mode="json"),
        "evaluation_instant": DEMO_EVALUATION_INSTANT.isoformat(),
    }


@app.post("/api/v1/scenarios/demo/evaluate", tags=["scenarios"])
def evaluate_demo(payload: EvaluateRequest) -> dict:
    """Deterministic evaluation of the seeded scenario (in-memory; no persistence yet)."""
    bundle = _bundle()
    rulepack = _rulepack()
    scenario = _demo_scenario(bundle, rulepack)
    try:
        profile = next(p for p in DEMO_PROFILES if p.id == payload.profile_id)
    except StopIteration:
        return JSONResponse(
            status_code=404,
            content={
                "code": "PROFILE_NOT_FOUND",
                "message": f"unknown profile {payload.profile_id!r}",
                "details": {"known_profiles": [p.id for p in DEMO_PROFILES]},
                "request_id": "n/a",
            },
        )
    result = run_analysis(
        base_graph=bundle.graph,
        scenario=scenario,
        phase_id=payload.phase_id,
        profile_id=profile.id,
        rulepack=rulepack,
        profile=profile,
        as_of=DEMO_EVALUATION_INSTANT,
    )
    payload_dict = result.model_dump(mode="json")
    payload_dict["evaluation_instant"] = DEMO_EVALUATION_INSTANT.isoformat()
    payload_dict["engine_version"] = ENGINE_VERSION
    payload_dict["notice"] = bundle.notice
    return payload_dict