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

## 6. Indicative Battery Runtime Calculation

Battery runtime is calculated **only** when battery nominal capacity, nominal voltage, and load assumptions are supplied:
$$\text{Runtime (Hours)} = \frac{C_{\text{nominal}} \times F_{\text{usable}}}{I_{\text{mean}}}$$
- $C_{\text{nominal}}$: Battery rated capacity in $\text{mAh}$.
- $F_{\text{usable}}$: Usable depth-of-discharge factor (default $0.85$).
- $I_{\text{mean}}$: Operating average current in $\text{mA}$.

> [!WARNING]
> Battery runtime is an indicative linear projection. In real deployments, runtime is non-linear and governed by Peukert's law, temperature, battery internal resistance (ESR), and switching regulator efficiency.
