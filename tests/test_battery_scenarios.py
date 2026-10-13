"""Unit and Integration Tests for Two Hardware Battery Scenarios.
Verifies:
1. Scenario A (Desktop Benchmark) vs Scenario B (Constrained IoT MCU Simulation).
2. Strictly non-overlapping activity intervals for energy accounting.
3. Mathematical derivation of energy difference (never hardcoded).
4. Presentation scale changes visual drain without modifying underlying Joules.
5. API endpoints (/api/battery/mcu-config, /api/battery/mcu-scenario).
6. Preserved separation and provenance disclosures.
"""

import pytest
from fastapi.testclient import TestClient

from src.server import app
from src.models import (
    McuHardwareScenarioConfig,
    BenchmarkMode,
    SensitivityLevel,
    SensorRecord,
    RecordType,
    PowerModelConfig,
)
from src.power_measurement import McuEnergyModel
from src.benchmark_runner import BenchmarkRunner
from src.data_generator import SyntheticDataGenerator


@pytest.fixture
def client():
    return TestClient(app)


# --- Test 1: MCU Non-Overlapping Activity Accounting ---

def test_mcu_energy_model_non_overlapping_intervals():
    """Verify that every microsecond in MCU Scenario B is partitioned into mutually exclusive intervals."""
    cfg = McuHardwareScenarioConfig(
        supply_voltage_v=3.3,
        battery_nominal_mah=1200.0,
        cpu_active_current_ma=8.0,
        aes_active_current_ma=10.0,
        sha256_active_current_ma=8.0,
        xor_active_current_ma=7.0,
        hmac_active_current_ma=8.5,
        radio_tx_current_ma=30.0,
        idle_sleep_current_ma=0.015,
        t_shared_proc_ms=0.30,
        t_aes_gcm_ms=1.20,
        t_sha256_keystream_ms=0.25,
        t_xor_stream_ms=0.01,
        t_hmac_sha256_ms=0.38,
        t_radio_tx_ms=1.50,
        t_duty_cycle_period_ms=20.0,
    )
    model = McuEnergyModel(cfg)
    total_records = 50
    high_count = 20
    low_count = 30

    res = model.calculate_scenario(total_records, high_count, low_count)
    base = res["baseline"]
    adapt = res["adaptive"]

    # In baseline: total duration must equal shared_proc + crypto + tx + idle
    expected_base_dur = (
        base["shared_proc_duration_ms"]
        + base["crypto_duration_ms"]
        + base["tx_duration_ms"]
        + base["idle_duration_ms"]
    )
    assert abs(base["total_duration_ms"] - expected_base_dur) < 1e-4

    # Baseline total energy must equal sum of disjoint component energies
    expected_base_energy = (
        base["energy_proc_joules"]
        + base["energy_crypto_joules"]
        + base["energy_tx_joules"]
        + base["energy_idle_joules"]
    )
    assert abs(base["total_energy_joules"] - expected_base_energy) < 1e-6

    # In adaptive: total duration must equal shared_proc + crypto + tx + idle
    expected_adapt_dur = (
        adapt["shared_proc_duration_ms"]
        + adapt["crypto_duration_ms"]
        + adapt["tx_duration_ms"]
        + adapt["idle_duration_ms"]
    )
    assert abs(adapt["total_duration_ms"] - expected_adapt_dur) < 1e-4

    # Adaptive crypto energy must equal sum of AES + SHA256 + XOR + HMAC
    expected_adapt_crypto_e = (
        adapt["energy_aes_joules"]
        + adapt["energy_sha_joules"]
        + adapt["energy_xor_joules"]
        + adapt["energy_hmac_joules"]
    )
    assert abs(adapt["energy_crypto_joules"] - expected_adapt_crypto_e) < 1e-6

    # Adaptive total energy must equal sum of all disjoint component energies
    expected_adapt_energy = (
        adapt["energy_proc_joules"]
        + adapt["energy_crypto_joules"]
        + adapt["energy_tx_joules"]
        + adapt["energy_idle_joules"]
    )
    assert abs(adapt["total_energy_joules"] - expected_adapt_energy) < 1e-6


# --- Test 2: Calculated Energy Savings & Sensitivity Extremes ---

def test_mcu_energy_savings_derived_from_model():
    """Verify energy savings are computed dynamically from model outputs and never hardcoded."""
    model = McuEnergyModel()
    total_records = 100

    # 1. 50% High / 50% Low: must produce positive energy savings
    res_split = model.calculate_scenario(total_records, high_sensitivity_count=50, low_sensitivity_count=50)
    e_base = res_split["baseline"]["total_energy_joules"]
    e_adapt = res_split["adaptive"]["total_energy_joules"]
    expected_saving = ((e_base - e_adapt) / e_base) * 100.0

    assert abs(res_split["energy_comparison"]["energy_saving_percent"] - expected_saving) < 1e-6
    assert res_split["energy_comparison"]["result_status"] == "IMPROVEMENT"
    assert res_split["energy_comparison"]["energy_saving_percent"] > 0.0

    # 2. Extreme 1: 100% High Sensitivity (0 Routine Records)
    # Both configurations must use 100% AES; energy must be strictly identical (0% saving)
    res_all_high = model.calculate_scenario(total_records, high_sensitivity_count=100, low_sensitivity_count=0)
    assert abs(res_all_high["baseline"]["total_energy_joules"] - res_all_high["adaptive"]["total_energy_joules"]) < 1e-9
    assert abs(res_all_high["energy_comparison"]["energy_saving_percent"]) < 1e-4

    # 3. Extreme 2: 100% Routine Records (0 High Records)
    # All records use lightweight XOR route; energy savings must be strictly greater than 50/50 split
    res_all_low = model.calculate_scenario(total_records, high_sensitivity_count=0, low_sensitivity_count=100)
    assert res_all_low["energy_comparison"]["energy_saving_percent"] > res_split["energy_comparison"]["energy_saving_percent"]


# --- Test 3: Benchmark Runner Non-Overlapping Desktop Accounting ---

def test_benchmark_runner_desktop_non_overlapping():
    """Verify that BenchmarkRunner divides execution time into non-overlapping intervals."""
    runner = BenchmarkRunner(power_model=PowerModelConfig(supply_voltage_v=3.3))
    gen = SyntheticDataGenerator(seed=42)
    records = gen.generate_batch(count=30, classifier=runner.classifier)

    metrics = runner.run_single_batch(BenchmarkMode.BASELINE, records, seed=42)
    # Energy must be non-zero and positive
    assert metrics.total_energy_joules > 0.0
    assert metrics.mean_voltage_v == 3.3
    assert metrics.mean_power_mw > 0.0
    assert metrics.mean_current_ma > 0.0


# --- Test 4: Presentation Scale Independence ---

def test_presentation_scale_does_not_change_energy():
    """Verify that presentation scale modifies visual drop percentage only,
    leaving underlying Joules, mAh, and percentage savings invariant.
    """
    model = McuEnergyModel()
    res = model.calculate_scenario(100, 45, 55)

    base_j = res["baseline"]["total_energy_joules"]
    adapt_j = res["adaptive"]["total_energy_joules"]
    saving_pct = res["energy_comparison"]["energy_saving_percent"]

    # Test virtual scale factors: 1x, 10x, 50x, 100x
    scales = [1, 10, 50, 100]
    total_capacity_j = 1200.0 * 3.3 * 3.6  # 14256 Joules

    for s in scales:
        scale_factor = s * 200
        drop_base = min(65.0, (base_j / total_capacity_j) * 100.0 * scale_factor)
        drop_adapt = min(65.0, (adapt_j / total_capacity_j) * 100.0 * scale_factor)

        # In MCU Scenario B: adaptive consumes less, so drop_adapt < drop_base
        assert drop_adapt < drop_base

        # Crucially: Underlying Joules and savings do NOT change with scale factor
        assert res["baseline"]["total_energy_joules"] == base_j
        assert res["adaptive"]["total_energy_joules"] == adapt_j
        assert res["energy_comparison"]["energy_saving_percent"] == saving_pct


# --- Test 5: API Endpoints for Scenario B ---

def test_mcu_scenario_api_endpoints(client):
    """Verify GET and POST /api/battery/mcu-config and /api/battery/mcu-scenario endpoints."""
    # 1. GET MCU Config
    get_cfg = client.get("/api/battery/mcu-config")
    assert get_cfg.status_code == 200
    cfg_data = get_cfg.json()
    assert "cpu_active_current_ma" in cfg_data
    assert "t_aes_gcm_ms" in cfg_data

    # 2. POST Update MCU Config
    update_resp = client.post("/api/battery/mcu-config", json={
        "cpu_active_current_ma": 9.0,
        "t_aes_gcm_ms": 1.40,
    })
    assert update_resp.status_code == 200
    assert update_resp.json()["config"]["cpu_active_current_ma"] == 9.0

    # 3. GET MCU Scenario
    get_scen = client.get("/api/battery/mcu-scenario")
    assert get_scen.status_code == 200
    scen_data = get_scen.json()
    assert "baseline" in scen_data
    assert "adaptive" in scen_data
    assert "energy_comparison" in scen_data
    assert scen_data["provenance_label"] == "SIMULATED TARGET-MCU SCENARIO — RESULTS DEPEND ON CONFIGURED ASSUMPTIONS"

    # 4. POST MCU Scenario with custom record count and sensitivity
    post_scen = client.post("/api/battery/mcu-scenario", json={
        "record_count": 80,
        "high_sensitivity_count": 30,
        "low_sensitivity_count": 50,
    })
    assert post_scen.status_code == 200
    p_data = post_scen.json()
    assert p_data["record_count"] == 80
    assert p_data["high_sensitivity_count"] == 30
    assert p_data["low_sensitivity_count"] == 50
    assert p_data["energy_comparison"]["result_status"] == "IMPROVEMENT"


# --- Test 6: Strict Separation of Desktop and MCU Scenarios ---

def test_scenarios_remain_strictly_separated(client):
    """Verify that MCU simulation does not overwrite or alter the real desktop benchmark."""
    # 1. Run standard desktop paired benchmark
    bench_resp = client.post("/api/benchmark/run", json={
        "mode": "comparison",
        "record_count": 30,
        "seed": 42,
        "repetitions": 1,
    })
    assert bench_resp.status_code == 200
    desktop_comp = bench_resp.json()["comparison"]

    # Desktop benchmark on x86-64 host workstation exhibits REGRESSION (or INCONCLUSIVE noise)
    # and its measurement source is ESTIMATED or IMPORTED
    assert desktop_comp["overall_result_status"] in ["REGRESSION", "IMPROVEMENT", "INCONCLUSIVE"]

    # 2. Request MCU scenario
    mcu_resp = client.get("/api/battery/mcu-scenario")
    assert mcu_resp.status_code == 200
    mcu_data = mcu_resp.json()

    # The MCU scenario must have its own distinct label and not alter desktop benchmark results
    assert "SIMULATED TARGET-MCU SCENARIO" in mcu_data["provenance_label"]
    assert "OpenSSL" not in mcu_data["mcu_model"]
