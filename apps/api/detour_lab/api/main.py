"""Application factory and process-wide wiring.

* one SQLite database (``DETOUR_LAB_DB_PATH`` or ``var/detour_lab.sqlite3``),
* migrations applied at startup,
* the synthetic demonstration project imported **idempotently**, so a fresh clone
  opens a working demo without a separate seeding step and without duplicating
  rows on restart.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from detour_lab import ENGINE_VERSION, MANIFEST_SCHEMA_VERSION, __version__
from detour_lab.api.state import (
    DEMO_PROJECT_ID,
    DEMO_SCENARIO_ID,
    database_path,
    default_basis,
    default_source,
    seed_dataset_path,
)
from detour_lab.api.v1.evidence import router as evidence_router
from detour_lab.api.v1.failure_lab import router as failure_lab_router
from detour_lab.api.v1.optimization import router as optimization_router
from detour_lab.api.v1.reports import router as reports_router
from detour_lab.api.v1.routers import router as v1_router
from detour_lab.domain.contracts import Scenario
from detour_lab.domain.units import UnitError
from detour_lab.graph.model import GraphValidationError
from detour_lab.ingestion.schema import IngestionError, load_local_planar_dataset
from detour_lab.persistence.db import Database
from detour_lab.persistence.repository import NotFoundError, OptimisticConflictError, Repository
from detour_lab.rules.engine import load_rulepack
from detour_lab.rules.profiles import DEMO_PROFILES
from detour_lab.scenarios.apply import GraphEditError

__all__ = ["app", "create_app"]


def _error(status_code: int, code: str, message: str, details: dict | None = None) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message, "details": details or {}, "request_id": "n/a"},
    )


def seed_demo(repository: Repository) -> dict[str, bool]:
    """Import the synthetic demo project and scenario exactly once."""
    created: dict[str, bool] = {"project": False, "scenario": False}
    try:
        repository.get_project(DEMO_PROJECT_ID)
    except NotFoundError:
        bundle = load_local_planar_dataset(seed_dataset_path())
        repository.import_dataset(
            project_id=DEMO_PROJECT_ID,
            project_name=bundle.project.name,
            graph=bundle.graph,
            origins_destinations=list(bundle.origins_destinations),
            phases=list(bundle.phases),
            temporary_edges=list(bundle.temporary_edges),
            notice=bundle.notice,
            study_area_description=bundle.project.study_area_description,
        )
        created["project"] = True

    try:
        repository.get_scenario(DEMO_SCENARIO_ID)
    except NotFoundError:
        bundle = load_local_planar_dataset(seed_dataset_path())
        rulepack = load_rulepack(Path(__file__).resolve().parents[1] / "rules" / "rulepacks" / "DEMO_RULEPACK_NOT_LEGAL.v1.json")
        repository.create_scenario(
            Scenario(
                id=DEMO_SCENARIO_ID,
                name="Seeded demonstration scenario (synthetic data)",
                base_graph_version_id=bundle.graph.version.id,
                rulepack_id=rulepack.id,
                rulepack_hash=rulepack.content_hash,
                profile_ids=[p.id for p in DEMO_PROFILES],
                phases=list(bundle.phases),
                origins_destinations=list(bundle.origins_destinations),
                temporary_edges=list(bundle.temporary_edges),
                note="Seeded scenario. Every attribute is a synthetic demonstration value.",
            ),
            project_id=DEMO_PROJECT_ID,
        )
        created["scenario"] = True
    return created


def create_app(database: str | Path | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI):
        db = Database(database or database_path())
        db.migrate()
        repository = Repository(db)
        application.state.database = db
        application.state.repository = repository
        application.state.seed_report = seed_demo(repository)
        yield

    application = FastAPI(
        title="DETOUR LAB API",
        version=__version__,
        description=(
            "Pre-construction pedestrian detour decision support and model verification. "
            "Verdicts are 'Pass in modeled checks' / 'Fail' / 'Unknown' / 'Not applicable'; they are "
            "never a legal, regulatory or safety certification. All bundled data is synthetic."
        ),
        lifespan=lifespan,
    )

    @application.exception_handler(RequestValidationError)
    async def _validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        """Field-level validation failures also use the flat envelope."""
        fields = [
            {
                "location": ".".join(str(part) for part in error.get("loc", ())),
                "message": error.get("msg", ""),
                "type": error.get("type", ""),
            }
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={
                "code": "REQUEST_VALIDATION_ERROR",
                "message": "The request body or parameters failed validation.",
                "details": {"fields": fields},
                "request_id": "n/a",
            },
        )

    @application.exception_handler(StarletteHTTPException)
    async def _http_error(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        """One flat error envelope for every failure mode.

        FastAPI would otherwise nest handler-raised errors under ``detail`` while
        custom handlers return a flat body. Clients should never have to care which
        produced the response (MASTER_PROMPT §9).
        """
        detail = exc.detail
        if isinstance(detail, dict) and {"code", "message"} <= set(detail):
            body = {
                "code": detail["code"],
                "message": detail["message"],
                "details": detail.get("details", {}),
                "request_id": detail.get("request_id", "n/a"),
            }
        else:
            body = {
                "code": f"HTTP_{exc.status_code}",
                "message": str(detail),
                "details": {},
                "request_id": "n/a",
            }
        return JSONResponse(status_code=exc.status_code, content=body)

    @application.exception_handler(NotFoundError)
    async def _not_found(_request: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"code": exc.code, "message": str(exc), "details": {}, "request_id": "n/a"},
        )

    @application.exception_handler(OptimisticConflictError)
    async def _conflict(_request: Request, exc: OptimisticConflictError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "code": exc.code,
                "message": str(exc),
                "details": {"expected_revision": exc.expected, "actual_revision": exc.actual},
                "request_id": "n/a",
            },
        )

    for error_type, code, status_code in (
        (IngestionError, "ingestion", 422),
        (GraphEditError, "graph_edit", 422),
        (GraphValidationError, "graph_validation", 422),
        (UnitError, "unit", 422),
    ):
        def _make(error_type=error_type, code=code, status_code=status_code):
            async def _handler(_request: Request, exc) -> JSONResponse:
                return JSONResponse(
                    status_code=status_code,
                    content={
                        "code": getattr(exc, "code", code),
                        "message": str(exc),
                        "details": getattr(exc, "detail", {}),
                        "request_id": "n/a",
                    },
                )

            return _handler

        application.add_exception_handler(error_type, _make())

    application.include_router(v1_router)
    application.include_router(optimization_router)
    application.include_router(evidence_router)
    application.include_router(failure_lab_router)
    application.include_router(reports_router)
    return application


app = create_app()

_ = (ENGINE_VERSION, MANIFEST_SCHEMA_VERSION, default_basis, default_source)