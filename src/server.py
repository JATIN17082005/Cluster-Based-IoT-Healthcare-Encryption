"""FastAPI backend application serving the IoT Healthcare Data Encryption API and Dashboard."""

import os
import io
import csv
import json
from typing import Optional, List, Dict, Any
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
)
from src.data_generator import SyntheticDataGenerator
from src.classifier import SensitivityClassifier, get_default_ruleset
from src.cluster_manager import ClusterManager
from src.crypto import KeyManager, EncryptionEngine, tamper_envelope
from src.receiver import LocalHealthcareReceiver
from src.benchmark_runner import BenchmarkRunner
from src.power_measurement import CSVPowerImporter, SimulationPowerProvider, McuEnergyModel
from src.run_store import RunStore
from src.metrics import compute_percentage_change, integrate_energy_joules

app = FastAPI(
    title="Cluster-Based IoT Healthcare Encryption Demo",
    description="Academic benchmark comparing AES-256-GCM baseline with sensitivity-based adaptive encryption",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global services
key_manager = KeyManager()
receiver = LocalHealthcareReceiver(key_manager)
power_config = PowerModelConfig()
mcu_config = McuHardwareScenarioConfig()
runner = BenchmarkRunner(key_manager=key_manager, receiver=receiver, power_model=power_config)
run_store = RunStore()

# State for currently generated demo batch
current_demo_records: List[SensorRecord] = []
current_power_override: Optional[Any] = None


class McuScenarioRequest(BaseModel):
    record_count: Optional[int] = Field(default=None, ge=1, le=1000)
    high_sensitivity_count: Optional[int] = Field(default=None, ge=0)
    low_sensitivity_count: Optional[int] = Field(default=None, ge=0)
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
):
    """Calculate MCU scenario using query params, current demo records, or default 100-record batch."""
    global current_demo_records, mcu_config
    if record_count is not None:
        rec_count = max(1, record_count)
        if high_count is not None and low_count is not None:
            high_cnt = max(0, high_count)
            low_cnt = max(0, low_count)
        else:
            high_cnt = int(rec_count * 0.45)
            low_cnt = rec_count - high_cnt
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
    )


@app.post("/api/battery/mcu-scenario")
def run_mcu_scenario(req: McuScenarioRequest):
    """Calculate MCU Scenario B energy values for a requested record count and sensitivity split."""
    global current_demo_records, mcu_config
    active_cfg = req.config or mcu_config

    if req.record_count is not None:
        rec_count = req.record_count
        if req.high_sensitivity_count is not None and req.low_sensitivity_count is not None:
            high_cnt = req.high_sensitivity_count
            low_cnt = req.low_sensitivity_count
        else:
            high_cnt = int(rec_count * 0.45)
            low_cnt = rec_count - high_cnt
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
    )


@app.post("/api/demo/generate")
def generate_synthetic_data(req: GenerateRequest):
    """Generate a seeded batch of synthetic healthcare sensor records."""
    global current_demo_records
    gen = SyntheticDataGenerator(seed=req.seed)
    records = gen.generate_batch(
        count=req.count,
        classifier=runner.classifier,
        cluster_manager=runner.cluster_manager,
    )
    current_demo_records = records

    high_group, low_group = runner.cluster_manager.form_clusters(records)

    return {
        "seed": req.seed,
        "count": len(records),
        "high_cluster_count": high_group.record_count,
        "low_cluster_count": low_group.record_count,
        "records_preview": [r.model_dump() for r in records[:20]],
        "all_records": [r.model_dump() for r in records],
    }


@app.post("/api/benchmark/run")
def execute_benchmark(req: BenchmarkRunRequest):
    """Execute baseline, adaptive, or paired comparison benchmark."""
    global current_demo_records, current_power_override

    # Use pre-generated records if count and seed match, otherwise generate fresh
    if current_demo_records and len(current_demo_records) == req.record_count:
        records = current_demo_records
    else:
        gen = SyntheticDataGenerator(seed=req.seed)
        records = gen.generate_batch(
            count=req.record_count,
            classifier=runner.classifier,
            cluster_manager=runner.cluster_manager,
        )
        current_demo_records = records

    if req.mode == "comparison":
        comp_result = runner.run_comparison(
            record_count=req.record_count,
            seed=req.seed,
            repetitions=req.repetitions,
        )
        if "error" in comp_result:
            raise HTTPException(status_code=400, detail=comp_result["error"])

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
    global current_demo_records, current_power_override
    run_store.reset()
    receiver.reset_stats()
    current_demo_records = []
    current_power_override = None
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
