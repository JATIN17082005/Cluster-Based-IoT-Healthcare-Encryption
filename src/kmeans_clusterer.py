"""Machine-learning K-Means clustering pipeline for IoT healthcare data.
Uses scikit-learn KMeans and StandardScaler with modality-aware feature engineering,
defensible calibration and held-out evaluation, deterministic semantic mapping,
clinical security safety guardrails, and diagnostics.

Academic Notice:
This module performs unsupervised clustering on extracted physiological features.
Sensitivity policies act as an external reference for evaluation and as an inviolable
security safety guardrail to prevent privacy downgrades. Within-run agreement evaluates
concordance against synthetic heuristic policy rules, NOT physical clinical diagnosis.
"""

import math
from typing import List, Dict, Tuple, Optional, Any
import numpy as np
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score

from src.models import (
    SensorRecord,
    RecordType,
    SensitivityLevel,
    KMeansConfig,
    KMeansDiagnostics,
    ClusteringResult,
    FeatureVector,
    ClusterGroup,
)


class HealthcareFeatureExtractor:
    """Extracts modality-aware numerical features from synthetic healthcare sensor records without target leakage.

    Feature Matrix:
    1. type_heart_rate: One-hot indicator for heart rate sensor.
    2. type_ecg_summary: One-hot indicator for ECG summary sensor.
    3. type_temperature: One-hot indicator for body temperature sensor.
    4. type_step_count: One-hot indicator for ambulatory step cadence sensor.
    5. modality_normalized_value: Continuous measurement normalized against its sensor modality's physiological span [0.0, 1.0].
    6. physiological_range_deviation: Normalized distance from resting physiological normal limits.

    Academic Design Note:
    StandardScaler alone cannot make raw bpm (e.g. 75), body temperature in °C (e.g. 37.0),
    ECG voltage in mV (e.g. 1.0), and step counts (e.g. 40) directly comparable when pooled
    in a single raw column. Modality-specific normalization maps each measurement into a dimensionless
    [0.0, 1.0] interval relative to its own physical physiological span before clustering.
    """

    FEATURE_NAMES = [
        "type_heart_rate",
        "type_ecg_summary",
        "type_temperature",
        "type_step_count",
        "modality_normalized_value",
        "physiological_range_deviation",
    ]

    # Physiological physical dynamic spans per sensor modality
    MODALITY_SPANS = {
        RecordType.HEART_RATE: {"min": 30.0, "max": 220.0, "unit": "bpm"},
        RecordType.TEMPERATURE: {"min": 34.0, "max": 42.0, "unit": "degC"},
        RecordType.ECG_SUMMARY: {"min": 0.0, "max": 3.0, "unit": "mV"},
        RecordType.STEP_COUNT: {"min": 0.0, "max": 200.0, "unit": "steps"},
    }

    # Reconciled clinical reference boundaries for deviation calculation
    # Heart Rate: normal [50, 100] bpm, center 75 bpm, scale 25 bpm
    # Temperature: normothermic [35.5, 38.0] °C, center 36.75 °C, scale 1.25 °C
    # ECG Summary: diagnostic peak [0.8, 1.4] mV, center 1.0 mV, scale 0.4 mV
    # Step Count: routine cadence [0, 100] steps, center 30 steps, scale 50 steps
    NORMAL_RANGES = {
        RecordType.HEART_RATE: {"min": 50.0, "max": 100.0, "center": 75.0, "scale": 25.0},
        RecordType.TEMPERATURE: {"min": 35.5, "max": 38.0, "center": 36.75, "scale": 1.25},
        RecordType.ECG_SUMMARY: {"min": 0.8, "max": 1.4, "center": 1.0, "scale": 0.4},
        RecordType.STEP_COUNT: {"min": 0.0, "max": 100.0, "center": 30.0, "scale": 50.0},
    }

    @classmethod
    def validate_and_sanitize_value(cls, rec_type: RecordType, raw_val: Any) -> float:
        """Validate input sensor measurement, handling NaN, Inf, or invalid types safely."""
        try:
            val = float(raw_val)
        except (ValueError, TypeError):
            val = cls.NORMAL_RANGES.get(rec_type, {}).get("center", 0.0)

        if math.isnan(val) or math.isinf(val):
            val = cls.NORMAL_RANGES.get(rec_type, {}).get("center", 0.0)

        # Physical boundary sanity checks
        if rec_type == RecordType.HEART_RATE and val < 0.0:
            val = 0.0
        elif rec_type == RecordType.STEP_COUNT and val < 0.0:
            val = 0.0

        return float(val)

    @classmethod
    def calculate_modality_normalized_value(cls, rec_type: RecordType, value: float) -> float:
        """Normalize measurement within its own modality's physiological span into [0.0, 1.0]."""
        span = cls.MODALITY_SPANS.get(rec_type)
        if not span:
            return 0.0

        span_min = span["min"]
        span_max = span["max"]
        clamped = max(span_min, min(span_max, value))
        return float((clamped - span_min) / (span_max - span_min))

    @classmethod
    def calculate_range_deviation(cls, rec_type: RecordType, value: float) -> float:
        """Compute normalized physiological deviation from expected resting baseline.

        A value within normal bounds has low deviation.
        Extreme abnormal values (e.g. tachycardia 140 bpm, fever 40°C) produce high deviation.
        This provides a continuous physiological signal to K-Means without supplying policy labels.
        """
        ref = cls.NORMAL_RANGES.get(rec_type)
        if not ref:
            return 0.0

        val = float(value)
        if val < ref["min"]:
            return float(abs(ref["min"] - val) / ref["scale"])
        elif val > ref["max"]:
            return float(abs(val - ref["max"]) / ref["scale"])
        else:
            # Within physiological limits, measure distance from clinical midpoint
            return float(abs(val - ref["center"]) / (ref["scale"] * 2.0))

    @classmethod
    def extract_features(cls, record: SensorRecord) -> Dict[str, float]:
        """Extract unscaled feature dictionary for a single record.
        Includes all 6 clustering features plus raw_measurement for traceability and backward compatibility.
        """
        rec_type = record.record_type
        sanitized_val = cls.validate_and_sanitize_value(rec_type, record.value)
        modality_norm = cls.calculate_modality_normalized_value(rec_type, sanitized_val)
        deviation = cls.calculate_range_deviation(rec_type, sanitized_val)

        return {
            "type_heart_rate": 1.0 if rec_type == RecordType.HEART_RATE else 0.0,
            "type_ecg_summary": 1.0 if rec_type == RecordType.ECG_SUMMARY else 0.0,
            "type_temperature": 1.0 if rec_type == RecordType.TEMPERATURE else 0.0,
            "type_step_count": 1.0 if rec_type == RecordType.STEP_COUNT else 0.0,
            "modality_normalized_value": float(modality_norm),
            "physiological_range_deviation": float(deviation),
            "raw_measurement": float(sanitized_val),
        }

    @classmethod
    def build_matrix(cls, records: List[SensorRecord]) -> Tuple[np.ndarray, List[Dict[str, float]]]:
        """Build NumPy feature matrix for a batch of records using FEATURE_NAMES."""
        if not records:
            return np.empty((0, len(cls.FEATURE_NAMES))), []

        dict_list = [cls.extract_features(r) for r in records]
        matrix = np.array(
            [[d[f] for f in cls.FEATURE_NAMES] for d in dict_list],
            dtype=np.float64,
        )
        return matrix, dict_list


class KMeansPipeline:
    """Complete machine-learning clustering pipeline for IoT telemetry.
    1. Feature extraction with modality-aware normalization (no label leakage).
    2. Standardization via StandardScaler.
    3. Defensible calibration and held-out evaluation workflow.
    4. Deterministic semantic mapping to CLUSTER-HIGH and CLUSTER-LOW.
    5. Inviolable security guardrail protecting clinical HIGH records.
    6. Comprehensive diagnostic reporting with explicit limitation disclosures.
    """

    def __init__(self, config: Optional[KMeansConfig] = None):
        self.config = config or KMeansConfig()
        self.scaler = StandardScaler()
        self.kmeans: Optional[KMeans] = None
        self.last_result: Optional[ClusteringResult] = None

    def fit_and_cluster(
        self,
        records: List[SensorRecord],
        pipeline_run_id: str = "PIPE-DEFAULT",
        calibration_ratio: float = 0.5,
    ) -> Tuple[ClusteringResult, List[FeatureVector]]:
        """Fit K-Means, calibrate cluster orientation, evaluate on held-out split,
        apply security guardrails, and return full diagnostics.
        """
        n_records = len(records)
        if n_records == 0:
            raise ValueError("Cannot perform K-Means clustering on an empty record set.")

        warnings: List[str] = []
        effective_k = min(self.config.n_clusters, n_records)

        # 1. Feature Extraction on full batch
        feature_matrix, raw_dicts = HealthcareFeatureExtractor.build_matrix(records)
        dev_idx = HealthcareFeatureExtractor.FEATURE_NAMES.index("physiological_range_deviation")

        # 2. Defensible Calibration / Evaluation Protocol Split
        use_held_out = (n_records >= 10 and 0.1 <= calibration_ratio <= 0.9 and effective_k == 2)
        held_out_agreement: Optional[float] = None
        held_out_confusion: Optional[Dict[str, int]] = None
        cal_count: Optional[int] = None
        eval_count: Optional[int] = None

        if use_held_out:
            cal_count = max(4, int(n_records * calibration_ratio))
            eval_count = n_records - cal_count

            # Calibration partition (training)
            cal_matrix = feature_matrix[:cal_count]
            cal_records = records[:cal_count]

            # Fit scaler and KMeans ONLY on calibration partition
            scaled_cal_matrix = self.scaler.fit_transform(cal_matrix)
            self.kmeans = KMeans(
                n_clusters=effective_k,
                random_state=self.config.random_state,
                n_init=self.config.n_init,
                algorithm=self.config.algorithm,
            )
            cal_labels = self.kmeans.fit_predict(scaled_cal_matrix)

            # Determine semantic mapping purely on calibration data
            cal_devs: Dict[int, float] = {}
            for c_id in range(effective_k):
                mask = (cal_labels == c_id)
                cal_devs[c_id] = float(np.mean(cal_matrix[mask, dev_idx])) if np.any(mask) else 0.0

            d0 = cal_devs.get(0, 0.0)
            d1 = cal_devs.get(1, 0.0)
            dev_separation = abs(d0 - d1)

            cluster_mapping: Dict[str, str] = {}
            if dev_separation < 0.05:
                warnings.append(
                    f"Semantic mapping uncertainty: centroid physiological deviation separation is narrow "
                    f"(|d0 - d1| = {dev_separation:.4f} < 0.05). Inferred semantic polarity may be sensitive to noise."
                )

            if d0 >= d1:
                cluster_mapping["0"] = "CLUSTER-HIGH"
                cluster_mapping["1"] = "CLUSTER-LOW"
            else:
                cluster_mapping["1"] = "CLUSTER-HIGH"
                cluster_mapping["0"] = "CLUSTER-LOW"

            # Held-out evaluation using frozen scaler, frozen kmeans, and frozen mapping
            eval_matrix = feature_matrix[cal_count:]
            eval_records = records[cal_count:]
            scaled_eval_matrix = self.scaler.transform(eval_matrix)
            eval_labels = self.kmeans.predict(scaled_eval_matrix)

            held_out_confusion = {
                "true_high_as_high": 0,
                "true_low_as_low": 0,
                "high_as_low_mismatch": 0,
                "low_as_high_upgrade": 0,
            }
            eval_correct = 0
            for idx, rec in enumerate(eval_records):
                c_id = int(eval_labels[idx])
                c_label = cluster_mapping[str(c_id)]
                policy_sens = rec.sensitivity or SensitivityLevel.LOW

                if policy_sens == SensitivityLevel.HIGH:
                    if c_label == "CLUSTER-HIGH":
                        held_out_confusion["true_high_as_high"] += 1
                        eval_correct += 1
                    else:
                        held_out_confusion["high_as_low_mismatch"] += 1
                else:
                    if c_label == "CLUSTER-LOW":
                        held_out_confusion["true_low_as_low"] += 1
                        eval_correct += 1
                    else:
                        held_out_confusion["low_as_high_upgrade"] += 1

            held_out_agreement = round(eval_correct / max(1, eval_count), 4)

            # Transform the complete batch with the calibration-fitted scaler & model
            scaled_matrix = self.scaler.transform(feature_matrix)
            raw_cluster_labels = self.kmeans.predict(scaled_matrix)

        else:
            # Exploratory fitting on full dataset (e.g. small sample N < 10)
            scaled_matrix = self.scaler.fit_transform(feature_matrix)
            self.kmeans = KMeans(
                n_clusters=effective_k,
                random_state=self.config.random_state,
                n_init=self.config.n_init,
                algorithm=self.config.algorithm,
            )
            raw_cluster_labels = self.kmeans.fit_predict(scaled_matrix)

            # Inferred semantic mapping from full batch centroids
            cluster_devs: Dict[int, float] = {}
            for c_id in range(effective_k):
                mask = (raw_cluster_labels == c_id)
                cluster_devs[c_id] = float(np.mean(feature_matrix[mask, dev_idx])) if np.any(mask) else 0.0

            cluster_mapping = {}
            if effective_k == 2:
                d0 = cluster_devs.get(0, 0.0)
                d1 = cluster_devs.get(1, 0.0)
                if abs(d0 - d1) < 0.05:
                    warnings.append(
                        "Semantic mapping uncertainty: centroid physiological deviation separation is narrow (< 0.05)."
                    )
                if d0 >= d1:
                    cluster_mapping["0"] = "CLUSTER-HIGH"
                    cluster_mapping["1"] = "CLUSTER-LOW"
                else:
                    cluster_mapping["1"] = "CLUSTER-HIGH"
                    cluster_mapping["0"] = "CLUSTER-LOW"
            else:
                cluster_mapping["0"] = "CLUSTER-HIGH"

        # 3. Apply Security Guardrail & Annotate Records
        feature_vectors: List[FeatureVector] = []
        guardrail_overrides = 0
        within_run_confusion = {
            "true_high_as_high": 0,
            "true_low_as_low": 0,
            "high_as_low_mismatch": 0,
            "low_as_high_upgrade": 0,
        }

        for idx, rec in enumerate(records):
            c_id = int(raw_cluster_labels[idx])
            c_label = cluster_mapping[str(c_id)]
            policy_sens = rec.sensitivity or SensitivityLevel.LOW

            # Security Guardrail Logic:
            # Clinical HIGH records must NEVER be downgraded to low encryption path
            if policy_sens == SensitivityLevel.HIGH and c_label == "CLUSTER-LOW":
                effective_sec = SensitivityLevel.HIGH
                override = True
                reason = "Policy guardrail enforced: Clinical HIGH record protected against K-Means cluster downgrade"
                guardrail_overrides += 1
                within_run_confusion["high_as_low_mismatch"] += 1
            elif c_label == "CLUSTER-HIGH":
                effective_sec = SensitivityLevel.HIGH
                override = False
                reason = None
                if policy_sens == SensitivityLevel.HIGH:
                    within_run_confusion["true_high_as_high"] += 1
                else:
                    within_run_confusion["low_as_high_upgrade"] += 1
            else:  # CLUSTER-LOW and policy LOW
                effective_sec = SensitivityLevel.LOW
                override = False
                reason = None
                within_run_confusion["true_low_as_low"] += 1

            # Update record in-place with complete traceability fields
            rec.pipeline_run_id = pipeline_run_id
            rec.kmeans_cluster_id = c_id
            rec.cluster_label = c_label
            rec.cluster_id = c_label  # Backward-compatible link
            rec.policy_sensitivity = policy_sens
            rec.effective_security_class = effective_sec
            rec.policy_override = override
            rec.override_reason = reason

            # Prepare FeatureVector representation for export and UI
            scaled_dict = {
                name: round(float(scaled_matrix[idx, f_idx]), 4)
                for f_idx, name in enumerate(HealthcareFeatureExtractor.FEATURE_NAMES)
            }
            feature_vectors.append(
                FeatureVector(
                    record_id=rec.record_id,
                    record_type=rec.record_type.value,
                    raw_value=float(rec.value),
                    unit=rec.unit,
                    features=raw_dicts[idx],
                    scaled_features=scaled_dict,
                )
            )

        # 4. Compute Comprehensive Diagnostics
        cluster_counts = {str(c_id): int(np.sum(raw_cluster_labels == c_id)) for c_id in range(effective_k)}
        semantic_counts = {
            "CLUSTER-HIGH": sum(1 for r in records if r.cluster_label == "CLUSTER-HIGH"),
            "CLUSTER-LOW": sum(1 for r in records if r.cluster_label == "CLUSTER-LOW"),
        }

        # Calculate cluster centroids in both scaled and original unscaled feature space
        scaled_centroids: Dict[str, Dict[str, float]] = {}
        unscaled_centroids: Dict[str, Dict[str, float]] = {}

        for c_id in range(effective_k):
            c_scaled = self.kmeans.cluster_centers_[c_id]
            c_unscaled = self.scaler.inverse_transform(c_scaled.reshape(1, -1))[0]
            scaled_centroids[str(c_id)] = {
                name: round(float(c_scaled[i]), 4)
                for i, name in enumerate(HealthcareFeatureExtractor.FEATURE_NAMES)
            }
            unscaled_centroids[str(c_id)] = {
                name: round(float(c_unscaled[i]), 4)
                for i, name in enumerate(HealthcareFeatureExtractor.FEATURE_NAMES)
            }

        # Calculate Silhouette Score safely
        sil_score: Optional[float] = None
        sil_note: Optional[str] = None

        if effective_k < self.config.n_clusters:
            warnings.append(
                f"Dataset size ({n_records}) is smaller than requested clusters ({self.config.n_clusters}); "
                f"adjusted effective K to {effective_k}."
            )

        if effective_k > 1 and n_records > effective_k:
            unique_rows = np.unique(scaled_matrix, axis=0)
            if unique_rows.shape[0] > effective_k:
                try:
                    score = float(silhouette_score(scaled_matrix, raw_cluster_labels))
                    sil_score = round(score, 4)
                    if sil_score < 0.20:
                        warnings.append("Low silhouette score (< 0.20) indicates borderline separation between cluster boundaries.")
                except Exception as e:
                    sil_note = f"Silhouette score could not be calculated: {str(e)}"
            else:
                sil_note = "All feature vectors are identical; silhouette score undefined."
                warnings.append("Degenerate feature space: feature vectors lack variance.")
        else:
            sil_note = "Sample count too small for valid silhouette computation (N <= K)."

        # Check for imbalanced clusters (< 5% in any cluster)
        for c_id, count in cluster_counts.items():
            if n_records > 20 and (count / n_records) < 0.05:
                warnings.append(f"Cluster {c_id} is heavily imbalanced ({count}/{n_records} records).")

        # Within-run agreement ratio with synthetic rule-based sensitivity labels
        correct_matches = within_run_confusion["true_high_as_high"] + within_run_confusion["true_low_as_low"]
        within_run_agreement_ratio = round(correct_matches / max(1, n_records), 4)

        if guardrail_overrides > 0:
            warnings.append(
                f"Security guardrail intervened for {guardrail_overrides} record(s): "
                "prevented K-Means from downgrading clinical HIGH records."
            )

        protocol_str = (
            f"CALIBRATION_HELD_OUT_EVALUATION (Calibration: {cal_count}, Held-out: {eval_count})"
            if use_held_out
            else f"WITHIN_RUN_EXPLORATORY (N={n_records})"
        )

        diagnostics = KMeansDiagnostics(
            n_samples=n_records,
            n_features=len(HealthcareFeatureExtractor.FEATURE_NAMES),
            feature_names=HealthcareFeatureExtractor.FEATURE_NAMES,
            cluster_counts=cluster_counts,
            semantic_counts=semantic_counts,
            centroids=scaled_centroids,
            unscaled_centroids=unscaled_centroids,
            inertia=round(float(self.kmeans.inertia_), 4),
            silhouette_score=sil_score,
            silhouette_note=sil_note,
            agreement_metric_label="within-run agreement with synthetic rule-based sensitivity labels",
            agreement_ratio=within_run_agreement_ratio,
            within_run_agreement_ratio=within_run_agreement_ratio,
            evaluation_protocol=protocol_str,
            calibration_sample_count=cal_count,
            held_out_sample_count=eval_count,
            held_out_agreement_ratio=held_out_agreement,
            held_out_confusion_matrix=held_out_confusion,
            semantic_mapping_method="centroid_physiological_deviation",
            limitations_note=(
                "Within-run agreement measures alignment with synthetic rule-based heuristic labels; "
                "this does NOT represent independent clinical diagnostic accuracy or real-world generalization."
            ),
            confusion_matrix=within_run_confusion,
            guardrail_overrides_count=guardrail_overrides,
            warnings=warnings,
        )

        result = ClusteringResult(
            pipeline_run_id=pipeline_run_id,
            config=self.config,
            diagnostics=diagnostics,
            total_records=n_records,
            cluster_mapping=cluster_mapping,
        )
        self.last_result = result
        return result, feature_vectors
