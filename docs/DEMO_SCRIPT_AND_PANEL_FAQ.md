# Final-Review Demo Script & Panel Defense FAQ

## 1. Five-Minute Presentation Demo Script

### Step 1: Problem Statement & Background (1 Minute)
* **Presenter says:**
  > "Good morning, professors. Wearable medical devices—such as continuous ECG monitors and smart pulse patches—operate under severe energy constraints. Conventional systems apply uniform heavy encryption like AES-256 to every routine packet, which rapidly depletes the limited battery capacity of microcontrollers.
  > In this project, we evaluate **ClusterGuard: A Cluster-Based Sensitivity-Adaptive Encryption architecture**. We partition patient telemetry using an unsupervised machine-learning K-Means clustering pipeline backed by an immutable Clinical Safety Guardrail: critical diagnostic vitals route through NIST-compliant AES-256-GCM, while routine telemetry routes through an experimental lightweight comparison path."

### Step 2: Interactive 3-Button Faculty Demo Workflow — Stage 1: Data Generation (1 Minute)
* **Action in UI:** Open Tab 1 (*Overview & Live Demo*). Keep Batch Size = 50, Seed = 42. Click **1. Generate Synthetic Data**.
* **Presenter points to screen:**
  > "Notice what happens immediately upon clicking Button 1:
  > 1. Our deterministic generator produces 50 raw synthetic records across cardiac, thermal, and activity modalities with a globally unique `pipeline_run_id` (e.g. `PIPE-S42-XXXX`).
  > 2. The pristine raw telemetry table renders immediately. Notice that cluster IDs and security classes are strictly empty at this stage—no fabricated cluster data exists prior to running ML.
  > 3. The **Download Raw CSV** button is immediately enabled. We can click it to download the pure raw dataset (`record_id, timestamp, demo_patient_id, record_type, value, unit, is_synthetic, pipeline_run_id`).
  > 4. Generating a new batch automatically invalidates any downstream clustering or battery state to prevent stale data lineage."

### Step 3: Feature Engineering Inspection & Executable ML Model File (45 Seconds)
* **Action in UI:** Click the view switcher pill **View 2: Feature Engineering Matrix (Stage 2)**. Point to the ML Model Callout card.
* **Presenter points to screen:**
  > "Above the table, our **Executable ML Model Source File** callout prominently identifies `src/kmeans_clusterer.py`. This standalone, fully executable file contains our scikit-learn K-Means model, `StandardScaler`, modality-aware physical span normalization, and the `ClinicalSafetyGuardrail`.
  > On screen, our 6-dimensional feature vector table displays: 4 one-hot modality flags (Heart Rate, ECG, Temperature, Steps), modality-normalized values in $[0.0, 1.0]$, raw measurements, and baseline physiological range deviations. Notice the **Label Isolation** column: ground-truth clinical sensitivity labels are strictly excluded—zero target label leakage."

### Step 4: Run Machine Learning Clustering (Stage 3 & 4) (1 Minute)
* **Action in UI:** Click **2. Run ML Clustering**.
* **Presenter demonstrates:**
  > "Clicking Button 2 executes `sklearn.cluster.KMeans` ($K=2$, `random_state=42`, `n_init=10`, `algorithm="lloyd"`):
  > 1. The model derives semantic cluster mapping (`CLUSTER-HIGH` for elevated vitals, `CLUSTER-LOW` for routine data).
  > 2. The **Metadata Ribbon** updates with **Within-Run Rule Agreement** (~96.0%) and Silhouette Score (~0.347).
  > 3. Our **Clinical Safety Guardrail** activates: if any abnormal vital (such as an arrhythmia or fever) is clustered into a routine group, the guardrail immediately overrides it, forcing `effective_security_class = HIGH` (AES-256-GCM) with an immutable audit log.
  > 4. The **Download Clustered CSV** button is enabled, exporting cluster assignments, semantic tags, and guardrail override reasons."

### Step 5: Simulate Battery on Current Dataset (Stage 4 & Tab 2) (1 Minute)
* **Action in UI:** Click **3. Simulate Battery on Current Dataset**, then navigate to Tab 2 (*Battery Lab & Simulation*).
* **Presenter shows result:**
  > "Clicking Button 3 executes our physics-based MCU battery model on the **exact records, count, and effective security classes** of the dataset we just clustered:
  > 1. Guarded records that were upgraded by the safety guardrail are evaluated under NIST AES-256-GCM energy, ensuring realistic energy accounting.
  > 2. The table computes per-record energy ($E = V \times I \times t$) over non-overlapping CPU, crypto, radio, and sleep intervals ($3.3\,\text{V} \times 10\,\text{mA} \times 1\,\text{ms} = 0.033\,\text{mJ}$).
  > 3. Cumulative energy is tracked against our 1200 mAh Li-Po rail capacity (**12,117.60 Joules** usable rail energy), computing exact remaining battery percentages (e.g. 99.999998% per batch).
  > 4. In Tab 2, our dedicated **Per-Record Battery Simulation Table** displays all 50 simulated records, and we can download the full simulation log via **Download Battery Simulation CSV**."

### Step 6: Desktop Performance Honesty & Security Verification (45 Seconds)
* **Action in UI:** Return to Tab 1. Scroll down to **Interactive Tamper Rejection Verification**, select `AES-256-GCM`, Mutation Target `Ciphertext`, and click **Execute Tamper Test**.
* **Presenter concludes:**
  > "Flipping a single bit in the ciphertext causes the receiver to immediately reject the payload with `tampering detected`. The same occurs for the XOR path via HMAC-SHA-256.
  > On our host PC, the dashboard honestly reports `STATUS: REGRESSION` because x86 desktop CPUs feature hardware AES-NI instructions, whereas on target IoT MCUs (16 MHz Cortex-M0+), adaptive clustering saves ~48.8% CPU cycles and ~56.6% per-operation cryptographic energy. All 7 stages can be inspected and exported with zero key leakage. In conclusion, ClusterGuard provides an academically rigorous, transparent, and reproducible framework for evaluating IoT healthcare security."

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

### Q4: How is the 12,117.60 Joule battery capacity derived, and how does it relate to cell voltage?
> **Answer:** The capacity accounts for the physical boundary between the 1S Li-Po electrochemical cell and the regulated MCU rail:
> 1. **Cell Source Energy (3.7V Nominal):** A standard 1200 mAh Li-Po cell holds:
>    $$E_{\text{cell, total}} = 1.2\,\text{Ah} \times 3.7\,\text{V} \times 3600\,\text{s/h} = 15,984.00\,\text{Joules}$$
>    At an 85% safe Depth-of-Discharge (DoD) margin, usable cell energy is $15,984.00 \times 0.85 = 13,586.40\,\text{Joules}$.
> 2. **Delivered Rail Energy (3.3V Regulated):** Stepping down from 3.7V to 3.3V via an on-board linear low-dropout regulator (LDO) operates at efficiency $\eta = 3.3 / 3.7 \approx 89.19\%$:
>    $$E_{\text{rail, usable}} = 13,586.40\,\text{J} \times \left(\frac{3.3}{3.7}\right) = 1.2\,\text{Ah} \times 3.3\,\text{V} \times 3600 \times 0.85 = 12,117.60\,\text{Joules}$$
> All microcontroller current draws are measured/modeled at this 3.3V regulated rail boundary.

### Q5: How do you guarantee energy is not double-counted between CPU, crypto, and radio?
> **Answer:** We formulate the energy model over **strictly non-overlapping, mutually exclusive time intervals**:
> $$E_{\text{total}} = V_{\text{cc}} \left( I_{\text{proc}} t_{\text{proc}} + I_{\text{crypto}} t_{\text{crypto}} + I_{\text{tx}} t_{\text{tx}} + I_{\text{idle}} t_{\text{idle}} \right)$$
> On an edge microcontroller without an RTOS or multithreading, operations are sequential: the CPU processes data ($t_{\text{proc}}$), performs encryption ($t_{\text{crypto}}$), triggers the radio SPI/UART burst ($t_{\text{tx}}$), and enters low-power sleep ($t_{\text{idle}}$). Crypto energy is never stacked on top of an active baseline.

### Q6: Is XOR encryption acceptable for real healthcare data in production?
> **Answer:** **No, absolutely not.** XOR stream ciphers alone do not provide production-grade confidentiality. If an XOR keystream repeats or is predictable, plaintext recovery is trivial via many-time pad cryptanalysis.
> In ClusterGuard, the XOR route is implemented strictly as an **algorithmic lower-bound baseline** to evaluate the theoretical computational savings proposed in academic literature. The attached HMAC-SHA-256 provides message authentication only. Production devices must utilize authenticated AEAD ciphers (e.g., AES-256-GCM or ChaCha20-Poly1305).

### Q7: Why did your desktop test show that AES-256-GCM was faster than the lightweight route?
> **Answer:** Modern x86-64 desktop processors include **Intel/AMD AES-NI** hardware instructions. Python's `cryptography` library uses OpenSSL, which executes AES in dedicated silicon cycles. In contrast, the experimental XOR cipher is implemented in pure Python bytecode with HMAC-SHA-256 integrity verification, incurring interpreter loop overhead.
> On constrained edge microcontrollers lacking AES-NI hardware (such as ARM Cortex-M0+ @ 16 MHz, 3.3V), software AES-256 requires 20,000 clock cycles (1.25 ms at 9.8 mA = 0.040425 mJ), while the composite SHA+XOR+HMAC routine requires 10,240 clock cycles (0.64 ms at 8.31 mA avg = 0.0175461 mJ)—yielding a 48.8% CPU cycle saving and a 56.6% per-operation cryptographic energy saving for routine telemetry.

### Q8: Did you physically measure battery savings?
> **Answer:** We do not claim verified physical battery savings on this workstation. The UI explicitly displays the badge `SIMULATED / ESTIMATED — NOT A PHYSICAL BATTERY READING`.
> The `HardwareSerialPowerAdapter` class provides a defined interface (`INTERFACE_PLACEHOLDER_HARDWARE_PENDING`) that cleanly raises a `ConnectionError` directing users to CSV laboratory log imports when physical hardware is not attached.
> To validate real battery savings, the platform provides a **CSV Instrument Importer** (`/api/power/import`) and a numerical trapezoidal integration engine. A research team can connect a Monsoon Power Monitor or Otii Arc to an actual IoT microcontroller board, capture current waveforms, and import the log to integrate true physical energy.

### Q9: How does the system protect against replay attacks and nonce reuse?
> **Answer:** Reusing a nonce with the same key in AES-256-GCM is catastrophic (it leaks the authentication hash key). Our `AES256GCMService` generates a cryptographically fresh 96-bit (12-byte) pseudo-random nonce for every envelope using `secrets.token_bytes(12)` and tracks used nonces in memory to prevent reuse. The experimental path uses fresh 12-byte IVs with SHA-256 keystream expansion.

### Q10: How are secrets managed? Are keys exposed in logs or reports?
> **Answer:** Cryptographic keys are ephemeral development keys generated in memory at startup, or loaded securely from environment variables (`IOT_AES_KEY_HEX`, `IOT_XOR_KEY_HEX`, `IOT_HMAC_KEY_HEX`).
> The `KeyManager` explicitly redacts key bytes in `__repr__` and `__str__`. Automated security tests (`test_zero_secret_leakage_audit`) scan the SQLite database and exported CSV/JSON files to verify that zero secret keys are ever leaked.
