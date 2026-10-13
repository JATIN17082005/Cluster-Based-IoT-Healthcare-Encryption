# Phase 0: Workspace Inspection & Architecture Plan

## 1. Initial Workspace State & Hardware Inspection

- **Workspace Path:** `C:\Cluster based IoT data encryption`
- **Initial Content:** The workspace was initially blank; the project specification `Antigravity_Execution_Plan_IoT_Healthcare_Encryption.md` was retrieved and positioned in the workspace root.
- **Python Environment:** Python 3.14.5 (Windows 64-bit).
- **Core Dependencies:** Installed `cryptography` (v50.0.2), `fastapi` (v0.143.0), `pytest` (v9.1.1), `pydantic` (v2.14.1), and `uvicorn` (v0.52.4).
- **Hardware Inspection:** Enumeration of serial ports identified virtual Bluetooth COM ports (COM3 - COM10). No dedicated hardware power meter (such as Monsoon, Keysight, Otii Arc, or INA219 current sensor) is connected.
- **Hardware Handling Decision:**
  - Provide a modular `PowerMeasurementAdapter` interface.
  - Implement a rigorous **Software Simulation / Estimate** mode with visible parameters and a strict `SIMULATED / ESTIMATED — NOT A PHYSICAL BATTERY READING` badge.
  - Provide an **Imported Instrument Log (CSV)** parser supporting physical readings from external benchtop power analyzers.
  - Provide a live hardware serial adapter stub for optional sensor attachments.

## 2. Technology Stack Selection & Rationale

- **Backend Framework:** FastAPI (Python 3.14)
  - *Rationale:* Lightweight, high-performance async web framework with automatic OpenAPI documentation and native Pydantic v2 validation.
- **Cryptographic Library:** `cryptography.hazmat.primitives.ciphers.aead.AESGCM`
  - *Rationale:* Standard vetted NIST-compliant AEAD implementation ensuring authenticated encryption with 256-bit keys and fresh 96-bit nonces.
- **Experimental XOR Module:** Pure Python bitwise XOR stream with HMAC-SHA256 integrity tag
  - *Rationale:* Directly models the student review proposal with strict documentation of known cryptographic weaknesses and clear isolation.
- **Data Storage:** SQLite (`sqlite3` built-in)
  - *Rationale:* Zero external service dependency, reliable persistence for runs, metrics, and power samples.
- **Frontend:** Lightweight modern HTML5, CSS3, and Vanilla JavaScript
  - *Rationale:* Zero Node.js/npm dependencies, works 100% offline, highly responsive, renders live pipeline flows, side-by-side metric tables, and charts.

## 3. Requirement Traceability Matrix (Phases 1 to 7)

| Requirement | Description | Target Module |
|---|---|---|
| FR-01 | Seeded synthetic healthcare data | `src/data_generator.py` |
| FR-02 | Deterministic configurable sensitivity rules | `src/classifier.py` |
| FR-03 | Deterministic high/low clustering | `src/cluster_manager.py` |
| FR-04 | Pipeline visualization | `static/index.html`, `static/app.js` |
| FR-05 | AES-256-GCM encryption for high sensitivity | `src/crypto.py` |
| FR-06 | Experimental XOR encryption with HMAC-SHA256 | `src/crypto.py` |
| FR-07 | Baseline mode (all AES-256-GCM) | `src/benchmark_runner.py` |
| FR-08 | Decryption & integrity verification | `src/receiver.py` |
| FR-09 | Transmission to local healthcare receiver | `src/receiver.py`, `src/server.py` |
| FR-10 | Controlled tamper rejection demo | `src/receiver.py`, `src/crypto.py` |
| FR-11 | Monotonic high-res encryption timing | `src/benchmark_runner.py`, `src/metrics.py` |
| FR-12 | TSR and PLR transmission metrics | `src/metrics.py` |
| FR-13 | Hardware measurement adapter | `src/power_measurement.py` |
| FR-14 | Imported CSV power log parser | `src/power_measurement.py` |
| FR-15 | Software estimation fallback model | `src/power_measurement.py` |
| FR-16 | Energy integration ($E = \int V \times I \, dt$) | `src/metrics.py`, `src/power_measurement.py` |
| FR-17 | Indicative battery runtime calculation | `src/metrics.py` |
| FR-18 | Baseline vs. Adaptive comparison | `src/benchmark_runner.py`, `src/metrics.py` |
| FR-19 | Configurable batch size & repetitions | `src/benchmark_runner.py` |
| FR-20 | CSV and JSON result export | `src/server.py`, `src/run_store.py` |
| FR-21 to FR-25 | Interactive Dashboard & Honest Reporting | `static/index.html`, `static/app.js` |

## 4. Phase Gates & Verification Strategy

Each phase will conclude with automated tests verifying that all acceptance criteria are met before moving to subsequent phases.
