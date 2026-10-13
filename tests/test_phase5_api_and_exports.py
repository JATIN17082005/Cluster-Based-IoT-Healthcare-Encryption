"""Phase 5 Unit Tests: REST API Endpoints, UI Data Binding, and CSV/JSON Exports."""

import pytest
from fastapi.testclient import TestClient
from src.server import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health_endpoint(client):
    """Verify health endpoint response and key manager status."""
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "HEALTHY"
    assert "key_manager_status" in data
    assert data["receiver_active"] is True


def test_demo_generate_endpoint(client):
    """Verify synthetic batch generation API."""
    resp = client.post("/api/demo/generate", json={"count": 30, "seed": 42})
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 30
    assert data["high_cluster_count"] + data["low_cluster_count"] == 30
    assert len(data["all_records"]) == 30
    assert "records_preview" in data


def test_benchmark_run_and_comparison_endpoints(client):
    """Verify benchmark run endpoint in baseline, adaptive, and comparison modes."""
    # Run comparison
    resp = client.post("/api/benchmark/run", json={
        "mode": "comparison",
        "record_count": 20,
        "seed": 99,
        "repetitions": 1,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "comparison"
    assert "comparison" in data
    comp = data["comparison"]
    assert "baseline_summary" in comp
    assert "adaptive_summary" in comp
    assert "encryption_time_mean_ms" in comp
    assert "total_energy_joules" in comp
    assert comp["baseline_summary"]["aes_record_count"] == 20
    assert comp["adaptive_summary"]["aes_record_count"] + comp["adaptive_summary"]["xor_record_count"] == 20


def test_tamper_demo_endpoint(client):
    """Verify live tamper rejection API for AES-256-GCM and XOR."""
    # AES-256-GCM tamper test
    resp_aes = client.post("/api/demo/tamper", json={
        "algorithm": "AES-256-GCM",
        "tamper_target": "ciphertext",
    })
    assert resp_aes.status_code == 200
    data_aes = resp_aes.json()
    assert data_aes["rejection_verified"] is True
    assert data_aes["valid_result"]["verified"] is True
    assert data_aes["tampered_result"]["verified"] is False
    assert "tampering detected" in data_aes["tampered_result"]["error_message"]

    # XOR tamper test
    resp_xor = client.post("/api/demo/tamper", json={
        "algorithm": "XOR-EXPERIMENTAL",
        "tamper_target": "hmac",
    })
    assert resp_xor.status_code == 200
    data_xor = resp_xor.json()
    assert data_xor["rejection_verified"] is True
    assert data_xor["valid_result"]["verified"] is True
    assert data_xor["tampered_result"]["verified"] is False
    assert "integrity verification failed" in data_xor["tampered_result"]["error_message"]


def test_power_csv_import_endpoint(client):
    """Verify importing lab instrument power CSV via API."""
    valid_csv = b"timestamp_ms,voltage_v,current_ma\n0.0,3.3,45.0\n10.0,3.3,55.0\n"
    files = {"file": ("power_test.csv", valid_csv, "text/csv")}
    resp = client.post("/api/power/import", files=files)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "SUCCESS"
    assert data["sample_count"] == 2
    assert data["mean_voltage_v"] == 3.3

    # Invalid CSV
    files_bad = {"file": ("bad.csv", b"invalid_columns\n1,2\n", "text/csv")}
    resp_bad = client.post("/api/power/import", files=files_bad)
    assert resp_bad.status_code == 400


def test_export_endpoints(client):
    """Verify CSV and JSON exports omit secret keys and include metadata."""
    # First trigger a run
    run_resp = client.post("/api/benchmark/run", json={
        "mode": "baseline",
        "record_count": 10,
        "seed": 42,
    })
    run_id = run_resp.json()["run_id"]

    # 1. Export CSV
    csv_resp = client.get(f"/api/runs/{run_id}/export.csv")
    assert csv_resp.status_code == 200
    assert csv_resp.headers["content-type"].startswith("text/csv")
    csv_content = csv_resp.text
    assert "run_id,mode,seed" in csv_content
    assert run_id in csv_content
    # Confirm NO secret key names or raw keys in CSV
    assert "secret_key" not in csv_content
    assert "aes_key" not in csv_content

    # 2. Export JSON
    json_resp = client.get(f"/api/runs/{run_id}/export.json")
    assert json_resp.status_code == 200
    assert json_resp.headers["content-type"].startswith("application/json")
    json_data = json_resp.json()
    assert json_data["metrics"]["run_id"] == run_id
    assert "metadata" in json_data
    assert "records" in json_data
    # Confirm no keys in JSON
    json_str = str(json_data)
    assert "aes_key" not in json_str
    assert "xor_key" not in json_str


def test_index_html_serving(client):
    """Verify frontend dashboard is served at root /."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Cluster-Based IoT Healthcare Encryption" in resp.text
    assert "SIMULATED / ESTIMATED" in resp.text
