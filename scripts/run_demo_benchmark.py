"""Automated script to run a real demonstration benchmark and export artifacts."""

import os
import sys
import csv
import json
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.benchmark_runner import BenchmarkRunner
from src.run_store import RunStore
from src.models import BenchmarkMode

def main():
    print("=== IoT Healthcare Encryption: Running Seeded Demo Benchmark (Phase 8 Audit) ===")
    store = RunStore(db_path="data/iot_benchmark.db")
    runner = BenchmarkRunner()

    record_count = 50
    seed = 42
    repetitions = 10
    warmup_repetitions = 2

    print(f"Configuration: {record_count} records, Seed: {seed}, Repetitions: {repetitions} (Warmup: {warmup_repetitions})")
    result = runner.run_comparison(
        record_count=record_count,
        seed=seed,
        repetitions=repetitions,
        warmup_repetitions=warmup_repetitions,
    )

    base = result["baseline_summary"]
    adapt = result["adaptive_summary"]

    store.save_run(base)
    store.save_run(adapt)

    enc_pct = result["encryption_time_mean_ms"]["percentage_change"]
    energy_pct = result["total_energy_joules"]["percentage_change"]
    energy_saving_pct = result["total_energy_joules"]["energy_saving_percent"]
    status = result["overall_result_status"]

    print("\n--- Benchmark Results ---")
    print(f"Overall Result Status:          {status}")
    print(f"Measurement Source:             {base.measurement_source.value.upper()}")
    print(f"Baseline Mean Encryption Time:  {base.encryption_time_mean_ms:.6f} ms")
    print(f"Adaptive Mean Encryption Time:  {adapt.encryption_time_mean_ms:.6f} ms")
    print(f"Latency Percentage Change:      {enc_pct:+.2f}% ({result['encryption_time_mean_ms']['direction']})")

    # Verification of mathematical consistency
    expected_enc_pct = ((adapt.encryption_time_mean_ms - base.encryption_time_mean_ms) / base.encryption_time_mean_ms) * 100.0
    print(f"Latency Formula Check:          (({adapt.encryption_time_mean_ms:.6f} - {base.encryption_time_mean_ms:.6f}) / {base.encryption_time_mean_ms:.6f}) * 100 = {expected_enc_pct:+.2f}% [Match: {abs(enc_pct - expected_enc_pct) < 1e-4}]")

    print(f"\nBaseline Total Batch Energy:    {base.total_energy_joules:.6f} J")
    print(f"Adaptive Total Batch Energy:    {adapt.total_energy_joules:.6f} J")
    print(f"Energy Percentage Change:       {energy_pct:+.2f}%")
    print(f"Energy Percentage Saving:       {energy_saving_pct:+.2f}% ({result['total_energy_joules']['direction']})")

    expected_saving_pct = ((base.total_energy_joules - adapt.total_energy_joules) / base.total_energy_joules) * 100.0
    print(f"Energy Saving Formula Check:    (({base.total_energy_joules:.6f} - {adapt.total_energy_joules:.6f}) / {base.total_energy_joules:.6f}) * 100 = {expected_saving_pct:+.2f}% [Match: {abs(energy_saving_pct - expected_saving_pct) < 1e-4}]")

    print(f"\nTransmission Success Rate (TSR): Baseline={base.tsr_percent}%, Adaptive={adapt.tsr_percent}%")
    print(f"Packet Loss Rate (PLR):          Baseline={base.plr_percent}%, Adaptive={adapt.plr_percent}%")

    # Generate sample export artifacts
    exports_dir = Path("exports")
    exports_dir.mkdir(parents=True, exist_ok=True)

    csv_path = exports_dir / "sample_benchmark_run.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "run_id", "mode", "seed", "record_count", "repeat_index",
            "aes_count", "xor_count", "high_sensitivity_count", "low_sensitivity_count",
            "classification_time_total_ms", "clustering_time_total_ms",
            "enc_mean_ms", "enc_median_ms", "enc_p95_ms", "enc_total_ms", "authentication_total_ms",
            "serialization_total_ms", "transmission_total_ms", "end_to_end_duration_ms",
            "records_sent", "records_received", "records_rejected", "records_lost",
            "tsr_percent", "plr_percent", "measurement_source",
            "mean_voltage_v", "mean_current_ma", "mean_power_mw",
            "total_energy_joules", "energy_per_record_mj", "energy_per_100_records_mj", "energy_per_1000_records_mj",
            "estimated_battery_charge_consumed_mah", "estimated_runtime_hours", "started_at", "completed_at", "status"
        ])
        for r in [base, adapt]:
            writer.writerow([
                r.run_id, r.mode.value, r.seed, r.record_count, r.repeat_index,
                r.aes_record_count, r.xor_record_count, r.high_sensitivity_count, r.low_sensitivity_count,
                r.classification_time_total_ms, r.clustering_time_total_ms,
                r.encryption_time_mean_ms, r.encryption_time_median_ms, r.encryption_time_p95_ms, r.encryption_time_total_ms,
                r.authentication_time_total_ms, r.serialization_time_total_ms, r.transmission_time_total_ms, r.end_to_end_duration_ms,
                r.records_sent, r.records_received, r.records_rejected, r.records_lost,
                r.tsr_percent, r.plr_percent, r.measurement_source.value,
                r.mean_voltage_v, r.mean_current_ma, r.mean_power_mw,
                r.total_energy_joules, r.energy_per_record_mj, r.energy_per_100_records_mj, r.energy_per_1000_records_mj,
                r.estimated_battery_charge_consumed_mah or "N/A", r.estimated_runtime_hours or "N/A",
                r.started_at, r.completed_at, r.status
            ])

    json_path = exports_dir / "sample_benchmark_comparison.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=lambda o: o.model_dump() if hasattr(o, "model_dump") else str(o))

    print(f"\nExports written to:\n  - {csv_path}\n  - {json_path}")

if __name__ == "__main__":
    main()
