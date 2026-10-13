# ClusterGuard UI Redesign & Faculty Review Presentation Guide

## 1. Executive Summary & Design Objective

The user interface of the **Cluster-Based IoT Healthcare Encryption & Energy Benchmark** application was completely redesigned into **ClusterGuard: IoT Healthcare Security & Energy Lab**—a modern research analytics dashboard.

Within **10 seconds** of opening the interface, a university faculty reviewer can immediately grasp:
1. **The Core Research Objective:** Evaluating the computational, latency, and energy trade-offs of sensitivity-adaptive encryption on resource-constrained IoT healthcare devices.
2. **The Clinical Pipeline:** How patient records are categorized into high-risk emergency vitals (`CLUSTER-HIGH`) versus routine vitals (`CLUSTER-LOW`).
3. **The Cryptographic Routes:** NIST-standard AES-256-GCM AEAD encryption for high-sensitivity data versus an experimental lightweight stream cipher for routine telemetry.
4. **The Security Guarantee:** Rejection of tampered payloads by the local clinical receiver with constant-time authentication tag and HMAC verification.
5. **The Real Benchmark Outcome:** An honest demonstration showing that on an x86 desktop host with hardware AES-NI instructions, AES-256-GCM is faster than interpreted Python loops (**`STATUS: REGRESSION`**), transparently explaining why microcontroller targets behave differently.
6. **The Battery Honesty:** Prominent labeling of software-modeled estimates (`SIMULATED / ESTIMATED — NOT A PHYSICAL BATTERY READING`), accompanied by an interactive model-driven battery discharge simulation and a physical laboratory instrument CSV importer.

---

## 2. Design System Architecture

- **Color Palette:**
  - Dark Navy & Obsidian Surface: `#080c15` / `#0f172a` / `#162035`
  - Primary Accents: Cyan (`#06b6d4`), Sky Blue (`#0ea5e9`), Teal (`#14b8a6`)
  - Status Indicators: Emerald Success (`#10b981`), Rose Failure/Regression (`#f43f5e`), Amber Warning (`#f59e0b`)
  - Typography: System sans-serif with accessible high-contrast scale and monospaced numerical data columns.
- **Responsiveness:**
  - Optimized for 1440 × 900 desktop review environments.
  - Fully reflowable for laptop, tablet, and mobile (375 × 812) viewports.

---

## 3. Key Redesigned Features

### A. Top Navigation & Executive Summary
- **Live Health Pill:** Real-time polling of `/api/health` with a pulsing green indicator.
- **Measurement Provenance Banner:** Unmistakable yellow badge indicating software estimation mode.
- **"Guided Demo" Action:** Prominently launches the 8-step guided demonstration stepper.
- **Four Dynamic KPI Cards:**
  1. Records Processed & High/Routine split.
  2. Transmission Success Rate (TSR) & Packet Loss Rate (PLR).
  3. Mean Encryption Latency with delta badge.
  4. Normalized Energy Consumption ($mJ/1,000$ records) & Charge consumed ($mAh$).

### B. Interactive 6-Stage Processing Pipeline (FR-04)
A visual sequence:
$$\text{Data Generation} \longrightarrow \text{Classifier} \longrightarrow \text{Cluster Partition} \longrightarrow \text{Adaptive Cipher} \longrightarrow \text{Local Receiver} \longrightarrow \text{Energy Evaluation}$$

- **Clickable Stage Inspector Drawer:** Clicking any pipeline stage opens a drawer detailing:
  - Stage purpose and clinical rationale.
  - Exact inputs and outputs.
  - Live status and record counts.
  - Non-specialist faculty summary explaining the step in plain English.

### C. Guided Demonstration Mode (Walkthrough Stepper)
A presentation stepper providing a structured 8-step sequence:
1. Generate 50 Seeded Records (Seed 42).
2. Inspect Clinical Sensitivity Classification (15 High vs. 35 Routine).
3. Demonstrate Dual Cryptographic Routing (AES-256-GCM vs. XOR stream).
4. Execute 10-Repetition Benchmark Trial.
5. Analyze Performance & Scientific Honesty (Desktop regression explanation).
6. Verify Interactive Tamper Rejection (Ciphertext bit flip dropped).
7. Review Battery Measurement Methodology (Mode A estimate vs Mode B lab CSV).
8. Inspect Evidence Exports (CSV/JSON) & Conclude Defense.

### D. Interactive Battery Drain Simulation (Model-Driven Visual Feature)
- **SVG Rechargeable Battery Meter:** Custom vector battery body with positive terminal, animated liquid fill bar, and dynamic color transitions (Green $\rightarrow$ Amber $\rightarrow$ Red).
- **Dual Meter Comparison:** Displays Baseline vs Adaptive remaining charge side by side.
- **Driven by Energy Model:** Because the adaptive proposal consumes $+1.67\%$ more energy (regression: $0.025902\,\text{J}$ vs $0.025477\,\text{J}$), the adaptive battery fill drains slightly more, strictly matching real results.
- **Controls:** `Start Simulation Demo`, `Pause`, `Resume`, `Reset Battery`, and a `Visual Presentation Scale` selector (50x scale for a noticeable 10-second presentation drain).
- **Permanent Label:** `SIMULATED BATTERY — VISUAL DEMONSTRATION ONLY`.

### E. Record Explorer & Slide-Over Details Drawer
- Interactive searchable and filterable table.
- Search by record ID, patient ID, vital type, or classification reason.
- Filters by Sensitivity (HIGH / LOW), Cluster (`CLUSTER-HIGH` / `CLUSTER-LOW`), and Vital Type.
- Row click opens a details drawer revealing the clinical vital payload, physiological thresholds, and cryptographic route.

### F. Security Demonstration & Lab CSV Importer
- Single-bit tamper mutations on AES-256-GCM and XOR-EXPERIMENTAL payloads.
- Immediate rejection with receiver diagnostic error messages.
- External lab instrument CSV importer validating headers, monotonic timestamps, positive voltage/current, and trapezoidal integration ($P = V \times I$).

---

## 4. Verification Evidence & Captured Screenshots

All screenshots captured during automated Playwright browser verification are located in the conversation artifacts directory:
- [`redesign_tab1_overview.png`](file:///C:/Users/Jatinp/.gemini/antigravity/brain/216a23d8-eb99-4432-b028-034538522d8e/redesign_tab1_overview.png) — Executive overview, KPI cards, and processing pipeline.
- [`redesign_tab1_pipeline_drawer.png`](file:///C:/Users/Jatinp/.gemini/antigravity/brain/216a23d8-eb99-4432-b028-034538522d8e/redesign_tab1_pipeline_drawer.png) — Interactive pipeline stage drawer inspection.
- [`redesign_guided_demo_modal.png`](file:///C:/Users/Jatinp/.gemini/antigravity/brain/216a23d8-eb99-4432-b028-034538522d8e/redesign_guided_demo_modal.png) — Guided demonstration walkthrough stepper.
- [`redesign_tab2_battery_sim.png`](file:///C:/Users/Jatinp/.gemini/antigravity/brain/216a23d8-eb99-4432-b028-034538522d8e/redesign_tab2_battery_sim.png) — Interactive dual battery drain simulation feature.
- [`redesign_tab2_comparison.png`](file:///C:/Users/Jatinp/.gemini/antigravity/brain/216a23d8-eb99-4432-b028-034538522d8e/redesign_tab2_comparison.png) — Performance audit table and visual comparative bars.
- [`redesign_tab3_record_explorer.png`](file:///C:/Users/Jatinp/.gemini/antigravity/brain/216a23d8-eb99-4432-b028-034538522d8e/redesign_tab3_record_explorer.png) — Record explorer with search, filters, and details drawer.
- [`redesign_tab4_security.png`](file:///C:/Users/Jatinp/.gemini/antigravity/brain/216a23d8-eb99-4432-b028-034538522d8e/redesign_tab4_security.png) — Security boundary and software power model configuration.
- [`redesign_tab5_history.png`](file:///C:/Users/Jatinp/.gemini/antigravity/brain/216a23d8-eb99-4432-b028-034538522d8e/redesign_tab5_history.png) — Benchmark execution history and CSV/JSON downloads.
- [`redesign_mobile_view.png`](file:///C:/Users/Jatinp/.gemini/antigravity/brain/216a23d8-eb99-4432-b028-034538522d8e/redesign_mobile_view.png) — Mobile viewport rendering (375 × 812).

---

## 5. Startup Commands for Live Presentation

```powershell
# 1. Start application server (if not already running)
python -m uvicorn src.server:app --port 8000 --host 127.0.0.1

# 2. Open dashboard in modern browser
# http://127.0.0.1:8000

# 3. Run automated verification script (optional)
python scripts/test_browser_e2e.py
```
