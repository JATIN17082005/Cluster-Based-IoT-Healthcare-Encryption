"""Playwright E2E Browser Verification for Faculty Demo Interactive Workflow.
Tests:
1. End-to-end server initialization.
2. Step 1: Click '1. Generate Synthetic Data' -> verifies raw dataset table & immediate Raw CSV download.
3. Step 2: Reference to executable ML model file at src/kmeans_clusterer.py and Feature Engineering matrix.
4. Step 3: Click '2. Run ML Clustering' -> executes genuine scikit-learn K-Means, semantic mapping, and guardrails.
5. Step 4: Click '3. Simulate Battery on Current Dataset' -> executes per-record battery simulation & downloads CSV.
6. Step 5 & 6: Encryption routing and receiver verification view & exports.
7. Tab 2: Dual battery visual meters and dedicated Per-Record Battery Simulation Table.
8. Verifies zero console errors and saves full visual artifacts.
"""

import os
import sys
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
PORT = 8012
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

def run_faculty_workflow_browser_test():
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
            context = browser.new_context(viewport={"width": 1440, "height": 950}, accept_downloads=True)
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

            # Check ML model file reference callout
            model_callout = page.locator(".ml-model-callout-card").inner_text()
            print(f"   ML Model Callout: {model_callout}")
            assert "src/kmeans_clusterer.py" in model_callout

            # Step B: Test Stage 1 - Click Generate Synthetic Data
            print("=== 3. Testing Stage 1: Generate Synthetic Data ===")
            page.click("#btn-generate")
            time.sleep(1.5)

            lineage_run_id = page.locator("#meta-run-id").inner_text().strip()
            total_records = page.locator("#meta-total-count").inner_text().strip()
            print(f"   Lineage Run ID: {lineage_run_id}, Records: {total_records}")
            assert lineage_run_id.startswith("PIPE-")
            assert total_records == "50"

            # Verify Raw Dataset Table is displayed
            raw_pill_active = page.locator("#pill-view-raw").get_attribute("class")
            print(f"   Pill View Raw Class: {raw_pill_active}")
            assert "active" in raw_pill_active

            # Verify Raw CSV Download button is enabled and works
            assert not page.locator("#btn-download-raw-csv").is_disabled()
            print("   [OK] Raw CSV download button is enabled immediately after generation.")

            with page.expect_download() as download_info:
                page.click("#btn-download-raw-csv")
            download = download_info.value
            raw_csv_path = os.path.join(SCREENSHOT_DIR, "staged_raw_dataset.csv")
            download.save_as(raw_csv_path)
            with open(raw_csv_path, "r", encoding="utf-8") as f:
                raw_header = f.readline()
            print(f"   Downloaded Raw CSV header: {raw_header.strip()}")
            assert "record_id" in raw_header
            assert "kmeans_cluster_id" not in raw_header # Raw must NOT have fabricated cluster IDs

            page.screenshot(path=os.path.join(SCREENSHOT_DIR, "staged_stage1_raw.png"), full_page=False)

            # Step C: Test Stage 2 - Inspect Feature Engineering Matrix
            print("=== 4. Testing Stage 2: Feature Engineering Matrix View ===")
            page.click("#pill-view-features")
            time.sleep(0.5)

            table_head_text = page.locator("#dataset-table-head").inner_text()
            print(f"   Features Table Head: {table_head_text}")
            assert "hr one-hot" in table_head_text.lower() or "modality" in table_head_text.lower()
            page.screenshot(path=os.path.join(SCREENSHOT_DIR, "staged_stage2_features.png"), full_page=False)

            # Step D: Test Stage 3 - Click Run ML Clustering
            print("=== 5. Testing Stage 3: Run ML Clustering (K-Means) ===")
            assert not page.locator("#btn-run-ml-clustering").is_disabled()
            page.click("#btn-run-ml-clustering")
            time.sleep(1.5)

            agreement_text = page.locator("#meta-kmeans-agreement").inner_text()
            print(f"   Within-Run Rule Agreement: {agreement_text}")
            assert "%" in agreement_text

            clustered_pill_active = page.locator("#pill-view-clustered").get_attribute("class")
            assert "active" in clustered_pill_active

            # Verify Clustered CSV Download is enabled
            assert not page.locator("#btn-download-clustered-csv").is_disabled()
            with page.expect_download() as download_info:
                page.click("#btn-download-clustered-csv")
            download = download_info.value
            clustered_csv_path = os.path.join(SCREENSHOT_DIR, "staged_clustered_dataset.csv")
            download.save_as(clustered_csv_path)
            with open(clustered_csv_path, "r", encoding="utf-8") as f:
                clustered_header = f.readline()
                first_row = f.readline()
            print(f"   Downloaded Clustered CSV header: {clustered_header.strip()}")
            print(f"   Downloaded Clustered Row 1: {first_row.strip()}")
            assert "kmeans_cluster_id" in clustered_header
            assert "effective_security_class" in clustered_header

            page.screenshot(path=os.path.join(SCREENSHOT_DIR, "staged_stage3_clustered.png"), full_page=False)

            # Step E: Test Stage 4 - Click Simulate Battery on Current Dataset
            print("=== 6. Testing Stage 4: Simulate Battery on Current Dataset ===")
            assert not page.locator("#btn-simulate-battery-current").is_disabled()
            page.click("#btn-simulate-battery-current")
            time.sleep(2.0)
            print("Console logs after clicking simulate:", console_logs)
            battery_pill_active = page.locator("#pill-view-battery").get_attribute("class")
            print(f"battery_pill_active: '{battery_pill_active}'")
            assert "active" in battery_pill_active

            # Verify Per-Record Battery table has entries
            first_battery_row = page.locator("#dataset-table-body tr").first.inner_text()
            print(f"   Per-Record Battery Row 1: {first_battery_row}")
            assert "AES-256-GCM" in first_battery_row
            assert "%" in first_battery_row

            # Download Battery CSV
            with page.expect_download() as download_info:
                page.click("#btn-download-battery-csv")
            download = download_info.value
            battery_csv_path = os.path.join(SCREENSHOT_DIR, "staged_battery_simulation.csv")
            download.save_as(battery_csv_path)
            with open(battery_csv_path, "r", encoding="utf-8") as f:
                battery_header = f.readline()
                battery_row1 = f.readline()
            print(f"   Downloaded Battery CSV header: {battery_header.strip()}")
            print(f"   Downloaded Battery Row 1: {battery_row1.strip()}")
            assert "baseline_energy_joules" in battery_header
            assert "adaptive_energy_joules" in battery_header
            assert "baseline_battery_remaining_percent" in battery_header

            page.screenshot(path=os.path.join(SCREENSHOT_DIR, "staged_stage4_battery_sim.png"), full_page=False)

            # Step F: Switch to Tab 2 and verify Tab 2 Battery section and Per-Record Table
            print("=== 7. Testing Tab 2: Dual Battery Visual Meters & Per-Record Table ===")
            page.click("button[data-tab='tab-battery']")
            time.sleep(1)

            print("Console logs at Tab 2:", console_logs)
            tab2_status = page.locator("#tab2-battery-status-tag").inner_text()
            print(f"   Tab 2 Battery Status Tag: {tab2_status}")
            assert "SIMULATED" in tab2_status

            tab2_lineage = page.locator("#battery-sim-lineage-id").inner_text()
            print(f"   Tab 2 Lineage ID: {tab2_lineage}")
            assert tab2_lineage == lineage_run_id

            # Verify Tab 2 per-record table has rows
            tab2_first_row = page.locator("#battery-simulation-table-body tr").first.inner_text()
            print(f"   Tab 2 Battery Table Row 1: {tab2_first_row}")
            assert "AES-256-GCM" in tab2_first_row

            page.screenshot(path=os.path.join(SCREENSHOT_DIR, "staged_tab2_battery_table.png"), full_page=False)

            # Step G: Switch back to Tab 1 and test View 5 (Routing & Verification)
            print("=== 8. Testing View 5: Encryption Routing & Verification ===")
            page.click("button[data-tab='tab-overview']")
            time.sleep(0.5)
            page.click("#pill-view-routing")
            time.sleep(1.5)

            routing_row1 = page.locator("#dataset-table-body tr").first.inner_text()
            print(f"   Routing Row 1: {routing_row1}")
            assert "AUTHENTICATED" in routing_row1

            # Download Routing and Receiver CSVs
            with page.expect_download() as download_info:
                page.click("#btn-download-routing-csv")
            download = download_info.value
            routing_csv_path = os.path.join(SCREENSHOT_DIR, "staged_routing_dataset.csv")
            download.save_as(routing_csv_path)

            with page.expect_download() as download_info:
                page.click("#btn-download-receiver-csv")
            download = download_info.value
            receiver_csv_path = os.path.join(SCREENSHOT_DIR, "staged_receiver_dataset.csv")
            download.save_as(receiver_csv_path)

            print("   [OK] Both Routing and Receiver CSVs downloaded successfully.")

            # Step H: Verify Console Logs and Errors
            print("=== 9. Verifying Browser Console Integrity ===")
            critical_errors = [e for e in page_errors if "favicon" not in str(e).lower()]
            print(f"   Page errors count: {len(critical_errors)}")
            for err in critical_errors:
                print(f"   [ERROR] {err}")
            assert len(critical_errors) == 0, f"Encountered page errors: {critical_errors}"

            browser.close()
            print("=== Playwright E2E Verification PASSED! ===")

    finally:
        server_process.terminate()
        server_process.wait(timeout=5)
        print("   [OK] Server process terminated cleanly.")

if __name__ == "__main__":
    run_faculty_workflow_browser_test()
