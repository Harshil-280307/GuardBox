"""
TRINETRA Builder - Validation & Security Test Suite
"""

import unittest
import json
import zipfile
import tempfile
from pathlib import Path

import sys
BUILDER_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BUILDER_DIR))

from app.schemas import CustomerBuildConfig
from app.validator import validate_customer_config, sanitize_folder_name
from app.build_engine import BuildEngine


class TestBuilderValidation(unittest.TestCase):
    def setUp(self):
        self.valid_sa = json.dumps({
            "type": "service_account",
            "project_id": "test-project-123",
            "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQC...\n-----END PRIVATE KEY-----\n",
            "client_email": "firebase-adminsdk@test-project-123.iam.gserviceaccount.com"
        })
        self.valid_gs = json.dumps({
            "project_info": {"project_number": "123456", "project_id": "test-project-123"},
            "client": [{"client_info": {"mobilesdk_app_id": "1:123:android:abc"}}]
        })

    def test_valid_customer_config(self):
        cfg = CustomerBuildConfig(
            shop_name="Rajkot Jewellery",
            shop_id="SHOP-RK-001",
            device_id="TRI-7F29A8C4",
            device_name="Main Security Device",
            firebase_db_url="https://test-project-rtdb.firebaseio.com",
            firebase_service_account_json=self.valid_sa,
            google_services_json=self.valid_gs,
            supabase_url="https://xyz.supabase.co",
            supabase_bucket="snapshots",
            supabase_secret_key="service_role_secret_key_12345",
            veronic_admin_user="admin",
            veronic_admin_secret="supersecret123",
            build_windows=True,
            build_android=True
        )
        res = validate_customer_config(cfg)
        self.assertTrue(res.is_valid)
        self.assertEqual(len(res.errors), 0)
        self.assertEqual(res.sanitized_summary["shop_id"], "SHOP-RK-001")
        # Ensure secrets are NOT in sanitized summary
        self.assertNotIn("service_role_secret_key_12345", str(res.sanitized_summary))
        self.assertNotIn("supersecret123", str(res.sanitized_summary))

    def test_path_traversal_rejection(self):
        cfg = CustomerBuildConfig(
            shop_name="Bad Shop",
            shop_id="../SHOP-HACK",
            device_id="TRI-001/../../etc",
            device_name="Hacked Device",
            firebase_db_url="https://test.firebaseio.com",
            firebase_service_account_json=self.valid_sa,
            google_services_json=self.valid_gs,
            supabase_url="https://xyz.supabase.co",
            supabase_bucket="snapshots",
            supabase_secret_key="secret12345",
            veronic_admin_user="admin",
            veronic_admin_secret="secret12345"
        )
        res = validate_customer_config(cfg)
        self.assertFalse(res.is_valid)
        self.assertTrue(any("dangerous" in err or "alphanumeric" in err for err in res.errors))

    def test_invalid_firebase_url(self):
        cfg = CustomerBuildConfig(
            shop_name="Test Shop",
            shop_id="SHOP-001",
            device_id="TRI-001",
            device_name="Test Device",
            firebase_db_url="ftp://invalid-url.com",
            firebase_service_account_json=self.valid_sa,
            google_services_json=self.valid_gs,
            supabase_url="https://xyz.supabase.co",
            supabase_secret_key="secret12345",
            veronic_admin_secret="secret12345"
        )
        res = validate_customer_config(cfg)
        self.assertFalse(res.is_valid)
        self.assertTrue(any("Firebase Database URL is invalid" in err for err in res.errors))

    def test_malformed_json_rejection(self):
        cfg = CustomerBuildConfig(
            shop_name="Test Shop",
            shop_id="SHOP-001",
            device_id="TRI-001",
            device_name="Test Device",
            firebase_db_url="https://test.firebaseio.com",
            firebase_service_account_json="{bad-json",
            google_services_json=self.valid_gs,
            supabase_url="https://xyz.supabase.co",
            supabase_secret_key="secret12345",
            veronic_admin_secret="secret12345"
        )
        res = validate_customer_config(cfg)
        self.assertFalse(res.is_valid)
        self.assertTrue(any("not valid JSON" in err for err in res.errors))

    def test_empty_or_initial_payload_validation(self):
        # Reproduces the initial blank Builder form submission
        cfg = CustomerBuildConfig(
            shop_name="",
            shop_id="",
            device_id="",
            device_name="",
            firebase_db_url="",
            firebase_service_account_json=None,
            google_services_json=None,
            supabase_url="",
            supabase_bucket="snapshots",
            supabase_secret_key=None,
            veronic_admin_user="admin",
            veronic_admin_secret=None,
            build_windows=True,
            build_android=True
        )
        res = validate_customer_config(cfg)
        self.assertFalse(res.is_valid)
        self.assertIsInstance(res.errors, list)
        self.assertGreater(len(res.errors), 0)
        # Ensure errors can be iterated over (no undefined .forEach)
        for err in res.errors:
            self.assertIsInstance(err, str)
            self.assertGreater(len(err), 0)

    def test_sanitize_folder_name(self):
        self.assertEqual(sanitize_folder_name("Rajkot Jewellery & Co."), "Rajkot-Jewellery-Co")
        self.assertEqual(sanitize_folder_name("Shop / 123 *? test"), "Shop-123-test")
        self.assertEqual(sanitize_folder_name("---A---B---"), "A-B")


class TestBuilderSecurityScan(unittest.TestCase):
    def test_security_scan_detects_secret_leak(self):
        cfg = CustomerBuildConfig(
            shop_name="Security Test Shop",
            shop_id="SHOP-SEC-001",
            device_id="TRI-SEC01",
            device_name="Security Test Device",
            firebase_db_url="https://test.firebaseio.com",
            supabase_url="https://xyz.supabase.co",
            supabase_secret_key="MY_SUPER_SECRET_SUPABASE_KEY",
            veronic_admin_secret="MY_SUPER_ADMIN_PASSWORD"
        )
        engine = BuildEngine(cfg)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_apk = Path(tmpdir) / "test-leaked.apk"
            with zipfile.ZipFile(tmp_apk, "w") as zf:
                # Intentionally insert secret string in mock APK asset
                zf.writestr("assets/config.json", '{"secret": "MY_SUPER_SECRET_SUPABASE_KEY"}')

            passed, msg = engine._perform_android_security_scan(tmp_apk)
            self.assertFalse(passed)
            self.assertIn("Supabase Secret Key", msg)

    def test_security_scan_passes_on_clean_apk(self):
        cfg = CustomerBuildConfig(
            shop_name="Security Test Shop",
            shop_id="SHOP-SEC-001",
            device_id="TRI-SEC01",
            device_name="Security Test Device",
            firebase_db_url="https://test.firebaseio.com",
            supabase_url="https://xyz.supabase.co",
            supabase_secret_key="MY_SUPER_SECRET_SUPABASE_KEY",
            veronic_admin_secret="MY_SUPER_ADMIN_PASSWORD"
        )
        engine = BuildEngine(cfg)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_apk = Path(tmpdir) / "test-clean.apk"
            with zipfile.ZipFile(tmp_apk, "w") as zf:
                zf.writestr("AndroidManifest.xml", "<manifest></manifest>")
                zf.writestr("classes.dex", "Clean binary data without any server secrets")

            passed, msg = engine._perform_android_security_scan(tmp_apk)
            self.assertTrue(passed)


if __name__ == "__main__":
    unittest.main()
