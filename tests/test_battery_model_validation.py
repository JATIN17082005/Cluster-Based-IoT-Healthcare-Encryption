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

