"""Versioned HTTP routes (PRD §10.2).

Persistence, scenario branching with optimistic concurrency, deterministic
evaluation, and the canonical manifest endpoint. Errors use one envelope:

``{"code": ..., "message": ..., "details": {...}, "request_id": ...}``

with 400/404/409/422/500 semantics chosen per failure mode.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from detour_lab import ENGINE_VERSION
from detour_lab.analysis.phases import build_timeline, phase_graph_payload
from detour_lab.analysis.run import MAX_BLOCKER_PROBES
from detour_lab.domain.contracts import (
    CoordinateBasis,
    DataSource,
    GraphEdit,
    MobilityProfile,
    OriginDestination,
    Phase,
    RulePack,
    Scenario,
    TemporaryEdge,
)
from detour_lab.graph.model import PedestrianGraph
from detour_lab.ingestion.schema import IngestionError, load_local_planar_dataset
from detour_lab.persistence.repository import (
    NotFoundError,
    OptimisticConflictError,
    Repository,
    RunRecord,
    ScenarioIdExistsError,
)
from detour_lab.reporting.manifest import build_manifest
from detour_lab.rules.engine import load_rulepack
from detour_lab.rules.profiles import DEMO_PROFILES

router = APIRouter(prefix="/api/v1")

#: Fixed instant used by the seeded demonstration project so that replaying the
#: demo is reproducible. Real runs pass their own instant and it is recorded.
DEMO_EVALUATION_INSTANT = datetime(2026, 3, 1, tzinfo=UTC)


def _error(status_code: int, code: str, message: str, details: dict | None = None) -> HTTPException:
    """Single error envelope used by every route."""
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message, "details": details or {}, "request_id": "n/a"},
    )


def get_repository(request: Request) -> Repository:
    return request.app.state.repository


def run_summary(record: RunRecord) -> dict:
    """Run metadata shared by the run list and the phase timeline."""
    return {
        "id": record.run_id,
        "scenario_id": record.scenario_id,
        "scenario_revision": record.scenario_revision,
        "phase_id": record.phase_id,
        "profile_id": record.profile_id,
        "engine_version": record.engine_version,
        "evaluation_instant": record.evaluation_instant,
        "input_hash": record.input_hash,
        "semantic_hash": record.semantic_hash,
        "created_at": record.created_at,
    }


def _profile_or_404(profile_id: str) -> MobilityProfile:
    for profile in DEMO_PROFILES:
        if profile.id == profile_id:
            return profile
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "code": "PROFILE_NOT_FOUND",
            "message": f"unknown profile {profile_id!r}",
            "details": {"known_profiles": [p.id for p in DEMO_PROFILES]},
            "request_id": "n/a",
        },
    )


def _rulepack() -> RulePack:
    return request_rulepack()


def request_rulepack() -> RulePack:
    from detour_lab.api.state import rulepack_path

    return load_rulepack(rulepack_path())


class CreateProjectRequest(BaseModel):
    id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=300)
    study_area_description: str = ""
    jurisdiction: str = "unspecified"
    owner: str = "unspecified"
    notice: str = ""


class ImportRequest(BaseModel):
    """A local-planar dataset payload (the seeded demo format)."""

    dataset: dict = Field(description="detour-lab-local-planar/1.0 dataset object")
    graph_version_id_override: str | None = None


class ScenarioRequest(BaseModel):
    id: str = Field(min_length=1, max_length=120)
    name: str = ""
    parent_scenario_id: str | None = None
    base_graph_version_id: str | None = None
    rulepack_id: str | None = None
    profile_ids: list[str] | None = None
    phases: list[Phase] | None = None
    origins_destinations: list[OriginDestination] | None = None
    temporary_edges: list[TemporaryEdge] | None = None
    intervention_ids: list[str] = []
    note: str = ""


class ScenarioPatchRequest(BaseModel):
    expected_revision: int = Field(ge=1, description="revision the client believes it is editing")
    edits: list[GraphEdit] = Field(min_length=1)
    note: str = ""


class EvaluateRequest(BaseModel):
    profile_id: str = DEMO_PROFILES[0].id
    phase_id: str = "phase-1"
    evaluation_instant: datetime | None = Field(
        default=None,
        description=(
            "Instant at which evidence freshness is judged. Defaults to the current time for "
            "ad-hoc runs; the seeded demo uses a fixed instant. Always stored with the run."
        ),
    )


@router.get("/health")
def health(repository: Repository = Depends(get_repository)) -> dict:
    rulepack = request_rulepack()
    return {
        "status": "ok",
        "engine_version": ENGINE_VERSION,
        "rulepack_id": rulepack.id,
        "rulepack_hash": rulepack.content_hash,
        "legal_applicability": rulepack.legal_applicability,
        "database_schema_version": repository.database.applied_version(),
        "row_counts": repository.counts(),
        "max_blocker_probes": MAX_BLOCKER_PROBES,
        "profiles": [p.id for p in DEMO_PROFILES],
    }


@router.post("/projects", status_code=status.HTTP_201_CREATED)
def create_project(payload: CreateProjectRequest, repository: Repository = Depends(get_repository)) -> dict:
    try:
        existing = repository.get_project(payload.id)
    except NotFoundError:
        existing = None
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "PROJECT_EXISTS",
                "message": f"project {payload.id!r} already exists",
                "details": {},
                "request_id": "n/a",
            },
        )
    from detour_lab.api.state import default_basis, default_source

    project = repository.create_project(
        project_id=payload.id,
        name=payload.name,
        basis=default_basis(),
        source=default_source(),
        study_area_description=payload.study_area_description,
        jurisdiction=payload.jurisdiction,
        owner=payload.owner,
        notice=payload.notice,
    )
    return project.model_dump(mode="json")


@router.get("/projects")
def list_projects(repository: Repository = Depends(get_repository)) -> dict:
    return {"projects": [p.model_dump(mode="json") for p in repository.list_projects()]}


@router.post("/projects/{project_id}/imports", status_code=status.HTTP_201_CREATED)
def import_dataset(
    project_id: str, payload: ImportRequest, repository: Repository = Depends(get_repository)
) -> dict:
    """Validate and ingest a dataset atomically. A rejected file changes nothing."""
    import json
    import tempfile
    from pathlib import Path

    from detour_lab.persistence.db import SCHEMA_VERSION  # noqa: F401  (keeps schema coupling explicit)

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "import.json"
        path.write_text(json.dumps(payload.dataset), encoding="utf-8")
        try:
            bundle = load_local_planar_dataset(path)
        except IngestionError as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": exc.code,
                    "message": str(exc),
                    "details": exc.detail,
                    "request_id": "n/a",
                },
            ) from exc

    graph = bundle.graph
    if payload.graph_version_id_override:
        graph = PedestrianGraph.from_version(graph.version.model_copy(update={"id": payload.graph_version_id_override, "content_hash": ""}))
    project = repository.import_dataset(
        project_id=project_id,
        project_name=bundle.project.name,
        graph=graph,
        origins_destinations=list(bundle.origins_destinations),
        phases=list(bundle.phases),
        temporary_edges=list(bundle.temporary_edges),
        notice=bundle.notice,
        study_area_description=bundle.project.study_area_description,
    )
    return {
        "project": project.model_dump(mode="json"),
        "graph_version_id": graph.version.id,
        "graph_content_hash": graph.content_hash,
        "node_count": len(graph.nodes),
        "edge_count": len(graph.edges),
        "evidence_count": len(graph.evidence_registry.all_records()),
        "notice": bundle.notice,
    }


@router.get("/projects/{project_id}/graph")
def get_project_graph(project_id: str, repository: Repository = Depends(get_repository)) -> dict:
    project = repository.get_project(project_id)
    graph = repository.get_latest_graph_version(project_id)
    return {
        "project_id": project.id,
        "graph_version_id": graph.version.id,
        "content_hash": graph.content_hash,
        "basis": graph.version.basis.model_dump(mode="json"),
        "source": graph.version.source.model_dump(mode="json"),
        "nodes": [n.model_dump(mode="json") for n in graph.nodes],
        "edges": [e.model_dump(mode="json") for e in graph.edges],
        "evidence": [r.model_dump(mode="json") for r in graph.evidence_registry.all_records()],
        "unlinked_crossings": graph.unlinked_crossings(),
    }


@router.get("/projects/{project_id}/scenarios")
def list_project_scenarios(project_id: str, repository: Repository = Depends(get_repository)) -> dict:
    """Scenarios belonging to a project, for scenario selection and branching."""
    repository.get_project(project_id)
    scenarios = repository.list_scenarios(project_id)
    return {
        "project_id": project_id,
        "scenarios": [
            {
                "id": s.id,
                "name": s.name,
                "revision": s.revision,
                "content_hash": s.content_hash,
                "parent_scenario_id": s.parent_scenario_id,
                "base_graph_version_id": s.base_graph_version_id,
                "rulepack_id": s.rulepack_id,
                "phase_count": len(s.phases),
                "edit_count": len(s.edits),
                "note": s.note,
            }
            for s in scenarios
        ],
    }


@router.get("/scenarios/{scenario_id}/timeline")
def scenario_timeline(scenario_id: str, repository: Repository = Depends(get_repository)) -> dict:
    """Ordered construction timeline for a scenario revision.

    Ordering comes from ``Phase.order`` (the domain's only temporal authority);
    phases are never sorted by id or label. ``analysis.state`` is ``NOT_ANALYSED``
    when no run exists for the current revision - which is not a verdict.
    """
    scenario = repository.get_scenario(scenario_id)
    base_graph = repository.get_graph_version(scenario.base_graph_version_id)
    runs = [run_summary(r) for r in repository.list_runs(scenario_id)]
    entries = build_timeline(
        scenario,
        base_graph,
        runs=runs,
        profile_ids=tuple(scenario.profile_ids),
    )
    return {
        "scenario_id": scenario.id,
        "scenario_revision": scenario.revision,
        "scenario_content_hash": scenario.content_hash,
        "ordering": "phase_order",
        "phases": [
            {
                "phase_id": entry.phase_id,
                "order": entry.order,
                "label": entry.label,
                "notes": entry.notes,
                "boundary_convention": entry.boundary_convention,
                "closed_edge_ids": list(entry.closed_edge_ids),
                "temporary_edge_ids": list(entry.temporary_edge_ids),
                "phase_graph_id": entry.phase_graph_id,
                "phase_graph_hash": entry.phase_graph_hash,
                "warnings": list(entry.warnings),
                "analysis": entry.analysis,
            }
            for entry in entries
        ],
    }


@router.get("/scenarios/{scenario_id}/phases/{phase_id}/graph")
def scenario_phase_graph(
    scenario_id: str, phase_id: str, repository: Repository = Depends(get_repository)
) -> dict:
    """The authoritative materialised graph of one phase.

    Served so the client never reconstructs closures or temporary connections by
    toggling edges itself. An unknown phase id is rejected by the domain and
    surfaces as a flat 422 - never as "a phase with no closures".
    """
    scenario = repository.get_scenario(scenario_id)
    base_graph = repository.get_graph_version(scenario.base_graph_version_id)
    return phase_graph_payload(base_graph, scenario, phase_id)


@router.get("/scenarios/{scenario_id}")
def get_scenario(scenario_id: str, repository: Repository = Depends(get_repository)) -> dict:
    """Full scenario payload: phases, origins/destinations, edits and revision.

    Required by the planning UI before any edit can be composed; without it a
    client cannot know which revision to submit or which phases exist.
    """
    return repository.get_scenario(scenario_id).model_dump(mode="json")


@router.get("/scenarios/{scenario_id}/runs")
def list_scenario_runs(scenario_id: str, repository: Repository = Depends(get_repository)) -> dict:
    """Stored runs for a scenario, newest first, for baseline/after comparison."""
    repository.get_scenario(scenario_id)
    runs = repository.list_runs(scenario_id)
    return {
        "scenario_id": scenario_id,
        "runs": [
            {
                "id": r.run_id,
                "scenario_revision": r.scenario_revision,
                "phase_id": r.phase_id,
                "profile_id": r.profile_id,
                "engine_version": r.engine_version,
                "evaluation_instant": r.evaluation_instant,
                "input_hash": r.input_hash,
                "semantic_hash": r.semantic_hash,
                "created_at": r.created_at,
            }
            for r in sorted(runs, key=lambda r: (r.created_at, r.run_id), reverse=True)
        ],
    }


@router.post("/projects/{project_id}/scenarios", status_code=status.HTTP_201_CREATED)
def create_scenario(
    project_id: str, payload: ScenarioRequest, repository: Repository = Depends(get_repository)
) -> dict:
    graph = repository.get_latest_graph_version(project_id)
    rulepack = request_rulepack()
    scenario = Scenario(
        id=payload.id,
        name=payload.name,
        parent_scenario_id=payload.parent_scenario_id,
        base_graph_version_id=payload.base_graph_version_id or graph.version.id,
        rulepack_id=payload.rulepack_id or rulepack.id,
        rulepack_hash=rulepack.content_hash,
        profile_ids=payload.profile_ids or [p.id for p in DEMO_PROFILES],
        phases=payload.phases or [Phase(id="phase-1", order=1)],
        origins_destinations=payload.origins_destinations or [],
        temporary_edges=payload.temporary_edges or [],
        intervention_ids=payload.intervention_ids,
        note=payload.note,
        created_at=datetime.now(UTC),
    )
    try:
        repository.create_scenario(scenario, project_id=project_id)
    except ScenarioIdExistsError as exc:
        # The id is already taken. This is a conflict the caller can act on,
        # not a server fault, and it is the same 409 SCENARIO_ID_EXISTS the
        # apply-to-branch path returns.
        raise _error(
            409,
            exc.code,
            f"scenario id {exc.scenario_id!r} already exists; nothing was written",
            {"scenario_id": exc.scenario_id},
        ) from exc
    except KeyError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "UNKNOWN_REFERENCE",
                "message": f"scenario references an entity that does not exist: {exc}",
                "details": {},
                "request_id": "n/a",
            },
        ) from exc
    return repository.get_scenario(scenario.id).model_dump(mode="json")


@router.patch("/scenarios/{scenario_id}")
def patch_scenario(
    scenario_id: str, payload: ScenarioPatchRequest, repository: Repository = Depends(get_repository)
) -> dict:
    """Validate then apply edits as a new immutable revision.

    Validation runs against a *prospective* scenario before anything is written,
    so a malformed edit is rejected with 422 and never becomes a stored revision
    (MASTER_PROMPT §9 "apply validated edits").
    """
    from detour_lab.scenarios.apply import GraphEditError, build_phase_graph

    current = repository.get_scenario(scenario_id)
    graph = repository.get_graph_version(current.base_graph_version_id)
    prospective = Scenario.model_validate(
        {
            **current.model_dump(mode="json"),
            "edits": [
                *[e.model_dump(mode="json") for e in current.edits],
                *[e.model_dump(mode="json") for e in payload.edits],
            ],
            "content_hash": "",
        }
    )
    try:
        for phase in prospective.phases:
            build_phase_graph(graph, prospective, phase.id)
    except GraphEditError as exc:
        raise _error(422, exc.code, str(exc)) from exc

    updated = current
    for index, edit in enumerate(payload.edits):
        try:
            updated = repository.apply_scenario_edit(
                scenario_id=scenario_id,
                expected_revision=payload.expected_revision if index == 0 else updated.revision,
                edit=edit,
                note=payload.note,
            )
        except OptimisticConflictError as exc:
            raise _error(
                409,
                exc.code,
                str(exc),
                {"expected_revision": exc.expected, "actual_revision": exc.actual},
            ) from exc
    return updated.model_dump(mode="json")


@router.get("/scenarios/{scenario_id}/revisions")
def scenario_revisions(scenario_id: str, repository: Repository = Depends(get_repository)) -> dict:
    revisions = repository.scenario_revisions(scenario_id)
    return {
        "scenario_id": scenario_id,
        "revisions": [
            {"revision": r["revision"], "content_hash": r["content_hash"], "created_at": r["created_at"]}
            for r in revisions
        ],
    }


@router.post("/scenarios/{scenario_id}/evaluate", status_code=status.HTTP_201_CREATED)
def evaluate(
    scenario_id: str, payload: EvaluateRequest, repository: Repository = Depends(get_repository)
) -> dict:
    profile = _profile_or_404(payload.profile_id)
    rulepack = request_rulepack()
    instant = payload.evaluation_instant or datetime.now(UTC)
    from detour_lab.scenarios.apply import GraphEditError

    try:
        record = repository.evaluate_and_store(
            scenario_id=scenario_id,
            phase_id=payload.phase_id,
            profile=profile,
            rulepack=rulepack,
            evaluation_instant=instant,
        )
    except GraphEditError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": exc.code, "message": str(exc), "details": {}, "request_id": "n/a"},
        ) from exc
    return {
        "run": {
            "id": record.run_id,
            "scenario_id": record.scenario_id,
            "scenario_revision": record.scenario_revision,
            "phase_id": record.phase_id,
            "profile_id": record.profile_id,
            "engine_version": record.engine_version,
            "evaluation_instant": record.evaluation_instant,
            "input_hash": record.input_hash,
            "semantic_hash": record.semantic_hash,
            "created_at": record.created_at,
        },
        "result": record.result.model_dump(mode="json"),
    }


@router.get("/runs/{run_id}")
def get_run(run_id: str, repository: Repository = Depends(get_repository)) -> dict:
    record: RunRecord = repository.get_run(run_id)
    return {
        "run": {
            "id": record.run_id,
            "scenario_id": record.scenario_id,
            "scenario_revision": record.scenario_revision,
            "phase_id": record.phase_id,
            "profile_id": record.profile_id,
            "engine_version": record.engine_version,
            "evaluation_instant": record.evaluation_instant,
            "input_hash": record.input_hash,
            "semantic_hash": record.semantic_hash,
            "duration_ms": record.duration_ms,
            "created_at": record.created_at,
        },
        "result": record.result.model_dump(mode="json"),
    }


@router.get("/runs/{run_id}/manifest")
def get_manifest(run_id: str, repository: Repository = Depends(get_repository)) -> dict:
    record = repository.get_run(run_id)
    scenario = repository.get_scenario(record.scenario_id)
    graph = repository.get_graph_version(scenario.base_graph_version_id)
    rulepack = request_rulepack()
    profile = _profile_or_404(record.profile_id)
    return build_manifest(
        record=record,
        graph=graph,
        rulepack=rulepack,
        profile=profile,
        scenario=scenario,
        dataset_notice=graph.version.source.description,
    )


@router.get("/rulesets")
def list_rulesets() -> dict:
    rulepack = request_rulepack()
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


def _unused(*args, **kwargs) -> None:  # pragma: no cover - keeps optional imports explicit
    _ = (CoordinateBasis, DataSource, _rulepack)