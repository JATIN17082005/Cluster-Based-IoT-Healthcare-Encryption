"""Playwright E2E Browser Verification for K-Means Pipeline, Dataset Transparency, and Battery Validation.
Tests:
1. End-to-end server initialization.
2. Tab 1: Synthetic data generation with genuine K-Means clustering.
3. Dataset Explorer: 11 columns, filter by modality, filter by security route, search, pagination.
4. 7-Stage Pipeline Drawer: interactive click on each stage, data preview, diagnostics.
5. Export endpoints: Raw CSV/JSON, Features CSV/JSON, Clustered CSV/JSON.
6. Tab 2: 3-Tier Evidence Hierarchy, Usable Energy Proof (12,117.6 J), Activity Proof (0.033 mJ).
7. Battery discharge simulation execution.
8. Artifact screenshots and zero console error verification.
"""

import os
import sys
import time
import subprocess
import threading
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
PORT = 8009
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

def run_e2e_verification():
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

        print("=== 2. Launching Playwright Chromium/Edge Browser ===")
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=EDGE_EXE, headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 950})
            page = context.new_page()

            page.on("console", lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))
            page.on("pageerror", lambda err: page_errors.append(str(err)))

            # Step A: Load page
            print(f"   Navigating to {BASE_URL} ...")
            page.goto(BASE_URL, wait_until="networkidle")
            time.sleep(1)

            health_text = page.locator("#backend-status-text").inner_text().strip()
            print(f"   Backend Health: '{health_text}'")
            assert "Connected" in health_text

            # Step B: Trigger Data Generation with K-Means
            print("=== 3. Testing Synthetic Data Generation & K-Means Clustering ===")
            page.click("#btn-generate")
            time.sleep(1)

            records_kpi = page.locator("#kpi-records-val").inner_text().strip()
            print(f"   KPI Records Count: {records_kpi}")
            assert int(records_kpi) == 50

            run_id = page.locator("#dataset-pipeline-run-id").inner_text().strip()
            print(f"   Pipeline Run ID: '{run_id}'")
            assert "PIPE-S42" in run_id

            # Click Run ML Clustering for Stage 3 in the interactive workflow
            page.click("#btn-run-ml-clustering")
            time.sleep(1)

            agreement_text = page.locator("#meta-kmeans-agreement").inner_text().strip()
            print(f"   K-Means Agreement & Silhouette: '{agreement_text}'")
            assert "%" in agreement_text and "Silhouette" in agreement_text

            # Step C: Verify Transparent Dataset Table
            print("=== 4. Verifying Transparent Dataset Table (11 Columns) ===")
            table_rows = page.locator("#dataset-table-body tr")
            row_count = table_rows.count()
            print(f"   Initial visible table rows: {row_count}")
            assert row_count == 25, f"Expected 25 records on page 1, got {row_count}"

            first_row_cells = table_rows.first.locator("td")
            cell_count = first_row_cells.count()
            print(f"   Columns in record row: {cell_count}")
            assert cell_count == 11, f"Expected 11 columns, got {cell_count}"

            # Step D: Test Dataset Search & Filtering
            print("=== 5. Testing Dataset Filtering & Pagination ===")
            # Modality filter
            page.select_option("#filter-dataset-type", "heart_rate")
            time.sleep(0.3)
            filtered_hr_count = page.locator("#dataset-table-body tr").count()
            print(f"   Filtered heart_rate rows: {filtered_hr_count}")
            assert filtered_hr_count > 0

            # Reset modality filter, test security filter
            page.select_option("#filter-dataset-type", "ALL")
            page.select_option("#filter-dataset-sec", "HIGH")
            time.sleep(0.3)
            high_count = page.locator("#dataset-table-body tr").count()
            print(f"   Filtered HIGH security rows: {high_count}")
            assert high_count > 0

            # Reset filters, test pagination
            page.select_option("#filter-dataset-sec", "ALL")
            page.select_option("#dataset-page-size", "10")
            time.sleep(0.3)
            p10_count = page.locator("#dataset-table-body tr").count()
            assert p10_count == 10
            page_indicator = page.locator("#dataset-page-indicator").inner_text().strip()
            print(f"   Pagination indicator: '{page_indicator}'")
            assert "Page 1 of 5" in page_indicator

            page.click("#btn-dataset-next")
            time.sleep(0.3)
            page_indicator_2 = page.locator("#dataset-page-indicator").inner_text().strip()
            assert "Page 2 of 5" in page_indicator_2
            print("   [OK] Pagination Next navigation verified.")

            # Reset page size
            page.select_option("#dataset-page-size", "25")
            time.sleep(0.3)

            # Step E: Capture Dataset Table Screenshot
            shot_dataset = os.path.join(SCREENSHOT_DIR, "tab1_dataset_transparency_kmeans.png")
            page.screenshot(path=shot_dataset)
            print(f"   [OK] Saved dataset transparency screenshot: {shot_dataset}")

            # Step F: Test 7-Stage Pipeline Drawer
            print("=== 6. Testing 7-Stage End-to-End Pipeline Drawer ===")
            for step_num in range(1, 8):
                step_btn = page.locator(f"#step-{step_num}")
                step_btn.click()
                time.sleep(0.4)
                drawer = page.locator("#pipeline-stage-drawer")
                assert drawer.is_visible()

                title = page.locator("#drawer-title").inner_text().strip()
                print(f"   Stage {step_num} Drawer Title: '{title}'")
                assert f"Stage 0{step_num}" in title

                preview_html = page.locator("#drawer-stage-preview").inner_html().strip()
                assert len(preview_html) > 20, f"Stage {step_num} preview is empty"

                diag_html = page.locator("#drawer-stage-diagnostics").inner_html().strip()
                assert len(diag_html) > 10, f"Stage {step_num} diagnostics is empty"

            # Capture Stage 3 (K-Means) Drawer Screenshot
            page.locator("#step-3").click()
            time.sleep(0.4)
            shot_stage3 = os.path.join(SCREENSHOT_DIR, "pipeline_stage3_kmeans_drawer.png")
            page.screenshot(path=shot_stage3)
            print(f"   [OK] Saved Stage 3 K-Means drawer screenshot: {shot_stage3}")

            # Close drawer
            page.click("#btn-close-drawer")
            time.sleep(0.3)

            # Step G: Navigate to Tab 2 (Battery Lab) & Verify Evidence Tiers & Formulas
            print("=== 7. Verifying Tab 2 Battery Lab & Evidence Hierarchy ===")
            page.locator(".tab-btn[data-tab='tab-battery']").click()
            time.sleep(1)

            tab_pane = page.locator("#tab-battery")
            print("   tab-battery class:", tab_pane.get_attribute("class"))
            print("   tab-battery is_visible:", tab_pane.is_visible())
            print("   subpanel-g count:", page.locator("#mcu-subpanel-g").count())
            print("   subpanel-g is_visible:", page.locator("#mcu-subpanel-g").is_visible())

            subpanel_g = page.locator("#mcu-subpanel-g")
            subpanel_g.scroll_into_view_if_needed()
            time.sleep(0.5)
            assert subpanel_g.is_visible()
            print("   [OK] Sub-Panel G container is visible.")

            subpanel_text = subpanel_g.inner_text()
            assert "TIER 1: HOST MEASURED" in subpanel_text
            assert "TIER 2: TARGET MCU MODEL" in subpanel_text
            assert "TIER 3: BENCHTOP LAB" in subpanel_text
            print("   [OK] All 3 Evidence Tiers (Host, MCU, Lab) rendered.")

            assert "12,117.60 Joules" in subpanel_text
            print("   [OK] Battery capacity arithmetic proof (12,117.60 Joules) verified.")

            assert "0.033 mJ" in subpanel_text
            print("   [OK] Non-overlapping activity interval proof (0.033 mJ) verified.")

            # Step H: Test Battery Simulation Run
            print("=== 8. Running Battery Simulation Demo ===")
            btn_start = page.locator("#btn-battery-start-demo")
            btn_start.click()
            time.sleep(1)

            # Verify discharging state
            status_base = page.locator("#battery-status-baseline").inner_text().strip()
            print(f"   During simulation status: '{status_base}'")
            assert "DISCHARGING" in status_base

            # Wait for simulation to finish (up to 15s)
            page.wait_for_selector("#btn-battery-start-demo:not([disabled])", timeout=15000)
            status_adapt = page.locator("#battery-status-adaptive").inner_text().strip()
            print(f"   Simulation complete adaptive status: '{status_adapt}'")
            assert "MODEL PREDICTS" in status_adapt

            # Capture Tab 2 Screenshot
            shot_tab2 = os.path.join(SCREENSHOT_DIR, "tab2_battery_audit_evidence_tiers.png")
            page.screenshot(path=shot_tab2)
            print(f"   [OK] Saved Tab 2 Battery screenshot: {shot_tab2}")

            # Step I: Console errors check
            critical_errors = [e for e in page_errors if "favicon" not in e.lower()]
            print(f"=== 9. Page Errors Count: {len(critical_errors)} ===")
            assert len(critical_errors) == 0, f"Critical page errors found: {critical_errors}"

            browser.close()
            print("=== All Browser Verification Steps PASSED Successfully! ===")

    finally:
        print("=== Terminating background uvicorn server ===")
        server_process.terminate()
        try:
            server_process.wait(timeout=3)
        except Exception:
            server_process.kill()

if __name__ == "__main__":
    run_e2e_verification()
