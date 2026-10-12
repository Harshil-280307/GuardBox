"""
TRINETRA Phase 6.5 - Clean Installation and Launcher Verification Test
"""

import os
import sys
import json
import time
import shutil
import tempfile
import subprocess
import urllib.request
from pathlib import Path

def main():
    installer = Path(r"E:\GuardBox\TRINETRA-BUILDS\TRINETRA-TEST-SHOP\TRINETRA-TRINETRA-TEST-SHOP-Setup.exe")
    if not installer.exists():
        print(f"Error: Installer not found at {installer}", flush=True)
        sys.exit(1)

    temp_install_dir = Path(tempfile.gettempdir()) / "TRINETRA_CLEAN_INSTALL_TEST"
    if temp_install_dir.exists():
        shutil.rmtree(temp_install_dir, ignore_errors=True)

    print(f"1. Installing TRINETRA to clean test location: {temp_install_dir}", flush=True)
    cmd = [str(installer), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-", f"/DIR={temp_install_dir}"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    print(f"   Installer Exit Code: {proc.returncode}", flush=True)

    if proc.returncode != 0:
        print(f"   Installer Error Output: {proc.stderr}", flush=True)
        sys.exit(1)

    print("2. Verifying Installed Application Files:", flush=True)
    installed_files = [f.name for f in temp_install_dir.iterdir()]
    print(f"   Files found: {installed_files}", flush=True)
    
    assert "TRINETRA.exe" in installed_files, "TRINETRA.exe missing!"
    assert ".env" in installed_files, ".env missing!"
    assert "serviceAccountKey.json" in installed_files, "serviceAccountKey.json missing!"
    assert (temp_install_dir / "data" / "device_identity.json").exists(), "data/device_identity.json missing!"

    # Read customer identity
    identity_path = temp_install_dir / "data" / "device_identity.json"
    identity_data = json.loads(identity_path.read_text(encoding="utf-8"))
    print(f"   Customer Device ID: {identity_data.get('device_id')}", flush=True)
    print(f"   Customer Shop ID:   {identity_data.get('shop_id')}", flush=True)
    print(f"   Customer Shop Name: {identity_data.get('shop_name')}", flush=True)

    assert identity_data.get("device_id") == "TRI-TEST1234", "Device ID mismatch!"
    assert identity_data.get("shop_id") == "SHOP-TEST-001", "Shop ID mismatch!"

    print("\n3. Testing Backend Readiness / HTTP Serving from Installed Package:", flush=True)
    env = os.environ.copy()
    test_port = "8045"
    env["PORT"] = test_port

    # Launch installed TRINETRA.exe
    app_exe = temp_install_dir / "TRINETRA.exe"
    print(f"   Launching installed {app_exe} on port {test_port}...", flush=True)
    app_proc = subprocess.Popen([str(app_exe)], cwd=str(temp_install_dir), env=env)

    # Poll HTTP endpoint
    ready = False
    for attempt in range(30):
        time.sleep(0.5)
        try:
            url = f"http://127.0.0.1:{test_port}/"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                if resp.status == 200:
                    html_content = resp.read(500).decode("utf-8", errors="ignore")
                    print(f"   [SUCCESS] Backend & Frontend HTTP 200 OK received! (HTML snippet: {html_content[:60]}...)", flush=True)
                    ready = True
                    break
        except Exception:
            pass

    # Kill test process
    try:
        subprocess.run(["taskkill", "/PID", str(app_proc.pid), "/F", "/T"], capture_output=True)
    except Exception:
        app_proc.kill()

    assert ready, "Installed application did not respond with HTTP 200 on test port!"

    # Verify launcher log was created
    launcher_log = temp_install_dir / "data" / "logs" / "trinetra-launcher.log"
    if launcher_log.exists():
        print(f"\n4. Verifying Launcher Diagnostics Log ({launcher_log.name}):", flush=True)
        log_lines = launcher_log.read_text(encoding="utf-8", errors="ignore").strip().splitlines()
        for l in log_lines[-6:]:
            print(f"   {l}", flush=True)

    print("\n[ALL CLEAN INSTALLATION TESTS PASSED]", flush=True)

if __name__ == "__main__":
    main()
