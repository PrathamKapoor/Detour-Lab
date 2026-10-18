"""Ingestion validation, including the geographic-caution requirement (FR-001)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from detour_lab.domain.enums import ProvenanceClass
from detour_lab.ingestion.schema import (
    IngestionError,
    load_local_planar_dataset,
    load_rfc7946_geojson,
)

VALID_GEOJSON = {
    "type": "FeatureCollection",
    "features": [
        {"type": "Feature", "properties": {"id": "P1"}, "geometry": {"type": "Point", "coordinates": [77.5000, 12.9700]}},
        {"type": "Feature", "properties": {"id": "P2"}, "geometry": {"type": "Point", "coordinates": [77.5010, 12.9700]}},
        {
            "type": "Feature",
            "properties": {"id": "L1", "from": "P1", "to": "P2"},
            "geometry": {"type": "LineString", "coordinates": [[77.5000, 12.9700], [77.5010, 12.9700]]},
        },
    ],
}

SOURCE = {
    "name": "test source",
    "description": "synthetic test geojson",
    "license": "ODbL (as with OpenStreetMap data)",
    "attribution": "test fixture",
    "provenance_class": "external_source",
}


class TestLocalPlanarDataset:
    def test_seed_loads_with_explicit_labels(self, seed):
        assert "SYNTHETIC" in seed.notice.upper()
        assert seed.graph.version.basis.kind == "local_planar_meters"
        assert seed.graph.version.basis.local_origin_label
        assert seed.project.jurisdiction == "unspecified"
        assert seed.graph.version.source.provenance_class is ProvenanceClass.SYNTHETIC

    def test_seed_every_edge_has_provenance(self, seed):
        assert all(e.provenance_class is ProvenanceClass.SYNTHETIC for e in seed.graph.edges)
        assert all(r.synthetic for r in seed.graph.evidence_registry.all_records())

    def test_local_planar_without_origin_label_is_rejected(self, tmp_path: Path):
        payload = json.loads(json.dumps(_minimal_local_planar()))
        payload["basis"].pop("local_origin_label")
        path = tmp_path / "bad.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(IngestionError) as excinfo:
            load_local_planar_dataset(path)
        assert excinfo.value.code == "MISSING_FIELD"

    def test_unsupported_schema_is_rejected(self, tmp_path: Path):
        payload = json.loads(json.dumps(_minimal_local_planar()))
        payload["schema"] = "something/else"
        path = tmp_path / "bad.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(IngestionError) as excinfo:
            load_local_planar_dataset(path)
        assert excinfo.value.code == "UNSUPPORTED_SCHEMA"

    def test_evidence_for_an_unknown_element_is_rejected(self, tmp_path: Path):
        payload = json.loads(json.dumps(_minimal_local_planar()))
        payload["evidence"].append(
            {
                "id": "EV-GHOST", "element_id": "E_GHOST", "field": "width_mm", "value": 1000, "unit": "mm",
                "method": "test", "source": "test",
            }
        )
        path = tmp_path / "bad.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(IngestionError) as excinfo:
            load_local_planar_dataset(path)
        assert excinfo.value.code == "UNKNOWN_NODE_REFERENCE"

    def test_declared_length_contradicting_geometry_is_rejected(self, tmp_path: Path):
        payload = json.loads(json.dumps(_minimal_local_planar()))
        payload["edges"][0]["length_m"] = 999.0
        path = tmp_path / "bad.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(IngestionError) as excinfo:
            load_local_planar_dataset(path)
        assert excinfo.value.code == "LENGTH_GEOMETRY_MISMATCH"

    def test_edge_referencing_unknown_node_is_rejected(self, tmp_path: Path):
        payload = json.loads(json.dumps(_minimal_local_planar()))
        payload["edges"][0]["v"] = "N_MISSING"
        path = tmp_path / "bad.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(IngestionError) as excinfo:
            load_local_planar_dataset(path)
        assert excinfo.value.code == "UNKNOWN_NODE_REFERENCE"


class TestRfc7946GeoJson:
    def test_valid_geojson_is_converted_to_project_metres(self):
        graph = load_rfc7946_geojson(VALID_GEOJSON, source=_source(), version_id="v1")
        assert graph.version.basis.kind == "wgs84_degrees"
        assert "equirectangular" in graph.version.basis.crs_note.lower()
        edge_obj = graph.edge("L1")
        # 0.001 degree of longitude at ~12.97 N is roughly 108 m, not 0.001 units:
        # proof that the projection ran and that degrees were never used as metres.
        assert edge_obj.length_m == pytest.approx(108.4, abs=0.5)
        assert edge_obj.length_m > 100

    def test_local_planar_metres_claiming_to_be_geojson_are_rejected(self):
        """The classic failure this product must never ship."""
        payload = json.loads(json.dumps(VALID_GEOJSON))
        for feature in payload["features"]:
            if feature["geometry"]["type"] == "Point":
                feature["geometry"]["coordinates"] = [4000.0, 0.0]
            else:
                feature["geometry"]["coordinates"] = [[4000.0, 0.0], [9000.0, 0.0]]
        with pytest.raises(IngestionError) as excinfo:
            load_rfc7946_geojson(payload, source=_source(), version_id="v1")
        assert excinfo.value.code == "INVALID_CRS"
        assert "local planar" in str(excinfo.value).lower()

    def test_non_featurecollection_rejected(self):
        with pytest.raises(IngestionError) as excinfo:
            load_rfc7946_geojson({"type": "Feature"}, source=_source(), version_id="v1")
        assert excinfo.value.code == "UNSUPPORTED_SCHEMA"

    def test_linestring_without_node_references_rejected(self):
        payload = json.loads(json.dumps(VALID_GEOJSON))
        payload["features"][2]["properties"].pop("from")
        with pytest.raises(IngestionError) as excinfo:
            load_rfc7946_geojson(payload, source=_source(), version_id="v1")
        assert excinfo.value.code == "MISSING_FIELD"
        assert "never inferred" in str(excinfo.value)

    def test_edge_to_missing_node_rejected(self):
        payload = json.loads(json.dumps(VALID_GEOJSON))
        payload["features"][2]["properties"]["to"] = "P_MISSING"
        with pytest.raises(IngestionError) as excinfo:
            load_rfc7946_geojson(payload, source=_source(), version_id="v1")
        assert excinfo.value.code == "UNKNOWN_NODE_REFERENCE"

    def test_unsupported_geometry_rejected(self):
        payload = json.loads(json.dumps(VALID_GEOJSON))
        payload["features"][0]["geometry"] = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}
        with pytest.raises(IngestionError) as excinfo:
            load_rfc7946_geojson(payload, source=_source(), version_id="v1")
        assert excinfo.value.code == "UNSUPPORTED_GEOMETRY"

    def test_missing_feature_id_rejected(self):
        payload = json.loads(json.dumps(VALID_GEOJSON))
        payload["features"][0]["properties"].pop("id")
        with pytest.raises(IngestionError) as excinfo:
            load_rfc7946_geojson(payload, source=_source(), version_id="v1")
        assert excinfo.value.code == "MISSING_FIELD"

    def test_non_numeric_coordinates_rejected(self):
        payload = json.loads(json.dumps(VALID_GEOJSON))
        payload["features"][0]["geometry"]["coordinates"] = ["drop table", "x"]
        with pytest.raises(IngestionError) as excinfo:
            load_rfc7946_geojson(payload, source=_source(), version_id="v1")
        assert excinfo.value.code == "INVALID_COORDINATES"

    def test_imported_graph_records_its_licence(self):
        graph = load_rfc7946_geojson(VALID_GEOJSON, source=_source(), version_id="v1")
        assert "ODbL" in graph.version.source.license
        assert graph.version.source.attribution == "test fixture"

    def test_import_is_deterministic(self):
        first = load_rfc7946_geojson(VALID_GEOJSON, source=_source(), version_id="v1")
        second = load_rfc7946_geojson(json.loads(json.dumps(VALID_GEOJSON)), source=_source(), version_id="v1")
        assert first.content_hash == second.content_hash


def test_imported_geojson_has_no_evidence_so_nothing_can_pass(seed):
    """A network with zero evidence must produce zero confirmations."""
    graph = load_rfc7946_geojson(VALID_GEOJSON, source=_source(), version_id="v1")
    assert graph.evidence_registry.all_records() == ()
    from detour_lab.rules.engine import evaluate_graph, load_rulepack
    from tests.conftest import AS_OF, RULEPACK_PATH

    evaluation = evaluate_graph(
        graph=graph, rulepack=load_rulepack(RULEPACK_PATH),
        profile_id="DEMO_PROFILE_MANUAL_WHEELCHAIR", phase_id="p1", as_of=AS_OF,
    )
    assert all(state.value == "UNKNOWN" for state in evaluation.edge_states.values())


def _source():
    from detour_lab.domain.contracts import DataSource

    return DataSource.model_validate(SOURCE)


def _minimal_local_planar() -> dict:
    return {
        "schema": "detour-lab-local-planar/1.0",
        "NOTICE": "synthetic",
        "dataset": SOURCE,
        "project": {"name": "minimal"},
        "basis": {
            "kind": "local_planar_meters",
            "unit": "m",
            "local_origin_label": "test",
            "crs_note": "test",
        },
        "graph_version_id": "minimal-v1",
        "nodes": [
            {"id": "N1", "x": 0.0, "y": 0.0},
            {"id": "N2", "x": 10.0, "y": 0.0},
        ],
        "edges": [{"id": "E12", "u": "N1", "v": "N2", "length_m": 10.0}],
        "evidence": [],
        "origins_destinations": [{"id": "OD1", "label": "a", "node_id": "N1", "kind": "origin"}],
        "phases": [{"id": "p1", "order": 1}],
        "temporary_edges": [],
    }