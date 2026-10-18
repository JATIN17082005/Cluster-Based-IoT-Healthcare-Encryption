"""Integration and unit tests for pipeline transparency, exact dataset provenance,
7-stage intermediate outputs, and CSV/JSON exports.
"""

import pytest
import json
import csv
import io
from fastapi.testclient import TestClient
from src.server import app
from src.run_store import RunStore


@pytest.fixture
def client():
    return TestClient(app)


def test_synthetic_data_generation_transparency(client):
    """Verify that synthetic generation returns full metadata, full records, and methodology."""
    resp = client.post("/api/demo/generate", json={"count": 50, "seed": 42})
    assert resp.status_code == 200
    data = resp.json()

    assert data["count"] == 50
    assert data["seed"] == 42
    assert "pipeline_run_id" in data
    assert data["pipeline_run_id"].startswith("PIPE-S42-")

    # Check methodology and full dataset
    assert "generation_methodology" in data
    assert len(data["all_records"]) == 50
    assert len(data["all_features"]) == 50
    assert "clustering_diagnostics" in data

    # Check that individual record has all required fields
    rec = data["all_records"][0]
    assert "record_id" in rec
    assert "timestamp" in rec
    assert "demo_patient_id" in rec
    assert "record_type" in rec
    assert "value" in rec
    assert "unit" in rec
    assert "kmeans_cluster_id" in rec
    assert "cluster_label" in rec
    assert "effective_security_class" in rec


def test_pipeline_current_endpoint(client):
    """Verify that /api/pipeline/current exposes all 7 stages."""
    # First generate data
    gen_resp = client.post("/api/demo/generate", json={"count": 40, "seed": 77})
    assert gen_resp.status_code == 200
    gen_data = gen_resp.json()
    pipe_id = gen_data["pipeline_run_id"]

    # Fetch current pipeline
    pipe_resp = client.get("/api/pipeline/current")
    assert pipe_resp.status_code == 200
    pdata = pipe_resp.json()

    assert pdata["has_data"] is True
    assert pdata["pipeline_run_id"] == pipe_id
    assert pdata["record_count"] == 40

    stages = pdata["stages"]
    assert "stage1_raw" in stages
    assert "stage2_features" in stages
    assert "stage3_kmeans" in stages
    assert "stage4_clustered" in stages
    assert "stage5_routing" in stages
    assert "stage6_receiver" in stages
    assert "stage7_benchmark" in stages

    assert stages["stage1_raw"]["record_count"] == 40
    assert stages["stage2_features"]["label_leakage_prevented"] is True
    assert stages["stage4_clustered"]["high_cluster_count"] + stages["stage4_clustered"]["low_cluster_count"] == 40


def test_pipeline_stage_exports_csv_and_json(client):
    """Verify that stage intermediate exports (raw, features, clustered) return valid CSV and JSON."""
    client.post("/api/demo/generate", json={"count": 25, "seed": 100})

    for stage in ["raw", "features", "clustered"]:
        # Test CSV export
        csv_resp = client.get(f"/api/pipeline/export/{stage}.csv")
        assert csv_resp.status_code == 200
        assert "text/csv" in csv_resp.headers["content-type"]
        csv_reader = csv.reader(io.StringIO(csv_resp.text))
        rows = list(csv_reader)
        # Header + 25 records = 26 rows
        assert len(rows) == 26

        # Test JSON export
        json_resp = client.get(f"/api/pipeline/export/{stage}.json")
        assert json_resp.status_code == 200
        assert "application/json" in json_resp.headers["content-type"]
        jdata = json_resp.json()
        assert "stage" in jdata
        assert "pipeline_run_id" in jdata


def test_kmeans_reconfiguration_endpoint(client):
    """Verify that /api/pipeline/kmeans/configure allows custom K-Means parameter tuning."""
    client.post("/api/demo/generate", json={"count": 30, "seed": 88})

    cfg_payload = {
        "n_clusters": 2,
        "random_state": 99,
        "n_init": 15,
        "max_iter": 400,
        "algorithm": "lloyd",
    }
    resp = client.post("/api/pipeline/kmeans/configure", json=cfg_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "SUCCESS"
    assert data["clustering_config"]["random_state"] == 99
    assert data["clustering_config"]["n_init"] == 15
    assert data["high_cluster_count"] + data["low_cluster_count"] == 30


def test_exact_data_lineage_across_stages(client):
    """Verify that exact record IDs and counts are preserved from Stage 1 through Stage 5."""
    gen_resp = client.post("/api/demo/generate", json={"count": 20, "seed": 55})
    gen_data = gen_resp.json()
    raw_ids = [r["record_id"] for r in gen_data["all_records"]]

    pipe_resp = client.get("/api/pipeline/current")
    pdata = pipe_resp.json()

    stage1_ids = [r["record_id"] for r in pdata["stages"]["stage1_raw"]["records"]]
    stage2_ids = [f["record_id"] for f in pdata["stages"]["stage2_features"]["features"]]
    stage4_ids = [r["record_id"] for r in pdata["stages"]["stage4_clustered"]["records"]]

    assert raw_ids == stage1_ids
    assert raw_ids == stage2_ids
    assert raw_ids == stage4_ids
