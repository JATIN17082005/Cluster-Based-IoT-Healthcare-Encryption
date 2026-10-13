"""Phase 3 Unit Tests: Baseline Benchmark Engine and Authoritative Metrics."""

import pytest
from src.models import (
    BenchmarkMode,
    EncryptionAlgorithm,
    SensitivityLevel,
)
from src.metrics import (
    compute_timing_stats,
    compute_tsr,
    compute_plr,
    compute_percentage_change,
    integrate_energy_joules,
)
from src.benchmark_runner import BenchmarkRunner
from src.data_generator import SyntheticDataGenerator
from src.classifier import SensitivityClassifier
from src.cluster_manager import ClusterManager


def test_tsr_and_plr_formulas():
    """Verify transmission formula calculations and edge case handling."""
    # 1. Normal case: 100 sent, 95 accepted, 98 received (2 lost, 3 rejected)
    assert compute_tsr(100, 95) == 95.0
    assert compute_plr(100, 98) == 2.0

    # 2. Zero records sent: must not divide by zero
    assert compute_tsr(0, 0) == 0.0
    assert compute_plr(0, 0) == 0.0

    # 3. 100% loss
    assert compute_tsr(50, 0) == 0.0
    assert compute_plr(50, 0) == 100.0

    # 4. Perfect delivery
    assert compute_tsr(50, 50) == 100.0
    assert compute_plr(50, 50) == 0.0


def test_timing_stats():
    """Verify mean, median, and p95 percentile calculations."""
    samples = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    mean, median, p95, total = compute_timing_stats(samples)
    assert mean == 5.5
    assert median == 5.5
    assert p95 == 10.0
    assert total == 55.0

    # Empty list handling
    assert compute_timing_stats([]) == (0.0, 0.0, 0.0, 0.0)


def test_percentage_change_directions():
    """Verify percentage change signs and direction semantics."""
    # 1. Latency reduced from 10ms to 6ms (-40% is better)
    res_lat = compute_percentage_change(10.0, 6.0, lower_is_better=True)
    assert res_lat["percent_change"] == -40.0
    assert res_lat["is_improvement"] is True
    assert "REDUCED (BETTER)" in res_lat["direction"]

    # 2. Energy increased from 10J to 12J (+20% is worse)
    res_energy = compute_percentage_change(10.0, 12.0, lower_is_better=True)
    assert res_energy["percent_change"] == 20.0
    assert res_energy["is_improvement"] is False
    assert "INCREASED (WORSE)" in res_energy["direction"]

    # 3. TSR increased from 90% to 99% (+10% is better)
    res_tsr = compute_percentage_change(90.0, 99.0, lower_is_better=False)
    assert res_tsr["percent_change"] == 10.0
    assert res_tsr["is_improvement"] is True
    assert "INCREASED (BETTER)" in res_tsr["direction"]

    # 4. Baseline zero edge case
    res_zero = compute_percentage_change(0.0, 5.0, lower_is_better=True)
    assert res_zero["percent_change"] == 0.0


def test_paired_benchmark_execution():
    """Verify that paired benchmark comparison executes with identical record counts and seed."""
    runner = BenchmarkRunner()
    result = runner.run_comparison(record_count=30, seed=777, repetitions=1)

    assert "baseline_summary" in result
    assert "adaptive_summary" in result
    base = result["baseline_summary"]
    adapt = result["adaptive_summary"]

    # Both modes processed exactly 30 records
    assert base.record_count == 30
    assert adapt.record_count == 30
    assert base.seed == 777
    assert adapt.seed == 777

    # In baseline mode, ALL 30 records used AES-256-GCM
    assert base.aes_record_count == 30
    assert base.xor_record_count == 0

    # In adaptive mode, records were split based on sensitivity
    assert adapt.aes_record_count + adapt.xor_record_count == 30
    assert adapt.aes_record_count == adapt.high_sensitivity_count
    assert adapt.xor_record_count == adapt.low_sensitivity_count

    # Isolated timers must be positive
    assert base.encryption_time_mean_ms >= 0.0
    assert base.serialization_time_total_ms >= 0.0
    assert base.transmission_time_total_ms >= 0.0


def test_benchmark_cancellation():
    """Verify that cancellation stops execution safely."""
    runner = BenchmarkRunner()
    gen = SyntheticDataGenerator(seed=42)
    records = gen.generate_batch(count=100)

    # Cancel immediately
    runner.request_cancellation()
    metrics = runner.run_single_batch(BenchmarkMode.BASELINE, records, seed=42)
    assert metrics.status == "CANCELLED"
    assert metrics.records_sent == 0
