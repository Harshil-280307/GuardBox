"""
Scratch script to run an end-to-end customer build test using the Builder Engine.
"""

import sys
import json
from pathlib import Path

# Add builder root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "builder"))

from app.schemas import CustomerBuildConfig
from app.build_engine import BuildEngine

def main():
    gs_path = PROJECT_ROOT / "android" / "app" / "google-services.json"
    gs_content = gs_path.read_text(encoding="utf-8") if gs_path.exists() else json.dumps({
        "project_info": {"project_id": "test-project"},
        "client": [{"client_info": {"mobilesdk_app_id": "1:123:android:abc"}}]
    })

    sa_content = json.dumps({
        "type": "service_account",
        "project_id": "trinetra-test-project",
        "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQC...\n-----END PRIVATE KEY-----\n",
        "client_email": "trinetra-test@trinetra-test-project.iam.gserviceaccount.com"
    })

    cfg = CustomerBuildConfig(
        shop_name="TRINETRA TEST SHOP",
        shop_id="SHOP-TEST-001",
        device_id="TRI-TEST1234",
        device_name="Test Security Hub",
        firebase_db_url="https://guardbox-jewelleryshop-default-rtdb.firebaseio.com",
        firebase_service_account_json=sa_content,
        google_services_json=gs_content,
        supabase_url="https://test.supabase.co",
        supabase_bucket="snapshots",
        supabase_secret_key="mock_test_supabase_secret_key_12345",
        veronic_admin_user="admin",
        veronic_admin_secret="mockadminpass123",
        build_windows=True,
        build_android=True
    )

    print("Executing customer build test...")
    engine = BuildEngine(cfg)
    res = engine.execute_build()

    print("\n=== BUILD RESULT ===")
    print(f"Success: {res.is_success}")
    print(f"Windows Status: {res.windows_status}")
    print(f"Android Status: {res.android_status}")
    print(f"Security Scan: {res.security_scan_status}")
    print(f"Installer Available: {res.installer_available}")
    print(f"Output Directory: {res.output_directory}")
    print(f"Artifacts ({len(res.artifacts)}):")
    for a in res.artifacts:
        print(f"  • {a}")
    
    print("\n=== BUILD LOGS ===")
    for l in res.logs:
        print(l)

    if res.errors:
        print(f"\nErrors: {res.errors}")

if __name__ == "__main__":
    main()
