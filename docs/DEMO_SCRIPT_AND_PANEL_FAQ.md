# Final-Review Demo Script & Panel Defense FAQ

## 1. Five-Minute Presentation Demo Script

### Step 1: Problem Statement & Background (1 Minute)
* **Presenter says:**
  > "Good morning, professors. Wearable medical devices—such as continuous ECG monitors and smart pulse patches—operate under severe energy constraints. Conventional systems apply uniform heavy encryption like AES-256 to every routine packet, which rapidly depletes the limited battery capacity of microcontrollers.
  > In this project, we evaluate **ClusterGuard: A Cluster-Based Sensitivity-Adaptive Encryption architecture**. We partition patient telemetry using an unsupervised machine-learning K-Means clustering pipeline backed by an immutable Clinical Safety Guardrail: critical diagnostic vitals route through NIST-compliant AES-256-GCM, while routine telemetry routes through an experimental lightweight comparison path."

### Step 2: Synthetic Data Generation, ML Feature Extraction & K-Means Clustering (1.5 Minutes)
* **Action in UI:** Open Tab 1 (*Overview & Live Demo*). Keep Batch Size = 50, Seed = 42. Click **Generate Synthetic Data**.
* **Presenter points to screen:**
  > "Notice what happens automatically:
  > 1. Our deterministic generator produces 50 synthetic records across cardiac, thermal, and activity modalities with a globally unique `pipeline_run_id`.
  > 2. Our `HealthcareFeatureExtractor` constructs a 6-dimensional normalized feature vector per record with zero label leakage—ground-truth sensitivity is never exposed to the ML algorithm.
  > 3. `sklearn.cluster.KMeans` automatically clusters the records into `CLUSTER-HIGH` and `CLUSTER-LOW` with ~96% agreement against clinical thresholds.
  > 4. Notice the **Metadata Ribbon** and our **Clinical Safety Guardrail**: if an abnormal reading—such as an arrhythmia or fever—is clustered into a routine group, our safety guardrail immediately intervenes, forcing `effective_security_class = HIGH` (AES-256-GCM) with an immutable audit log.
  > 5. Down below, our **Synthetic Healthcare Dataset & Provenance Lineage** table displays all 11 columns: Record ID, Modality, Raw Measurement, Timestamps, Policy Sensitivity, ML Cluster, Guardrail Overrides, and Nonce/Tag previews. We can search, filter by modality or security class, and download full CSV/JSON artifacts for all 7 stages."

### Step 3: Interactive Pipeline Drawer Inspection (45 Seconds)
* **Action in UI:** Click on **Step 02 (Feature Engineering)** and **Step 03 (ML Clustering)** in the 7-Stage Pipeline strip.
* **Presenter demonstrates:**
  > "Clicking any stage opens our slide-out **Stage Inspection Drawer**. Here we can inspect the exact intermediate dataset: for Stage 02, we view the 6D normalized feature vectors; for Stage 03, we inspect K-Means diagnostics including silhouette score, inertia, iterations to converge, and cluster centroids."

### Step 4: Paired Benchmark Execution & Desktop Regression Analysis (1 Minute)
* **Action in UI:** Click **Run Both / Compare**.
* **Presenter explains:**
  > "The benchmark executes two paired runs under identical workload conditions:
  > 1. **Baseline Mode:** Encrypts 100% of records with authenticated AES-256-GCM.
  > 2. **Adaptive Mode:** High-sensitivity records use AES-256-GCM; routine records use the lightweight XOR path.
  > Look at the latency metric on this laptop: our dashboard honestly reports `STATUS: REGRESSION`. Why? Because modern x86 desktop processors have silicon-level **AES-NI instructions** that execute AES at hardware speeds via OpenSSL in C, whereas the experimental XOR/HMAC cipher runs in Python bytecode. We do not falsify desktop results to pretend there is a saving on a PC."

### Step 5: Battery Lab & Sub-Panel G Evidence Audit (45 Seconds)
* **Action in UI:** Navigate to Tab 2 (*Comparison & Battery Lab*). Switch scenario to **Constrained IoT Microcontroller (Simulated Target MCU)**. Select **Compute-Intensive / Short-TX** preset. Scroll down to **Sub-Panel G**.
* **Presenter shows result:**
  > "In an IoT microcontroller lacking AES-NI (e.g. ARM Cortex-M0+ @ 16 MHz), software AES takes ~20,000 cycles, while lightweight XOR takes ~10,000 cycles.
  > Under **Sub-Panel G**, we provide our 3-tier evidence hierarchy and authoritative battery math:
  > - A 1200 mAh Li-Po cell at 3.3V with 85% usable depth-of-discharge provides exactly **12,117.60 Joules**.
  > - Energy is calculated strictly over **non-overlapping, mutually exclusive activity intervals**: $3.3\,\text{V} \times 10\,\text{mA} \times 1\,\text{ms} = 0.033\,\text{mJ}$.
  > - With short radio airtime (0.5 ms), adaptive encryption predicts **~12.9% batch energy savings**."

### Step 6: Security Verification & Conclusion (30 Seconds)
* **Action in UI:** Navigate to Tab 1, scroll to **Interactive Tamper Rejection Verification**, select `AES-256-GCM`, Mutation Target `Ciphertext`, and click **Execute Tamper Test**.
* **Presenter concludes:**
  > "Flipping a single bit in the ciphertext causes the receiver to immediately reject the payload with `tampering detected`. The same occurs for the XOR path via HMAC-SHA-256. All run history is persisted to SQLite and exportable to CSV and JSON with zero secret key leakage. In conclusion, ClusterGuard provides an academically defensible, transparent, and reproducible framework for evaluating IoT healthcare security."

---

## 2. Review Panel Defense FAQ

### Q1: Why did you use Machine Learning (K-Means) instead of simple if/else rules?
> **Answer:** Simple threshold rules evaluate scalar parameters in isolation. In continuous wearable telemetry, vital signs are multidimensional and contextual: a high heart rate during vigorous exercise is normal, whereas the same heart rate combined with low movement and high body temperature indicates physiological distress.
> Our `HealthcareFeatureExtractor` constructs a 6-dimensional normalized feature vector incorporating sensor modality one-hot encodings, absolute values, and baseline physiological deviations. `sklearn.cluster.KMeans` groups vitals into natural geometric clusters based on multivariate similarity.

### Q2: What happens if K-Means makes a mistake and clusters an abnormal vital sign into the routine cluster?
> **Answer:** The **Clinical Safety Guardrail** prevents any downgrade. In clinical engineering, unsupervised ML cannot be given unchecked authority over patient safety.
> If a record's deterministic clinical rule classifies it as `HIGH` sensitivity, our safety guardrail enforces `effective_security_class = HIGH` (AES-256-GCM), overriding the ML assignment and recording `override_reason = "SAFETY_GUARDRAIL_APPLIED: Clinical policy takes precedence over ML clustering"`. Critical diagnostic telemetry can never be downgraded to lightweight security.

### Q3: Does your feature vector suffer from data leakage?
> **Answer:** **No, absolutely not.** Target leakage occurs when the target variable or its direct derivatives are included in the feature set.
> Our feature extractor strictly takes only raw physiological values (`sensor_type`, `measurement`, `unit`) and calculates baseline deviations from population medical norms. The sensitivity label (`sensitivity` or `policy_sensitivity`) is strictly excluded. This is verified by automated unit tests (`test_feature_extractor_no_label_leakage`).

### Q4: How is the 12,117.60 Joule battery capacity derived?
> **Answer:** The capacity is derived from basic electrical engineering principles:
> $$\text{Energy} = C_{\text{nominal}} \times k_{\text{usable}} \times V_{\text{rail}} \times 3.6$$
> - $1200\,\text{mAh}$: Standard rechargeable 1S lithium-polymer pouch cell.
> - $3.3\,\text{V}$: Regulated microcontroller rail voltage.
> - $3.6$: Conversion constant ($1\,\text{mAh} \times 1\,\text{V} = 3.6\,\text{Joules}$).
> - $0.85$ ($85\%$): Usable capacity factor enforcing a standard Depth-of-Discharge (DoD) margin to prevent irreversible lithium cell damage.
> $$1200 \times 0.85 \times 3.3 \times 3.6 = 12,117.60\,\text{Joules}$$

### Q5: How do you guarantee energy is not double-counted between CPU, crypto, and radio?
> **Answer:** We formulate the energy model over **strictly non-overlapping, mutually exclusive time intervals**:
> $$E_{\text{total}} = V_{\text{cc}} \left( I_{\text{proc}} t_{\text{proc}} + I_{\text{crypto}} t_{\text{crypto}} + I_{\text{tx}} t_{\text{tx}} + I_{\text{idle}} t_{\text{idle}} \right)$$
> On an edge microcontroller without an RTOS or multithreading, operations are sequential: the CPU processes data ($t_{\text{proc}}$), performs encryption ($t_{\text{crypto}}$), triggers the radio SPI/UART burst ($t_{\text{tx}}$), and enters low-power sleep ($t_{\text{idle}}$). Crypto energy is never stacked on top of an active baseline.

### Q6: Is XOR encryption acceptable for real healthcare data in production?
> **Answer:** **No, absolutely not.** XOR stream ciphers alone do not provide production-grade confidentiality. If an XOR keystream repeats or is predictable, plaintext recovery is trivial via many-time pad cryptanalysis.
> In ClusterGuard, the XOR route is implemented strictly as an **algorithmic lower-bound baseline** to evaluate the theoretical computational savings proposed in academic literature. The attached HMAC-SHA-256 provides message authentication only. Production devices must utilize authenticated AEAD ciphers (e.g., AES-256-GCM or ChaCha20-Poly1305).

### Q7: Why did your desktop test show that AES-256-GCM was faster than the lightweight route?
> **Answer:** Modern x86-64 desktop processors include **Intel/AMD AES-NI** hardware instructions. Python's `cryptography` library uses OpenSSL, which executes AES in dedicated silicon cycles. In contrast, the experimental XOR cipher is implemented in pure Python bytecode with HMAC-SHA-256 integrity verification, incurring interpreter loop overhead. On constrained edge microcontrollers lacking AES-NI hardware (such as ARM Cortex-M0+), software AES requires ~20,000 clock cycles, while bitwise XOR requires ~160 cycles.

### Q8: Did you physically measure battery savings?
> **Answer:** We do not claim verified physical battery savings on this workstation. The UI explicitly displays the badge `SIMULATED / ESTIMATED — NOT A PHYSICAL BATTERY READING`.
> To validate real battery savings, the platform provides a **CSV Instrument Importer** and a modular **Hardware Power Adapter interface**. A research team can connect a Monsoon Power Monitor or Otii Arc to an actual IoT microcontroller board, capture current waveforms, and import the log to integrate true physical energy.

### Q9: How does the system protect against replay attacks and nonce reuse?
> **Answer:** Reusing a nonce with the same key in AES-256-GCM is catastrophic (it leaks the authentication hash key). Our `AES256GCMService` generates a cryptographically fresh 96-bit (12-byte) pseudo-random nonce for every envelope using `secrets.token_bytes(12)` and tracks used nonces in memory to prevent reuse. The experimental path uses fresh 12-byte IVs with SHA-256 keystream expansion.

### Q10: How are secrets managed? Are keys exposed in logs or reports?
> **Answer:** Cryptographic keys are ephemeral development keys generated in memory at startup, or loaded securely from environment variables (`IOT_AES_KEY_HEX`, `IOT_XOR_KEY_HEX`, `IOT_HMAC_KEY_HEX`).
> The `KeyManager` explicitly redacts key bytes in `__repr__` and `__str__`. Automated security tests (`test_zero_secret_leakage_audit`) scan the SQLite database and exported CSV/JSON files to verify that zero secret keys are ever leaked.
