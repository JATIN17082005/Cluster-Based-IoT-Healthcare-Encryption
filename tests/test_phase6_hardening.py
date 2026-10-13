"""Phase 6 Unit Tests: End-to-End Hardening, Fault Injection, and Security Boundary Verification."""

import pytest
import sqlite3
import json
import gc
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient

from src.server import app
from src.models import (
    BenchmarkMode,
    SensorRecord,
    RecordType,
    SensitivityLevel,
    EncryptionAlgorithm,
    EncryptedEnvelope,
)
from src.data_generator import SyntheticDataGenerator
from src.crypto import KeyManager, EncryptionEngine, tamper_envelope
from src.receiver import LocalHealthcareReceiver
from src.benchmark_runner import BenchmarkRunner
from src.run_store import RunStore
from src.power_measurement import CSVPowerImporter


@pytest.fixture
def client():
    return TestClient(app)


def test_sqlite_persistence_across_reloads(tmp_path):
    """Verify that runs and records persist across RunStore instances (app restart simulation)."""
    db_file = str(tmp_path / "test_restart.db")
    store1 = RunStore(db_path=db_file)
    store1.reset()

    runner = BenchmarkRunner()
    gen = SyntheticDataGenerator(seed=101)
    records = gen.generate_batch(count=15)
    metrics = runner.run_single_batch(BenchmarkMode.BASELINE, records, seed=101)

    store1.save_run(metrics, records)
    assert len(store1.list_runs()) == 1

    # Simulate app restart by instantiating new store on same SQLite file
    store2 = RunStore(db_path=db_file)
    reloaded_run = store2.get_run(metrics.run_id)
    assert reloaded_run is not None
    assert reloaded_run.run_id == metrics.run_id
    assert reloaded_run.record_count == 15
    assert reloaded_run.mode == BenchmarkMode.BASELINE

    reloaded_records = store2.get_run_records(metrics.run_id)
    assert len(reloaded_records) == 15
    assert reloaded_records[0]["record_id"] == records[0].record_id


def test_zero_secret_leakage_audit(tmp_path):
    """Security audit: Scan SQLite store and models to guarantee no secret key material is ever persisted."""
    km = KeyManager()
    aes_hex = km.aes_key.hex()
    xor_hex = km.xor_key.hex()
    hmac_hex = km.hmac_key.hex()

    db_file = str(tmp_path / "test_leakage.db")
    store = RunStore(db_path=db_file)
    store.reset()

    runner = BenchmarkRunner(key_manager=km)
    gen = SyntheticDataGenerator(seed=55)
    records = gen.generate_batch(count=20)
    metrics = runner.run_single_batch(BenchmarkMode.ADAPTIVE, records, seed=55)
    store.save_run(metrics, records)

    # Force gc to ensure all connections released
    gc.collect()

    # Read raw database binary content
    with open(db_file, "rb") as f:
        raw_db_bytes = f.read()

    # Assert keys do not exist in binary database file
    assert aes_hex.encode("utf-8") not in raw_db_bytes
    assert xor_hex.encode("utf-8") not in raw_db_bytes
    assert hmac_hex.encode("utf-8") not in raw_db_bytes


def test_corrupt_envelope_handling():
    """Verify receiver robustly handles corrupt envelopes with invalid hex or missing fields."""
    km = KeyManager()
    receiver = LocalHealthcareReceiver(km)

    # 1. Invalid hex in ciphertext
    corrupt_env1 = EncryptedEnvelope(
        run_id="RUN-CORRUPT-1",
        record_id="REC-BAD-1",
        algorithm=EncryptionAlgorithm.AES_256_GCM,
        sensitivity=SensitivityLevel.HIGH,
        cluster_id="CLUSTER-HIGH",
        nonce_hex="0102030405060708090a0b0c",
        ciphertext_hex="NOT_VALID_HEX",
        tag_hex="0102030405060708090a0b0c0d0e0f10",
        payload_bytes=10,
        created_at="2026-10-13T10:00:00Z",
    )
    res1 = receiver.receive_envelope(corrupt_env1)
    assert res1.verified is False
    assert res1.error_message is not None

    # 2. Truncated tag
    corrupt_env2 = EncryptedEnvelope(
        run_id="RUN-CORRUPT-2",
        record_id="REC-BAD-2",
        algorithm=EncryptionAlgorithm.AES_256_GCM,
        sensitivity=SensitivityLevel.HIGH,
        cluster_id="CLUSTER-HIGH",
        nonce_hex="0102030405060708090a0b0c",
        ciphertext_hex="abcd1234",
        tag_hex="01020304",  # Too short (only 4 bytes instead of 16)
        payload_bytes=4,
        created_at="2026-10-13T10:00:00Z",
    )
    res2 = receiver.receive_envelope(corrupt_env2)
    assert res2.verified is False


def test_repeated_comparison_reproducibility():
    """Verify that repeating comparisons with the same seed yields equivalent workloads."""
    runner = BenchmarkRunner()
    comp1 = runner.run_comparison(record_count=25, seed=888, repetitions=2)
    comp2 = runner.run_comparison(record_count=25, seed=888, repetitions=2)

    # Counts must be identical
    assert comp1["record_count"] == comp2["record_count"] == 25
    assert comp1["baseline_summary"].record_count == comp2["baseline_summary"].record_count == 25
    assert comp1["adaptive_summary"].high_sensitivity_count == comp2["adaptive_summary"].high_sensitivity_count
    assert comp1["adaptive_summary"].low_sensitivity_count == comp2["adaptive_summary"].low_sensitivity_count


def test_source_label_honesty():
    """Verify that software estimates never carry hardware measurement tags."""
    runner = BenchmarkRunner()
    gen = SyntheticDataGenerator(seed=12)
    records = gen.generate_batch(count=10)
    metrics = runner.run_single_batch(BenchmarkMode.BASELINE, records, seed=12)

    assert metrics.measurement_source.value == "estimated"
    assert metrics.measurement_source.value != "hardware"
