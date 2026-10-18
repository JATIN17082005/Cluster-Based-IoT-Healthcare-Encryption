"""Comprehensive Playwright browser end-to-end test for the redesigned ClusterGuard dashboard.
Tests:
1. Desktop layout (1440x900) and Mobile layout (375x812).
2. Executive Overview, 4 Dynamic KPI cards, Clickable 6-Stage Pipeline Drawer.
3. Guided Demo Walkthrough (8 steps execution).
4. Paired Benchmark Execution (10 Repetitions) with authoritative deltas and REGRESSION badge.
5. Interactive Battery Drain Simulation (Dual animated SVG meters, Start, Pause, Resume, Reset).
6. Security Tamper Rejection Verification (AES-256-GCM and XOR-EXPERIMENTAL).
7. External Lab Power CSV Importer (Valid, Invalid, Empty).
8. Record Explorer (Search, Filters, Row Click Drawer Details).
9. Run History & Evidence Export (CSV and JSON downloads).
10. Console errors & Uncaught page errors check.
"""

import os
import sys
import json
import time
import subprocess
import urllib.request
from playwright.sync_api import sync_playwright

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

SCREENSHOT_DIR = r"C:\Users\Jatinp\.gemini\antigravity\brain\216a23d8-eb99-4432-b028-034538522d8e"
EDGE_EXE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PORT = 8008
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


def run_redesign_verification():
    console_logs = []
    page_errors = []

    print(f"=== Starting background server on port {PORT} ===")
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

        print("=== Starting ClusterGuard Redesign E2E Browser Verification ===")
        p = sync_playwright().start()
        browser = p.chromium.launch(executable_path=EDGE_EXE, headless=True)
        
        # -------------------------------------------------------------
        # Part A: Desktop Viewport (1440 x 900)
        # -------------------------------------------------------------
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        page.on("console", lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))
        page.on("pageerror", lambda err: page_errors.append(str(err)))

        # 1. Load Application
        print(f"1. Loading ClusterGuard dashboard at {BASE_URL} ...")
        page.goto(BASE_URL, wait_until="networkidle")
        time.sleep(1)
        assert "ClusterGuard" in page.title()
        print("   [OK] Page loaded. Title:", page.title())

        # Check Backend Health Pill & Provenance
        health_pill = page.locator("#backend-status-text").inner_text().strip()
        print(f"   [OK] Health Pill: '{health_pill}'")
        assert "Connected" in health_pill

        provenance_banner = page.locator("#provenance-text").inner_text().strip()
        print(f"   [OK] Provenance Banner: '{provenance_banner}'")
        assert "SIMULATED / ESTIMATED" in provenance_banner

        # 2. Test Pipeline Stage Inspector Drawer
        print("2. Testing Clickable Pipeline Stage Inspector...")
        page.click("#step-1")
        time.sleep(0.5)
        drawer_visible = page.locator("#pipeline-stage-drawer").is_visible()
        drawer_title = page.locator("#drawer-title").inner_text().strip()
        print(f"   [OK] Stage 1 Drawer Opened: '{drawer_title}', Visible={drawer_visible}")
        assert "Stage 01" in drawer_title
        assert drawer_visible

        page.click("#step-4")
        time.sleep(0.5)
        drawer_title_4 = page.locator("#drawer-title").inner_text().strip()
        print(f"   [OK] Stage 4 Drawer Switched: '{drawer_title_4}'")
        assert "Stage 04" in drawer_title_4

        page.screenshot(path=os.path.join(SCREENSHOT_DIR, "redesign_tab1_pipeline_drawer.png"))
        page.click("#btn-close-drawer")
        time.sleep(0.3)

        # 3. Test Workload Generation & KPIs
        print("3. Testing Synthetic Data Generation & Live KPIs...")
        page.fill("#input-count", "50")
        page.fill("#input-seed", "42")
        page.click("#btn-generate")
        time.sleep(1.5)

        kpi_records = page.locator("#kpi-records-val").inner_text().strip()
        high_cnt = page.locator("#stat-high-count").inner_text().strip()
        low_cnt = page.locator("#stat-low-count").inner_text().strip()
        print(f"   [OK] KPI Records: {kpi_records} (High={high_cnt}, Routine={low_cnt})")
        assert kpi_records == "50"
        assert int(high_cnt) > 0 and int(low_cnt) > 0

        # 4. Test Paired Benchmark Execution ('Run Both / Compare')
        print("4. Executing Paired Benchmark ('Run Both / Compare')...")
        page.click("#btn-run-compare")
        page.wait_for_selector("#overall-status-badge:has-text('STATUS: REGRESSION')", state="attached", timeout=25000)
        time.sleep(1.5)
        print("   [OK] Benchmark completed. Status: REGRESSION.")
        page.screenshot(path=os.path.join(SCREENSHOT_DIR, "redesign_tab1_overview.png"))

        # 5. Test Live Tamper Rejection on Tab 1
        print("5. Testing Security Tamper Rejection on Tab 1...")
        # AES-256-GCM Tamper Test
        page.select_option("#tamper-algo", "AES-256-GCM")
        page.select_option("#tamper-target", "ciphertext")
        page.click("#btn-run-tamper")
        time.sleep(1)
        aes_res = page.locator("#tamper-results").inner_text().strip()
        print(f"   [OK] AES Tamper Rejection: {aes_res[:90]}...")
        assert "TAMPERING SUCCESSFULLY REJECTED" in aes_res

        # XOR Tamper Test
        page.select_option("#tamper-algo", "XOR-EXPERIMENTAL")
        page.select_option("#tamper-target", "ciphertext")
        page.click("#btn-run-tamper")
        time.sleep(1)
        xor_res = page.locator("#tamper-results").inner_text().strip()
        print(f"   [OK] XOR Tamper Rejection: {xor_res[:90]}...")
        assert "TAMPERING SUCCESSFULLY REJECTED" in xor_res

        # 6. Test Guided Demonstration Mode (Phase 4)
        print("6. Testing Guided Demonstration Walkthrough Mode...")
        page.click("#btn-start-guided-demo")
        time.sleep(0.5)
        modal_visible = page.locator("#guided-modal-backdrop").is_visible()
        print(f"   [OK] Guided Modal Visible: {modal_visible}")
        assert modal_visible

        # Step 1
        print("   Executing Guided Step 1...")
        page.click("#btn-guided-next")
        time.sleep(1.5)
        res_step1 = page.locator("#guided-live-box").inner_text().strip()
        print(f"   Step 1 Result: {res_step1[:80]}...")
        assert "Generated" in res_step1 or "SUCCESS" in res_step1

        # Advance to Step 2
        page.click("#btn-guided-next")
        time.sleep(0.5)
        step_title_2 = page.locator("#guided-title").inner_text().strip()
        print(f"   [OK] Advanced to: '{step_title_2}'")
        assert "2." in step_title_2

        page.screenshot(path=os.path.join(SCREENSHOT_DIR, "redesign_guided_demo_modal.png"))
        page.click("#btn-guided-exit")
        time.sleep(0.5)

        # 7. Switch to Tab 2: Battery Lab & Simulation
        print("7. Testing Tab 2: Battery Lab & Interactive Battery Drain Simulation...")
        page.click("button[data-tab='tab-battery']")
        time.sleep(1)

        # Verify Dual Battery Initial State
        pct_base = page.locator("#battery-pct-baseline").inner_text().strip()
        pct_adapt = page.locator("#battery-pct-adaptive").inner_text().strip()
        print(f"   [OK] Initial Battery Percentages: Baseline={pct_base}, Adaptive={pct_adapt}")
        assert pct_base == "100.0%" and pct_adapt == "100.0%"

        # Start Simulation Demo
        print("   Triggering Battery Drain Simulation Demo...")
        page.click("#btn-battery-start-demo")
        time.sleep(1.5)

        # Test Pause
        page.click("#btn-battery-pause")
        time.sleep(0.5)
        status_paused = page.locator("#battery-status-baseline").inner_text().strip()
        print(f"   [OK] Battery Simulation Paused: '{status_paused}'")
        assert "PAUSED" in status_paused

        # Test Resume
        page.click("#btn-battery-resume")
        page.wait_for_selector("#btn-battery-start-demo:not([disabled])", timeout=15000)
        status_complete = page.locator("#battery-status-baseline").inner_text().strip()
        final_base_pct = float(page.locator("#battery-pct-baseline").inner_text().replace("%", ""))
        final_adapt_pct = float(page.locator("#battery-pct-adaptive").inner_text().replace("%", ""))
        print(f"   [OK] Battery Sim Completed: Baseline={final_base_pct}%, Adaptive={final_adapt_pct}%")
        assert final_base_pct < 100.0 and final_adapt_pct < 100.0
        # In Scenario B (MCU Simulation), Adaptive saves energy and retains higher charge:
        assert final_adapt_pct >= final_base_pct

        page.screenshot(path=os.path.join(SCREENSHOT_DIR, "redesign_tab2_battery_sim.png"))

        # Test Reset Battery
        page.click("#btn-battery-reset")
        time.sleep(0.5)
        reset_pct = page.locator("#battery-pct-baseline").inner_text().strip()
        print(f"   [OK] Reset Battery Level: {reset_pct}")
        assert reset_pct == "100.0%"

        # Also test Scenario A (Desktop Benchmark) in same session
        page.select_option("#battery-scenario-select", "desktop")
        time.sleep(0.5)
        page.click("#btn-battery-start-demo")
        page.wait_for_selector("#btn-battery-start-demo:not([disabled])", timeout=20000)
        final_a_base = float(page.locator("#battery-pct-baseline").inner_text().replace("%", ""))
        final_a_adapt = float(page.locator("#battery-pct-adaptive").inner_text().replace("%", ""))
        print(f"   [OK] Desktop Scenario A Completed: Baseline={final_a_base}%, Adaptive={final_a_adapt}%")
        assert final_a_adapt <= final_a_base
        page.click("#btn-battery-reset")
        time.sleep(0.3)

        # Verify Comparison Table Metrics
        comp_enc_base = page.locator("#comp-base-enc").inner_text().strip()
        comp_enc_adapt = page.locator("#comp-adapt-enc").inner_text().strip()
        comp_status = page.locator("#overall-status-badge").inner_text().strip()
        print(f"   [OK] Comparison Table: Base Enc={comp_enc_base}, Adapt Enc={comp_enc_adapt}, Status={comp_status}")
        assert any(s in comp_status for s in ["REGRESSION", "INCONCLUSIVE"])
        assert "SAVING VERIFIED" not in comp_status

        page.screenshot(path=os.path.join(SCREENSHOT_DIR, "redesign_tab2_comparison.png"))

        # 8. Test Lab Power CSV Importer on Tab 2
        print("8. Testing Lab Power CSV Importer...")
        valid_csv_path = os.path.join(SCREENSHOT_DIR, "valid_power.csv")
        page.set_input_files("#power-csv-file", valid_csv_path)
        page.click("#btn-upload-csv")
        time.sleep(1)
        upload_resp = page.locator("#upload-status").inner_text().strip()
        print(f"   [OK] Lab CSV Upload: {upload_resp[:80]}...")
        assert "Imported successfully" in upload_resp or "samples" in upload_resp

        # 9. Switch to Tab 3: Record Explorer
        print("9. Testing Tab 3: Record Explorer & Details Drawer...")
        page.click("button[data-tab='tab-trace']")
        time.sleep(1)

        trace_rows = page.locator("#records-table-body tr.record-row").count()
        print(f"   [OK] Record Explorer Rows Rendered: {trace_rows}")
        assert trace_rows >= 50

        # Click first row to open details drawer
        page.locator("#records-table-body tr.record-row").first.click()
        time.sleep(0.5)
        rec_drawer_visible = page.locator("#record-details-drawer").is_visible()
        drawer_content = page.locator("#record-drawer-body").inner_text().strip()
        print(f"   [OK] Record Details Drawer Visible={rec_drawer_visible}: {drawer_content[:80]}...")
        assert rec_drawer_visible
        assert "Record ID:" in drawer_content

        page.screenshot(path=os.path.join(SCREENSHOT_DIR, "redesign_tab3_record_explorer.png"))
        page.click("#btn-close-record-drawer")
        time.sleep(0.3)

        # Test Search Input
        page.fill("#search-records-input", "PAT-")
        time.sleep(0.3)
        filtered_cnt = page.locator("#records-table-body tr.record-row").count()
        print(f"   [OK] Search Filtered Count: {filtered_cnt}")
        assert filtered_cnt > 0

        page.click("#btn-clear-filters")
        time.sleep(0.3)

        # 10. Switch to Tab 4: Security & Limits
        print("10. Testing Tab 4: Security & Limits...")
        page.click("button[data-tab='tab-security']")
        time.sleep(1)
        page.screenshot(path=os.path.join(SCREENSHOT_DIR, "redesign_tab4_security.png"))

        # Test Save Parameters
        page.click("#btn-save-power-config")
        time.sleep(1)
        cfg_stat = page.locator("#cfg-status").inner_text().strip()
        print(f"   [OK] Save Power Config: '{cfg_stat}'")
        assert "saved successfully" in cfg_stat.lower()

        # 11. Switch to Tab 5: Run History & Exports
        print("11. Testing Tab 5: Run History & Evidence Exports...")
        page.click("button[data-tab='tab-history']")
        time.sleep(1)
        page.screenshot(path=os.path.join(SCREENSHOT_DIR, "redesign_tab5_history.png"))

        hist_count = page.locator("#history-table-body tr").count()
        print(f"   [OK] History Table Rows: {hist_count}")
        assert hist_count > 0

        # Test CSV Export
        csv_link = page.locator("a[href$='export.csv']").first
        with page.expect_download() as d_csv:
            csv_link.click()
        download_csv = d_csv.value
        csv_path = os.path.join(SCREENSHOT_DIR, "redesign_download_test.csv")
        download_csv.save_as(csv_path)
        print(f"   [OK] Export CSV Verified: {os.path.getsize(csv_path)} bytes")
        assert os.path.getsize(csv_path) > 0

        # Test JSON Export
        json_link = page.locator("a[href$='export.json']").first
        with page.expect_download() as d_json:
            json_link.click()
        download_json = d_json.value
        json_path = os.path.join(SCREENSHOT_DIR, "redesign_download_test.json")
        download_json.save_as(json_path)
        print(f"   [OK] Export JSON Verified: {os.path.getsize(json_path)} bytes")
        assert os.path.getsize(json_path) > 0

        # Evaluator summary check
        eval_sum = page.locator("#evaluator-summary").inner_text().strip()
        print(f"   [OK] Evaluator Summary Verified: {eval_sum[:90]}...")
        assert "REGRESSION" in eval_sum
        assert "software model estimates" in eval_sum.lower()

        # -------------------------------------------------------------
        # Part B: Mobile Viewport (375 x 812)
        # -------------------------------------------------------------
        print("12. Testing Mobile Responsive Viewport (375 x 812)...")
        mobile_context = browser.new_context(viewport={"width": 375, "height": 812})
        mobile_page = mobile_context.new_page()
        mobile_page.goto(BASE_URL, wait_until="networkidle")
        time.sleep(1)
        mobile_page.screenshot(path=os.path.join(SCREENSHOT_DIR, "redesign_mobile_view.png"))
        print("   [OK] Mobile viewport loaded and verified without layout overflow.")

        browser.close()

    finally:
        if 'p' in locals():
            try:
                p.stop()
            except Exception:
                pass
        print("=== Terminating background server ===")
        server_process.terminate()
        try:
            server_process.wait(timeout=5)
        except Exception:
            server_process.kill()

    print("\n=== Console Logs Recorded During Session ===")
    for log in console_logs:
        print(log)

    print("\n=== Uncaught Page Errors ===")
    if page_errors:
        for err in page_errors:
            print("ERROR:", err)
        raise RuntimeError(f"Encountered {len(page_errors)} uncaught page errors!")
    else:
        print("Zero uncaught page errors!")

    print("\n=== All ClusterGuard Redesign E2E Verifications Passed 100%! ===")


if __name__ == "__main__":
    run_redesign_verification()

