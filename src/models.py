"""Data models for IoT Healthcare Data Encryption and Clustering.
All records are strictly synthetic demo data for research and education.
"""

from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class SensitivityLevel(str, Enum):
    HIGH = "HIGH"
    LOW = "LOW"


class EncryptionAlgorithm(str, Enum):
    AES_256_GCM = "AES-256-GCM"
    XOR_LIGHTWEIGHT = "XOR-EXPERIMENTAL"


class MeasurementSource(str, Enum):
    HARDWARE = "hardware"
    IMPORTED = "imported"
    ESTIMATED = "estimated"
    SIMULATED = "simulated"


class BenchmarkMode(str, Enum):
    BASELINE = "baseline"
    ADAPTIVE = "adaptive"


class RecordType(str, Enum):
    HEART_RATE = "heart_rate"
    ECG_SUMMARY = "ecg_summary"
    TEMPERATURE = "temperature"
    STEP_COUNT = "step_count"


class SensorRecord(BaseModel):
    """Synthetic healthcare sensor record."""
    record_id: str
    timestamp: str
    demo_patient_id: str
    record_type: RecordType
    value: float
    unit: str
    is_synthetic: bool = True
    sensitivity: Optional[SensitivityLevel] = None
    classification_reason: Optional[str] = None
    cluster_id: Optional[str] = None

    # Lineage and ML K-Means clustering traceability
    pipeline_run_id: Optional[str] = None
    kmeans_cluster_id: Optional[int] = None
    cluster_label: Optional[str] = None
    policy_sensitivity: Optional[SensitivityLevel] = None
    effective_security_class: Optional[SensitivityLevel] = None
    policy_override: bool = False
    override_reason: Optional[str] = None

    model_config = {"frozen": False}


class FeatureVector(BaseModel):
    """Engineered and standardized features for a single sensor record."""
    record_id: str
    record_type: str
    raw_value: float
    unit: str
    features: Dict[str, float]
    scaled_features: Dict[str, float]


class KMeansConfig(BaseModel):
    """Configuration parameters for scikit-learn K-Means model."""
    n_clusters: int = 2
    random_state: int = 42
    n_init: int = 10
    algorithm: str = "lloyd"


class KMeansDiagnostics(BaseModel):
    """Mathematical, evaluation protocol, and security diagnostic metrics for K-Means clustering run."""
    n_samples: int
    n_features: int
    feature_names: List[str]
    cluster_counts: Dict[str, int]
    semantic_counts: Dict[str, int]
    centroids: Dict[str, Dict[str, float]]
    unscaled_centroids: Dict[str, Dict[str, float]]
    inertia: float
    silhouette_score: Optional[float] = None
    silhouette_note: Optional[str] = None

    # Defensible evaluation protocol and explicit labeling
    agreement_metric_label: str = "within-run agreement with synthetic rule-based sensitivity labels"
    agreement_ratio: float  # Maintained for backward compatibility (= within_run_agreement_ratio)
    within_run_agreement_ratio: float = 0.0
    evaluation_protocol: str = "CALIBRATION_HELD_OUT_EVALUATION"
    calibration_sample_count: Optional[int] = None
    held_out_sample_count: Optional[int] = None
    held_out_agreement_ratio: Optional[float] = None
    held_out_confusion_matrix: Optional[Dict[str, int]] = None
    semantic_mapping_method: str = "centroid_physiological_deviation"
    limitations_note: str = (
        "Evaluated against synthetic rule-based policy labels; "
        "does not constitute independent clinical or generalization validation."
    )

    confusion_matrix: Dict[str, int]
    guardrail_overrides_count: int
    warnings: List[str] = Field(default_factory=list)


class ClusteringResult(BaseModel):
    """Outcome of fitting and predicting with real K-Means on a dataset."""
    pipeline_run_id: str
    config: KMeansConfig
    diagnostics: KMeansDiagnostics
    total_records: int
    cluster_mapping: Dict[str, str]



class SensitivityRule(BaseModel):
    """Rule definition for classifying sensor record sensitivity."""
    record_type: RecordType
    min_critical_value: Optional[float] = None
    max_critical_value: Optional[float] = None
    always_high: bool = False
    always_low: bool = False
    high_reason: str
    low_reason: str


class SensitivityRuleset(BaseModel):
    """Configurable collection of classification rules."""
    rules: Dict[RecordType, SensitivityRule] = Field(default_factory=dict)


class ClusterGroup(BaseModel):
    """Cluster containing partitioned records."""
    cluster_id: str
    sensitivity: SensitivityLevel
    records: List[SensorRecord]
    record_count: int


class EncryptedEnvelope(BaseModel):
    """Envelope holding encrypted record payload and cryptographic metadata."""
    run_id: str
    record_id: str
    algorithm: EncryptionAlgorithm
    sensitivity: SensitivityLevel
    cluster_id: str
    nonce_hex: str  # 96-bit nonce for AES-GCM or keystream IV for XOR
    ciphertext_hex: str
    tag_hex: Optional[str] = None  # 128-bit authentication tag for AES-GCM
    hmac_hex: Optional[str] = None  # HMAC-SHA256 integrity tag for experimental XOR
    payload_bytes: int
    created_at: str
    tampered: bool = False


class ReceiverVerificationResult(BaseModel):
    """Verification outcome produced by local healthcare receiver."""
    record_id: str
    verified: bool
    algorithm: EncryptionAlgorithm
    decrypted_record: Optional[SensorRecord] = None
    error_message: Optional[str] = None
    arrival_timestamp: str


class PowerSample(BaseModel):
    """Single electrical power observation."""
    timestamp_ms: float
    voltage_v: float
    current_ma: float
    power_mw: float
    measurement_source: MeasurementSource


class PowerModelConfig(BaseModel):
    """Configurable parameters for software energy estimation."""
    battery_cell_nominal_voltage_v: float = 3.7  # 1S Li-Po cell nominal voltage
    supply_voltage_v: float = 3.3                # Regulated MCU rail voltage
    ldo_efficiency_factor: float = 0.8919        # Theoretical LDO efficiency (3.3V / 3.7V)
    idle_current_ma: float = 12.0
    active_mcu_current_ma: float = 35.0
    aes_crypto_current_ma: float = 54.0
    xor_crypto_current_ma: float = 22.0
    tx_current_ma: float = 85.0
    tx_duration_ms_per_packet: float = 1.8
    battery_nominal_mah: float = 1200.0
    battery_usable_factor: float = 0.85


class McuHardwareScenarioConfig(BaseModel):
    """Configurable parameters for the hypothetical constrained IoT microcontroller (Scenario B).
    Models a bare-metal edge MCU without hardware AES acceleration (e.g. ARM Cortex-M0+ or AVR @ 16 MHz).
    """
    mcu_model_name: str = "ARM Cortex-M0+ (16 MHz, No AES Hardware)"
    battery_cell_nominal_voltage_v: float = 3.7  # 1S Li-Po cell nominal voltage (3.0V - 4.2V operating range)
    supply_voltage_v: float = 3.3                # Regulated MCU operating rail voltage
    ldo_efficiency_factor: float = 0.8919        # Theoretical linear LDO step-down efficiency (V_rail / V_cell = 3.3 / 3.7)
    mcu_clock_hz: float = 16_000_000.0          # Configurable MCU CPU clock (default 16 MHz)
    battery_nominal_mah: float = 1200.0
    battery_usable_factor: float = 0.85

    # Non-overlapping operational current draws (mA)
    cpu_active_current_ma: float = 8.5
    aes_active_current_ma: float = 9.8
    sha256_active_current_ma: float = 8.2
    xor_active_current_ma: float = 7.5
    hmac_active_current_ma: float = 8.4
    radio_tx_current_ma: float = 28.0
    idle_sleep_current_ma: float = 0.015  # 15 uA

    # Non-overlapping per-record operational timings (ms)
    t_shared_proc_ms: float = 0.35       # Sensor sample reading, packaging, serialization (~5,600 cycles @ 16 MHz)
    t_aes_gcm_ms: float = 1.25           # Software AES-256 + GHASH (~20,000 CPU cycles @ 16 MHz)
    t_sha256_keystream_ms: float = 0.25  # SHA-256 block keystream generation (~4,000 cycles @ 16 MHz)
    t_xor_stream_ms: float = 0.01        # Bitwise 64-byte XOR loop (~160 cycles @ 16 MHz)
    t_hmac_sha256_ms: float = 0.38       # 2-pass HMAC-SHA256 authentication tag (~6,080 cycles @ 16 MHz)
    t_radio_tx_ms: float = 1.50          # Radio packet transmission (802.15.4 / BLE)
    t_duty_cycle_period_ms: float = 20.0 # Nominal packet cycle period for idle interval calculation


class PerRecordBatteryEntry(BaseModel):
    """Detailed energy accounting and cumulative battery drain for a single record."""
    pipeline_run_id: str
    record_id: str
    repetition_index: int = 1
    packet_index: int = 1
    kmeans_cluster_id: int
    cluster_label: str
    effective_security_class: str
    baseline_algorithm: str
    adaptive_algorithm: str
    baseline_energy_joules: float
    adaptive_energy_joules: float
    baseline_cumulative_energy_joules: float
    adaptive_cumulative_energy_joules: float
    baseline_battery_remaining_percent: float
    adaptive_battery_remaining_percent: float
    baseline_crypto_energy_joules: Optional[float] = None
    adaptive_crypto_energy_joules: Optional[float] = None
    shared_proc_energy_joules: Optional[float] = None
    radio_tx_energy_joules: Optional[float] = None
    idle_sleep_energy_joules: Optional[float] = None


class BatterySimulationResult(BaseModel):
    """Result of running physics-based battery simulation on an active dataset."""
    pipeline_run_id: str
    total_records: int
    high_sensitivity_count: int
    low_sensitivity_count: int
    scenario_name: str
    profile_id: str
    simulated_repetitions: int = 1
    simulated_operating_seconds: float
    cadence_period_ms: float = 20.0
    reporting_frequency_hz: Optional[float] = None
    starting_capacity_mah: float
    usable_capacity_mah: Optional[float] = None
    usable_rail_energy_joules: float
    baseline_batch_energy_joules: float
    adaptive_batch_energy_joules: float
    baseline_total_energy_joules: float
    adaptive_total_energy_joules: float
    baseline_final_remaining_percent: float
    adaptive_final_remaining_percent: float
    energy_saving_percent: float
    records: List[PerRecordBatteryEntry]
    record_count: Optional[int] = None
    total_packets_simulated: Optional[int] = None
    baseline_remaining_pct: Optional[float] = None
    adaptive_remaining_pct: Optional[float] = None
    energy_savings_pct: Optional[float] = None
    battery_nominal_mah: Optional[float] = None
    duration_batches: Optional[int] = None
    derivation_formula: Optional[str] = None
    cadence_disclaimer: Optional[str] = None



class BatchMetrics(BaseModel):
    """Computed metrics for a single baseline or adaptive run."""
    run_id: str
    mode: BenchmarkMode
    seed: int
    record_count: int
    repeat_index: int = 1
    high_sensitivity_count: int
    low_sensitivity_count: int
    aes_record_count: int
    xor_record_count: int
    total_payload_bytes: int

    # Timing breakdown (milliseconds)
    classification_time_total_ms: float = 0.0
    clustering_time_total_ms: float = 0.0
    encryption_time_mean_ms: float
    encryption_time_median_ms: float
    encryption_time_p95_ms: float
    encryption_time_total_ms: float
    authentication_time_total_ms: float = 0.0
    serialization_time_total_ms: float
    transmission_time_total_ms: float
    end_to_end_duration_ms: float

    # Transmission metrics
    records_sent: int
    records_received: int
    records_rejected: int
    records_lost: int
    tsr_percent: float  # Transmission Success Rate
    plr_percent: float  # Packet Loss Rate

    # Energy metrics
    measurement_source: MeasurementSource
    mean_voltage_v: float
    mean_current_ma: float
    mean_power_mw: float
    total_energy_joules: float
    energy_per_record_mj: float
    energy_per_100_records_mj: float
    energy_per_1000_records_mj: float = 0.0
    estimated_battery_charge_consumed_mah: Optional[float] = None
    estimated_runtime_hours: Optional[float] = None

    started_at: str
    completed_at: str
    status: str = "COMPLETED"
    error_details: Optional[str] = None
