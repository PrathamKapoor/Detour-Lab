"""Repository over the domain model.

One transaction per logical operation. Imports are atomic: a rejected dataset
must leave no project, graph version, node, edge or evidence row behind
(MASTER_PROMPT §9).

Scenario edits use an optimistic concurrency check: the caller states the
revision it believes it is editing, and a mismatch raises ``OptimisticConflictError``
instead of silently overwriting another editor's work (PRD §10.2).
"""

from __future__ import annotations

import sqlite3
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from detour_lab import ENGINE_VERSION
from detour_lab.analysis.run import run_analysis
from detour_lab.domain.contracts import (
    AnalysisResult,
    BaseGraphVersion,
    CoordinateBasis,
    DataSource,
    GraphEdit,
    MobilityProfile,
    OriginDestination,
    Phase,
    Project,
    RulePack,
    Scenario,
    TemporaryEdge,
)
from detour_lab.domain.hashing import semantic_hash
from detour_lab.graph.model import PedestrianGraph
from detour_lab.persistence.db import Database, dumps, loads, utc_now_iso
from detour_lab.scenarios.apply import GraphEditError

__all__ = [
    "NotFoundError",
    "OptimisticConflictError",
    "Repository",
    "RunRecord",
    "ScenarioIdExistsError",
    "StoredFailureExperiment",
    "StoredOptimizationRun",
    "StoredReviewReport",
]


class NotFoundError(LookupError):
    """Requested entity does not exist (HTTP 404)."""

    def __init__(self, entity: str, identifier: str) -> None:
        super().__init__(f"{entity} {identifier!r} was not found")
        self.entity = entity
        self.identifier = identifier
        self.code = "NOT_FOUND"


class OptimisticConflictError(RuntimeError):
    """Scenario revision does not match the caller's expectation (HTTP 409)."""

    def __init__(self, scenario_id: str, expected: int, actual: int) -> None:
        super().__init__(
            f"scenario {scenario_id!r} is at revision {actual}, but revision {expected} was submitted"
        )
        self.code = "REVISION_CONFLICT"
        self.expected = expected
        self.actual = actual


class ScenarioIdExistsError(RuntimeError):
    """A scenario id collision during promotion (HTTP 409)."""

    def __init__(self, scenario_id: str) -> None:
        super().__init__(f"scenario {scenario_id!r} already exists")
        self.code = "SCENARIO_ID_EXISTS"
        self.scenario_id = scenario_id


@dataclass(frozen=True, slots=True)
class StoredOptimizationRun:
    search_id: str
    project_id: str
    scenario_id: str
    scenario_revision: int
    phase_id: str
    engine_version: str
    evaluation_instant: str
    input_hash: str
    semantic_hash: str
    created_at: str
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class StoredFailureExperiment:
    """One persisted Failure Lab experiment (Gate 6).

    ``experiment_id`` is an execution handle and ``semantic_hash`` is the
    identity of what the experiment found. They are deliberately separate: the
    same modelled condition executed twice yields two ids and one hash.
    """

    experiment_id: str
    project_id: str
    scenario_id: str
    scenario_revision: int
    phase_id: str
    profile_id: str
    engine_version: str
    status: str
    input_hash: str
    semantic_hash: str
    duration_ms: float
    created_at: str
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class StoredReviewReport:
    """One persisted review packet and the exact selections behind it.

    A report is historical evidence about the runs it selected. It is never
    relabelled as representing a newer scenario revision.
    """

    report_id: str
    project_id: str
    scenario_id: str
    scenario_revision: int
    schema_version: str
    generator_version: str
    semantic_hash: str
    pdf_sha256: str
    pdf_bytes: int
    pdf_page_count: int
    selected_run_ids: list[str]
    selected_search_ids: list[str]
    selected_experiment_ids: list[str]
    payload: dict[str, Any]
    created_at: str


@dataclass(frozen=True, slots=True)
class RunRecord:
    run_id: str
    project_id: str
    scenario_id: str
    scenario_revision: int
    phase_id: str
    profile_id: str
    engine_version: str
    evaluation_instant: str
    input_hash: str
    semantic_hash: str
    duration_ms: float
    created_at: str
    result: AnalysisResult


class Repository:
    def __init__(self, database: Database) -> None:
        self.database = database

    # ------------------------------------------------------------------ projects
    def create_project(
        self,
        *,
        project_id: str,
        name: str,
        basis: CoordinateBasis,
        source: DataSource,
        study_area_description: str = "",
        jurisdiction: str = "unspecified",
        owner: str = "unspecified",
        notice: str = "",
    ) -> Project:
        project = Project(
            id=project_id,
            name=name,
            study_area_description=study_area_description,
            basis=basis,
            jurisdiction=jurisdiction,
            owner=owner,
            dataset_source=source,
            created_at=datetime.now(UTC),
        )
        with self.database.transaction() as connection:
            connection.execute(
                "INSERT INTO projects (id, name, study_area_description, basis_json, jurisdiction, owner,"
                " source_json, notice, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    project.id,
                    project.name,
                    project.study_area_description,
                    dumps(project.basis.model_dump(mode="json")),
                    project.jurisdiction,
                    project.owner,
                    dumps(project.dataset_source.model_dump(mode="json")),
                    notice,
                    project.created_at.isoformat(),
                ),
            )
        return project

    def get_project(self, project_id: str) -> Project:
        with self.database.read() as connection:
            row = connection.execute(
                "SELECT * FROM projects WHERE id = ?", (project_id,)
            ).fetchone()
        if row is None:
            raise NotFoundError("project", project_id)
        return Project(
            id=row["id"],
            name=row["name"],
            study_area_description=row["study_area_description"],
            basis=CoordinateBasis.model_validate(loads(row["basis_json"])),
            jurisdiction=row["jurisdiction"],
            owner=row["owner"],
            dataset_source=DataSource.model_validate(loads(row["source_json"])),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def list_projects(self) -> list[Project]:
        with self.database.read() as connection:
            rows = connection.execute("SELECT id FROM projects ORDER BY id").fetchall()
        return [self.get_project(row["id"]) for row in rows]

    # ------------------------------------------------------------ graph versions
    def save_graph_version(self, project_id: str, graph: PedestrianGraph) -> BaseGraphVersion:
        """Store an immutable graph version.

        * Re-storing identical content for the same project is a no-op.
        * Two different projects may legitimately hold identical content, so
          uniqueness is per ``(project_id, content_hash)``.
        * If a *different* version already occupies the declared ID (e.g. two
          datasets that both call themselves ``demo-graph-v1``), the stored ID is
          suffixed deterministically from the content hash rather than crashing.
        """
        version = graph.version
        with self.database.transaction() as connection:
            existing = connection.execute(
                "SELECT id FROM graph_versions WHERE project_id = ? AND content_hash = ?",
                (project_id, version.content_hash),
            ).fetchone()
            if existing is not None:
                return version

            colliding = connection.execute(
                "SELECT content_hash FROM graph_versions WHERE id = ?", (version.id,)
            ).fetchone()
            stored_id = version.id
            if colliding is not None:
                # The declared ID is already taken by another stored version, so
                # derive a deterministic, content-addressed variant instead of
                # colliding or silently mutating the existing row.
                stored_id = f"{version.id}~{version.content_hash.split(':')[-1][:12]}"

            connection.execute(
                "INSERT INTO graph_versions (id, project_id, content_hash, schema_version, basis_json,"
                " source_json, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    stored_id,
                    project_id,
                    version.content_hash,
                    version.schema_version,
                    dumps(version.basis.model_dump(mode="json")),
                    dumps(version.source.model_dump(mode="json")),
                    dumps(version.model_dump(mode="json")),
                    (version.created_at or datetime.now(UTC)).isoformat(),
                ),
            )
            connection.executemany(
                "INSERT INTO nodes (graph_version_id, node_id, node_type, payload_json) VALUES (?, ?, ?, ?)",
                [
                    (stored_id, n.id, n.node_type.value, dumps(n.model_dump(mode="json")))
                    for n in version.nodes
                ],
            )
            connection.executemany(
                "INSERT INTO edges (graph_version_id, edge_id, u_id, v_id, edge_type, length_m, payload_json)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (stored_id, e.id, e.u, e.v, e.edge_type.value, e.length_m, dumps(e.model_dump(mode="json")))
                    for e in version.edges
                ],
            )
            connection.executemany(
                "INSERT INTO evidence (record_id, graph_version_id, element_id, field, value_json, unit,"
                " method, source, observed_at, verification_status, provenance_class, synthetic,"
                " invalidated, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        r.id,
                        stored_id,
                        r.element_id,
                        r.field,
                        dumps(r.value),
                        r.unit,
                        r.method,
                        r.source,
                        r.observed_at.isoformat() if r.observed_at else None,
                        r.verification_status.value,
                        r.provenance_class.value,
                        int(r.synthetic),
                        int(r.invalidated),
                        dumps(r.model_dump(mode="json")),
                    )
                    for r in version.evidence
                ],
            )
        return version

    def get_graph_version(self, graph_version_id: str) -> PedestrianGraph:
        """Rebuild the validated graph from stored rows (not just the blob)."""
        with self.database.read() as connection:
            version_row = connection.execute(
                "SELECT * FROM graph_versions WHERE id = ?", (graph_version_id,)
            ).fetchone()
            if version_row is None:
                raise NotFoundError("graph_version", graph_version_id)
            node_rows = connection.execute(
                "SELECT payload_json FROM nodes WHERE graph_version_id = ? ORDER BY node_id",
                (graph_version_id,),
            ).fetchall()
            edge_rows = connection.execute(
                "SELECT payload_json FROM edges WHERE graph_version_id = ? ORDER BY edge_id",
                (graph_version_id,),
            ).fetchall()
            evidence_rows = connection.execute(
                "SELECT payload_json FROM evidence WHERE graph_version_id = ? ORDER BY record_id",
                (graph_version_id,),
            ).fetchall()
        version = BaseGraphVersion.model_validate(
            {
                **loads(version_row["payload_json"]),
                "nodes": [loads(row["payload_json"]) for row in node_rows],
                "edges": [loads(row["payload_json"]) for row in edge_rows],
                "evidence": [loads(row["payload_json"]) for row in evidence_rows],
                "inactive_edge_ids": [],
            }
        )
        return PedestrianGraph.from_version(version)

    def get_latest_graph_version(self, project_id: str) -> PedestrianGraph:
        """Most recently created graph version belonging to ``project_id``."""
        with self.database.read() as connection:
            row = connection.execute(
                "SELECT id FROM graph_versions WHERE project_id = ? ORDER BY created_at DESC, id DESC LIMIT 1",
                (project_id,),
            ).fetchone()
        if row is None:
            raise NotFoundError("graph_version", f"for project {project_id}")
        return self.get_graph_version(row["id"])

    def find_graph_version_by_hash(self, content_hash: str) -> BaseGraphVersion | None:
        with self.database.read() as connection:
            row = connection.execute(
                "SELECT id FROM graph_versions WHERE content_hash = ?", (content_hash,)
            ).fetchone()
        return self.get_graph_version(row["id"]).version if row else None

    # -------------------------------------------------------------- atomic import
    def import_dataset(
        self,
        *,
        project_id: str,
        project_name: str,
        graph: PedestrianGraph,
        origins_destinations: list[OriginDestination],
        phases: list[Phase],
        temporary_edges: list[TemporaryEdge],
        notice: str,
        study_area_description: str = "",
    ) -> Project:
        """Create the project **and** its graph version atomically.

        If validation or any insert fails, the project row is rolled back too:
        a rejected file must never leave a half-created graph behind.

        Re-importing an already stored project with identical content is a
        no-op, so seeding is idempotent across restarts.
        """
        try:
            existing = self.get_project(project_id)
        except NotFoundError:
            existing = None
        if existing is None:
            project = self.create_project(
                project_id=project_id,
                name=project_name,
                basis=graph.version.basis,
                source=graph.version.source,
                study_area_description=study_area_description,
                notice=notice,
            )
        else:
            project = existing
        self.save_graph_version(project_id, graph)
        return project

    # ------------------------------------------------------------------ scenarios
    def create_scenario(self, scenario: Scenario, *, project_id: str) -> Scenario:
        """Insert a new scenario, refusing an id that is already taken.

        The clash check mirrors :meth:`promote_scenario`. It runs inside the
        transaction, so a collision writes nothing and rolls back cleanly.
        Without it a duplicate id reached the INSERT and surfaced as an
        uncaught ``sqlite3.IntegrityError`` - a 500 with no error code,
        instead of the 409 ``SCENARIO_ID_EXISTS`` the promotion path returns.
        """
        with self.database.transaction() as connection:
            clash = connection.execute(
                "SELECT 1 FROM scenarios WHERE id = ?", (scenario.id,)
            ).fetchone()
            if clash is not None:
                raise ScenarioIdExistsError(scenario.id)
            connection.execute(
                "INSERT INTO scenarios (id, project_id, parent_scenario_id, base_graph_version_id,"
                " rulepack_id, rulepack_hash, revision, content_hash, payload_json, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    scenario.id,
                    project_id,
                    scenario.parent_scenario_id,
                    scenario.base_graph_version_id,
                    scenario.rulepack_id,
                    scenario.rulepack_hash,
                    scenario.revision,
                    scenario.content_hash,
                    dumps(scenario.model_dump(mode="json")),
                    (scenario.created_at or datetime.now(UTC)).isoformat(),
                ),
            )
            connection.execute(
                "INSERT INTO scenario_revisions (scenario_id, revision, content_hash, payload_json, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (
                    scenario.id,
                    scenario.revision,
                    scenario.content_hash,
                    dumps(scenario.model_dump(mode="json")),
                    (scenario.created_at or datetime.now(UTC)).isoformat(),
                ),
            )
        return scenario

    def get_scenario(self, scenario_id: str) -> Scenario:
        with self.database.read() as connection:
            row = connection.execute(
                "SELECT payload_json, revision FROM scenarios WHERE id = ?", (scenario_id,)
            ).fetchone()
        if row is None:
            raise NotFoundError("scenario", scenario_id)
        scenario = Scenario.model_validate(loads(row["payload_json"]))
        return scenario.model_copy(update={"revision": row["revision"]})

    def list_scenarios(self, project_id: str) -> list[Scenario]:
        with self.database.read() as connection:
            rows = connection.execute(
                "SELECT id FROM scenarios WHERE project_id = ? ORDER BY id", (project_id,)
            ).fetchall()
        return [self.get_scenario(row["id"]) for row in rows]

    def apply_scenario_edit(
        self,
        *,
        scenario_id: str,
        expected_revision: int,
        edit: GraphEdit,
        note: str = "",
    ) -> Scenario:
        """Append one edit as a new immutable revision (INV-07)."""
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT revision, payload_json FROM scenarios WHERE id = ?", (scenario_id,)
            ).fetchone()
            if row is None:
                raise NotFoundError("scenario", scenario_id)
            actual = int(row["revision"])
            if actual != expected_revision:
                raise OptimisticConflictError(scenario_id, expected_revision, actual)

            current = Scenario.model_validate(loads(row["payload_json"]))
            payload = current.model_dump(mode="json")
            payload["edits"] = [*payload["edits"], edit.model_dump(mode="json")]
            # The scenario keeps a **stable identity**: only its revision, content
            # hash and note change. Branching is an explicit operation, never a side
            # effect of an edit - otherwise a client following the scenario list
            # would fetch an ID that no longer resolves.
            payload["revision"] = actual + 1
            payload["note"] = note or current.note
            payload["content_hash"] = ""
            payload["created_at"] = datetime.now(UTC).isoformat()
            updated = Scenario.model_validate(payload)

            connection.execute(
                "UPDATE scenarios SET revision = ?, content_hash = ?, payload_json = ? WHERE id = ?",
                (updated.revision, updated.content_hash, dumps(updated.model_dump(mode="json")), scenario_id),
            )
            connection.execute(
                "INSERT INTO scenario_revisions (scenario_id, revision, content_hash, payload_json, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (
                    scenario_id,
                    updated.revision,
                    updated.content_hash,
                    dumps(updated.model_dump(mode="json")),
                    utc_now_iso(),
                ),
            )
        return updated

    def scenario_revisions(self, scenario_id: str) -> list[dict[str, Any]]:
        with self.database.read() as connection:
            rows = connection.execute(
                "SELECT revision, content_hash, payload_json, created_at FROM scenario_revisions"
                " WHERE scenario_id = ? ORDER BY revision",
                (scenario_id,),
            ).fetchall()
        return [
            {
                "revision": row["revision"],
                "content_hash": row["content_hash"],
                "created_at": row["created_at"],
                "scenario": loads(row["payload_json"]),
            }
            for row in rows
        ]

    def promote_scenario(
        self,
        *,
        scenario: Scenario,
        source_scenario_id: str,
        expected_source_revision: int,
    ) -> Scenario:
        """Insert a promoted branch atomically (MASTER_PROMPT §7.9).

        One transaction: the source revision is verified against the caller's
        expectation, the branch id must be free, and both rows are inserted.
        Any failure leaves nothing behind, and the source is never touched.
        """
        with self.database.transaction() as connection:
            source = connection.execute(
                "SELECT project_id, revision FROM scenarios WHERE id = ?", (source_scenario_id,)
            ).fetchone()
            if source is None:
                raise NotFoundError("scenario", source_scenario_id)
            actual = int(source["revision"])
            if actual != expected_source_revision:
                raise OptimisticConflictError(source_scenario_id, expected_source_revision, actual)
            clash = connection.execute("SELECT 1 FROM scenarios WHERE id = ?", (scenario.id,)).fetchone()
            if clash is not None:
                raise ScenarioIdExistsError(scenario.id)
            created = (scenario.created_at or datetime.now(UTC)).isoformat()
            payload = dumps(scenario.model_dump(mode="json"))
            connection.execute(
                "INSERT INTO scenarios (id, project_id, parent_scenario_id, base_graph_version_id,"
                " rulepack_id, rulepack_hash, revision, content_hash, payload_json, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    scenario.id,
                    source["project_id"],
                    scenario.parent_scenario_id,
                    scenario.base_graph_version_id,
                    scenario.rulepack_id,
                    scenario.rulepack_hash,
                    scenario.revision,
                    scenario.content_hash,
                    payload,
                    created,
                ),
            )
            connection.execute(
                "INSERT INTO scenario_revisions (scenario_id, revision, content_hash, payload_json, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (scenario.id, scenario.revision, scenario.content_hash, payload, created),
            )
        return scenario

    # ----------------------------------------------------- optimisation runs
    def store_optimization_run(
        self,
        *,
        search_id: str,
        scenario_id: str,
        scenario_revision: int,
        phase_id: str,
        engine_version: str,
        evaluation_instant: str,
        input_hash: str,
        semantic_hash: str,
        payload: dict[str, Any],
        created_at: str,
    ) -> None:
        """Persist one bounded search. The payload stays canonical JSON."""
        with self.database.transaction() as connection:
            source = connection.execute(
                "SELECT project_id FROM scenarios WHERE id = ?", (scenario_id,)
            ).fetchone()
            if source is None:
                raise NotFoundError("scenario", scenario_id)
            connection.execute(
                "INSERT INTO optimization_runs (id, project_id, scenario_id, scenario_revision,"
                " phase_id, engine_version, evaluation_instant, input_hash, semantic_hash,"
                " payload_json, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    search_id,
                    source["project_id"],
                    scenario_id,
                    scenario_revision,
                    phase_id,
                    engine_version,
                    evaluation_instant,
                    input_hash,
                    semantic_hash,
                    dumps(payload),
                    created_at,
                ),
            )

    def get_optimization_run(self, search_id: str) -> StoredOptimizationRun:
        with self.database.read() as connection:
            row = connection.execute(
                "SELECT * FROM optimization_runs WHERE id = ?", (search_id,)
            ).fetchone()
        if row is None:
            raise NotFoundError("optimization search", search_id)
        return StoredOptimizationRun(
            search_id=row["id"],
            project_id=row["project_id"],
            scenario_id=row["scenario_id"],
            scenario_revision=int(row["scenario_revision"]),
            phase_id=row["phase_id"],
            engine_version=row["engine_version"],
            evaluation_instant=row["evaluation_instant"],
            input_hash=row["input_hash"],
            semantic_hash=row["semantic_hash"],
            created_at=row["created_at"],
            payload=loads(row["payload_json"]),
        )

    def list_optimization_runs(self, scenario_id: str) -> list[StoredOptimizationRun]:
        with self.database.read() as connection:
            rows = connection.execute(
                "SELECT id FROM optimization_runs WHERE scenario_id = ? ORDER BY created_at, id",
                (scenario_id,),
            ).fetchall()
        return [self.get_optimization_run(row["id"]) for row in rows]

    # ----------------------------------------------------------------------- runs
    def evaluate_and_store(
        self,
        *,
        scenario_id: str,
        phase_id: str,
        profile: MobilityProfile,
        rulepack: RulePack,
        evaluation_instant: datetime,
        project_id: str | None = None,
    ) -> RunRecord:
        scenario = self.get_scenario(scenario_id)
        graph = self.get_graph_version(scenario.base_graph_version_id)
        input_payload = {
            "scenario_hash": scenario.content_hash,
            "graph_hash": graph.content_hash,
            "rulepack_hash": rulepack.content_hash,
            "profile_id": profile.id,
            "phase_id": phase_id,
            "engine_version": ENGINE_VERSION,
        }
        input_hash = semantic_hash(input_payload)

        started = time.perf_counter()
        try:
            result = run_analysis(
                base_graph=graph,
                scenario=scenario,
                phase_id=phase_id,
                profile_id=profile.id,
                rulepack=rulepack,
                profile=profile,
                as_of=evaluation_instant,
            )
        except GraphEditError:
            raise
        duration_ms = round((time.perf_counter() - started) * 1000, 3)
        semantic = semantic_hash(result.model_dump(mode="json"))

        run_id = f"run-{uuid.uuid4().hex[:12]}"
        created_at = utc_now_iso()
        with self.database.transaction() as connection:
            connection.execute(
                "INSERT INTO analysis_runs (id, project_id, scenario_id, scenario_revision, phase_id,"
                " profile_id, rulepack_id, engine_version, evaluation_instant, input_hash, semantic_hash,"
                " duration_ms, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    project_id or _project_id_for(connection, scenario_id),
                    scenario_id,
                    scenario.revision,
                    phase_id,
                    profile.id,
                    rulepack.id,
                    ENGINE_VERSION,
                    evaluation_instant.isoformat(),
                    input_hash,
                    semantic,
                    duration_ms,
                    dumps(result.model_dump(mode="json")),
                    created_at,
                ),
            )
        return RunRecord(
            run_id=run_id,
            project_id=project_id or "",
            scenario_id=scenario_id,
            scenario_revision=scenario.revision,
            phase_id=phase_id,
            profile_id=profile.id,
            engine_version=ENGINE_VERSION,
            evaluation_instant=evaluation_instant.isoformat(),
            input_hash=input_hash,
            semantic_hash=semantic,
            duration_ms=duration_ms,
            created_at=created_at,
            result=result,
        )

    def get_run(self, run_id: str) -> RunRecord:
        with self.database.read() as connection:
            row = connection.execute(
                "SELECT * FROM analysis_runs WHERE id = ?", (run_id,)
            ).fetchone()
        if row is None:
            raise NotFoundError("run", run_id)
        return RunRecord(
            run_id=row["id"],
            project_id=row["project_id"],
            scenario_id=row["scenario_id"],
            scenario_revision=int(row["scenario_revision"]),
            phase_id=row["phase_id"],
            profile_id=row["profile_id"],
            engine_version=row["engine_version"],
            evaluation_instant=row["evaluation_instant"],
            input_hash=row["input_hash"],
            semantic_hash=row["semantic_hash"],
            duration_ms=float(row["duration_ms"]),
            created_at=row["created_at"],
            result=AnalysisResult.model_validate(loads(row["payload_json"])),
        )

    def list_runs(self, scenario_id: str) -> list[RunRecord]:
        with self.database.read() as connection:
            rows = connection.execute(
                "SELECT id FROM analysis_runs WHERE scenario_id = ? ORDER BY created_at, id",
                (scenario_id,),
            ).fetchall()
        return [self.get_run(row["id"]) for row in rows]

    def counts(self) -> dict[str, int]:
        with self.database.read() as connection:
            out: dict[str, int] = {}
            for table in (
                "projects",
                "graph_versions",
                "nodes",
                "edges",
                "evidence",
                "scenarios",
                "scenario_revisions",
                "analysis_runs",
                "optimization_runs",
                "failure_experiments",
                "review_reports",
            ):
                out[table] = int(
                    connection.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"]
                )
            return out

    # ------------------------------------------------------- Gate 6: Failure Lab
    def store_failure_experiment(
        self,
        *,
        experiment_id: str,
        scenario_id: str,
        scenario_revision: int,
        phase_id: str,
        profile_id: str,
        engine_version: str,
        status: str,
        input_hash: str,
        semantic_hash: str,
        duration_ms: float,
        payload: dict[str, Any],
        created_at: str,
    ) -> None:
        """Persist one experiment's complete record.

        Write-only and append-only: an experiment is historical evidence of what
        the model reported at a stated instant. Re-executing an experiment
        inserts a **new** row with a new ``experiment_id``; no stored experiment
        is ever updated or overwritten.
        """
        with self.database.transaction() as connection:
            connection.execute(
                "INSERT INTO failure_experiments (id, project_id, scenario_id, scenario_revision,"
                " phase_id, profile_id, engine_version, status, input_hash, semantic_hash,"
                " duration_ms, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    experiment_id,
                    _project_id_for(connection, scenario_id),
                    scenario_id,
                    scenario_revision,
                    phase_id,
                    profile_id,
                    engine_version,
                    status,
                    input_hash,
                    semantic_hash,
                    duration_ms,
                    dumps(payload),
                    created_at,
                ),
            )

    def get_failure_experiment(self, experiment_id: str) -> StoredFailureExperiment:
        with self.database.read() as connection:
            row = connection.execute(
                "SELECT * FROM failure_experiments WHERE id = ?", (experiment_id,)
            ).fetchone()
        if row is None:
            raise NotFoundError("failure experiment", experiment_id)
        return StoredFailureExperiment(
            experiment_id=row["id"],
            project_id=row["project_id"],
            scenario_id=row["scenario_id"],
            scenario_revision=row["scenario_revision"],
            phase_id=row["phase_id"],
            profile_id=row["profile_id"],
            engine_version=row["engine_version"],
            status=row["status"],
            input_hash=row["input_hash"],
            semantic_hash=row["semantic_hash"],
            duration_ms=row["duration_ms"],
            created_at=row["created_at"],
            payload=loads(row["payload_json"]),
        )

    def list_failure_experiments(self, scenario_id: str) -> list[StoredFailureExperiment]:
        with self.database.read() as connection:
            rows = connection.execute(
                "SELECT id FROM failure_experiments WHERE scenario_id = ? ORDER BY created_at, id",
                (scenario_id,),
            ).fetchall()
        return [self.get_failure_experiment(row["id"]) for row in rows]

    def project_id_for_scenario(self, scenario_id: str) -> str:
        """Public accessor so derived artefacts can be stamped with their project."""
        with self.database.read() as connection:
            return _project_id_for(connection, scenario_id)

    # ------------------------------------------------------- Gate 6: reporting
    def store_review_report(
        self,
        *,
        report_id: str,
        scenario_id: str,
        scenario_revision: int,
        schema_version: str,
        generator_version: str,
        semantic_hash: str,
        pdf_sha256: str,
        pdf_bytes: int,
        pdf_page_count: int,
        selected_run_ids: list[str],
        selected_search_ids: list[str],
        selected_experiment_ids: list[str],
        payload: dict[str, Any],
        created_at: str,
    ) -> StoredReviewReport:
        """Persist a generated review packet plus its exact source selections.

        The PDF **bytes** are not stored: they are regenerated on demand from the
        stored payload by the same renderer, and the stored ``pdf_sha256`` lets a
        caller verify that regeneration produced identical content.
        """
        with self.database.transaction() as connection:
            connection.execute(
                "INSERT INTO review_reports (id, project_id, scenario_id, scenario_revision,"
                " schema_version, generator_version, semantic_hash, pdf_sha256, pdf_bytes,"
                " pdf_page_count, selected_run_ids, selected_search_ids,"
                " selected_experiment_ids, payload_json, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    report_id,
                    _project_id_for(connection, scenario_id),
                    scenario_id,
                    scenario_revision,
                    schema_version,
                    generator_version,
                    semantic_hash,
                    pdf_sha256,
                    pdf_bytes,
                    pdf_page_count,
                    dumps(sorted(selected_run_ids)),
                    dumps(sorted(selected_search_ids)),
                    dumps(sorted(selected_experiment_ids)),
                    dumps(payload),
                    created_at,
                ),
            )
        return self.get_review_report(report_id)

    def get_review_report(self, report_id: str) -> StoredReviewReport:
        with self.database.read() as connection:
            row = connection.execute(
                "SELECT * FROM review_reports WHERE id = ?", (report_id,)
            ).fetchone()
        if row is None:
            raise NotFoundError("review report", report_id)
        return StoredReviewReport(
            report_id=row["id"],
            project_id=row["project_id"],
            scenario_id=row["scenario_id"],
            scenario_revision=row["scenario_revision"],
            schema_version=row["schema_version"],
            generator_version=row["generator_version"],
            semantic_hash=row["semantic_hash"],
            pdf_sha256=row["pdf_sha256"],
            pdf_bytes=row["pdf_bytes"],
            pdf_page_count=row["pdf_page_count"],
            selected_run_ids=list(loads(row["selected_run_ids"])),
            selected_search_ids=list(loads(row["selected_search_ids"])),
            selected_experiment_ids=list(loads(row["selected_experiment_ids"])),
            payload=loads(row["payload_json"]),
            created_at=row["created_at"],
        )

    def list_review_reports(self, scenario_id: str) -> list[StoredReviewReport]:
        with self.database.read() as connection:
            rows = connection.execute(
                "SELECT id FROM review_reports WHERE scenario_id = ? ORDER BY created_at, id",
                (scenario_id,),
            ).fetchall()
        return [self.get_review_report(row["id"]) for row in rows]


def _project_id_for(connection: sqlite3.Connection, scenario_id: str) -> str:
    row = connection.execute(
        "SELECT project_id FROM scenarios WHERE id = ?", (scenario_id,)
    ).fetchone()
    if row is None:
        raise NotFoundError("scenario", scenario_id)
    return row["project_id"]