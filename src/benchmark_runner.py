"""Benchmark execution engine.
Orchestrates baseline and adaptive benchmark runs, collects isolated high-resolution timing,
evaluates receiver verification, and computes BatchMetrics and Authoritative Comparative Analytics.
"""

import time
import uuid
import json
from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple, Any
import threading

from src.models import (
    BenchmarkMode,
    EncryptionAlgorithm,
    SensitivityLevel,
    SensorRecord,
    EncryptedEnvelope,
    BatchMetrics,
    MeasurementSource,
    PowerModelConfig,
)
from src.data_generator import SyntheticDataGenerator
from src.classifier import SensitivityClassifier
from src.cluster_manager import ClusterManager
from src.crypto import KeyManager, EncryptionEngine
from src.receiver import LocalHealthcareReceiver
from src.metrics import (
    compute_timing_stats,
    compute_aggregate_stats,
    compute_tsr,
    compute_plr,
    integrate_energy_joules,
    compute_indicative_runtime_hours,
    compute_charge_consumed_mah,
    compute_authoritative_comparison,
    evaluate_result_status,
)


class BenchmarkRunner:
    """Orchestrates controlled baseline and adaptive benchmarking."""

    def __init__(
        self,
        key_manager: Optional[KeyManager] = None,
        receiver: Optional[LocalHealthcareReceiver] = None,
        power_model: Optional[PowerModelConfig] = None,
    ):
        self.key_manager = key_manager or KeyManager()
        self.encryption_engine = EncryptionEngine(self.key_manager)
        self.receiver = receiver or LocalHealthcareReceiver(self.key_manager)
        self.classifier = SensitivityClassifier()
        self.cluster_manager = ClusterManager()
        self.power_model = power_model or PowerModelConfig()

        self._cancel_requested = False
        self._lock = threading.Lock()

    def request_cancellation(self):
        """Request the currently executing benchmark to abort safely."""
        with self._lock:
            self._cancel_requested = True

    def reset_cancellation(self):
        with self._lock:
            self._cancel_requested = False

    def run_single_batch(
        self,
        mode: BenchmarkMode,
        records: List[SensorRecord],
        seed: int,
        repeat_index: int = 1,
        run_id: Optional[str] = None,
        simulate_packet_loss_rate: float = 0.0,
        tamper_first_n_records: int = 0,
        power_samples_override: Optional[Tuple[List[float], List[float], List[float], MeasurementSource]] = None,
    ) -> BatchMetrics:
        """Execute a single batch benchmark run with strictly isolated timing."""
        actual_run_id = run_id or f"RUN-{mode.value.upper()}-{uuid.uuid4().hex[:8]}"

        started_at = datetime.now(timezone.utc).isoformat()
        total_start_ns = time.perf_counter_ns()

        # Step 1 & 2: Measure classification and clustering overhead
        t_class_0 = time.perf_counter_ns()
        self.classifier.classify_batch(records)
        t_class_1 = time.perf_counter_ns()
        classification_time_total_ms = (t_class_1 - t_class_0) / 1_000_000.0

        t_clust_0 = time.perf_counter_ns()
        self.cluster_manager.form_clusters(records)
        t_clust_1 = time.perf_counter_ns()
        clustering_time_total_ms = (t_clust_1 - t_clust_0) / 1_000_000.0

        encryption_times_ms: List[float] = []
        authentication_times_ms: List[float] = []
        serialization_times_ms: List[float] = []
        transmission_times_ms: List[float] = []

        sent_count = 0
        received_count = 0
        accepted_count = 0
        rejected_count = 0
        lost_count = 0

        aes_count = 0
        xor_count = 0
        high_sens_count = 0
        low_sens_count = 0
        total_payload_bytes = 0

        self.receiver.reset_stats(actual_run_id)

        for idx, record in enumerate(records):
            with self._lock:
                if self._cancel_requested:
                    break

            if record.sensitivity == SensitivityLevel.HIGH:
                high_sens_count += 1
            else:
                low_sens_count += 1

            # Decide encryption route
            if mode == BenchmarkMode.BASELINE:
                algorithm = EncryptionAlgorithm.AES_256_GCM
            else:
                if record.sensitivity == SensitivityLevel.HIGH:
                    algorithm = EncryptionAlgorithm.AES_256_GCM
                else:
                    algorithm = EncryptionAlgorithm.XOR_LIGHTWEIGHT

            if algorithm == EncryptionAlgorithm.AES_256_GCM:
                aes_count += 1
            else:
                xor_count += 1

            # 1. Measure Serialization time separately (isolated from pure cryptography)
            t0 = time.perf_counter_ns()
            serialized_bytes = json.dumps(
                record.model_dump(), sort_keys=True
            ).encode("utf-8")
            t1 = time.perf_counter_ns()
            serialization_times_ms.append((t1 - t0) / 1_000_000.0)

            # 2. Measure Pure Cryptographic Encryption time (isolated from JSON I/O and network)
            t_enc_0 = time.perf_counter_ns()
            envelope = self.encryption_engine.encrypt_record(
                record=record,
                run_id=actual_run_id,
                algorithm=algorithm,
                pre_serialized_bytes=serialized_bytes,
            )
            t_enc_1 = time.perf_counter_ns()
            enc_duration_ms = (t_enc_1 - t_enc_0) / 1_000_000.0
            encryption_times_ms.append(enc_duration_ms)
            total_payload_bytes += envelope.payload_bytes

            # Measure authentication stage if applicable (HMAC for XOR)
            if algorithm == EncryptionAlgorithm.XOR_LIGHTWEIGHT:
                auth_ms = self.encryption_engine.xor_service.last_auth_time_ns / 1_000_000.0
                authentication_times_ms.append(auth_ms)
            else:
                authentication_times_ms.append(0.0)

            sent_count += 1

            # Apply intentional tamper if configured for demo verification
            if idx < tamper_first_n_records:
                from src.crypto import tamper_envelope
                envelope = tamper_envelope(envelope, target="ciphertext")

            # 3. Measure Transmission / Receiver ingestion time
            t_tx_0 = time.perf_counter_ns()
            if simulate_packet_loss_rate > 0.0 and (idx % int(1.0 / simulate_packet_loss_rate) == 0):
                lost_count += 1
                t_tx_1 = time.perf_counter_ns()
                transmission_times_ms.append((t_tx_1 - t_tx_0) / 1_000_000.0)
                continue

            received_count += 1
            verification = self.receiver.receive_envelope(envelope)
            t_tx_1 = time.perf_counter_ns()
            transmission_times_ms.append((t_tx_1 - t_tx_0) / 1_000_000.0)

            if verification.verified:
                accepted_count += 1
            else:
                rejected_count += 1

        total_end_ns = time.perf_counter_ns()
        end_to_end_duration_ms = (total_end_ns - total_start_ns) / 1_000_000.0
        completed_at = datetime.now(timezone.utc).isoformat()

        # Compute isolated timing stats
        enc_mean, enc_median, enc_p95, enc_total = compute_timing_stats(encryption_times_ms)
        ser_total = sum(serialization_times_ms)
        auth_total = sum(authentication_times_ms)
        tx_total = sum(transmission_times_ms)

        # Transmission metrics
        tsr = compute_tsr(sent_count, accepted_count)
        plr = compute_plr(sent_count, received_count)

        # Energy & Power evaluation
        if power_samples_override:
            voltages, currents, timestamps, source = power_samples_override
            total_joules, mean_v, mean_i, mean_p = integrate_energy_joules(
                voltages, currents, timestamps
            )
        else:
            source = MeasurementSource.ESTIMATED
            mean_v = self.power_model.supply_voltage_v

            enc_active_s = enc_total / 1000.0
            tx_active_s = (sent_count * self.power_model.tx_duration_ms_per_packet) / 1000.0
            total_duration_s = max(0.001, end_to_end_duration_ms / 1000.0)

            # Non-overlapping activity intervals:
            # 1. Dedicated crypto active intervals for AES and XOR routes
            aes_enc_s = (enc_total * (aes_count / max(1, sent_count))) / 1000.0
            xor_enc_s = (enc_total * (xor_count / max(1, sent_count))) / 1000.0

            # 2. Shared non-crypto CPU processing interval (serialization, clustering, classification)
            # Subtract crypto and TX intervals from total duration to guarantee non-overlapping accounting
            proc_active_s = max(0.0, total_duration_s - (aes_enc_s + xor_enc_s + tx_active_s))

            energy_proc_j = (mean_v * (self.power_model.active_mcu_current_ma / 1000.0)) * proc_active_s
            energy_aes_j = (mean_v * (self.power_model.aes_crypto_current_ma / 1000.0)) * aes_enc_s
            energy_xor_j = (mean_v * (self.power_model.xor_crypto_current_ma / 1000.0)) * xor_enc_s
            energy_tx_j = (mean_v * (self.power_model.tx_current_ma / 1000.0)) * tx_active_s

            total_joules = energy_proc_j + energy_aes_j + energy_xor_j + energy_tx_j
            mean_p = (total_joules / total_duration_s) * 1000.0  # mW
            mean_i = mean_p / mean_v  # mA

        energy_per_rec_mj = (total_joules * 1000.0) / max(1, sent_count)
        energy_per_100_rec_mj = energy_per_rec_mj * 100.0
        energy_per_1000_rec_mj = energy_per_rec_mj * 1000.0

        runtime_hours = compute_indicative_runtime_hours(
            self.power_model.battery_nominal_mah,
            self.power_model.battery_usable_factor,
            mean_i,
        )
        total_duration_s = max(0.001, end_to_end_duration_ms / 1000.0)
        charge_consumed_mah = compute_charge_consumed_mah(mean_i, total_duration_s)

        return BatchMetrics(
            run_id=actual_run_id,
            mode=mode,
            seed=seed,
            record_count=len(records),
            repeat_index=repeat_index,
            high_sensitivity_count=high_sens_count,
            low_sensitivity_count=low_sens_count,
            aes_record_count=aes_count,
            xor_record_count=xor_count,
            total_payload_bytes=total_payload_bytes,
            classification_time_total_ms=round(classification_time_total_ms, 6),
            clustering_time_total_ms=round(clustering_time_total_ms, 6),
            encryption_time_mean_ms=enc_mean,
            encryption_time_median_ms=enc_median,
            encryption_time_p95_ms=enc_p95,
            encryption_time_total_ms=enc_total,
            authentication_time_total_ms=round(auth_total, 6),
            serialization_time_total_ms=round(ser_total, 6),
            transmission_time_total_ms=round(tx_total, 6),
            end_to_end_duration_ms=round(end_to_end_duration_ms, 6),
            records_sent=sent_count,
            records_received=received_count,
            records_rejected=rejected_count,
            records_lost=lost_count,
            tsr_percent=tsr,
            plr_percent=plr,
            measurement_source=source,
            mean_voltage_v=round(mean_v, 4),
            mean_current_ma=round(mean_i, 4),
            mean_power_mw=round(mean_p, 4),
            total_energy_joules=round(total_joules, 6),
            energy_per_record_mj=round(energy_per_rec_mj, 6),
            energy_per_100_records_mj=round(energy_per_100_rec_mj, 6),
            energy_per_1000_records_mj=round(energy_per_1000_rec_mj, 6),
            estimated_battery_charge_consumed_mah=charge_consumed_mah,
            estimated_runtime_hours=runtime_hours,
            started_at=started_at,
            completed_at=completed_at,
            status="CANCELLED" if self._cancel_requested else "COMPLETED",
        )

    def run_comparison(
        self,
        record_count: int = 100,
        seed: int = 42,
        repetitions: int = 10,
        warmup_repetitions: int = 2,
    ) -> Dict[str, Any]:
        """Execute paired comparison runs with warmup, multi-repetition distribution stats,
        and authoritative unrounded percentage change / energy savings.
        """
        gen = SyntheticDataGenerator(seed=seed)
        records = gen.generate_batch(
            count=record_count,
            classifier=self.classifier,
            cluster_manager=self.cluster_manager,
        )

        # 1. Warm-up runs to stabilize JIT, CPU governor, and crypto caches
        for _ in range(warmup_repetitions):
            if self._cancel_requested:
                break
            self.run_single_batch(BenchmarkMode.BASELINE, records, seed=seed, run_id="WARMUP-BASE")
            self.run_single_batch(BenchmarkMode.ADAPTIVE, records, seed=seed, run_id="WARMUP-ADAPT")

        baseline_runs: List[BatchMetrics] = []
        adaptive_runs: List[BatchMetrics] = []

        # 2. Measured repetitions (at least 10 in production review benchmarks)
        for rep in range(1, repetitions + 1):
            if self._cancel_requested:
                break
            base_metrics = self.run_single_batch(
                mode=BenchmarkMode.BASELINE,
                records=records,
                seed=seed,
                repeat_index=rep,
            )
            baseline_runs.append(base_metrics)

            adapt_metrics = self.run_single_batch(
                mode=BenchmarkMode.ADAPTIVE,
                records=records,
                seed=seed,
                repeat_index=rep,
            )
            adaptive_runs.append(adapt_metrics)

        n_reps = len(baseline_runs)
        if n_reps == 0:
            return {"error": "Benchmark was cancelled before completing any repetitions"}

        # 3. Compute multi-repetition distribution stats
        base_enc_means = [r.encryption_time_mean_ms for r in baseline_runs]
        adapt_enc_means = [r.encryption_time_mean_ms for r in adaptive_runs]
        base_enc_medians = [r.encryption_time_median_ms for r in baseline_runs]
        adapt_enc_medians = [r.encryption_time_median_ms for r in adaptive_runs]
        base_energies = [r.total_energy_joules for r in baseline_runs]
        adapt_energies = [r.total_energy_joules for r in adaptive_runs]
        base_tsrs = [r.tsr_percent for r in baseline_runs]
        adapt_tsrs = [r.tsr_percent for r in adaptive_runs]
        base_plrs = [r.plr_percent for r in baseline_runs]
        adapt_plrs = [r.plr_percent for r in adaptive_runs]

        base_enc_agg = compute_aggregate_stats(base_enc_means)
        adapt_enc_agg = compute_aggregate_stats(adapt_enc_means)
        base_energy_agg = compute_aggregate_stats(base_energies)
        adapt_energy_agg = compute_aggregate_stats(adapt_energies)
        base_tsr_agg = compute_aggregate_stats(base_tsrs)
        adapt_tsr_agg = compute_aggregate_stats(adapt_tsrs)
        base_plr_agg = compute_aggregate_stats(base_plrs)
        adapt_plr_agg = compute_aggregate_stats(adapt_plrs)

        # 4. Authoritative comparison calculated on aggregate values
        mean_base_enc = base_enc_agg["mean"]
        mean_adapt_enc = adapt_enc_agg["mean"]
        mean_base_energy = base_energy_agg["mean"]
        mean_adapt_energy = adapt_energy_agg["mean"]
        mean_base_tsr = base_tsr_agg["mean"]
        mean_adapt_tsr = adapt_tsr_agg["mean"]
        mean_base_plr = base_plr_agg["mean"]
        mean_adapt_plr = adapt_plr_agg["mean"]

        comp_enc = compute_authoritative_comparison(
            mean_base_enc, mean_adapt_enc, "Mean Encryption Time", lower_is_better=True, is_energy_metric=False
        )
        comp_enc_median = compute_authoritative_comparison(
            compute_aggregate_stats(base_enc_medians)["median"],
            compute_aggregate_stats(adapt_enc_medians)["median"],
            "Median Encryption Time",
            lower_is_better=True,
            is_energy_metric=False,
        )
        comp_energy = compute_authoritative_comparison(
            mean_base_energy, mean_adapt_energy, "Total Energy", lower_is_better=True, is_energy_metric=True
        )
        comp_tsr = compute_authoritative_comparison(
            mean_base_tsr, mean_adapt_tsr, "Transmission Success Rate", lower_is_better=False, is_energy_metric=False
        )
        comp_plr = compute_authoritative_comparison(
            mean_base_plr, mean_adapt_plr, "Packet Loss Rate", lower_is_better=True, is_energy_metric=False
        )

        # Aggregate representative summaries for export and UI
        # Ensure values match the aggregate means exactly so no discrepancies exist!
        last_base = baseline_runs[-1]
        last_adapt = adaptive_runs[-1]

        base_summary = last_base.model_copy(update={
            "encryption_time_mean_ms": mean_base_enc,
            "encryption_time_median_ms": compute_aggregate_stats(base_enc_medians)["median"],
            "total_energy_joules": mean_base_energy,
            "energy_per_record_mj": (mean_base_energy * 1000.0) / record_count,
            "energy_per_100_records_mj": (mean_base_energy * 1000.0 * 100.0) / record_count,
            "energy_per_1000_records_mj": (mean_base_energy * 1000.0 * 1000.0) / record_count,
            "tsr_percent": mean_base_tsr,
            "plr_percent": mean_base_plr,
        })

        adapt_summary = last_adapt.model_copy(update={
            "encryption_time_mean_ms": mean_adapt_enc,
            "encryption_time_median_ms": compute_aggregate_stats(adapt_enc_medians)["median"],
            "total_energy_joules": mean_adapt_energy,
            "energy_per_record_mj": (mean_adapt_energy * 1000.0) / record_count,
            "energy_per_100_records_mj": (mean_adapt_energy * 1000.0 * 100.0) / record_count,
            "energy_per_1000_records_mj": (mean_adapt_energy * 1000.0 * 1000.0) / record_count,
            "tsr_percent": mean_adapt_tsr,
            "plr_percent": mean_adapt_plr,
        })

        overall_status = evaluate_result_status(mean_base_energy, mean_adapt_energy, lower_is_better=True)

        return {
            "repetitions": n_reps,
            "warmup_repetitions": warmup_repetitions,
            "record_count": record_count,
            "seed": seed,
            "measurement_source": baseline_runs[0].measurement_source.value,
            "overall_result_status": overall_status,
            "encryption_time_mean_ms": comp_enc,
            "encryption_time_median_ms": comp_enc_median,
            "total_energy_joules": comp_energy,
            "tsr_percent": comp_tsr,
            "plr_percent": comp_plr,
            "baseline_aggregate": {
                "encryption_mean": base_enc_agg,
                "energy_mean": base_energy_agg,
                "tsr": base_tsr_agg,
                "plr": base_plr_agg,
            },
            "adaptive_aggregate": {
                "encryption_mean": adapt_enc_agg,
                "energy_mean": adapt_energy_agg,
                "tsr": adapt_tsr_agg,
                "plr": adapt_plr_agg,
            },
            "baseline_summary": base_summary,
            "adaptive_summary": adapt_summary,
            "all_baseline_runs": baseline_runs,
            "all_adaptive_runs": adaptive_runs,
        }
