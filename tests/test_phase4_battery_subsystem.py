"""Phase 4 Unit Tests: Battery and Energy Subsystem."""

import pytest
from src.models import MeasurementSource, PowerModelConfig
from src.metrics import integrate_energy_joules, compute_indicative_runtime_hours
from src.power_measurement import (
    convert_current_to_ma,
    convert_voltage_to_v,
    joules_to_mwh,
    mwh_to_joules,
    CSVPowerImporter,
    SimulationPowerProvider,
    HardwareSerialPowerAdapter,
)


def test_unit_conversions():
    """Verify current, voltage, and energy unit conversion accuracy."""
    # Current
    assert convert_current_to_ma(1.5, "A") == 1500.0
    assert convert_current_to_ma(25.0, "mA") == 25.0
    assert convert_current_to_ma(500.0, "uA") == 0.5
    with pytest.raises(ValueError):
        convert_current_to_ma(1.0, "invalid_unit")

    # Voltage
    assert convert_voltage_to_v(3300.0, "mV") == 3.3
    assert convert_voltage_to_v(5.0, "V") == 5.0
    with pytest.raises(ValueError):
        convert_voltage_to_v(1.0, "invalid_unit")

    # Energy conversions
    # 3.6 Joules = 1 mWh
    assert joules_to_mwh(3.6) == 1.0
    assert mwh_to_joules(1.0) == 3.6


def test_energy_integration_known_signal():
    """Verify numerical energy integration against analytical ground truth."""
    # Constant 3.3 V and 100 mA (0.1 A) for 2 seconds (0 to 2000 ms)
    # Power = 3.3 * 0.1 = 0.33 Watts
    # Energy = 0.33 W * 2.0 s = 0.66 Joules
    voltages = [3.3, 3.3, 3.3]
    currents = [100.0, 100.0, 100.0]
    timestamps = [0.0, 1000.0, 2000.0]

    joules, mean_v, mean_i, mean_p = integrate_energy_joules(voltages, currents, timestamps)
    assert joules == 0.66
    assert mean_v == 3.3
    assert mean_i == 100.0
    assert mean_p == 330.0


def test_indicative_battery_runtime():
    """Verify indicative battery runtime formula and boundary checks."""
    # 1200 mAh * 0.85 usable factor = 1020 usable mAh
    # At 51 mA average current -> 1020 / 51 = 20.0 hours
    hours = compute_indicative_runtime_hours(1200.0, 0.85, 51.0)
    assert hours == 20.0

    # Negative / zero inputs return None
    assert compute_indicative_runtime_hours(0.0, 0.85, 50.0) is None
    assert compute_indicative_runtime_hours(1200.0, 0.85, 0.0) is None


def test_csv_importer_valid():
    """Verify parsing valid instrument CSV power logs."""
    csv_data = """timestamp_ms,voltage_v,current_ma
0.0,3.3,45.2
10.0,3.3,55.4
20.0,3.29,48.1
"""
    voltages, currents, timestamps, source = CSVPowerImporter.parse_csv_content(csv_data)
    assert len(voltages) == 3
    assert len(currents) == 3
    assert len(timestamps) == 3
    assert source == MeasurementSource.IMPORTED
    assert timestamps == [0.0, 10.0, 20.0]
    assert voltages[0] == 3.3
    assert currents[0] == 45.2


def test_csv_importer_valid_alternate_headers():
    """Verify parsing CSV logs with seconds and amperes units."""
    csv_data = """time_s,voltage,current_a
0.0,3.3,0.05
1.0,3.3,0.06
"""
    voltages, currents, timestamps, source = CSVPowerImporter.parse_csv_content(csv_data)
    assert timestamps == [0.0, 1000.0]  # Converted to ms
    assert currents == [50.0, 60.0]  # Converted to mA
    assert source == MeasurementSource.IMPORTED


def test_csv_importer_rejections():
    """Verify that invalid CSV files are strictly rejected with helpful errors."""
    # 1. Empty CSV
    with pytest.raises(ValueError, match="empty"):
        CSVPowerImporter.parse_csv_content("")

    # 2. Missing voltage column
    with pytest.raises(ValueError, match="missing required voltage column"):
        CSVPowerImporter.parse_csv_content("timestamp_ms,current_ma\n0.0,50.0")

    # 3. Non-monotonic timestamp
    non_monotonic = """timestamp_ms,voltage_v,current_ma
10.0,3.3,50.0
5.0,3.3,50.0
"""
    with pytest.raises(ValueError, match="Non-monotonic timestamp"):
        CSVPowerImporter.parse_csv_content(non_monotonic)

    # 4. Negative values
    neg_voltage = """timestamp_ms,voltage_v,current_ma
0.0,-3.3,50.0
"""
    with pytest.raises(ValueError, match="Negative voltage"):
        CSVPowerImporter.parse_csv_content(neg_voltage)


def test_simulation_fallback_provenance():
    """Verify that simulation provider strictly marks outputs as ESTIMATED/SIMULATED."""
    provider = SimulationPowerProvider()
    v, i, t, source = provider.generate_estimated_samples(duration_ms=100.0, mean_current_ma=40.0)

    # Must never claim hardware measurement
    assert source == MeasurementSource.ESTIMATED
    assert source != MeasurementSource.HARDWARE

    prov = provider.get_provenance()
    assert prov["source"] == "estimated"
    assert "SIMULATED / ESTIMATED — NOT A PHYSICAL BATTERY READING" in prov["badge_label"]
    assert "supply_voltage_v" in prov["model_assumptions"]


def test_hardware_adapter_unconnected():
    """Verify that hardware adapter fails cleanly when no hardware port is configured."""
    adapter = HardwareSerialPowerAdapter(port=None)
    with pytest.raises(ConnectionError, match="No hardware power sensor"):
        adapter.start_sampling()
