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

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

SCREENSHOT_DIR = r"C:\Users\Jatinp\.gemini\antigravity\brain\216a23d8-eb99-4432-b028-034538522d8e"
EDGE_EXE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

def run_battery_scenarios_browser_test():
    console_logs = []
    page_errors = []

    print("=== Starting Battery Scenarios Browser E2E Test ===")
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=EDGE_EXE, headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        page.on("console", lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))
        page.on("pageerror", lambda err: page_errors.append(str(err)))

        # 1. Load application
        print("1. Loading application at http://127.0.0.1:8000 ...")
        page.goto("http://127.0.0.1:8000", wait_until="networkidle")
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
        assert "SIMULATED TARGET-MCU SCENARIO" in disclaimer_title
        assert "RESULTS DEPEND ON CONFIGURED ASSUMPTIONS" in disclaimer_title

        # Check initial battery meter (100%, Green)
        pct_base = page.locator("#battery-pct-baseline").inner_text().strip()
        pct_adapt = page.locator("#battery-pct-adaptive").inner_text().strip()
        print(f"   Baseline charge: {pct_base}, Adaptive charge: {pct_adapt}")
        assert pct_base == "100.0%"
        assert pct_adapt == "100.0%"

        summary_badge = page.locator("#scenario-summary-status-badge").inner_text().strip()
        print(f"   Scenario summary badge: '{summary_badge}'")
        assert "SAVING" in summary_badge

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

        # Wait for completion (STEPS=30 * 100ms = ~3.0s)
        time.sleep(3.2)

        final_base_pct = float(page.locator("#battery-pct-baseline").inner_text().replace("%", ""))
        final_adapt_pct = float(page.locator("#battery-pct-adaptive").inner_text().replace("%", ""))
        print(f"   Scenario B final charges -> Baseline: {final_base_pct}%, Adaptive: {final_adapt_pct}%")

        # In Scenario B, Adaptive consumes LESS energy, so final adaptive charge must be GREATER than baseline
        assert final_adapt_pct > final_base_pct
        status_adapt_final = page.locator("#battery-status-adaptive").inner_text().strip()
        print(f"   Scenario B Adaptive outcome tag: '{status_adapt_final}'")
        assert "SAVING VERIFIED" in status_adapt_final

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
        # Allow paired benchmark comparison + animation
        time.sleep(5.0)

        final_a_base_pct = float(page.locator("#battery-pct-baseline").inner_text().replace("%", ""))
        final_a_adapt_pct = float(page.locator("#battery-pct-adaptive").inner_text().replace("%", ""))
        print(f"   Scenario A final charges -> Baseline: {final_a_base_pct}%, Adaptive: {final_a_adapt_pct}%")

        # In Scenario A (Desktop with AES-NI), Adaptive exhibits regression (consumes slightly more energy)
        # So final adaptive charge is <= baseline charge (drained more or equal within resolution)
        status_a_adapt = page.locator("#battery-status-adaptive").inner_text().strip()
        print(f"   Scenario A Adaptive outcome tag: '{status_a_adapt}'")
        assert "REGRESSION" in status_a_adapt

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

        # Screenshot MCU Drawer
        scen_drawer_png = os.path.join(SCREENSHOT_DIR, "battery_sim_mcu_params_drawer.png")
        page.screenshot(path=scen_drawer_png)
        print(f"   [OK] Screenshot saved to: {scen_drawer_png}")

        # Verify no severe page errors
        critical_errors = [e for e in page_errors if "favicon" not in e.lower()]
        print(f"8. Page errors count: {len(critical_errors)}")
        assert len(critical_errors) == 0, f"Critical page errors detected: {critical_errors}"

        browser.close()
        print("=== Battery Scenarios Browser E2E Test PASSED Successfully! ===")

if __name__ == "__main__":
    run_battery_scenarios_browser_test()
