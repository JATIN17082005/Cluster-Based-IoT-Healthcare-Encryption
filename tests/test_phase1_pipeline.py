"""Phase 1 Unit Tests: Data Generation, Classification, and Deterministic Clustering."""

import pytest
from src.models import (
    RecordType,
    SensitivityLevel,
    SensorRecord,
)
from src.data_generator import SyntheticDataGenerator
from src.classifier import SensitivityClassifier, get_default_ruleset
from src.cluster_manager import ClusterManager


def test_generator_reproducibility():
    """Verify that identical seeds produce byte-for-byte identical batches."""
    gen1 = SyntheticDataGenerator(seed=12345)
    batch1 = gen1.generate_batch(count=50)

    gen2 = SyntheticDataGenerator(seed=12345)
    batch2 = gen2.generate_batch(count=50)

    assert len(batch1) == len(batch2) == 50
    for r1, r2 in zip(batch1, batch2):
        assert r1.record_id == r2.record_id
        assert r1.record_type == r2.record_type
        assert r1.value == r2.value
        assert r1.unit == r2.unit
        assert r1.timestamp == r2.timestamp
        assert r1.demo_patient_id == r2.demo_patient_id
        assert r1.is_synthetic is True


def test_generator_different_seeds():
    """Verify that different seeds produce distinct datasets."""
    gen1 = SyntheticDataGenerator(seed=100)
    batch1 = gen1.generate_batch(count=20)

    gen2 = SyntheticDataGenerator(seed=999)
    batch2 = gen2.generate_batch(count=20)

    # Values should differ between different seeds
    values1 = [r.value for r in batch1]
    values2 = [r.value for r in batch2]
    assert values1 != values2


def test_classification_rules():
    """Verify deterministic rule outcomes and human-readable explanations."""
    classifier = SensitivityClassifier()

    # 1. ECG is always HIGH
    rec_ecg = SensorRecord(
        record_id="T1",
        timestamp="2026-10-13T10:00:00Z",
        demo_patient_id="P1",
        record_type=RecordType.ECG_SUMMARY,
        value=1.1,
        unit="mV",
    )
    classified_ecg = classifier.classify_record(rec_ecg)
    assert classified_ecg.sensitivity == SensitivityLevel.HIGH
    assert "ECG rhythm summary" in classified_ecg.classification_reason

    # 2. Step count is always LOW
    rec_steps = SensorRecord(
        record_id="T2",
        timestamp="2026-10-13T10:00:00Z",
        demo_patient_id="P1",
        record_type=RecordType.STEP_COUNT,
        value=85.0,
        unit="steps",
    )
    classified_steps = classifier.classify_record(rec_steps)
    assert classified_steps.sensitivity == SensitivityLevel.LOW
    assert "ambulatory step count" in classified_steps.classification_reason

    # 3. Heart rate: normal vs bradycardia vs tachycardia
    hr_normal = SensorRecord(
        record_id="T3",
        timestamp="2026-10-13T10:00:00Z",
        demo_patient_id="P1",
        record_type=RecordType.HEART_RATE,
        value=72.0,
        unit="bpm",
    )
    assert classifier.classify_record(hr_normal).sensitivity == SensitivityLevel.LOW

    hr_brady = SensorRecord(
        record_id="T4",
        timestamp="2026-10-13T10:00:00Z",
        demo_patient_id="P1",
        record_type=RecordType.HEART_RATE,
        value=42.0,
        unit="bpm",
    )
    assert classifier.classify_record(hr_brady).sensitivity == SensitivityLevel.HIGH
    assert "Abnormal heart rate" in hr_brady.classification_reason

    hr_tachy = SensorRecord(
        record_id="T5",
        timestamp="2026-10-13T10:00:00Z",
        demo_patient_id="P1",
        record_type=RecordType.HEART_RATE,
        value=125.0,
        unit="bpm",
    )
    assert classifier.classify_record(hr_tachy).sensitivity == SensitivityLevel.HIGH

    # 4. Temperature: normal vs fever vs hypothermia
    temp_normal = SensorRecord(
        record_id="T6",
        timestamp="2026-10-13T10:00:00Z",
        demo_patient_id="P1",
        record_type=RecordType.TEMPERATURE,
        value=36.8,
        unit="degC",
    )
    assert classifier.classify_record(temp_normal).sensitivity == SensitivityLevel.LOW

    temp_fever = SensorRecord(
        record_id="T7",
        timestamp="2026-10-13T10:00:00Z",
        demo_patient_id="P1",
        record_type=RecordType.TEMPERATURE,
        value=39.1,
        unit="degC",
    )
    assert classifier.classify_record(temp_fever).sensitivity == SensitivityLevel.HIGH

    temp_hypo = SensorRecord(
        record_id="T8",
        timestamp="2026-10-13T10:00:00Z",
        demo_patient_id="P1",
        record_type=RecordType.TEMPERATURE,
        value=34.8,
        unit="degC",
    )
    assert classifier.classify_record(temp_hypo).sensitivity == SensitivityLevel.HIGH


def test_cluster_formation():
    """Verify that clustering preserves every record and partitions deterministically."""
    gen = SyntheticDataGenerator(seed=42)
    classifier = SensitivityClassifier()
    cluster_mgr = ClusterManager()

    records = gen.generate_batch(count=100, classifier=classifier, cluster_manager=cluster_mgr)
    high_group, low_group = cluster_mgr.form_clusters(records)

    # Acceptance criteria: sum of clusters equals total batch
    assert high_group.record_count + low_group.record_count == len(records)
    assert high_group.record_count > 0
    assert low_group.record_count > 0

    # Every record belongs to exactly one cluster
    for rec in high_group.records:
        assert rec.sensitivity == SensitivityLevel.HIGH
        assert rec.cluster_id == ClusterManager.CLUSTER_HIGH_ID

    for rec in low_group.records:
        assert rec.sensitivity == SensitivityLevel.LOW
        assert rec.cluster_id == ClusterManager.CLUSTER_LOW_ID
