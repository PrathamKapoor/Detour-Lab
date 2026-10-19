"""SQLite persistence: explicit migrations, foreign keys, transactional writes.

Design rules enforced here (MASTER_PROMPT §9):

* Every statement uses **parameterised SQL**. Values are never interpolated.
* Schema changes are ordered, numbered migrations recorded in
  ``schema_migrations``; a database reports its applied version.
* Foreign keys are enforced (``PRAGMA foreign_keys=ON``), and every write that
  touches more than one table runs inside a single transaction, so a rejected
  import leaves no half-created graph.
* Canonical payloads *and* their hashes are stored next to the structured rows so
  a run can be replayed and re-verified byte-for-byte after a restart.
* No secret tokens are ever written; the demo dataset contains none.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

__all__ = ["SCHEMA_VERSION", "Database", "MigrationError", "utc_now_iso"]

SCHEMA_VERSION = 3


class MigrationError(RuntimeError):
    """Raised when the database schema cannot be created or upgraded."""


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    name: str
    statements: tuple[str, ...]


MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        version=1,
        name="initial_detour_lab_schema",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version    INTEGER PRIMARY KEY,
                name       TEXT NOT NULL,
                applied_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS projects (
                id                    TEXT PRIMARY KEY,
                name                  TEXT NOT NULL,
                study_area_description TEXT NOT NULL DEFAULT '',
                basis_json            TEXT NOT NULL,
                jurisdiction          TEXT NOT NULL DEFAULT 'unspecified',
                owner                 TEXT NOT NULL DEFAULT 'unspecified',
                source_json           TEXT NOT NULL,
                notice                TEXT NOT NULL DEFAULT '',
                created_at            TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS graph_versions (
                id             TEXT PRIMARY KEY,
                project_id     TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                content_hash   TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                basis_json     TEXT NOT NULL,
                source_json    TEXT NOT NULL,
                payload_json   TEXT NOT NULL,
                created_at     TEXT NOT NULL,
                UNIQUE (project_id, content_hash)
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_graph_versions_project ON graph_versions(project_id)",
            """
            CREATE TABLE IF NOT EXISTS nodes (
                graph_version_id TEXT NOT NULL REFERENCES graph_versions(id) ON DELETE CASCADE,
                node_id          TEXT NOT NULL,
                node_type        TEXT NOT NULL,
                payload_json     TEXT NOT NULL,
                PRIMARY KEY (graph_version_id, node_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS edges (
                graph_version_id TEXT NOT NULL REFERENCES graph_versions(id) ON DELETE CASCADE,
                edge_id          TEXT NOT NULL,
                u_id             TEXT NOT NULL,
                v_id             TEXT NOT NULL,
                edge_type        TEXT NOT NULL,
                length_m         REAL NOT NULL,
                payload_json     TEXT NOT NULL,
                PRIMARY KEY (graph_version_id, edge_id),
                FOREIGN KEY (graph_version_id, u_id) REFERENCES nodes(graph_version_id, node_id),
                FOREIGN KEY (graph_version_id, v_id) REFERENCES nodes(graph_version_id, node_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS evidence (
                record_id           TEXT NOT NULL,
                graph_version_id    TEXT NOT NULL REFERENCES graph_versions(id) ON DELETE CASCADE,
                element_id          TEXT NOT NULL,
                field               TEXT NOT NULL,
                value_json          TEXT,
                unit                TEXT,
                method              TEXT NOT NULL,
                source              TEXT NOT NULL,
                observed_at         TEXT,
                verification_status TEXT NOT NULL,
                provenance_class    TEXT NOT NULL,
                synthetic           INTEGER NOT NULL DEFAULT 1,
                invalidated         INTEGER NOT NULL DEFAULT 0,
                payload_json        TEXT NOT NULL,
                PRIMARY KEY (graph_version_id, record_id)
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_evidence_element ON evidence(graph_version_id, element_id, field)",
            """
            CREATE TABLE IF NOT EXISTS scenarios (
                id                      TEXT PRIMARY KEY,
                project_id              TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                parent_scenario_id      TEXT REFERENCES scenarios(id),
                base_graph_version_id   TEXT NOT NULL REFERENCES graph_versions(id),
                rulepack_id             TEXT NOT NULL,
                rulepack_hash           TEXT NOT NULL,
                revision                INTEGER NOT NULL,
                content_hash            TEXT NOT NULL,
                payload_json            TEXT NOT NULL,
                created_at              TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS scenario_revisions (
                scenario_id  TEXT NOT NULL REFERENCES scenarios(id) ON DELETE CASCADE,
                revision     INTEGER NOT NULL,
                content_hash TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at   TEXT NOT NULL,
                PRIMARY KEY (scenario_id, revision)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS analysis_runs (
                id                  TEXT PRIMARY KEY,
                project_id          TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                scenario_id         TEXT NOT NULL REFERENCES scenarios(id) ON DELETE CASCADE,
                scenario_revision   INTEGER NOT NULL,
                phase_id            TEXT NOT NULL,
                profile_id          TEXT NOT NULL,
                rulepack_id         TEXT NOT NULL,
                engine_version      TEXT NOT NULL,
                evaluation_instant  TEXT NOT NULL,
                input_hash          TEXT NOT NULL,
                semantic_hash       TEXT NOT NULL,
                duration_ms         REAL NOT NULL,
                payload_json        TEXT NOT NULL,
                created_at          TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_runs_scenario ON analysis_runs(scenario_id, created_at)",
        ),
    ),
    Migration(
        version=2,
        name="bounded_optimization_runs",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS optimization_runs (
                id                  TEXT PRIMARY KEY,
                project_id          TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                scenario_id         TEXT NOT NULL REFERENCES scenarios(id) ON DELETE CASCADE,
                scenario_revision   INTEGER NOT NULL,
                phase_id            TEXT NOT NULL,
                engine_version      TEXT NOT NULL,
                evaluation_instant  TEXT NOT NULL,
                input_hash          TEXT NOT NULL,
                semantic_hash       TEXT NOT NULL,
                payload_json        TEXT NOT NULL,
                created_at          TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_optimization_runs_scenario"
            " ON optimization_runs(scenario_id, created_at)",
        ),
    ),
    Migration(
        version=3,
        name="failure_lab_experiments_and_reports",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS failure_experiments (
                id                  TEXT PRIMARY KEY,
                project_id          TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                scenario_id         TEXT NOT NULL REFERENCES scenarios(id) ON DELETE CASCADE,
                scenario_revision   INTEGER NOT NULL,
                phase_id            TEXT NOT NULL,
                profile_id          TEXT NOT NULL,
                engine_version      TEXT NOT NULL,
                status              TEXT NOT NULL,
                input_hash          TEXT NOT NULL,
                semantic_hash       TEXT NOT NULL,
                duration_ms         REAL NOT NULL,
                payload_json        TEXT NOT NULL,
                created_at          TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_failure_experiments_scenario"
            " ON failure_experiments(scenario_id, created_at)",
            """
            CREATE TABLE IF NOT EXISTS review_reports (
                id                  TEXT PRIMARY KEY,
                project_id          TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                scenario_id         TEXT NOT NULL REFERENCES scenarios(id) ON DELETE CASCADE,
                scenario_revision   INTEGER NOT NULL,
                schema_version      TEXT NOT NULL,
                generator_version   TEXT NOT NULL,
                semantic_hash       TEXT NOT NULL,
                pdf_sha256          TEXT NOT NULL,
                pdf_bytes           INTEGER NOT NULL,
                pdf_page_count      INTEGER NOT NULL,
                selected_run_ids    TEXT NOT NULL,
                selected_search_ids TEXT NOT NULL,
                selected_experiment_ids TEXT NOT NULL,
                payload_json        TEXT NOT NULL,
                created_at          TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_review_reports_scenario"
            " ON review_reports(scenario_id, created_at)",
        ),
    ),
)


class Database:
    """Thin, explicit SQLite wrapper. No ORM, no dynamic SQL."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """One transaction; any exception rolls the whole thing back."""
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    @contextmanager
    def read(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            yield connection
        finally:
            connection.close()

    def applied_version(self) -> int:
        with self.read() as connection:
            try:
                row = connection.execute("SELECT MAX(version) AS v FROM schema_migrations").fetchone()
            except sqlite3.OperationalError:
                return 0
            return int(row["v"]) if row and row["v"] is not None else 0

    def migrate(self) -> list[str]:
        """Apply pending migrations in order. Returns the names applied."""
        applied: list[str] = []
        current = self.applied_version()
        for migration in sorted(MIGRATIONS, key=lambda m: m.version):
            if migration.version <= current:
                continue
            try:
                with self.transaction() as connection:
                    for statement in migration.statements:
                        connection.execute(statement)
                    connection.execute(
                        "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                        (migration.version, migration.name, utc_now_iso()),
                    )
            except sqlite3.Error as exc:  # pragma: no cover - surfaced, not swallowed
                raise MigrationError(f"migration {migration.version} failed: {exc}") from exc
            applied.append(migration.name)
        return applied

    def reset(self) -> None:  # pragma: no cover - developer utility
        """Delete the database file. Only used by scripts/seed and tests."""
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(str(self.path) + suffix)
            if candidate.exists():
                candidate.unlink()


def dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def loads(payload: str) -> Any:
    return json.loads(payload)