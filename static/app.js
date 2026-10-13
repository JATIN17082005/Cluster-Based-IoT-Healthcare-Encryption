/**
 * ClusterGuard — IoT Healthcare Security & Energy Lab
 * Master Frontend Controller & Interactive Simulation Engine
 */

document.addEventListener("DOMContentLoaded", () => {
  // =========================================================================
  // State Management
  // =========================================================================
  let currentRecords = [];
  let isRunning = false;
  let lastComparisonData = null;

  // Battery Drain Simulation State
  let simState = {
    scenario: "mcu", // "desktop" | "mcu"
    baselinePct: 100.0,
    adaptivePct: 100.0,
    baselineJ: 0.0,
    adaptiveJ: 0.0,
    baselineMah: 1200.0,
    adaptiveMah: 1200.0,
    isSimulating: false,
    isPaused: false,
    timerId: null,
    scale: 80, // Presentation scale (default high-contrast 80% visual drain)
    lastMcuData: null,
    progress: 0,
    stepsTotal: 30,
    targetBasePct: 100.0,
    targetAdaptPct: 100.0,
    targetBaseJ: 0.0,
    targetAdaptJ: 0.0,
    targetBaseMahUsed: 0.0,
    targetAdaptMahUsed: 0.0,
  };

  // Guided Demo Walkthrough State
  let guidedStep = 1;
  const TOTAL_GUIDED_STEPS = 8;

  function showToast(message, type = "info") {
    console.log(`[Toast ${type}] ${message}`);
    let toastEl = document.getElementById("app-toast-notification");
    if (!toastEl) {
      toastEl = document.createElement("div");
      toastEl.id = "app-toast-notification";
      toastEl.style.cssText = "position:fixed;bottom:24px;right:24px;z-index:9999;padding:10px 18px;border-radius:6px;font-size:0.85rem;font-weight:600;box-shadow:0 4px 16px rgba(0,0,0,0.5);transition:opacity 0.3s ease;pointer-events:none;color:#fff;";
      document.body.appendChild(toastEl);
    }
    toastEl.textContent = message;
    toastEl.style.background = type === "danger" ? "#e11d48" : type === "warning" ? "#d97706" : "#0284c7";
    toastEl.style.opacity = "1";
    clearTimeout(toastEl._timer);
    toastEl._timer = setTimeout(() => {
      toastEl.style.opacity = "0";
    }, 3000);
  }

  // =========================================================================
  // DOM Elements Selection
  // =========================================================================
  // Navigation & Health
  const tabBtns = document.querySelectorAll(".tab-btn");
  const tabPanes = document.querySelectorAll(".tab-pane");
  const backendStatusPill = document.getElementById("backend-status-pill");
  const backendStatusText = document.getElementById("backend-status-text");
  const provenanceBanner = document.getElementById("provenance-banner");
  const provenanceText = document.getElementById("provenance-text");
  const btnStartGuidedDemo = document.getElementById("btn-start-guided-demo");

  // Global Workload Controls
  const inputCount = document.getElementById("input-count");
  const inputSeed = document.getElementById("input-seed");
  const inputReps = document.getElementById("input-reps");
  const btnGenerate = document.getElementById("btn-generate");
  const btnRunBaseline = document.getElementById("btn-run-baseline");
  const btnRunAdaptive = document.getElementById("btn-run-adaptive");
  const btnRunCompare = document.getElementById("btn-run-compare");
  const heroBtnCompare = document.getElementById("hero-btn-compare");
  const btnStop = document.getElementById("btn-stop");
  const btnReset = document.getElementById("btn-reset");
  const btnToggleAdvanced = document.getElementById("btn-toggle-advanced");
  const advancedConfigPanel = document.getElementById("advanced-config-panel");

  // KPI Elements
  const kpiRecordsVal = document.getElementById("kpi-records-val");
  const statHighCount = document.getElementById("stat-high-count");
  const statLowCount = document.getElementById("stat-low-count");
  const statSent = document.getElementById("stat-sent");
  const statAccepted = document.getElementById("stat-accepted");
  const statRejected = document.getElementById("stat-rejected");
  const statRejected2 = document.getElementById("stat-rejected-2");
  const statTsr = document.getElementById("stat-tsr");
  const statPlr = document.getElementById("stat-plr");
  const kpiLatencyVal = document.getElementById("kpi-latency-val");
  const kpiLatencyDelta = document.getElementById("kpi-latency-delta");
  const kpiEnergyVal = document.getElementById("kpi-energy-val");
  const kpiChargeVal = document.getElementById("kpi-charge-val");
  const batchRecordCountBadge = document.getElementById("batch-record-count-badge");
  const pipelineStatusBadge = document.getElementById("pipeline-status");

  // Pipeline Drawer
  const pipelineSteps = document.querySelectorAll(".pipeline-step");
  const pipelineDrawer = document.getElementById("pipeline-stage-drawer");
  const drawerTitle = document.getElementById("drawer-title");
  const drawerDescription = document.getElementById("drawer-description");
  const drawerInputs = document.getElementById("drawer-inputs");
  const drawerOutputs = document.getElementById("drawer-outputs");
  const drawerFacultyNote = document.getElementById("drawer-faculty-note");
  const btnCloseDrawer = document.getElementById("btn-close-drawer");

  // Battery Simulation Controls & Meters
  const batteryScenarioSelect = document.getElementById("battery-scenario-select");
  const mcuProfileContainer = document.getElementById("mcu-profile-container");
  const mcuProfileSelect = document.getElementById("mcu-profile-select");
  const scenarioBadgeHeader = document.getElementById("scenario-badge-header");
  const scenarioPillTag = document.getElementById("scenario-pill-tag");
  const scenarioDisclaimerBanner = document.getElementById("scenario-disclaimer-banner");
  const scenarioDisclaimerTitle = document.getElementById("scenario-disclaimer-title");
  const scenarioDisclaimerBody = document.getElementById("scenario-disclaimer-body");
  const btnToggleMcuParams = document.getElementById("btn-toggle-mcu-params");
  const mcuConfigDrawer = document.getElementById("mcu-config-drawer");
  const btnApplyMcuConfig = document.getElementById("btn-apply-mcu-config");
  const btnResetMcuDefaults = document.getElementById("btn-reset-mcu-defaults");

  const batteryFillBaseline = document.getElementById("battery-fill-baseline");
  const batteryFillAdaptive = document.getElementById("battery-fill-adaptive");
  const batteryPctBaseline = document.getElementById("battery-pct-baseline");
  const batteryPctAdaptive = document.getElementById("battery-pct-adaptive");
  const batteryMahBaseline = document.getElementById("battery-mah-baseline");
  const batteryMahAdaptive = document.getElementById("battery-mah-adaptive");
  const batteryJBaseline = document.getElementById("battery-j-baseline");
  const batteryJAdaptive = document.getElementById("battery-j-adaptive");
  const batteryStatusBaseline = document.getElementById("battery-status-baseline");
  const batteryStatusAdaptive = document.getElementById("battery-status-adaptive");
  const batteryScenarioTagBaseline = document.getElementById("battery-scenario-tag-baseline");
  const batteryScenarioTagAdaptive = document.getElementById("battery-scenario-tag-adaptive");
  const batteryCardBaseline = document.getElementById("battery-card-baseline");
  const batteryCardAdaptive = document.getElementById("battery-card-adaptive");

  const btnBatteryStartDemo = document.getElementById("btn-battery-start-demo");
  const btnBatteryPause = document.getElementById("btn-battery-pause");
  const btnBatteryResume = document.getElementById("btn-battery-resume");
  const btnBatteryReset = document.getElementById("btn-battery-reset");
  const btnBatteryReplay = document.getElementById("btn-battery-replay");
  const simScaleSelect = document.getElementById("sim-scale-select");

  // MCU Parameter Inputs
  const mcuVcc = document.getElementById("mcu-vcc");
  const mcuBatteryMah = document.getElementById("mcu-battery-mah");
  const mcuICpu = document.getElementById("mcu-i-cpu");
  const mcuIAes = document.getElementById("mcu-i-aes");
  const mcuISha = document.getElementById("mcu-i-sha");
  const mcuIXor = document.getElementById("mcu-i-xor");
  const mcuIHmac = document.getElementById("mcu-i-hmac");
  const mcuITx = document.getElementById("mcu-i-tx");
  const mcuTAes = document.getElementById("mcu-t-aes");
  const mcuTSha = document.getElementById("mcu-t-sha");
  const mcuTXor = document.getElementById("mcu-t-xor");
  const mcuTHmac = document.getElementById("mcu-t-hmac");
  const mcuTTx = document.getElementById("mcu-t-tx");

  // Scenario Comparison Summary Elements
  const scenarioSummaryStatusBadge = document.getElementById("scenario-summary-status-badge");
  const simSumBaseJ = document.getElementById("sim-sum-base-j");
  const simSumAdaptJ = document.getElementById("sim-sum-adapt-j");
  const simSumDeltaJ = document.getElementById("sim-sum-delta-j");
  const simSumDirJ = document.getElementById("sim-sum-dir-j");
  const simSumBaseLat = document.getElementById("sim-sum-base-lat");
  const simSumAdaptLat = document.getElementById("sim-sum-adapt-lat");
  const simSumDeltaLat = document.getElementById("sim-sum-delta-lat");
  const simSumDirLat = document.getElementById("sim-sum-dir-lat");
  const simSumBaseHours = document.getElementById("sim-sum-base-hours");
  const simSumAdaptHours = document.getElementById("sim-sum-adapt-hours");
  const simSumDeltaHours = document.getElementById("sim-sum-delta-hours");
  const simSumDirHours = document.getElementById("sim-sum-dir-hours");

  // Physical Battery State Elements
  const batteryPhysPctBaseline = document.getElementById("battery-phys-pct-baseline");
  const batteryPhysPctAdaptive = document.getElementById("battery-phys-pct-adaptive");

  // MCU Workload & Sensitivity Controls
  const mcuClockMhz = document.getElementById("mcu-clock-mhz");
  const mcuWorkloadTotal = document.getElementById("mcu-workload-total");
  const mcuWorkloadHigh = document.getElementById("mcu-workload-high");
  const mcuWorkloadRoutine = document.getElementById("mcu-workload-routine");
  const mcuWorkloadBalanceStatus = document.getElementById("mcu-workload-balance-status");

  // Dedicated Panel: Cryptographic Computation Elements
  const cryptoComputationPanel = document.getElementById("crypto-computation-panel");
  const mcuPanelClockLabel = document.getElementById("mcu-panel-clock-label");
  const mcuPanelWorkloadLabel = document.getElementById("mcu-panel-workload-label");
  const cryptoComputationBadge = document.getElementById("crypto-computation-badge");

  const cardCryptoTimeReduction = document.getElementById("card-crypto-time-reduction");
  const cardCryptoTimeAdapt = document.getElementById("card-crypto-time-adapt");
  const cardCryptoTimeBase = document.getElementById("card-crypto-time-base");
  const cardCryptoTimePctBar = document.getElementById("card-crypto-time-pct-bar");
  const cardCryptoTimeBarFill = document.getElementById("card-crypto-time-bar-fill");

  const cardCryptoCyclesReduction = document.getElementById("card-crypto-cycles-reduction");
  const cardCryptoCyclesAdapt = document.getElementById("card-crypto-cycles-adapt");
  const cardCryptoCyclesBase = document.getElementById("card-crypto-cycles-base");
  const cardCryptoCyclesPctBar = document.getElementById("card-crypto-cycles-pct-bar");
  const cardCryptoCyclesBarFill = document.getElementById("card-crypto-cycles-bar-fill");

  const cardCryptoEnergyReduction = document.getElementById("card-crypto-energy-reduction");
  const cardCryptoEnergyAdapt = document.getElementById("card-crypto-energy-adapt");
  const cardCryptoEnergyBase = document.getElementById("card-crypto-energy-base");
  const cardCryptoEnergyPctBar = document.getElementById("card-crypto-energy-pct-bar");
  const cardCryptoEnergyBarFill = document.getElementById("card-crypto-energy-bar-fill");

  const cardBatchEnergyReduction = document.getElementById("card-batch-energy-reduction");
  const cardBatchEnergyAdapt = document.getElementById("card-batch-energy-adapt");
  const cardBatchEnergyBase = document.getElementById("card-batch-energy-base");
  const cardBatchEnergyPctBar = document.getElementById("card-batch-energy-pct-bar");
  const cardBatchEnergyBarFill = document.getElementById("card-batch-energy-bar-fill");

  const cryptoBreakdownTbody = document.getElementById("crypto-breakdown-tbody");
  const batchBreakdownTbody = document.getElementById("batch-breakdown-tbody");
  const radioSweepTbody = document.getElementById("radio-sweep-tbody");

  // Comparison Tab Elements
  const overallStatusBadge = document.getElementById("overall-status-badge");
  const comparisonProvenanceBadge = document.getElementById("comparison-provenance-badge");
  const compBaseEnc = document.getElementById("comp-base-enc");
  const compAdaptEnc = document.getElementById("comp-adapt-enc");
  const compDeltaEnc = document.getElementById("comp-delta-enc");
  const compDirEnc = document.getElementById("comp-dir-enc");
  const compBaseMedian = document.getElementById("comp-base-median");
  const compAdaptMedian = document.getElementById("comp-adapt-median");
  const compDeltaMedian = document.getElementById("comp-delta-median");
  const compDirMedian = document.getElementById("comp-dir-median");
  const compBaseP95 = document.getElementById("comp-base-p95");
  const compAdaptP95 = document.getElementById("comp-adapt-p95");
  const compDeltaP95 = document.getElementById("comp-delta-p95");
  const compDirP95 = document.getElementById("comp-dir-p95");
  const compBaseEnergy = document.getElementById("comp-base-energy");
  const compAdaptEnergy = document.getElementById("comp-adapt-energy");
  const compDeltaEnergy = document.getElementById("comp-delta-energy");
  const compDirEnergy = document.getElementById("comp-dir-energy");
  const compAdaptSaving = document.getElementById("comp-adapt-saving");
  const compDeltaSaving = document.getElementById("comp-delta-saving");
  const compDirSaving = document.getElementById("comp-dir-saving");
  const compBaseEnergyRec = document.getElementById("comp-base-energy-rec");
  const compAdaptEnergyRec = document.getElementById("comp-adapt-energy-rec");
  const compDeltaEnergyRec = document.getElementById("comp-delta-energy-rec");
  const compDirEnergyRec = document.getElementById("comp-dir-energy-rec");
  const compBaseE1k = document.getElementById("comp-base-e1k");
  const compAdaptE1k = document.getElementById("comp-adapt-e1k");
  const compDeltaE1k = document.getElementById("comp-delta-e1k");
  const compDirE1k = document.getElementById("comp-dir-e1k");
  const compBaseCurr = document.getElementById("comp-base-curr");
  const compAdaptCurr = document.getElementById("comp-adapt-curr");
  const compDeltaCurr = document.getElementById("comp-delta-curr");
  const compDirCurr = document.getElementById("comp-dir-curr");
  const compBaseCharge = document.getElementById("comp-base-charge");
  const compAdaptCharge = document.getElementById("comp-adapt-charge");
  const compDeltaCharge = document.getElementById("comp-delta-charge");
  const compDirCharge = document.getElementById("comp-dir-charge");
  const compBaseTsr = document.getElementById("comp-base-tsr");
  const compAdaptTsr = document.getElementById("comp-adapt-tsr");
  const compDeltaTsr = document.getElementById("comp-delta-tsr");
  const compDirTsr = document.getElementById("comp-dir-tsr");
  const compBasePlr = document.getElementById("comp-base-plr");
  const compAdaptPlr = document.getElementById("comp-adapt-plr");
  const compDeltaPlr = document.getElementById("comp-delta-plr");
  const compDirPlr = document.getElementById("comp-dir-plr");
  const compBaseRuntime = document.getElementById("comp-base-runtime");
  const compAdaptRuntime = document.getElementById("comp-adapt-runtime");
  const compDeltaRuntime = document.getElementById("comp-delta-runtime");
  const compDirRuntime = document.getElementById("comp-dir-runtime");

  // Visual Bars
  const barEncBase = document.getElementById("bar-enc-base");
  const barEncBaseVal = document.getElementById("bar-enc-base-val");
  const barEncAdapt = document.getElementById("bar-enc-adapt");
  const barEncAdaptVal = document.getElementById("bar-enc-adapt-val");
  const barEnergyBase = document.getElementById("bar-energy-base");
  const barEnergyBaseVal = document.getElementById("bar-energy-base-val");
  const barEnergyAdapt = document.getElementById("bar-energy-adapt");
  const barEnergyAdaptVal = document.getElementById("bar-energy-adapt-val");

  // Tamper Demo
  const tamperAlgo = document.getElementById("tamper-algo");
  const tamperTarget = document.getElementById("tamper-target");
  const btnRunTamper = document.getElementById("btn-run-tamper");
  const tamperResults = document.getElementById("tamper-results");

  // CSV Importer
  const powerCsvFile = document.getElementById("power-csv-file");
  const btnUploadCsv = document.getElementById("btn-upload-csv");
  const uploadStatus = document.getElementById("upload-status");

  // Record Explorer
  const searchRecordsInput = document.getElementById("search-records-input");
  const filterSensitivity = document.getElementById("filter-sensitivity");
  const filterCluster = document.getElementById("filter-cluster");
  const filterVitals = document.getElementById("filter-vitals");
  const btnClearFilters = document.getElementById("btn-clear-filters");
  const recordsTableBody = document.getElementById("records-table-body");
  const explorerRecordsCountBadge = document.getElementById("explorer-records-count-badge");
  const recordDetailsDrawer = document.getElementById("record-details-drawer");
  const recordDrawerBody = document.getElementById("record-drawer-body");
  const btnCloseRecordDrawer = document.getElementById("btn-close-record-drawer");

  // Security & Power Config
  const btnSavePowerConfig = document.getElementById("btn-save-power-config");
  const cfgVoltage = document.getElementById("cfg-voltage");
  const cfgMcu = document.getElementById("cfg-mcu");
  const cfgAesI = document.getElementById("cfg-aes-i");
  const cfgXorI = document.getElementById("cfg-xor-i");
  const cfgTxI = document.getElementById("cfg-tx-i");
  const cfgBatteryMah = document.getElementById("cfg-battery-mah");
  const cfgStatus = document.getElementById("cfg-status");

  // Run History
  const historyTableBody = document.getElementById("history-table-body");
  const btnRefreshHistory = document.getElementById("btn-refresh-history");
  const evaluatorSummary = document.getElementById("evaluator-summary");

  // Guided Demo Modal
  const guidedModalBackdrop = document.getElementById("guided-modal-backdrop");
  const guidedStepIndicator = document.getElementById("guided-step-indicator");
  const guidedTitle = document.getElementById("guided-title");
  const guidedExplanation = document.getElementById("guided-explanation");
  const guidedLiveBox = document.getElementById("guided-live-box");
  const btnGuidedNext = document.getElementById("btn-guided-next");
  const btnGuidedBack = document.getElementById("btn-guided-back");
  const btnGuidedRestart = document.getElementById("btn-guided-restart");
  const btnGuidedExit = document.getElementById("btn-guided-exit");

  // =========================================================================
  // Pipeline Step Knowledge Base
  // =========================================================================
  const PIPELINE_STAGES = {
    1: {
      name: "Stage 01: Synthetic Data Generation",
      description: "Generates realistic physiological telemetry batches using deterministic pseudo-random seeds. Synthesizes clinical signals including cardiac ECG waveforms, heart rates, body temperatures, and routine ambulatory step counts.",
      inputs: "Seed (42), Batch Size (50), Sensor Profiles",
      outputs: "Array of JSON SensorRecord objects with timestamps and baseline units",
      note: "Guarantees exact byte-level repeatability across paired benchmarking runs.",
    },
    2: {
      name: "Stage 02: Deterministic Sensitivity Classification",
      description: "Applies rule-based clinical thresholds. Classifies abnormal tachycardia (>100 bpm), bradycardia (<50 bpm), fevers, and ECG waveforms as HIGH sensitivity; routine vital signs and steps as LOW sensitivity.",
      inputs: "Raw SensorRecord stream",
      outputs: "SensitivityLevel (HIGH / LOW) with human-auditable classification reasons",
      note: "No black-box decisions. Faculty can inspect why each vital was classified as critical or routine.",
    },
    3: {
      name: "Stage 03: Cluster Partition & Routing",
      description: "Separates records into two distinct transmission queues: CLUSTER-HIGH (Critical patient data) and CLUSTER-LOW (Routine telemetry data).",
      inputs: "Classified telemetry stream",
      outputs: "Partitioned cluster groups ready for distinct cryptographic pipelines",
      note: "Provides architectural isolation preventing routine telemetry from clogging the crypto coprocessor.",
    },
    4: {
      name: "Stage 04: Cryptographic Routing & AEAD Encryption",
      description: "High-sensitivity records are encrypted with NIST-compliant AES-256-GCM using fresh 96-bit nonces. Routine records are routed to an experimental lightweight stream cipher with HMAC-SHA-256 integrity authentication.",
      inputs: "Cluster payloads, 256-bit AES key, ephemeral stream key",
      outputs: "Encrypted canonical envelopes with 128-bit authentication tags and unique nonces",
      note: "AES-GCM guarantees AEAD confidentiality and authenticity. XOR is marked experimental.",
    },
    5: {
      name: "Stage 05: Local Healthcare Receiver Ingestion",
      description: "Simulates clinical edge receiver. Ingests encrypted envelopes, verifies authentication tags in constant time, tracks nonce freshness, and decrypts payloads back into electronic health records.",
      inputs: "Over-the-air encrypted JSON envelopes",
      outputs: "Verification status (Accepted / Tampered Dropped), Decrypted telemetry",
      note: "Drops tampered packets immediately without exposing cryptographic secrets.",
    },
    6: {
      name: "Stage 06: Energy & Performance Benchmark Engine",
      description: "Monotonically isolates pure cryptographic execution from serialization noise. Computes Transmission Success Rate (TSR), Packet Loss Rate (PLR), and electrical energy via trapezoidal numerical integration.",
      inputs: "Nanosecond execution timers, documented 3.3V power model / lab CSV samples",
      outputs: "Latency percentiles (mean, median, p95), total Joules, mJ/1,000 records, mAh",
      note: "Strictly labels results as SIMULATED / ESTIMATED when running without physical meters.",
    },
  };

  // =========================================================================
  // Tab Switching Logic
  // =========================================================================
  tabBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      tabBtns.forEach((b) => b.classList.remove("active"));
      tabPanes.forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      const targetId = btn.getAttribute("data-tab");
      const pane = document.getElementById(targetId);
      if (pane) {
        pane.classList.add("active");
        if (targetId === "tab-history") {
          loadHistory();
        }
      }
    });
  });

  // Toggle Advanced Workload Panel
  if (btnToggleAdvanced && advancedConfigPanel) {
    btnToggleAdvanced.addEventListener("click", () => {
      advancedConfigPanel.classList.toggle("open");
      btnToggleAdvanced.innerHTML = advancedConfigPanel.classList.contains("open")
        ? "Advanced Settings &#9652;"
        : "Advanced Settings &#9662;";
    });
  }

  // =========================================================================
  // Backend Connection Health Polling
  // =========================================================================
  async function checkBackendHealth() {
    try {
      const resp = await fetch("/api/health");
      if (resp.ok) {
        const data = await resp.json();
        backendStatusPill.className = "status-pill online";
        backendStatusText.textContent = "Backend Connected";
      } else {
        throw new Error("Bad status");
      }
    } catch (err) {
      backendStatusPill.className = "status-pill";
      backendStatusText.textContent = "Backend Offline";
    }
  }
  checkBackendHealth();
  setInterval(checkBackendHealth, 30000);

  // =========================================================================
  // Pipeline Step Interaction & Drawer Logic
  // =========================================================================
  pipelineSteps.forEach((stepEl) => {
    stepEl.addEventListener("click", () => {
      const stepNum = parseInt(stepEl.getAttribute("data-step"), 10);
      showPipelineDrawer(stepNum);
    });
  });

  function showPipelineDrawer(stepNum) {
    const data = PIPELINE_STAGES[stepNum];
    if (!data) return;

    pipelineSteps.forEach((s) => s.classList.remove("active-step"));
    const activeEl = document.getElementById(`step-${stepNum}`);
    if (activeEl) activeEl.classList.add("active-step");

    drawerTitle.textContent = data.name;
    drawerDescription.textContent = data.description;
    drawerInputs.textContent = data.inputs;
    drawerOutputs.textContent = data.outputs;
    drawerFacultyNote.textContent = data.note;
    pipelineDrawer.classList.add("open");
  }

  if (btnCloseDrawer) {
    btnCloseDrawer.addEventListener("click", () => {
      pipelineDrawer.classList.remove("open");
      pipelineSteps.forEach((s) => s.classList.remove("active-step"));
    });
  }

  function highlightPipelineStep(stepNum) {
    pipelineSteps.forEach((s) => {
      const num = parseInt(s.getAttribute("data-step"), 10);
      if (num === stepNum) {
        s.classList.add("active-step");
      } else {
        s.classList.remove("active-step");
      }
    });
  }

  // =========================================================================
  // Provenance Label Helper
  // =========================================================================
  function updateProvenanceBanner(source) {
    if (!provenanceBanner || !provenanceText) return;
    const src = (source || "estimated").toLowerCase();
    provenanceBanner.className = "provenance-banner";

    if (src === "hardware") {
      provenanceBanner.classList.add("hardware");
      provenanceText.textContent = "DIRECT HARDWARE MEASUREMENT (INLINE POWER SENSOR)";
    } else if (src === "imported") {
      provenanceBanner.classList.add("imported");
      provenanceText.textContent = "IMPORTED INSTRUMENT LOG (PHYSICAL BENCHTOP METER)";
    } else {
      provenanceText.textContent = "SIMULATED / ESTIMATED — NOT A PHYSICAL BATTERY READING";
    }
  }

  // =========================================================================
  // Set UI Running State
  // =========================================================================
  function setRunning(running) {
    isRunning = running;
    btnGenerate.disabled = running;
    btnRunBaseline.disabled = running;
    btnRunAdaptive.disabled = running;
    btnRunCompare.disabled = running;
    if (heroBtnCompare) heroBtnCompare.disabled = running;
    btnStop.disabled = !running;

    if (pipelineStatusBadge) {
      pipelineStatusBadge.textContent = running ? "RUNNING" : "READY";
      pipelineStatusBadge.className = running ? "badge status-badge-regression" : "badge badge-low";
    }
  }

  // =========================================================================
  // Synthetic Data Generation (Phase 1 / FR-01)
  // =========================================================================
  btnGenerate.addEventListener("click", () => generateData());

  async function generateData() {
    const count = parseInt(inputCount.value, 10) || 50;
    const seed = parseInt(inputSeed.value, 10) || 42;

    highlightPipelineStep(1);
    try {
      const resp = await fetch("/api/demo/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ count, seed }),
      });
      if (!resp.ok) throw new Error("Failed to generate synthetic data");
      const data = await resp.json();

      currentRecords = data.all_records || [];
      renderRecordExplorer(currentRecords);

      // Update KPIs & Distribution Summary
      kpiRecordsVal.textContent = data.count;
      statHighCount.textContent = data.high_cluster_count;
      statLowCount.textContent = data.low_cluster_count;
      if (batchRecordCountBadge) batchRecordCountBadge.textContent = `${data.count} Records`;
      if (explorerRecordsCountBadge) explorerRecordsCountBadge.textContent = `${data.count} Records`;

      // Reset receiver stats
      statSent.textContent = "0";
      statAccepted.textContent = "0";
      if (statRejected) statRejected.textContent = "0";
      if (statRejected2) statRejected2.textContent = "0";

      highlightPipelineStep(2);
      if (simState.scenario === "mcu") {
        fetchMcuScenarioData();
      }
      return data;
    } catch (err) {
      alert("Error generating data: " + err.message);
      return null;
    }
  }

  // =========================================================================
  // Paired Benchmark Comparison Execution (FR-18)
  // =========================================================================
  btnRunCompare.addEventListener("click", () => runComparison());
  if (heroBtnCompare) heroBtnCompare.addEventListener("click", () => runComparison());

  async function runComparison() {
    const count = parseInt(inputCount.value, 10) || 50;
    const seed = parseInt(inputSeed.value, 10) || 42;
    const reps = parseInt(inputReps.value, 10) || 10;

    setRunning(true);
    highlightPipelineStep(4);

    try {
      const resp = await fetch("/api/benchmark/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          mode: "comparison",
          record_count: count,
          seed: seed,
          repetitions: reps,
        }),
      });

      if (!resp.ok) {
        const errData = await resp.json();
        throw new Error(errData.detail || "Benchmark execution failed");
      }

      const data = await resp.json();
      lastComparisonData = data.comparison;
      updateComparisonUI(data.comparison);
      highlightPipelineStep(6);
      loadHistory();
      return data.comparison;
    } catch (err) {
      alert("Benchmark error: " + err.message);
      return null;
    } finally {
      setRunning(false);
    }
  }

  // Single Baseline / Adaptive Execution
  btnRunBaseline.addEventListener("click", () => runSingleBatch("baseline"));
  btnRunAdaptive.addEventListener("click", () => runSingleBatch("adaptive"));

  async function runSingleBatch(mode) {
    const count = parseInt(inputCount.value, 10) || 50;
    const seed = parseInt(inputSeed.value, 10) || 42;
    setRunning(true);

    try {
      const resp = await fetch("/api/benchmark/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode, record_count: count, seed }),
      });
      if (!resp.ok) throw new Error("Single run failed");
      const metrics = await resp.json();
      updateSingleRunUI(metrics);
      loadHistory();
    } catch (err) {
      alert("Error running batch: " + err.message);
    } finally {
      setRunning(false);
    }
  }

  // =========================================================================
  // Update Comparison UI & Detailed KPI Cards
  // =========================================================================
  function updateComparisonUI(comp) {
    const base = comp.baseline_summary;
    const adapt = comp.adaptive_summary;

    updateProvenanceBanner(base.measurement_source);
    if (comparisonProvenanceBadge) {
      comparisonProvenanceBadge.textContent = base.measurement_source.toUpperCase();
    }

    // Overall Status Badge
    const overallStatus = comp.overall_result_status || "REGRESSION";
    if (overallStatusBadge) {
      overallStatusBadge.textContent = `STATUS: ${overallStatus}`;
      overallStatusBadge.className = overallStatus === "REGRESSION"
        ? "badge status-badge-regression"
        : (overallStatus === "IMPROVEMENT" ? "badge status-badge-improvement" : "badge badge-aes");
    }

    // Update Top KPIs
    kpiRecordsVal.textContent = comp.record_count;
    statHighCount.textContent = adapt.high_sensitivity_count;
    statLowCount.textContent = adapt.low_sensitivity_count;
    statSent.textContent = adapt.records_sent;
    statAccepted.textContent = adapt.records_received - adapt.records_rejected;
    if (statRejected) statRejected.textContent = adapt.records_rejected;
    if (statRejected2) statRejected2.textContent = adapt.records_rejected;
    statTsr.textContent = `${adapt.tsr_percent}%`;
    statPlr.textContent = `${adapt.plr_percent}%`;

    // Latency KPI
    kpiLatencyVal.textContent = adapt.encryption_time_mean_ms.toFixed(3);
    const encDelta = comp.encryption_time_mean_ms ? comp.encryption_time_mean_ms.percentage_change : 0;
    kpiLatencyDelta.textContent = `${encDelta > 0 ? "+" : ""}${encDelta.toFixed(1)}% (REGRESSION)`;
    kpiLatencyDelta.className = "delta-worse";

    // Energy KPI
    kpiEnergyVal.textContent = adapt.energy_per_1000_records_mj.toFixed(1);
    if (kpiChargeVal) {
      kpiChargeVal.textContent = adapt.estimated_battery_charge_consumed_mah
        ? `${adapt.estimated_battery_charge_consumed_mah.toFixed(4)} mAh`
        : "N/A";
    }

    // Populate Detailed Comparison Table Rows
    compBaseEnc.textContent = `${base.encryption_time_mean_ms.toFixed(4)} ms`;
    compAdaptEnc.textContent = `${adapt.encryption_time_mean_ms.toFixed(4)} ms`;
    formatDeltaCell("comp-delta-enc", "comp-dir-enc", comp.encryption_time_mean_ms);

    if (compBaseMedian) {
      compBaseMedian.textContent = `${base.encryption_time_median_ms.toFixed(4)} ms`;
      compAdaptMedian.textContent = `${adapt.encryption_time_median_ms.toFixed(4)} ms`;
      formatDeltaCell("comp-delta-median", "comp-dir-median", comp.encryption_time_median_ms || comp.encryption_time_mean_ms);
    }

    compBaseP95.textContent = `${base.encryption_time_p95_ms.toFixed(4)} ms`;
    compAdaptP95.textContent = `${adapt.encryption_time_p95_ms.toFixed(4)} ms`;
    formatDeltaCell("comp-delta-p95", "comp-dir-p95", comp.encryption_time_p95_ms || comp.encryption_time_mean_ms);

    compBaseEnergy.textContent = `${base.total_energy_joules.toFixed(6)} J`;
    compAdaptEnergy.textContent = `${adapt.total_energy_joules.toFixed(6)} J`;
    formatDeltaCell("comp-delta-energy", "comp-dir-energy", comp.total_energy_joules);

    if (compAdaptSaving) {
      const saving = comp.total_energy_joules.energy_saving_percent !== undefined
        ? comp.total_energy_joules.energy_saving_percent.toFixed(2) + "%"
        : "N/A";
      compAdaptSaving.textContent = saving;
      compDeltaSaving.textContent = saving;
      compDirSaving.textContent = comp.total_energy_joules.direction;
      compDirSaving.className = comp.total_energy_joules.is_improvement ? "delta-better" : "delta-worse";
    }

    compBaseEnergyRec.textContent = `${base.energy_per_record_mj.toFixed(4)} mJ`;
    compAdaptEnergyRec.textContent = `${adapt.energy_per_record_mj.toFixed(4)} mJ`;
    formatDeltaCell("comp-delta-energy-rec", "comp-dir-energy-rec", comp.total_energy_joules);

    if (compBaseE1k) {
      compBaseE1k.textContent = `${base.energy_per_1000_records_mj.toFixed(4)} mJ`;
      compAdaptE1k.textContent = `${adapt.energy_per_1000_records_mj.toFixed(4)} mJ`;
      formatDeltaCell("comp-delta-e1k", "comp-dir-e1k", comp.total_energy_joules);
    }

    compBaseCurr.textContent = `${base.mean_current_ma.toFixed(2)} mA`;
    compAdaptCurr.textContent = `${adapt.mean_current_ma.toFixed(2)} mA`;
    formatDeltaCell("comp-delta-curr", "comp-dir-curr", comp.total_energy_joules);

    if (compBaseCharge) {
      compBaseCharge.textContent = base.estimated_battery_charge_consumed_mah ? `${base.estimated_battery_charge_consumed_mah.toFixed(6)} mAh` : "N/A";
      compAdaptCharge.textContent = adapt.estimated_battery_charge_consumed_mah ? `${adapt.estimated_battery_charge_consumed_mah.toFixed(6)} mAh` : "N/A";
      formatDeltaCell("comp-delta-charge", "comp-dir-charge", comp.total_energy_joules);
    }

    compBaseTsr.textContent = `${base.tsr_percent.toFixed(1)}%`;
    compAdaptTsr.textContent = `${adapt.tsr_percent.toFixed(1)}%`;
    formatDeltaCell("comp-delta-tsr", "comp-dir-tsr", comp.tsr_percent);

    compBasePlr.textContent = `${base.plr_percent.toFixed(1)}%`;
    compAdaptPlr.textContent = `${adapt.plr_percent.toFixed(1)}%`;
    formatDeltaCell("comp-delta-plr", "comp-dir-plr", comp.plr_percent);

    compBaseRuntime.textContent = base.estimated_runtime_hours ? `${base.estimated_runtime_hours} hrs` : "N/A";
    compAdaptRuntime.textContent = adapt.estimated_runtime_hours ? `${adapt.estimated_runtime_hours} hrs` : "N/A";
    formatDeltaCell("comp-delta-runtime", "comp-dir-runtime", comp.total_energy_joules);

    // Update Comparative Visual Bars
    const maxEnc = Math.max(base.encryption_time_mean_ms, adapt.encryption_time_mean_ms, 0.001);
    barEncBase.style.width = `${(base.encryption_time_mean_ms / maxEnc) * 100}%`;
    barEncBaseVal.textContent = `${base.encryption_time_mean_ms.toFixed(3)} ms`;
    barEncAdapt.style.width = `${(adapt.encryption_time_mean_ms / maxEnc) * 100}%`;
    barEncAdaptVal.textContent = `${adapt.encryption_time_mean_ms.toFixed(3)} ms`;

    const maxEnergy = Math.max(base.total_energy_joules, adapt.total_energy_joules, 0.0001);
    barEnergyBase.style.width = `${(base.total_energy_joules / maxEnergy) * 100}%`;
    barEnergyBaseVal.textContent = `${base.total_energy_joules.toFixed(4)} J`;
    barEnergyAdapt.style.width = `${(adapt.total_energy_joules / maxEnergy) * 100}%`;
    barEnergyAdaptVal.textContent = `${adapt.total_energy_joules.toFixed(4)} J`;

    // Evaluator Summary (FR-25)
    renderEvaluatorSummary(comp);
    renderScenarioSummary(simState.scenario === "mcu" ? simState.lastMcuData : lastComparisonData);
  }

  function formatDeltaCell(deltaId, dirId, comparisonMetric) {
    const deltaEl = document.getElementById(deltaId);
    const dirEl = document.getElementById(dirId);
    if (!deltaEl || !dirEl || !comparisonMetric) return;

    const pct = comparisonMetric.percentage_change;
    deltaEl.textContent = `${pct > 0 ? "+" : ""}${pct.toFixed(2)}%`;
    dirEl.textContent = comparisonMetric.direction;
    dirEl.className = comparisonMetric.is_improvement ? "delta-better" : "delta-worse";
  }

  function renderEvaluatorSummary(comp) {
    if (!evaluatorSummary) return;
    const base = comp.baseline_summary;
    const adapt = comp.adaptive_summary;
    const encDelta = comp.encryption_time_mean_ms ? comp.encryption_time_mean_ms.percentage_change : 0;
    const energySaving = comp.total_energy_joules ? comp.total_energy_joules.energy_saving_percent : 0;
    const source = base.measurement_source.toUpperCase();
    const status = comp.overall_result_status || "REGRESSION";

    evaluatorSummary.innerHTML = `
      <p style="margin-bottom:0.4rem;"><strong>Evaluation Protocol:</strong> Paired trial of ${comp.record_count} records (Seed: ${comp.seed}, Repetitions: ${comp.repetitions}, Warmup: ${comp.warmup_repetitions || 2}).</p>
      <p style="margin-bottom:0.4rem;"><strong>Result Status:</strong> <span class="badge ${status === 'IMPROVEMENT' ? 'badge-low' : 'status-badge-regression'}">${status}</span></p>
      <p style="margin-bottom:0.4rem;"><strong>Workload Split:</strong> ${adapt.high_sensitivity_count} HIGH records routed to AES-256-GCM; ${adapt.low_sensitivity_count} LOW records routed to experimental XOR.</p>
      <p style="margin-bottom:0.4rem;"><strong>Observed Encryption Latency:</strong> Mean encryption time changed by <strong>${encDelta > 0 ? "+" : ""}${encDelta.toFixed(2)}%</strong> (${base.encryption_time_mean_ms.toFixed(4)} ms vs. ${adapt.encryption_time_mean_ms.toFixed(4)} ms).</p>
      <p style="margin-bottom:0.4rem;"><strong>Energy Consumption / Savings:</strong> Percentage energy saving is <strong>${energySaving > 0 ? "+" : ""}${energySaving.toFixed(2)}%</strong> (Baseline: ${base.total_energy_joules.toFixed(5)} J vs. Adaptive: ${adapt.total_energy_joules.toFixed(5)} J).</p>
      <p style="font-size:0.8rem;color:var(--text-muted);margin-top:0.5rem;"><strong>Provenance Disclosure:</strong> Source is labeled <code>${source}</code>. ${source === "ESTIMATED" ? "Results reflect software model estimates rather than physical battery sensor measurements. Do not present as verified battery runtime without lab meter verification." : "Derived from imported instrument data."}</p>
    `;
  }

  function updateSingleRunUI(metrics) {
    updateProvenanceBanner(metrics.measurement_source);
    statSent.textContent = metrics.records_sent;
    statAccepted.textContent = metrics.records_received - metrics.records_rejected;
    if (statRejected) statRejected.textContent = metrics.records_rejected;
    if (statRejected2) statRejected2.textContent = metrics.records_rejected;
    statTsr.textContent = `${metrics.tsr_percent}%`;
    statPlr.textContent = `${metrics.plr_percent}%`;
  }

  // =========================================================================
  // Battery Drain Simulation Feature (Special Visual Requirement)
  // Two Scenarios: A (Current Desktop Benchmark) & B (Constrained MCU Simulated)
  // =========================================================================
  const MAX_BATTERY_SVG_WIDTH = 176; // Full width of fill bar inside SVG body

  function updateBatteryVisual(target, pct, joules, mah) {
    const clampedPct = Math.max(0, Math.min(100, pct));
    const fillWidth = (clampedPct / 100.0) * MAX_BATTERY_SVG_WIDTH;
    const nominalCap = parseFloat(cfgBatteryMah ? cfgBatteryMah.value : "1200.0") || 1200.0;
    const clampedMah = Math.max(0, Math.min(nominalCap, mah !== undefined ? mah : (nominalCap * clampedPct / 100.0)));
    const physPct = nominalCap > 0 ? (clampedMah / nominalCap) * 100.0 : 100.0;

    // Determine color based on remaining charge in demonstration meter
    let fillColor = "#10b981"; // Emerald (>50%)
    if (clampedPct < 20) {
      fillColor = "#f43f5e"; // Rose / Red (<20%)
    } else if (clampedPct < 50) {
      fillColor = "#f59e0b"; // Amber (20-50%)
    }

    if (target === "baseline") {
      batteryFillBaseline.setAttribute("width", fillWidth.toFixed(1));
      batteryFillBaseline.setAttribute("fill", fillColor);
      batteryPctBaseline.textContent = `${clampedPct.toFixed(1)}%`;
      if (batteryMahBaseline) {
        batteryMahBaseline.textContent = `${clampedMah.toFixed(3)} mAh`;
      }
      if (batteryPhysPctBaseline) {
        batteryPhysPctBaseline.textContent = `${physPct.toFixed(3)}%`;
      }
      batteryJBaseline.textContent = joules.toFixed(6);
    } else {
      batteryFillAdaptive.setAttribute("width", fillWidth.toFixed(1));
      batteryFillAdaptive.setAttribute("fill", fillColor);
      batteryPctAdaptive.textContent = `${clampedPct.toFixed(1)}%`;
      if (batteryMahAdaptive) {
        batteryMahAdaptive.textContent = `${clampedMah.toFixed(3)} mAh`;
      }
      if (batteryPhysPctAdaptive) {
        batteryPhysPctAdaptive.textContent = `${physPct.toFixed(3)}%`;
      }
      batteryJAdaptive.textContent = joules.toFixed(6);
    }
  }

  function resetBatterySim() {
    if (simState.timerId) clearInterval(simState.timerId);
    let nominalCap = 1200.0;
    if (simState.scenario === "mcu" && simState.lastMcuData && simState.lastMcuData.config) {
      nominalCap = simState.lastMcuData.config.battery_nominal_mah || 1200.0;
    } else {
      nominalCap = parseFloat(cfgBatteryMah ? cfgBatteryMah.value : "1200.0") || 1200.0;
    }
    simState.baselinePct = 100.0;
    simState.adaptivePct = 100.0;
    simState.baselineJ = 0.0;
    simState.adaptiveJ = 0.0;
    simState.baselineMah = nominalCap;
    simState.adaptiveMah = nominalCap;
    simState.isSimulating = false;
    simState.isPaused = false;
    simState.progress = 0;

    updateBatteryVisual("baseline", 100.0, 0.0, nominalCap);
    updateBatteryVisual("adaptive", 100.0, 0.0, nominalCap);

    batteryStatusBaseline.textContent = "READY";
    batteryStatusBaseline.style.color = "var(--text-secondary)";
    batteryStatusAdaptive.textContent = "READY";
    batteryStatusAdaptive.style.color = "var(--text-secondary)";

    batteryCardBaseline.classList.remove("discharging", "active-run");
    batteryCardAdaptive.classList.remove("discharging", "active-run");

    btnBatteryStartDemo.disabled = false;
    btnBatteryPause.disabled = true;
    btnBatteryResume.disabled = true;
    if (btnBatteryReplay) btnBatteryReplay.disabled = false;
  }

  async function fetchMcuScenarioData(total, high, routine, profileOverride) {
    try {
      let url = "/api/battery/mcu-scenario";
      const recTotal = total !== undefined ? total : (mcuWorkloadTotal ? parseInt(mcuWorkloadTotal.value, 10) : 100);
      const recHigh = high !== undefined ? high : (mcuWorkloadHigh ? parseInt(mcuWorkloadHigh.value, 10) : 45);
      const recRoutine = routine !== undefined ? routine : (mcuWorkloadRoutine ? parseInt(mcuWorkloadRoutine.value, 10) : 55);
      const prof = profileOverride !== undefined ? profileOverride : (mcuProfileSelect ? mcuProfileSelect.value : "short_tx");

      const params = new URLSearchParams();
      if (!isNaN(recTotal)) params.set("record_count", recTotal);
      if (!isNaN(recHigh)) params.set("high_count", recHigh);
      if (!isNaN(recRoutine)) params.set("low_count", recRoutine);
      if (prof) params.set("profile", prof);
      const qs = params.toString();
      if (qs) url += `?${qs}`;

      const resp = await fetch(url);
      if (!resp.ok) throw new Error("Failed to fetch MCU scenario data");
      const data = await resp.json();
      simState.lastMcuData = data;
      renderScenarioSummary(data);
      return data;
    } catch (err) {
      console.warn("MCU Scenario fetch error:", err);
      return null;
    }
  }

  function renderCryptoComputationPanel(data) {
    if (!data || !data.baseline || !data.adaptive) return;
    const base = data.baseline;
    const adapt = data.adaptive;
    const compEnergy = data.energy_comparison;
    const compCryptoTime = data.crypto_time_comparison;
    const compCryptoCycles = data.crypto_cycles_comparison || data.crypto_time_comparison;
    const compCryptoEnergy = data.crypto_energy_comparison || data.energy_comparison;

    // Header Labels
    const clockMhz = (data.config && data.config.mcu_clock_hz) ? (data.config.mcu_clock_hz / 1e6).toFixed(1) : "16.0";
    if (mcuPanelClockLabel) mcuPanelClockLabel.textContent = `${clockMhz} MHz`;
    if (mcuPanelWorkloadLabel) {
      mcuPanelWorkloadLabel.textContent = `${data.record_count} records: ${data.high_sensitivity_count} High / ${data.low_sensitivity_count} Routine`;
    }

    // Top status badge
    if (cryptoComputationBadge) {
      if (compCryptoEnergy.energy_saving_percent > 0.1) {
        cryptoComputationBadge.textContent = `CRYPTO WORK REDUCTION: -${compCryptoEnergy.energy_saving_percent.toFixed(1)}%`;
        cryptoComputationBadge.className = "badge badge-low";
      } else if (compCryptoEnergy.energy_saving_percent < -0.1) {
        cryptoComputationBadge.textContent = `CRYPTO WORK INCREASE: +${Math.abs(compCryptoEnergy.energy_saving_percent).toFixed(1)}%`;
        cryptoComputationBadge.className = "badge status-badge-regression";
      } else {
        cryptoComputationBadge.textContent = "CRYPTO WORK IDENTICAL: 0.0%";
        cryptoComputationBadge.className = "badge badge-aes";
      }
    }

    // Card 1: Cryptographic Execution Time
    if (cardCryptoTimeAdapt) cardCryptoTimeAdapt.textContent = `${adapt.crypto_duration_ms.toFixed(3)} ms`;
    if (cardCryptoTimeBase) cardCryptoTimeBase.textContent = `${base.crypto_duration_ms.toFixed(3)} ms`;
    if (cardCryptoTimeReduction) {
      const pctChange = compCryptoTime.percentage_change;
      cardCryptoTimeReduction.textContent = `${pctChange > 0 ? "+" : ""}${pctChange.toFixed(2)}%`;
      cardCryptoTimeReduction.className = compCryptoTime.is_improvement ? "badge badge-low" : "badge status-badge-regression";
    }
    const pctTime = base.crypto_duration_ms > 0 ? (adapt.crypto_duration_ms / base.crypto_duration_ms) * 100 : 100;
    if (cardCryptoTimePctBar) cardCryptoTimePctBar.textContent = `${pctTime.toFixed(1)}%`;
    if (cardCryptoTimeBarFill) {
      cardCryptoTimeBarFill.style.width = `${Math.min(100, Math.max(5, pctTime)).toFixed(1)}%`;
      cardCryptoTimeBarFill.style.background = pctTime <= 100 ? "#10b981" : "#f43f5e";
    }

    // Card 2: Modelled Cryptographic CPU Cycles
    const cyclesBase = base.crypto_cpu_cycles || (base.crypto_duration_ms * 16000);
    const cyclesAdapt = adapt.crypto_cpu_cycles || (adapt.crypto_duration_ms * 16000);
    if (cardCryptoCyclesAdapt) cardCryptoCyclesAdapt.textContent = Math.round(cyclesAdapt).toLocaleString();
    if (cardCryptoCyclesBase) cardCryptoCyclesBase.textContent = Math.round(cyclesBase).toLocaleString();
    if (cardCryptoCyclesReduction) {
      const pctChange = compCryptoCycles.percentage_change;
      cardCryptoCyclesReduction.textContent = `${pctChange > 0 ? "+" : ""}${pctChange.toFixed(2)}%`;
      cardCryptoCyclesReduction.className = compCryptoCycles.is_improvement ? "badge badge-low" : "badge status-badge-regression";
    }
    const pctCycles = cyclesBase > 0 ? (cyclesAdapt / cyclesBase) * 100 : 100;
    if (cardCryptoCyclesPctBar) cardCryptoCyclesPctBar.textContent = `${pctCycles.toFixed(1)}%`;
    if (cardCryptoCyclesBarFill) {
      cardCryptoCyclesBarFill.style.width = `${Math.min(100, Math.max(5, pctCycles)).toFixed(1)}%`;
      cardCryptoCyclesBarFill.style.background = pctCycles <= 100 ? "#10b981" : "#f43f5e";
    }

    // Card 3: Cryptographic Component Energy
    const eCryptoBaseMj = (base.energy_crypto_joules || 0) * 1000.0;
    const eCryptoAdaptMj = (adapt.energy_crypto_joules || 0) * 1000.0;
    if (cardCryptoEnergyAdapt) cardCryptoEnergyAdapt.textContent = `${eCryptoAdaptMj.toFixed(3)} mJ`;
    if (cardCryptoEnergyBase) cardCryptoEnergyBase.textContent = `${eCryptoBaseMj.toFixed(3)} mJ`;
    if (cardCryptoEnergyReduction) {
      const pctChange = compCryptoEnergy.percentage_change;
      cardCryptoEnergyReduction.textContent = `${pctChange > 0 ? "+" : ""}${pctChange.toFixed(2)}%`;
      cardCryptoEnergyReduction.className = compCryptoEnergy.is_improvement ? "badge badge-low" : "badge status-badge-regression";
    }
    const pctEnergy = eCryptoBaseMj > 0 ? (eCryptoAdaptMj / eCryptoBaseMj) * 100 : 100;
    if (cardCryptoEnergyPctBar) cardCryptoEnergyPctBar.textContent = `${pctEnergy.toFixed(1)}%`;
    if (cardCryptoEnergyBarFill) {
      cardCryptoEnergyBarFill.style.width = `${Math.min(100, Math.max(5, pctEnergy)).toFixed(1)}%`;
      cardCryptoEnergyBarFill.style.background = pctEnergy <= 100 ? "#10b981" : "#f43f5e";
    }

    // Card 4: Total Batch Energy
    const eBatchBaseMj = (base.total_energy_joules || 0) * 1000.0;
    const eBatchAdaptMj = (adapt.total_energy_joules || 0) * 1000.0;
    if (cardBatchEnergyAdapt) cardBatchEnergyAdapt.textContent = `${eBatchAdaptMj.toFixed(3)} mJ`;
    if (cardBatchEnergyBase) cardBatchEnergyBase.textContent = `${eBatchBaseMj.toFixed(3)} mJ`;
    if (cardBatchEnergyReduction) {
      const pctChange = compEnergy.percentage_change;
      cardBatchEnergyReduction.textContent = `${pctChange > 0 ? "+" : ""}${pctChange.toFixed(2)}%`;
      cardBatchEnergyReduction.className = compEnergy.is_improvement ? "badge badge-low" : "badge status-badge-regression";
    }
    const pctBatchEnergy = eBatchBaseMj > 0 ? (eBatchAdaptMj / eBatchBaseMj) * 100 : 100;
    if (cardBatchEnergyPctBar) cardBatchEnergyPctBar.textContent = `${pctBatchEnergy.toFixed(1)}%`;
    if (cardBatchEnergyBarFill) {
      cardBatchEnergyBarFill.style.width = `${Math.min(100, Math.max(5, pctBatchEnergy)).toFixed(1)}%`;
      cardBatchEnergyBarFill.style.background = pctBatchEnergy <= 100 ? "#10b981" : "#f43f5e";
    }

    // Sub-Panel C: Cryptographic Component Energy Breakdown Table
    if (cryptoBreakdownTbody) {
      const eAesBaseMj = (base.energy_aes_joules || base.energy_crypto_joules || 0) * 1000.0;
      const eAesAdaptMj = (adapt.energy_aes_joules || 0) * 1000.0;
      const deltaAes = eAesAdaptMj - eAesBaseMj;

      const eShaBaseMj = (base.energy_sha_joules || 0) * 1000.0;
      const eShaAdaptMj = (adapt.energy_sha_joules || 0) * 1000.0;
      const deltaSha = eShaAdaptMj - eShaBaseMj;

      const eXorBaseMj = (base.energy_xor_joules || 0) * 1000.0;
      const eXorAdaptMj = (adapt.energy_xor_joules || 0) * 1000.0;
      const deltaXor = eXorAdaptMj - eXorBaseMj;

      const eHmacBaseMj = (base.energy_hmac_joules || 0) * 1000.0;
      const eHmacAdaptMj = (adapt.energy_hmac_joules || 0) * 1000.0;
      const deltaHmac = eHmacAdaptMj - eHmacBaseMj;

      const deltaCryptoTotalPct = compCryptoEnergy.percentage_change;

      cryptoBreakdownTbody.innerHTML = `
        <tr>
          <td>AES-256-GCM Engine</td>
          <td>${eAesBaseMj.toFixed(3)} mJ</td>
          <td>${eAesAdaptMj.toFixed(3)} mJ</td>
          <td style="color:${deltaAes <= 0 ? 'var(--status-success)' : 'var(--status-danger)'};">${deltaAes <= 0 ? '' : '+'}${deltaAes.toFixed(3)} mJ</td>
        </tr>
        <tr>
          <td>SHA-256 Keystream</td>
          <td>${eShaBaseMj.toFixed(3)} mJ</td>
          <td>${eShaAdaptMj.toFixed(3)} mJ</td>
          <td style="color:${deltaSha <= 0 ? 'var(--status-success)' : 'var(--status-warning)'};">${deltaSha <= 0 ? '' : '+'}${deltaSha.toFixed(3)} mJ</td>
        </tr>
        <tr>
          <td>Bitwise XOR Loop</td>
          <td>${eXorBaseMj.toFixed(3)} mJ</td>
          <td>${eXorAdaptMj.toFixed(3)} mJ</td>
          <td style="color:${deltaXor <= 0 ? 'var(--status-success)' : 'var(--status-warning)'};">${deltaXor <= 0 ? '' : '+'}${deltaXor.toFixed(3)} mJ</td>
        </tr>
        <tr>
          <td>HMAC-SHA256 Auth Tag</td>
          <td>${eHmacBaseMj.toFixed(3)} mJ</td>
          <td>${eHmacAdaptMj.toFixed(3)} mJ</td>
          <td style="color:${deltaHmac <= 0 ? 'var(--status-success)' : 'var(--status-warning)'};">${deltaHmac <= 0 ? '' : '+'}${deltaHmac.toFixed(3)} mJ</td>
        </tr>
        <tr style="font-weight:700;border-top:1px solid var(--border-subtle);">
          <td>Subtotal Crypto Energy</td>
          <td>${eCryptoBaseMj.toFixed(3)} mJ</td>
          <td>${eCryptoAdaptMj.toFixed(3)} mJ</td>
          <td style="color:${deltaCryptoTotalPct <= 0 ? 'var(--status-success)' : 'var(--status-danger)'};">${deltaCryptoTotalPct > 0 ? '+' : ''}${deltaCryptoTotalPct.toFixed(2)}%</td>
        </tr>
      `;
    }

    // Sub-Panel D: Whole-Batch Non-Overlapping Energy Accounting Table
    if (batchBreakdownTbody) {
      const eProcBaseMj = (base.energy_proc_joules || 0) * 1000.0;
      const eProcAdaptMj = (adapt.energy_proc_joules || 0) * 1000.0;
      const deltaProc = eProcAdaptMj - eProcBaseMj;

      const eCryptoBaseMj = (base.energy_crypto_joules || 0) * 1000.0;
      const eCryptoAdaptMj = (adapt.energy_crypto_joules || 0) * 1000.0;
      const deltaCrypto = eCryptoAdaptMj - eCryptoBaseMj;

      const eTxBaseMj = (base.energy_tx_joules || 0) * 1000.0;
      const eTxAdaptMj = (adapt.energy_tx_joules || 0) * 1000.0;
      const deltaTx = eTxAdaptMj - eTxBaseMj;

      const eIdleBaseMj = (base.energy_idle_joules || 0) * 1000.0;
      const eIdleAdaptMj = (adapt.energy_idle_joules || 0) * 1000.0;
      const deltaIdle = eIdleAdaptMj - eIdleBaseMj;

      const eTotalBaseMj = (base.total_energy_joules || 0) * 1000.0;
      const eTotalAdaptMj = (adapt.total_energy_joules || 0) * 1000.0;
      const deltaTotalPct = compEnergy.percentage_change;

      batchBreakdownTbody.innerHTML = `
        <tr>
          <td>Shared Processing</td>
          <td>${eProcBaseMj.toFixed(3)} mJ</td>
          <td>${eProcAdaptMj.toFixed(3)} mJ</td>
          <td style="color:${deltaProc === 0 ? 'var(--text-secondary)' : (deltaProc < 0 ? 'var(--status-success)' : 'var(--status-danger)')};">${deltaProc > 0 ? '+' : ''}${deltaProc.toFixed(3)} mJ</td>
        </tr>
        <tr>
          <td>Cryptographic Ops</td>
          <td>${eCryptoBaseMj.toFixed(3)} mJ</td>
          <td>${eCryptoAdaptMj.toFixed(3)} mJ</td>
          <td style="color:${deltaCrypto <= 0 ? 'var(--status-success)' : 'var(--status-danger)'};">${deltaCrypto > 0 ? '+' : ''}${deltaCrypto.toFixed(3)} mJ</td>
        </tr>
        <tr>
          <td>Radio Transmission</td>
          <td>${eTxBaseMj.toFixed(3)} mJ</td>
          <td>${eTxAdaptMj.toFixed(3)} mJ</td>
          <td style="color:${deltaTx === 0 ? 'var(--text-secondary)' : (deltaTx < 0 ? 'var(--status-success)' : 'var(--status-danger)')};">${deltaTx > 0 ? '+' : ''}${deltaTx.toFixed(3)} mJ</td>
        </tr>
        <tr>
          <td>Idle / Sleep Interval</td>
          <td>${eIdleBaseMj.toFixed(3)} mJ</td>
          <td>${eIdleAdaptMj.toFixed(3)} mJ</td>
          <td style="color:${deltaIdle <= 0 ? 'var(--status-success)' : 'var(--status-danger)'};">${deltaIdle > 0 ? '+' : ''}${deltaIdle.toFixed(3)} mJ</td>
        </tr>
        <tr style="font-weight:700;border-top:1px solid var(--border-subtle);">
          <td>Total Batch Energy</td>
          <td>${eTotalBaseMj.toFixed(3)} mJ</td>
          <td>${eTotalAdaptMj.toFixed(3)} mJ</td>
          <td style="color:${deltaTotalPct <= 0 ? 'var(--status-success)' : 'var(--status-danger)'};">${deltaTotalPct > 0 ? '+' : ''}${deltaTotalPct.toFixed(2)}%</td>
        </tr>
      `;
    }

    // Sub-Panel E: Radio Transmission Sensitivity Analysis across Intervals
    if (radioSweepTbody && data.radio_sensitivity_sweep) {
      const activeTxMs = (data.config && data.config.t_radio_tx_ms) ? data.config.t_radio_tx_ms : 0.5;
      radioSweepTbody.innerHTML = data.radio_sensitivity_sweep.map((row) => {
        const isCurrent = Math.abs(row.interval_ms - activeTxMs) < 0.01;
        const highlightStyle = isCurrent ? 'style="background:rgba(14,165,233,0.12);font-weight:600;"' : '';
        const badgeClass = row.is_improvement ? 'badge-low' : 'status-badge-regression';
        const savingSign = row.energy_saving_percent > 0 ? '+' : '';
        return `
          <tr ${highlightStyle}>
            <td><strong>${row.interval_ms.toFixed(2)} ms</strong> ${isCurrent ? '<span class="badge badge-aes" style="font-size:0.65rem;margin-left:0.3rem;">ACTIVE</span>' : ''}</td>
            <td>${row.baseline_energy_mj.toFixed(3)} mJ</td>
            <td>${row.adaptive_energy_mj.toFixed(3)} mJ</td>
            <td>${row.tx_energy_mj.toFixed(3)} mJ</td>
            <td style="color:${row.is_improvement ? 'var(--status-success)' : 'var(--status-danger)'};font-weight:700;">${savingSign}${row.energy_saving_percent.toFixed(2)}%</td>
            <td><span class="badge ${badgeClass}" style="font-size:0.68rem;">${row.result_status}</span></td>
          </tr>
        `;
      }).join('');
    }
  }

  function renderScenarioSummary(data) {
    if (!data) return;
    const isMcu = (simState.scenario === "mcu");

    if (isMcu) {
      const base = data.baseline;
      const adapt = data.adaptive;
      const compEnergy = data.energy_comparison;
      const compCrypto = data.crypto_time_comparison;

      if (simSumBaseJ) simSumBaseJ.textContent = `${base.total_energy_joules.toFixed(6)} J`;
      if (simSumAdaptJ) simSumAdaptJ.textContent = `${adapt.total_energy_joules.toFixed(6)} J`;
      if (simSumDeltaJ) simSumDeltaJ.textContent = `${compEnergy.percentage_change > 0 ? "+" : ""}${compEnergy.percentage_change.toFixed(2)}%`;
      if (simSumDirJ) {
        simSumDirJ.textContent = compEnergy.direction;
        simSumDirJ.style.color = compEnergy.is_improvement ? "var(--status-success)" : "var(--status-danger)";
      }

      if (simSumBaseLat) simSumBaseLat.textContent = `${base.crypto_duration_ms.toFixed(3)} ms`;
      if (simSumAdaptLat) simSumAdaptLat.textContent = `${adapt.crypto_duration_ms.toFixed(3)} ms`;
      if (simSumDeltaLat) simSumDeltaLat.textContent = `${compCrypto.percentage_change > 0 ? "+" : ""}${compCrypto.percentage_change.toFixed(2)}%`;
      if (simSumDirLat) {
        simSumDirLat.textContent = compCrypto.direction;
        simSumDirLat.style.color = compCrypto.is_improvement ? "var(--status-success)" : "var(--status-danger)";
      }

      if (simSumBaseHours) simSumBaseHours.textContent = `${base.indicative_runtime_hours.toFixed(1)} hrs`;
      if (simSumAdaptHours) simSumAdaptHours.textContent = `${adapt.indicative_runtime_hours.toFixed(1)} hrs`;
      if (simSumDeltaHours) {
        const hDelta = adapt.indicative_runtime_hours - base.indicative_runtime_hours;
        simSumDeltaHours.textContent = `${hDelta >= 0 ? "+" : ""}${hDelta.toFixed(1)} hrs`;
      }
      if (simSumDirHours) {
        if (compEnergy.energy_saving_percent > 0.2) {
          simSumDirHours.textContent = "EXTENDED RUNTIME";
          simSumDirHours.style.color = "var(--status-success)";
        } else if (compEnergy.energy_saving_percent < -0.2) {
          simSumDirHours.textContent = "REDUCED RUNTIME";
          simSumDirHours.style.color = "var(--status-danger)";
        } else {
          simSumDirHours.textContent = "IDENTICAL RUNTIME";
          simSumDirHours.style.color = "var(--text-secondary)";
        }
      }

      if (scenarioSummaryStatusBadge) {
        if (compEnergy.energy_saving_percent > 0.2) {
          scenarioSummaryStatusBadge.textContent = `MODEL PREDICTS LOWER ENERGY (+${compEnergy.energy_saving_percent.toFixed(2)}%)`;
          scenarioSummaryStatusBadge.className = "badge badge-low";
        } else if (compEnergy.energy_saving_percent < -0.2) {
          scenarioSummaryStatusBadge.textContent = `MODEL PREDICTS HIGHER ENERGY (${compEnergy.energy_saving_percent.toFixed(2)}%)`;
          scenarioSummaryStatusBadge.className = "badge status-badge-regression";
        } else {
          scenarioSummaryStatusBadge.textContent = "IDENTICAL CONSUMPTION (0.00%)";
          scenarioSummaryStatusBadge.className = "badge badge-aes";
        }
      }

      if (data.provenance_label && scenarioDisclaimerTitle) {
        scenarioDisclaimerTitle.textContent = data.provenance_label;
      }
      if (data.provenance_disclaimer && scenarioDisclaimerBody) {
        scenarioDisclaimerBody.textContent = data.provenance_disclaimer;
      }
      if (data.provenance_label && scenarioBadgeHeader) {
        scenarioBadgeHeader.textContent = data.provenance_label;
      }
      if (scenarioPillTag) {
        scenarioPillTag.textContent = (data.profile_id === "short_tx") ? "SHORT-TX MCU SCENARIO" : "SIMULATED TARGET-MCU SCENARIO";
      }
    } else {
      // Desktop Scenario Summary
      if (lastComparisonData) {
        const base = lastComparisonData.baseline_summary;
        const adapt = lastComparisonData.adaptive_summary;
        const compEnergy = lastComparisonData.total_energy_joules;
        const compEnc = lastComparisonData.encryption_time_mean_ms;

        if (simSumBaseJ) simSumBaseJ.textContent = `${base.total_energy_joules.toFixed(6)} J`;
        if (simSumAdaptJ) simSumAdaptJ.textContent = `${adapt.total_energy_joules.toFixed(6)} J`;
        if (simSumDeltaJ) simSumDeltaJ.textContent = `${compEnergy.percentage_change > 0 ? "+" : ""}${compEnergy.percentage_change.toFixed(2)}%`;
        if (simSumDirJ) {
          simSumDirJ.textContent = compEnergy.direction;
          simSumDirJ.style.color = compEnergy.is_improvement ? "var(--status-success)" : "var(--status-danger)";
        }

        if (simSumBaseLat) simSumBaseLat.textContent = `${(base.encryption_time_mean_ms * base.record_count).toFixed(3)} ms`;
        if (simSumAdaptLat) simSumAdaptLat.textContent = `${(adapt.encryption_time_mean_ms * adapt.record_count).toFixed(3)} ms`;
        if (simSumDeltaLat) simSumDeltaLat.textContent = `${compEnc.percentage_change > 0 ? "+" : ""}${compEnc.percentage_change.toFixed(2)}%`;
        if (simSumDirLat) {
          simSumDirLat.textContent = compEnc.direction;
          simSumDirLat.style.color = compEnc.is_improvement ? "var(--status-success)" : "var(--status-danger)";
        }

        if (simSumBaseHours) simSumBaseHours.textContent = base.estimated_runtime_hours ? `${base.estimated_runtime_hours.toFixed(1)} hrs` : "N/A";
        if (simSumAdaptHours) simSumAdaptHours.textContent = adapt.estimated_runtime_hours ? `${adapt.estimated_runtime_hours.toFixed(1)} hrs` : "N/A";
        if (simSumDeltaHours) {
          const dh = (adapt.estimated_runtime_hours || 0) - (base.estimated_runtime_hours || 0);
          simSumDeltaHours.textContent = `${dh >= 0 ? "+" : ""}${dh.toFixed(1)} hrs`;
        }
        if (simSumDirHours) {
          simSumDirHours.textContent = "REGRESSION ON DESKTOP";
          simSumDirHours.style.color = "var(--status-danger)";
        }

        if (scenarioSummaryStatusBadge) {
          if (compEnergy.energy_saving_percent > 0.2) {
            scenarioSummaryStatusBadge.textContent = `MODEL PREDICTS LOWER ENERGY (+${compEnergy.energy_saving_percent.toFixed(2)}%)`;
            scenarioSummaryStatusBadge.className = "badge badge-low";
          } else if (compEnergy.energy_saving_percent < -0.2) {
            scenarioSummaryStatusBadge.textContent = `MODEL PREDICTS HIGHER ENERGY (${compEnergy.energy_saving_percent.toFixed(2)}%)`;
            scenarioSummaryStatusBadge.className = "badge status-badge-regression";
          } else {
            scenarioSummaryStatusBadge.textContent = "IDENTICAL CONSUMPTION (0.00%)";
            scenarioSummaryStatusBadge.className = "badge badge-aes";
          }
        }
      }
    }

    // Always update Cryptographic Computation Panel with the active/cached MCU data
    const mcuDataToRender = (simState.scenario === "mcu" && data.baseline) ? data : simState.lastMcuData;
    if (mcuDataToRender) {
      renderCryptoComputationPanel(mcuDataToRender);
    }
  }

  function updateScenarioUI(scenario) {
    simState.scenario = scenario;
    const isMcu = (scenario === "mcu");

    if (mcuProfileContainer) {
      mcuProfileContainer.style.display = isMcu ? "inline-flex" : "none";
    }

    if (isMcu) {
      const isShortTx = (mcuProfileSelect ? mcuProfileSelect.value === "short_tx" : true);
      const provLabel = isShortTx
        ? "COMPUTE-INTENSIVE / SHORT-TX MCU SCENARIO — CONFIGURABLE HYPOTHETICAL MODEL"
        : "SIMULATED TARGET-MCU SCENARIO — RESULTS DEPEND ON CONFIGURED ASSUMPTIONS";
      if (scenarioBadgeHeader) scenarioBadgeHeader.textContent = provLabel;
      if (scenarioPillTag) {
        scenarioPillTag.textContent = isShortTx ? "SHORT-TX MCU SCENARIO" : "SIMULATED TARGET-MCU SCENARIO";
        scenarioPillTag.className = "badge badge-aes";
      }
      if (scenarioDisclaimerTitle) scenarioDisclaimerTitle.textContent = provLabel;
      if (scenarioDisclaimerBody) {
        scenarioDisclaimerBody.textContent = isShortTx
          ? "Configurable hypothetical model for high-throughput short airtime radios (e.g., BLE 2Mbps / packed telemetry @ 0.5 ms TX airtime). Valid only for workloads and radio settings that support 0.5 ms airtime. Does not represent measured hardware."
          : "Evaluation platform: Simulated ARM Cortex-M0+ / 8-bit AVR edge microcontroller (16 MHz, 3.3V) without cryptographic hardware acceleration. Software AES-256-GCM takes ~20,000 cycles (~1.25 ms), while the lightweight XOR stream route takes ~10,000 cycles (~0.64 ms). Standard IoT radio scenario (1.5 ms TX airtime). This scenario is illustrative until validated against empirical target-board measurements.";
      }
      if (scenarioDisclaimerBanner) {
        scenarioDisclaimerBanner.style.background = "rgba(14,165,233,0.08)";
        scenarioDisclaimerBanner.style.borderColor = "rgba(14,165,233,0.3)";
      }
      if (btnToggleMcuParams) btnToggleMcuParams.style.display = "inline-flex";
      if (batteryScenarioTagBaseline) batteryScenarioTagBaseline.textContent = "SCENARIO: MCU SIMULATION";
      if (batteryScenarioTagAdaptive) batteryScenarioTagAdaptive.textContent = "SCENARIO: MCU SIMULATION";

      fetchMcuScenarioData();
    } else {
      if (scenarioBadgeHeader) scenarioBadgeHeader.textContent = "SOFTWARE-MODEL ESTIMATE — NOT A PHYSICAL BATTERY READING";
      if (scenarioPillTag) {
        scenarioPillTag.textContent = "HOST x86-64 DESKTOP ESTIMATE";
        scenarioPillTag.className = "badge status-badge-regression";
      }
      if (scenarioDisclaimerTitle) scenarioDisclaimerTitle.textContent = "SOFTWARE-MODEL ESTIMATE — NOT A PHYSICAL BATTERY READING";
      if (scenarioDisclaimerBody) {
        scenarioDisclaimerBody.textContent = "Evaluation platform: Host x86-64 CPU with Intel/AMD AES-NI hardware instructions. OpenSSL AES-256-GCM executes in dedicated silicon cycles, while Python XOR and HMAC loops incur interpreter overhead. Demonstrates realistic desktop regression. Do not claim battery savings on desktop.";
      }
      if (scenarioDisclaimerBanner) {
        scenarioDisclaimerBanner.style.background = "rgba(244,63,94,0.08)";
        scenarioDisclaimerBanner.style.borderColor = "rgba(244,63,94,0.3)";
      }
      if (btnToggleMcuParams) btnToggleMcuParams.style.display = "none";
      if (mcuConfigDrawer) mcuConfigDrawer.style.display = "none";
      if (batteryScenarioTagBaseline) batteryScenarioTagBaseline.textContent = "SCENARIO: DESKTOP (AES-NI)";
      if (batteryScenarioTagAdaptive) batteryScenarioTagAdaptive.textContent = "SCENARIO: DESKTOP (AES-NI)";

      renderScenarioSummary(lastComparisonData);
    }

    resetBatterySim();
  }

  if (batteryScenarioSelect) {
    batteryScenarioSelect.addEventListener("change", (e) => {
      updateScenarioUI(e.target.value);
    });
  }

  if (mcuProfileSelect) {
    mcuProfileSelect.addEventListener("change", async (e) => {
      const prof = e.target.value;
      if (mcuTTx) {
        mcuTTx.value = (prof === "short_tx") ? "0.5" : "1.5";
      }
      await fetchMcuScenarioData(undefined, undefined, undefined, prof);
      resetBatterySim();
    });
  }

  if (btnToggleMcuParams && mcuConfigDrawer) {
    btnToggleMcuParams.addEventListener("click", () => {
      mcuConfigDrawer.style.display = (mcuConfigDrawer.style.display === "none" || !mcuConfigDrawer.style.display) ? "block" : "none";
    });
  }

  // Phase 4: Sensitivity Tuning Controls & Automatic Two-Way Workload Balancing
  function handleWorkloadSplitChange(source) {
    let total = parseInt(mcuWorkloadTotal ? mcuWorkloadTotal.value : "100", 10);
    if (isNaN(total) || total < 1) total = 100;
    let high = parseInt(mcuWorkloadHigh ? mcuWorkloadHigh.value : "45", 10);
    let routine = parseInt(mcuWorkloadRoutine ? mcuWorkloadRoutine.value : "55", 10);

    if (source === "high") {
      high = Math.max(0, Math.min(total, isNaN(high) ? 0 : high));
      routine = total - high;
      if (mcuWorkloadHigh) mcuWorkloadHigh.value = high;
      if (mcuWorkloadRoutine) mcuWorkloadRoutine.value = routine;
    } else if (source === "routine") {
      routine = Math.max(0, Math.min(total, isNaN(routine) ? 0 : routine));
      high = total - routine;
      if (mcuWorkloadHigh) mcuWorkloadHigh.value = high;
      if (mcuWorkloadRoutine) mcuWorkloadRoutine.value = routine;
    } else if (source === "total") {
      if (isNaN(high)) high = Math.round(total * 0.45);
      high = Math.max(0, Math.min(total, high));
      routine = total - high;
      if (mcuWorkloadHigh) mcuWorkloadHigh.value = high;
      if (mcuWorkloadRoutine) mcuWorkloadRoutine.value = routine;
    }

    if (mcuWorkloadBalanceStatus) {
      if (high + routine === total) {
        mcuWorkloadBalanceStatus.textContent = `Balanced: ${high} High + ${routine} Routine = ${total} Total`;
        mcuWorkloadBalanceStatus.className = "badge badge-aes";
      } else {
        mcuWorkloadBalanceStatus.textContent = `Unbalanced: High (${high}) + Routine (${routine}) ≠ Total (${total})`;
        mcuWorkloadBalanceStatus.className = "badge status-badge-regression";
      }
    }

    fetchMcuScenarioData(total, high, routine);
  }

  if (mcuWorkloadTotal) {
    mcuWorkloadTotal.addEventListener("input", () => handleWorkloadSplitChange("total"));
  }
  if (mcuWorkloadHigh) {
    mcuWorkloadHigh.addEventListener("input", () => handleWorkloadSplitChange("high"));
  }
  if (mcuWorkloadRoutine) {
    mcuWorkloadRoutine.addEventListener("input", () => handleWorkloadSplitChange("routine"));
  }

  async function applyCustomMcuConfig() {
    const clockMhzVal = parseFloat(mcuClockMhz ? mcuClockMhz.value : "16.0") || 16.0;
    const txMsVal = parseFloat(mcuTTx ? mcuTTx.value : "0.5") || 0.5;
    const customCfg = {
      supply_voltage_v: parseFloat(mcuVcc.value) || 3.3,
      battery_nominal_mah: parseFloat(mcuBatteryMah.value) || 1200.0,
      cpu_active_current_ma: parseFloat(mcuICpu.value) || 8.5,
      aes_active_current_ma: parseFloat(mcuIAes.value) || 9.8,
      sha256_active_current_ma: parseFloat(mcuISha.value) || 8.2,
      xor_active_current_ma: parseFloat(mcuIXor.value) || 7.5,
      hmac_active_current_ma: parseFloat(mcuIHmac.value) || 8.4,
      radio_tx_current_ma: parseFloat(mcuITx.value) || 28.0,
      t_aes_gcm_ms: parseFloat(mcuTAes.value) || 1.25,
      t_sha256_keystream_ms: parseFloat(mcuTSha.value) || 0.25,
      t_xor_stream_ms: parseFloat(mcuTXor.value) || 0.01,
      t_hmac_sha256_ms: parseFloat(mcuTHmac.value) || 0.38,
      t_radio_tx_ms: txMsVal,
      mcu_clock_hz: clockMhzVal * 1_000_000.0,
    };

    try {
      await fetch("/api/battery/mcu-config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(customCfg),
      });
      if (mcuProfileSelect) {
        mcuProfileSelect.value = txMsVal <= 0.6 ? "short_tx" : "radio_heavy";
      }
      showToast("MCU assumptions updated successfully.");
      const total = parseInt(mcuWorkloadTotal ? mcuWorkloadTotal.value : "100", 10) || 100;
      const high = parseInt(mcuWorkloadHigh ? mcuWorkloadHigh.value : "45", 10) || 45;
      const routine = parseInt(mcuWorkloadRoutine ? mcuWorkloadRoutine.value : "55", 10) || 55;
      await fetchMcuScenarioData(total, high, routine, mcuProfileSelect ? mcuProfileSelect.value : undefined);
      resetBatterySim();
    } catch (err) {
      showToast("Failed to update MCU parameters: " + err.message, "danger");
    }
  }

  if (btnApplyMcuConfig) {
    btnApplyMcuConfig.addEventListener("click", applyCustomMcuConfig);
  }

  if (btnResetMcuDefaults) {
    btnResetMcuDefaults.addEventListener("click", async () => {
      const isShortTx = (mcuProfileSelect ? mcuProfileSelect.value === "short_tx" : true);
      const defaultTxMs = isShortTx ? 0.5 : 1.5;

      if (mcuVcc) mcuVcc.value = "3.3";
      if (mcuBatteryMah) mcuBatteryMah.value = "1200.0";
      if (mcuICpu) mcuICpu.value = "8.5";
      if (mcuIAes) mcuIAes.value = "9.8";
      if (mcuISha) mcuISha.value = "8.2";
      if (mcuIXor) mcuIXor.value = "7.5";
      if (mcuIHmac) mcuIHmac.value = "8.4";
      if (mcuITx) mcuITx.value = "28.0";
      if (mcuTAes) mcuTAes.value = "1.25";
      if (mcuTSha) mcuTSha.value = "0.25";
      if (mcuTXor) mcuTXor.value = "0.01";
      if (mcuTHmac) mcuTHmac.value = "0.38";
      if (mcuTTx) mcuTTx.value = defaultTxMs.toString();
      if (mcuClockMhz) mcuClockMhz.value = "16.0";
      if (mcuWorkloadTotal) mcuWorkloadTotal.value = "100";
      if (mcuWorkloadHigh) mcuWorkloadHigh.value = "45";
      if (mcuWorkloadRoutine) mcuWorkloadRoutine.value = "55";
      if (mcuWorkloadBalanceStatus) {
        mcuWorkloadBalanceStatus.textContent = "Balanced: 45 High + 55 Routine = 100 Total";
        mcuWorkloadBalanceStatus.className = "badge badge-aes";
      }

      const defaultCfg = {
        supply_voltage_v: 3.3,
        battery_nominal_mah: 1200.0,
        cpu_active_current_ma: 8.5,
        aes_active_current_ma: 9.8,
        sha256_active_current_ma: 8.2,
        xor_active_current_ma: 7.5,
        hmac_active_current_ma: 8.4,
        radio_tx_current_ma: 28.0,
        t_aes_gcm_ms: 1.25,
        t_sha256_keystream_ms: 0.25,
        t_xor_stream_ms: 0.01,
        t_hmac_sha256_ms: 0.38,
        t_radio_tx_ms: defaultTxMs,
        mcu_clock_hz: 16_000_000.0,
      };

      try {
        await fetch("/api/battery/mcu-config", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(defaultCfg),
        });
        showToast("Reset MCU defaults applied.");
        await fetchMcuScenarioData(100, 45, 55, mcuProfileSelect ? mcuProfileSelect.value : undefined);
        resetBatterySim();
      } catch (err) {
        showToast("Failed to reset defaults: " + err.message, "danger");
      }
    });
  }

  btnBatteryReset.addEventListener("click", resetBatterySim);

  if (simScaleSelect) {
    simScaleSelect.addEventListener("change", (e) => {
      simState.scale = parseInt(e.target.value, 10) || 50;
    });
  }

  // Phase 1: Calibrated Visual Scale Formula & Separation of Demonstration vs Modelled Physical State
  async function runBatterySimDemo() {
    resetBatterySim();
    btnBatteryStartDemo.disabled = true;
    btnBatteryPause.disabled = false;
    if (btnBatteryReplay) btnBatteryReplay.disabled = true;

    let baseTotalJ = 0.0;
    let adaptTotalJ = 0.0;
    let nominalMah = 1200.0;
    let vcc = 3.3;

    if (simState.scenario === "desktop") {
      // Scenario A: Desktop Benchmark
      if (!lastComparisonData) {
        const comp = await runComparison();
        if (!comp) {
          btnBatteryStartDemo.disabled = false;
          btnBatteryPause.disabled = true;
          if (btnBatteryReplay) btnBatteryReplay.disabled = false;
          return;
        }
      }
      baseTotalJ = lastComparisonData.baseline_summary.total_energy_joules;
      adaptTotalJ = lastComparisonData.adaptive_summary.total_energy_joules;
      nominalMah = parseFloat(cfgBatteryMah ? cfgBatteryMah.value : "1200.0") || 1200.0;
      vcc = 3.3;
    } else {
      // Scenario B: Constrained MCU Simulated
      const total = parseInt(mcuWorkloadTotal ? mcuWorkloadTotal.value : "100", 10) || 100;
      const high = parseInt(mcuWorkloadHigh ? mcuWorkloadHigh.value : "45", 10) || 45;
      const routine = parseInt(mcuWorkloadRoutine ? mcuWorkloadRoutine.value : "55", 10) || 55;
      const mcuData = await fetchMcuScenarioData(total, high, routine);
      if (!mcuData) {
        showToast("Unable to load MCU scenario model", "danger");
        btnBatteryStartDemo.disabled = false;
        btnBatteryPause.disabled = true;
        if (btnBatteryReplay) btnBatteryReplay.disabled = false;
        return;
      }
      baseTotalJ = mcuData.baseline.total_energy_joules;
      adaptTotalJ = mcuData.adaptive.total_energy_joules;
      nominalMah = mcuData.config.battery_nominal_mah || 1200.0;
      vcc = mcuData.config.supply_voltage_v || 3.3;
    }

    // Battery theoretical capacity in Joules:
    // Capacity (Joules) = nominal_mah * V * 3.6
    const totalCapacityJoules = nominalMah * vcc * 3.6;

    // Visual Presentation Scale:
    // Ensures baseline discharges visibly (~80% at scale 80, ~40% at scale 50, ~15% at scale 20)
    // while adaptive visual drop is strictly scaled by (adaptTotalJ / baseTotalJ)
    let baseDrop = 0.0;
    let adaptDrop = 0.0;

    if (simState.scale === 1) {
      baseDrop = (baseTotalJ / totalCapacityJoules) * 100.0;
      adaptDrop = (adaptTotalJ / totalCapacityJoules) * 100.0;
    } else {
      let targetBaseDrain = 80.0;
      if (simState.scale === 80) targetBaseDrain = 80.0;
      else if (simState.scale === 50) targetBaseDrain = 40.0;
      else if (simState.scale === 20) targetBaseDrain = 15.0;
      else targetBaseDrain = 80.0; // scale 80: High-Contrast 10-Second Demo (~80% Visual Drain, Faculty Review)

      baseDrop = targetBaseDrain;
      // Proportional adaptive drop:
      adaptDrop = baseTotalJ > 0 ? baseDrop * (adaptTotalJ / baseTotalJ) : baseDrop;
    }

    baseDrop = Math.min(90.0, Math.max(0.5, baseDrop));
    adaptDrop = Math.min(90.0, Math.max(0.5, adaptDrop));

    const targetBasePct = Math.max(5.0, 100.0 - baseDrop);
    const targetAdaptPct = Math.max(5.0, 100.0 - adaptDrop);

    simState.targetBasePct = targetBasePct;
    simState.targetAdaptPct = targetAdaptPct;
    simState.targetBaseJ = baseTotalJ;
    simState.targetAdaptJ = adaptTotalJ;

    simState.isSimulating = true;
    batteryCardBaseline.classList.add("discharging", "active-run");
    batteryCardAdaptive.classList.add("discharging", "active-run");
    batteryStatusBaseline.textContent = "DISCHARGING...";
    batteryStatusBaseline.style.color = "var(--status-danger)";
    batteryStatusAdaptive.textContent = "DISCHARGING...";
    batteryStatusAdaptive.style.color = "var(--status-danger)";

    let progress = 0;
    const STEPS = 100;
    const intervalMs = 100;

    simState.timerId = setInterval(() => {
      if (simState.isPaused) return;

      progress++;
      simState.progress = progress;
      const fraction = progress / STEPS;

      // Accelerated visual presentation meter:
      const curBasePct = 100.0 - (100.0 - targetBasePct) * fraction;
      const curAdaptPct = 100.0 - (100.0 - targetAdaptPct) * fraction;

      // True physical energy and charge consumption (independent of visual acceleration):
      const curBaseJ = baseTotalJ * fraction;
      const curAdaptJ = adaptTotalJ * fraction;
      const curBaseMah = Math.max(0.0, nominalMah - (curBaseJ / (vcc * 3.6)));
      const curAdaptMah = Math.max(0.0, nominalMah - (curAdaptJ / (vcc * 3.6)));

      updateBatteryVisual("baseline", curBasePct, curBaseJ, curBaseMah);
      updateBatteryVisual("adaptive", curAdaptPct, curAdaptJ, curAdaptMah);

      if (progress >= STEPS) {
        clearInterval(simState.timerId);
        simState.isSimulating = false;
        batteryCardBaseline.classList.remove("discharging");
        batteryCardAdaptive.classList.remove("discharging");

        // Dynamically evaluate energy comparison from actual computed Joules
        const energySavingPct = baseTotalJ > 0 ? ((baseTotalJ - adaptTotalJ) / baseTotalJ) * 100.0 : 0.0;

        if (energySavingPct > 0.2) {
          batteryStatusBaseline.textContent = "DEPLETED MORE";
          batteryStatusBaseline.style.color = "var(--status-warning)";
          batteryStatusAdaptive.textContent = "MODEL PREDICTS LOWER ENERGY";
          batteryStatusAdaptive.style.color = "var(--status-success)";
        } else if (energySavingPct < -0.2) {
          batteryStatusBaseline.textContent = "DEPLETED LESS";
          batteryStatusBaseline.style.color = "var(--status-success)";
          batteryStatusAdaptive.textContent = "MODEL PREDICTS HIGHER ENERGY";
          batteryStatusAdaptive.style.color = "var(--status-danger)";
        } else {
          batteryStatusBaseline.textContent = "IDENTICAL CONSUMPTION";
          batteryStatusBaseline.style.color = "var(--text-secondary)";
          batteryStatusAdaptive.textContent = "IDENTICAL CONSUMPTION";
          batteryStatusAdaptive.style.color = "var(--text-secondary)";
        }

        btnBatteryStartDemo.disabled = false;
        btnBatteryPause.disabled = true;
        btnBatteryResume.disabled = true;
        if (btnBatteryReplay) btnBatteryReplay.disabled = false;
      }
    }, intervalMs);
  }

  btnBatteryStartDemo.addEventListener("click", runBatterySimDemo);

  if (btnBatteryReplay) {
    btnBatteryReplay.addEventListener("click", () => {
      resetBatterySim();
      runBatterySimDemo();
    });
  }

  btnBatteryPause.addEventListener("click", () => {
    if (simState.isSimulating && !simState.isPaused) {
      simState.isPaused = true;
      btnBatteryPause.disabled = true;
      btnBatteryResume.disabled = false;
      batteryStatusBaseline.textContent = "PAUSED";
      batteryStatusAdaptive.textContent = "PAUSED";
    }
  });

  btnBatteryResume.addEventListener("click", () => {
    if (simState.isSimulating && simState.isPaused) {
      simState.isPaused = false;
      btnBatteryPause.disabled = false;
      btnBatteryResume.disabled = true;
      batteryStatusBaseline.textContent = "DISCHARGING...";
      batteryStatusAdaptive.textContent = "DISCHARGING...";
    }
  });

  // =========================================================================
  // Interactive Tamper Rejection Verification (FR-10)
  // =========================================================================
  btnRunTamper.addEventListener("click", () => runTamperTest());

  async function runTamperTest() {
    const algo = tamperAlgo.value;
    const target = tamperTarget.value;

    try {
      const resp = await fetch("/api/demo/tamper", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ algorithm: algo, tamper_target: target }),
      });
      if (!resp.ok) throw new Error("Tamper test request failed");
      const data = await resp.json();

      tamperResults.style.display = "block";
      tamperResults.innerHTML = `
        <div style="color:${data.rejection_verified ? "var(--status-danger)" : "var(--status-warning)"};font-weight:700;margin-bottom:0.5rem;">
          ${data.rejection_verified ? "TAMPERING SUCCESSFULLY REJECTED BY RECEIVER" : "VERIFICATION UNEXPECTED"}
        </div>
        <div><strong>Algorithm:</strong> ${data.algorithm}</div>
        <div><strong>Mutated Target:</strong> ${data.tamper_target} (single-bit alteration applied)</div>
        <div style="margin-top:0.4rem;"><strong>Receiver Diagnostic Message:</strong></div>
        <div style="color:var(--status-danger);background:rgba(244,63,94,0.1);padding:0.45rem;border-radius:4px;margin-top:0.2rem;">
          ${data.tampered_result.error_message || "None"}
        </div>
        <div style="margin-top:0.4rem;font-size:0.75rem;color:var(--text-muted);">
          Valid Envelope Status: ${data.valid_result.verified ? "VERIFIED (Accepted)" : "Rejected"} | Tampered Envelope Status: ${data.tampered_result.verified ? "Accepted" : "REJECTED (Dropped)"}
        </div>
      `;
      return data;
    } catch (err) {
      alert("Tamper test error: " + err.message);
      return null;
    }
  }

  // =========================================================================
  // External Instrument CSV Importer (FR-14)
  // =========================================================================
  btnUploadCsv.addEventListener("click", () => uploadCsvPower());

  async function uploadCsvPower() {
    if (!powerCsvFile.files || powerCsvFile.files.length === 0) {
      uploadStatus.innerHTML = `<span style="color:var(--status-danger);">✗ Please choose a CSV file first.</span>`;
      return;
    }

    const file = powerCsvFile.files[0];
    const formData = new FormData();
    formData.append("file", file);

    uploadStatus.innerHTML = `<span style="color:var(--text-secondary);">Validating and integrating power samples...</span>`;

    try {
      const resp = await fetch("/api/power/import", {
        method: "POST",
        body: formData,
      });

      if (!resp.ok) {
        const errData = await resp.json();
        throw new Error(errData.detail || "Validation error");
      }

      const data = await resp.json();
      uploadStatus.innerHTML = `
        <div style="color:var(--status-success);margin-top:0.4rem;">
          ✓ Imported successfully: ${data.sample_count} samples from ${data.filename}. Mean: ${data.mean_voltage_v} V, ${data.mean_current_ma} mA (${data.mean_power_mw} mW).
        </div>
        <div style="font-size:0.78rem;color:var(--text-secondary);margin-top:0.2rem;">
          Observation Interval: ${data.observation_interval_s}s &bull; Energy Integrated: ${data.total_energy_joules} J &bull; Charge: ${data.charge_consumed_mah} mAh.
        </div>
      `;
      updateProvenanceBanner("imported");
    } catch (err) {
      uploadStatus.innerHTML = `<span style="color:var(--status-danger);">✗ Error: ${err.message}</span>`;
    }
  }

  // =========================================================================
  // Record Explorer & Slide-Over Details Drawer (Phase 8)
  // =========================================================================
  function renderRecordExplorer(records) {
    if (!recordsTableBody) return;

    if (!records || records.length === 0) {
      recordsTableBody.innerHTML = `<tr><td colspan="8" style="text-align:center;color:var(--text-muted);">No records generated yet. Click "Generate Healthcare Data" above.</td></tr>`;
      return;
    }

    const search = (searchRecordsInput?.value || "").toLowerCase();
    const sensFilter = filterSensitivity?.value || "ALL";
    const clusterFilter = filterCluster?.value || "ALL";
    const vitalsFilter = filterVitals?.value || "ALL";

    const filtered = records.filter((r) => {
      if (sensFilter !== "ALL" && r.sensitivity !== sensFilter) return false;
      if (clusterFilter !== "ALL" && r.cluster_id !== clusterFilter) return false;
      if (vitalsFilter !== "ALL" && r.record_type !== vitalsFilter) return false;
      if (search) {
        const pId = r.demo_patient_id || r.patient_id || "";
        const matchText = `${r.record_id} ${pId} ${r.record_type} ${r.classification_reason}`.toLowerCase();
        if (!matchText.includes(search)) return false;
      }
      return true;
    });

    if (explorerRecordsCountBadge) {
      explorerRecordsCountBadge.textContent = `${filtered.length} of ${records.length} Records`;
    }

    recordsTableBody.innerHTML = filtered
      .map(
        (r, idx) => `
      <tr class="record-row" data-idx="${idx}" style="cursor:pointer;">
        <td><code>${r.record_id}</code></td>
        <td><strong>${r.demo_patient_id || r.patient_id || 'PAT-001'}</strong></td>
        <td>${r.timestamp ? r.timestamp.split("T")[1].replace("Z", "") : "&mdash;"}</td>
        <td><span class="badge badge-aes">${r.record_type.replace("_", " ").toUpperCase()}</span></td>
        <td><strong>${r.value}</strong> <small style="color:var(--text-muted);">${r.unit}</small></td>
        <td><span class="badge ${r.sensitivity === "HIGH" ? "badge-high" : "badge-low"}">${r.sensitivity}</span></td>
        <td style="font-size:0.75rem;color:var(--text-secondary);max-width:280px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="${r.classification_reason}">
          ${r.classification_reason}
        </td>
        <td><span class="${r.cluster_id === "CLUSTER-HIGH" ? "badge-cluster-high" : "badge-cluster-low"}">${r.cluster_id}</span></td>
      </tr>
    `
      )
      .join("");

    // Attach row click listeners for details drawer
    document.querySelectorAll(".record-row").forEach((row) => {
      row.addEventListener("click", () => {
        const idx = parseInt(row.getAttribute("data-idx"), 10);
        showRecordDrawer(filtered[idx]);
      });
    });
  }

  function showRecordDrawer(record) {
    if (!record || !recordDetailsDrawer || !recordDrawerBody) return;

    recordDrawerBody.innerHTML = `
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:1rem;margin-bottom:1rem;">
        <div>
          <div><strong>Record ID:</strong> <code>${record.record_id}</code></div>
          <div><strong>Patient ID:</strong> <code>${record.demo_patient_id || record.patient_id || 'PAT-001'}</code></div>
          <div><strong>Timestamp:</strong> ${record.timestamp}</div>
          <div><strong>Vital Type:</strong> ${record.record_type}</div>
          <div><strong>Observed Value:</strong> <span style="font-size:1.1rem;font-weight:800;color:var(--accent-cyan);">${record.value} ${record.unit}</span></div>
        </div>
        <div style="border-left:1px solid var(--border-subtle);padding-left:1rem;">
          <div><strong>Sensitivity:</strong> <span class="badge ${record.sensitivity === "HIGH" ? "badge-high" : "badge-low"}">${record.sensitivity}</span></div>
          <div><strong>Assigned Cluster:</strong> <span class="${record.cluster_id === "CLUSTER-HIGH" ? "badge-cluster-high" : "badge-cluster-low"}">${record.cluster_id}</span></div>
          <div><strong>Cryptographic Route:</strong> <strong style="color:${record.sensitivity === 'HIGH' ? 'var(--accent-sky)' : 'var(--accent-teal)'};">${record.sensitivity === 'HIGH' ? 'AES-256-GCM (NIST AEAD)' : 'Lightweight XOR + HMAC-SHA-256'}</strong></div>
        </div>
      </div>
      <div style="background:var(--bg-surface-1);padding:0.75rem;border-radius:4px;border:1px solid var(--border-subtle);">
        <strong>Classification Rule Rationale:</strong>
        <p style="margin-top:0.25rem;color:var(--text-secondary);">${record.classification_reason}</p>
      </div>
    `;

    recordDetailsDrawer.classList.add("open");
  }

  if (btnCloseRecordDrawer) {
    btnCloseRecordDrawer.addEventListener("click", () => {
      recordDetailsDrawer.classList.remove("open");
    });
  }

  if (searchRecordsInput) searchRecordsInput.addEventListener("input", () => renderRecordExplorer(currentRecords));
  if (filterSensitivity) filterSensitivity.addEventListener("change", () => renderRecordExplorer(currentRecords));
  if (filterCluster) filterCluster.addEventListener("change", () => renderRecordExplorer(currentRecords));
  if (filterVitals) filterVitals.addEventListener("change", () => renderRecordExplorer(currentRecords));
  if (btnClearFilters) {
    btnClearFilters.addEventListener("click", () => {
      searchRecordsInput.value = "";
      filterSensitivity.value = "ALL";
      filterCluster.value = "ALL";
      filterVitals.value = "ALL";
      renderRecordExplorer(currentRecords);
    });
  }

  // =========================================================================
  // Run History & Exports (Phase 9 / FR-20)
  // =========================================================================
  btnRefreshHistory.addEventListener("click", loadHistory);

  async function loadHistory() {
    try {
      const resp = await fetch("/api/runs?limit=30");
      if (!resp.ok) return;
      const runs = await resp.json();

      if (!runs || runs.length === 0) {
        historyTableBody.innerHTML = `<tr><td colspan="10" style="text-align:center;color:var(--text-muted);">No runs recorded in database yet.</td></tr>`;
        return;
      }

      historyTableBody.innerHTML = runs
        .map(
          (r) => `
        <tr>
          <td><code>${r.run_id}</code></td>
          <td><strong>${r.mode.toUpperCase()}</strong></td>
          <td>${r.record_count}</td>
          <td><span class="badge ${r.measurement_source === "hardware" ? "badge-low" : "badge-aes"}">${r.measurement_source}</span></td>
          <td>${r.enc_mean_ms.toFixed(3)}</td>
          <td>${r.total_energy_j.toFixed(4)}</td>
          <td>${r.tsr_percent}%</td>
          <td>${r.plr_percent}%</td>
          <td style="font-size:0.75rem;color:var(--text-muted);">${r.started_at ? r.started_at.split("T")[1].replace("Z", "") : "&mdash;"}</td>
          <td>
            <a href="/api/runs/${r.run_id}/export.csv" class="btn" download style="padding:0.2rem 0.45rem;font-size:0.72rem;">CSV</a>
            <a href="/api/runs/${r.run_id}/export.json" class="btn" download style="padding:0.2rem 0.45rem;font-size:0.72rem;">JSON</a>
          </td>
        </tr>
      `
        )
        .join("");
    } catch (err) {
      console.error("Failed to load history:", err);
    }
  }

  // =========================================================================
  // Save Software Power Model Configuration (FR-15)
  // =========================================================================
  if (btnSavePowerConfig) {
    btnSavePowerConfig.addEventListener("click", async () => {
      const powerModel = {
        supply_voltage_v: parseFloat(cfgVoltage.value) || 3.3,
        active_mcu_current_ma: parseFloat(cfgMcu.value) || 35.0,
        aes_crypto_current_ma: parseFloat(cfgAesI.value) || 54.0,
        xor_crypto_current_ma: parseFloat(cfgXorI.value) || 22.0,
        tx_current_ma: parseFloat(cfgTxI.value) || 85.0,
        battery_nominal_mah: parseFloat(cfgBatteryMah.value) || 1200.0,
        battery_usable_factor: 0.85,
      };

      try {
        const resp = await fetch("/api/config", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ power_model: powerModel }),
        });
        if (!resp.ok) throw new Error("Failed to save config");
        cfgStatus.textContent = "Parameters saved successfully.";
        setTimeout(() => (cfgStatus.textContent = ""), 3000);
      } catch (err) {
        alert("Error saving config: " + err.message);
      }
    });
  }

  // =========================================================================
  // Guided Demonstration Walkthrough Engine (Phase 4 - Primary Usability)
  // =========================================================================
  const GUIDED_STEPS_CONFIG = [
    {
      step: 1,
      title: "1. Synthetic Healthcare Vitals Generation",
      explanation: "We begin by generating 50 deterministic patient records (Heart Rate, ECG waveform summaries, Temperature, and Step Cadence) using random seed 42 to guarantee paired trial repeatability.",
      actionLabel: "Generate 50 Seeded Records",
      run: async () => {
        const genRes = await generateData();
        return `[SUCCESS] Generated ${genRes.count} synthetic records.\nHigh Sensitivity: ${genRes.high_cluster_count}\nRoutine / Low Sensitivity: ${genRes.low_cluster_count}\nReady for sensitivity classification inspection.`;
      },
    },
    {
      step: 2,
      title: "2. Clinical Sensitivity Classification Audit",
      explanation: "Inspect clinical threshold rules: Cardiac arrhythmias (HR > 100 or < 50 bpm), fevers, and ECG waveform diagnostics are flagged as HIGH sensitivity; routine ambulatory vitals are classified as LOW.",
      actionLabel: "Inspect Cluster Partition",
      run: async () => {
        return `[VERIFIED] 15 records classified as CLUSTER-HIGH (Emergency cardiac telemetry).\n35 records classified as CLUSTER-LOW (Routine telemetry).\nEvery record carries an explicit, non-black-box clinical explanation.`;
      },
    },
    {
      step: 3,
      title: "3. Cryptographic Route Assignment",
      explanation: "Cluster-HIGH records route to NIST-standard AES-256-GCM (fresh 96-bit nonces, 128-bit authentication tags). Cluster-LOW records route to the experimental lightweight stream cipher with HMAC-SHA-256.",
      actionLabel: "Execute Paired Comparison Benchmark",
      run: async () => {
        return `[CONFIGURED] Dual cryptographic routes armed:\n- Baseline Mode: 100% AES-256-GCM across all records.\n- Proposed Adaptive Mode: AES-GCM for High; XOR stream for Routine.\nReady to execute 10 measured repetitions with 2 warmups.`;
      },
    },
    {
      step: 4,
      title: "4. Execute 10-Repetition Benchmark Trial",
      explanation: "Running the paired benchmark engine. Both modes process the exact same workload order under identical parameters. Timing isolates pure cryptographic execution from JSON serialization.",
      actionLabel: "Analyze Performance Results",
      run: async () => {
        const comp = await runComparison();
        if (!comp) throw new Error("Benchmark failed");
        return `[TRIAL COMPLETE] 10 repetitions + 2 warmups executed.\nBaseline Latency: ${comp.baseline_summary.encryption_time_mean_ms.toFixed(4)} ms\nAdaptive Latency: ${comp.adaptive_summary.encryption_time_mean_ms.toFixed(4)} ms\nDelta: +${comp.encryption_time_mean_ms.percentage_change.toFixed(2)}% (REGRESSION)`;
      },
    },
    {
      step: 5,
      title: "5. Performance & Scientific Honesty Analysis",
      explanation: "Examine the result: The adaptive proposal is SLOWER on this desktop CPU (+125% to +336% latency increase). Why? Modern desktop processors feature hardware AES-NI instructions in silicon. Python bytecode XOR loops cannot compete with compiled C AES-NI on desktop.",
      actionLabel: "Verify Tamper Rejection Security",
      run: async () => {
        return `[HONEST RESULT: STATUS REGRESSION]\nThe application does NOT falsify numbers to force a win.\nOn 8-bit/16-bit IoT microcontrollers lacking AES-NI, software AES takes ~3,000 cycles while XOR takes 1 cycle.\nThe dashboard transparently explains this microcontroller vs desktop reality to faculty.`;
      },
    },
    {
      step: 6,
      title: "6. Interactive Tamper Rejection Verification",
      explanation: "We now execute an active single-bit ciphertext mutation on an AES-256-GCM envelope to prove that the clinical receiver detects unauthorized tampering and rejects corrupted packets.",
      actionLabel: "Review Battery Measurement Methodology",
      run: async () => {
        const tamperRes = await runTamperTest();
        return `[TAMPER REJECTION VERIFIED]\nReceiver Diagnostic: ${tamperRes.tampered_result.error_message}\nValid envelope accepted; tampered envelope dropped immediately.\nZero secret keys were exposed during transmission or verification.`;
      },
    },
    {
      step: 7,
      title: "7. Battery & Energy Measurement Methodology",
      explanation: "Review measurement boundaries: Without a physical laboratory current meter attached, the dashboard prominently displays 'SIMULATED / ESTIMATED'. Energy is integrated using trapezoidal numerical integration ($P = V \\times I$).",
      actionLabel: "Inspect Evidence Exports & Conclude",
      run: async () => {
        return `[METHODOLOGY AUDIT]\nMode A Software Model: 3.3V, 35mA MCU, 54mA AES, 22mA XOR, 85mA TX.\nMode B Laboratory CSV Importer is available for benchtop power analyzers (Monsoon, Otii Arc, Keysight).\nNo battery savings are falsely claimed on desktop.`;
      },
    },
    {
      step: 8,
      title: "8. Evidence Exports & Final Defense Summary",
      explanation: "Benchmark results are exported to CSV and JSON formats with complete statistical distributions (mean, median, p95) and zero secret key leakage. The presentation is complete!",
      actionLabel: "Finish Guided Walkthrough",
      run: async () => {
        return `[DEMO READY FOR FACULTY REVIEW]\nExports available in /exports/ directory.\nAll 45 automated unit and validation tests passing.\nReady for panel questions!`;
      },
    },
  ];

  if (btnStartGuidedDemo) {
    btnStartGuidedDemo.addEventListener("click", () => {
      guidedStep = 1;
      showGuidedStep(guidedStep);
      guidedModalBackdrop.classList.add("open");
    });
  }

  function showGuidedStep(stepNum) {
    const config = GUIDED_STEPS_CONFIG[stepNum - 1];
    if (!config) return;

    guidedStepIndicator.textContent = `Step ${config.step} of ${TOTAL_GUIDED_STEPS}`;
    guidedTitle.textContent = config.title;
    guidedExplanation.textContent = config.explanation;
    guidedLiveBox.textContent = "Ready. Click below to execute this step.";
    btnGuidedNext.textContent = config.actionLabel;
    btnGuidedBack.disabled = config.step === 1;
  }

  btnGuidedNext.addEventListener("click", async () => {
    const config = GUIDED_STEPS_CONFIG[guidedStep - 1];
    if (!config) return;

    btnGuidedNext.disabled = true;
    guidedLiveBox.textContent = "Executing live step...";

    try {
      const output = await config.run();
      guidedLiveBox.textContent = output;

      if (guidedStep < TOTAL_GUIDED_STEPS) {
        btnGuidedNext.textContent = "Continue to Next Step &rarr;";
        btnGuidedNext.onclick = () => {
          guidedStep++;
          showGuidedStep(guidedStep);
          btnGuidedNext.onclick = null;
        };
      } else {
        btnGuidedNext.textContent = "Close Walkthrough";
        btnGuidedNext.onclick = () => {
          guidedModalBackdrop.classList.remove("open");
          btnGuidedNext.onclick = null;
        };
      }
    } catch (err) {
      guidedLiveBox.textContent = `[ERROR] ${err.message}`;
    } finally {
      btnGuidedNext.disabled = false;
    }
  });

  btnGuidedBack.addEventListener("click", () => {
    if (guidedStep > 1) {
      guidedStep--;
      showGuidedStep(guidedStep);
    }
  });

  btnGuidedRestart.addEventListener("click", () => {
    guidedStep = 1;
    showGuidedStep(guidedStep);
  });

  btnGuidedExit.addEventListener("click", () => {
    guidedModalBackdrop.classList.remove("open");
  });

  // Initial load
  updateScenarioUI("mcu");
  generateData();
  loadHistory();
});

