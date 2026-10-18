"""FastAPI backend application serving the IoT Healthcare Data Encryption API and Dashboard."""

import os
import io
import csv
import json
import time
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
current_demo_records: List[SensorRecord] = []
current_demo_seed: Optional[int] = None
current_power_override: Optional[Any] = None
current_pipeline_run_id: Optional[str] = None
current_clustering_result: Optional[ClusteringResult] = None
current_feature_vectors: List[FeatureVector] = []


class McuScenarioRequest(BaseModel):
    record_count: Optional[int] = Field(default=None, ge=1, le=1000)
    high_sensitivity_count: Optional[int] = Field(default=None, ge=0)
    low_sensitivity_count: Optional[int] = Field(default=None, ge=0)
    profile: Optional[str] = None
    radio_tx_ms: Optional[float] = None
    config: Optional[McuHardwareScenarioConfig] = None


class GenerateRequest(BaseModel):
    count: int = Field(default=50, ge=1, le=1000)
    seed: int = Field(default=42, ge=0)


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
        high_cnt = sum(1 for r in current_demo_records if r.sensitivity == SensitivityLevel.HIGH)
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
        high_cnt = sum(1 for r in current_demo_records if r.sensitivity == SensitivityLevel.HIGH)
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


@app.post("/api/demo/generate")
def generate_synthetic_data(req: GenerateRequest):
    """Generate a seeded batch of synthetic healthcare sensor records with ML K-Means clustering."""
    global current_demo_records, current_demo_seed, current_pipeline_run_id, current_clustering_result, current_feature_vectors
    pipeline_run_id = f"PIPE-S{req.seed}-{int(time.time())}"
    gen = SyntheticDataGenerator(seed=req.seed)
    records = gen.generate_batch(
        count=req.count,
        classifier=runner.classifier,
    )
    for r in records:
        r.pipeline_run_id = pipeline_run_id

    high_group, low_group, clust_result = runner.cluster_manager.cluster_with_kmeans(
        records, pipeline_run_id=pipeline_run_id
    )

    current_demo_records = records
    current_demo_seed = req.seed
    current_pipeline_run_id = pipeline_run_id
    current_clustering_result = clust_result
    current_feature_vectors = runner.cluster_manager.last_feature_vectors

    methodology = {
        "generator_type": "Deterministic pseudo-random generator with fixed seed control",
        "seed": req.seed,
        "sample_count": len(records),
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

    # Persist immutable snapshot of this pipeline run
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
        "pipeline_run_id": pipeline_run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seed": req.seed,
        "count": len(records),
        "high_cluster_count": high_group.record_count,
        "low_cluster_count": low_group.record_count,
        "records_preview": [r.model_dump() for r in records[:20]],
        "all_records": [r.model_dump() for r in records],
        "features_preview": [f.model_dump() for f in current_feature_vectors[:20]],
        "all_features": [f.model_dump() for f in current_feature_vectors],
        "clustering_diagnostics": clust_result.diagnostics.model_dump() if clust_result else None,
        "clustering_config": clust_result.config.model_dump() if clust_result else None,
        "generation_methodology": methodology,
    }


@app.get("/api/pipeline/current")
def get_current_pipeline():
    """Retrieve the end-to-end state and intermediate data across all 7 pipeline stages."""
    global current_demo_records, current_demo_seed, current_pipeline_run_id, current_clustering_result, current_feature_vectors
    if not current_demo_records:
        return {
            "has_data": False,
            "pipeline_run_id": None,
            "message": "No active pipeline run. Generate synthetic data or run a benchmark to initialize.",
        }

    records_dump = [r.model_dump() for r in current_demo_records]
    features_dump = [f.model_dump() for f in current_feature_vectors]
    
    high_cluster_records = [r for r in records_dump if r.get("cluster_label") == "CLUSTER-HIGH"]
    low_cluster_records = [r for r in records_dump if r.get("cluster_label") == "CLUSTER-LOW"]
    overrides = [r for r in records_dump if r.get("policy_override")]

    return {
        "has_data": True,
        "pipeline_run_id": current_pipeline_run_id,
        "seed": current_demo_seed,
        "record_count": len(current_demo_records),
        "stages": {
            "stage1_raw": {
                "name": "Synthetic Dataset Generation",
                "record_count": len(records_dump),
                "records": records_dump,
                "provenance": {
                    "pipeline_run_id": current_pipeline_run_id,
                    "seed": current_demo_seed,
                    "generator": "SyntheticDataGenerator",
                    "time_anchor": "2026-10-13T10:00:00Z",
                },
            },
            "stage2_features": {
                "name": "Feature Engineering & Preprocessing",
                "feature_names": HealthcareFeatureExtractor.FEATURE_NAMES,
                "feature_count": len(HealthcareFeatureExtractor.FEATURE_NAMES),
                "features": features_dump,
                "normalization": "StandardScaler (z = (x - u) / s)",
                "label_leakage_prevented": True,
            },
            "stage3_kmeans": {
                "name": "Unsupervised K-Means Clustering",
                "config": current_clustering_result.config.model_dump() if current_clustering_result else None,
                "diagnostics": current_clustering_result.diagnostics.model_dump() if current_clustering_result else None,
            },
            "stage4_clustered": {
                "name": "Post-Clustering Dataset with Guardrail",
                "high_cluster_count": len(high_cluster_records),
                "low_cluster_count": len(low_cluster_records),
                "guardrail_override_count": len(overrides),
                "records": records_dump,
            },
            "stage5_routing": {
                "name": "Encryption Routing",
                "baseline_route": "100% AES-256-GCM",
                "adaptive_route": {
                    "aes_256_gcm_count": sum(1 for r in records_dump if r.get("effective_security_class") == "HIGH"),
                    "xor_lightweight_count": sum(1 for r in records_dump if r.get("effective_security_class") == "LOW"),
                },
            },
            "stage6_receiver": {
                "name": "Simulated Healthcare Receiver Verification",
                "receiver_stats": receiver.get_stats(),
            },
            "stage7_benchmark": {
                "name": "Energy & Timing Benchmark",
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
    global current_demo_records, current_feature_vectors, current_pipeline_run_id
    if not current_demo_records:
        raise HTTPException(status_code=400, detail="No active dataset available for export.")

    run_id = current_pipeline_run_id or "UNKNOWN-PIPE"
    output = io.StringIO()
    writer = csv.writer(output)

    stage_key = stage.lower()
    if stage_key in ["raw", "stage1", "stage1_raw"]:
        writer.writerow(["record_id", "timestamp", "demo_patient_id", "record_type", "value", "unit", "is_synthetic", "pipeline_run_id"])
        for r in current_demo_records:
            writer.writerow([r.record_id, r.timestamp, r.demo_patient_id, r.record_type.value, r.value, r.unit, r.is_synthetic, r.pipeline_run_id or run_id])
        filename = f"stage1_raw_dataset_{run_id}.csv"
    elif stage_key in ["features", "stage2", "stage2_features"]:
        writer.writerow(["record_id", "type_heart_rate", "type_ecg_summary", "type_temperature", "type_step_count", "modality_normalized_value", "physiological_range_deviation", "raw_measurement", "pipeline_run_id"])
        for fv in current_feature_vectors:
            writer.writerow([
                fv.record_id,
                fv.features.get("type_heart_rate", 0.0),
                fv.features.get("type_ecg_summary", 0.0),
                fv.features.get("type_temperature", 0.0),
                fv.features.get("type_step_count", 0.0),
                fv.features.get("modality_normalized_value", 0.0),
                fv.features.get("physiological_range_deviation", 0.0),
                fv.features.get("raw_measurement", 0.0),
                run_id,
            ])
        filename = f"stage2_features_{run_id}.csv"
    elif stage_key in ["clustered", "stage3", "stage4", "stage4_clustered", "kmeans"]:
        writer.writerow(["record_id", "record_type", "value", "unit", "kmeans_cluster_id", "cluster_label", "policy_sensitivity", "effective_security_class", "policy_override", "override_reason", "pipeline_run_id"])
        for r in current_demo_records:
            writer.writerow([
                r.record_id,
                r.record_type.value,
                r.value,
                r.unit,
                r.kmeans_cluster_id,
                r.cluster_label,
                r.policy_sensitivity.value if r.policy_sensitivity else (r.sensitivity.value if r.sensitivity else "LOW"),
                r.effective_security_class.value if r.effective_security_class else "LOW",
                1 if r.policy_override else 0,
                r.override_reason or "",
                r.pipeline_run_id or run_id,
            ])
        filename = f"stage4_clustered_dataset_{run_id}.csv"
    else:
        raise HTTPException(status_code=400, detail=f"Unknown export stage '{stage}'. Valid stages: raw, features, clustered.")

    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.get("/api/pipeline/export/{stage}.json")
def export_pipeline_stage_json(stage: str):
    """Export a specific pipeline stage intermediate dataset as JSON."""
    global current_demo_records, current_feature_vectors, current_pipeline_run_id, current_clustering_result
    if not current_demo_records:
        raise HTTPException(status_code=400, detail="No active dataset available for export.")

    run_id = current_pipeline_run_id or "UNKNOWN-PIPE"
    stage_key = stage.lower()
    if stage_key in ["raw", "stage1", "stage1_raw"]:
        data = {
            "stage": "stage1_raw_dataset",
            "pipeline_run_id": run_id,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "record_count": len(current_demo_records),
            "records": [r.model_dump() for r in current_demo_records],
        }
        filename = f"stage1_raw_dataset_{run_id}.json"
    elif stage_key in ["features", "stage2", "stage2_features"]:
        data = {
            "stage": "stage2_features",
            "pipeline_run_id": run_id,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "feature_names": HealthcareFeatureExtractor.FEATURE_NAMES,
            "feature_count": len(HealthcareFeatureExtractor.FEATURE_NAMES),
            "records": [fv.model_dump() for fv in current_feature_vectors],
        }
        filename = f"stage2_features_{run_id}.json"
    elif stage_key in ["clustered", "stage3", "stage4", "stage4_clustered", "kmeans"]:
        data = {
            "stage": "stage4_clustered_dataset",
            "pipeline_run_id": run_id,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "record_count": len(current_demo_records),
            "clustering_diagnostics": current_clustering_result.diagnostics.model_dump() if current_clustering_result else None,
            "records": [r.model_dump() for r in current_demo_records],
        }
        filename = f"stage4_clustered_dataset_{run_id}.json"
    else:
        raise HTTPException(status_code=400, detail=f"Unknown export stage '{stage}'. Valid stages: raw, features, clustered.")

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
    global current_demo_records, current_power_override, current_pipeline_run_id, current_clustering_result, current_feature_vectors
    run_store.reset()
    receiver.reset_stats()
    current_demo_records = []
    current_power_override = None
    current_pipeline_run_id = None
    current_clustering_result = None
    current_feature_vectors = []
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
