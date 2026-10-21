"""Power and Energy Measurement Subsystem.
Provides:
1. Isolated PowerMeasurementAdapter interface.
2. Hardware serial power meter adapter stub.
3. Strict CSV power measurement importer for external lab instruments.
4. Transparent software estimation fallback model.
5. Unit conversion and integration utilities.
"""

import io
import csv
from abc import ABC, abstractmethod
from typing import List, Dict, Tuple, Optional, Any
from src.models import (
    MeasurementSource,
    PowerSample,
    PowerModelConfig,
    McuHardwareScenarioConfig,
)
from src.metrics import (
    integrate_energy_joules,
    calculate_percentage_change,
    calculate_energy_saving,
    evaluate_result_status,
    compute_authoritative_comparison,
)


# Unit Conversion Helpers
def convert_current_to_ma(value: float, unit: str) -> float:
    """Convert current to milliamperes (mA)."""
    u = unit.strip().lower()
    if u in ("ma", "milliamp", "milliamps"):
        return value
    elif u in ("a", "amp", "amps", "ampere", "amperes"):
        return value * 1000.0
    elif u in ("ua", "microamp", "microamps"):
        return value / 1000.0
    raise ValueError(f"Unsupported current unit '{unit}'. Expected mA, A, or uA.")


def convert_voltage_to_v(value: float, unit: str) -> float:
    """Convert voltage to volts (V)."""
    u = unit.strip().lower()
    if u in ("v", "volt", "volts"):
        return value
    elif u in ("mv", "millivolt", "millivolts"):
        return value / 1000.0
    elif u in ("kv", "kilovolt"):
        return value * 1000.0
    raise ValueError(f"Unsupported voltage unit '{unit}'. Expected V or mV.")


def joules_to_mwh(joules: float) -> float:
    """Convert Joules (J) to milliwatt-hours (mWh).
    1 Joule = 1 Watt-second = (1000 mW * 1 s) / 3600 = 1000/3600 mWh = 1/3.6 mWh
    """
    return round(joules * (1000.0 / 3600.0), 6)


def mwh_to_joules(mwh: float) -> float:
    """Convert milliwatt-hours (mWh) to Joules (J)."""
    return round(mwh * 3.6, 6)


class BasePowerAdapter(ABC):
    """Abstract interface for power measurement sources."""

    @abstractmethod
    def start_sampling(self):
        """Begin sampling power."""
        pass

    @abstractmethod
    def stop_sampling(self) -> Tuple[List[float], List[float], List[float], MeasurementSource]:
        """Stop sampling and return (voltages_v, currents_ma, timestamps_ms, source)."""
        pass

    @abstractmethod
    def get_provenance(self) -> Dict[str, Any]:
        """Return provenance metadata (source, instrument ID, device boundary)."""
        pass


class HardwareSerialPowerAdapter(BasePowerAdapter):
    """Hardware serial power adapter interface / placeholder for dedicated power meters (e.g. Monsoon / Otii / INA219).

    Academic Disclosure:
    This class defines the software adapter contract for streaming real-time electrical telemetry
    from physical hardware over a serial/COM interface.
    Live physical serial acquisition requires an attached hardware instrument. In the current release,
    physical laboratory power measurements are supported via CSVPowerImporter (/api/power/import).
    This class serves as an interface placeholder and does NOT manufacture synthetic hardware data.
    """

    def __init__(self, port: Optional[str] = None, baudrate: int = 115200):
        self.port = port
        self.baudrate = baudrate
        self.is_connected = False
        self._samples_v: List[float] = []
        self._samples_i_ma: List[float] = []
        self._samples_t_ms: List[float] = []

    def start_sampling(self):
        if not self.port:
            raise ConnectionError(
                "No hardware power sensor COM port configured. "
                "Physical serial streaming requires an attached hardware instrument. "
                "For empirical power validation, import laboratory instrument CSV logs via /api/power/import."
            )
        # Dedicated hardware meter connection hook
        self.is_connected = True
        self._samples_v.clear()
        self._samples_i_ma.clear()
        self._samples_t_ms.clear()

    def stop_sampling(self) -> Tuple[List[float], List[float], List[float], MeasurementSource]:
        if not self.is_connected:
            raise RuntimeError("Hardware power sampling was not started or sensor disconnected.")
        self.is_connected = False
        return (
            list(self._samples_v),
            list(self._samples_i_ma),
            list(self._samples_t_ms),
            MeasurementSource.HARDWARE,
        )

    def get_provenance(self) -> Dict[str, Any]:
        return {
            "source": MeasurementSource.HARDWARE.value,
            "instrument": f"Serial Sensor on {self.port or 'NONE'}",
            "device_boundary": "IoT Device Supply Boundary (VCC to GND)",
            "status": "INTERFACE_PLACEHOLDER_HARDWARE_PENDING",
            "methodology": "Hardware Pending (Serial INA219/INA226/Oscilloscope probe interface)",
            "description": (
                "Hardware serial adapter interface. Live hardware connection is pending attached instrument; "
                "use /api/power/import to load physical laboratory power logs."
            ),
        }


class CSVPowerImporter:
    """Parses and validates external lab instrument power CSV logs."""

    REQUIRED_FIELD_ALIASES = {
        "timestamp": ["timestamp_ms", "time_ms", "timestamp", "time_s", "time"],
        "voltage": ["voltage_v", "voltage_mv", "voltage", "v"],
        "current": ["current_ma", "current_a", "current", "i_ma", "i"],
    }

    @classmethod
    def parse_csv_content(
        cls,
        csv_text: str,
        default_voltage_unit: str = "V",
        default_current_unit: str = "mA",
        default_time_unit: str = "ms",
    ) -> Tuple[List[float], List[float], List[float], MeasurementSource]:
        """Validate and parse CSV power samples.
        Returns: (voltages_v, currents_ma, timestamps_ms, MeasurementSource.IMPORTED)
        """
        if not csv_text or not csv_text.strip():
            raise ValueError("CSV power log is empty.")

        reader = csv.reader(io.StringIO(csv_text.strip()))
        try:
            raw_headers = next(reader)
        except StopIteration:
            raise ValueError("CSV power log has no header row.")

        headers = [h.strip().lower() for h in raw_headers]

        # Identify column indices
        col_time = cls._find_col(headers, cls.REQUIRED_FIELD_ALIASES["timestamp"])
        col_v = cls._find_col(headers, cls.REQUIRED_FIELD_ALIASES["voltage"])
        col_i = cls._find_col(headers, cls.REQUIRED_FIELD_ALIASES["current"])

        if col_time is None:
            raise ValueError("CSV missing required timestamp column (e.g., 'timestamp_ms' or 'time_s').")
        if col_v is None:
            raise ValueError("CSV missing required voltage column (e.g., 'voltage_v' or 'voltage_mv').")
        if col_i is None:
            raise ValueError("CSV missing required current column (e.g., 'current_ma' or 'current_a').")

        # Determine units from header names if present
        time_unit = "s" if "s" in headers[col_time] and "ms" not in headers[col_time] else default_time_unit
        v_unit = "mv" if "mv" in headers[col_v] else default_voltage_unit
        i_unit = "a" if "_a" in headers[col_i] or headers[col_i] == "current_a" else default_current_unit

        voltages_v: List[float] = []
        currents_ma: List[float] = []
        timestamps_ms: List[float] = []

        last_time_ms = -1.0
        row_num = 1

        for row in reader:
            row_num += 1
            if not row or not any(field.strip() for field in row):
                continue

            try:
                raw_t = float(row[col_time].strip())
                raw_v = float(row[col_v].strip())
                raw_i = float(row[col_i].strip())
            except (ValueError, IndexError) as e:
                raise ValueError(f"Malformed numerical data in CSV row {row_num}: {row}") from e

            # Non-negativity checks
            if raw_v < 0:
                raise ValueError(f"Negative voltage ({raw_v}) encountered at CSV row {row_num}.")
            if raw_i < 0:
                raise ValueError(f"Negative current ({raw_i}) encountered at CSV row {row_num}.")

            # Time unit conversion
            t_ms = raw_t * 1000.0 if time_unit.lower() == "s" else raw_t

            # Verify monotonic timestamps
            if t_ms < last_time_ms:
                raise ValueError(
                    f"Non-monotonic timestamp anomaly at row {row_num}: {t_ms} ms < previous {last_time_ms} ms."
                )
            last_time_ms = t_ms

            v_val = convert_voltage_to_v(raw_v, v_unit)
            i_val = convert_current_to_ma(raw_i, i_unit)

            timestamps_ms.append(t_ms)
            voltages_v.append(v_val)
            currents_ma.append(i_val)

        if not timestamps_ms:
            raise ValueError("CSV contained no data rows after header.")

        return voltages_v, currents_ma, timestamps_ms, MeasurementSource.IMPORTED

    @staticmethod
    def _find_col(headers: List[str], aliases: List[str]) -> Optional[int]:
        for alias in aliases:
            for idx, h in enumerate(headers):
                if h == alias or alias in h:
                    return idx
        return None


class SimulationPowerProvider:
    """Software-estimated power model fallback provider.
    Never misrepresents estimates as physical hardware readings.
    """

    def __init__(self, config: Optional[PowerModelConfig] = None):
        self.config = config or PowerModelConfig()

    def generate_estimated_samples(
        self,
        duration_ms: float,
        mean_current_ma: float,
        sample_interval_ms: float = 10.0,
    ) -> Tuple[List[float], List[float], List[float], MeasurementSource]:
        """Generate synthetic power trace samples for visualization and integration checks."""
        timestamps_ms: List[float] = []
        voltages_v: List[float] = []
        currents_ma: List[float] = []

        t = 0.0
        while t <= duration_ms:
            timestamps_ms.append(round(t, 2))
            voltages_v.append(self.config.supply_voltage_v)
            currents_ma.append(mean_current_ma)
            t += sample_interval_ms

        # Must strictly return ESTIMATED, never HARDWARE
        return voltages_v, currents_ma, timestamps_ms, MeasurementSource.ESTIMATED

    def get_provenance(self) -> Dict[str, Any]:
        return {
            "source": MeasurementSource.ESTIMATED.value,
            "badge_label": "SIMULATED / ESTIMATED — NOT A PHYSICAL BATTERY READING",
            "model_assumptions": {
                "supply_voltage_v": self.config.supply_voltage_v,
                "idle_current_ma": self.config.idle_current_ma,
                "active_mcu_current_ma": self.config.active_mcu_current_ma,
                "aes_crypto_current_ma": self.config.aes_crypto_current_ma,
                "xor_crypto_current_ma": self.config.xor_crypto_current_ma,
                "tx_current_ma": self.config.tx_current_ma,
                "tx_duration_ms_per_packet": self.config.tx_duration_ms_per_packet,
                "battery_nominal_mah": self.config.battery_nominal_mah,
                "battery_usable_factor": self.config.battery_usable_factor,
            },
        }


class McuEnergyModel:
    """Configurable mathematical energy simulator for a constrained IoT microcontroller (Scenario B).
    Models an edge microcontroller without hardware AES acceleration (e.g. ARM Cortex-M0+ / AVR).
    Strictly partitions activity into non-overlapping mutually exclusive intervals:
    [Shared CPU Processing] -> [Cryptographic Engine] -> [Radio TX] -> [Idle/Sleep].
    """

    def __init__(self, config: Optional[McuHardwareScenarioConfig] = None):
        self.config = config or McuHardwareScenarioConfig()

    def calculate_scenario(
        self,
        total_records: int,
        high_sensitivity_count: int,
        low_sensitivity_count: int,
        radio_tx_ms_override: Optional[float] = None,
        profile_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Calculate non-overlapping energy breakdown for baseline (100% AES) vs adaptive (AES + XOR route).
        All parameters, record counts, and capacities are identical between baseline and adaptive.
        Supports both Profile 1 (Radio-Heavy @ 1.5 ms) and Profile 2 (Compute-Intensive / Short-TX @ 0.5 ms).
        """
        cfg = self.config
        if radio_tx_ms_override is not None:
            cfg = cfg.model_copy(update={"t_radio_tx_ms": max(0.0, float(radio_tx_ms_override))})
        elif profile_name in ["short_tx", "compute"]:
            cfg = cfg.model_copy(update={"t_radio_tx_ms": 0.50})
        elif profile_name in ["radio_heavy", "heavy"]:
            cfg = cfg.model_copy(update={"t_radio_tx_ms": 1.50})

        v = cfg.supply_voltage_v
        n = max(1, total_records)
        n_high = max(0, high_sensitivity_count)
        n_routine = max(0, low_sensitivity_count)
        if n_high + n_routine != n:
            raise ValueError(
                f"Invalid workload split: high_sensitivity_count ({n_high}) + "
                f"low_sensitivity_count ({n_routine}) must equal total_records ({n})."
            )

        # Baseline: All N records use Software AES-256-GCM
        # 1. Non-overlapping activity intervals for Baseline (ms)
        t_proc_base_ms = n * cfg.t_shared_proc_ms
        t_crypto_base_ms = n * cfg.t_aes_gcm_ms
        t_tx_base_ms = n * cfg.t_radio_tx_ms

        active_per_rec_base = cfg.t_shared_proc_ms + cfg.t_aes_gcm_ms + cfg.t_radio_tx_ms
        idle_per_rec_base = max(0.0, cfg.t_duty_cycle_period_ms - active_per_rec_base)
        t_idle_base_ms = n * idle_per_rec_base
        t_total_base_ms = t_proc_base_ms + t_crypto_base_ms + t_tx_base_ms + t_idle_base_ms

        # Energy components for Baseline (Joules = V * (mA/1000) * (ms/1000))
        e_proc_base_j = v * (cfg.cpu_active_current_ma / 1000.0) * (t_proc_base_ms / 1000.0)
        e_crypto_base_j = v * (cfg.aes_active_current_ma / 1000.0) * (t_crypto_base_ms / 1000.0)
        e_tx_base_j = v * (cfg.radio_tx_current_ma / 1000.0) * (t_tx_base_ms / 1000.0)
        e_idle_base_j = v * (cfg.idle_sleep_current_ma / 1000.0) * (t_idle_base_ms / 1000.0)
        total_energy_base_j = e_proc_base_j + e_crypto_base_j + e_tx_base_j + e_idle_base_j

        duration_base_s = max(0.0001, t_total_base_ms / 1000.0)
        mean_power_base_mw = (total_energy_base_j / duration_base_s) * 1000.0
        mean_current_base_ma = mean_power_base_mw / v
        charge_consumed_base_mah = mean_current_base_ma * (duration_base_s / 3600.0)
        usable_capacity_mah = cfg.battery_nominal_mah * cfg.battery_usable_factor
        runtime_base_hours = usable_capacity_mah / max(0.001, mean_current_base_ma)

        # Adaptive: n_high use Software AES, n_routine use Complete XOR Route (SHA256 + XOR + HMAC)
        # 1. Non-overlapping activity intervals for Adaptive (ms)
        t_proc_adapt_ms = n * cfg.t_shared_proc_ms
        t_aes_adapt_ms = n_high * cfg.t_aes_gcm_ms
        t_sha_adapt_ms = n_routine * cfg.t_sha256_keystream_ms
        t_xor_adapt_ms = n_routine * cfg.t_xor_stream_ms
        t_hmac_adapt_ms = n_routine * cfg.t_hmac_sha256_ms
        t_crypto_adapt_ms = t_aes_adapt_ms + t_sha_adapt_ms + t_xor_adapt_ms + t_hmac_adapt_ms
        t_tx_adapt_ms = n * cfg.t_radio_tx_ms

        active_per_rec_high = cfg.t_shared_proc_ms + cfg.t_aes_gcm_ms + cfg.t_radio_tx_ms
        xor_route_per_rec = cfg.t_sha256_keystream_ms + cfg.t_xor_stream_ms + cfg.t_hmac_sha256_ms
        active_per_rec_routine = cfg.t_shared_proc_ms + xor_route_per_rec + cfg.t_radio_tx_ms

        idle_high_ms = n_high * max(0.0, cfg.t_duty_cycle_period_ms - active_per_rec_high)
        idle_routine_ms = n_routine * max(0.0, cfg.t_duty_cycle_period_ms - active_per_rec_routine)
        t_idle_adapt_ms = idle_high_ms + idle_routine_ms
        t_total_adapt_ms = t_proc_adapt_ms + t_crypto_adapt_ms + t_tx_adapt_ms + t_idle_adapt_ms

        # Energy components for Adaptive (Joules)
        e_proc_adapt_j = v * (cfg.cpu_active_current_ma / 1000.0) * (t_proc_adapt_ms / 1000.0)
        e_aes_adapt_j = v * (cfg.aes_active_current_ma / 1000.0) * (t_aes_adapt_ms / 1000.0)
        e_sha_adapt_j = v * (cfg.sha256_active_current_ma / 1000.0) * (t_sha_adapt_ms / 1000.0)
        e_xor_adapt_j = v * (cfg.xor_active_current_ma / 1000.0) * (t_xor_adapt_ms / 1000.0)
        e_hmac_adapt_j = v * (cfg.hmac_active_current_ma / 1000.0) * (t_hmac_adapt_ms / 1000.0)
        e_crypto_adapt_j = e_aes_adapt_j + e_sha_adapt_j + e_xor_adapt_j + e_hmac_adapt_j
        e_tx_adapt_j = v * (cfg.radio_tx_current_ma / 1000.0) * (t_tx_adapt_ms / 1000.0)
        e_idle_adapt_j = v * (cfg.idle_sleep_current_ma / 1000.0) * (t_idle_adapt_ms / 1000.0)
        total_energy_adapt_j = e_proc_adapt_j + e_crypto_adapt_j + e_tx_adapt_j + e_idle_adapt_j

        duration_adapt_s = max(0.0001, t_total_adapt_ms / 1000.0)
        mean_power_adapt_mw = (total_energy_adapt_j / duration_adapt_s) * 1000.0
        mean_current_adapt_ma = mean_power_adapt_mw / v
        charge_consumed_adapt_mah = mean_current_adapt_ma * (duration_adapt_s / 3600.0)
        runtime_adapt_hours = usable_capacity_mah / max(0.001, mean_current_adapt_ma)

        # Modelled cryptographic CPU cycles from configured clock frequency (Hz)
        crypto_cycles_base = (t_crypto_base_ms / 1000.0) * cfg.mcu_clock_hz
        crypto_cycles_adapt = (t_crypto_adapt_ms / 1000.0) * cfg.mcu_clock_hz

        # Comparative analytics using authoritative calculation functions
        comp_energy = compute_authoritative_comparison(
            baseline_val=total_energy_base_j,
            proposed_val=total_energy_adapt_j,
            metric_name="Simulated MCU Batch Energy",
            lower_is_better=True,
            is_energy_metric=True,
        )
        comp_crypto_time = compute_authoritative_comparison(
            baseline_val=t_crypto_base_ms,
            proposed_val=t_crypto_adapt_ms,
            metric_name="Simulated MCU Cryptographic Latency",
            lower_is_better=True,
            is_energy_metric=False,
        )
        comp_crypto_cycles = compute_authoritative_comparison(
            baseline_val=crypto_cycles_base,
            proposed_val=crypto_cycles_adapt,
            metric_name="Modelled Cryptographic CPU Cycles",
            lower_is_better=True,
            is_energy_metric=False,
        )
        comp_crypto_energy = compute_authoritative_comparison(
            baseline_val=e_crypto_base_j,
            proposed_val=e_crypto_adapt_j,
            metric_name="Cryptographic Component Energy",
            lower_is_better=True,
            is_energy_metric=True,
        )

        # Dynamic sensitivity comparison across radio transmission intervals: 0.5, 0.75, 1.0, 1.5 ms
        sweep_intervals = [0.50, 0.75, 1.00, 1.50]
        radio_sensitivity_sweep = []
        for interval in sweep_intervals:
            sw_tx_base_j = v * (cfg.radio_tx_current_ma / 1000.0) * ((n * interval) / 1000.0)
            sw_idle_per_rec_b = max(0.0, cfg.t_duty_cycle_period_ms - (cfg.t_shared_proc_ms + cfg.t_aes_gcm_ms + interval))
            sw_idle_base_j = v * (cfg.idle_sleep_current_ma / 1000.0) * ((n * sw_idle_per_rec_b) / 1000.0)
            sw_base_j = e_proc_base_j + e_crypto_base_j + sw_tx_base_j + sw_idle_base_j

            sw_idle_h_ms = n_high * max(0.0, cfg.t_duty_cycle_period_ms - (cfg.t_shared_proc_ms + cfg.t_aes_gcm_ms + interval))
            sw_idle_r_ms = n_routine * max(0.0, cfg.t_duty_cycle_period_ms - (cfg.t_shared_proc_ms + xor_route_per_rec + interval))
            sw_idle_adapt_j = v * (cfg.idle_sleep_current_ma / 1000.0) * ((sw_idle_h_ms + sw_idle_r_ms) / 1000.0)
            sw_adapt_j = e_proc_adapt_j + e_crypto_adapt_j + sw_tx_base_j + sw_idle_adapt_j

            sw_comp = compute_authoritative_comparison(
                baseline_val=sw_base_j,
                proposed_val=sw_adapt_j,
                metric_name=f"Batch Energy at {interval}ms TX",
                lower_is_better=True,
                is_energy_metric=True,
            )
            radio_sensitivity_sweep.append({
                "interval_ms": interval,
                "baseline_energy_j": round(sw_base_j, 8),
                "baseline_energy_mj": round(sw_base_j * 1000.0, 3),
                "adaptive_energy_j": round(sw_adapt_j, 8),
                "adaptive_energy_mj": round(sw_adapt_j * 1000.0, 3),
                "crypto_energy_base_mj": round(e_crypto_base_j * 1000.0, 3),
                "crypto_energy_adapt_mj": round(e_crypto_adapt_j * 1000.0, 3),
                "tx_energy_mj": round(sw_tx_base_j * 1000.0, 3),
                "energy_saving_percent": round(sw_comp.get("energy_saving_percent", 0.0), 2),
                "direction": sw_comp.get("direction", ""),
                "result_status": sw_comp.get("result_status", "INCONCLUSIVE"),
                "is_improvement": sw_comp.get("is_improvement", False),
            })

        # Profile classification metadata:
        # Check if parameters match preset 1 (short_tx @ 0.50 ms) or preset 2 (radio_heavy @ 1.50 ms)
        is_default_params = (
            abs(cfg.t_aes_gcm_ms - 1.25) < 0.05
            and abs(cfg.supply_voltage_v - 3.3) < 0.05
            and abs(cfg.mcu_clock_hz - 16_000_000.0) < 100_000.0
            and abs(cfg.t_sha256_keystream_ms - 0.25) < 0.05
            and abs(cfg.t_xor_stream_ms - 0.01) < 0.005
            and abs(cfg.t_hmac_sha256_ms - 0.38) < 0.05
        )

        is_short_tx_preset = is_default_params and abs(cfg.t_radio_tx_ms - 0.50) < 0.05
        is_radio_heavy_preset = is_default_params and abs(cfg.t_radio_tx_ms - 1.50) < 0.05

        if is_short_tx_preset:
            profile_id = "short_tx"
            profile_name_str = "Compute-Intensive / Short-Transmission MCU Scenario (0.50 ms Radio TX)"
            provenance_label_str = "COMPUTE-INTENSIVE / SHORT-TX MCU SCENARIO — CONFIGURABLE HYPOTHETICAL MODEL"
            provenance_disclaimer_str = (
                "Configurable hypothetical model for high-throughput short airtime radios (e.g., BLE 2Mbps / packed telemetry @ 0.5 ms TX airtime). "
                "Valid only for workloads and radio settings that support 0.5 ms airtime. "
                "Simulated values depend on configured clock, current, and airtime assumptions. Does not represent measured hardware."
            )
        elif is_radio_heavy_preset:
            profile_id = "radio_heavy"
            profile_name_str = "Radio-Heavy MCU Model (1.50 ms Radio TX)"
            provenance_label_str = "SIMULATED TARGET-MCU SCENARIO — RESULTS DEPEND ON CONFIGURED ASSUMPTIONS"
            provenance_disclaimer_str = (
                "Illustrative mathematical energy model for a constrained target MCU without hardware AES acceleration. "
                "Standard IoT radio scenario (802.15.4 / low-baud BLE @ 1.5 ms TX) where radio transmission dominates the power budget (~73%). "
                "Requires empirical physical measurements on target hardware before real-world energy savings can be verified."
            )
        else:
            profile_id = "custom"
            profile_name_str = f"Custom MCU Configuration ({cfg.t_radio_tx_ms:.2f} ms Radio TX)"
            provenance_label_str = f"CUSTOM MCU PARAMETERS ({cfg.t_radio_tx_ms:.2f} ms Radio TX) — USER-CONFIGURED HYPOTHETICAL MODEL"
            provenance_disclaimer_str = (
                f"User-customized microcontroller parameters (Supply: {cfg.supply_voltage_v:.1f}V, "
                f"Clock: {cfg.mcu_clock_hz/1e6:.1f} MHz, AES: {cfg.t_aes_gcm_ms:.2f} ms, "
                f"Radio TX: {cfg.t_radio_tx_ms:.2f} ms @ {cfg.radio_tx_current_ma:.1f} mA). "
                "Parametric sensitivity exploration. Does not represent measured hardware."
            )

        duty_cycle_info = {
            "reporting_frequency_hz": round(1000.0 / cfg.t_duty_cycle_period_ms, 2),
            "nominal_packet_period_ms": cfg.t_duty_cycle_period_ms,
            "baseline": {
                "active_time_per_record_ms": round(active_per_rec_base, 3),
                "sleep_time_per_record_ms": round(idle_per_rec_base, 3),
                "duty_cycle_percent": round((active_per_rec_base / cfg.t_duty_cycle_period_ms) * 100.0, 2),
            },
            "adaptive": {
                "active_time_per_record_ms": round((t_proc_adapt_ms + t_crypto_adapt_ms + t_tx_adapt_ms) / n, 3),
                "sleep_time_per_record_ms": round(t_idle_adapt_ms / n, 3),
                "duty_cycle_percent": round(((t_proc_adapt_ms + t_crypto_adapt_ms + t_tx_adapt_ms) / (n * cfg.t_duty_cycle_period_ms)) * 100.0, 2),
            },
            "runtime_derivation_note": (
                f"Indicative runtime ({cfg.battery_nominal_mah} mAh @ {cfg.battery_usable_factor*100:.0f}% usable capacity) "
                f"assumes periodic {1000.0 / cfg.t_duty_cycle_period_ms:.0f} Hz reporting ({cfg.t_duty_cycle_period_ms:.1f} ms period per record) "
                f"with MCU deep sleep ({cfg.idle_sleep_current_ma*1000:.0f} µA) between packet transmissions. "
                f"Does not extrapolate from continuous unconstrained CPU burst execution."
            ),
        }

        return {
            "scenario_name": profile_name_str,
            "profile_id": profile_id,
            "profile_name": profile_name_str,
            "mcu_model": cfg.mcu_model_name,
            "provenance_label": provenance_label_str,
            "provenance_disclaimer": provenance_disclaimer_str,
            "duty_cycle_info": duty_cycle_info,
            "battery_accounting": {
                "cell_nominal_voltage_v": cfg.battery_cell_nominal_voltage_v,
                "regulated_rail_voltage_v": cfg.supply_voltage_v,
                "cell_total_energy_joules": round((cfg.battery_nominal_mah / 1000.0) * 3600.0 * cfg.battery_cell_nominal_voltage_v, 2),
                "cell_usable_energy_joules": round((cfg.battery_nominal_mah / 1000.0) * 3600.0 * cfg.battery_cell_nominal_voltage_v * cfg.battery_usable_factor, 2),
                "rail_delivered_usable_energy_joules": round((cfg.battery_nominal_mah / 1000.0) * 3600.0 * cfg.supply_voltage_v * cfg.battery_usable_factor, 2),
                "rail_usable_energy_joules": round((cfg.battery_nominal_mah / 1000.0) * 3600.0 * cfg.supply_voltage_v * cfg.battery_usable_factor, 2),
                "ldo_efficiency_factor": cfg.ldo_efficiency_factor,
                "voltage_reference_explanation": (
                    "Currents are measured at the 3.3V regulated MCU rail boundary. "
                    "A 1200 mAh 1S Li-Po cell (3.7V nominal, 13,586.40 J usable @ 85% DoD) "
                    "delivers 12,117.60 J through a 3.3V linear regulator (efficiency 3.3V/3.7V ≈ 89.2%)."
                ),
            },
            "radio_sensitivity_sweep": radio_sensitivity_sweep,
            "record_count": n,
            "high_sensitivity_count": n_high,
            "low_sensitivity_count": n_routine,
            "config": cfg.model_dump(),
            "baseline": {
                "total_energy_joules": total_energy_base_j,
                "total_energy_joules_display": round(total_energy_base_j, 8),
                "energy_proc_joules": round(e_proc_base_j, 8),
                "energy_crypto_joules": round(e_crypto_base_j, 8),
                "energy_aes_joules": round(e_crypto_base_j, 8),
                "energy_sha_joules": 0.0,
                "energy_xor_joules": 0.0,
                "energy_hmac_joules": 0.0,
                "energy_tx_joules": round(e_tx_base_j, 8),
                "energy_idle_joules": round(e_idle_base_j, 8),
                "crypto_duration_ms": round(t_crypto_base_ms, 4),
                "crypto_cpu_cycles": round(crypto_cycles_base, 0),
                "shared_proc_duration_ms": round(t_proc_base_ms, 4),
                "tx_duration_ms": round(t_tx_base_ms, 4),
                "idle_duration_ms": round(t_idle_base_ms, 4),
                "total_duration_ms": round(t_total_base_ms, 4),
                "mean_current_ma": round(mean_current_base_ma, 4),
                "mean_power_mw": round(mean_power_base_mw, 4),
                "charge_consumed_mah": round(charge_consumed_base_mah, 8),
                "indicative_runtime_hours": round(runtime_base_hours, 2),
            },
            "adaptive": {
                "total_energy_joules": total_energy_adapt_j,
                "total_energy_joules_display": round(total_energy_adapt_j, 8),
                "energy_proc_joules": round(e_proc_adapt_j, 8),
                "energy_crypto_joules": round(e_crypto_adapt_j, 8),
                "energy_aes_joules": round(e_aes_adapt_j, 8),
                "energy_sha_joules": round(e_sha_adapt_j, 8),
                "energy_xor_joules": round(e_xor_adapt_j, 8),
                "energy_hmac_joules": round(e_hmac_adapt_j, 8),
                "energy_tx_joules": round(e_tx_adapt_j, 8),
                "energy_idle_joules": round(e_idle_adapt_j, 8),
                "crypto_duration_ms": round(t_crypto_adapt_ms, 4),
                "crypto_cpu_cycles": round(crypto_cycles_adapt, 0),
                "shared_proc_duration_ms": round(t_proc_adapt_ms, 4),
                "tx_duration_ms": round(t_tx_adapt_ms, 4),
                "idle_duration_ms": round(t_idle_adapt_ms, 4),
                "total_duration_ms": round(t_total_adapt_ms, 4),
                "mean_current_ma": round(mean_current_adapt_ma, 4),
                "mean_power_mw": round(mean_power_adapt_mw, 4),
                "charge_consumed_mah": round(charge_consumed_adapt_mah, 8),
                "indicative_runtime_hours": round(runtime_adapt_hours, 2),
            },
            "energy_comparison": comp_energy,
            "crypto_time_comparison": comp_crypto_time,
            "crypto_cycles_comparison": comp_crypto_cycles,
            "crypto_energy_comparison": comp_crypto_energy,
        }

    def simulate_battery_on_records(
        self,
        records: List[Any],
        pipeline_run_id: str = "PIPE-DEFAULT",
        repetitions: int = 1,
        radio_tx_ms_override: Optional[float] = None,
        profile_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Perform authoritative per-record battery simulation and cumulative drain tracking
        on the exact records of the current pipeline run using the active MCU hardware model.
        """
        cfg = self.config
        if radio_tx_ms_override is not None:
            cfg = cfg.model_copy(update={"t_radio_tx_ms": float(radio_tx_ms_override)})
        elif profile_name in ["short_tx", "short"]:
            cfg = cfg.model_copy(update={"t_radio_tx_ms": 0.50})
        elif profile_name in ["radio_heavy", "heavy"]:
            cfg = cfg.model_copy(update={"t_radio_tx_ms": 1.50})

        v = cfg.supply_voltage_v
        usable_rail_energy_joules = (
            (cfg.battery_nominal_mah / 1000.0) * 3600.0 * v * cfg.battery_usable_factor
        )

        # Baseline per-record timing and energy components
        t_proc_ms = cfg.t_shared_proc_ms
        t_tx_ms = cfg.t_radio_tx_ms
        t_crypto_base_ms = cfg.t_aes_gcm_ms
        t_active_base_ms = t_proc_ms + t_crypto_base_ms + t_tx_ms
        t_idle_base_ms = max(0.0, cfg.t_duty_cycle_period_ms - t_active_base_ms)

        e_proc_j = v * (cfg.cpu_active_current_ma / 1000.0) * (t_proc_ms / 1000.0)
        e_tx_j = v * (cfg.radio_tx_current_ma / 1000.0) * (t_tx_ms / 1000.0)
        e_crypto_base_j = v * (cfg.aes_active_current_ma / 1000.0) * (t_crypto_base_ms / 1000.0)
        e_idle_base_j = v * (cfg.idle_sleep_current_ma / 1000.0) * (t_idle_base_ms / 1000.0)
        e_rec_base_j = e_proc_j + e_crypto_base_j + e_tx_j + e_idle_base_j

        # Adaptive routine per-record timing and energy components (SHA-256 + XOR + HMAC)
        t_sha_ms = cfg.t_sha256_keystream_ms
        t_xor_ms = cfg.t_xor_stream_ms
        t_hmac_ms = cfg.t_hmac_sha256_ms
        t_crypto_routine_ms = t_sha_ms + t_xor_ms + t_hmac_ms
        t_active_routine_ms = t_proc_ms + t_crypto_routine_ms + t_tx_ms
        t_idle_routine_ms = max(0.0, cfg.t_duty_cycle_period_ms - t_active_routine_ms)

        e_sha_j = v * (cfg.sha256_active_current_ma / 1000.0) * (t_sha_ms / 1000.0)
        e_xor_j = v * (cfg.xor_active_current_ma / 1000.0) * (t_xor_ms / 1000.0)
        e_hmac_j = v * (cfg.hmac_active_current_ma / 1000.0) * (t_hmac_ms / 1000.0)
        e_crypto_routine_j = e_sha_j + e_xor_j + e_hmac_j
        e_idle_routine_j = v * (cfg.idle_sleep_current_ma / 1000.0) * (t_idle_routine_ms / 1000.0)
        e_rec_routine_j = e_proc_j + e_crypto_routine_j + e_tx_j + e_idle_routine_j

        reps = max(1, int(repetitions))
        max_sim_packets = 50_000
        total_requested = len(records) * reps
        if total_requested > max_sim_packets:
            raise ValueError(
                f"Simulation workload of {total_requested} packets ({reps} repetitions x {len(records)} records) "
                f"exceeds documented safe export limit of {max_sim_packets} packets. "
                f"Please select repetitions <= {max_sim_packets // max(1, len(records))} to prevent memory exhaustion."
            )

        cum_base_j = 0.0
        cum_adapt_j = 0.0
        per_record_entries: List[Dict[str, Any]] = []
        n_high = 0
        n_routine = 0
        global_packet_idx = 0

        for rep in range(1, reps + 1):
            for r in records:
                global_packet_idx += 1
                rec_id = getattr(r, "record_id", "UNKNOWN-REC")
                c_id = getattr(r, "kmeans_cluster_id", 0)
                if c_id is None:
                    c_id = 0
                c_label = getattr(r, "cluster_label", "CLUSTER-LOW") or "CLUSTER-LOW"

                eff_sec_attr = getattr(r, "effective_security_class", None) or getattr(r, "sensitivity", None) or "LOW"
                eff_sec_str = eff_sec_attr.value if hasattr(eff_sec_attr, "value") else str(eff_sec_attr)

                is_high = (eff_sec_str.upper() == "HIGH")
                if rep == 1:
                    if is_high:
                        n_high += 1
                    else:
                        n_routine += 1

                if is_high:
                    adapt_algo = "AES-256-GCM"
                    adapt_e_crypto = e_crypto_base_j
                    adapt_e_idle = e_idle_base_j
                    adapt_e_rec = e_rec_base_j
                else:
                    adapt_algo = "XOR-EXPERIMENTAL"
                    adapt_e_crypto = e_crypto_routine_j
                    adapt_e_idle = e_idle_routine_j
                    adapt_e_rec = e_rec_routine_j

                cum_base_j += e_rec_base_j
                cum_adapt_j += adapt_e_rec

                base_depletion_pct = (cum_base_j / usable_rail_energy_joules) * 100.0
                adapt_depletion_pct = (cum_adapt_j / usable_rail_energy_joules) * 100.0

                base_rem_pct = max(0.0, min(100.0, 100.0 - base_depletion_pct))
                adapt_rem_pct = max(0.0, min(100.0, 100.0 - adapt_depletion_pct))

                per_record_entries.append({
                    "pipeline_run_id": pipeline_run_id,
                    "dataset_id": pipeline_run_id,
                    "record_id": rec_id,
                    "repetition_index": rep,
                    "packet_index": global_packet_idx,
                    "kmeans_cluster_id": int(c_id),
                    "cluster_label": c_label,
                    "effective_security_class": eff_sec_str,
                    "baseline_algorithm": "AES-256-GCM",
                    "adaptive_algorithm": adapt_algo,
                    "baseline_energy_joules": round(e_rec_base_j, 8),
                    "adaptive_energy_joules": round(adapt_e_rec, 8),
                    "baseline_cumulative_energy_joules": round(cum_base_j, 8),
                    "adaptive_cumulative_energy_joules": round(cum_adapt_j, 8),
                    "baseline_battery_remaining_percent": round(base_rem_pct, 6),
                    "adaptive_battery_remaining_percent": round(adapt_rem_pct, 6),
                    "baseline_crypto_energy_joules": round(e_crypto_base_j, 8),
                    "adaptive_crypto_energy_joules": round(adapt_e_crypto, 8),
                    "shared_proc_energy_joules": round(e_proc_j, 8),
                    "radio_tx_energy_joules": round(e_tx_j, 8),
                    "idle_sleep_energy_joules": round(adapt_e_idle, 8),
                })

        total_base_j = cum_base_j
        total_adapt_j = cum_adapt_j
        single_batch_base_j = cum_base_j / reps
        single_batch_adapt_j = cum_adapt_j / reps

        final_base_rem = max(0.0, min(100.0, 100.0 - (total_base_j / usable_rail_energy_joules) * 100.0))
        final_adapt_rem = max(0.0, min(100.0, 100.0 - (total_adapt_j / usable_rail_energy_joules) * 100.0))

        delta_energy = total_base_j - total_adapt_j
        pct_saving = (delta_energy / total_base_j) * 100.0 if total_base_j > 0 else 0.0

        packet_cadence_ms = cfg.t_duty_cycle_period_ms
        sim_duration_s = reps * (len(records) * packet_cadence_ms / 1000.0)

        # Profile naming
        if abs(cfg.t_radio_tx_ms - 0.50) < 0.05:
            prof_id = "short_tx"
            prof_name = "Compute-Intensive / Short-Transmission MCU Scenario (0.50 ms Radio TX)"
        elif abs(cfg.t_radio_tx_ms - 1.50) < 0.05:
            prof_id = "radio_heavy"
            prof_name = "Radio-Heavy MCU Model (1.50 ms Radio TX)"
        else:
            prof_id = "custom"
            prof_name = f"Custom MCU Configuration ({cfg.t_radio_tx_ms:.2f} ms Radio TX)"

        return {
            "pipeline_run_id": pipeline_run_id,
            "dataset_id": pipeline_run_id,
            "total_records": len(records),
            "total_packets_simulated": len(per_record_entries),
            "high_sensitivity_count": n_high,
            "low_sensitivity_count": n_routine,
            "scenario_name": prof_name,
            "profile_id": prof_id,
            "simulated_repetitions": reps,
            "simulated_operating_seconds": round(sim_duration_s, 2),
            "cadence_period_ms": packet_cadence_ms,
            "reporting_frequency_hz": round(1000.0 / packet_cadence_ms, 2),
            "starting_capacity_mah": cfg.battery_nominal_mah,
            "usable_capacity_mah": round(cfg.battery_nominal_mah * cfg.battery_usable_factor, 2),
            "usable_rail_energy_joules": round(usable_rail_energy_joules, 2),
            "baseline_batch_energy_joules": round(single_batch_base_j, 8),
            "adaptive_batch_energy_joules": round(single_batch_adapt_j, 8),
            "baseline_total_energy_joules": round(total_base_j, 8),
            "adaptive_total_energy_joules": round(total_adapt_j, 8),
            "baseline_final_remaining_percent": round(final_base_rem, 4),
            "adaptive_final_remaining_percent": round(final_adapt_rem, 4),
            "energy_saving_percent": round(pct_saving, 2),
            "record_count": len(records),
            "baseline_remaining_pct": round(final_base_rem, 4),
            "adaptive_remaining_pct": round(final_adapt_rem, 4),
            "energy_savings_pct": round(pct_saving, 2),
            "battery_nominal_mah": cfg.battery_nominal_mah,
            "duration_batches": reps,
            "derivation_formula": (
                "Energy (J) = Voltage (3.3V) x Current (A) x Duration (s). "
                "Depletion % = (Cumulative Energy / 12,117.60 J) x 100. "
                "Remaining % = 100.0% - Depletion %."
            ),
            "cadence_disclaimer": (
                f"Physical energy model assumes periodic {1000.0 / packet_cadence_ms:.0f} Hz reporting "
                f"({packet_cadence_ms:.1f} ms period) with MCU sleep ({cfg.idle_sleep_current_ma*1000:.0f} µA). "
                "Generated timestamps represent record indices and human timeline readability."
            ),
            "records": per_record_entries,
        }

