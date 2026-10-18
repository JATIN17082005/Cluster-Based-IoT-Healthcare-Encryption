"""Cluster manager for partitioning sensor records by privacy sensitivity.
Integrates real K-Means machine learning with safety guardrail fallbacks.
Deterministic grouping into CLUSTER-HIGH and CLUSTER-LOW.
"""

from typing import List, Tuple, Optional
from src.models import (
    SensorRecord,
    SensitivityLevel,
    ClusterGroup,
    ClusteringResult,
    FeatureVector,
    KMeansConfig,
)
from src.kmeans_clusterer import KMeansPipeline


class ClusterManager:
    """Partitions classified sensor records into deterministic sensitivity clusters
    using real scikit-learn K-Means machine learning and security safety guardrails.
    """

    CLUSTER_HIGH_ID = "CLUSTER-HIGH"
    CLUSTER_LOW_ID = "CLUSTER-LOW"

    def __init__(self, kmeans_config: Optional[KMeansConfig] = None):
        self.kmeans_pipeline = KMeansPipeline(kmeans_config)
        self.last_clustering_result: Optional[ClusteringResult] = None
        self.last_feature_vectors: List[FeatureVector] = []

    def form_clusters(
        self,
        records: List[SensorRecord],
        run_kmeans: bool = False,
        pipeline_run_id: Optional[str] = None,
    ) -> Tuple[ClusterGroup, ClusterGroup]:
        """Form sensitivity-based clusters from classified records.

        If run_kmeans is True, fits real K-Means on engineered features,
        maps clusters to semantic labels, applies security guardrail, and stores diagnostics.
        If run_kmeans is False (default for backward compatibility), uses rule-based classification.
        Assigns cluster_id to each record and returns high and low cluster groups.
        """
        high_records: List[SensorRecord] = []
        low_records: List[SensorRecord] = []

        if run_kmeans and len(records) > 0:
            run_id = pipeline_run_id or getattr(records[0], "pipeline_run_id", None) or "PIPE-DEFAULT"
            result, feature_vectors = self.kmeans_pipeline.fit_and_cluster(records, pipeline_run_id=run_id)
            self.last_clustering_result = result
            self.last_feature_vectors = feature_vectors

            for record in records:
                if record.cluster_label == self.CLUSTER_HIGH_ID:
                    high_records.append(record)
                else:
                    low_records.append(record)
        else:
            # Rule-based fallback
            for record in records:
                if record.sensitivity == SensitivityLevel.HIGH:
                    record.cluster_id = self.CLUSTER_HIGH_ID
                    record.cluster_label = self.CLUSTER_HIGH_ID
                    record.effective_security_class = SensitivityLevel.HIGH
                    high_records.append(record)
                else:
                    record.cluster_id = self.CLUSTER_LOW_ID
                    record.cluster_label = self.CLUSTER_LOW_ID
                    record.effective_security_class = SensitivityLevel.LOW
                    low_records.append(record)

        high_cluster = ClusterGroup(
            cluster_id=self.CLUSTER_HIGH_ID,
            sensitivity=SensitivityLevel.HIGH,
            records=high_records,
            record_count=len(high_records),
        )

        low_cluster = ClusterGroup(
            cluster_id=self.CLUSTER_LOW_ID,
            sensitivity=SensitivityLevel.LOW,
            records=low_records,
            record_count=len(low_records),
        )

        return high_cluster, low_cluster

    def cluster_with_kmeans(
        self,
        records: List[SensorRecord],
        pipeline_run_id: Optional[str] = None,
        config: Optional[KMeansConfig] = None,
    ) -> Tuple[ClusterGroup, ClusterGroup, Optional[ClusteringResult]]:
        """Explicitly run ML-based K-Means clustering pipeline."""
        if config is not None:
            self.kmeans_pipeline = KMeansPipeline(config)
        high_group, low_group = self.form_clusters(
            records=records,
            run_kmeans=True,
            pipeline_run_id=pipeline_run_id,
        )
        return high_group, low_group, self.last_clustering_result
