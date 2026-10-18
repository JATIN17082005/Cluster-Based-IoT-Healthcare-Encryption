"""Unit and integration tests for battery model audit, mathematical proofs,
evidence separation, and component energy accounting.
"""

import pytest
import math
from fastapi.testclient import TestClient
from src.server import app
from src.models import McuHardwareScenarioConfig
from src.power_measurement import McuEnergyModel


@pytest.fixture
def client():
    return TestClient(app)


def test_battery_energy_model_endpoint(client):
    """Verify that /api/battery/energy-model provides full specifications and formulas."""
    resp = client.get("/api/battery/energy-model")
    assert resp.status_code == 200
    data = resp.json()

    assert "mcu_specification" in data
    assert "battery_specification" in data
    assert "mathematical_formulas" in data
    assert "evidence_hierarchy" in data
    assert "active_parameters" in data
    assert "reference_100_record_breakdown" in data

    # Verify battery capacity arithmetic
    bat = data["battery_specification"]
    # 1200 mAh = 1.2 Ah; usable factor 0.85 -> 1020 mAh usable
    assert bat["nominal_capacity_mah"] == 1200.0
    assert bat["usable_capacity_factor"] == 0.85
    assert bat["usable_capacity_mah"] == 1020.0
    # Usable energy = 1.2 Ah * 3600 s * 3.3 V * 0.85 = 12117.6 J
    expected_usable_j = (1200.0 / 1000.0) * 3600.0 * 3.3 * 0.85
    assert math.isclose(bat["usable_energy_joules"], expected_usable_j, rel_tol=1e-3)


def test_known_arithmetic_example():
    """Verify known arithmetic: 3.3 V, 10 mA, 1 ms = 0.000033 J (0.033 mJ)."""
    voltage_v = 3.3
    current_ma = 10.0
    duration_ms = 1.0

    current_a = current_ma / 1000.0
    duration_s = duration_ms / 1000.0
    energy_j = voltage_v * current_a * duration_s

    assert math.isclose(energy_j, 0.000033, rel_tol=1e-6)
    assert math.isclose(energy_j * 1000.0, 0.033, rel_tol=1e-6)


def test_zero_duration_zero_energy():
    """Verify that zero duration yields strictly zero energy."""
    cfg = McuHardwareScenarioConfig()
    model = McuEnergyModel(cfg)

    # Calculate for single record with zero radio duration
    res = model.calculate_scenario(
        total_records=1,
        high_sensitivity_count=1,
        low_sensitivity_count=0,
        radio_tx_ms_override=0.0,
    )
    assert res["baseline"]["energy_tx_joules"] == 0.0
    assert res["adaptive"]["energy_tx_joules"] == 0.0


def test_non_overlapping_execution_intervals():
    """Verify that execution durations and energies equal the exact sum of isolated components."""
    cfg = McuHardwareScenarioConfig()
    model = McuEnergyModel(cfg)

    res = model.calculate_scenario(
        total_records=100,
        high_sensitivity_count=45,
        low_sensitivity_count=55,
        radio_tx_ms_override=1.0,
    )

    base = res["baseline"]
    sum_base_j = (
        base["energy_crypto_joules"]
        + base["energy_proc_joules"]
        + base["energy_tx_joules"]
        + base["energy_idle_joules"]
    )
    assert math.isclose(base["total_energy_joules"], sum_base_j, rel_tol=1e-6)

    adapt = res["adaptive"]
    sum_adapt_j = (
        adapt["energy_crypto_joules"]
        + adapt["energy_proc_joules"]
        + adapt["energy_tx_joules"]
        + adapt["energy_idle_joules"]
    )
    assert math.isclose(adapt["total_energy_joules"], sum_adapt_j, rel_tol=1e-6)


def test_evidence_hierarchy_separation(client):
    """Verify that evidence hierarchy tiers remain distinct and properly documented."""
    resp = client.get("/api/battery/energy-model")
    tiers = {t["tier"]: t for t in resp.json()["evidence_hierarchy"]}

    assert "A" in tiers
    assert "B" in tiers
    assert "C" in tiers

    assert tiers["A"]["badge"] == "DESKTOP_MEASURED_HOST"
    assert tiers["B"]["badge"] == "MODELED_ESTIMATED_MCU"
    assert tiers["C"]["badge"] == "INSTRUMENT_MEASURED_LAB"


def test_battery_cell_vs_rail_accounting(client):
    """Verify the physical distinction between 3.7V cell capacity and 3.3V regulated rail capacity."""
    resp = client.get("/api/battery/energy-model")
    assert resp.status_code == 200
    bat = resp.json()["battery_specification"]

    # 1S Li-Po electrochemical cell specs
    assert bat["cell_nominal_voltage_v"] == 3.7
    assert bat["regulated_rail_voltage_v"] == 3.3
    assert bat["nominal_capacity_mah"] == 1200.0
    assert bat["usable_capacity_factor"] == 0.85

    # Cell total energy: 1.2 Ah * 3.7 V * 3600 s = 15984.0 J
    assert math.isclose(bat["cell_total_energy_joules"], 15984.0, rel_tol=1e-3)
    # Cell usable energy at 85% DoD: 15984.0 * 0.85 = 13586.40 J
    assert math.isclose(bat["cell_usable_energy_joules"], 13586.40, rel_tol=1e-3)

    # LDO step-down efficiency: 3.3 / 3.7 ~ 0.8919
    assert math.isclose(bat["ldo_efficiency_factor"], 3.3 / 3.7, rel_tol=1e-3)

    # Rail delivered energy: 13586.40 J * (3.3 / 3.7) = 12117.60 J
    assert math.isclose(bat["usable_energy_joules"], 12117.60, rel_tol=1e-3)
    assert math.isclose(
        bat["usable_energy_joules"],
        bat["cell_usable_energy_joules"] * bat["ldo_efficiency_factor"],
        rel_tol=1e-3,
    )

    # Also verify calculate_scenario includes battery_accounting metadata
    cfg = McuHardwareScenarioConfig()
    model = McuEnergyModel(cfg)
    res = model.calculate_scenario(
        total_records=100,
        high_sensitivity_count=45,
        low_sensitivity_count=55,
    )
    assert "battery_accounting" in res
    acc = res["battery_accounting"]
    assert acc["cell_nominal_voltage_v"] == 3.7
    assert acc["regulated_rail_voltage_v"] == 3.3
    assert acc["rail_usable_energy_joules"] == 12117.60


def test_hardware_adapter_placeholder_provenance():
    """Verify that HardwareSerialPowerAdapter exposes its placeholder status and throws safe ConnectionError."""
    from src.power_measurement import HardwareSerialPowerAdapter

    adapter = HardwareSerialPowerAdapter(port=None)
    prov = adapter.get_provenance()
    assert prov["status"] == "INTERFACE_PLACEHOLDER_HARDWARE_PENDING"
    assert "Hardware Pending" in prov["methodology"]

    with pytest.raises(ConnectionError, match="No hardware power sensor"):
        adapter.start_sampling()


def test_configured_operation_timings_and_cycles():
    """Verify that McuHardwareScenarioConfig timings match the active model and convert
    to exact cycle counts via cycles = duration_ms * 16,000 at 16 MHz.
    """
    cfg = McuHardwareScenarioConfig()

    assert cfg.supply_voltage_v == 3.3
    assert cfg.mcu_clock_hz == 16_000_000.0
    clock_khz = cfg.mcu_clock_hz / 1000.0  # 16,000 cycles per ms

    # Configured durations (ms)
    assert cfg.t_shared_proc_ms == 0.35
    assert cfg.t_aes_gcm_ms == 1.25
    assert cfg.t_sha256_keystream_ms == 0.25
    assert cfg.t_xor_stream_ms == 0.01
    assert cfg.t_hmac_sha256_ms == 0.38
    assert cfg.idle_sleep_current_ma == 0.015

    # Cycles = duration_ms * 16,000
    cycles_proc = cfg.t_shared_proc_ms * clock_khz
    cycles_aes = cfg.t_aes_gcm_ms * clock_khz
    cycles_sha = cfg.t_sha256_keystream_ms * clock_khz
    cycles_xor = cfg.t_xor_stream_ms * clock_khz
    cycles_hmac = cfg.t_hmac_sha256_ms * clock_khz
    cycles_composite_routine = cycles_sha + cycles_xor + cycles_hmac

    assert math.isclose(cycles_proc, 5600.0, rel_tol=1e-6)
    assert math.isclose(cycles_aes, 20000.0, rel_tol=1e-6)
    assert math.isclose(cycles_sha, 4000.0, rel_tol=1e-6)
    assert math.isclose(cycles_xor, 160.0, rel_tol=1e-6)
    assert math.isclose(cycles_hmac, 6080.0, rel_tol=1e-6)
    assert math.isclose(cycles_composite_routine, 10240.0, rel_tol=1e-6)

    # Per-operation cryptographic cycle saving
    cycle_saving_pct = ((cycles_aes - cycles_composite_routine) / cycles_aes) * 100.0
    assert math.isclose(cycle_saving_pct, 48.80, abs_tol=0.01)


def test_per_operation_cryptographic_energies():
    """Verify per-operation cryptographic energies (V * I * t) derived from configured currents and durations:
    AES-GCM = 0.040425 mJ, SHA-256 = 0.006765 mJ, XOR = 0.0002475 mJ, HMAC = 0.0105336 mJ, Combined = 0.0175461 mJ.
    """
    cfg = McuHardwareScenarioConfig()
    v = cfg.supply_voltage_v  # 3.3 V

    assert cfg.cpu_active_current_ma == 8.5
    assert cfg.aes_active_current_ma == 9.8
    assert cfg.sha256_active_current_ma == 8.2
    assert cfg.xor_active_current_ma == 7.5
    assert cfg.hmac_active_current_ma == 8.4

    # Energies in Joules: V * (mA / 1000) * (ms / 1000)
    e_aes_j = v * (cfg.aes_active_current_ma / 1000.0) * (cfg.t_aes_gcm_ms / 1000.0)
    e_sha_j = v * (cfg.sha256_active_current_ma / 1000.0) * (cfg.t_sha256_keystream_ms / 1000.0)
    e_xor_j = v * (cfg.xor_active_current_ma / 1000.0) * (cfg.t_xor_stream_ms / 1000.0)
    e_hmac_j = v * (cfg.hmac_active_current_ma / 1000.0) * (cfg.t_hmac_sha256_ms / 1000.0)
    e_composite_j = e_sha_j + e_xor_j + e_hmac_j
    e_proc_j = v * (cfg.cpu_active_current_ma / 1000.0) * (cfg.t_shared_proc_ms / 1000.0)

    # In mJ (1 J = 1000 mJ)
    assert math.isclose(e_aes_j * 1000.0, 0.040425, rel_tol=1e-6)
    assert math.isclose(e_sha_j * 1000.0, 0.006765, rel_tol=1e-6)
    assert math.isclose(e_xor_j * 1000.0, 0.0002475, rel_tol=1e-6)
    assert math.isclose(e_hmac_j * 1000.0, 0.0105336, rel_tol=1e-6)
    assert math.isclose(e_composite_j * 1000.0, 0.0175461, rel_tol=1e-6)
    assert math.isclose(e_proc_j * 1000.0, 0.0098175, rel_tol=1e-6)

    # Per-operation cryptographic energy saving
    per_op_crypto_saving_pct = ((e_aes_j - e_composite_j) / e_aes_j) * 100.0
    assert math.isclose(per_op_crypto_saving_pct, 56.595918, abs_tol=0.01)

    # Per-operation saving (~56.6%) is distinctly different from batch energy savings
    assert per_op_crypto_saving_pct > 50.0


def test_reference_100_record_breakdown_matches_active_config():
    """Verify that calculate_scenario with standard 45/55 workload produces exact
    reconciled batch cryptographic energies and deltas.
    """
    cfg = McuHardwareScenarioConfig()
    model = McuEnergyModel(cfg)
    res = model.calculate_scenario(
        total_records=100,
        high_sensitivity_count=45,
        low_sensitivity_count=55,
    )

    base = res["baseline"]
    adapt = res["adaptive"]

    # Baseline: 100 * 0.000040425 J = 0.0040425 J
    assert math.isclose(base["energy_crypto_joules"], 0.0040425, rel_tol=1e-5)
    assert math.isclose(base["energy_aes_joules"], 0.0040425, rel_tol=1e-5)

    # Adaptive: 45 * 0.000040425 J + 55 * 0.0000175461 J = 0.001819125 + 0.0009650355 = 0.0027841605 J
    assert math.isclose(adapt["energy_aes_joules"], 45 * 0.000040425, rel_tol=1e-4, abs_tol=1e-6)
    assert math.isclose(adapt["energy_sha_joules"], 55 * 0.000006765, rel_tol=1e-4, abs_tol=1e-6)
    assert math.isclose(adapt["energy_xor_joules"], 55 * 0.0000002475, rel_tol=1e-4, abs_tol=1e-6)
    assert math.isclose(adapt["energy_hmac_joules"], 55 * 0.0000105336, rel_tol=1e-4, abs_tol=1e-6)
    assert math.isclose(adapt["energy_crypto_joules"], 0.0027841605, rel_tol=1e-4, abs_tol=1e-6)

    # Batch crypto energy saving: (4.0425 - 2.7841605) / 4.0425 = 31.1277...% ~ 31.13%
    comp_crypto_energy = res["crypto_energy_comparison"]
    assert math.isclose(comp_crypto_energy["energy_saving_percent"], 31.13, abs_tol=0.05)


def test_energy_model_api_consistency(client):
    """Verify that the /api/battery/energy-model API response has consistent active parameters
    and reference breakdown matching the backend source of truth.
    """
    resp = client.get("/api/battery/energy-model")
    assert resp.status_code == 200
    data = resp.json()

    params = data["active_parameters"]
    assert params["supply_voltage_v"] == 3.3
    assert params["mcu_clock_hz"] == 16_000_000.0
    assert params["aes_active_current_ma"] == 9.8
    assert params["sha256_active_current_ma"] == 8.2
    assert params["xor_active_current_ma"] == 7.5
    assert params["hmac_active_current_ma"] == 8.4
    assert params["cpu_active_current_ma"] == 8.5
    assert params["t_aes_gcm_ms"] == 1.25
    assert params["t_sha256_keystream_ms"] == 0.25
    assert params["t_xor_stream_ms"] == 0.01
    assert params["t_hmac_sha256_ms"] == 0.38
    assert params["t_shared_proc_ms"] == 0.35

    ref = data["reference_100_record_breakdown"]
    assert ref["record_count"] == 100
    assert ref["high_sensitivity_count"] == 45
    assert ref["low_sensitivity_count"] == 55
    assert math.isclose(ref["baseline"]["energy_crypto_joules"], 0.0040425, rel_tol=1e-5)
    assert math.isclose(ref["adaptive"]["energy_crypto_joules"], 0.0027841605, rel_tol=1e-5)


def test_documented_reference_discrepancy_detection():
    """Verify that documented reference values match the active configuration.
    If any parameter in McuHardwareScenarioConfig is changed, this test ensures that
    the documented reference constants and derivations remain synchronized.
    """
    cfg = McuHardwareScenarioConfig()

    EXPECTED_DOCUMENTED_PARAMS = {
        "supply_voltage_v": 3.3,
        "mcu_clock_hz": 16_000_000.0,
        "t_aes_gcm_ms": 1.25,
        "t_sha256_keystream_ms": 0.25,
        "t_xor_stream_ms": 0.01,
        "t_hmac_sha256_ms": 0.38,
        "t_shared_proc_ms": 0.35,
        "aes_active_current_ma": 9.8,
        "sha256_active_current_ma": 8.2,
        "xor_active_current_ma": 7.5,
        "hmac_active_current_ma": 8.4,
        "cpu_active_current_ma": 8.5,
        "idle_sleep_current_ma": 0.015,
    }

    discrepancies = []
    for param, expected_val in EXPECTED_DOCUMENTED_PARAMS.items():
        actual_val = getattr(cfg, param, None)
        if actual_val is None or not math.isclose(actual_val, expected_val, rel_tol=1e-5):
            discrepancies.append(
                f"Discrepancy in {param}: active config={actual_val}, documented reference={expected_val}"
            )

    assert not discrepancies, f"Found configuration discrepancies with documented references: {discrepancies}"



