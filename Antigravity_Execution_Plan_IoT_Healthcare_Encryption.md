# Antigravity Execution Plan
## Cluster-Based Encryption for Privacy and Security in IoT Healthcare

**Purpose:** Build a reliable, repeatable final-review demo from the project described in the review slides. The demo must show the complete data path and give measurable evidence about encryption performance and energy/battery use.

## 1. Project definition taken from the review slides

The proposed system:
1. Generates healthcare/IoT sensor data.
2. Classifies records by sensitivity.
3. Groups records into sensitivity-based clusters.
4. Applies AES-256 to highly sensitive records.
5. Applies lightweight XOR encryption to routine/low-sensitivity records.
6. Transmits encrypted records to a healthcare-server receiver.
7. Evaluates the system using transmission success, packet loss, encryption time, and energy efficiency.

The slides' examples of healthcare data include heart rate, ECG, body temperature, and step count. Their stated problem is that applying the same expensive encryption to every record may increase computation and energy use on battery-constrained IoT devices.

**Implementation boundary:** Treat this as an academic prototype, not a medical device or production healthcare service. Use synthetic/demo data only. Do not claim that battery use is lower until a controlled comparison produces results.

## 2. Critical security and evidence rules

- Use **AES-256-GCM** for the high-sensitivity path. This preserves the AES-256 requirement and adds authenticated encryption so tampering can be detected. Use a fresh, unique nonce for every encryption under a key. Never reuse a nonce with the same AES-GCM key.
- Preserve the project's XOR path as a clearly labelled **experimental lightweight comparison path**. XOR by itself is not secure encryption: it has no built-in integrity protection and can be broken if keys/masks are reused or predictable. Do not describe XOR alone as production-grade healthcare security. Add an HMAC-SHA-256 integrity check with a separately configured secret if the prototype needs to detect tampering on that path. Document that HMAC does not make weak/reused XOR encryption confidential.
- Do not store keys in source code, the browser, logs, screenshots, or exported reports. Load demo secrets from environment variables or generate ephemeral development-only keys at startup. Warn clearly when a development key is being used.
- Do not send real patient data to any external service. Keep the default demo local/offline.
- Never fabricate battery readings, power measurements, encryption savings, packet-loss results, or successful test outcomes. Every chart and export must state whether values are **hardware-measured**, **software-estimated**, or **simulated**.
- Keep a conventional **all-AES-256-GCM baseline**. Compare it with the adaptive AES/XOR route using the same records, batch sizes, network conditions, and run duration.
- If the adaptive approach is slower or consumes more energy in a test, show that result honestly. The goal is to measure the trade-off, not force a desired conclusion.

## 3. Functional requirements (FR)

### Data and sensitivity classification

**FR-01 — Generate demo data.** Generate repeatable synthetic records containing fields such as patient/demo ID, timestamp, heart rate, ECG sample/summary, temperature, step count, and record type. Clearly label all values as synthetic. Support a fixed random seed so repeated runs use identical data.

**FR-02 — Configure sensitivity rules.** Classify each record as `HIGH` or `LOW` using a visible, deterministic ruleset. Provide the reason for the classification in the UI and record metadata. Rules must be editable in configuration, not scattered through the code.

**FR-03 — Form sensitivity clusters.** Group the batch into high- and low-sensitivity clusters after classification. Display record count and cluster ID for each group. For the first version, use deterministic grouping by sensitivity; do not imply that an unsupervised machine-learning clustering algorithm is being used.

**FR-04 — Show the pipeline.** Visualize the sequence: data generation → sensitivity classification → cluster formation → encryption route → transmission → receiver verification → metrics.

### Encryption and transmission

**FR-05 — Encrypt high-sensitivity records.** Use AES-256-GCM with a unique nonce and authentication tag. Record algorithm name, elapsed time, payload size, and success/failure status; never record plaintext secrets or encryption keys in logs.

**FR-06 — Encrypt routine records using the project's XOR route.** Implement the XOR transformation as a separate, testable module and label it in the UI as an experimental comparison. Do not use a fixed hard-coded XOR key. Add HMAC-SHA-256 verification with a separate key if tamper detection is shown for this path. Explain the limits of XOR in the Security panel and report.

**FR-07 — Provide a baseline mode.** Encrypt all records with AES-256-GCM, regardless of sensitivity, to represent uniform encryption. This is the control group for performance and energy comparison.

**FR-08 — Decrypt and verify.** The receiver must decrypt valid records back to the original serialized content. Reject records with a bad authentication tag or integrity check. Display a useful error without exposing key material.

**FR-09 — Transmit to a receiver.** Send encrypted envelopes to a local healthcare-server endpoint. The receiver must record received count, accepted/rejected count, and arrival time. If networking is unavailable, show a clear offline error and keep local benchmark functionality available.

**FR-10 — Demonstrate tamper rejection.** Provide a demo-only control that changes a ciphertext/tag or integrity value and confirms that receiver verification rejects it. Make it impossible to accidentally trigger during a normal benchmark run.

### Metrics and energy/battery measurement

**FR-11 — Measure encryption time.** Use a monotonic high-resolution timer around the encryption operation. Report per-record times and batch-level mean, median, and p95. Separate encryption time from serialization and network latency.

**FR-12 — Measure transmission performance.** Report sent, received, rejected, and timed-out records. Show formulas next to metrics:
- `Transmission Success Rate (TSR, provisional expansion) = successfully received and verified records / records sent × 100%`.
- `Packet Loss Rate (PLR) = records sent but not received / records sent × 100%`.
- Rejected records must be shown separately from packets not received, so integrity failures are not misreported as network loss.
- Confirm with the project team that TSR is intended to mean *Transmission Success Rate*. The source slides do not define the acronym.

**FR-13 — Support a hardware measurement mode.** If a supported current/voltage sensor or external power meter is connected, sample device supply voltage and current with timestamps during the benchmark. Keep the sensor reader in an isolated adapter so the system can run without hardware. Do not assume a particular board or sensor exists; inspect available hardware before selecting an adapter.

**FR-14 — Support imported measurements.** Allow a documented CSV format for external power measurements if live sensor integration is unavailable. Validate required columns, units, missing values, and sample order. Display whether the data came from an instrument or was imported.

**FR-15 — Provide an estimate/simulation fallback.** Without power hardware or imported measurements, calculate an explicitly labelled estimate from a documented, editable current/power model. All model inputs must be visible, such as assumed voltage, average current by operating state, encryption duration, and radio-active duration. Add a visible `SIMULATED / ESTIMATED — NOT A PHYSICAL BATTERY READING` label. Do not use made-up sensor values to imply a measurement.

**FR-16 — Calculate and display energy use.** For hardware/imported samples, calculate energy by integrating measured power over time: `Energy (J) = Σ [voltage (V) × current (A) × elapsed time (s)]`. Report average current, average power, total energy per batch, energy per record, and energy per 100 records. State what measurement interval and device boundary were used.

For a model-based estimate, use the same equations but label all outputs estimated and show the model assumptions. If the device runs at approximately constant voltage, optionally show `mAh used = average current (mA) × duration (hours)`.

**FR-17 — Estimate battery runtime cautiously.** Allow the user to enter nominal battery capacity in mAh and a usable-capacity factor. Calculate an indicative runtime as `usable capacity (mAh) / measured-or-assumed average current (mA)`. Show a warning that this is an estimate affected by battery age, regulator losses, radio conditions, and device sleep/wake patterns. Do not call it a measured battery-life result.

**FR-18 — Compare baseline and adaptive modes.** Run identical batches in baseline and adaptive modes. Show side-by-side encryption time, total elapsed time, energy per batch, energy per record, average current, transmission success, packet loss, receiver rejection count, and payload bytes. Calculate percentage change with the sign and direction explained. If no actual power data is available, comparison charts must say `estimated` or `simulated`.

**FR-19 — Repeat tests and show variability.** Permit configurable batch size and number of repetitions. Save per-run results and aggregate mean/median/spread; disclose sample count. Use the same seed and workload for paired baseline/adaptive comparisons. Avoid presenting a single run as conclusive evidence.

**FR-20 — Export results.** Export a CSV of per-run metrics and a JSON summary. Include timestamp, app version, mode, run ID, data seed, record count, measurement source, units, hardware/sensor identifier where applicable, and model assumptions. Do not export secrets or personal data.

### Dashboard and operational behavior

**FR-21 — Main dashboard.** Show generated records, sensitivity split, cluster counts, encryption route counts, receiver results, and current benchmark status.

**FR-22 — Battery and performance page.** Show baseline vs adaptive charts, measurement source label, energy per record/batch, average current/power, estimated runtime where applicable, encryption timing, transmission metrics, and test configuration.

**FR-23 — Record inspection.** Show a safe summary of a record, its sensitivity reason, cluster, algorithm, status, and timings. Do not display keys. Do not persist plaintext by default after a run; any debug display must use synthetic data and be clearly marked.

**FR-24 — Demo controls.** Include `Generate Data`, `Run Baseline`, `Run Adaptive`, `Run Both / Compare`, `Stop Run`, `Reset Demo`, and `Export Results`. Disable conflicting controls while a benchmark is running. Show progress and clear error states.

**FR-25 — Explain the results.** Provide a short generated summary based on actual stored metrics. It must state the measurement source, test conditions, sample count, actual observed changes, and caveats. Do not hard-code success language such as “battery saved” before results are available.

## 4. Non-functional requirements (NFR)

**NFR-01 — Correctness.** Encryption/decryption round trips must reproduce the exact original serialized record. Tampering must be detected on authenticated paths. Classification and metrics must be deterministic for a fixed configuration and data seed.

**NFR-02 — Security.** Use a vetted cryptographic library, safe key handling, unique AES-GCM nonces, authenticated verification, and no secrets in logs or browser assets. XOR's experimental limitations must be plainly stated. No production-security claim may be based on XOR alone.

**NFR-03 — Measurement honesty.** Every energy value and chart must carry a source label: hardware-measured, imported instrument data, software-estimated, or simulated. Keep raw measurements and model-based values distinguishable in storage and exports.

**NFR-04 — Repeatability.** Same app version, seed, configuration, data size, and test conditions must produce the same synthetic input. Cryptographic nonces may differ; the plaintext workload and comparison setup must remain equivalent.

**NFR-05 — Reliability.** Recover cleanly from missing hardware, disconnected receiver, malformed CSV, invalid configuration, timeout, corrupt envelope, and interrupted benchmark. Show actionable errors and preserve completed run results.

**NFR-06 — Performance.** Benchmark code must not include UI rendering, file writing, or network waiting inside the measured encryption interval. Report those operations separately. Avoid arbitrary performance claims or hard-coded target savings.

**NFR-07 — Resource efficiency.** The app must run locally on an ordinary student laptop without requiring a cloud account or Docker. Avoid heavyweight dependencies unless the existing repository already relies on them.

**NFR-08 — Usability.** Provide a clear workflow for a live presentation, readable units, definitions beside metrics, visible running/completed/error states, and a reset option that restores a known demo state.

**NFR-09 — Privacy.** Use synthetic data, bind services to localhost by default, and avoid sending health data or benchmark logs to external endpoints.

**NFR-10 — Maintainability.** Separate classification, clustering, encryption, transport, measurement adapters, benchmark orchestration, metric calculations, and UI. Keep configuration in one documented location.

**NFR-11 — Portability.** The software-only path must work without a sensor. Hardware-specific code must be optional and tested independently. Document operating-system and dependency requirements.

**NFR-12 — Accessibility and clarity.** Do not rely on color alone to distinguish high/low sensitivity, baseline/adaptive mode, measured/estimated values, or success/failure.

## 5. Recommended architecture

Keep the implementation modular. Adapt it to the existing repository after inspecting the current files; do not replace an existing working stack without a reason.

1. **Synthetic data generator** — reproducible sensor records and batch generation.
2. **Sensitivity classifier** — deterministic configurable rules and classification explanations.
3. **Cluster manager** — deterministic high/low grouping and cluster metadata.
4. **Encryption service** — AES-256-GCM module, experimental XOR module, verification/decryption, and timing.
5. **Envelope/schema layer** — record ID, cluster, sensitivity, algorithm, nonce/tag or integrity metadata, payload size, timestamp, and run ID. Validate input before processing.
6. **Local receiver service** — receive, verify, decrypt, count arrivals/rejections, and return acknowledgements.
7. **Benchmark runner** — paired baseline/adaptive runs with fixed input, run IDs, cancellation, timeouts, and per-operation timing.
8. **Power measurement adapter** — live hardware adapter if available, CSV importer, and a separate estimate/simulation provider. Do not silently switch sources.
9. **Metrics service** — one authoritative implementation of formulas used by both dashboard and export.
10. **Dashboard** — workflow, record view, run controls, benchmark comparison, battery panel, security caveats, and export.
11. **Run store** — local-only storage (SQLite or the repository's existing local storage pattern) for settings and run summaries. Avoid retaining plaintext unless needed for a clearly controlled demo view.

### Stack selection rule

First inspect the repository and continue with its existing framework if it is usable. If the workspace is empty, choose a small local stack with a Python backend (for example, FastAPI) and a lightweight frontend. Do not add cloud infrastructure, accounts, databases requiring a server, Docker, or unrelated features. Write down the chosen stack and why before implementing it.

## 6. Battery experiment protocol

This part is required, because the project's claim includes reduced battery/energy usage.

### Comparison groups

- **Baseline:** all records encrypted with AES-256-GCM.
- **Adaptive proposal:** high-sensitivity records use AES-256-GCM; low-sensitivity records use the project's XOR comparison path.
- Use exactly the same generated records, serialized input, batch sizes, receiver, Wi-Fi/network conditions, and number of repetitions for both groups.
- Record the number and size of records routed to each algorithm. If the algorithms change the transmitted byte count, display that fact because it can affect radio energy.

### Hardware measurement option

1. Identify the actual IoT board, power source, and available current/voltage instrument before writing a hardware driver.
2. Measure current and voltage at the device supply boundary. If a USB power meter measures the laptop/USB hub rather than the device alone, label the boundary accordingly and do not call it board-only consumption.
3. Capture a baseline idle interval, then run each paired batch long enough for the instrument to resolve the difference. Encryption-only operations may be too brief to distinguish individually, so measure repeated batches and integrate power over the full controlled run.
4. Keep radio state, transmit count, sleep settings, sensor polling, and power source identical between the baseline and adaptive runs.
5. Run at least 10 paired trials as a demo minimum; use more if results vary widely. Display the number of trials, median, and spread. Do not imply this sample size proves universal battery savings.
6. Save raw timestamped power samples, not only averages. Include voltage/current units, sample period, mode, and run ID.
7. Calculate total energy over the full benchmark interval and optionally subtract a separately measured idle baseline only when both intervals are aligned and the subtraction method is documented. Show both gross energy and incremental energy if baseline subtraction is used.

### Software-only fallback

If hardware is unavailable, retain the battery screen using an explicit model. Document every assumed state/current value and editable configuration. Estimate encryption energy from measured encryption duration and an assumed/known active current, and estimate radio energy separately from an assumed/known transmit duration/current. Make it clear that the model may not capture real hardware, regulator, radio, or battery effects. The software-only fallback is useful for a demo of the method but cannot validate a physical battery-life claim.

### Required battery outputs

- Measurement source: hardware, imported instrument log, or estimate/simulation.
- Device/power boundary and relevant hardware information, if known.
- Mean current (mA), mean voltage (V), mean power (mW), total energy (J or mWh), energy per record (mJ/record), and energy per 100 records.
- Batch elapsed time and record count.
- Estimated runtime only if battery capacity and average current are supplied; mark it as indicative.
- Baseline/adaptive difference with actual values and percentage change.
- Repetition count and variability.

Percentage change formula: `(adaptive value - baseline value) / baseline value × 100%`. Negative means the adaptive value is lower; label the direction for each metric, since lower latency/energy is usually better while higher transmission success is better.

## 7. Data model and interface contracts

Use typed schemas and validate each API boundary. Adapt names to the existing codebase if needed.

### SensorRecord
- `record_id`: unique ID
- `timestamp`: ISO-8601 timestamp
- `demo_patient_id`: synthetic ID only
- `record_type`: for example `heart_rate`, `ecg_summary`, `temperature`, `step_count`
- `value` and `unit`: synthetic measurement value and unit
- `sensitivity`: `HIGH` or `LOW`
- `classification_reason`: human-readable rule result
- `cluster_id`: sensitivity cluster

### EncryptedEnvelope
- `run_id`, `record_id`, `algorithm`, `sensitivity`, `cluster_id`
- `nonce` and authentication tag fields as required by the AES-GCM library
- `ciphertext`, `payload_bytes`, `created_at`
- integrity metadata for the experimental XOR route, if enabled
- Never include secret keys in the envelope.

### BenchmarkRun
- `run_id`, `mode` (`baseline` or `adaptive`), `seed`, `record_count`, `repeat_index`
- `measurement_source` (`hardware`, `imported`, `estimated`, `simulated`)
- encryption mean/median/p95, end-to-end duration, sent/received/rejected/timed-out counts
- TSR, PLR, bytes sent, average voltage/current/power, energy total, energy per record
- battery-capacity assumptions and runtime estimate if relevant
- `started_at`, `completed_at`, status, errors, application version

### Suggested endpoint boundaries

Use equivalent endpoints if an existing framework already provides them:
- `GET /api/health` — app and receiver status.
- `POST /api/demo/generate` — create a seeded synthetic batch.
- `POST /api/benchmark/run` — run baseline, adaptive, or comparison mode.
- `POST /api/benchmark/stop` — request cancellation safely.
- `GET /api/benchmark/{run_id}` — run status and results.
- `GET /api/metrics/compare?baseline_id=...&adaptive_id=...` — comparison values.
- `POST /api/power/import` — validate and import power samples.
- `GET /api/runs` and `GET /api/runs/{run_id}` — local run summaries.
- `GET /api/runs/{run_id}/export.csv` and `/export.json` — export results.

Do not make the API asynchronous or distributed unless required by the current project. Keep it simple and predictable for the review demo.

## 8. Dashboard layout

### A. Overview / Live demo
- One clear pipeline view.
- Synthetic batch controls and record count.
- Count of high/low records and clusters.
- Per-algorithm route counts.
- Current step and progress for a running demo.
- Receiver status and accepted/rejected/lost counts.

### B. Battery & performance
- Baseline vs adaptive comparison.
- Encryption time and end-to-end time shown separately.
- Energy per batch, energy per record, mean current/power, and battery runtime estimate if inputs exist.
- A persistent measurement-source banner.
- Trial count and spread/uncertainty.
- Clear statement if energy values are simulated or estimated.

### C. Record trace
- Filterable synthetic records showing classification reason, cluster, encryption route, timing, and receiver result.
- Mask or omit fields that are not needed for the demo.

### D. Security and configuration
- AES-256-GCM details and nonce/tag verification status.
- Explain that XOR is an experimental lightweight comparison and must not be presented as secure on its own.
- Classification rules, batch size, repeats, battery capacity, and any model assumptions.

### E. Results and export
- Paired-run table and charts.
- Downloadable CSV/JSON.
- Automatically generated plain-language explanation that only describes measured values.

## 9. Execution phases and completion gates

Antigravity must work in the phases below. Do not implement everything at once and do not move to the next phase until the current gate passes.

### Phase 0 — Inspect and protect
1. Inspect all project files, README, framework, dependency files, and existing tests.
2. Identify the actual run commands and current state. Do not assume a blank repository.
3. Write a short implementation plan mapping existing code to the requirements in this document.
4. Preserve existing working features. Do not delete or rewrite files wholesale just to make the structure match this plan.
5. Identify whether actual IoT hardware or power sensors are available. If unknown, implement the no-hardware path first.

**Gate:** The selected stack, existing features, planned changes, and known constraints are documented.

### Phase 1 — Core data pipeline
1. Implement seeded synthetic data generation.
2. Implement configurable sensitivity rules with a classification reason.
3. Implement deterministic high/low clustering.
4. Add schema validation and pipeline unit tests.

**Gate:** Same seed/configuration produces the same input workload and classification. Every record belongs to exactly one cluster.

### Phase 2 — Encryption and local receiver
1. Implement AES-256-GCM through a vetted library.
2. Implement the separate XOR comparison module with explicit warnings and optional HMAC integrity verification.
3. Implement envelope serialization and local receiver/decryption.
4. Implement tamper rejection and key configuration.

**Gate:** Valid records round-trip exactly. Modified AES ciphertext/tag fails verification. Reused AES-GCM nonces are prevented by the design. XOR limitations are visible in the application. No key appears in logs, UI, or exports.

### Phase 3 — Baseline benchmark engine
1. Implement all-AES baseline and adaptive routing.
2. Use a monotonic timer and separate encryption, serialization, receiver/network, and full-run timing.
3. Add repeatable paired tests and cancellation/timeouts.
4. Implement TSR/PLR/count formulas in a single metrics module.

**Gate:** Unit tests verify every formula and edge case, including zero records, zero received records, all records received, and rejected records. Identical workload is used for paired modes.

### Phase 4 — Battery subsystem
1. Define a power-measurement interface before integrating any board-specific driver.
2. Implement the documented CSV importer and validation.
3. Implement the simulation/estimate fallback with visible assumptions and provenance labels.
4. Integrate a live sensor only after the actual hardware and sensor are identified.
5. Compute energy from raw samples, compare paired runs, and estimate runtime only when the necessary inputs exist.

**Gate:** Tests verify unit conversions, integration, missing samples, invalid current/voltage, non-monotonic timestamps, unit mismatch, and source labelling. Simulation data can never be labelled hardware-measured.

### Phase 5 — Dashboard and exports
1. Build the overview, record trace, battery/performance, security/configuration, and results views.
2. Bind UI values to the actual backend run data; no fake hard-coded charts.
3. Handle loading, running, stopping, empty, disconnected, invalid-input, and failed-run states.
4. Add CSV/JSON exports and verify contents.

**Gate:** An evaluator can generate data, run both modes, see the receiver results, inspect the comparison, and export it without using developer tools or editing code.

### Phase 6 — End-to-end hardening
1. Run the unit and integration test suites.
2. Run a complete comparison repeatedly with the hardware-free mode.
3. Test receiver disconnect, malformed data, corrupt ciphertext, invalid CSV, missing sensor, cancelled run, and application restart.
4. Check that no secrets, keys, or unexpected personal data are persisted.
5. Confirm no measurement labels or success text exaggerate the evidence.
6. Check dashboard layout at the expected presentation screen size and at a narrow/mobile width.

**Gate:** All critical tests pass; remaining known issues and hardware limitations are listed in the README. No test result is reported as passing unless it was executed.

### Phase 7 — Final-review demo readiness
1. Add exact setup/run/stop/reset instructions.
2. Add a small known-good demo profile with a fixed seed, a manageable batch size, and repeat count.
3. Add a one-page demo script and an FAQ for likely panel questions.
4. Verify the app starts from a clean checkout using the documented commands.
5. Prepare an example result only from a real run of the app, and label the measurement mode.

**Gate:** A teammate unfamiliar with the code can start the demo by following the README. Demo must not depend on internet access unless a documented component explicitly requires it.

## 10. Required test matrix

- Synthetic generator is reproducible for a fixed seed.
- Every record receives one valid sensitivity label and explanation.
- Cluster counts add up to the total record count.
- High records route through AES-256-GCM in adaptive mode.
- Low records route through XOR in adaptive mode.
- Every record routes through AES-256-GCM in baseline mode.
- AES encryption/decryption round trip returns the original bytes.
- Wrong AES key, altered ciphertext, altered nonce, or altered tag is rejected.
- XOR path detects a changed payload when integrity verification is configured; UI still states XOR alone is not secure.
- Receiver reports received, rejected, timeout, and unreceived records separately.
- TSR and PLR formulas handle zero denominators safely and display `N/A` where undefined.
- Encryption timer excludes serialization and networking.
- Battery energy integration is correct for a known test signal.
- mA, A, V, W, mW, J, Wh, mWh, and mAh conversions are unit-tested where supported.
- CSV importer rejects absent columns, invalid units, invalid numbers, duplicate/out-of-order timestamps, and empty files with clear messages.
- No sensor connected → application still works and labels estimates correctly.
- Hardware readings are never overwritten by model-generated values without an explicit source change.
- Baseline/adaptive comparison uses equivalent data and records the actual repeat count.
- Export includes provenance, units, run IDs, and model assumptions and omits secrets.
- Stop/reset actions do not corrupt saved completed runs.
- Receiver unavailable → show an error but keep local encryption timing available where possible.
- UI never displays hard-coded performance/battery results as if they came from the current run.

## 11. Final-review demo sequence (about 5–7 minutes)

1. State the problem: a constrained IoT device has limited energy, and applying one encryption route to every record can add avoidable computation.
2. Generate a seeded synthetic healthcare batch and show each record's sensitivity reason and high/low cluster.
3. Run the all-AES baseline and wait for the receiver to verify the records.
4. Run the adaptive AES/XOR comparison on the equivalent batch.
5. Open the comparison page and explain encryption time, receiver success/loss/rejection, payload size, and energy-per-record metric.
6. Point to the measurement-source label. If using an instrument, identify the measured power boundary. If using estimates, state clearly that these are model estimates rather than physical battery readings.
7. Show the tamper demo: change an authenticated ciphertext/tag and show that verification rejects it.
8. Export the result and finish with the observed result, sample count, measurement type, and limitations. Claim reduced energy only if measured or explicitly modelled numbers support it, and state which kind of evidence was obtained.

## 12. Required project deliverables

- Working local application and source code.
- README with setup, run, test, hardware wiring/measurement instructions if applicable, and troubleshooting.
- Architecture/data-flow diagram.
- Functional and non-functional requirements traceability table.
- Unit/integration test results from tests actually executed.
- Seeded demo profile and repeatable baseline/adaptive benchmark.
- Battery methodology explaining measurement boundary, sample rate, formulas, model assumptions, and limitations.
- CSV and JSON benchmark exports.
- Final-review demo script and known-limitations section.

## 13. Definition of done

The project is ready only when a clean startup works; the full pipeline operates; adaptive and all-AES modes both run; verified receiver counts and performance metrics are displayed; battery results are clearly labelled as hardware-measured, imported, estimated, or simulated; baseline/adaptive experiments use equivalent workloads; exports work; security caveats are visible; and critical tests pass.

Do not stop after producing a visually attractive dashboard. The key deliverable is a working, repeatable demonstration supported by traceable measurements.

---

# Copy/paste execution instruction for Antigravity

You are implementing the final-review demo for **Cluster-Based Encryption for Privacy and Security in IoT Healthcare**. Treat this document as the product specification and acceptance checklist.

Start by inspecting the existing workspace and report its current structure, framework, run commands, tests, and any existing functionality. Preserve working code. Then implement the phases in order, stopping at each phase gate to run tests and fix failures before continuing. Use synthetic data only. Keep the demo local by default. Implement the all-AES-256-GCM baseline and the sensitivity-based AES-256-GCM/XOR comparison. Make the XOR limitations explicit in the UI and documentation. Implement battery-energy reporting with a real hardware/CSV measurement route and a separate clearly labelled estimate/simulation fallback. Never fabricate results or label estimated values as measured. Use the requirements, formulas, security rules, test matrix, and definition of done above as acceptance criteria.

Before finishing, execute the available tests and the complete demo workflow, record the actual commands and outcomes, list unimplemented items and hardware limitations, and update the README with clean-start instructions. Do not claim completion for a phase whose gate has not passed. Do not report a battery saving unless the app's captured baseline/adaptive results support that statement.
