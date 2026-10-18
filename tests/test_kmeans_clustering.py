"""Unit tests for ML-based K-Means clustering pipeline, feature engineering,
semantic cluster mapping, diagnostics, and security guardrails.
"""

import pytest
import numpy as np
from src.models import (
    SensorRecord,
    RecordType,
    SensitivityLevel,
    KMeansConfig,
)
from src.data_generator import SyntheticDataGenerator
from src.classifier import SensitivityClassifier
from src.kmeans_clusterer import HealthcareFeatureExtractor, KMeansPipeline
from src.cluster_manager import ClusterManager


def test_feature_extractor_no_label_leakage():
    """Verify that feature extraction uses only physiological data and contains NO sensitivity labels."""
    record = SensorRecord(
        record_id="REC-TEST-001",
        timestamp="2026-10-13T10:00:00Z",
        demo_patient_id="SYNTH-PAT-001",
        record_type=RecordType.HEART_RATE,
        value=115.0,
        unit="bpm",
        sensitivity=SensitivityLevel.HIGH,
        classification_reason="Tachycardia alert",
    )

    feat_dict = HealthcareFeatureExtractor.extract_features(record)
    assert "sensitivity" not in feat_dict
    assert "classification_reason" not in feat_dict
    assert "label" not in feat_dict
    assert "policy" not in feat_dict

    # Check extracted values
    assert feat_dict["type_heart_rate"] == 1.0
    assert feat_dict["type_temperature"] == 0.0
    assert feat_dict["raw_measurement"] == 115.0
    assert feat_dict["physiological_range_deviation"] > 0.0  # Above 100 bpm boundary


def test_feature_extractor_all_modalities():
    """Verify feature extraction across all four sensor modalities."""
    gen = SyntheticDataGenerator(seed=42)
    classifier = SensitivityClassifier()
    records = gen.generate_batch(count=20, classifier=classifier)

    matrix, dict_list = HealthcareFeatureExtractor.build_matrix(records)
    assert matrix.shape == (20, len(HealthcareFeatureExtractor.FEATURE_NAMES))
    assert len(dict_list) == 20

    for d in dict_list:
        assert len(d) == len(HealthcareFeatureExtractor.FEATURE_NAMES)
        for val in d.values():
            assert not np.isnan(val)
            assert not np.isinf(val)


def test_kmeans_pipeline_fit_and_clusters():
    """Verify that KMeansPipeline genuinely fits scikit-learn KMeans and clusters records."""
    gen = SyntheticDataGenerator(seed=42)
    classifier = SensitivityClassifier()
    records = gen.generate_batch(count=100, classifier=classifier)

    pipeline = KMeansPipeline(KMeansConfig(n_clusters=2, random_state=42, n_init=10))
    result, feature_vectors = pipeline.fit_and_cluster(records, pipeline_run_id="PIPE-TEST-42")

    assert result.pipeline_run_id == "PIPE-TEST-42"
    assert result.total_records == 100
    assert len(feature_vectors) == 100

    # Cluster assignments
    diag = result.diagnostics
    assert sum(diag.cluster_counts.values()) == 100
    assert sum(diag.semantic_counts.values()) == 100

    # Centroids
    assert len(diag.unscaled_centroids) == 2
    assert len(diag.centroids) == 2
    for centroid in diag.unscaled_centroids.values():
        assert len(centroid) == len(HealthcareFeatureExtractor.FEATURE_NAMES)

    # Silhouette score is calculated and bounded
    if diag.silhouette_score is not None:
        assert -1.0 <= diag.silhouette_score <= 1.0


def test_safety_guardrail_prevents_high_downgrade():
    """Verify that a clinical HIGH record assigned to CLUSTER-LOW is NEVER downgraded to LOW route."""
    # Create synthetic abnormal record
    high_record = SensorRecord(
        record_id="REC-TAMPER-TEST",
        timestamp="2026-10-13T10:00:00Z",
        demo_patient_id="SYNTH-PAT-001",
        record_type=RecordType.TEMPERATURE,
        value=39.5,  # High fever
        unit="°C",
        sensitivity=SensitivityLevel.HIGH,
        classification_reason="High fever requiring clinical monitoring",
    )
    routine_records = [
        SensorRecord(
            record_id=f"REC-ROUTINE-{i}",
            timestamp="2026-10-13T10:00:00Z",
            demo_patient_id="SYNTH-PAT-002",
            record_type=RecordType.STEP_COUNT,
            value=float(i * 5),
            unit="steps",
            sensitivity=SensitivityLevel.LOW,
            classification_reason="Routine step count",
        )
        for i in range(15)
    ]

    all_records = [high_record] + routine_records
    pipeline = KMeansPipeline()
    result, _ = pipeline.fit_and_cluster(all_records, pipeline_run_id="PIPE-GUARDRAIL-TEST")

    # The high record must have effective_security_class == HIGH regardless of cluster assignment
    assert high_record.effective_security_class == SensitivityLevel.HIGH
    if high_record.cluster_label == "CLUSTER-LOW":
        assert high_record.policy_override is True
        assert high_record.override_reason is not None
        assert "Clinical HIGH" in high_record.override_reason


def test_kmeans_deterministic_reproducibility():
    """Verify that identical seed and configuration produce identical cluster results."""
    gen1 = SyntheticDataGenerator(seed=123)
    c1 = SensitivityClassifier()
    recs1 = gen1.generate_batch(count=50, classifier=c1)

    gen2 = SyntheticDataGenerator(seed=123)
    c2 = SensitivityClassifier()
    recs2 = gen2.generate_batch(count=50, classifier=c2)

    pipe1 = KMeansPipeline(KMeansConfig(random_state=42))
    res1, _ = pipe1.fit_and_cluster(recs1, "PIPE-1")

    pipe2 = KMeansPipeline(KMeansConfig(random_state=42))
    res2, _ = pipe2.fit_and_cluster(recs2, "PIPE-2")

    assert res1.diagnostics.cluster_counts == res2.diagnostics.cluster_counts
    assert res1.diagnostics.semantic_counts == res2.diagnostics.semantic_counts
    for r1, r2 in zip(recs1, recs2):
        assert r1.kmeans_cluster_id == r2.kmeans_cluster_id
        assert r1.cluster_label == r2.cluster_label
        assert r1.effective_security_class == r2.effective_security_class


def test_kmeans_degenerate_dataset_handling():
    """Verify that single-record or empty batches do not crash K-Means."""
    pipeline = KMeansPipeline()
    with pytest.raises(ValueError):
        pipeline.fit_and_cluster([], "PIPE-EMPTY")

    single_record = [
        SensorRecord(
            record_id="REC-SINGLE",
            timestamp="2026-10-13T10:00:00Z",
            demo_patient_id="SYNTH-PAT-001",
            record_type=RecordType.HEART_RATE,
            value=72.0,
            unit="bpm",
            sensitivity=SensitivityLevel.LOW,
            classification_reason="Normal resting heart rate",
        )
    ]
    res_single, fv_single = pipeline.fit_and_cluster(single_record, "PIPE-SINGLE")
    assert res_single.total_records == 1
    assert len(res_single.diagnostics.warnings) > 0
