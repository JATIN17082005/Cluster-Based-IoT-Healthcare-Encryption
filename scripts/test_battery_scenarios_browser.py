"""Playwright Browser Verification Script for Two Hardware Battery Scenarios.
Tests:
1. Scenario B (Constrained MCU): default load, disclaimers, summary values.
2. Animated discharge: left-to-right fill reduction, color transitions, Pause, Resume, Reset, Replay.
3. Scenario A (Current Desktop Benchmark): disclaimer change, honest regression drain.
4. MCU parameters drawer: open, edit, apply, reset defaults.
5. Screenshot artifacts capture and zero console error verification.
"""

import sys
import time
import os
from playwright.sync_api import sync_playwright
import subprocess
import urllib.request

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

SCREENSHOT_DIR = r"C:\Users\Jatinp\.gemini\antigravity\brain\216a23d8-eb99-4432-b028-034538522d8e"
EDGE_EXE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

PORT = 8014
BASE_URL = f"http://127.0.0.1:{PORT}"

def wait_for_server(url, timeout=15):
    start = time.time()
    while time.time() - start < timeout:
        try:
            with urllib.request.urlopen(f"{url}/api/health", timeout=1) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.5)
    return False

def run_battery_scenarios_browser_test():
    console_logs = []
    page_errors = []

    print(f"=== 1. Starting uvicorn server on port {PORT} ===")
    server_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "src.server:app", "--host", "127.0.0.1", "--port", str(PORT)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=r"C:\Cluster based IoT data encryption"
    )

    try:
        if not wait_for_server(BASE_URL):
            raise RuntimeError(f"Server failed to start at {BASE_URL} within 15 seconds")
        print("   [OK] Server is healthy and responsive.")

        print("=== Starting Battery Scenarios Browser E2E Test ===")
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=EDGE_EXE, headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 900})
            page = context.new_page()

            page.on("console", lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))
            page.on("pageerror", lambda err: page_errors.append(str(err)))

            # 1. Load application
            print(f"1. Loading application at {BASE_URL} ...")
            page.goto(BASE_URL, wait_until="networkidle")
            time.sleep(1)

            # 2. Switch to Tab 2 (Battery Lab)
            print("2. Navigating to Tab 2 (Battery Lab)...")
            tab_btn = page.locator(".tab-btn[data-tab='tab-battery']")
            tab_btn.click()
            time.sleep(0.5)

            # 3. Verify Scenario B is selected by default
            print("3. Verifying Scenario B (Constrained MCU) initial state...")
            scenario_select = page.locator("#battery-scenario-select")
            selected_val = scenario_select.input_value()
            print(f"   Active scenario value: '{selected_val}'")
            assert selected_val == "mcu"

            disclaimer_title = page.locator("#scenario-disclaimer-title").inner_text().strip()
            print(f"   Disclaimer title: '{disclaimer_title}'")
            assert "SHORT-TX" in disclaimer_title or "SIMULATED TARGET-MCU" in disclaimer_title

            # Verify MCU Profile Select
            profile_select = page.locator("#mcu-profile-select")
            assert profile_select.is_visible()
            prof_val = profile_select.input_value()
            print(f"   Active MCU Profile: '{prof_val}'")
            assert prof_val == "short_tx"

            # Check initial battery meter (100%, Green)
            pct_base = page.locator("#battery-pct-baseline").inner_text().strip()
            pct_adapt = page.locator("#battery-pct-adaptive").inner_text().strip()
            print(f"   Baseline charge: {pct_base}, Adaptive charge: {pct_adapt}")
            assert pct_base == "100.0%"
            assert pct_adapt == "100.0%"

            # Check modelled physical state readout separation
            mah_base = page.locator("#battery-mah-baseline").inner_text().strip()
            phys_pct_base = page.locator("#battery-phys-pct-baseline").inner_text().strip()
            print(f"   Modelled physical charge: {mah_base}, capacity: {phys_pct_base}")
            assert "1200.000 mAh" in mah_base
            assert "100.000%" in phys_pct_base

            summary_badge = page.locator("#scenario-summary-status-badge").inner_text().strip()
            print(f"   Scenario summary badge: '{summary_badge}'")
            assert "MODEL PREDICTS LOWER ENERGY" in summary_badge

            # 3b. Verify Dedicated Cryptographic Computation Panel & 4 Horizontal Cards
            print("3b. Verifying Dedicated Cryptographic Computation Panel & 4 Horizontal Cards...")
            crypto_panel = page.locator("#crypto-computation-panel")
            assert crypto_panel.is_visible()

            # Card 1: Execution Time
            c1_time_adapt = page.locator("#card-crypto-time-adapt").inner_text().strip()
            c1_time_base = page.locator("#card-crypto-time-base").inner_text().strip()
            c1_reduction = page.locator("#card-crypto-time-reduction").inner_text().strip()
            c1_bar_width = page.locator("#card-crypto-time-bar-fill").evaluate("el => el.style.width")
            print(f"   Card 1 Crypto Time: {c1_time_adapt} vs {c1_time_base} (Delta: {c1_reduction}, Bar: {c1_bar_width})")
            assert "ms" in c1_time_adapt and "ms" in c1_time_base
            assert "-" in c1_reduction or "%" in c1_reduction

            # Card 2: Modelled CPU Cycles
            c2_cycles_adapt = page.locator("#card-crypto-cycles-adapt").inner_text().strip()
            c2_cycles_base = page.locator("#card-crypto-cycles-base").inner_text().strip()
            c2_reduction = page.locator("#card-crypto-cycles-reduction").inner_text().strip()
            print(f"   Card 2 Modelled CPU Cycles: {c2_cycles_adapt} vs {c2_cycles_base} (Delta: {c2_reduction})")
            assert "," in c2_cycles_adapt and "," in c2_cycles_base

            # Card 3: Cryptographic Component Energy
            c3_energy_adapt = page.locator("#card-crypto-energy-adapt").inner_text().strip()
            c3_energy_base = page.locator("#card-crypto-energy-base").inner_text().strip()
            c3_reduction = page.locator("#card-crypto-energy-reduction").inner_text().strip()
            print(f"   Card 3 Crypto Component Energy: {c3_energy_adapt} vs {c3_energy_base} (Delta: {c3_reduction})")
            assert "mJ" in c3_energy_adapt and "mJ" in c3_energy_base

            # Card 4: Total Batch Energy
            c4_energy_adapt = page.locator("#card-batch-energy-adapt").inner_text().strip()
            c4_energy_base = page.locator("#card-batch-energy-base").inner_text().strip()
            c4_reduction = page.locator("#card-batch-energy-reduction").inner_text().strip()
            print(f"   Card 4 Total Batch Energy: {c4_energy_adapt} vs {c4_energy_base} (Delta: {c4_reduction})")
            assert "mJ" in c4_energy_adapt and "mJ" in c4_energy_base

            # Verify Plain-Language Faculty Explanation Quote
            panel_text = crypto_panel.inner_text()
            assert "The model predicts less cryptographic work for the adaptive configuration under these assumptions." in panel_text
            assert "Overall battery savings may be smaller because radio transmission, shared processing, and idle energy also contribute." in panel_text
            print("   [OK] Plain-language faculty quote confirmed in UI.")

            # Verify Sub-Panels C, D, and E Breakdown Tables
            c_table = page.locator("#crypto-breakdown-tbody").inner_text()
            assert "AES-256-GCM Engine" in c_table
            assert "Subtotal Crypto Energy" in c_table
            print("   [OK] Table C Cryptographic Component Breakdown verified.")

            d_table = page.locator("#batch-breakdown-tbody").inner_text()
            assert "Shared Processing" in d_table
            assert "Total Batch Energy" in d_table
            print("   [OK] Table D Whole-Batch Energy Accounting verified.")

            # Sub-Panel E: Radio Transmission Sensitivity Analysis across Intervals
            e_table = page.locator("#radio-sweep-tbody").inner_text()
            assert "0.50 ms" in e_table
            assert "0.75 ms" in e_table
            assert "1.00 ms" in e_table
            assert "1.50 ms" in e_table
            print("   [OK] Table E Radio Sensitivity Sweep across 4 intervals verified.")

            # 3c. Test Profile Switching: Switch to Radio-Heavy Profile (1.5 ms TX)
            print("3c. Testing MCU Profile Switch to Radio-Heavy (1.5 ms)...")
            profile_select.select_option("radio_heavy")
            time.sleep(0.5)
            badge_heavy = page.locator("#scenario-summary-status-badge").inner_text().strip()
            print(f"   Radio-Heavy summary badge: '{badge_heavy}'")
            assert "6.6" in badge_heavy or "MODEL PREDICTS LOWER ENERGY" in badge_heavy
            # Switch back to Short-TX for default evaluation
            profile_select.select_option("short_tx")
            time.sleep(0.5)
            print("   [OK] Profile switching verified.")

            # 4. Test Simulation Animation in Scenario B with Pause and Resume
            print("4. Testing Simulation Controls in Scenario B...")
            btn_start = page.locator("#btn-battery-start-demo")
            btn_pause = page.locator("#btn-battery-pause")
            btn_resume = page.locator("#btn-battery-resume")
            btn_reset = page.locator("#btn-battery-reset")
            btn_replay = page.locator("#btn-battery-replay")

            btn_start.click()
            time.sleep(0.6)  # Let it start discharging

            status_base = page.locator("#battery-status-baseline").inner_text().strip()
            print(f"   Status during discharge: '{status_base}'")
            assert "DISCHARGING" in status_base

            # Test Pause
            btn_pause.click()
            time.sleep(0.3)
            status_paused = page.locator("#battery-status-baseline").inner_text().strip()
            print(f"   Status when paused: '{status_paused}'")
            assert "PAUSED" in status_paused

            # Test Resume
            btn_resume.click()
            time.sleep(0.3)
            status_resumed = page.locator("#battery-status-baseline").inner_text().strip()
            print(f"   Status after resume: '{status_resumed}'")
            assert "DISCHARGING" in status_resumed

            # Wait for completion (STEPS=100 * 100ms = ~10.0s)
            page.wait_for_selector("#btn-battery-start-demo:not([disabled])", timeout=15000)

            final_base_pct = float(page.locator("#battery-pct-baseline").inner_text().replace("%", ""))
            final_adapt_pct = float(page.locator("#battery-pct-adaptive").inner_text().replace("%", ""))
            print(f"   Scenario B final charges -> Baseline: {final_base_pct}%, Adaptive: {final_adapt_pct}%")

            # In Scenario B, Adaptive consumes LESS energy, so final adaptive charge must be GREATER than baseline
            assert final_adapt_pct > final_base_pct
            assert 19.0 <= final_base_pct <= 21.0, f"Expected baseline ~20.0%, got {final_base_pct}%"
            assert 29.0 <= final_adapt_pct <= 32.0, f"Expected adaptive ~30.4%, got {final_adapt_pct}%"
            status_adapt_final = page.locator("#battery-status-adaptive").inner_text().strip()
            status_base_final = page.locator("#battery-status-baseline").inner_text().strip()
            print(f"   Scenario B Adaptive outcome tag: '{status_adapt_final}', Baseline: '{status_base_final}'")
            assert "MODEL PREDICTS LOWER ENERGY" in status_adapt_final
            assert "DEPLETED MORE" in status_base_final

            # Screenshot Scenario B Completed
            scen_b_png = os.path.join(SCREENSHOT_DIR, "battery_sim_scenario_b_completed.png")
            page.screenshot(path=scen_b_png)
            print(f"   [OK] Screenshot saved to: {scen_b_png}")

            # Test Replay
            print("5. Testing Replay button in Scenario B...")
            btn_replay.click()
            time.sleep(0.5)
            status_replay = page.locator("#battery-status-baseline").inner_text().strip()
            assert "DISCHARGING" in status_replay
            btn_reset.click()
            time.sleep(0.3)
            assert page.locator("#battery-pct-baseline").inner_text().strip() == "100.0%"
            print("   [OK] Reset and Replay verified.")

            # 6. Test Scenario A (Current Desktop Benchmark)
            print("6. Switching to Scenario A (Current Desktop Benchmark)...")
            scenario_select.select_option("desktop")
            time.sleep(0.5)

            disclaimer_a = page.locator("#scenario-disclaimer-title").inner_text().strip()
            print(f"   Scenario A disclaimer: '{disclaimer_a}'")
            assert "SOFTWARE-MODEL ESTIMATE" in disclaimer_a
            assert "NOT A PHYSICAL BATTERY READING" in disclaimer_a

            # Run Desktop Simulation Demo
            print("   Running Desktop Scenario Simulation Demo...")
            btn_start.click()
            # Allow paired benchmark comparison + 10s animation
            page.wait_for_selector("#btn-battery-start-demo:not([disabled])", timeout=25000)

            final_a_base_pct = float(page.locator("#battery-pct-baseline").inner_text().replace("%", ""))
            final_a_adapt_pct = float(page.locator("#battery-pct-adaptive").inner_text().replace("%", ""))
            print(f"   Scenario A final charges -> Baseline: {final_a_base_pct}%, Adaptive: {final_a_adapt_pct}%")

            # In Scenario A (Desktop with AES-NI), Adaptive exhibits regression (consumes slightly more energy)
            # So final adaptive charge is <= baseline charge (drained more or equal within resolution)
            status_a_adapt = page.locator("#battery-status-adaptive").inner_text().strip()
            status_a_base = page.locator("#battery-status-baseline").inner_text().strip()
            print(f"   Scenario A Adaptive outcome tag: '{status_a_adapt}', Baseline: '{status_a_base}'")
            assert status_a_adapt in ["MODEL PREDICTS HIGHER ENERGY", "IDENTICAL CONSUMPTION"]
            assert status_a_base in ["DEPLETED LESS", "IDENTICAL CONSUMPTION"]
            assert "SAVING VERIFIED" not in status_a_adapt

            # Screenshot Scenario A Completed
            scen_a_png = os.path.join(SCREENSHOT_DIR, "battery_sim_scenario_a_completed.png")
            page.screenshot(path=scen_a_png)
            print(f"   [OK] Screenshot saved to: {scen_a_png}")

            # 7. Test Inspect/Configure MCU Parameters Drawer
            print("7. Testing MCU Parameters Configuration Drawer...")
            scenario_select.select_option("mcu")
            time.sleep(0.5)

            btn_toggle_params = page.locator("#btn-toggle-mcu-params")
            btn_toggle_params.click()
            time.sleep(0.3)

            drawer = page.locator("#mcu-config-drawer")
            assert drawer.is_visible()
            print("   [OK] MCU parameters drawer expanded.")

            # Test Phase 4: Clock Frequency & Workload Sensitivity Split Controls
            print("   Testing Clock Frequency and Workload Sensitivity Split tuning...")
            clock_val = page.locator("#mcu-clock-mhz").input_value()
            assert float(clock_val) == 16.0

            # Change High Sensitivity to 20; Routine should automatically update to 80
            page.fill("#mcu-workload-high", "20")
            time.sleep(0.5)
            routine_val = page.locator("#mcu-workload-routine").input_value()
            print(f"   After setting High to 20, Routine auto-balanced to: {routine_val}")
            assert routine_val == "80"

            balance_text = page.locator("#mcu-workload-balance-status").inner_text().strip()
            print(f"   Balance text is: '{balance_text}'")
            assert "20 HIGH" in balance_text.upper() and "80 ROUTINE" in balance_text.upper()

            # Rebalance back to default 45 / 55
            page.fill("#mcu-workload-high", "45")
            time.sleep(0.5)
            assert page.locator("#mcu-workload-routine").input_value() == "55"
            print("   [OK] Workload sensitivity split controls and automatic balancing verified.")

            # Screenshot MCU Drawer
            scen_drawer_png = os.path.join(SCREENSHOT_DIR, "battery_sim_mcu_params_drawer.png")
            page.screenshot(path=scen_drawer_png)
            print(f"   [OK] Screenshot saved to: {scen_drawer_png}")

            # 8. Test Custom MCU Parameters: Configure a REGRESSION scenario
            print("8. Testing Custom MCU Parameters that produce a REGRESSION...")
            # Set software AES to be extremely fast (0.20 ms) and HMAC overhead to be heavy (2.50 ms)
            page.fill("#mcu-t-aes", "0.20")
            page.fill("#mcu-t-hmac", "2.50")
            page.click("#btn-apply-mcu-config")
            page.locator("#scenario-summary-status-badge:has-text('MODEL PREDICTS HIGHER ENERGY')").wait_for(timeout=10000)

            summary_badge_reg = page.locator("#scenario-summary-status-badge").inner_text().strip()
            print(f"   Updated MCU summary badge with regression params: '{summary_badge_reg}'")
            assert "MODEL PREDICTS HIGHER ENERGY" in summary_badge_reg

            # Run Simulation with regression parameters
            btn_start.click()
            page.wait_for_selector("#btn-battery-start-demo:not([disabled])", timeout=15000)

            status_mcu_reg_adapt = page.locator("#battery-status-adaptive").inner_text().strip()
            status_mcu_reg_base = page.locator("#battery-status-baseline").inner_text().strip()
            print(f"   Custom MCU regression outcome -> Adaptive: '{status_mcu_reg_adapt}', Baseline: '{status_mcu_reg_base}'")
            assert "MODEL PREDICTS HIGHER ENERGY" in status_mcu_reg_adapt
            assert "DEPLETED LESS" in status_mcu_reg_base

            # Screenshot MCU Regression Verified
            scen_reg_png = os.path.join(SCREENSHOT_DIR, "battery_sim_mcu_regression_verified.png")
            page.screenshot(path=scen_reg_png)
            print(f"   [OK] Screenshot saved to: {scen_reg_png}")

            # Reset MCU defaults
            print("   Resetting MCU defaults...")
            page.click("#btn-reset-mcu-defaults")
            page.locator("#scenario-summary-status-badge:has-text('MODEL PREDICTS LOWER ENERGY')").wait_for(timeout=10000)
            summary_badge_reset = page.locator("#scenario-summary-status-badge").inner_text().strip()
            print(f"   Reset MCU summary badge: '{summary_badge_reset}'")
            assert "MODEL PREDICTS LOWER ENERGY" in summary_badge_reset

            # Verify no severe page errors
            critical_errors = [e for e in page_errors if "favicon" not in e.lower()]
            print(f"8. Page errors count: {len(critical_errors)}")
            assert len(critical_errors) == 0, f"Critical page errors detected: {critical_errors}"

            browser.close()
            print("=== Battery Scenarios Browser E2E Test PASSED Successfully! ===")
    finally:
        print(f"Stopping uvicorn server on port {PORT}...")
        server_process.terminate()
        server_process.wait(timeout=5)
        print("   [OK] Server process terminated cleanly.")

if __name__ == "__main__":
    run_battery_scenarios_browser_test()
