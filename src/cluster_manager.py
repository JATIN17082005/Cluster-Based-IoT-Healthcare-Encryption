"""Cluster manager for partitioning sensor records by privacy sensitivity.
Deterministic grouping into CLUSTER-HIGH and CLUSTER-LOW.
"""

from typing import List, Tuple
from src.models import (
    SensorRecord,
    SensitivityLevel,
    ClusterGroup,
)


class ClusterManager:
    """Partitions classified sensor records into deterministic sensitivity clusters."""

    CLUSTER_HIGH_ID = "CLUSTER-HIGH"
    CLUSTER_LOW_ID = "CLUSTER-LOW"

    def form_clusters(self, records: List[SensorRecord]) -> Tuple[ClusterGroup, ClusterGroup]:
        """Form sensitivity-based clusters from classified records.

        Assigns cluster_id to each record and returns high and low cluster groups.
        """
        high_records: List[SensorRecord] = []
        low_records: List[SensorRecord] = []

        for record in records:
            if record.sensitivity == SensitivityLevel.HIGH:
                record.cluster_id = self.CLUSTER_HIGH_ID
                high_records.append(record)
            else:
                # Default to low if not marked high
                record.cluster_id = self.CLUSTER_LOW_ID
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
