"""Resolved file locations and defaults shared by the API layer.

Kept in one module so that tests can point the application at a temporary
database without touching environment variables globally.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from detour_lab.domain.contracts import CoordinateBasis, DataSource
from detour_lab.domain.enums import ProvenanceClass

__all__ = [
    "database_path",
    "default_basis",
    "default_source",
    "interventions_path",
    "repo_root",
    "rulepack_path",
    "seed_dataset_path",
]

DEMO_PROJECT_ID = "demo-project-synthetic"
DEMO_SCENARIO_ID = "scn-demo-baseline"


@lru_cache(maxsize=1)
def repo_root() -> Path:
    """Repository root, resolved from this file's location."""
    return Path(__file__).resolve().parents[4]


def seed_dataset_path() -> Path:
    return repo_root() / "data" / "demo" / "synthetic_study_area.localplanar.json"


def rulepack_path() -> Path:
    return repo_root() / "apps" / "api" / "detour_lab" / "rules" / "rulepacks" / "DEMO_RULEPACK_NOT_LEGAL.v1.json"


def interventions_path() -> Path:
    """Bundled demonstration intervention library (immutable, versioned data)."""
    return repo_root() / "data" / "demo" / "interventions.demo.json"


def database_path() -> Path:
    """SQLite file location. Override with DETOUR_LAB_DB_PATH (used by tests)."""
    override = os.environ.get("DETOUR_LAB_DB_PATH")
    if override:
        return Path(override)
    data_dir = os.environ.get("DETOUR_LAB_DATA_DIR", "var")
    return repo_root() / data_dir / "detour_lab.sqlite3"


def default_basis() -> CoordinateBasis:
    """Placeholder basis for a project created before any dataset is imported."""
    return CoordinateBasis(
        kind="local_planar_meters",
        unit="m",
        local_origin_label="declared by the first imported dataset",
        crs_note="Placeholder: this project has no imported network yet.",
    )


def default_source() -> DataSource:
    return DataSource(
        name="undeclared",
        description="No dataset imported yet.",
        license="unspecified",
        provenance_class=ProvenanceClass.SYNTHETIC,
    )