"""Phase 8 Unit Tests: Performance Audit, Battery Validation, and Final Review Readiness."""

import pytest
import math
import io
import csv
import json
from pathlib import Path
from fastapi.testclient import TestClient

from src.server import app
from src.models import (
    BenchmarkMode,
    EncryptionAlgorithm,
    SensitivityLevel,
    SensorRecord,
    RecordType,
    EncryptedEnvelope,
)
from src.metrics import (
    calculate_percentage_change,
    calculate_energy_saving,
    evaluate_result_status,
    compute_aggregate_stats,
    compute_authoritative_comparison,
    compute_charge_consumed_mah,
    integrate_energy_joules,
)
from src.crypto import KeyManager, EncryptionEngine, tamper_envelope
from src.receiver import LocalHealthcareReceiver
from src.benchmark_runner import BenchmarkRunner
from src.data_generator import SyntheticDataGenerator
from src.power_measurement import CSVPowerImporter
from src.run_store import RunStore


@pytest.fixture
def client():
    return TestClient(app)


# --- Section 1: Audit Benchmark Calculations ---

def test_percentage_change_and_energy_saving_formulas():
    """Verify exact formula behavior:
    Percentage change = ((Proposed - Baseline) / Baseline) * 100
    Percentage energy saving = ((Baseline Energy - Proposed Energy) / Baseline Energy) * 100
    """
    # 1. Energy regression (Proposed consumes more energy)
    # Baseline: 10 J, Proposed: 12 J
    # Change = ((12 - 10) / 10) * 100 = +20% (Increase)
    # Saving = ((10 - 12) / 10) * 100 = -20% (Negative saving / dissaving)
    pct_change = calculate_percentage_change(10.0, 12.0)
    energy_saving = calculate_energy_saving(10.0, 12.0)
    assert pct_change == 20.0
    assert energy_saving == -20.0

    # 2. Energy improvement (Proposed consumes less energy)
    # Baseline: 20 J, Proposed: 15 J
    # Change = ((15 - 20) / 20) * 100 = -25% (Reduction)
    # Saving = ((20 - 15) / 20) * 100 = +25% (Positive saving / 25% energy saved)
    pct_change_save = calculate_percentage_change(20.0, 15.0)
    energy_saving_pos = calculate_energy_saving(20.0, 15.0)
    assert pct_change_save == -25.0
    assert energy_saving_pos == 25.0

    # 3. Identical energy
    assert calculate_percentage_change(5.0, 5.0) == 0.0
    assert calculate_energy_saving(5.0, 5.0) == 0.0

    # 4. Zero denominator edge cases (safe division)
    assert calculate_percentage_change(0.0, 10.0) == 0.0
    assert calculate_energy_saving(0.0, 10.0) == 0.0
    assert calculate_percentage_change(0.0, 0.0) == 0.0
    assert calculate_energy_saving(0.0, 0.0) == 0.0


def test_evaluate_result_status_classification():
    """Verify result status classification: IMPROVEMENT, REGRESSION, or INCONCLUSIVE."""
    # Latency: lower is better
    assert evaluate_result_status(10.0, 6.0, lower_is_better=True) == "IMPROVEMENT"
    assert evaluate_result_status(10.0, 14.0, lower_is_better=True) == "REGRESSION"
    assert evaluate_result_status(10.0, 10.01, lower_is_better=True) == "INCONCLUSIVE"  # Within 0.2% noise

    # TSR: higher is better
    assert evaluate_result_status(90.0, 99.0, lower_is_better=False) == "IMPROVEMENT"
    assert evaluate_result_status(99.0, 90.0, lower_is_better=False) == "REGRESSION"
    assert evaluate_result_status(100.0, 100.0, lower_is_better=False) == "INCONCLUSIVE"


def test_multi_repetition_aggregate_statistics():
    """Verify distribution metrics: mean, median, p95, min, max, std_dev, spread."""
    samples = [10.0, 12.0, 14.0, 16.0, 18.0]
    agg = compute_aggregate_stats(samples)
    assert agg["mean"] == 14.0
    assert agg["median"] == 14.0
    assert agg["min"] == 10.0
    assert agg["max"] == 18.0
    assert agg["spread"] == 8.0
    assert round(agg["std_dev"], 4) == round(math.sqrt(10.0), 4)

    # Empty samples
    empty_agg = compute_aggregate_stats([])
    assert empty_agg["mean"] == 0.0
    assert empty_agg["std_dev"] == 0.0


def test_unrounded_mathematical_consistency_in_authoritative_comparison():
    """Verify that unrounded raw values produce identical percentage deltas."""
    # Exact values from regression audit
    base_raw = 0.0143941234
    proposed_raw = 0.0614398765

    comp = compute_authoritative_comparison(
        base_raw, proposed_raw, "Mean Latency", lower_is_better=True, is_energy_metric=False
    )
    expected_pct = ((proposed_raw - base_raw) / base_raw) * 100.0
    assert abs(comp["percentage_change"] - expected_pct) < 1e-9
    assert comp["result_status"] == "REGRESSION"
    assert "INCREASED (WORSE / REGRESSION)" in comp["direction"]


# --- Section 2: Fair & Repeatable Benchmarking (Warmup & 10+ Repetitions) ---

def test_warmup_and_ten_measured_repetitions():
    """Verify execution of warm-up runs and at least 10 measured repetitions."""
    runner = BenchmarkRunner()
    record_count = 20
    seed = 42
    reps = 10
    warmup = 2

    res = runner.run_comparison(
        record_count=record_count,
        seed=seed,
        repetitions=reps,
        warmup_repetitions=warmup,
    )

    assert res["repetitions"] == 10
    assert res["warmup_repetitions"] == 2
    assert len(res["all_baseline_runs"]) == 10
    assert len(res["all_adaptive_runs"]) == 10

    # Ensure baseline and adaptive summaries match the aggregate means exactly
    base = res["baseline_summary"]
    adapt = res["adaptive_summary"]
    expected_base_mean = res["baseline_aggregate"]["encryption_mean"]["mean"]
    expected_adapt_mean = res["adaptive_aggregate"]["encryption_mean"]["mean"]

    assert abs(base.encryption_time_mean_ms - expected_base_mean) < 1e-9
    assert abs(adapt.encryption_time_mean_ms - expected_adapt_mean) < 1e-9

    # Mathematical consistency check
    calc_delta = calculate_percentage_change(base.encryption_time_mean_ms, adapt.encryption_time_mean_ms)
    assert abs(calc_delta - res["encryption_time_mean_ms"]["percentage_change"]) < 1e-9


def test_timing_isolation_and_breakdown():
    """Verify classification, clustering, pure crypto, authentication, and serialization are separated."""
    runner = BenchmarkRunner()
    gen = SyntheticDataGenerator(seed=123)
    records = gen.generate_batch(count=30)

    metrics = runner.run_single_batch(BenchmarkMode.ADAPTIVE, records, seed=123)
    assert metrics.classification_time_total_ms >= 0.0
    assert metrics.clustering_time_total_ms >= 0.0
    assert metrics.serialization_time_total_ms >= 0.0
    assert metrics.encryption_time_total_ms >= 0.0
    assert metrics.transmission_time_total_ms >= 0.0
    assert metrics.end_to_end_duration_ms > metrics.encryption_time_total_ms


# --- Section 3 & 4: Power Measurement Modes & Regression Technicality ---

def test_mode_b_physical_power_integration():
    """Verify Mode B numerical energy integration and charge consumed from physical time series."""
    # 3.3V, 50mA for 2 seconds (0, 1000, 2000 ms)
    # Power = 3.3 * 0.05 = 0.165 Watts
    # Energy = 0.165 W * 2 s = 0.33 Joules
    voltages = [3.3, 3.3, 3.3]
    currents = [50.0, 50.0, 50.0]
    timestamps = [0.0, 1000.0, 2000.0]

    total_j, mean_v, mean_i, mean_p = integrate_energy_joules(voltages, currents, timestamps)
    assert abs(total_j - 0.33) < 1e-6
    assert mean_v == 3.3
    assert mean_i == 50.0
    assert mean_p == 165.0

    # Battery charge consumed: 50mA * (2s / 3600s) = 0.027778 mAh
    charge_mah = compute_charge_consumed_mah(mean_i, 2.0)
    assert round(charge_mah, 5) == round(50.0 * (2.0 / 3600.0), 5)


# --- Section 5: Security Audit & Tamper Rejection ---

def test_security_audit_key_sizes_nonces_and_tampering():
    """Security audit: AES-256 key size (32B), nonce size (12B), tag size (16B), and tamper rejection."""
    km = KeyManager()
    assert len(km.aes_key) == 32  # 256 bits
    assert len(km.xor_key) >= 16
    assert len(km.hmac_key) >= 16

    engine = EncryptionEngine(km)
    receiver = LocalHealthcareReceiver(km)

    sample_rec = SensorRecord(
        record_id="REC-AUDIT-1",
        timestamp="2026-10-13T12:00:00Z",
        demo_patient_id="SYNTH-PAT-001",
        record_type=RecordType.ECG_SUMMARY,
        value=1.2,
        unit="mV",
        sensitivity=SensitivityLevel.HIGH,
    )

    env = engine.encrypt_record(sample_rec, "RUN-AUDIT", EncryptionAlgorithm.AES_256_GCM)
    assert len(bytes.fromhex(env.nonce_hex)) == 12  # 96-bit nonce
    assert len(bytes.fromhex(env.tag_hex)) == 16    # 128-bit tag

    # Altered tag must fail verification
    tampered_tag = tamper_envelope(env, target="tag")
    res_tamper = receiver.receive_envelope(tampered_tag)
    assert res_tamper.verified is False
    assert "tampering detected" in res_tamper.error_message


# --- Section 6: End-to-End Workflow & Export Validation ---

def test_full_pipeline_api_and_export_consistency(client, tmp_path):
    """Test full workflow: generation, comparison benchmark, storage, and CSV/JSON export agreement."""
    # 1. Generate
    gen_resp = client.post("/api/demo/generate", json={"count": 20, "seed": 77})
    assert gen_resp.status_code == 200

    # 2. Run Comparison with 10 repetitions
    run_resp = client.post("/api/benchmark/run", json={
        "mode": "comparison",
        "record_count": 20,
        "seed": 77,
        "repetitions": 10,
    })
    assert run_resp.status_code == 200
    run_data = run_resp.json()
    base_id = run_data["baseline_run_id"]
    comp = run_data["comparison"]
    assert comp["overall_result_status"] in ["REGRESSION", "IMPROVEMENT", "INCONCLUSIVE"]

    # 3. Verify CSV Export
    csv_resp = client.get(f"/api/runs/{base_id}/export.csv")
    assert csv_resp.status_code == 200
    csv_text = csv_resp.text
    assert base_id in csv_text
    assert "classification_time_total_ms" in csv_text
    assert "energy_per_1000_records_mj" in csv_text
    assert "aes_key" not in csv_text  # No key leakage

    # 4. Verify JSON Export
    json_resp = client.get(f"/api/runs/{base_id}/export.json")
    assert json_resp.status_code == 200
    json_data = json_resp.json()
    assert json_data["metrics"]["run_id"] == base_id
    assert "aes_key" not in str(json_data)  # No key leakage
