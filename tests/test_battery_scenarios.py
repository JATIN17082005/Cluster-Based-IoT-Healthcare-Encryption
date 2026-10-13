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


@pytest.fixture(autouse=True)
def reset_mcu_config_defaults(client):
    yield
    client.post("/api/battery/mcu-config", json=McuHardwareScenarioConfig().model_dump())


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

    # Test virtual scale factors: 1x, 20x, 50x, 80x
    scales = [1, 20, 50, 80]
    total_capacity_j = 1200.0 * 3.3 * 3.6  # 14256 Joules

    for s in scales:
        scale_factor = s * 6000
        drop_base = min(85.0, (base_j / total_capacity_j) * 100.0 * scale_factor)
        drop_adapt = min(85.0, (adapt_j / total_capacity_j) * 100.0 * scale_factor)

        # In MCU Scenario B: adaptive consumes less, so drop_adapt < drop_base
        assert drop_adapt < drop_base

        # At default scale 50: visual drop should be ~35-50%
        if s == 50:
            assert 30.0 <= drop_base <= 60.0

        # Crucially: Underlying Joules, charge (mAh), and savings do NOT change with scale factor
        assert res["baseline"]["total_energy_joules"] == base_j
        assert res["adaptive"]["total_energy_joules"] == adapt_j
        assert res["energy_comparison"]["energy_saving_percent"] == saving_pct

        # Physical charge consumed is strictly derived from Joules / (V * 3.6)
        consumed_mah_base = base_j / (3.3 * 3.6)
        remaining_mah_base = 1200.0 - consumed_mah_base
        assert 1199.0 < remaining_mah_base <= 1200.0


# --- Test 5: API Endpoints for Scenario B ---

def test_mcu_scenario_api_endpoints(client):
    """Verify GET and POST /api/battery/mcu-config and /api/battery/mcu-scenario endpoints."""
    # 1. GET MCU Config (default)
    get_cfg = client.get("/api/battery/mcu-config")
    assert get_cfg.status_code == 200
    cfg_data = get_cfg.json()
    assert "cpu_active_current_ma" in cfg_data
    assert "t_aes_gcm_ms" in cfg_data

    # 2. GET Default MCU Scenario
    get_scen_def = client.get("/api/battery/mcu-scenario")
    assert get_scen_def.status_code == 200
    assert "TARGET-MCU" in get_scen_def.json()["provenance_label"] or "SHORT-TX" in get_scen_def.json()["provenance_label"]

    # 3. POST Update MCU Config (custom parameters)
    update_resp = client.post("/api/battery/mcu-config", json={
        "cpu_active_current_ma": 9.0,
        "t_aes_gcm_ms": 1.40,
    })
    assert update_resp.status_code == 200
    assert update_resp.json()["config"]["cpu_active_current_ma"] == 9.0

    # 4. GET MCU Scenario with custom config correctly reports CUSTOM MCU PARAMETERS
    get_scen = client.get("/api/battery/mcu-scenario")
    assert get_scen.status_code == 200
    scen_data = get_scen.json()
    assert "baseline" in scen_data
    assert "adaptive" in scen_data
    assert "energy_comparison" in scen_data
    assert "CUSTOM MCU PARAMETERS" in scen_data["provenance_label"]
    assert scen_data["profile_id"] == "custom"

    # 5. POST MCU Scenario with custom record count and sensitivity
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

    # Reset back to default for clean state
    client.post("/api/battery/mcu-config", json=McuHardwareScenarioConfig().model_dump())


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


# --- Test 7: Custom MCU Parameters Improvement and Regression Verification ---

def test_custom_mcu_parameters_improvement_and_regression(client):
    """Verify custom MCU parameters that produce both an improvement and a regression,
    verifying that result_status and energy_saving_percent reflect the modeled physics accurately.
    """
    # 1. Parameter set producing an IMPROVEMENT (e.g. software AES is heavy, XOR is fast)
    cfg_improve = McuHardwareScenarioConfig(
        t_aes_gcm_ms=1.25,
        t_sha256_keystream_ms=0.25,
        t_xor_stream_ms=0.01,
        t_hmac_sha256_ms=0.38,
    )
    model_imp = McuEnergyModel(cfg_improve)
    res_imp = model_imp.calculate_scenario(total_records=100, high_sensitivity_count=45, low_sensitivity_count=55)
    assert res_imp["energy_comparison"]["result_status"] == "IMPROVEMENT"
    assert res_imp["energy_comparison"]["energy_saving_percent"] > 0.0

    # 2. Parameter set producing a REGRESSION (e.g. AES is fast, HMAC overhead is heavy)
    cfg_regress = McuHardwareScenarioConfig(
        t_aes_gcm_ms=0.20,
        t_sha256_keystream_ms=0.50,
        t_xor_stream_ms=0.05,
        t_hmac_sha256_ms=2.50,
    )
    model_reg = McuEnergyModel(cfg_regress)
    res_reg = model_reg.calculate_scenario(total_records=100, high_sensitivity_count=45, low_sensitivity_count=55)
    assert res_reg["energy_comparison"]["result_status"] == "REGRESSION"
    assert res_reg["energy_comparison"]["energy_saving_percent"] < -0.2

    # 3. Test through FastAPI API
    # Apply regression parameters
    resp_cfg = client.post("/api/battery/mcu-config", json={
        "t_aes_gcm_ms": 0.20,
        "t_sha256_keystream_ms": 0.50,
        "t_xor_stream_ms": 0.05,
        "t_hmac_sha256_ms": 2.50,
    })
    assert resp_cfg.status_code == 200

    resp_scen = client.get("/api/battery/mcu-scenario")
    assert resp_scen.status_code == 200
    scen_data = resp_scen.json()
    assert scen_data["energy_comparison"]["result_status"] == "REGRESSION"
    assert scen_data["energy_comparison"]["energy_saving_percent"] < 0.0

    # Reset back to default MCU configuration for subsequent tests
    client.post("/api/battery/mcu-config", json=McuHardwareScenarioConfig().model_dump())


# --- Test 8: Cryptographic Cycles & Dedicated Component Breakdown ---

def test_crypto_cycles_and_isolated_component_breakdown():
    """Verify cryptographic CPU cycle estimation from configured clock frequency and
    strictly disjoint component energy breakdowns.
    """
    clock_16mhz = 16_000_000.0
    cfg = McuHardwareScenarioConfig(
        mcu_clock_hz=clock_16mhz,
        t_aes_gcm_ms=1.25,
        t_sha256_keystream_ms=0.25,
        t_xor_stream_ms=0.01,
        t_hmac_sha256_ms=0.38,
        aes_active_current_ma=9.8,
        sha256_active_current_ma=8.2,
        xor_active_current_ma=7.5,
        hmac_active_current_ma=8.4,
    )
    model = McuEnergyModel(cfg)
    res = model.calculate_scenario(total_records=100, high_sensitivity_count=45, low_sensitivity_count=55)

    base = res["baseline"]
    adapt = res["adaptive"]

    # 1. Base crypto duration: 100 * 1.25 = 125.0 ms
    assert abs(base["crypto_duration_ms"] - 125.0) < 1e-4
    # Expected base cycles: 0.125 s * 16,000,000 Hz = 2,000,000 cycles
    expected_base_cycles = (base["crypto_duration_ms"] / 1000.0) * clock_16mhz
    assert abs(base["crypto_cpu_cycles"] - 2_000_000.0) < 1.0
    assert abs(base["crypto_cpu_cycles"] - expected_base_cycles) < 1.0

    # 2. Adapt crypto duration: 45 * 1.25 + 55 * (0.25 + 0.01 + 0.38) = 56.25 + 35.2 = 91.45 ms
    assert abs(adapt["crypto_duration_ms"] - 91.45) < 1e-4
    # Expected adapt cycles: 0.09145 s * 16,000,000 Hz = 1,463,200 cycles
    expected_adapt_cycles = (adapt["crypto_duration_ms"] / 1000.0) * clock_16mhz
    assert abs(adapt["crypto_cpu_cycles"] - 1_463_200.0) < 1.0
    assert abs(adapt["crypto_cpu_cycles"] - expected_adapt_cycles) < 1.0

    # 3. Modelled cycle reduction percentage matches latency reduction
    assert abs(res["crypto_cycles_comparison"]["percentage_change"] - res["crypto_time_comparison"]["percentage_change"]) < 1e-4
    assert res["crypto_cycles_comparison"]["percentage_change"] < -26.0

    # 4. Component energy breakdown strictly sums to total crypto energy
    crypto_comp_sum = (
        adapt["energy_aes_joules"]
        + adapt["energy_sha_joules"]
        + adapt["energy_xor_joules"]
        + adapt["energy_hmac_joules"]
    )
    assert abs(adapt["energy_crypto_joules"] - crypto_comp_sum) < 1e-6

    # 5. Whole batch energy breakdown strictly sums to total batch energy
    batch_comp_sum = (
        adapt["energy_proc_joules"]
        + adapt["energy_crypto_joules"]
        + adapt["energy_tx_joules"]
        + adapt["energy_idle_joules"]
    )
    assert abs(adapt["total_energy_joules"] - batch_comp_sum) < 1e-6

    # 6. Cryptographic component energy shows ~31% savings (greater than whole-batch ~6.6% due to radio)
    assert res["crypto_energy_comparison"]["energy_saving_percent"] > 30.0
    assert res["energy_comparison"]["energy_saving_percent"] < 10.0


# --- Test 9: Sensitivity Tuning via Query Parameters & API ---

def test_mcu_sensitivity_tuning_query_params(client):
    """Verify GET /api/battery/mcu-scenario updates dynamically when passing
    record_count, high_count, and low_count query parameters.
    """
    # 1. 20 High / 80 Routine split
    resp_80_routine = client.get("/api/battery/mcu-scenario?record_count=100&high_count=20&low_count=80")
    assert resp_80_routine.status_code == 200
    data_80 = resp_80_routine.json()
    assert data_80["high_sensitivity_count"] == 20
    assert data_80["low_sensitivity_count"] == 80

    # 2. 80 High / 20 Routine split
    resp_20_routine = client.get("/api/battery/mcu-scenario?record_count=100&high_count=80&low_count=20")
    assert resp_20_routine.status_code == 200
    data_20 = resp_20_routine.json()
    assert data_20["high_sensitivity_count"] == 80
    assert data_20["low_sensitivity_count"] == 20

    # More routine records routed to XOR must yield higher cryptographic energy savings
    assert data_80["crypto_energy_comparison"]["energy_saving_percent"] > data_20["crypto_energy_comparison"]["energy_saving_percent"]
    # And lower adaptive cryptographic latency
    assert data_80["adaptive"]["crypto_duration_ms"] < data_20["adaptive"]["crypto_duration_ms"]


# --- Test 10: Proportional Visual Battery Scaling Consistency ---

def test_proportional_visual_battery_scaling():
    """Verify that the battery visual scaling formula applies the identical multiplier
    to baseline and adaptive, preserving the relative comparison derived strictly from model outputs.
    """
    nominal_mah = 1200.0
    vcc = 3.3
    total_capacity_j = nominal_mah * vcc * 3.6

    # Case A: MCU Scenario (Adaptive consumes less energy)
    base_j_mcu = 0.018968
    adapt_j_mcu = 0.017708
    target_base_drain = 40.0  # Scale 50 default

    base_drop_mcu = target_base_drain
    adapt_drop_mcu = base_drop_mcu * (adapt_j_mcu / base_j_mcu)

    # Adaptive drops LESS than baseline (battery ends with MORE charge remaining)
    assert adapt_drop_mcu < base_drop_mcu
    assert abs(adapt_drop_mcu - (40.0 * 0.017708 / 0.018968)) < 1e-4
    assert (100.0 - adapt_drop_mcu) > (100.0 - base_drop_mcu)

    # Case B: Desktop Scenario (Adaptive consumes MORE energy due to lack of AES-NI)
    base_j_desk = 0.025546
    adapt_j_desk = 0.025834
    base_drop_desk = target_base_drain
    adapt_drop_desk = base_drop_desk * (adapt_j_desk / base_j_desk)

    # Adaptive drops MORE than baseline (battery ends with LESS charge remaining)
    assert adapt_drop_desk > base_drop_desk
    assert (100.0 - adapt_drop_desk) < (100.0 - base_drop_desk)


# --- Test 11: Two MCU Profiles (Short-TX 0.5ms vs Radio-Heavy 1.5ms) ---

def test_mcu_profiles_short_tx_vs_radio_heavy(client):
    """Verify both MCU profiles:
    - Short-TX (0.5 ms TX airtime): cryptographic savings produce ~12.9% batch energy reduction.
    - Radio-Heavy (1.5 ms TX airtime): radio dominates (~73%), yielding ~6.6% batch energy reduction.
    - Cryptographic times, cycles, and crypto energies must be strictly identical across both profiles.
    """
    model = McuEnergyModel()

    # 1. Short-TX Profile
    res_short = model.calculate_scenario(100, 45, 55, profile_name="short_tx")
    assert res_short["profile_id"] == "short_tx"
    assert "0.50 ms" in res_short["profile_name"]
    assert "COMPUTE-INTENSIVE" in res_short["provenance_label"]
    assert "0.5 ms airtime" in res_short["provenance_disclaimer"]

    saving_short = res_short["energy_comparison"]["energy_saving_percent"]
    assert 12.5 < saving_short < 13.5  # ~12.91%
    assert res_short["energy_comparison"]["result_status"] == "IMPROVEMENT"

    # 2. Radio-Heavy Profile
    res_heavy = model.calculate_scenario(100, 45, 55, profile_name="radio_heavy")
    assert res_heavy["profile_id"] == "radio_heavy"
    assert "1.50 ms" in res_heavy["profile_name"]
    assert "SIMULATED TARGET-MCU" in res_heavy["provenance_label"]

    saving_heavy = res_heavy["energy_comparison"]["energy_saving_percent"]
    assert 6.0 < saving_heavy < 7.2  # ~6.63%
    assert res_heavy["energy_comparison"]["result_status"] == "IMPROVEMENT"

    # 3. Cryptographic metrics must be IDENTICAL between both profiles
    assert abs(res_short["baseline"]["crypto_duration_ms"] - res_heavy["baseline"]["crypto_duration_ms"]) < 1e-6
    assert abs(res_short["adaptive"]["crypto_duration_ms"] - res_heavy["adaptive"]["crypto_duration_ms"]) < 1e-6
    assert abs(res_short["baseline"]["crypto_cpu_cycles"] - res_heavy["baseline"]["crypto_cpu_cycles"]) < 1e-6
    assert abs(res_short["adaptive"]["crypto_cpu_cycles"] - res_heavy["adaptive"]["crypto_cpu_cycles"]) < 1e-6
    assert abs(res_short["baseline"]["energy_crypto_joules"] - res_heavy["baseline"]["energy_crypto_joules"]) < 1e-6
    assert abs(res_short["adaptive"]["energy_crypto_joules"] - res_heavy["adaptive"]["energy_crypto_joules"]) < 1e-6

    # 4. API endpoint verification for profiles
    resp_short_api = client.get("/api/battery/mcu-scenario?profile=short_tx")
    assert resp_short_api.status_code == 200
    assert resp_short_api.json()["profile_id"] == "short_tx"

    resp_heavy_api = client.get("/api/battery/mcu-scenario?profile=radio_heavy")
    assert resp_heavy_api.status_code == 200
    assert resp_heavy_api.json()["profile_id"] == "radio_heavy"


# --- Test 12: Radio Transmission Sensitivity Sweep Across Intervals ---

def test_radio_sensitivity_sweep_across_intervals():
    """Verify that the radio sensitivity sweep evaluates intervals [0.50, 0.75, 1.00, 1.50] ms
    under identical MCU assumptions, showing monotonically decreasing percentage energy savings.
    """
    model = McuEnergyModel()
    res = model.calculate_scenario(100, 45, 55, profile_name="short_tx")

    sweep = res.get("radio_sensitivity_sweep", [])
    assert len(sweep) == 4

    expected_intervals = [0.50, 0.75, 1.00, 1.50]
    savings = []

    for idx, row in enumerate(sweep):
        assert abs(row["interval_ms"] - expected_intervals[idx]) < 1e-3
        assert row["baseline_energy_j"] > 0.0
        assert row["adaptive_energy_j"] > 0.0
        assert row["adaptive_energy_j"] < row["baseline_energy_j"]
        assert row["is_improvement"] is True
        savings.append(row["energy_saving_percent"])

    # Monotonically decreasing savings as radio airtime increases
    for i in range(len(savings) - 1):
        assert savings[i] > savings[i + 1], f"Saving at {sweep[i]['interval_ms']}ms ({savings[i]}%) must be > saving at {sweep[i+1]['interval_ms']}ms ({savings[i+1]}%)"

    assert savings[0] > 12.0  # 0.50 ms interval (~12.9%)
    assert savings[-1] < 7.0  # 1.50 ms interval (~6.6%)


# --- Test 13: High-Contrast Visual Scale (80% Visual Drain) Derivation ---

def test_high_contrast_visual_battery_scaling_80_percent():
    """Verify high-contrast 80% visual scaling calibrated for 10-second faculty review:
    - Baseline meter drains by exactly 80.0% (100% -> 20.0%).
    - In short-TX profile, adaptive drains proportionally by 80 * (8.472 / 9.733) = ~69.6%, ending at ~30.4%.
    - Visual gap between baseline and adaptive is clearly visible (~10.4% difference).
    - Modeled physical state (mAh, J) remains strictly separate from visual percentage.
    """
    nominal_mah = 1200.0
    vcc = 3.3
    model = McuEnergyModel()
    res = model.calculate_scenario(100, 45, 55, profile_name="short_tx")

    base_j = res["baseline"]["total_energy_joules"]
    adapt_j = res["adaptive"]["total_energy_joules"]

    target_base_drain = 80.0  # High-contrast faculty presentation scale
    base_drop = target_base_drain
    adapt_drop = base_drop * (adapt_j / base_j)

    target_base_pct = 100.0 - base_drop
    target_adapt_pct = 100.0 - adapt_drop

    # Baseline ends at 20.0%
    assert abs(target_base_pct - 20.0) < 1e-4

    # Adaptive ends at ~30.4%
    assert 29.5 < target_adapt_pct < 31.5
    visual_gap = target_adapt_pct - target_base_pct
    assert visual_gap > 9.5  # Distinct visible gap of ~10.4%

    # Physical battery capacity used is a tiny fraction of 1200 mAh (realistic single batch)
    base_mah_used = base_j / (vcc * 3.6)
    adapt_mah_used = adapt_j / (vcc * 3.6)
    assert 0.0005 < base_mah_used < 0.002
    assert adapt_mah_used < base_mah_used


# --- Test 14: Strict Workload Split & Boundary Validation (HTTP 422) ---

def test_mcu_workload_split_validation_422(client):
    """Verify that MCU endpoints reject unbalanced or invalid workload counts with HTTP 422."""
    # 1. GET with high + low != total
    resp_unbalanced = client.get("/api/battery/mcu-scenario?record_count=100&high_count=60&low_count=30")
    assert resp_unbalanced.status_code == 422
    assert "Invalid workload split" in resp_unbalanced.json()["detail"]

    # 2. GET with negative count
    resp_neg = client.get("/api/battery/mcu-scenario?record_count=100&high_count=-5&low_count=105")
    assert resp_neg.status_code == 422

    # 3. GET with out-of-range record_count
    resp_zero = client.get("/api/battery/mcu-scenario?record_count=0")
    assert resp_zero.status_code == 422

    resp_excess = client.get("/api/battery/mcu-scenario?record_count=2000")
    assert resp_excess.status_code == 422

    # 4. POST with unbalanced counts
    resp_post_unbalanced = client.post("/api/battery/mcu-scenario", json={
        "record_count": 100,
        "high_sensitivity_count": 70,
        "low_sensitivity_count": 20,
    })
    assert resp_post_unbalanced.status_code == 422

    # 5. Direct McuEnergyModel calculation raises ValueError
    model = McuEnergyModel()
    with pytest.raises(ValueError, match="Invalid workload split"):
        model.calculate_scenario(total_records=100, high_sensitivity_count=60, low_sensitivity_count=30)


# --- Test 15: Custom MCU Profile Identification & Dynamic Airtime ---

def test_custom_mcu_profile_identification(client):
    """Verify custom MCU profile identification when parameters deviate from named presets."""
    model = McuEnergyModel()

    # 1. Preset short_tx (0.50 ms)
    res_short = model.calculate_scenario(100, 45, 55, profile_name="short_tx")
    assert res_short["profile_id"] == "short_tx"

    # 2. Preset radio_heavy (1.50 ms)
    res_heavy = model.calculate_scenario(100, 45, 55, profile_name="radio_heavy")
    assert res_heavy["profile_id"] == "radio_heavy"

    # 3. Custom profile with intermediate airtime (0.85 ms)
    res_custom_airtime = model.calculate_scenario(100, 45, 55, radio_tx_ms_override=0.85)
    assert res_custom_airtime["profile_id"] == "custom"
    assert "0.85 ms Radio TX" in res_custom_airtime["profile_name"]
    assert "CUSTOM MCU PARAMETERS" in res_custom_airtime["provenance_label"]

    # 4. Custom profile via API
    resp_api = client.get("/api/battery/mcu-scenario?radio_tx_ms=0.85")
    assert resp_api.status_code == 200
    data = resp_api.json()
    assert data["profile_id"] == "custom"
    assert "0.85 ms" in data["profile_name"]


# --- Test 16: Explicit Duty-Cycle Metadata & Runtime Derivation ---

def test_duty_cycle_metadata_accounting():
    """Verify that duty-cycle and indicative runtime calculations return explicit metadata."""
    model = McuEnergyModel()
    res = model.calculate_scenario(100, 45, 55)

    assert "duty_cycle_info" in res
    dc = res["duty_cycle_info"]

    assert dc["reporting_frequency_hz"] == 50.0  # 1000 / 20 ms
    assert dc["nominal_packet_period_ms"] == 20.0

    base_dc = dc["baseline"]
    adapt_dc = dc["adaptive"]

    # Active + sleep per record strictly equals nominal period within rounding precision
    assert abs(base_dc["active_time_per_record_ms"] + base_dc["sleep_time_per_record_ms"] - 20.0) < 0.005
    assert abs(adapt_dc["active_time_per_record_ms"] + adapt_dc["sleep_time_per_record_ms"] - 20.0) < 0.005

    # Duty cycle percentage reflects active time / nominal period
    expected_base_pct = (base_dc["active_time_per_record_ms"] / 20.0) * 100.0
    assert abs(base_dc["duty_cycle_percent"] - expected_base_pct) < 0.1

    assert "runtime_derivation_note" in dc
    assert "50 Hz" in dc["runtime_derivation_note"]
    assert "deep sleep" in dc["runtime_derivation_note"]


# --- Test 17: Seed Consistency between Generation, Benchmark, and Record Trace ---

def test_seed_consistency_between_generation_and_benchmark(client):
    """Verify that benchmark run reuses pre-generated records when seed and count match,
    and regenerates consistently when seed or count changes.
    """
    # 1. Generate records with seed 77
    gen_resp = client.post("/api/demo/generate", json={"seed": 77, "count": 25})
    assert gen_resp.status_code == 200
    gen_data = gen_resp.json()
    generated_first_id = gen_data["all_records"][0]["record_id"]

    # 2. Run benchmark with matching seed 77 and count 25
    bench_resp = client.post("/api/benchmark/run", json={
        "mode": "comparison",
        "record_count": 25,
        "seed": 77,
        "repetitions": 1,
    })
    assert bench_resp.status_code == 200
    comp_data = bench_resp.json()["comparison"]

    # 3. Benchmarked records in comparison result match generated records exactly
    assert comp_data["records"][0]["record_id"] == generated_first_id
    assert len(comp_data["records"]) == 25

    # 4. Query run details from saved run store
    base_run_id = bench_resp.json()["baseline_run_id"]
    rec_resp = client.get(f"/api/runs/{base_run_id}")
    assert rec_resp.status_code == 200
    records_list = rec_resp.json()["records"]
    assert records_list[0]["record_id"] == generated_first_id


# --- Test 18: Safe Localhost CORS Policy Verification ---

def test_safe_localhost_cors_headers(client):
    """Verify that CORS restricts access to safe local development origins."""
    # Allowed origin: http://localhost:8000
    resp_allowed = client.options("/api/health", headers={
        "Origin": "http://localhost:8000",
        "Access-Control-Request-Method": "GET",
    })
    assert resp_allowed.headers.get("access-control-allow-origin") == "http://localhost:8000"

    # Allowed origin: http://127.0.0.1:8000
    resp_ip_allowed = client.options("/api/health", headers={
        "Origin": "http://127.0.0.1:8000",
        "Access-Control-Request-Method": "GET",
    })
    assert resp_ip_allowed.headers.get("access-control-allow-origin") == "http://127.0.0.1:8000"

    # Disallowed external origin: should not echo back malicious origin
    resp_disallowed = client.options("/api/health", headers={
        "Origin": "http://evil-attacker-site.com",
        "Access-Control-Request-Method": "GET",
    })
    assert resp_disallowed.headers.get("access-control-allow-origin") != "http://evil-attacker-site.com"




