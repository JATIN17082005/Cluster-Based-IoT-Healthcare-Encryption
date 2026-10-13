"""Verification script comparing API response, CSV export, and JSON export for full seeded benchmark."""

import os
import sys
import json
import csv
import urllib.request

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

def test_benchmark_consistency():
    print("=== Testing Seeded Benchmark Consistency Across API, CSV, and JSON ===")
    
    # 1. Trigger benchmark run via API
    url_run = "http://127.0.0.1:8000/api/benchmark/run"
    payload = json.dumps({
        "mode": "comparison",
        "record_count": 50,
        "seed": 42,
        "repetitions": 10,
    }).encode("utf-8")
    
    req = urllib.request.Request(url_run, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    comp = data["comparison"]
    base_run_id = data["baseline_run_id"]
    adapt_run_id = data["adaptive_run_id"]
    
    print(f"[OK] Benchmark executed: Baseline ID={base_run_id}, Adaptive ID={adapt_run_id}")
    
    # Verify API status
    assert comp["overall_result_status"] == "REGRESSION", f"Expected REGRESSION, got {comp['overall_result_status']}"
    assert comp["measurement_source"] == "estimated"
    
    # Extract API values
    api_enc_base = comp["encryption_time_mean_ms"]["baseline"]
    api_enc_adapt = comp["encryption_time_mean_ms"]["proposed"]
    api_enc_pct = comp["encryption_time_mean_ms"]["percentage_change"]
    
    api_energy_base = comp["total_energy_joules"]["baseline"]
    api_energy_adapt = comp["total_energy_joules"]["proposed"]
    api_energy_pct = comp["total_energy_joules"]["percentage_change"]
    api_energy_saving = comp["total_energy_joules"]["energy_saving_percent"]
    
    print(f"API Encryption Latency: Base={api_enc_base:.6f} ms, Adapt={api_enc_adapt:.6f} ms, Change={api_enc_pct:+.2f}%")
    print(f"API Energy Consumption: Base={api_energy_base:.6f} J, Adapt={api_energy_adapt:.6f} J, Change={api_energy_pct:+.2f}%, Saving={api_energy_saving:+.2f}%")
    
    # Formula check
    expected_enc_pct = ((api_enc_adapt - api_enc_base) / api_enc_base) * 100.0
    expected_energy_saving = ((api_energy_base - api_energy_adapt) / api_energy_base) * 100.0
    assert abs(api_enc_pct - expected_enc_pct) < 1e-9, "API latency percentage change formula mismatch!"
    assert abs(api_energy_saving - expected_energy_saving) < 1e-9, "API energy saving percentage formula mismatch!"
    print("[OK] Exact API unrounded formulas verified.")

    # 2. Check JSON Export for Adaptive Run
    url_json = f"http://127.0.0.1:8000/api/runs/{adapt_run_id}/export.json"
    with urllib.request.urlopen(url_json) as resp:
        json_export = json.loads(resp.read().decode("utf-8"))
        
    json_metrics = json_export["metrics"]
    assert json_metrics["run_id"] == adapt_run_id
    assert abs(json_metrics["encryption_time_mean_ms"] - api_enc_adapt) < 1e-6
    assert abs(json_metrics["total_energy_joules"] - api_energy_adapt) < 1e-6
    assert json_metrics["measurement_source"] == "estimated"
    print("[OK] JSON Export matches API response exactly.")

    # 3. Check CSV Export for Adaptive Run
    url_csv = f"http://127.0.0.1:8000/api/runs/{adapt_run_id}/export.csv"
    with urllib.request.urlopen(url_csv) as resp:
        csv_text = resp.read().decode("utf-8")
        
    reader = csv.DictReader(csv_text.strip().splitlines())
    csv_rows = list(reader)
    assert len(csv_rows) == 1
    row = csv_rows[0]
    
    csv_enc_mean = float(row["enc_mean_ms"])
    csv_energy = float(row["total_energy_joules"])
    csv_tsr = float(row["tsr_percent"])
    csv_plr = float(row["plr_percent"])
    
    assert abs(csv_enc_mean - api_enc_adapt) < 1e-5
    assert abs(csv_energy - api_energy_adapt) < 1e-5
    assert csv_tsr == 100.0
    assert csv_plr == 0.0
    assert row["measurement_source"] == "estimated"
    print("[OK] CSV Export matches API response exactly.")
    
    # 4. Zero secret key audit in exports
    raw_json_str = json.dumps(json_export)
    for forbidden in ["aes_key", "secret_key", "raw_key", "xor_key", "hmac_key"]:
        assert forbidden not in raw_json_str.lower(), f"Leaked {forbidden} in JSON export!"
        assert forbidden not in csv_text.lower(), f"Leaked {forbidden} in CSV export!"
    print("[OK] Zero secret keys confirmed in both JSON and CSV exports.")

    print("=== All Consistency and Verification Checks Passed! ===")

if __name__ == "__main__":
    test_benchmark_consistency()
