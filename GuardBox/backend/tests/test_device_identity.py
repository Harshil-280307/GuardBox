"""
Comprehensive Test Suite for Phase 5.9:
Multi-Shop Device Identity, Shop Binding, Veronic Protected Administration & Isolation.
Uses Python's built-in unittest framework with FastAPI TestClient.
"""

import os
import json
import time
import unittest
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.device_identity import device_identity_manager, DATA_DIR, IDENTITY_FILE

client = TestClient(app)


class TestDeviceIdentityAndVeronicProtection(unittest.TestCase):

    def test_01_device_identity_persistence(self):
        """Verify Device ID is preserved across multiple loads and is stable."""
        ident1 = device_identity_manager.load_identity()
        self.assertIsNotNone(ident1["device_id"])
        self.assertTrue(len(ident1["device_id"]) > 0)
        self.assertTrue(ident1["is_locked"])

        # Re-fetch from memory/disk
        ident2 = device_identity_manager.get_identity()
        self.assertEqual(ident2["device_id"], ident1["device_id"])
        self.assertEqual(ident2["shop_id"], ident1["shop_id"])

    def test_02_public_device_info_endpoint(self):
        """Verify GET /api/device/info returns locked, read-only identity metadata."""
        res = client.get("/api/device/info")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("device_id", data)
        self.assertIn("shop_id", data)
        self.assertIn("shop_name", data)
        self.assertTrue(data["is_locked"])
        self.assertEqual(data["registration_status"], "REGISTERED")
        self.assertEqual(data["connection_status"], "ONLINE")

    def test_03_veronic_admin_auth_failures(self):
        """Verify invalid credentials return 401 Unauthorized."""
        res = client.post("/api/admin/veronic-auth", json={
            "username": "wrong_user",
            "password": "wrong_password"
        })
        self.assertEqual(res.status_code, 401)
        self.assertIn("Invalid", res.json()["detail"])

    def test_04_veronic_admin_auth_success(self):
        """Verify correct Veronic credentials return valid session token."""
        admin_user = getattr(settings, "VERONIC_ADMIN_USER", "veronic_admin")
        admin_pass = getattr(settings, "VERONIC_ADMIN_SECRET", "VeronicSecureAdmin2026!")

        res = client.post("/api/admin/veronic-auth", json={
            "username": admin_user,
            "password": admin_pass
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["success"])
        self.assertIn("token", data)
        self.assertTrue(data["token"].startswith("VTK-"))
        self.assertEqual(data["expires_in"], 300)

    def test_05_unauthorized_device_identity_update_rejected(self):
        """Verify modifying device identity without Veronic authentication returns 403 Forbidden."""
        res = client.post("/api/device/identity", json={
            "device_id": "TRI-HACKED-ID",
            "shop_id": "SHOP-HACKED"
        })
        self.assertEqual(res.status_code, 403)
        self.assertIn("Veronic administrator authentication required", res.json()["detail"])

    def test_06_authorized_device_identity_update_flow(self):
        """Verify full Veronic authentication -> Edit Mode -> Update -> Auto Lock flow."""
        admin_user = getattr(settings, "VERONIC_ADMIN_USER", "veronic_admin")
        admin_pass = getattr(settings, "VERONIC_ADMIN_SECRET", "VeronicSecureAdmin2026!")

        # 1. Authenticate
        auth_res = client.post("/api/admin/veronic-auth", json={
            "username": admin_user,
            "password": admin_pass
        })
        self.assertEqual(auth_res.status_code, 200)
        token = auth_res.json()["token"]

        # 2. Update Identity with token
        target_shop_id = "SHOP-RK-001"
        target_shop_name = "Rajkot Jewellery Flagship"

        update_res = client.post(
            "/api/device/identity",
            headers={"X-Veronic-Token": token},
            json={
                "shop_id": target_shop_id,
                "shop_name": target_shop_name
            }
        )
        self.assertEqual(update_res.status_code, 200)
        updated = update_res.json()
        self.assertTrue(updated["success"])
        self.assertEqual(updated["identity"]["shop_id"], target_shop_id)
        self.assertEqual(updated["identity"]["shop_name"], target_shop_name)
        self.assertTrue(updated["identity"]["is_locked"])

        # 3. Verify public endpoint reflects changes in locked state
        info_res = client.get("/api/device/info")
        self.assertEqual(info_res.status_code, 200)
        self.assertEqual(info_res.json()["shop_id"], target_shop_id)
        self.assertEqual(info_res.json()["shop_name"], target_shop_name)
        self.assertTrue(info_res.json()["is_locked"])

    def test_07_shop_transfer_endpoint(self):
        """Verify protected shop transfer operation."""
        admin_user = getattr(settings, "VERONIC_ADMIN_USER", "veronic_admin")
        admin_pass = getattr(settings, "VERONIC_ADMIN_SECRET", "VeronicSecureAdmin2026!")

        auth_res = client.post("/api/admin/veronic-auth", json={
            "username": admin_user,
            "password": admin_pass
        })
        token = auth_res.json()["token"]

        transfer_res = client.post(
            "/api/device/transfer-shop",
            headers={"X-Veronic-Token": token},
            json={
                "target_shop_id": "SHOP-AH-002",
                "target_shop_name": "Ahmedabad Diamonds Branch"
            }
        )
        self.assertEqual(transfer_res.status_code, 200)
        self.assertEqual(transfer_res.json()["identity"]["shop_id"], "SHOP-AH-002")

        # Restore to primary test shop
        client.post(
            "/api/device/transfer-shop",
            headers={"X-Veronic-Token": token},
            json={
                "target_shop_id": "SHOP-RK-001",
                "target_shop_name": "Rajkot Jewellery"
            }
        )

    def test_08_sanitized_pairing_info_endpoint(self):
        """Verify pairing info contains ONLY public identifiers and no secrets."""
        res = client.get("/api/device/pairing-info")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("device_id", data)
        self.assertIn("shop_id", data)
        self.assertIn("pairing_type", data)
        # Ensure NO secrets are present
        self.assertNotIn("secret", data)
        self.assertNotIn("api_key", data)
        self.assertNotIn("password", data)
        self.assertNotIn("private_key", data)


if __name__ == "__main__":
    unittest.main()
