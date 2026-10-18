"""Shared fixtures and small builders used by the domain test-suite.

Builders here deliberately construct *minimal* graphs so each test can prove one
behaviour in isolation instead of depending on the demo fixture.
"""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path

import pytest
from detour_lab.domain.contracts import (
    BaseGraphVersion,
    CoordinateBasis,
    DataSource,
    Edge,
    EvidenceRecord,
    Node,
    OriginDestination,
    Phase,
    Scenario,
    TemporaryEdge,
)
from detour_lab.domain.enums import EdgeType, NodeType, ProvenanceClass
from detour_lab.graph.model import PedestrianGraph
from detour_lab.ingestion.schema import SeedBundle, load_local_planar_dataset
from detour_lab.rules.engine import load_rulepack
from detour_lab.rules.profiles import DEMO_PROFILES, profile_by_id

REPO_ROOT = Path(__file__).resolve().parents[3]
RULEPACK_PATH = REPO_ROOT / "apps" / "api" / "detour_lab" / "rules" / "rulepacks" / "DEMO_RULEPACK_NOT_LEGAL.v1.json"
SEED_PATH = REPO_ROOT / "data" / "demo" / "synthetic_study_area.localplanar.json"

#: Fixed evaluation instant. Never ``datetime.now()``: freshness verdicts must be
#: reproducible, and the run records this value.
AS_OF = datetime(2026, 3, 1, tzinfo=UTC)

SYNTHETIC_SOURCE = DataSource(
    name="test synthetic source",
    description="Synthetic fixture for automated tests",
    license="Apache-2.0",
    provenance_class=ProvenanceClass.SYNTHETIC,
    version="test",
)

PLANAR_BASIS = CoordinateBasis(
    kind="local_planar_meters",
    unit="m",
    local_origin_label="test fixture origin (not a real place)",
    crs_note="Local planar metres for tests only.",
)


@pytest.fixture(scope="session")
def rulepack():
    return load_rulepack(RULEPACK_PATH)


@pytest.fixture(scope="session")
def profile_a():
    return profile_by_id("DEMO_PROFILE_MANUAL_WHEELCHAIR")


@pytest.fixture(scope="session")
def profile_b():
    return profile_by_id("DEMO_PROFILE_LIMITED_MOBILITY_WALKER")


@pytest.fixture(scope="session")
def all_profiles():
    return DEMO_PROFILES


@pytest.fixture(scope="session")
def seed() -> SeedBundle:
    return load_local_planar_dataset(SEED_PATH)


@pytest.fixture()
def demo_scenario(seed, rulepack) -> Scenario:
    return build_scenario(
        seed=seed,
        rulepack=rulepack,
        scenario_id="scn-test-base",
    )


def build_scenario(
    *,
    seed: SeedBundle,
    rulepack,
    scenario_id: str = "scn-test",
    phases: list[Phase] | None = None,
    origins_destinations: list[OriginDestination] | None = None,
    temporary_edges: list[TemporaryEdge] | None = None,
    edits: list | None = None,
    intervention_ids: list[str] | None = None,
) -> Scenario:
    return Scenario(
        id=scenario_id,
        name="test scenario",
        base_graph_version_id=seed.graph.version.id,
        rulepack_id=rulepack.id,
        rulepack_hash=rulepack.content_hash,
        profile_ids=[profile.id for profile in DEMO_PROFILES],
        phases=phases if phases is not None else list(seed.phases),
        origins_destinations=(
            origins_destinations if origins_destinations is not None else list(seed.origins_destinations)
        ),
        temporary_edges=temporary_edges if temporary_edges is not None else list(seed.temporary_edges),
        edits=edits or [],
        intervention_ids=intervention_ids or [],
    )


# --------------------------------------------------------------------------- builders


def node(node_id: str, x: float, y: float, node_type: NodeType = NodeType.JUNCTION) -> Node:
    return Node(id=node_id, x=x, y=y, node_type=node_type, provenance_class=ProvenanceClass.SYNTHETIC)


def edge(
    edge_id: str,
    u: str,
    v: str,
    nodes: dict[str, Node],
    *,
    edge_type: EdgeType = EdgeType.SIDEWALK,
    mid: tuple[float, float] | None = None,
) -> Edge:
    points = [(nodes[u].x, nodes[u].y)]
    if mid is not None:
        points.append(mid)
    points.append((nodes[v].x, nodes[v].y))
    length = sum(math.dist(points[i], points[i + 1]) for i in range(len(points) - 1))
    return Edge(
        id=edge_id,
        u=u,
        v=v,
        geometry=points,
        length_m=round(length, 6),
        edge_type=edge_type,
        provenance_class=ProvenanceClass.SYNTHETIC,
    )


def evidence(
    record_id: str,
    element_id: str,
    field: str,
    value,
    *,
    unit: str | None = None,
    observed_at: datetime | str | None = "2026-01-05T09:00:00Z",
    verification_status: str = "unverified",
    provenance_class: str = "synthetic",
    synthetic: bool = True,
    invalidated: bool = False,
) -> EvidenceRecord:
    return EvidenceRecord(
        id=record_id,
        element_id=element_id,
        field=field,
        value=value,
        unit=unit,
        method="test_fixture",
        source="synthetic test fixture",
        observed_at=observed_at,
        verification_status=verification_status,
        provenance_class=provenance_class,
        synthetic=synthetic,
        invalidated=invalidated,
    )


def accessible_evidence(prefix: str, element_id: str, *, width_mm: int = 2000, slope: float = 1.0, surface: str = "asphalt") -> list[EvidenceRecord]:
    """A full, satisfying evidence set (passes both demo profiles)."""
    return [
        evidence(f"{prefix}-width", element_id, "width_mm", width_mm, unit="mm"),
        evidence(f"{prefix}-slope", element_id, "slope_percent", slope, unit="percent"),
        evidence(f"{prefix}-surface", element_id, "surface", surface, unit=None),
    ]


def make_graph(nodes: list[Node], edges: list[Edge], records: list[EvidenceRecord] | None = None, *, version_id: str = "test-graph-v1") -> PedestrianGraph:
    version = BaseGraphVersion(
        id=version_id,
        basis=PLANAR_BASIS,
        nodes=nodes,
        edges=edges,
        evidence=records or [],
        source=SYNTHETIC_SOURCE,
    )
    return PedestrianGraph.from_version(version)


def simple_line_graph(
    *,
    length_m: float = 40.0,
    evidence_for_first: list[EvidenceRecord] | None = None,
    version_id: str = "test-line-v1",
) -> PedestrianGraph:
    """N1 -> N2 -> N3 with only the first edge evidenced."""
    nodes = [node("N1", 0.0, 0.0), node("N2", length_m, 0.0), node("N3", 2 * length_m, 0.0)]
    edges = [edge("E12", "N1", "N2", {n.id: n for n in nodes}), edge("E23", "N2", "N3", {n.id: n for n in nodes})]
    return make_graph(nodes, edges, evidence_for_first or accessible_evidence("EV1", "E12"), version_id=version_id)


def write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path