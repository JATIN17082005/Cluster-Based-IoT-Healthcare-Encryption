"""Automated integration and regression tests for the staged faculty demonstration workflow.
Verifies Stage 1 through Stage 7:
1. Raw generation and immediate CSV download (without fabricated cluster assignments).
2. ML source file presence, feature engineering table, and features CSV download.
3. Genuine K-Means execution, semantic mapping, safety guardrail, and clustered CSV download.
4. Battery simulation on the exact clustered dataset, per-record energy math, and battery CSV download.
5. Invalidation of downstream state when a new dataset is generated.
6. Encryption routing and receiver verification CSV exports.
"""

import os
import io
import csv
import json
import math
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from src.server import app
from src.models import McuHardwareScenarioConfig


@pytest.fixture
def client():
    # Reset state before each test
    c = TestClient(app)
    c.post("/api/demo/reset")
    return c


def test_stage1_generate_raw_and_immediate_csv_download(client):
    """Stage 1: Generate synthetic healthcare data and immediately enable raw CSV download.
    Raw dataset must NOT contain cluster assignments.
    """
    resp = client.post("/api/pipeline/generate-raw", json={"count": 50, "seed": 42})
    assert resp.status_code == 200
    data = resp.json()

    assert data["count"] == 50
    assert data["seed"] == 42
    assert "pipeline_run_id" in data
    run_id = data["pipeline_run_id"]
    assert run_id.startswith("PIPE-S42-")
    assert data["is_clustered"] is False

    # Check raw records do NOT have cluster labels
    rec0 = data["all_records"][0]
    assert rec0["record_id"].startswith("REC-S42-")
    assert rec0["kmeans_cluster_id"] is None
    assert rec0["cluster_label"] is None

    # Immediate raw CSV download must work
    csv_resp = client.get("/api/pipeline/export/raw.csv")
    assert csv_resp.status_code == 200
    assert "text/csv" in csv_resp.headers["content-type"]
    assert f"stage1_raw_dataset_{run_id}.csv" in csv_resp.headers.get("content-disposition", "")

    reader = csv.reader(io.StringIO(csv_resp.text))
    rows = list(reader)
    # Header + 50 records = 51 rows
    assert len(rows) == 51

    headers = rows[0]
    expected_headers = ["record_id", "timestamp", "demo_patient_id", "record_type", "value", "unit", "is_synthetic", "pipeline_run_id"]
    assert headers == expected_headers

    # Check first record row
    first_row = rows[1]
    assert first_row[0].startswith("REC-S42-")
    assert first_row[7] == run_id


def test_stage2_clustering_fails_without_dataset(client):
    """Clustering action cannot run without an active raw dataset."""
    resp = client.post("/api/pipeline/cluster")
    assert resp.status_code == 400
    assert "No active raw dataset" in resp.json()["detail"]


def test_stage2_kmeans_model_file_and_features(client):
    """Verify that src/kmeans_clusterer.py contains actual scikit-learn implementation
    and that feature engineering intermediate table & CSV download work.
    """
    model_file = Path("src/kmeans_clusterer.py")
    assert model_file.exists(), "src/kmeans_clusterer.py must exist as a real model file"
    code = model_file.read_text(encoding="utf-8")
    assert "from sklearn.cluster import KMeans" in code
    assert "from sklearn.preprocessing import StandardScaler" in code
    assert "HealthcareFeatureExtractor" in code
    assert "fit_and_cluster" in code

    # Generate raw dataset first
    client.post("/api/pipeline/generate-raw", json={"count": 35, "seed": 77})

    # Run clustering
    clust_resp = client.post("/api/pipeline/cluster")
    assert clust_resp.status_code == 200
    cdata = clust_resp.json()
    assert cdata["status"] == "SUCCESS"
    assert cdata["total_records"] == 35

    # Download features CSV
    feat_resp = client.get("/api/pipeline/export/features.csv")
    assert feat_resp.status_code == 200
    reader = csv.reader(io.StringIO(feat_resp.text))
    rows = list(reader)
    assert len(rows) == 36  # Header + 35 records

    headers = rows[0]
    assert "record_id" in headers
    assert "sensor_type" in headers or "record_type" in headers
    assert "type_heart_rate" in headers
    assert "scaled_type_heart_rate" in headers
    assert "modality_normalized_value" in headers
    assert "physiological_range_deviation" in headers
    assert "policy_sensitivity" not in headers, "Feature matrix must not leak policy sensitivity labels"


def test_stage3_kmeans_execution_and_clustered_csv(client):
    """Verify scikit-learn K-Means execution, semantic mapping, safety guardrail, and clustered CSV download."""
    client.post("/api/pipeline/generate-raw", json={"count": 50, "seed": 42})
    clust_resp = client.post("/api/pipeline/cluster")
    assert clust_resp.status_code == 200
    data = clust_resp.json()

    assert data["high_cluster_count"] + data["low_cluster_count"] == 50
    diag = data["clustering_diagnostics"]
    assert diag["n_samples"] == 50
    assert diag["inertia"] > 0.0
    assert "centroids" in diag

    # Download clustered dataset CSV
    csv_resp = client.get("/api/pipeline/export/clustered.csv")
    assert csv_resp.status_code == 200
    reader = csv.reader(io.StringIO(csv_resp.text))
    rows = list(reader)
    assert len(rows) == 51

    headers = rows[0]
    for col in ["record_id", "record_type", "value", "unit", "kmeans_cluster_id", "cluster_label", "policy_sensitivity", "effective_security_class", "policy_override", "override_reason"]:
        assert col in headers

    # Verify safety guardrail: policy HIGH must never be downgraded to LOW
    rec_type_idx = headers.index("record_type")
    pol_idx = headers.index("policy_sensitivity")
    eff_idx = headers.index("effective_security_class")
    for r in rows[1:]:
        if r[pol_idx] == "HIGH":
            assert r[eff_idx] == "HIGH", f"Clinical HIGH record {r[0]} was downgraded to {r[eff_idx]}!"


def test_stage4_battery_simulation_fails_before_clustering(client):
    """Battery simulation cannot run before clustering has been performed."""
    client.post("/api/pipeline/generate-raw", json={"count": 50, "seed": 42})
    resp = client.post("/api/battery/simulate-current", json={"repetitions": 1})
    assert resp.status_code == 400
    assert "Run ML Clustering before simulating battery" in resp.json()["detail"]


def test_stage4_battery_simulation_on_current_dataset_math(client):
    """Verify that battery simulation uses current dataset's exact effective counts,
    calculates per-record energy matching E = V * I * t, and exports battery CSV.
    """
    client.post("/api/pipeline/generate-raw", json={"count": 60, "seed": 105})
    client.post("/api/pipeline/cluster")

    resp = client.post("/api/battery/simulate-current", json={"repetitions": 1})
    assert resp.status_code == 200
    bdata = resp.json()

    assert bdata["total_records"] == 60
    assert bdata["high_sensitivity_count"] + bdata["low_sensitivity_count"] == 60

    cfg = McuHardwareScenarioConfig()
    v = cfg.supply_voltage_v
    usable_j = (cfg.battery_nominal_mah / 1000.0) * 3600.0 * v * cfg.battery_usable_factor

    assert math.isclose(bdata["usable_rail_energy_joules"], usable_j, rel_tol=1e-5)

    records = bdata["records"]
    assert len(records) == 60

    running_base = 0.0
    running_adapt = 0.0

    for idx, r in enumerate(records):
        assert r["pipeline_run_id"] == bdata["pipeline_run_id"]
        assert r["baseline_algorithm"] == "AES-256-GCM"

        if r["effective_security_class"] == "HIGH":
            assert r["adaptive_algorithm"] == "AES-256-GCM"
            assert math.isclose(r["baseline_energy_joules"], r["adaptive_energy_joules"], rel_tol=1e-5)
        else:
            assert r["adaptive_algorithm"] in ["XOR-EXPERIMENTAL", "XOR-STREAM-HMAC"]
            assert r["adaptive_energy_joules"] < r["baseline_energy_joules"]

        running_base += r["baseline_energy_joules"]
        running_adapt += r["adaptive_energy_joules"]

        assert math.isclose(r["baseline_cumulative_energy_joules"], running_base, rel_tol=1e-4, abs_tol=1e-6)
        assert math.isclose(r["adaptive_cumulative_energy_joules"], running_adapt, rel_tol=1e-4, abs_tol=1e-6)

        assert 0.0 <= r["baseline_battery_remaining_percent"] <= 100.0
        assert 0.0 <= r["adaptive_battery_remaining_percent"] <= 100.0

    # Total batch energies match sum of records
    assert math.isclose(bdata["baseline_batch_energy_joules"], running_base, rel_tol=1e-4, abs_tol=1e-6)
    assert math.isclose(bdata["adaptive_batch_energy_joules"], running_adapt, rel_tol=1e-4, abs_tol=1e-6)

    # Battery CSV export
    b_csv_resp = client.get("/api/pipeline/export/battery.csv")
    assert b_csv_resp.status_code == 200
    b_rows = list(csv.reader(io.StringIO(b_csv_resp.text)))
    assert len(b_rows) == 61
    assert "baseline_battery_remaining_percent" in b_rows[0]
    assert "adaptive_battery_remaining_percent" in b_rows[0]


def test_stage5_and_6_encryption_and_receiver_verification(client):
    """Verify encryption routing and receiver verification intermediate datasets."""
    client.post("/api/pipeline/generate-raw", json={"count": 40, "seed": 42})
    client.post("/api/pipeline/cluster")

    resp = client.post("/api/pipeline/encrypt-and-verify")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "SUCCESS"
    assert data["records_count"] == 40
    assert data["aes_256_gcm_count"] + data["xor_lightweight_count"] == 40

    # Routing CSV export
    rout_resp = client.get("/api/pipeline/export/routing.csv")
    assert rout_resp.status_code == 200
    rout_rows = list(csv.reader(io.StringIO(rout_resp.text)))
    assert len(rout_rows) == 41
    assert "adaptive_selected_algorithm" in rout_rows[0]

    # Receiver CSV export
    rec_resp = client.get("/api/pipeline/export/receiver.csv")
    assert rec_resp.status_code == 200
    rec_rows = list(csv.reader(io.StringIO(rec_resp.text)))
    assert len(rec_rows) == 41
    assert "verified" in rec_rows[0]


def test_stage7_stale_data_invalidation_on_new_generation(client):
    """When a new dataset is generated, stale downstream state from previous run must be invalidated."""
    # Run 1
    client.post("/api/pipeline/generate-raw", json={"count": 30, "seed": 11})
    client.post("/api/pipeline/cluster")
    client.post("/api/battery/simulate-current")

    raw1_resp = client.get("/api/pipeline/export/raw.csv")
    assert "stage1_raw_dataset_PIPE-S11-" in raw1_resp.headers["content-disposition"]

    # Run 2: Generate fresh raw dataset with different seed
    client.post("/api/pipeline/generate-raw", json={"count": 25, "seed": 99})

    # Raw CSV must now immediately reflect Run 2
    raw2_resp = client.get("/api/pipeline/export/raw.csv")
    assert "stage1_raw_dataset_PIPE-S99-" in raw2_resp.headers["content-disposition"]
    rows2 = list(csv.reader(io.StringIO(raw2_resp.text)))
    assert len(rows2) == 26  # Header + 25 records

    # Battery simulation MUST fail because Run 2 has not yet been clustered
    bat_fail = client.post("/api/battery/simulate-current")
    assert bat_fail.status_code == 400
    assert "Run ML Clustering before simulating battery" in bat_fail.json()["detail"]


def test_repeated_batch_battery_simulation_repetitions_1(client):
    """Verify that repetitions=1 maintains single-batch behavior with packet and repetition indices."""
    client.post("/api/pipeline/generate-raw", json={"count": 50, "seed": 42})
    client.post("/api/pipeline/cluster")

    resp = client.post("/api/battery/simulate-current?repetitions=1")
    assert resp.status_code == 200
    data = resp.json()

    assert data["duration_batches"] == 1
    assert data["total_packets_simulated"] == 50
    assert len(data["records"]) == 50

    records = data["records"]
    running_base_j = 0.0
    for idx, r in enumerate(records):
        assert r["repetition_index"] == 1
        assert r["packet_index"] == idx + 1
        assert r["baseline_cumulative_energy_joules"] > running_base_j
        running_base_j = r["baseline_cumulative_energy_joules"]

    # Final row cumulative values must match summary
    last = records[-1]
    assert math.isclose(last["baseline_cumulative_energy_joules"], data["baseline_total_energy_joules"], rel_tol=1e-5)
    assert math.isclose(last["baseline_cumulative_energy_joules"], data["baseline_batch_energy_joules"], rel_tol=1e-5)
    assert math.isclose(last["adaptive_cumulative_energy_joules"], data["adaptive_total_energy_joules"], rel_tol=1e-5)
    assert math.isclose(last["baseline_battery_remaining_percent"], data["baseline_final_remaining_percent"], rel_tol=1e-5)
    assert math.isclose(last["adaptive_battery_remaining_percent"], data["adaptive_final_remaining_percent"], rel_tol=1e-5)

    # Battery CSV export row count & headers
    csv_resp = client.get("/api/pipeline/export/battery.csv")
    assert csv_resp.status_code == 200
    csv_rows = list(csv.reader(io.StringIO(csv_resp.text)))
    assert len(csv_rows) == 51  # 1 header + 50 entries
    assert "repetition_index" in csv_rows[0]
    assert "packet_index" in csv_rows[0]


def test_repeated_batch_battery_simulation_repetitions_2(client):
    """Verify that repetitions=2 advances progression monotonically across both passes without reset."""
    client.post("/api/pipeline/generate-raw", json={"count": 40, "seed": 77})
    client.post("/api/pipeline/cluster")

    resp = client.post("/api/battery/simulate-current?repetitions=2")
    assert resp.status_code == 200
    data = resp.json()

    assert data["duration_batches"] == 2
    assert data["total_packets_simulated"] == 80
    assert len(data["records"]) == 80

    records = data["records"]
    single_batch_base_j = data["baseline_batch_energy_joules"]
    total_base_j = data["baseline_total_energy_joules"]
    assert math.isclose(total_base_j, single_batch_base_j * 2, rel_tol=1e-5)

    # Monotonic accumulation and packet indexing check across entire multi-batch run
    for idx, r in enumerate(records):
        assert r["packet_index"] == idx + 1
        if idx < 40:
            assert r["repetition_index"] == 1
        else:
            assert r["repetition_index"] == 2
            # Pass 2 cumulative energy must be strictly greater than Pass 1 single-batch energy
            assert r["baseline_cumulative_energy_joules"] > single_batch_base_j

        if idx > 0:
            assert r["baseline_cumulative_energy_joules"] > records[idx - 1]["baseline_cumulative_energy_joules"]
            assert r["adaptive_cumulative_energy_joules"] > records[idx - 1]["adaptive_cumulative_energy_joules"]
            assert r["baseline_battery_remaining_percent"] <= records[idx - 1]["baseline_battery_remaining_percent"]
            assert r["adaptive_battery_remaining_percent"] <= records[idx - 1]["adaptive_battery_remaining_percent"]

    # End of Pass 1 check (record 39, index 39)
    assert math.isclose(records[39]["baseline_cumulative_energy_joules"], single_batch_base_j, rel_tol=1e-5)

    # End of Pass 2 check (record 79, index 79)
    last = records[79]
    assert math.isclose(last["baseline_cumulative_energy_joules"], total_base_j, rel_tol=1e-5)
    assert math.isclose(last["baseline_battery_remaining_percent"], data["baseline_final_remaining_percent"], rel_tol=1e-5)
    assert math.isclose(last["adaptive_battery_remaining_percent"], data["adaptive_final_remaining_percent"], rel_tol=1e-5)

    # Battery CSV export must contain all 80 rows across both passes
    csv_resp = client.get("/api/pipeline/export/battery.csv")
    assert csv_resp.status_code == 200
    csv_rows = list(csv.reader(io.StringIO(csv_resp.text)))
    assert len(csv_rows) == 81  # 1 header + 80 entries
    rep1_count = sum(1 for row in csv_rows[1:] if row[csv_rows[0].index("repetition_index")] == "1")
    rep2_count = sum(1 for row in csv_rows[1:] if row[csv_rows[0].index("repetition_index")] == "2")
    assert rep1_count == 40
    assert rep2_count == 40


def test_repeated_batch_battery_simulation_repetitions_10_duration(client):
    """Verify that larger repetitions (e.g. 10 passes) calculate simulated elapsed time correctly."""
    client.post("/api/pipeline/generate-raw", json={"count": 30, "seed": 101})
    client.post("/api/pipeline/cluster")

    resp = client.post("/api/battery/simulate-current?repetitions=10")
    assert resp.status_code == 200
    data = resp.json()

    assert data["duration_batches"] == 10
    assert data["total_packets_simulated"] == 300
    assert len(data["records"]) == 300
    # 300 packets at 50 Hz reporting frequency = 6.00 seconds
    assert math.isclose(data["simulated_operating_seconds"], 6.00, rel_tol=1e-4)

    last = data["records"][-1]
    assert last["packet_index"] == 300
    assert last["repetition_index"] == 10
    assert math.isclose(last["baseline_cumulative_energy_joules"], data["baseline_total_energy_joules"], rel_tol=1e-5)
    assert math.isclose(data["baseline_total_energy_joules"], data["baseline_batch_energy_joules"] * 10, rel_tol=1e-5)

    # Export check
    csv_resp = client.get("/api/pipeline/export/battery.csv")
    assert csv_resp.status_code == 200
    csv_rows = list(csv.reader(io.StringIO(csv_resp.text)))
    assert len(csv_rows) == 301


def test_repeated_batch_battery_safeguard_limit(client):
    """Verify safeguard prevents excessive workloads (>50,000 packets) with HTTP 422 and ValueError."""
    import pytest
    from src.power_measurement import McuEnergyModel

    client.post("/api/pipeline/generate-raw", json={"count": 100, "seed": 55})
    client.post("/api/pipeline/cluster")

    # 100 records * 600 repetitions = 60,000 packets (> 50,000 safeguard limit)
    resp = client.post("/api/battery/simulate-current?repetitions=600")
    assert resp.status_code == 422
    assert "exceeds documented safe export limit of 50000 packets" in resp.json()["detail"]

    # Direct model verification
    records = [{"record_id": f"REC-{i}", "effective_security_class": "HIGH"} for i in range(100)]
    model = McuEnergyModel()
    with pytest.raises(ValueError, match="exceeds documented safe export limit"):
        model.simulate_battery_on_records(records, repetitions=600)



def test_consecutive_generations_create_different_datasets_without_seed(client):
    """Verify two consecutive Generate calls without an explicit seed produce different datasets
    with distinct random seeds, different records, and identical requested schemas.
    """
    resp1 = client.post("/api/pipeline/generate-raw", json={"count": 50})
    assert resp1.status_code == 200
    data1 = resp1.json()

    resp2 = client.post("/api/pipeline/generate-raw", json={"count": 50})
    assert resp2.status_code == 200
    data2 = resp2.json()

    # 1. Dataset IDs and seeds must be different
    assert data1["dataset_id"] != data2["dataset_id"]
    assert data1["seed"] != data2["seed"]

    # 2. Both retain requested count and schema
    assert data1["count"] == 50
    assert data2["count"] == 50
    assert len(data1["all_records"]) == 50
    assert len(data2["all_records"]) == 50

    # 3. Records must contain different values
    values1 = [r["value"] for r in data1["all_records"]]
    values2 = [r["value"] for r in data2["all_records"]]
    assert values1 != values2, "Consecutive generations must not produce duplicate sensor readings"


def test_clustering_classifies_latest_generated_dataset(client):
    """Verify that running ML clustering strictly classifies the most recently generated dataset,
    not an earlier batch or a hardcoded set.
    """
    # Generation 1
    resp1 = client.post("/api/pipeline/generate-raw", json={"count": 40, "seed": 101})
    data1 = resp1.json()
    id1 = data1["dataset_id"]

    # Generation 2
    resp2 = client.post("/api/pipeline/generate-raw", json={"count": 40, "seed": 202})
    data2 = resp2.json()
    id2 = data2["dataset_id"]
    assert id1 != id2

    # Run ML clustering
    clust_resp = client.post("/api/pipeline/cluster")
    assert clust_resp.status_code == 200
    cdata = clust_resp.json()

    # Must classify dataset 2
    assert cdata["dataset_id"] == id2
    assert cdata["pipeline_run_id"] == id2
    assert cdata["total_records"] == 40

    records = cdata["all_records"]
    assert len(records) == 40
    for r in records:
        assert r["pipeline_run_id"] == id2
        assert r["dataset_id"] == id2
        assert r["record_id"].startswith("REC-S202-"), "Clustered record must trace to Generation 2 (seed 202)"


def test_dataset_id_traceability_across_all_stages_and_exports(client):
    """Verify that dataset_id correctly links raw data, features, clustered records,
    battery simulation, and exports across the pipeline.
    """
    # Generate fresh random dataset
    gen_resp = client.post("/api/pipeline/generate-raw", json={"count": 30})
    assert gen_resp.status_code == 200
    gen_data = gen_resp.json()
    ds_id = gen_data["dataset_id"]
    assert ds_id is not None

    # 1. Raw exports link
    raw_csv = client.get("/api/pipeline/export/raw.csv")
    assert ds_id in raw_csv.headers["content-disposition"]
    raw_rows = list(csv.reader(io.StringIO(raw_csv.text)))
    assert all(row[7] == ds_id for row in raw_rows[1:])

    raw_json = client.get("/api/pipeline/export/raw.json").json()
    assert raw_json["dataset_id"] == ds_id

    # 2. Cluster & check features + clustered exports
    c_resp = client.post("/api/pipeline/cluster")
    assert c_resp.json()["dataset_id"] == ds_id

    feat_json = client.get("/api/pipeline/export/features.json").json()
    assert feat_json["dataset_id"] == ds_id

    clust_json = client.get("/api/pipeline/export/clustered.json").json()
    assert clust_json["dataset_id"] == ds_id

    clust_csv = client.get("/api/pipeline/export/clustered.csv")
    assert ds_id in clust_csv.headers["content-disposition"]

    # 3. Battery simulation link
    bat_resp = client.post("/api/battery/simulate-current")
    assert bat_resp.json()["dataset_id"] == ds_id

    bat_json = client.get("/api/pipeline/export/battery.json").json()
    assert bat_json["dataset_id"] == ds_id

    # 4. Encryption & Receiver link
    enc_resp = client.post("/api/pipeline/encrypt-and-verify")
    assert enc_resp.json()["dataset_id"] == ds_id


def test_generation_invalidates_stale_active_stage_results_and_downloads(client):
    """Verify that generating a new dataset invalidates downstream stage results and downloads,
    while preserving run history snapshots.
    """
    # Complete Run 1
    client.post("/api/pipeline/generate-raw", json={"count": 30, "seed": 33})
    client.post("/api/pipeline/cluster")
    client.post("/api/battery/simulate-current")

    # Features and battery are available for Run 1
    assert client.get("/api/pipeline/export/features.csv").status_code == 200
    assert client.get("/api/pipeline/export/battery.csv").status_code == 200

    # Generate Run 2
    client.post("/api/pipeline/generate-raw", json={"count": 25, "seed": 44})

    # Raw is immediately available for Run 2
    raw_resp = client.get("/api/pipeline/export/raw.csv")
    assert raw_resp.status_code == 200
    assert "stage1_raw_dataset_PIPE-S44-" in raw_resp.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(raw_resp.text)))
    assert len(rows) == 26  # Header + 25 rows

    # Downstream exports MUST be invalidated (return 400)
    feat_resp = client.get("/api/pipeline/export/features.csv")
    assert feat_resp.status_code == 400
    assert "Run ML Clustering first" in feat_resp.json()["detail"]

    clust_resp = client.get("/api/pipeline/export/clustered.csv")
    assert clust_resp.status_code == 400

    bat_resp = client.get("/api/pipeline/export/battery.csv")
    assert bat_resp.status_code == 400


def test_explicit_seeds_allow_deterministic_reproducible_data(client):
    """Verify that specifying an explicit seed reproduces exact bit-for-bit synthetic records."""
    resp1 = client.post("/api/pipeline/generate-raw", json={"count": 30, "seed": 888})
    data1 = resp1.json()

    # Interleave with a different seed
    client.post("/api/pipeline/generate-raw", json={"count": 20, "seed": 999})

    # Re-run with seed 888
    resp2 = client.post("/api/pipeline/generate-raw", json={"count": 30, "seed": 888})
    data2 = resp2.json()

    assert data1["seed"] == 888
    assert data2["seed"] == 888

    records1 = data1["all_records"]
    records2 = data2["all_records"]

    for r1, r2 in zip(records1, records2):
        assert r1["record_type"] == r2["record_type"]
        assert r1["value"] == r2["value"]
        assert r1["unit"] == r2["unit"]
        assert r1["demo_patient_id"] == r2["demo_patient_id"]
