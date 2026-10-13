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
)
from src.metrics import integrate_energy_joules


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
    """Hardware adapter for dedicated serial power meters or INA219 current sensors."""

    def __init__(self, port: Optional[str] = None, baudrate: int = 115200):
        self.port = port
        self.baudrate = baudrate
        self.is_connected = False
        self._samples_v: List[float] = []
        self._samples_i_ma: List[float] = []
        self._samples_t_ms: List[float] = []

    def start_sampling(self):
        if not self.port:
            raise ConnectionError("No hardware power sensor COM port configured.")
        # In a real attached meter, open serial connection and begin reader thread
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
            "description": "Physical current/voltage sensor reading",
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
