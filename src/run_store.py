"""Local SQLite storage for benchmark runs, records, and power measurements.
Ensures 100% offline local operation without external databases.
"""

import sqlite3
import json
from typing import List, Dict, Optional, Any
from pathlib import Path
from src.models import (
    BatchMetrics,
    SensorRecord,
    BenchmarkMode,
    MeasurementSource,
)


from contextlib import contextmanager


class RunStore:
    """SQLite run store for persisting benchmark metadata and metrics."""

    def __init__(self, db_path: str = "data/iot_benchmark.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    mode TEXT NOT NULL,
                    seed INTEGER NOT NULL,
                    record_count INTEGER NOT NULL,
                    repeat_index INTEGER NOT NULL,
                    high_count INTEGER NOT NULL,
                    low_count INTEGER NOT NULL,
                    aes_count INTEGER NOT NULL,
                    xor_count INTEGER NOT NULL,
                    payload_bytes INTEGER NOT NULL,
                    enc_mean_ms REAL NOT NULL,
                    enc_median_ms REAL NOT NULL,
                    enc_p95_ms REAL NOT NULL,
                    enc_total_ms REAL NOT NULL,
                    ser_total_ms REAL NOT NULL,
                    tx_total_ms REAL NOT NULL,
                    e2e_duration_ms REAL NOT NULL,
                    records_sent INTEGER NOT NULL,
                    records_received INTEGER NOT NULL,
                    records_rejected INTEGER NOT NULL,
                    records_lost INTEGER NOT NULL,
                    tsr_percent REAL NOT NULL,
                    plr_percent REAL NOT NULL,
                    measurement_source TEXT NOT NULL,
                    mean_voltage_v REAL NOT NULL,
                    mean_current_ma REAL NOT NULL,
                    mean_power_mw REAL NOT NULL,
                    total_energy_j REAL NOT NULL,
                    energy_per_rec_mj REAL NOT NULL,
                    energy_per_100_rec_mj REAL NOT NULL,
                    estimated_runtime_hours REAL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    raw_metrics_json TEXT NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    record_id TEXT NOT NULL,
                    record_type TEXT NOT NULL,
                    value REAL NOT NULL,
                    unit TEXT NOT NULL,
                    sensitivity TEXT NOT NULL,
                    classification_reason TEXT NOT NULL,
                    cluster_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES runs (run_id)
                )
            """)
            conn.commit()

    def save_run(self, metrics: BatchMetrics, records: Optional[List[SensorRecord]] = None):
        """Persist a completed batch run and its records."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO runs (
                    run_id, mode, seed, record_count, repeat_index,
                    high_count, low_count, aes_count, xor_count, payload_bytes,
                    enc_mean_ms, enc_median_ms, enc_p95_ms, enc_total_ms,
                    ser_total_ms, tx_total_ms, e2e_duration_ms,
                    records_sent, records_received, records_rejected, records_lost,
                    tsr_percent, plr_percent, measurement_source,
                    mean_voltage_v, mean_current_ma, mean_power_mw,
                    total_energy_j, energy_per_rec_mj, energy_per_100_rec_mj,
                    estimated_runtime_hours, started_at, completed_at, status,
                    raw_metrics_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                metrics.run_id,
                metrics.mode.value,
                metrics.seed,
                metrics.record_count,
                metrics.repeat_index,
                metrics.high_sensitivity_count,
                metrics.low_sensitivity_count,
                metrics.aes_record_count,
                metrics.xor_record_count,
                metrics.total_payload_bytes,
                metrics.encryption_time_mean_ms,
                metrics.encryption_time_median_ms,
                metrics.encryption_time_p95_ms,
                metrics.encryption_time_total_ms,
                metrics.serialization_time_total_ms,
                metrics.transmission_time_total_ms,
                metrics.end_to_end_duration_ms,
                metrics.records_sent,
                metrics.records_received,
                metrics.records_rejected,
                metrics.records_lost,
                metrics.tsr_percent,
                metrics.plr_percent,
                metrics.measurement_source.value,
                metrics.mean_voltage_v,
                metrics.mean_current_ma,
                metrics.mean_power_mw,
                metrics.total_energy_joules,
                metrics.energy_per_record_mj,
                metrics.energy_per_100_records_mj,
                metrics.estimated_runtime_hours,
                metrics.started_at,
                metrics.completed_at,
                metrics.status,
                metrics.model_dump_json(),
            ))

            if records:
                for rec in records:
                    cursor.execute("""
                        INSERT INTO records (
                            run_id, record_id, record_type, value, unit,
                            sensitivity, classification_reason, cluster_id, timestamp
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        metrics.run_id,
                        rec.record_id,
                        rec.record_type.value,
                        rec.value,
                        rec.unit,
                        rec.sensitivity.value if rec.sensitivity else "LOW",
                        rec.classification_reason or "",
                        rec.cluster_id or "",
                        rec.timestamp,
                    ))

            conn.commit()

    def get_run(self, run_id: str) -> Optional[BatchMetrics]:
        """Fetch a run by run_id."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT raw_metrics_json FROM runs WHERE run_id = ?", (run_id,))
            row = cursor.fetchone()
            if row:
                data = json.loads(row["raw_metrics_json"])
                return BatchMetrics(**data)
            return None

    def list_runs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """List summary of recent runs."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT run_id, mode, seed, record_count, repeat_index,
                       enc_mean_ms, total_energy_j, energy_per_rec_mj, tsr_percent, plr_percent,
                       measurement_source, started_at, status
                FROM runs
                ORDER BY started_at DESC
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def get_run_records(self, run_id: str) -> List[Dict[str, Any]]:
        """Fetch records associated with a run."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT record_id, record_type, value, unit, sensitivity,
                       classification_reason, cluster_id, timestamp
                FROM records
                WHERE run_id = ?
            """, (run_id,))
            return [dict(row) for row in cursor.fetchall()]

    def reset(self):
        """Clear all stored runs and records."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM records")
            cursor.execute("DELETE FROM runs")
            conn.commit()
