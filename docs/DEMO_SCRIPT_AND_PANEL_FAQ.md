# Final-Review Demo Script & Panel Defense FAQ

## 1. Five-Minute Presentation Demo Script

### Step 1: Problem Statement & Background (1 Minute)
* **Presenter says:**
  > "Constrained IoT healthcare devices—such as battery-powered ECG monitors and wearable pulse sensors—operate under severe energy constraints. Conventional systems apply uniform heavy encryption like AES-256 to every routine packet, which can deplete battery life on resource-constrained microcontrollers.
  > In this project, we evaluate a **Cluster-Based Sensitivity-Adaptive Encryption architecture**. We partition patient telemetry by privacy sensitivity: high-risk diagnostic data uses NIST-compliant AES-256-GCM, while routine telemetry is routed to an experimental lightweight comparison path."

### Step 2: Synthetic Data Generation & Sensitivity Clustering (1 Minute)
* **Action in UI:** Open Tab 1 (*Overview & Live Demo*). Keep Batch Size = 50, Seed = 42. Click **Generate Synthetic Data**.
* **Presenter points to screen:**
  > "Here, our deterministic data generator produces 50 synthetic records representing cardiac and vitals telemetry: Heart Rate, ECG waveforms, Temperature, and Step Cadence.
  > Notice the automatic classification:
  > - Abnormal vitals (e.g. Heart Rate > 100 bpm or < 50 bpm, fever, and ECG summaries) are classified as **HIGH** sensitivity and assigned to `CLUSTER-HIGH`.
  > - Normal vital signs and routine step counts are classified as **LOW** sensitivity and assigned to `CLUSTER-LOW`.
  > Every record carries an explicit, deterministic rule explanation."

### Step 3: Paired Benchmark Execution (1.5 Minutes)
* **Action in UI:** Click **Run Both / Compare**.
* **Presenter explains:**
  > "The benchmark executes two paired runs under identical workload conditions:
  > 1. **Baseline Mode:** Encrypts 100% of records with AES-256-GCM.
  > 2. **Adaptive Mode:** High-sensitivity records use AES-256-GCM; routine records use experimental XOR.
  > Both batches are transmitted to our local healthcare receiver endpoint, which decrypts and verifies the cryptographic tags."

### Step 4: Battery & Performance Analysis (1 Minute)
* **Action in UI:** Navigate to Tab 2 (*Battery & Performance*). Point directly to the prominent yellow banner: `SIMULATED / ESTIMATED — NOT A PHYSICAL BATTERY READING`.
* **Presenter states with scientific honesty:**
  > "Notice first our persistent **Measurement Source Banner**. Because this laptop demo is running without an attached hardware power analyzer or physical current sensor, we state plainly that these energy values are model-based software estimates rather than physical battery measurements.
  > When we examine encryption latency: on our laptop, AES-256-GCM benefits from x86 AES-NI hardware CPU acceleration, while interpreted Python loops show how software overhead behaves. If physical instrument logs are available, our CSV importer can ingest calibrated data from a Monsoon or Keysight meter for true physical energy integration."

### Step 5: Live Tamper Rejection Verification (45 Seconds)
* **Action in UI:** Scroll to the **Interactive Tamper Rejection Verification** box. Select `AES-256-GCM`, Mutation Target `Ciphertext`, and click **Execute Tamper Test**.
* **Presenter shows result:**
  > "To verify security integrity: here we flip a single bit in the ciphertext. The local receiver immediately catches the tag mismatch and rejects the packet with `tampering detected`.
  > We can repeat the test on the XOR route with HMAC-SHA-256: any tampering is immediately dropped, preventing corrupted medical data from polluting electronic health records."

### Step 6: Export & Conclusion (30 Seconds)
* **Action in UI:** Navigate to Tab 5 (*Run History & Exports*). Click **CSV** and **JSON** export buttons.
* **Presenter concludes:**
  > "The benchmark records are exported to standard CSV and JSON formats containing complete metadata, timing percentiles, and model assumptions, with zero secret key leakage. In conclusion, our system provides an honest, repeatable framework for evaluating IoT encryption trade-offs."

---

## 2. Review Panel Defense FAQ

### Q1: Is XOR encryption acceptable for real healthcare data in production?
> **Answer:** **No, absolutely not.** XOR stream ciphers alone do not provide production-grade confidentiality. If an XOR mask is reused or predictable, plaintext recovery attacks (such as many-time pad cryptanalysis) are trivial.
> In our project, the XOR route is preserved strictly as an **experimental lightweight comparison path** to evaluate the theoretical lower-bound computational trade-off proposed in the review slides. For real clinical IoT deployments, authenticated AEAD ciphers like AES-256-GCM or ChaCha20-Poly1305 must be employed, potentially tuned with optimized hardware crypto co-processors.

### Q2: Why did your laptop test show that AES-256-GCM had lower encryption latency than the experimental XOR route?
> **Answer:** This is a crucial finding highlighting the difference between desktop CPUs and microcontroller environments:
> 1. Modern x86-64 desktop processors include **Intel/AMD AES-NI** hardware instructions. The Python `cryptography` library uses OpenSSL, which executes AES in native C with hardware-level parallelism.
> 2. The experimental XOR cipher is implemented in pure Python bytecode with HMAC-SHA-256 integrity verification, which incurs interpreter loop overhead.
> 3. On constrained 8-bit or 16-bit IoT microcontrollers (e.g. AVR ATmega or low-power Cortex-M0) lacking AES-NI hardware, AES software routines require thousands of CPU cycles, whereas bitwise XOR takes a single clock cycle. Our platform honestly reports the measured values without falsification.

### Q3: Did you physically save battery life?
> **Answer:** We do not claim verified physical battery savings on this workstation. Our user interface and exports explicitly display the label `SIMULATED / ESTIMATED — NOT A PHYSICAL BATTERY READING`.
> To validate real battery savings, the system includes a dedicated **CSV Instrument Importer** and a modular **Hardware Power Adapter interface**. A research team can connect a Monsoon Power Monitor or Otii Arc to an actual IoT sensor board, capture current waveforms, and import the log to integrate true physical energy.

### Q4: How does the system protect against replay attacks and nonce reuse?
> **Answer:** In AES-256-GCM, reusing a nonce with the same key is catastrophic (it leaks the authentication hash key). Our `AES256GCMService` generates a cryptographically fresh 96-bit (12-byte) pseudo-random nonce for every envelope using `secrets.token_bytes(12)` and tracks used nonces in memory to prevent reuse. The experimental XOR path uses fresh 12-byte IVs combined with SHA-256 keystream expansion.

### Q5: How are secrets managed? Are keys exposed in logs or reports?
> **Answer:** Cryptographic keys are ephemeral development keys generated in memory at startup, or loaded securely from environment variables (`IOT_AES_KEY_HEX`, `IOT_XOR_KEY_HEX`, `IOT_HMAC_KEY_HEX`).
> The `KeyManager` explicitly redacts key bytes in `__repr__` and `__str__`. Our automated security tests (`test_zero_secret_leakage_audit`) scan the SQLite database and exported CSV/JSON files to verify that zero secret keys are ever leaked.
