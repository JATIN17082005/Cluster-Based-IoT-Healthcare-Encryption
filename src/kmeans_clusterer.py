"""Machine-learning K-Means clustering pipeline for IoT healthcare data.
Uses scikit-learn KMeans and StandardScaler with feature engineering,
deterministic semantic mapping, security safety guardrail, and diagnostics.

Academic Notice:
This module performs unsupervised clustering on extracted physiological features.
Sensitivity policies act as an external ground-truth reference for semantic evaluation
and as an inviolable security safety guardrail to prevent privacy downgrades.
"""

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
    """Extracts numerical features from synthetic healthcare sensor records without target leakage.

    Feature Matrix:
    1. type_heart_rate: One-hot indicator for heart rate sensor.
    2. type_ecg_summary: One-hot indicator for ECG summary sensor.
    3. type_temperature: One-hot indicator for body temperature sensor.
    4. type_step_count: One-hot indicator for ambulatory step cadence sensor.
    5. raw_measurement: The raw recorded float value.
    6. physiological_range_deviation: Normalized distance from standard resting physiological normal.
    """

    FEATURE_NAMES = [
        "type_heart_rate",
        "type_ecg_summary",
        "type_temperature",
        "type_step_count",
        "raw_measurement",
        "physiological_range_deviation",
    ]

    # Clinical physiological reference boundaries for deviation extraction
    NORMAL_RANGES = {
        RecordType.HEART_RATE: {"min": 50.0, "max": 100.0, "center": 75.0, "scale": 25.0},
        RecordType.TEMPERATURE: {"min": 35.5, "max": 38.0, "center": 36.75, "scale": 1.25},
        RecordType.ECG_SUMMARY: {"min": 0.8, "max": 1.4, "center": 1.0, "scale": 0.4},
        RecordType.STEP_COUNT: {"min": 0.0, "max": 100.0, "center": 30.0, "scale": 50.0},
    }

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
        """Extract unscaled feature dictionary for a single record."""
        rec_type = record.record_type
        deviation = cls.calculate_range_deviation(rec_type, record.value)

        return {
            "type_heart_rate": 1.0 if rec_type == RecordType.HEART_RATE else 0.0,
            "type_ecg_summary": 1.0 if rec_type == RecordType.ECG_SUMMARY else 0.0,
            "type_temperature": 1.0 if rec_type == RecordType.TEMPERATURE else 0.0,
            "type_step_count": 1.0 if rec_type == RecordType.STEP_COUNT else 0.0,
            "raw_measurement": float(record.value),
            "physiological_range_deviation": float(deviation),
        }

    @classmethod
    def build_matrix(cls, records: List[SensorRecord]) -> Tuple[np.ndarray, List[Dict[str, float]]]:
        """Build NumPy feature matrix for a batch of records."""
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
    1. Feature extraction without label leakage.
    2. Standardization via StandardScaler.
    3. Unsupervised K-Means clustering.
    4. Deterministic semantic mapping to CLUSTER-HIGH and CLUSTER-LOW.
    5. Inviolable security guardrail protecting clinical HIGH records.
    6. Comprehensive diagnostic reporting.
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
    ) -> Tuple[ClusteringResult, List[FeatureVector]]:
        """Fit K-Means, transform records, apply security guardrails, and return full diagnostics."""
        n_records = len(records)
        if n_records == 0:
            raise ValueError("Cannot perform K-Means clustering on an empty record set.")

        # 1. Feature Extraction
        feature_matrix, raw_dicts = HealthcareFeatureExtractor.build_matrix(records)

        # 2. Standardization
        scaled_matrix = self.scaler.fit_transform(feature_matrix)

        # 3. K-Means Clustering
        # Handle degenerate case where n_records < n_clusters
        effective_k = min(self.config.n_clusters, n_records)
        self.kmeans = KMeans(
            n_clusters=effective_k,
            random_state=self.config.random_state,
            n_init=self.config.n_init,
            algorithm=self.config.algorithm,
        )
        raw_cluster_labels = self.kmeans.fit_predict(scaled_matrix)

        # 4. Semantic Cluster Label Mapping
        # Map numerical cluster IDs {0, 1} to {"CLUSTER-HIGH", "CLUSTER-LOW"}
        # Evaluate each cluster's proportion of policy-HIGH records (or physiological deviation if policy unavailable)
        cluster_high_proportions: Dict[int, float] = {}
        cluster_mean_deviations: Dict[int, float] = {}

        dev_idx = HealthcareFeatureExtractor.FEATURE_NAMES.index("physiological_range_deviation")

        for c_id in range(effective_k):
            mask = (raw_cluster_labels == c_id)
            c_records = [records[i] for i, m in enumerate(mask) if m]
            if len(c_records) > 0:
                high_count = sum(1 for r in c_records if getattr(r, "sensitivity", None) == SensitivityLevel.HIGH)
                cluster_high_proportions[c_id] = high_count / len(c_records)
                cluster_mean_deviations[c_id] = float(np.mean(feature_matrix[mask, dev_idx]))
            else:
                cluster_high_proportions[c_id] = 0.0
                cluster_mean_deviations[c_id] = 0.0

        # Deterministic semantic assignment
        cluster_mapping: Dict[str, str] = {}
        if effective_k == 2:
            p0 = cluster_high_proportions.get(0, 0.0)
            p1 = cluster_high_proportions.get(1, 0.0)
            if p0 > p1:
                cluster_mapping["0"] = "CLUSTER-HIGH"
                cluster_mapping["1"] = "CLUSTER-LOW"
            elif p1 > p0:
                cluster_mapping["1"] = "CLUSTER-HIGH"
                cluster_mapping["0"] = "CLUSTER-LOW"
            else:
                # Tie-breaking rule: Cluster with higher average physiological range deviation is CLUSTER-HIGH
                d0 = cluster_mean_deviations.get(0, 0.0)
                d1 = cluster_mean_deviations.get(1, 0.0)
                if d0 >= d1:
                    cluster_mapping["0"] = "CLUSTER-HIGH"
                    cluster_mapping["1"] = "CLUSTER-LOW"
                else:
                    cluster_mapping["1"] = "CLUSTER-HIGH"
                    cluster_mapping["0"] = "CLUSTER-LOW"
        else:
            # Single cluster fallback
            cluster_mapping["0"] = "CLUSTER-HIGH" if cluster_high_proportions.get(0, 0.0) > 0.5 else "CLUSTER-LOW"

        # 5. Apply Security Guardrail & Annotate Records
        feature_vectors: List[FeatureVector] = []
        guardrail_overrides = 0
        confusion = {
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
                confusion["high_as_low_mismatch"] += 1
            elif c_label == "CLUSTER-HIGH":
                effective_sec = SensitivityLevel.HIGH
                override = False
                reason = None
                if policy_sens == SensitivityLevel.HIGH:
                    confusion["true_high_as_high"] += 1
                else:
                    confusion["low_as_high_upgrade"] += 1
            else:  # CLUSTER-LOW and policy LOW
                effective_sec = SensitivityLevel.LOW
                override = False
                reason = None
                confusion["true_low_as_low"] += 1

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

        # 6. Compute Comprehensive Diagnostics
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
        warnings: List[str] = []

        if effective_k < self.config.n_clusters:
            warnings.append(f"Dataset size ({n_records}) is smaller than requested clusters ({self.config.n_clusters}); adjusted effective K to {effective_k}.")

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

        # Agreement ratio between semantic K-Means cluster and independent policy
        correct_matches = confusion["true_high_as_high"] + confusion["true_low_as_low"]
        agreement_ratio = round(correct_matches / max(1, n_records), 4)

        if guardrail_overrides > 0:
            warnings.append(
                f"Security guardrail intervened for {guardrail_overrides} record(s): "
                "prevented K-Means from downgrading clinical HIGH records."
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
            agreement_ratio=agreement_ratio,
            confusion_matrix=confusion,
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
