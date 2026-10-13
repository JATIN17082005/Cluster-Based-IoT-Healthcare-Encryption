"""Synthetic healthcare IoT data generator.
Generates reproducible, synthetic physiological telemetry records with a deterministic random seed.
"""

import random
from datetime import datetime, timezone, timedelta
from typing import List, Optional
import uuid

from src.models import (
    RecordType,
    SensorRecord,
)
from src.classifier import SensitivityClassifier
from src.cluster_manager import ClusterManager


class SyntheticDataGenerator:
    """Generates synthetic IoT healthcare sensor records with strict reproducibility."""

    PATIENT_IDS = [
        "SYNTH-PAT-001",
        "SYNTH-PAT-002",
        "SYNTH-PAT-003",
        "SYNTH-PAT-004",
        "SYNTH-PAT-005",
    ]

    RECORD_TYPE_UNITS = {
        RecordType.HEART_RATE: "bpm",
        RecordType.ECG_SUMMARY: "mV",
        RecordType.TEMPERATURE: "degC",
        RecordType.STEP_COUNT: "steps",
    }

    def __init__(self, seed: Optional[int] = 42):
        self.seed = seed
        self.rng = random.Random(seed)

    def set_seed(self, seed: int):
        """Reset generator seed for reproducibility."""
        self.seed = seed
        self.rng = random.Random(seed)

    def generate_record(
        self,
        index: int,
        base_time: Optional[datetime] = None,
    ) -> SensorRecord:
        """Generate a single synthetic sensor record."""
        if base_time is None:
            # Deterministic base timestamp
            base_time = datetime(2026, 10, 13, 10, 0, 0, tzinfo=timezone.utc)

        record_time = base_time + timedelta(seconds=index)
        patient_id = self.PATIENT_IDS[index % len(self.PATIENT_IDS)]

        # Cycle or sample record types to ensure balanced healthcare data representation
        record_types = [
            RecordType.HEART_RATE,
            RecordType.ECG_SUMMARY,
            RecordType.TEMPERATURE,
            RecordType.STEP_COUNT,
        ]
        rec_type = record_types[index % len(record_types)]

        val = 0.0
        if rec_type == RecordType.HEART_RATE:
            # 70% normal (60-95), 15% bradycardia (<50), 15% tachycardia (>100)
            p = self.rng.random()
            if p < 0.15:
                val = round(self.rng.uniform(38.0, 48.0), 1)  # Bradycardia
            elif p < 0.30:
                val = round(self.rng.uniform(105.0, 140.0), 1)  # Tachycardia
            else:
                val = round(self.rng.uniform(62.0, 92.0), 1)  # Normal
        elif rec_type == RecordType.ECG_SUMMARY:
            # ECG ST segment / peak voltage amplitude
            val = round(self.rng.uniform(0.65, 1.85), 3)
        elif rec_type == RecordType.TEMPERATURE:
            # 80% normal (36.2-37.4), 10% fever (>38.0), 10% hypothermia (<35.5)
            p = self.rng.random()
            if p < 0.10:
                val = round(self.rng.uniform(34.2, 35.3), 2)  # Hypothermia
            elif p < 0.20:
                val = round(self.rng.uniform(38.2, 39.8), 2)  # Fever
            else:
                val = round(self.rng.uniform(36.4, 37.3), 2)  # Normothermia
        elif rec_type == RecordType.STEP_COUNT:
            # Step cadence (0 to 120 steps)
            val = float(self.rng.randint(0, 120))

        # Deterministic record ID based on index and seed
        record_id = f"REC-S{self.seed if self.seed is not None else 0}-{index:05d}"

        return SensorRecord(
            record_id=record_id,
            timestamp=record_time.isoformat(),
            demo_patient_id=patient_id,
            record_type=rec_type,
            value=val,
            unit=self.RECORD_TYPE_UNITS[rec_type],
            is_synthetic=True,
        )

    def generate_batch(
        self,
        count: int = 100,
        classifier: Optional[SensitivityClassifier] = None,
        cluster_manager: Optional[ClusterManager] = None,
    ) -> List[SensorRecord]:
        """Generate a batch of classified and clustered synthetic records."""
        base_time = datetime(2026, 10, 13, 10, 0, 0, tzinfo=timezone.utc)
        records: List[SensorRecord] = [
            self.generate_record(i, base_time) for i in range(count)
        ]

        if classifier:
            classifier.classify_batch(records)

        if cluster_manager and classifier:
            cluster_manager.form_clusters(records)

        return records
