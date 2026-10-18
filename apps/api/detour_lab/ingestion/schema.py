"""Dataset ingestion with explicit, validated coordinate semantics.

Two supported inputs, and they are deliberately *different* formats:

``detour-lab-local-planar/1.0``
    The seeded synthetic schematic, in local planar **metres**. It is explicitly
    **not** RFC 7946 GeoJSON and carries an in-file notice saying so.

RFC 7946 GeoJSON (WGS 84 longitude/latitude)
    Accepted from external sources. Per MASTER_PROMPT §4, degree arithmetic is
    never used for metres: a documented local equirectangular projection about the
    dataset centroid (or an explicitly declared projected CRS note) produces the
    planar metre coordinates used for length/width computation.

Either way the result is a validated, content-addressed
:class:`~detour_lab.graph.model.PedestrianGraph`.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from detour_lab.domain.contracts import (
    BaseGraphVersion,
    CoordinateBasis,
    DataSource,
    Edge,
    EvidenceRecord,
    Node,
    OriginDestination,
    Phase,
    Project,
    TemporaryEdge,
)
from detour_lab.domain.enums import EdgeType, NodeType, ProvenanceClass
from detour_lab.domain.units import parse_timestamp
from detour_lab.graph.model import PedestrianGraph

__all__ = ["EARTH_RADIUS_M", "IngestionError", "SeedBundle", "load_local_planar_dataset", "load_rfc7946_geojson"]

#: IUGG mean Earth radius. Documented approximation, not a survey measurement.
EARTH_RADIUS_M = 6_371_008.8

LOCAL_PLANAR_SCHEMA = "detour-lab-local-planar/1.0"


class IngestionError(ValueError):
    """Rejected dataset with an actionable, field-level message."""

    def __init__(self, message: str, *, code: str, detail: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.detail = detail or {}


@dataclass(frozen=True, slots=True)
class SeedBundle:
    """Everything needed to open the demo project."""

    project: Project
    graph: PedestrianGraph
    origins_destinations: tuple[OriginDestination, ...]
    phases: tuple[Phase, ...]
    temporary_edges: tuple[TemporaryEdge, ...]
    notice: str


def _require(payload: dict[str, Any], key: str, kind: type, *, where: str) -> Any:
    if key not in payload:
        raise IngestionError(f"missing required member {key!r} in {where}", code="MISSING_FIELD")
    value = payload[key]
    if not isinstance(value, kind):
        raise IngestionError(
            f"member {key!r} in {where} must be {kind.__name__}, got {type(value).__name__}",
            code="INVALID_TYPE",
        )
    return value


def _evidence_from(payload: dict[str, Any], *, default_element: str | None = None) -> EvidenceRecord:
    element_id = payload.get("element_id", default_element)
    if not element_id:
        raise IngestionError(
            f"evidence record {payload.get('id')!r} has no element_id", code="MISSING_FIELD"
        )
    observed = payload.get("observed_at")
    return EvidenceRecord(
        id=_require(payload, "id", str, where="evidence record"),
        element_id=str(element_id),
        field=_require(payload, "field", str, where="evidence record"),
        value=payload.get("value"),
        unit=payload.get("unit"),
        method=_require(payload, "method", str, where="evidence record"),
        source=_require(payload, "source", str, where="evidence record"),
        source_url=payload.get("source_url"),
        observed_at=parse_timestamp(observed, field="observed_at") if observed else None,
        verification_status=payload.get("verification_status", "unverified"),
        quality=payload.get("quality", "medium"),
        reviewer=payload.get("reviewer"),
        invalidated=bool(payload.get("invalidated", False)),
        provenance_class=payload.get("provenance_class", ProvenanceClass.SYNTHETIC.value),
        synthetic=bool(payload.get("synthetic", True)),
        note=payload.get("note", ""),
    )


def load_local_planar_dataset(path: str | Path) -> SeedBundle:
    """Load the synthetic seeded study area."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    schema = _require(raw, "schema", str, where="dataset")
    if schema != LOCAL_PLANAR_SCHEMA:
        raise IngestionError(
            f"unsupported schema {schema!r}; expected {LOCAL_PLANAR_SCHEMA!r}", code="UNSUPPORTED_SCHEMA"
        )
    notice = _require(raw, "NOTICE", str, where="dataset")
    basis_payload = dict(_require(raw, "basis", dict, where="dataset"))
    if basis_payload.get("kind") != "local_planar_meters":
        raise IngestionError(
            "local planar datasets must declare kind='local_planar_meters'",
            code="INVALID_CRS",
        )
    if not basis_payload.get("local_origin_label"):
        raise IngestionError(
            "local planar datasets must declare local_origin_label so the coordinates cannot be "
            "mistaken for a real georeferenced location (MASTER_PROMPT geographic caution)",
            code="MISSING_FIELD",
        )
    basis = CoordinateBasis.model_validate(basis_payload)

    nodes = [
        Node.model_validate(item) for item in _require(raw, "nodes", list, where="dataset")
    ]
    nodes_by_id = {node.id: node for node in nodes}
    edges = [
        _edge_from(item, nodes_by_id) for item in _require(raw, "edges", list, where="dataset")
    ]
    evidence = [
        _evidence_from(item) for item in raw.get("evidence", [])
    ]
    unknown_elements = sorted(
        {r.element_id for r in evidence} - {n.id for n in nodes} - {e.id for e in edges}
    )
    if unknown_elements:
        raise IngestionError(
            f"evidence references unknown element(s) {unknown_elements}",
            code="UNKNOWN_NODE_REFERENCE",
            detail={"element_ids": unknown_elements},
        )

    source = DataSource.model_validate(_require(raw, "dataset", dict, where="dataset"))
    version = BaseGraphVersion(
        id=_require(raw, "graph_version_id", str, where="dataset"),
        basis=basis,
        nodes=nodes,
        edges=edges,
        evidence=evidence,
        source=source,
    )
    graph = PedestrianGraph.from_version(version)

    project_payload = _require(raw, "project", dict, where="dataset")
    project = Project(
        id="demo-project-synthetic",
        name=project_payload["name"],
        study_area_description=project_payload.get("study_area_description", ""),
        basis=basis,
        jurisdiction=project_payload.get("jurisdiction", "unspecified"),
        owner=project_payload.get("owner", "unspecified"),
        dataset_source=source,
    )
    origins = tuple(
        OriginDestination.model_validate(item)
        for item in _require(raw, "origins_destinations", list, where="dataset")
    )
    phases = tuple(Phase.model_validate(item) for item in _require(raw, "phases", list, where="dataset"))
    temporary = tuple(_temporary_edge(item, {n.id: n for n in nodes}) for item in raw.get("temporary_edges", []))
    return SeedBundle(
        project=project,
        graph=graph,
        origins_destinations=origins,
        phases=phases,
        temporary_edges=temporary,
        notice=notice,
    )


def _edge_from(payload: dict[str, Any], nodes: dict[str, Node]) -> Edge:
    """Build an edge, deriving geometry from its endpoint nodes when omitted.

    The declared length is kept as the source value, but a declared length that
    contradicts the node geometry by more than a millimetre is rejected rather
    than silently corrected.
    """
    edge_id = _require(payload, "id", str, where="edge")
    u_id = _require(payload, "u", str, where="edge")
    v_id = _require(payload, "v", str, where="edge")
    for endpoint in (u_id, v_id):
        if endpoint not in nodes:
            raise IngestionError(
                f"edge {edge_id!r} references unknown node {endpoint!r}", code="UNKNOWN_NODE_REFERENCE"
            )
    u, v = nodes[u_id], nodes[v_id]
    if u_id == v_id:
        raise IngestionError(f"edge {edge_id!r} is a self-loop", code="SELF_LOOP")
    geometry = (
        [(float(x), float(y)) for x, y in _require(payload, "geometry", list, where="edge")]
        if payload.get("geometry")
        else [(u.x, u.y), (v.x, v.y)]
    )
    if geometry[0] != (u.x, u.y) or geometry[-1] != (v.x, v.y):
        raise IngestionError(
            f"edge {edge_id!r} geometry endpoints must coincide with nodes {u_id!r} and {v_id!r}",
            code="GEOMETRY_ENDPOINT_MISMATCH",
        )
    geometric_length = sum(
        math.dist(geometry[i], geometry[i + 1]) for i in range(len(geometry) - 1)
    )
    declared_length = payload.get("length_m")
    if declared_length is None:
        length = geometric_length
    else:
        length = float(declared_length)
        if abs(length - geometric_length) > 0.001:
            raise IngestionError(
                f"edge {edge_id!r} declares length {length} m but its geometry is {geometric_length:.3f} m",
                code="LENGTH_GEOMETRY_MISMATCH",
                detail={"declared_length_m": length, "geometric_length_m": geometric_length},
            )
    return Edge(
        id=edge_id,
        u=u_id,
        v=v_id,
        geometry=geometry,
        length_m=round(length, 6),
        edge_type=EdgeType(payload.get("edge_type", EdgeType.SIDEWALK.value)),
        name=payload.get("name", ""),
        provenance_class=ProvenanceClass(payload.get("provenance_class", ProvenanceClass.SYNTHETIC.value)),
    )


def _temporary_edge(payload: dict[str, Any], nodes: dict[str, Node]) -> TemporaryEdge:
    """Temporary edges inherit node coordinates; their own measurements must be explicit."""
    temp_id = _require(payload, "id", str, where="temporary edge")
    u_id = _require(payload, "u", str, where="temporary edge")
    v_id = _require(payload, "v", str, where="temporary edge")
    for endpoint in (u_id, v_id):
        if endpoint not in nodes:
            raise IngestionError(
                f"temporary edge {temp_id!r} references unknown node {endpoint!r}",
                code="UNKNOWN_NODE_REFERENCE",
            )
    u, v = nodes[u_id], nodes[v_id]
    length = float(_require(payload, "length_m", int | float, where="temporary edge"))
    return TemporaryEdge(
        id=temp_id,
        u=u_id,
        v=v_id,
        geometry=[(u.x, u.y), (v.x, v.y)],
        length_m=length,
        edge_type=payload.get("edge_type", EdgeType.TEMPORARY_PATH.value),
        name=payload.get("name", ""),
        evidence=[
            _evidence_from(item, default_element=temp_id) for item in payload.get("evidence", [])
        ],
        constructible_in_field=bool(payload.get("constructible_in_field", False)),
    )


def load_rfc7946_geojson(
    payload: dict[str, Any],
    *,
    source: DataSource,
    version_id: str,
) -> PedestrianGraph:
    """Import a genuine RFC 7946 GeoJSON network.

    Requirements enforced here:

    * ``FeatureCollection`` with an explicit feature array;
    * coordinates inside the WGS 84 valid range (degree values that look like
      local metres are rejected rather than silently reinterpreted);
    * every edge feature names existing node features by ID, so connectivity is
      declared, never inferred from geometry that merely crosses;
    * metre lengths are computed through a recorded projection, never in degrees.
    """
    if payload.get("type") != "FeatureCollection":
        raise IngestionError(
            f"expected a GeoJSON FeatureCollection, got {payload.get('type')!r}",
            code="UNSUPPORTED_SCHEMA",
        )
    features = payload.get("features")
    if not isinstance(features, list):
        raise IngestionError("FeatureCollection requires a 'features' array", code="INVALID_TYPE")

    nodes: dict[str, tuple[float, float]] = {}
    edges: list[dict[str, Any]] = []
    for index, feature in enumerate(features):
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise IngestionError(f"features[{index}] is not a GeoJSON Feature", code="INVALID_TYPE")
        properties = feature.get("properties") or {}
        geometry = feature.get("geometry") or {}
        feature_id = properties.get("id") or feature.get("id")
        if not feature_id:
            raise IngestionError(
                f"features[{index}] has no properties.id; stable IDs are required",
                code="MISSING_FIELD",
            )
        coordinates = geometry.get("coordinates")
        match geometry.get("type"):
            case "Point":
                node_coords = _validate_lon_lat(coordinates, where=f"features[{index}].geometry")
                nodes[str(feature_id)] = node_coords
            case "LineString":
                if not properties.get("from") or not properties.get("to"):
                    raise IngestionError(
                        f"LineString feature {feature_id!r} must declare properties.from and properties.to "
                        "node IDs; connectivity is never inferred from crossing geometry",
                        code="MISSING_FIELD",
                    )
                line = [
                    _validate_lon_lat(point, where=f"features[{index}].geometry.coordinates")
                    for point in coordinates
                ]
                edges.append({"id": str(feature_id), "from": properties["from"], "to": properties["to"], "line": line})
            case other:
                raise IngestionError(
                    f"features[{index}] geometry type {other!r} is not supported; use Point or LineString",
                    code="UNSUPPORTED_GEOMETRY",
                )

    for edge in edges:
        for endpoint in (edge["from"], edge["to"]):
            if str(endpoint) not in nodes:
                raise IngestionError(
                    f"edge {edge['id']!r} references unknown node feature {endpoint!r}",
                    code="UNKNOWN_NODE_REFERENCE",
                )

    basis, projection = _projection_for(nodes, payload)
    node_models = [
        Node(
            id=node_id,
            x=round(projection(point)[0], 6),
            y=round(projection(point)[1], 6),
            node_type=NodeType.JUNCTION,
            name="",
            provenance_class=source.provenance_class,
        )
        for node_id, point in sorted(nodes.items())
    ]
    by_id = {node.id: node for node in node_models}
    edge_models: list[Edge] = []
    for edge in edges:
        u, v = by_id[str(edge["from"])], by_id[str(edge["to"])]
        geometry = [projection((lon, lat)) for lon, lat in edge["line"]]
        geometry[0] = (u.x, u.y)
        geometry[-1] = (v.x, v.y)
        length = sum(
            math.dist(geometry[i], geometry[i + 1]) for i in range(len(geometry) - 1)
        )
        edge_models.append(
            Edge(
                id=edge["id"],
                u=u.id,
                v=v.id,
                geometry=geometry,
                length_m=round(length, 6),
                edge_type=EdgeType.SIDEWALK,
                provenance_class=source.provenance_class,
            )
        )

    version = BaseGraphVersion(
        id=version_id,
        basis=basis,
        nodes=node_models,
        edges=edge_models,
        evidence=[],
        source=source,
    )
    return PedestrianGraph.from_version(version)


def _validate_lon_lat(coordinates: Any, *, where: str) -> tuple[float, float]:
    if not isinstance(coordinates, list | tuple) or len(coordinates) < 2:
        raise IngestionError(f"{where}: expected [longitude, latitude]", code="INVALID_COORDINATES")
    try:
        lon, lat = float(coordinates[0]), float(coordinates[1])
    except (TypeError, ValueError) as exc:
        raise IngestionError(f"{where}: coordinates must be numeric ({exc})", code="INVALID_COORDINATES") from exc
    if not (-180.0 <= lon <= 180.0) or not (-90.0 <= lat <= 90.0):
        raise IngestionError(
            f"{where}: [{lon}, {lat}] is outside the WGS 84 valid range. If these are local planar "
            "metres, use the local-planar dataset schema instead of claiming RFC 7946 GeoJSON.",
            code="INVALID_CRS",
        )
    return lon, lat


def _projection_for(
    nodes: dict[str, tuple[float, float]], payload: dict[str, Any]
) -> tuple[CoordinateBasis, Any]:
    """Return the recorded basis plus a lon/lat -> metre projection callable."""
    declared = (payload.get("detour_lab_crs") or {}) if isinstance(payload, dict) else {}
    lon0 = sum(point[0] for point in nodes.values()) / max(len(nodes), 1)
    lat0 = sum(point[1] for point in nodes.values()) / max(len(nodes), 1)
    cos_lat = max(math.cos(math.radians(lat0)), 1e-9)

    def project(point: tuple[float, float]) -> tuple[float, float]:
        x = math.radians(point[0] - lon0) * EARTH_RADIUS_M * cos_lat
        y = math.radians(point[1] - lat0) * EARTH_RADIUS_M
        return (x, y)

    basis = CoordinateBasis(
        kind="wgs84_degrees",
        unit="degree",
        crs_note=(
            "RFC 7946 WGS 84 longitude/latitude. Metre quantities use a local equirectangular "
            f"projection centred on ({lon0:.6f}, {lat0:.6f}) with mean Earth radius {EARTH_RADIUS_M} m. "
            "Degree arithmetic is never used for length or width."
        ),
        projected_crs=declared.get("projected_crs") or "LOCAL-EQUIRECTANGULAR (documented approximation)",
    )
    return basis, project