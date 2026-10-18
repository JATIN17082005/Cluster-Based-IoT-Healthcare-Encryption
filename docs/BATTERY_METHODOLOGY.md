# Battery and Energy Measurement Methodology (Phase 8 Validated)

## 1. Overview and Core Philosophy

In research and academic reviews concerning IoT healthcare telemetry, energy-efficiency claims must be backed by verifiable, reproducible measurement protocols. 

The Cluster-Based IoT Healthcare Encryption system strictly separates empirical laboratory measurements from software-modeled estimates:
1. **Mode A — Software Estimate (`estimated`):** Mathematical energy estimation calculated from high-resolution monotonic code execution timings combined with documented, configurable voltage and current parameters for each hardware operating state.
2. **Mode B — Physical Power Measurement (`imported` / `hardware`):** Physical laboratory instrument readings (such as Monsoon Power Monitor, Otii Arc, Keysight N6705, or calibrated INA219/INA226 current sense boards) imported via time-series CSV logs or captured via hardware serial port.

> [!IMPORTANT]
> When physical sensors are not attached, the dashboard, API, and exported data display an unmistakable provenance banner:
> `SIMULATED / ESTIMATED — NOT A PHYSICAL BATTERY READING`.
> Simulated values are never represented to a review panel as empirical battery savings.

---

## 2. Measurement Boundary & Software vs Whole-Device Scope

When reporting power consumption, the device boundary must be explicitly identified:
- **Whole-Device Supply Boundary (Board VCC to GND):** Measures total microcontroller, crystal oscillator, peripheral, and radio power consumption.
- **Laptop / USB Host Boundary:** USB inline meters measure the host port, hub, USB-to-UART bridge, and converter losses—not the IoT microcontroller alone.
- **Encryption-Stage / Software Scope:** Execution timing of encryption operations alone does NOT represent whole-device battery consumption. If radio or whole-device physical measurements are unavailable, the metrics are explicitly labeled as **software-model energy** or **encryption-stage energy**.

---

## 3. Authoritative Mathematical Formulas

All comparisons across the dashboard, API, CSV exports, and JSON summaries are derived using the unrounded raw values using these authoritative functions defined in `src/metrics.py`:

### A. Percentage Change (Latency, Throughput, Current)
$$\text{Percentage change} = \left(\frac{\text{Proposed} - \text{Baseline}}{\text{Baseline}}\right) \times 100$$
- **Positive percentage change ($+$):** Indicates an **increase**.
- **Negative percentage change ($-$) :** Indicates a **reduction**.

### B. Percentage Energy Saving
$$\text{Percentage energy saving} = \left(\frac{\text{Baseline Energy} - \text{Proposed Energy}}{\text{Baseline Energy}}\right) \times 100$$
- **Positive percentage saving ($+$):** Indicates an energy **saving / reduction** (favorable).
- **Negative percentage saving ($-$) :** Indicates **extra consumption / regression** (unfavorable).

### C. Result Status Classification
Results are categorized into three definitive states:
- **`IMPROVEMENT`**: Desired metric direction verified beyond noise margin ($> 0.2\%$).
- **`REGRESSION`**: Metric deteriorated beyond noise margin ($> 0.2\%$).
- **`INCONCLUSIVE`**: Change within measurement noise margin ($\le 0.2\%$).

---

## 4. Mode A — Software Estimation Model

### Model Formulation
Software estimation computes energy over isolated execution stages:
$$E_{\text{batch}} = V_{\text{cc}} \times \left( \sum_{\text{record} \in \text{AES}} I_{\text{aes}} \cdot t_{\text{aes}} + \sum_{\text{record} \in \text{XOR}} I_{\text{xor}} \cdot t_{\text{xor}} + \sum_{\text{all}} I_{\text{tx}} \cdot t_{\text{tx}} \right)$$

### Default Model Parameters (Configurable via UI)
| Parameter | Default Value | Technical Rationale & State Description |
|---|---|---|
| Supply Voltage ($V_{\text{cc}}$) | $3.3\,\text{V}$ | Regulated low-power microcontroller rail (e.g., nRF52840 / STM32WB) |
| MCU Baseline Current ($I_{\text{mcu}}$) | $35.0\,\text{mA}$ | Active core processing baseline current at $64\,\text{MHz}$ |
| AES-256-GCM Current ($I_{\text{aes}}$) | $54.0\,\text{mA}$ | Hardware cryptographic coprocessor active current |
| XOR Stream Current ($I_{\text{xor}}$) | $22.0\,\text{mA}$ | Lightweight bitwise transformation current |
| TX Radio Burst Current ($I_{\text{tx}}$) | $85.0\,\text{mA}$ | BLE / IEEE 802.15.4 PA active transmit burst at $+4\,\text{dBm}$ |
| TX Duration per Record ($t_{\text{tx}}$) | $1.8\,\text{ms}$ | Over-the-air packet transmission window |
| Battery Capacity | $1200\,\text{mAh}$ | Standard rechargeable Li-Po 1S pouch cell |
| Usable Capacity Factor | $0.85$ ($85\%$) | Depth-of-Discharge (DoD) safe cutoff margin |

### Limitations of Mode A
- Does not account for dynamic thermal throttling or operating voltage drop curves.
- Assumes square-wave current transitions without capacitive inrush spikes.
- Reflects software model assumptions rather than physical electrochemical cells.

> [!NOTE]
> **Separation of Power Configurations:**
> The parameters above belong to `PowerModelConfig` (used by `SimulationPowerProvider` to model a high-clock $64\,\text{MHz}$ wireless SoC with dedicated hardware crypto coprocessors).
> In contrast, the constrained microcontroller model (Scenario B, detailed in Section 7) uses `McuHardwareScenarioConfig` representing a low-power $16\,\text{MHz}$ CPU (ARM Cortex-M0+ / AVR) without hardware cryptographic acceleration, with microampere sleep modes ($15\,\mu\text{A}$) and non-overlapping execution intervals.

---

## 5. Mode B — Physical Power Measurement & Lab CSV Integration

### Physical Integration Formula
Given $N$ discrete laboratory instrument samples $[(t_0, V_0, I_0), (t_1, V_1, I_1), \dots, (t_N, V_N, I_N)]$ with timestamps in milliseconds, voltage in Volts, and current in milliamperes:

1. **Instantaneous Power:**
   $$P_k = V_k \times \left(\frac{I_k}{1000}\right) \quad (\text{Watts})$$

2. **Numerical Energy Integration (Trapezoidal Rule):**
   $$E_{\text{total}} = \sum_{k=0}^{N-2} \frac{P_k + P_{k+1}}{2} \times \left(\frac{t_{k+1} - t_k}{1000}\right) \quad (\text{Joules})$$

3. **Observation Interval:**
   $$\Delta T = \frac{t_{N-1} - t_0}{1000} \quad (\text{seconds})$$

4. **Estimated Charge Consumed:**
   $$Q = I_{\text{mean}} \times \left(\frac{\Delta T}{3600}\right) \quad (\text{mAh})$$

5. **Normalized Energy per 1,000 Records:**
   $$E_{1000} = \left(\frac{E_{\text{total}}}{\text{Records Sent}}\right) \times 1000 \times 1000 \quad (\text{mJ / 1,000 records})$$

### Validation & Rejection Criteria
External power CSV uploads (`/api/power/import`) enforce strict validation:
- Missing headers (`timestamp_ms`, `voltage_v`, `current_ma`) $\rightarrow$ Rejected with `400 Bad Request`.
- Non-monotonic timestamps ($t_{k+1} < t_k$) $\rightarrow$ Rejected with row anomaly error.
- Negative voltage or current values $\rightarrow$ Rejected.
- Non-numerical or corrupted values $\rightarrow$ Rejected.
- Empty files or headers-only files $\rightarrow$ Rejected.

---

## 6. Battery Capacity & Voltage Reconciliation (Cell vs Regulated Rail)

In embedded IoT telemetry nodes, current measurements and power calculations occur across distinct voltage domains that must not be conflated:

### A. 1S Li-Po Electrochemical Cell (Supply Source)
- **Nominal Cell Voltage ($V_{\text{cell}}$):** $3.7\,\text{V}$ (standard Lithium-ion / Lithium-Polymer nominal open-circuit voltage).
- **Nominal Capacity ($C_{\text{nom}}$):** $1200\,\text{mAh} = 1.2\,\text{Ah}$.
- **Total Electrochemical Cell Energy:**
  $$E_{\text{cell, total}} = 1.2\,\text{Ah} \times 3.7\,\text{V} \times 3600\,\text{s/h} = 15,984.00\,\text{J}$$
- **Usable Electrochemical Cell Energy ($85\%$ Depth of Discharge):**
  $$E_{\text{cell, usable}} = 15,984.00\,\text{J} \times 0.85 = 13,586.40\,\text{J}$$

### B. Microcontroller Regulated Rail (Measurement Boundary)
- **Regulated Supply Rail ($V_{\text{rail}}$):** $3.3\,\text{V}$ (stepped down from $3.7\,\text{V}$ via on-board low-dropout linear regulator, LDO).
- **Measurement Boundary:** All microcontroller active, cryptographic, and radio currents ($I_{\text{active}}, I_{\text{crypto}}, I_{\text{tx}}, I_{\text{sleep}}$) are measured or modeled at this **$3.3\,\text{V}$ regulated rail boundary**.
- **Linear LDO Step-Down Efficiency:**
  $$\eta_{\text{LDO}} = \frac{V_{\text{rail}}}{V_{\text{cell}}} = \frac{3.3\,\text{V}}{3.7\,\text{V}} \approx 89.189\% \quad (\approx 89.2\%)$$
- **Usable Energy Delivered to the $3.3\,\text{V}$ Rail:**
  $$E_{\text{rail, usable}} = 13,586.40\,\text{J} \times \eta_{\text{LDO}} = 1.2\,\text{Ah} \times 3.3\,\text{V} \times 3600\,\text{s/h} \times 0.85 = 12,117.60\,\text{J}$$

This rigorous mathematical relationship reconciles why the dashboard reports $12,117.60\,\text{J}$ usable energy for the $3.3\,\text{V}$ operating rail alongside the $13,586.40\,\text{J}$ usable energy of the $3.7\,\text{V}$ cell.

---

## 7. Execution Time and CPU Cycle Accounting at 16 MHz

The embedded microcontroller model targets an edge processor running at $16\,\text{MHz}$ (ARM Cortex-M0+ or 8-bit AVR architecture) without hardware AES coprocessor instructions.
At $16\,\text{MHz}$, clock cycles convert directly to time:
$$\text{Cycles} = \text{Duration (ms)} \times 16,000 \quad \left(1\,\text{ms} = 16,000\,\text{clock cycles}\right)$$

### Cryptographic Stage Comparison per Record:

The active microcontroller configuration (`McuHardwareScenarioConfig`) models a 3.3V rail and 16 MHz clock with the following non-overlapping stages:

| Operation | Stage / Algorithm | Duration ($t$) | Current ($I$) | Cycles @ $16\,\text{MHz}$ | Energy ($V_{\text{rail}} \cdot I \cdot t$) |
|---|---|---|---|---|---|
| **Baseline High/Routine** | Software AES-256-GCM | $1.250\,\text{ms}$ | $9.8\,\text{mA}$ | $20,000$ | $0.040425\,\text{mJ}$ |
| **Adaptive High-Sensitivity** | Software AES-256-GCM | $1.250\,\text{ms}$ | $9.8\,\text{mA}$ | $20,000$ | $0.040425\,\text{mJ}$ |
| **Adaptive Routine (SHA-256)** | SHA-256 block keystream | $0.250\,\text{ms}$ | $8.2\,\text{mA}$ | $4,000$ | $0.006765\,\text{mJ}$ |
| **Adaptive Routine (XOR)** | Streaming bitwise XOR | $0.010\,\text{ms}$ | $7.5\,\text{mA}$ | $160$ | $0.0002475\,\text{mJ}$ |
| **Adaptive Routine (HMAC)** | HMAC-SHA256 Auth Tag | $0.380\,\text{ms}$ | $8.4\,\text{mA}$ | $6,080$ | $0.0105336\,\text{mJ}$ |
| **Adaptive Routine Composite** | SHA + XOR + HMAC | **$0.640\,\text{ms}$** | **$8.31\,\text{mA}$ avg** | **$10,240$** | **$0.0175461\,\text{mJ}$** |

In addition, each record undergoes shared sensor preprocessing:
- **Sensor Preprocessing ($t_{\text{proc}}$):** $0.350\,\text{ms}$ ($5,600$ cycles) at $8.5\,\text{mA}$ ($0.0098175\,\text{mJ}$).

### Computational Efficiency Gain (Per Routine Operation):
For routine telemetry records, transitioning from software AES-256 to the composite SHA-256 + XOR + HMAC route yields:
$$\Delta \text{Cycles} = \frac{20,000 - 10,240}{20,000} \times 100\% = 48.80\% \text{ reduction in cryptographic CPU cycles}$$
$$\Delta t_{\text{crypto}} = \frac{1.250\,\text{ms} - 0.640\,\text{ms}}{1.250\,\text{ms}} \times 100\% = 48.80\% \text{ reduction in cryptographic execution time}$$
$$\Delta E_{\text{crypto}} = \frac{0.040425\,\text{mJ} - 0.0175461\,\text{mJ}}{0.040425\,\text{mJ}} \times 100\% = 56.60\% \text{ reduction in per-operation cryptographic energy}$$

### Separation of Per-Operation Cryptographic Energy and Total-Batch Energy

It is academically and practically vital to distinguish isolated per-operation cryptographic savings from total whole-device battery savings:

1. **Per-Operation Cryptographic Saving ($56.60\%$):**
   Applies strictly to the isolated cryptographic calculation on routine records ($0.040425\,\text{mJ} \rightarrow 0.0175461\,\text{mJ}$). High-sensitivity records still execute full AES-256-GCM ($0.040425\,\text{mJ}$).
2. **Whole-Batch Cryptographic Saving ($31.13\%$):**
   For a reference 100-record batch with 45 High-Sensitivity and 55 Routine records:
   - Baseline batch crypto: $100 \times 0.040425\,\text{mJ} = 4.0425\,\text{mJ}$
   - Adaptive batch crypto: $45 \times 0.040425\,\text{mJ} + 55 \times 0.0175461\,\text{mJ} = 1.819125 + 0.9650355 = 2.7841605\,\text{mJ}$
   - Batch crypto saving: $\frac{4.0425 - 2.7841605}{4.0425} \times 100\% = 31.13\%$
3. **Whole-Batch Total Device Energy Saving ($6.63\%$ to $12.91\%$):**
   When shared sensor preprocessing ($0.35\,\text{ms}$ at $8.5\,\text{mA} = 0.982\,\text{mJ}$/batch), radio transmission ($28\,\text{mA}$), and deep sleep ($15\,\mu\text{A}$) are included:
   - **Compute-Intensive / Short-TX ($0.50\,\text{ms}$ TX airtime):** Cryptographic work accounts for 44% of total energy; adaptive routing produces **~12.91%** batch energy savings.
   - **Radio-Heavy MCU Model ($1.50\,\text{ms}$ TX airtime):** Radio transmission dominates (73% of energy); adaptive routing produces **~6.63%** batch energy savings.

> [!WARNING]
> The per-operation cryptographic energy reduction of $56.60\%$ must **never** be cited as whole-device battery life extension. Radio transmission and sensor sampling remain dominant energy consumers in wireless IoT devices.

---

## 8. Indicative Battery Runtime & Duty Cycle Model

Battery runtime is calculated using an explicit, defensible duty-cycle model:
$$\text{Runtime (Hours)} = \frac{C_{\text{nominal}} \times F_{\text{usable}}}{I_{\text{effective}}}$$

### Duty-Cycle Formulation:
- **Reporting Period ($T_{\text{period}}$):** Configured as $1000.0\,\text{ms}$ ($1\,\text{Hz}$ telemetry cadence).
- **Active Time per Record ($t_{\text{active}}$):**
  $$t_{\text{active}} = t_{\text{proc}} + t_{\text{crypto}} + t_{\text{tx}}$$
  - Baseline: $0.35\,\text{ms} + 1.25\,\text{ms} + 1.50\,\text{ms} = 3.10\,\text{ms}$ per record (Scenario A) or $2.10\,\text{ms}$ (Scenario B).
  - Duty cycle: $\approx 0.2\% - 0.3\%$.
- **Sleep Time per Record ($t_{\text{sleep}}$):**
  $$t_{\text{sleep}} = T_{\text{period}} - t_{\text{active}}$$
- **Sleep Current ($I_{\text{sleep}}$):** $15\,\mu\text{A} = 0.015\,\text{mA}$ (Cortex-M0+ low-power deep sleep mode with RTC alarm).
- **Effective Average Current ($I_{\text{effective}}$):**
  $$I_{\text{effective}} = \frac{I_{\text{active}} \cdot t_{\text{active}} + I_{\text{sleep}} \cdot t_{\text{sleep}}}{T_{\text{period}}}$$

> [!NOTE]
> Indicative battery runtime reflects periodic $1\,\text{Hz}$ telemetry with deep sleep. Continuous active-loop execution without sleep is unrepresentative of real IoT devices and leads to artificially truncated runtimes.

---

## 9. Hardware Interface vs Laboratory Measurement Provenance

The system enforces clear evidence tier labeling across all modes:
- **Tier A — Desktop Measured Host (`DESKTOP_MEASURED_HOST`):** Wall-clock execution on host workstation. Demonstrates that adaptive classification adds CPU overhead on desktop architectures where AES-NI hardware acceleration exists.
- **Tier B — Modeled / Estimated MCU (`MODELED_ESTIMATED_MCU`):** Mathematical energy simulator modeling embedded IoT hardware. Parameters are explicitly configurable and labeled as hypothetical or literature-derived.
- **Tier C — Instrument Measured Lab (`INSTRUMENT_MEASURED_LAB`):** Time-series power samples imported via `/api/power/import` from calibrated laboratory measurement tools (Monsoon, Otii, Keysight).
- **Hardware Serial Interface (`INTERFACE_PLACEHOLDER_HARDWARE_PENDING`):** The `HardwareSerialPowerAdapter` class provides a defined interface for real-time serial DAQ boards (such as INA219/INA226). In the absence of attached physical hardware, it reports placeholder status and safely directs the user to CSV laboratory log imports.

