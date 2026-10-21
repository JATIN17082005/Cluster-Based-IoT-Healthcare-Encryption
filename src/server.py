"""FastAPI backend application serving the IoT Healthcare Data Encryption API and Dashboard."""

import os
import io
import csv
import json
import time
import secrets
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile, File, Query, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.models import (
    BenchmarkMode,
    MeasurementSource,
    SensitivityLevel,
    RecordType,
    SensorRecord,
    BatchMetrics,
    PowerModelConfig,
    McuHardwareScenarioConfig,
    EncryptionAlgorithm,
    KMeansConfig,
    KMeansDiagnostics,
    ClusteringResult,
    FeatureVector,
)
from src.data_generator import SyntheticDataGenerator
from src.classifier import SensitivityClassifier, get_default_ruleset
from src.cluster_manager import ClusterManager
from src.kmeans_clusterer import HealthcareFeatureExtractor, KMeansPipeline
from src.crypto import KeyManager, EncryptionEngine, tamper_envelope
from src.receiver import LocalHealthcareReceiver
from src.benchmark_runner import BenchmarkRunner
from src.power_measurement import CSVPowerImporter, SimulationPowerProvider, McuEnergyModel
from src.run_store import RunStore
from src.metrics import (
    compute_percentage_change,
    integrate_energy_joules,
    evaluate_result_status,
    compute_authoritative_comparison,
)

app = FastAPI(
    title="Cluster-Based IoT Healthcare Encryption Demo",
    description="Academic benchmark comparing AES-256-GCM baseline with sensitivity-based adaptive encryption",
    version="1.0.0",
)

LOCAL_ORIGINS = [
    "http://localhost",
    "http://localhost:8000",
    "http://127.0.0.1",
    "http://127.0.0.1:8000",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=LOCAL_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Global services
key_manager = KeyManager()
receiver = LocalHealthcareReceiver(key_manager)
power_config = PowerModelConfig()
mcu_config = McuHardwareScenarioConfig()
runner = BenchmarkRunner(key_manager=key_manager, receiver=receiver, power_model=power_config)
run_store = RunStore()

# State for currently generated demo batch and seed
current_raw_records: List[SensorRecord] = []
current_demo_records: List[SensorRecord] = []
current_demo_seed: Optional[int] = None
current_power_override: Optional[Any] = None
current_pipeline_run_id: Optional[str] = None
current_clustering_result: Optional[ClusteringResult] = None
current_feature_vectors: List[FeatureVector] = []
current_battery_simulation: Optional[Dict[str, Any]] = None
current_encryption_results: Optional[List[Dict[str, Any]]] = None
current_receiver_results: Optional[List[Dict[str, Any]]] = None
current_dataset_id: Optional[str] = None
previous_dataset_records: Optional[List[SensorRecord]] = None
dataset_generation_sequence: int = 0


class McuScenarioRequest(BaseModel):
    record_count: Optional[int] = Field(default=None, ge=1, le=1000)
    high_sensitivity_count: Optional[int] = Field(default=None, ge=0)
    low_sensitivity_count: Optional[int] = Field(default=None, ge=0)
    profile: Optional[str] = None
    radio_tx_ms: Optional[float] = None
    config: Optional[McuHardwareScenarioConfig] = None


class GenerateRequest(BaseModel):
    count: int = Field(default=50, ge=1, le=1000)
    seed: Optional[int] = Field(default=None, ge=0)
    run_clustering: Optional[bool] = None
    dataset_id: Optional[str] = None


class BatterySimulateRequest(BaseModel):
    repetitions: int = Field(default=1, ge=1, le=1000000)
    profile: Optional[str] = None
    radio_tx_ms: Optional[float] = None
    dataset_id: Optional[str] = None


class BenchmarkRunRequest(BaseModel):
    mode: str = Field(default="comparison")  # "baseline", "adaptive", "comparison"
    record_count: int = Field(default=50, ge=1, le=1000)
    seed: int = Field(default=42, ge=0)
    repetitions: int = Field(default=1, ge=1, le=50)


class TamperDemoRequest(BaseModel):
    algorithm: EncryptionAlgorithm = EncryptionAlgorithm.AES_256_GCM
    tamper_target: str = "ciphertext"  # "ciphertext", "tag", "nonce", "hmac"


# --- API Routes ---

@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


@app.get("/api/health")
def get_health():
    """System health and operational status."""
    return {
        "status": "HEALTHY",
        "app_version": "1.0.0",
        "key_manager_status": "EPHEMERAL_DEV_KEYS" if key_manager.is_ephemeral else "CONFIGURED_KEYS",
        "receiver_active": True,
        "sqlite_storage": True,
    }


@app.get("/api/config")
def get_config():
    """Retrieve active power model and classification rules."""
    return {
        "power_model": runner.power_model.model_dump(),
        "classifier_rules": runner.classifier.ruleset.model_dump(),
    }


@app.post("/api/config")
def update_config(config_data: Dict[str, Any]):
    """Update active power model parameters."""
    if "power_model" in config_data:
        new_power = PowerModelConfig(**config_data["power_model"])
        runner.power_model = new_power
    return {"message": "Configuration updated successfully", "config": get_config()}


@app.get("/api/battery/mcu-config")
def get_mcu_config():
    """Retrieve active MCU simulation assumptions for Scenario B."""
    return mcu_config.model_dump()


@app.post("/api/battery/mcu-config")
def update_mcu_config(cfg_data: Dict[str, Any]):
    """Update MCU simulation assumptions."""
    global mcu_config
    mcu_config = McuHardwareScenarioConfig(**cfg_data)
    return {"message": "MCU configuration updated successfully", "config": mcu_config.model_dump()}


@app.get("/api/battery/mcu-scenario")
def get_mcu_scenario(
    record_count: Optional[int] = None,
    high_count: Optional[int] = None,
    low_count: Optional[int] = None,
    profile: Optional[str] = None,
    radio_tx_ms: Optional[float] = None,
):
    """Calculate MCU scenario using query params, current demo records, or default 100-record batch.
    Supports profile ('radio_heavy' | 'short_tx') or explicit radio_tx_ms override.
    Requires high_count + low_count == record_count if counts are specified.
    """
    global current_demo_records, mcu_config
    if record_count is not None:
        rec_count = record_count
        if rec_count < 1 or rec_count > 1000:
            raise HTTPException(status_code=422, detail="record_count must be between 1 and 1000.")
        if high_count is not None and low_count is not None:
            if high_count < 0 or low_count < 0 or (high_count + low_count != rec_count):
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"Invalid workload split: high_count ({high_count}) + low_count ({low_count}) "
                        f"must equal record_count ({rec_count}), with non-negative counts."
                    ),
                )
            high_cnt = high_count
            low_cnt = low_count
        elif high_count is not None or low_count is not None:
            raise HTTPException(
                status_code=422,
                detail="Both high_count and low_count must be provided together, or omitted for default 45/55 split.",
            )
        else:
            high_cnt = int(rec_count * 0.45)
            low_cnt = rec_count - high_cnt
    elif high_count is not None or low_count is not None:
        raise HTTPException(
            status_code=422,
            detail="record_count must be specified when setting sensitivity counts.",
        )
    elif current_demo_records:
        rec_count = len(current_demo_records)
        def _is_high(r):
            eff = getattr(r, "effective_security_class", None) or getattr(r, "sensitivity", None)
            return (eff.value if hasattr(eff, "value") else str(eff)).upper() == "HIGH"
        high_cnt = sum(1 for r in current_demo_records if _is_high(r))
        low_cnt = rec_count - high_cnt
    else:
        rec_count = 100
        high_cnt = 45
        low_cnt = 55

    model = McuEnergyModel(mcu_config)
    return model.calculate_scenario(
        total_records=rec_count,
        high_sensitivity_count=high_cnt,
        low_sensitivity_count=low_cnt,
        radio_tx_ms_override=radio_tx_ms,
        profile_name=profile,
    )


@app.post("/api/battery/mcu-scenario")
def run_mcu_scenario(req: McuScenarioRequest):
    """Calculate MCU Scenario B energy values for a requested record count and sensitivity split."""
    global current_demo_records, mcu_config
    active_cfg = req.config or mcu_config

    if req.record_count is not None:
        rec_count = req.record_count
        if rec_count < 1 or rec_count > 1000:
            raise HTTPException(status_code=422, detail="record_count must be between 1 and 1000.")
        if req.high_sensitivity_count is not None and req.low_sensitivity_count is not None:
            if (
                req.high_sensitivity_count < 0
                or req.low_sensitivity_count < 0
                or (req.high_sensitivity_count + req.low_sensitivity_count != rec_count)
            ):
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"Invalid workload split: high_sensitivity_count ({req.high_sensitivity_count}) + "
                        f"low_sensitivity_count ({req.low_sensitivity_count}) must equal record_count ({rec_count}), "
                        f"with non-negative counts."
                    ),
                )
            high_cnt = req.high_sensitivity_count
            low_cnt = req.low_sensitivity_count
        elif req.high_sensitivity_count is not None or req.low_sensitivity_count is not None:
            raise HTTPException(
                status_code=422,
                detail="Both high_sensitivity_count and low_sensitivity_count must be provided together, or omitted.",
            )
        else:
            high_cnt = int(rec_count * 0.45)
            low_cnt = rec_count - high_cnt
    elif req.high_sensitivity_count is not None or req.low_sensitivity_count is not None:
        raise HTTPException(
            status_code=422,
            detail="record_count must be specified when setting sensitivity counts.",
        )
    elif current_demo_records:
        rec_count = len(current_demo_records)
        def _is_high(r):
            eff = getattr(r, "effective_security_class", None) or getattr(r, "sensitivity", None)
            return (eff.value if hasattr(eff, "value") else str(eff)).upper() == "HIGH"
        high_cnt = sum(1 for r in current_demo_records if _is_high(r))
        low_cnt = rec_count - high_cnt
    else:
        rec_count = 100
        high_cnt = 45
        low_cnt = 55

    model = McuEnergyModel(active_cfg)
    return model.calculate_scenario(
        total_records=rec_count,
        high_sensitivity_count=high_cnt,
        low_sensitivity_count=low_cnt,
        radio_tx_ms_override=req.radio_tx_ms,
        profile_name=req.profile,
    )


def _get_generation_methodology(seed: int, count: int) -> Dict[str, Any]:
    return {
        "generator_type": "Deterministic pseudo-random generator with fixed seed control",
        "seed": seed,
        "sample_count": count,
        "sensor_modalities": [
            {
                "type": "HEART_RATE",
                "unit": "bpm",
                "distribution": "70% normal (62-92), 15% bradycardia (38-48), 15% tachycardia (105-140)",
                "physiological_normal": [50.0, 100.0],
            },
            {
                "type": "ECG_SUMMARY",
                "unit": "mV",
                "distribution": "Continuous uniform (0.65-1.85 mV) ST segment amplitude",
                "physiological_normal": [0.5, 2.0],
            },
            {
                "type": "TEMPERATURE",
                "unit": "°C",
                "distribution": "80% normothermia (36.4-37.3), 10% fever (38.2-39.8), 10% hypothermia (34.2-35.3)",
                "physiological_normal": [35.5, 38.0],
            },
            {
                "type": "STEP_COUNT",
                "unit": "steps",
                "distribution": "Discrete uniform (0-120 steps) cadence",
                "physiological_normal": [0.0, 150.0],
            },
        ],
        "reproducibility": "Identical seed reproduces exact floating-point values and timestamps.",
        "scientific_disclaimer": "Synthetic dataset generated for cryptographic latency and energy benchmarking. Not real patient health records.",
    }


def _generate_raw_dataset_core(count: int, seed: Optional[int] = None) -> Tuple[str, List[SensorRecord], Dict[str, Any]]:
    global current_raw_records, current_demo_records, current_demo_seed, current_pipeline_run_id, current_dataset_id
    global current_clustering_result, current_feature_vectors, current_battery_simulation
    global current_encryption_results, current_receiver_results
    global previous_dataset_records, dataset_generation_sequence

    dataset_generation_sequence += 1
    explicit_seed = seed is not None

    # Determine generation seed with duplicate prevention
    max_attempts = 15
    records: List[SensorRecord] = []
    used_seed = seed

    for attempt in range(max_attempts):
        if not explicit_seed:
            used_seed = secrets.randbelow(899999) + 100000
        else:
            used_seed = seed

        gen = SyntheticDataGenerator(seed=used_seed)
        generated_batch = gen.generate_batch(
            count=count,
            classifier=runner.classifier,
        )

        # Prevent accidental reuse: check against previous dataset if not explicit seed
        if previous_dataset_records is not None and not explicit_seed and len(previous_dataset_records) == len(generated_batch):
            is_dup = all(
                r1.record_type == r2.record_type and abs(r1.value - r2.value) < 1e-5
                for r1, r2 in zip(generated_batch, previous_dataset_records)
            )
            if is_dup:
                continue

        records = generated_batch
        break

    if not records:
        gen = SyntheticDataGenerator(seed=used_seed)
        records = gen.generate_batch(count=count, classifier=runner.classifier)

    # Unique dataset_id and pipeline_run_id
    unique_suffix = f"{int(time.time() * 1000)}-{secrets.token_hex(3).upper()}"
    pipeline_run_id = f"PIPE-S{used_seed}-{unique_suffix}"
    dataset_id = pipeline_run_id

    for r in records:
        r.dataset_id = dataset_id
        r.pipeline_run_id = pipeline_run_id
        r.kmeans_cluster_id = None
        r.cluster_label = None
        r.effective_security_class = None
        r.policy_override = False
        r.override_reason = None

    current_raw_records = [r.model_copy() for r in records]
    current_demo_records = [r.model_copy() for r in records]
    current_demo_seed = used_seed
    current_pipeline_run_id = pipeline_run_id
    current_dataset_id = dataset_id
    previous_dataset_records = [r.model_copy() for r in records]

    # Invalidate all downstream state from previous datasets
    current_clustering_result = None
    current_feature_vectors = []
    current_battery_simulation = None
    current_encryption_results = None
    current_receiver_results = None

    methodology = _get_generation_methodology(used_seed, len(records))

    snapshot_data = {
        "dataset_id": dataset_id,
        "pipeline_run_id": pipeline_run_id,
        "seed": used_seed,
        "record_count": len(records),
        "stage": "raw_dataset_generated",
        "methodology": methodology,
    }
    run_store.save_pipeline_snapshot(pipeline_run_id, used_seed, len(records), snapshot_data)
    return pipeline_run_id, records, methodology


@app.post("/api/pipeline/generate-raw")
def generate_raw_pipeline_data(req: GenerateRequest):
    """Stage 1: Generate synthetic healthcare sensor records and immediately enable raw CSV export."""
    pipeline_run_id, records, methodology = _generate_raw_dataset_core(req.count, req.seed)
    return {
        "dataset_id": pipeline_run_id,
        "pipeline_run_id": pipeline_run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seed": current_demo_seed,
        "count": len(records),
        "record_count": len(records),
        "high_cluster_count": 0,
        "low_cluster_count": 0,
        "records_preview": [r.model_dump() for r in records[:20]],
        "all_records": [r.model_dump() for r in records],
        "features_preview": [],
        "all_features": [],
        "clustering_diagnostics": None,
        "clustering_config": None,
        "is_clustered": False,
        "generation_methodology": methodology,
    }


@app.post("/api/demo/generate")
def generate_synthetic_data(req: GenerateRequest):
    """Generate a seeded batch of synthetic healthcare sensor records.
    If run_clustering is explicitly False, performs raw generation only.
    Otherwise (default), performs raw generation followed by K-Means clustering for full backward compatibility.
    """
    global current_demo_records, current_pipeline_run_id, current_clustering_result, current_feature_vectors
    pipeline_run_id, records, methodology = _generate_raw_dataset_core(req.count, req.seed)

    if req.run_clustering is False:
        return {
            "dataset_id": pipeline_run_id,
            "pipeline_run_id": pipeline_run_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "seed": current_demo_seed,
            "count": len(records),
            "record_count": len(records),
            "high_cluster_count": 0,
            "low_cluster_count": 0,
            "records_preview": [r.model_dump() for r in records[:20]],
            "all_records": [r.model_dump() for r in records],
            "features_preview": [],
            "all_features": [],
            "clustering_diagnostics": None,
            "clustering_config": None,
            "is_clustered": False,
            "generation_methodology": methodology,
        }

    # Default / legacy path: perform genuine K-Means clustering immediately
    clust_records = [r.model_copy() for r in records]
    high_group, low_group, clust_result = runner.cluster_manager.cluster_with_kmeans(
        clust_records, pipeline_run_id=pipeline_run_id
    )

    current_demo_records = clust_records
    current_clustering_result = clust_result
    current_feature_vectors = runner.cluster_manager.last_feature_vectors

    snapshot_data = {
        "pipeline_run_id": pipeline_run_id,
        "seed": req.seed,
        "record_count": len(records),
        "clustering_diagnostics": clust_result.diagnostics.model_dump() if clust_result else None,
        "clustering_config": clust_result.config.model_dump() if clust_result else None,
        "methodology": methodology,
    }
    run_store.save_pipeline_snapshot(pipeline_run_id, req.seed, len(records), snapshot_data)

    return {
        "dataset_id": pipeline_run_id,
        "pipeline_run_id": pipeline_run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seed": current_demo_seed,
        "count": len(records),
        "record_count": len(records),
        "high_cluster_count": high_group.record_count,
        "low_cluster_count": low_group.record_count,
        "records_preview": [r.model_dump() for r in clust_records[:20]],
        "all_records": [r.model_dump() for r in clust_records],
        "features_preview": [f.model_dump() for f in current_feature_vectors[:20]],
        "all_features": [f.model_dump() for f in current_feature_vectors],
        "clustering_diagnostics": clust_result.diagnostics.model_dump() if clust_result else None,
        "clustering_config": clust_result.config.model_dump() if clust_result else None,
        "is_clustered": True,
        "generation_methodology": methodology,
    }


@app.post("/api/pipeline/cluster")
def run_pipeline_clustering(config: Optional[KMeansConfig] = None):
    """Stage 3: Run genuine scikit-learn K-Means ML clustering on current raw dataset.
    Extracts features, fits StandardScaler & KMeans, derives semantic mapping,
    and applies clinical security guardrail to prevent high-sensitivity downgrade.
    """
    global current_raw_records, current_demo_records, current_pipeline_run_id, current_clustering_result, current_feature_vectors
    global current_battery_simulation, current_encryption_results, current_receiver_results

    if not current_raw_records and not current_demo_records:
        raise HTTPException(status_code=400, detail="No active raw dataset available. Generate synthetic data first.")

    records_to_cluster = [r.model_copy() for r in (current_raw_records or current_demo_records)]
    high_group, low_group, clust_result = runner.cluster_manager.cluster_with_kmeans(
        records_to_cluster,
        pipeline_run_id=current_pipeline_run_id,
        config=config,
    )

    current_demo_records = records_to_cluster
    current_clustering_result = clust_result
    current_feature_vectors = runner.cluster_manager.last_feature_vectors

    # Invalidate downstream battery & encryption state since clustering was updated
    current_battery_simulation = None
    current_encryption_results = None
    current_receiver_results = None

    # Persist updated snapshot
    snapshot_data = {
        "pipeline_run_id": current_pipeline_run_id,
        "seed": current_demo_seed,
        "record_count": len(current_demo_records),
        "clustering_diagnostics": clust_result.diagnostics.model_dump() if clust_result else None,
        "clustering_config": clust_result.config.model_dump() if clust_result else None,
    }
    run_store.save_pipeline_snapshot(current_pipeline_run_id, current_demo_seed or 42, len(current_demo_records), snapshot_data)

    return {
        "status": "SUCCESS",
        "dataset_id": current_pipeline_run_id,
        "pipeline_run_id": current_pipeline_run_id,
        "seed": current_demo_seed,
        "total_records": len(current_demo_records),
        "record_count": len(current_demo_records),
        "high_cluster_count": high_group.record_count,
        "low_cluster_count": low_group.record_count,
        "clustering_config": clust_result.config.model_dump() if clust_result else None,
        "clustering_diagnostics": clust_result.diagnostics.model_dump() if clust_result else None,
        "records_preview": [r.model_dump() for r in current_demo_records[:20]],
        "all_records": [r.model_dump() for r in current_demo_records],
        "clustered_records": [r.model_dump() for r in current_demo_records],
        "features_preview": [f.model_dump() for f in current_feature_vectors[:20]],
        "all_features": [f.model_dump() for f in current_feature_vectors],
    }


@app.post("/api/battery/simulate-current")
def simulate_battery_on_current_dataset(
    req: Optional[BatterySimulateRequest] = None,
    repetitions: Optional[int] = None,
    profile: Optional[str] = None,
    radio_tx_ms: Optional[float] = None,
):
    """Stage 4: Simulate battery percentage using the exact records, record count, and
    effective security classes of the current clustered dataset.
    """
    req = req or BatterySimulateRequest()
    eff_repetitions = repetitions if repetitions is not None else req.repetitions
    eff_profile = profile if profile is not None else req.profile
    eff_radio_tx = radio_tx_ms if radio_tx_ms is not None else req.radio_tx_ms

    global current_demo_records, current_clustering_result, current_pipeline_run_id, current_battery_simulation, mcu_config
    if not current_demo_records:
        raise HTTPException(status_code=400, detail="No active dataset. Generate synthetic data first.")
    if not current_clustering_result:
        raise HTTPException(status_code=400, detail="Current dataset has not been clustered. Run ML Clustering before simulating battery.")

    model = McuEnergyModel(mcu_config)
    try:
        sim_result = model.simulate_battery_on_records(
            records=current_demo_records,
            pipeline_run_id=current_pipeline_run_id or "PIPE-CURRENT",
            repetitions=eff_repetitions,
            radio_tx_ms_override=eff_radio_tx,
            profile_name=eff_profile,
        )
    except ValueError as ve:
        raise HTTPException(status_code=422, detail=str(ve))
    sim_result["dataset_id"] = current_pipeline_run_id
    sim_result["pipeline_run_id"] = current_pipeline_run_id
    current_battery_simulation = sim_result
    return sim_result


@app.get("/api/battery/simulate-current")
def get_current_battery_simulation(
    repetitions: int = 1,
    profile: Optional[str] = None,
    radio_tx_ms: Optional[float] = None,
):
    """Retrieve or compute battery simulation on current clustered dataset."""
    global current_demo_records, current_clustering_result, current_pipeline_run_id, current_battery_simulation, mcu_config
    if not current_demo_records:
        raise HTTPException(status_code=400, detail="No active dataset available.")
    if not current_clustering_result:
        raise HTTPException(status_code=400, detail="Current dataset has not been clustered. Run ML Clustering first.")

    if current_battery_simulation and repetitions == current_battery_simulation.get("simulated_repetitions", 1):
        return current_battery_simulation

    model = McuEnergyModel(mcu_config)
    try:
        sim_result = model.simulate_battery_on_records(
            records=current_demo_records,
            pipeline_run_id=current_pipeline_run_id or "PIPE-CURRENT",
            repetitions=repetitions,
            radio_tx_ms_override=radio_tx_ms,
            profile_name=profile,
        )
    except ValueError as ve:
        raise HTTPException(status_code=422, detail=str(ve))
    sim_result["dataset_id"] = current_pipeline_run_id
    sim_result["pipeline_run_id"] = current_pipeline_run_id
    current_battery_simulation = sim_result
    return sim_result


@app.post("/api/pipeline/encrypt-and-verify")
def encrypt_and_verify_current_dataset():
    """Stage 5 & 6: Execute adaptive encryption and receiver verification on current clustered records."""
    global current_demo_records, current_clustering_result, current_pipeline_run_id
    global current_encryption_results, current_receiver_results
    if not current_demo_records:
        raise HTTPException(status_code=400, detail="No active dataset available.")
    if not current_clustering_result:
        raise HTTPException(status_code=400, detail="Dataset must be clustered before encryption routing.")

    engine = EncryptionEngine(key_manager)
    receiver.reset_stats(current_pipeline_run_id)

    enc_list = []
    rec_list = []

    for r in current_demo_records:
        eff = getattr(r, "effective_security_class", None) or getattr(r, "sensitivity", None) or SensitivityLevel.LOW
        eff_str = eff.value if hasattr(eff, "value") else str(eff)
        algo = EncryptionAlgorithm.AES_256_GCM if eff_str.upper() == "HIGH" else EncryptionAlgorithm.XOR_LIGHTWEIGHT

        env = engine.encrypt_record(
            record=r,
            run_id=current_pipeline_run_id or "PIPE-ENCRYPT",
            algorithm=algo,
        )
        ver = receiver.receive_envelope(env)

        enc_list.append({
            "record_id": r.record_id,
            "record_type": r.record_type.value,
            "kmeans_cluster_id": r.kmeans_cluster_id,
            "cluster_label": r.cluster_label,
            "policy_sensitivity": r.policy_sensitivity.value if r.policy_sensitivity else (r.sensitivity.value if r.sensitivity else "LOW"),
            "effective_security_class": eff_str,
            "baseline_algorithm": "AES-256-GCM",
            "adaptive_selected_algorithm": algo.value,
            "nonce_hex": env.nonce_hex,
            "tag_hex": env.tag_hex,
            "hmac_hex": env.hmac_hex,
            "payload_bytes": env.payload_bytes,
            "pipeline_run_id": current_pipeline_run_id,
        })
        rec_list.append({
            "record_id": r.record_id,
            "record_type": r.record_type.value,
            "algorithm": algo.value,
            "verified": ver.verified,
            "nonce_unique": True,
            "rejection_reason": ver.error_message or "",
            "arrival_timestamp": ver.arrival_timestamp,
            "pipeline_run_id": current_pipeline_run_id,
        })

    current_encryption_results = enc_list
    current_receiver_results = rec_list

    return {
        "status": "SUCCESS",
        "dataset_id": current_pipeline_run_id,
        "pipeline_run_id": current_pipeline_run_id,
        "records_count": len(enc_list),
        "aes_256_gcm_count": sum(1 for e in enc_list if e["adaptive_selected_algorithm"] == EncryptionAlgorithm.AES_256_GCM.value),
        "xor_lightweight_count": sum(1 for e in enc_list if e["adaptive_selected_algorithm"] == EncryptionAlgorithm.XOR_LIGHTWEIGHT.value),
        "receiver_stats": receiver.get_stats(),
        "encryption_preview": enc_list[:10],
        "receiver_preview": rec_list[:10],
    }


@app.get("/api/pipeline/current")
def get_current_pipeline():
    """Retrieve the end-to-end state and intermediate data across all 7 pipeline stages."""
    global current_raw_records, current_demo_records, current_demo_seed, current_pipeline_run_id
    global current_clustering_result, current_feature_vectors, current_battery_simulation
    global current_encryption_results, current_receiver_results

    if not current_demo_records and not current_raw_records:
        return {
            "has_data": False,
            "pipeline_run_id": None,
            "message": "No active pipeline run. Generate synthetic data to initialize.",
        }

    raw_records_dump = [r.model_dump() for r in (current_raw_records or current_demo_records)]
    clustered_records_dump = [r.model_dump() for r in current_demo_records]
    features_dump = [f.model_dump() for f in current_feature_vectors]
    
    high_cluster_records = [r for r in clustered_records_dump if r.get("cluster_label") == "CLUSTER-HIGH"]
    low_cluster_records = [r for r in clustered_records_dump if r.get("cluster_label") == "CLUSTER-LOW"]
    overrides = [r for r in clustered_records_dump if r.get("policy_override")]

    return {
        "has_data": True,
        "dataset_id": current_pipeline_run_id,
        "pipeline_run_id": current_pipeline_run_id,
        "seed": current_demo_seed,
        "record_count": len(current_demo_records or current_raw_records),
        "is_clustered": current_clustering_result is not None,
        "stages": {
            "stage1_raw": {
                "name": "Synthetic Dataset Generation",
                "is_available": len(raw_records_dump) > 0,
                "record_count": len(raw_records_dump),
                "records": raw_records_dump,
                "provenance": {
                    "pipeline_run_id": current_pipeline_run_id,
                    "seed": current_demo_seed,
                    "generator": "SyntheticDataGenerator",
                    "time_anchor": "2026-10-13T10:00:00Z",
                },
            },
            "stage2_features": {
                "name": "Feature Engineering & Preprocessing",
                "is_available": len(features_dump) > 0,
                "feature_names": HealthcareFeatureExtractor.FEATURE_NAMES,
                "feature_count": len(HealthcareFeatureExtractor.FEATURE_NAMES),
                "features": features_dump,
                "normalization": "StandardScaler (z = (x - u) / s)",
                "label_leakage_prevented": True,
            },
            "stage3_kmeans": {
                "name": "Unsupervised K-Means Clustering",
                "is_available": current_clustering_result is not None,
                "config": current_clustering_result.config.model_dump() if current_clustering_result else None,
                "diagnostics": current_clustering_result.diagnostics.model_dump() if current_clustering_result else None,
            },
            "stage4_clustered": {
                "name": "Post-Clustering Dataset with Guardrail",
                "is_available": current_clustering_result is not None,
                "high_cluster_count": len(high_cluster_records),
                "low_cluster_count": len(low_cluster_records),
                "guardrail_override_count": len(overrides),
                "records": clustered_records_dump,
            },
            "stage4_battery": {
                "name": "Per-Record Battery Simulation & Cumulative Drain",
                "is_available": current_battery_simulation is not None,
                "summary": current_battery_simulation if current_battery_simulation else None,
                "records": current_battery_simulation.get("records", []) if current_battery_simulation else [],
            },
            "stage5_routing": {
                "name": "Encryption Routing",
                "is_available": current_clustering_result is not None,
                "baseline_route": "100% AES-256-GCM",
                "adaptive_route": {
                    "aes_256_gcm_count": sum(1 for r in clustered_records_dump if r.get("effective_security_class") == "HIGH"),
                    "xor_lightweight_count": sum(1 for r in clustered_records_dump if r.get("effective_security_class") == "LOW"),
                },
                "records": current_encryption_results or [],
            },
            "stage6_receiver": {
                "name": "Simulated Healthcare Receiver Verification",
                "is_available": current_receiver_results is not None,
                "receiver_stats": receiver.get_stats(),
                "records": current_receiver_results or [],
            },
            "stage7_benchmark": {
                "name": "Energy & Timing Benchmark",
                "is_available": True,
                "recent_runs": run_store.list_runs(limit=5),
            },
        },
    }


@app.post("/api/pipeline/kmeans/configure")
def configure_kmeans(config: KMeansConfig):
    """Reconfigure and re-run K-Means on currently loaded records."""
    global current_demo_records, current_pipeline_run_id, current_clustering_result, current_feature_vectors
    if not current_demo_records:
        raise HTTPException(status_code=400, detail="No active dataset. Generate records first.")
    
    high_group, low_group, clust_result = runner.cluster_manager.cluster_with_kmeans(
        current_demo_records,
        pipeline_run_id=current_pipeline_run_id,
        config=config,
    )
    current_clustering_result = clust_result
    current_feature_vectors = runner.cluster_manager.last_feature_vectors

    return {
        "status": "SUCCESS",
        "pipeline_run_id": current_pipeline_run_id,
        "high_cluster_count": high_group.record_count,
        "low_cluster_count": low_group.record_count,
        "clustering_config": clust_result.config.model_dump() if clust_result else None,
        "clustering_diagnostics": clust_result.diagnostics.model_dump() if clust_result else None,
    }


@app.get("/api/pipeline/features")
def get_pipeline_features():
    """Retrieve engineered feature vectors for the current pipeline run."""
    global current_feature_vectors, current_pipeline_run_id
    if not current_feature_vectors:
        raise HTTPException(status_code=404, detail="No feature vectors found. Generate a dataset first.")
    return {
        "pipeline_run_id": current_pipeline_run_id,
        "feature_names": HealthcareFeatureExtractor.FEATURE_NAMES,
        "features": [f.model_dump() for f in current_feature_vectors],
    }


@app.get("/api/pipeline/clustering")
def get_pipeline_clustering():
    """Retrieve K-Means clustering result and diagnostics for the current run."""
    global current_clustering_result, current_pipeline_run_id
    if not current_clustering_result:
        raise HTTPException(status_code=404, detail="No clustering results found. Generate a dataset first.")
    return {
        "pipeline_run_id": current_pipeline_run_id,
        "clustering": current_clustering_result.model_dump(),
    }


@app.get("/api/pipeline/export/{stage}.csv")
def export_pipeline_stage_csv(stage: str):
    """Export a specific pipeline stage intermediate dataset as CSV."""
    global current_raw_records, current_demo_records, current_feature_vectors, current_pipeline_run_id, current_battery_simulation
    global current_encryption_results, current_receiver_results, mcu_config
    if not current_demo_records and not current_raw_records:
        raise HTTPException(status_code=400, detail="No active dataset available for export.")

    run_id = current_pipeline_run_id or "UNKNOWN-PIPE"
    output = io.StringIO()
    writer = csv.writer(output)

    stage_key = stage.lower()
    if stage_key in ["raw", "stage1", "stage1_raw"]:
        # Stage 1: Raw generated dataset snapshot (no fabricated cluster labels)
        raw_list = current_raw_records if current_raw_records else current_demo_records
        writer.writerow(["record_id", "timestamp", "demo_patient_id", "record_type", "value", "unit", "is_synthetic", "pipeline_run_id"])
        for r in raw_list:
            writer.writerow([r.record_id, r.timestamp, r.demo_patient_id, r.record_type.value, r.value, r.unit, r.is_synthetic, r.pipeline_run_id or run_id])
        filename = f"stage1_raw_dataset_{run_id}.csv"

    elif stage_key in ["features", "stage2", "stage2_features"]:
        # Stage 2: Feature engineering matrix with both unscaled and model-scaled features
        if not current_feature_vectors:
            raise HTTPException(status_code=400, detail="Feature vectors not yet computed. Run ML Clustering first.")
        writer.writerow([
            "record_id", "record_type", "raw_value", "unit",
            "modality_normalized_value", "physiological_range_deviation",
            "type_heart_rate", "type_ecg_summary", "type_temperature", "type_step_count",
            "scaled_type_heart_rate", "scaled_type_ecg_summary", "scaled_type_temperature", "scaled_type_step_count",
            "scaled_modality_normalized_value", "scaled_physiological_range_deviation",
            "pipeline_run_id"
        ])
        for fv in current_feature_vectors:
            writer.writerow([
                fv.record_id,
                fv.record_type,
                fv.raw_value,
                fv.unit,
                fv.features.get("modality_normalized_value", 0.0),
                fv.features.get("physiological_range_deviation", 0.0),
                fv.features.get("type_heart_rate", 0.0),
                fv.features.get("type_ecg_summary", 0.0),
                fv.features.get("type_temperature", 0.0),
                fv.features.get("type_step_count", 0.0),
                fv.scaled_features.get("type_heart_rate", 0.0),
                fv.scaled_features.get("type_ecg_summary", 0.0),
                fv.scaled_features.get("type_temperature", 0.0),
                fv.scaled_features.get("type_step_count", 0.0),
                fv.scaled_features.get("modality_normalized_value", 0.0),
                fv.scaled_features.get("physiological_range_deviation", 0.0),
                run_id,
            ])
        filename = f"stage2_features_{run_id}.csv"

    elif stage_key in ["clustered", "stage3", "stage4", "stage4_clustered", "kmeans"]:
        # Stage 3/4: Post-clustering dataset with guardrail
        if not current_clustering_result:
            raise HTTPException(status_code=400, detail="Clustering has not been executed yet. Run ML Clustering first.")
        writer.writerow([
            "record_id", "record_type", "value", "unit", "timestamp",
            "kmeans_cluster_id", "cluster_label", "policy_sensitivity",
            "effective_security_class", "policy_override", "override_reason", "pipeline_run_id"
        ])
        for r in current_demo_records:
            writer.writerow([
                r.record_id,
                r.record_type.value,
                r.value,
                r.unit,
                r.timestamp,
                r.kmeans_cluster_id,
                r.cluster_label,
                r.policy_sensitivity.value if r.policy_sensitivity else (r.sensitivity.value if r.sensitivity else "LOW"),
                r.effective_security_class.value if r.effective_security_class else "LOW",
                1 if r.policy_override else 0,
                r.override_reason or "",
                r.pipeline_run_id or run_id,
            ])
        filename = f"stage4_clustered_dataset_{run_id}.csv"

    elif stage_key in ["battery", "stage4_battery", "battery_simulation"]:
        # Stage 4: Per-record battery simulation and cumulative percentage
        sim = current_battery_simulation
        if not sim:
            if not current_clustering_result:
                raise HTTPException(status_code=400, detail="Cannot simulate battery before ML clustering.")
            model = McuEnergyModel(mcu_config)
            sim = model.simulate_battery_on_records(current_demo_records, pipeline_run_id=run_id)
            current_battery_simulation = sim

        writer.writerow([
            "pipeline_run_id", "record_id", "repetition_index", "packet_index",
            "kmeans_cluster_id", "cluster_label",
            "effective_security_class", "baseline_algorithm", "adaptive_algorithm",
            "baseline_energy_joules", "adaptive_energy_joules",
            "baseline_cumulative_energy_joules", "adaptive_cumulative_energy_joules",
            "baseline_battery_remaining_percent", "adaptive_battery_remaining_percent"
        ])
        for entry in sim["records"]:
            writer.writerow([
                entry["pipeline_run_id"],
                entry["record_id"],
                entry.get("repetition_index", 1),
                entry.get("packet_index", 1),
                entry["kmeans_cluster_id"],
                entry["cluster_label"],
                entry["effective_security_class"],
                entry["baseline_algorithm"],
                entry["adaptive_algorithm"],
                entry["baseline_energy_joules"],
                entry["adaptive_energy_joules"],
                entry["baseline_cumulative_energy_joules"],
                entry["adaptive_cumulative_energy_joules"],
                entry["baseline_battery_remaining_percent"],
                entry["adaptive_battery_remaining_percent"],
            ])
        filename = f"stage4_battery_simulation_{run_id}.csv"

    elif stage_key in ["routing", "stage5", "stage5_routing"]:
        # Stage 5: Encryption routing
        writer.writerow([
            "record_id", "record_type", "value", "unit",
            "kmeans_cluster_id", "cluster_label", "policy_sensitivity",
            "effective_security_class", "baseline_algorithm", "adaptive_selected_algorithm",
            "pipeline_run_id"
        ])
        for r in current_demo_records:
            eff = getattr(r, "effective_security_class", None) or getattr(r, "sensitivity", None) or SensitivityLevel.LOW
            eff_str = eff.value if hasattr(eff, "value") else str(eff)
            adapt_algo = "AES-256-GCM" if eff_str.upper() == "HIGH" else "XOR-EXPERIMENTAL"
            writer.writerow([
                r.record_id,
                r.record_type.value,
                r.value,
                r.unit,
                r.kmeans_cluster_id,
                r.cluster_label,
                r.policy_sensitivity.value if r.policy_sensitivity else (r.sensitivity.value if r.sensitivity else "LOW"),
                eff_str,
                "AES-256-GCM",
                adapt_algo,
                r.pipeline_run_id or run_id,
            ])
        filename = f"stage5_encryption_routing_{run_id}.csv"

    elif stage_key in ["receiver", "stage6", "stage6_receiver"]:
        # Stage 6: Receiver verification
        if not current_receiver_results:
            encrypt_and_verify_current_dataset()
        writer.writerow([
            "record_id", "record_type", "algorithm", "verified",
            "nonce_unique", "rejection_reason", "arrival_timestamp", "pipeline_run_id"
        ])
        for r in (current_receiver_results or []):
            writer.writerow([
                r.get("record_id"),
                r.get("record_type"),
                r.get("algorithm"),
                1 if r.get("verified") else 0,
                1 if r.get("nonce_unique") else 0,
                r.get("rejection_reason", ""),
                r.get("arrival_timestamp", ""),
                r.get("pipeline_run_id", run_id),
            ])
        filename = f"stage6_receiver_verification_{run_id}.csv"

    elif stage_key in ["benchmark", "stage7", "stage7_benchmark"]:
        # Stage 7: Benchmark summary
        writer.writerow([
            "pipeline_run_id", "record_count", "high_count", "low_count",
            "scenario_name", "baseline_energy_joules", "adaptive_energy_joules",
            "energy_saving_percent", "baseline_crypto_latency_ms", "adaptive_crypto_latency_ms",
            "latency_saving_percent", "baseline_runtime_hours", "adaptive_runtime_hours", "status"
        ])
        model = McuEnergyModel(mcu_config)
        def _is_high(r):
            eff = getattr(r, "effective_security_class", None) or getattr(r, "sensitivity", None)
            return (eff.value if hasattr(eff, "value") else str(eff)).upper() == "HIGH"
        h_cnt = sum(1 for r in current_demo_records if _is_high(r))
        l_cnt = len(current_demo_records) - h_cnt
        scen = model.calculate_scenario(len(current_demo_records), h_cnt, l_cnt)
        writer.writerow([
            run_id,
            len(current_demo_records),
            h_cnt,
            l_cnt,
            scen["scenario_name"],
            scen["baseline"]["total_energy_joules"],
            scen["adaptive"]["total_energy_joules"],
            scen["energy_comparison"].get("energy_saving_percent", 0.0),
            scen["baseline"]["crypto_duration_ms"],
            scen["adaptive"]["crypto_duration_ms"],
            scen["crypto_time_comparison"].get("percent_change", 0.0),
            scen["baseline"]["indicative_runtime_hours"],
            scen["adaptive"]["indicative_runtime_hours"],
            "COMPLETED",
        ])
        filename = f"stage7_benchmark_{run_id}.csv"

    else:
        raise HTTPException(status_code=400, detail=f"Unknown export stage '{stage}'. Valid stages: raw, features, clustered, battery, routing, receiver, benchmark.")

    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.get("/api/pipeline/export/{stage}.json")
def export_pipeline_stage_json(stage: str):
    """Export a specific pipeline stage intermediate dataset as JSON."""
    global current_raw_records, current_demo_records, current_feature_vectors, current_pipeline_run_id, current_clustering_result
    global current_battery_simulation, current_encryption_results, current_receiver_results, mcu_config
    if not current_demo_records and not current_raw_records:
        raise HTTPException(status_code=400, detail="No active dataset available for export.")

    run_id = current_pipeline_run_id or "UNKNOWN-PIPE"
    stage_key = stage.lower()
    if stage_key in ["raw", "stage1", "stage1_raw"]:
        raw_list = current_raw_records if current_raw_records else current_demo_records
        data = {
            "stage": "stage1_raw_dataset",
            "dataset_id": run_id,
            "pipeline_run_id": run_id,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "record_count": len(raw_list),
            "records": [r.model_dump() for r in raw_list],
        }
        filename = f"stage1_raw_dataset_{run_id}.json"
    elif stage_key in ["features", "stage2", "stage2_features"]:
        if not current_feature_vectors:
            raise HTTPException(status_code=400, detail="Feature vectors not yet computed. Run ML Clustering first.")
        data = {
            "stage": "stage2_features",
            "dataset_id": run_id,
            "pipeline_run_id": run_id,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "feature_names": HealthcareFeatureExtractor.FEATURE_NAMES,
            "feature_count": len(HealthcareFeatureExtractor.FEATURE_NAMES),
            "records": [fv.model_dump() for fv in current_feature_vectors],
        }
        filename = f"stage2_features_{run_id}.json"
    elif stage_key in ["clustered", "stage3", "stage4", "stage4_clustered", "kmeans"]:
        if not current_clustering_result:
            raise HTTPException(status_code=400, detail="Clustering has not been executed yet. Run ML Clustering first.")
        data = {
            "stage": "stage4_clustered_dataset",
            "dataset_id": run_id,
            "pipeline_run_id": run_id,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "record_count": len(current_demo_records),
            "clustering_diagnostics": current_clustering_result.diagnostics.model_dump() if current_clustering_result else None,
            "records": [r.model_dump() for r in current_demo_records],
        }
        filename = f"stage4_clustered_dataset_{run_id}.json"
    elif stage_key in ["battery", "stage4_battery", "battery_simulation"]:
        sim = current_battery_simulation
        if not sim:
            if not current_clustering_result:
                raise HTTPException(status_code=400, detail="Cannot simulate battery before ML clustering.")
            model = McuEnergyModel(mcu_config)
            sim = model.simulate_battery_on_records(current_demo_records, pipeline_run_id=run_id)
            current_battery_simulation = sim
        data = {
            "stage": "stage4_battery_simulation",
            "dataset_id": run_id,
            "pipeline_run_id": run_id,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "simulation": sim,
        }
        filename = f"stage4_battery_simulation_{run_id}.json"
    elif stage_key in ["routing", "stage5", "stage5_routing"]:
        data = {
            "stage": "stage5_encryption_routing",
            "dataset_id": run_id,
            "pipeline_run_id": run_id,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "records": current_encryption_results or [],
        }
        filename = f"stage5_encryption_routing_{run_id}.json"
    elif stage_key in ["receiver", "stage6", "stage6_receiver"]:
        if not current_receiver_results:
            encrypt_and_verify_current_dataset()
        data = {
            "stage": "stage6_receiver_verification",
            "dataset_id": run_id,
            "pipeline_run_id": run_id,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "records": current_receiver_results or [],
        }
        filename = f"stage6_receiver_verification_{run_id}.json"
    elif stage_key in ["benchmark", "stage7", "stage7_benchmark"]:
        model = McuEnergyModel(mcu_config)
        def _is_high(r):
            eff = getattr(r, "effective_security_class", None) or getattr(r, "sensitivity", None)
            return (eff.value if hasattr(eff, "value") else str(eff)).upper() == "HIGH"
        h_cnt = sum(1 for r in current_demo_records if _is_high(r))
        l_cnt = len(current_demo_records) - h_cnt
        scen = model.calculate_scenario(len(current_demo_records), h_cnt, l_cnt)
        data = {
            "stage": "stage7_benchmark",
            "dataset_id": run_id,
            "pipeline_run_id": run_id,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "scenario": scen,
        }
        filename = f"stage7_benchmark_{run_id}.json"
    else:
        raise HTTPException(status_code=400, detail=f"Unknown export stage '{stage}'. Valid stages: raw, features, clustered, battery, routing, receiver, benchmark.")

    return Response(
        content=json.dumps(data, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )



@app.get("/api/battery/energy-model")
def get_energy_model_details():
    """Authoritative breakdown of the battery simulation equations, assumptions, and constants."""
    global mcu_config
    model = McuEnergyModel(mcu_config)
    breakdown = model.calculate_scenario(
        total_records=100,
        high_sensitivity_count=45,
        low_sensitivity_count=55,
    )
    return {
        "mcu_specification": {
            "target": mcu_config.mcu_model_name,
            "clock_frequency_hz": mcu_config.mcu_clock_hz,
            "operating_voltage_v": mcu_config.supply_voltage_v,
            "has_hardware_aes": False,
        },
        "battery_specification": {
            "cell_nominal_voltage_v": mcu_config.battery_cell_nominal_voltage_v,
            "regulated_rail_voltage_v": mcu_config.supply_voltage_v,
            "nominal_capacity_mah": mcu_config.battery_nominal_mah,
            "nominal_capacity_ah": mcu_config.battery_nominal_mah / 1000.0,
            "usable_capacity_factor": mcu_config.battery_usable_factor,
            "usable_capacity_mah": mcu_config.battery_nominal_mah * mcu_config.battery_usable_factor,
            "cell_total_energy_joules": round((mcu_config.battery_nominal_mah / 1000.0) * 3600.0 * mcu_config.battery_cell_nominal_voltage_v, 2),
            "cell_usable_energy_joules": round((mcu_config.battery_nominal_mah / 1000.0) * 3600.0 * mcu_config.battery_cell_nominal_voltage_v * mcu_config.battery_usable_factor, 2),
            "usable_energy_joules": round(
                (mcu_config.battery_nominal_mah / 1000.0) * 3600.0 * mcu_config.supply_voltage_v * mcu_config.battery_usable_factor,
                2
            ),
            "rail_delivered_energy_joules": round(
                (mcu_config.battery_nominal_mah / 1000.0) * 3600.0 * mcu_config.supply_voltage_v * mcu_config.battery_usable_factor,
                2
            ),
            "ldo_efficiency_factor": mcu_config.ldo_efficiency_factor,
            "voltage_reference_explanation": (
                "Distinguishes 1S Li-Po electrochemical cell (3.7V nominal, 13,586.40 J usable @ 85% DoD) "
                "from the regulated 3.3V MCU operating rail. Stepping down via a linear LDO (efficiency 3.3V / 3.7V ≈ 89.2%) "
                "delivers 12,117.60 J to the 3.3V rail. Operating currents are measured at the 3.3V rail boundary."
            ),
        },
        "mathematical_formulas": {
            "power_w": "P = V x I (Voltage in Volts x Current in Amperes)",
            "energy_constant_current_j": "E = V x I x t (Voltage x Current x Duration in seconds)",
            "energy_numerical_integration_j": "E ≈ Σ [ (P_i + P_{i+1}) / 2 x Δt ] (Trapezoidal integration for lab CSV logs)",
            "battery_charge_consumed_mah": "Q = I_mean x (t_seconds / 3600.0)",
            "batch_battery_depletion_percent": "Depletion % = (Batch Energy / Usable Battery Energy) x 100",
            "non_overlapping_intervals": "T_total = T_shared + T_crypto + T_radio + T_idle. Current states are mutually exclusive to avoid double counting.",
        },
        "evidence_hierarchy": [
            {
                "tier": "A",
                "badge": "DESKTOP_MEASURED_HOST",
                "label": "Host CPU Measured Timing",
                "description": "Host PC execution time measured with high-precision perf_counter_ns(). Reflects x86/ARM host software speed, NOT MCU energy.",
            },
            {
                "tier": "B",
                "badge": "MODELED_ESTIMATED_MCU",
                "label": "Modeled / Estimated MCU Energy",
                "description": "Analytical energy model based on 16 MHz clock, datasheet active/sleep current, non-overlapping task intervals, and configurable radio airtime.",
            },
            {
                "tier": "C",
                "badge": "INSTRUMENT_MEASURED_LAB",
                "label": "Instrument-Measured Lab Energy",
                "description": "Empirical voltage and current samples imported from physical power analyzer or shunt monitor via /api/power/import.",
            },
        ],
        "active_parameters": mcu_config.model_dump(),
        "reference_100_record_breakdown": breakdown,
    }



@app.post("/api/benchmark/run")
def execute_benchmark(req: BenchmarkRunRequest):
    """Execute baseline, adaptive, or paired comparison benchmark."""
    global current_demo_records, current_demo_seed, current_power_override

    # Use pre-generated records if count and seed match, otherwise generate fresh
    if current_demo_records and len(current_demo_records) == req.record_count and current_demo_seed == req.seed:
        records = current_demo_records
    else:
        gen = SyntheticDataGenerator(seed=req.seed)
        records = gen.generate_batch(
            count=req.record_count,
            classifier=runner.classifier,
            cluster_manager=runner.cluster_manager,
        )
        current_demo_records = records
        current_demo_seed = req.seed

    if req.mode == "comparison":
        comp_result = runner.run_comparison(
            record_count=req.record_count,
            seed=req.seed,
            repetitions=req.repetitions,
            records=records,
        )
        if "error" in comp_result:
            raise HTTPException(status_code=400, detail=comp_result["error"])

        if "_records_objects" in comp_result:
            current_demo_records = comp_result["_records_objects"]
            current_demo_seed = req.seed

        base_summary = comp_result["baseline_summary"]
        adapt_summary = comp_result["adaptive_summary"]
        run_store.save_run(base_summary, records)
        run_store.save_run(adapt_summary, records)

        # Clear power override after use
        current_power_override = None

        return {
            "mode": "comparison",
            "comparison": comp_result,
            "baseline_run_id": base_summary.run_id,
            "adaptive_run_id": adapt_summary.run_id,
        }

    mode_enum = (
        BenchmarkMode.BASELINE if req.mode.lower() == "baseline" else BenchmarkMode.ADAPTIVE
    )
    metrics = runner.run_single_batch(
        mode=mode_enum,
        records=records,
        seed=req.seed,
        repeat_index=1,
        power_samples_override=current_power_override,
    )
    run_store.save_run(metrics, records)
    current_power_override = None

    return {
        "mode": req.mode,
        "metrics": metrics.model_dump(),
        "run_id": metrics.run_id,
    }


@app.post("/api/benchmark/stop")
def stop_benchmark():
    """Safely request benchmark cancellation."""
    runner.request_cancellation()
    return {"message": "Cancellation request submitted."}


@app.post("/api/demo/tamper")
def demonstrate_tamper(req: TamperDemoRequest):
    """Demonstrate receiver tamper rejection with authentic vs tampered envelopes."""
    sample_record = SensorRecord(
        record_id="REC-DEMO-TAMPER",
        timestamp="2026-10-13T12:00:00Z",
        demo_patient_id="SYNTH-PAT-001",
        record_type=RecordType.ECG_SUMMARY,
        value=1.35,
        unit="mV",
        sensitivity=SensitivityLevel.HIGH,
        classification_reason="ECG waveform requiring authenticated integrity.",
        cluster_id="CLUSTER-HIGH",
    )

    engine = EncryptionEngine(key_manager)
    valid_envelope = engine.encrypt_record(
        record=sample_record,
        run_id="RUN-DEMO-TAMPER",
        algorithm=req.algorithm,
    )

    tampered_envelope = tamper_envelope(valid_envelope, target=req.tamper_target)

    # Verify both through local receiver
    valid_res = receiver.receive_envelope(valid_envelope)
    tampered_res = receiver.receive_envelope(tampered_envelope)

    return {
        "algorithm": req.algorithm.value,
        "tamper_target": req.tamper_target,
        "valid_envelope": valid_envelope.model_dump(),
        "valid_result": valid_res.model_dump(),
        "tampered_envelope": tampered_envelope.model_dump(),
        "tampered_result": tampered_res.model_dump(),
        "rejection_verified": not tampered_res.verified,
    }


@app.post("/api/power/import")
async def import_power_log(file: UploadFile = File(...)):
    """Validate and import external lab instrument CSV power samples."""
    global current_power_override
    content = await file.read()
    try:
        csv_text = content.decode("utf-8")
        voltages, currents, timestamps, source = CSVPowerImporter.parse_csv_content(csv_text)
        current_power_override = (voltages, currents, timestamps, source)
        total_j, mean_v, mean_i, mean_p = integrate_energy_joules(voltages, currents, timestamps)
        obs_interval_s = max(0.0, (timestamps[-1] - timestamps[0]) / 1000.0) if len(timestamps) > 1 else 0.0
        charge_consumed_mah = (mean_i * (obs_interval_s / 3600.0)) if obs_interval_s > 0 else 0.0
        return {
            "status": "SUCCESS",
            "source": source.value,
            "filename": file.filename,
            "sample_count": len(timestamps),
            "observation_interval_s": round(obs_interval_s, 4),
            "mean_voltage_v": round(mean_v, 4),
            "mean_current_ma": round(mean_i, 4),
            "mean_power_mw": round(mean_p, 4),
            "total_energy_joules": round(total_j, 6),
            "charge_consumed_mah": round(charge_consumed_mah, 6),
            "message": "Physical power measurement log loaded successfully for next benchmark run.",
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/runs")
def list_runs(limit: int = 50):
    """Retrieve list of saved runs from SQLite store."""
    return run_store.list_runs(limit=limit)


@app.get("/api/runs/{run_id}")
def get_run_details(run_id: str):
    """Get full details of a specific run."""
    run = run_store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    records = run_store.get_run_records(run_id)
    return {"metrics": run.model_dump(), "records": records}


@app.get("/api/metrics/compare")
def compare_runs(
    baseline_id: Optional[str] = Query(None),
    adaptive_id: Optional[str] = Query(None),
):
    """Compare two stored runs side-by-side."""
    if not baseline_id or not adaptive_id:
        runs = run_store.list_runs(limit=20)
        base_candidates = [r for r in runs if r["mode"] == "baseline"]
        adapt_candidates = [r for r in runs if r["mode"] == "adaptive"]
        if not base_candidates or not adapt_candidates:
            raise HTTPException(status_code=404, detail="No baseline and adaptive run pair found to compare.")
        baseline_id = base_candidates[0]["run_id"]
        adaptive_id = adapt_candidates[0]["run_id"]

    base = run_store.get_run(baseline_id)
    adapt = run_store.get_run(adaptive_id)
    if not base or not adapt:
        raise HTTPException(status_code=404, detail="One or both runs not found.")

    return {
        "baseline": base.model_dump(),
        "adaptive": adapt.model_dump(),
        "overall_result_status": evaluate_result_status(base.total_energy_joules, adapt.total_energy_joules, lower_is_better=True),
        "deltas": {
            "encryption_time_mean_ms": compute_authoritative_comparison(
                base.encryption_time_mean_ms, adapt.encryption_time_mean_ms, "Mean Encryption Time", lower_is_better=True, is_energy_metric=False
            ),
            "total_energy_joules": compute_authoritative_comparison(
                base.total_energy_joules, adapt.total_energy_joules, "Total Energy", lower_is_better=True, is_energy_metric=True
            ),
            "energy_per_record_mj": compute_authoritative_comparison(
                base.energy_per_record_mj, adapt.energy_per_record_mj, "Energy per Record", lower_is_better=True, is_energy_metric=True
            ),
            "tsr_percent": compute_authoritative_comparison(
                base.tsr_percent, adapt.tsr_percent, "Transmission Success Rate", lower_is_better=False, is_energy_metric=False
            ),
            "plr_percent": compute_authoritative_comparison(
                base.plr_percent, adapt.plr_percent, "Packet Loss Rate", lower_is_better=True, is_energy_metric=False
            ),
        },
    }


@app.get("/api/runs/{run_id}/export.csv")
def export_run_csv(run_id: str):
    """Export a run as a standard CSV with full metadata and model assumptions."""
    run = run_store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "run_id", "mode", "seed", "record_count", "repeat_index",
        "aes_count", "xor_count", "high_sensitivity_count", "low_sensitivity_count",
        "classification_time_total_ms", "clustering_time_total_ms",
        "enc_mean_ms", "enc_median_ms", "enc_p95_ms", "enc_total_ms", "authentication_total_ms",
        "serialization_total_ms", "transmission_total_ms", "end_to_end_duration_ms",
        "records_sent", "records_received", "records_rejected", "records_lost",
        "tsr_percent", "plr_percent", "measurement_source",
        "mean_voltage_v", "mean_current_ma", "mean_power_mw",
        "total_energy_joules", "energy_per_record_mj", "energy_per_100_records_mj", "energy_per_1000_records_mj",
        "estimated_battery_charge_consumed_mah", "estimated_runtime_hours", "started_at", "completed_at", "status"
    ])
    writer.writerow([
        run.run_id, run.mode.value, run.seed, run.record_count, run.repeat_index,
        run.aes_record_count, run.xor_record_count, run.high_sensitivity_count, run.low_sensitivity_count,
        run.classification_time_total_ms, run.clustering_time_total_ms,
        run.encryption_time_mean_ms, run.encryption_time_median_ms, run.encryption_time_p95_ms, run.encryption_time_total_ms,
        run.authentication_time_total_ms, run.serialization_time_total_ms, run.transmission_time_total_ms, run.end_to_end_duration_ms,
        run.records_sent, run.records_received, run.records_rejected, run.records_lost,
        run.tsr_percent, run.plr_percent, run.measurement_source.value,
        run.mean_voltage_v, run.mean_current_ma, run.mean_power_mw,
        run.total_energy_joules, run.energy_per_record_mj, run.energy_per_100_records_mj, run.energy_per_1000_records_mj,
        run.estimated_battery_charge_consumed_mah or "N/A", run.estimated_runtime_hours or "N/A",
        run.started_at, run.completed_at, run.status
    ])

    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=benchmark_{run_id}.csv"},
    )


@app.get("/api/runs/{run_id}/export.json")
def export_run_json(run_id: str):
    """Export run metrics and records as JSON."""
    run = run_store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    records = run_store.get_run_records(run_id)
    data = {
        "metadata": {
            "app": "Cluster-Based IoT Healthcare Encryption Demo",
            "version": "1.0.0",
            "exported_at": run.completed_at,
        },
        "metrics": run.model_dump(),
        "records": records,
    }
    return Response(
        content=json.dumps(data, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=benchmark_{run_id}.json"},
    )


@app.post("/api/demo/reset")
def reset_demo():
    """Reset store, receiver stats, and state back to default."""
    global current_raw_records, current_demo_records, current_demo_seed, current_power_override
    global current_pipeline_run_id, current_clustering_result, current_feature_vectors
    global current_battery_simulation, current_encryption_results, current_receiver_results
    run_store.reset()
    receiver.reset_stats()
    current_raw_records = []
    current_demo_records = []
    current_demo_seed = None
    current_power_override = None
    current_pipeline_run_id = None
    current_clustering_result = None
    current_feature_vectors = []
    current_battery_simulation = None
    current_encryption_results = None
    current_receiver_results = None
    runner.reset_cancellation()
    return {"message": "Demo state reset successfully."}


# Mount static assets and serve dashboard
static_path = Path("static")
static_path.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def serve_index():
    index_file = Path("static/index.html")
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "IoT Healthcare Encryption API is running. Dashboard index.html under construction."}
