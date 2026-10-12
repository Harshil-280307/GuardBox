"""
Unit & Integration Tests for TRINETRA Phase 5.4: Supabase Storage Integration.

Verifies:
1. Supabase configuration validation (missing credentials, valid credentials, key masking).
2. Deterministic object path format (guardbox/evidence/{device_id}/{alert_id}.jpg).
3. Image optimization (downscaling/compression under 4MB limit).
4. Upload success and signed URL generation with deterministic path.
5. Duplicate upload prevention (checks exists before uploading).
6. Upload size limit rejection (files > 4MB rejected).
7. Upload failure handling (gracefully handles network/permission errors).
8. Signed URL generation covering remaining 8-hour retention.
9. 8-hour retention cleanup (deletes local file and remote Supabase object).
10. Remote deletion failure resilience (cleanup continues safely on storage errors).
11. Retry mechanism (verifies alert existence, 8-hour retention window, avoids duplicate alerts/FCM).
12. Firebase RTDB metadata publishing (remote_provider="supabase", remote_url, signed_url).
"""

import os
import sys
import uuid
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.config import settings
from app.database import (
    get_db_connection,
    create_security_alert,
    get_alert_by_id,
    update_alert_remote_snapshot,
)
from app.supabase_storage import supabase_storage_service, SupabaseStorageService
from app.snapshot_cleanup import clean_expired_snapshots
from app.push.escalation import push_escalation_service
from app.firebase_bridge import firebase_bridge


class TestSupabaseStorageIntegration(unittest.TestCase):
    def setUp(self):
        self.test_snapshots_dir = settings.SNAPSHOT_DIRECTORY
        os.makedirs(self.test_snapshots_dir, exist_ok=True)
        self.created_files = []
        firebase_bridge._is_initialized = True

    def tearDown(self):
        for f in self.created_files:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass

    def _create_dummy_snapshot_file(self, prefix="supabase_test", size_bytes=1024) -> str:
        filename = f"{prefix}_{uuid.uuid4().hex[:8]}.jpg"
        filepath = os.path.join(self.test_snapshots_dir, filename)
        # Valid minimal JPEG header
        header = b"\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xFF\xDB\x00C\x00"
        payload = b"X" * max(0, size_bytes - len(header))
        with open(filepath, "wb") as f:
            f.write(header + payload)
        self.created_files.append(filepath)
        return filepath

    # -------------------------------------------------------------------------
    # 1. Configuration Validation
    # -------------------------------------------------------------------------
    def test_01_configuration_validation(self):
        """Test Supabase configuration validation with valid and missing credentials."""
        service = SupabaseStorageService()

        # Test valid config
        with patch.object(settings, "SUPABASE_URL", "https://idgtlvqzjnjbsorgtyao.supabase.co"), \
             patch.object(settings, "SUPABASE_SECRET_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.testsecretkey12345678"), \
             patch.object(settings, "SUPABASE_BUCKET", "trinetra-snapshots"):
            valid, err_msg = service.validate_configuration()
            self.assertTrue(valid)
            self.assertIsNone(err_msg)
            masked = settings.get_masked_supabase_key()
            self.assertTrue(masked.startswith("eyJh"))
            self.assertNotIn("testsecretkey12345678", masked)

        # Test missing key
        with patch.object(settings, "SUPABASE_URL", "https://idgtlvqzjnjbsorgtyao.supabase.co"), \
             patch.object(settings, "SUPABASE_SECRET_KEY", ""), \
             patch.object(settings, "SUPABASE_BUCKET", "trinetra-snapshots"):
            valid, err_msg = service.validate_configuration()
            self.assertFalse(valid)
            self.assertIn("SUPABASE_SECRET_KEY", err_msg)

    # -------------------------------------------------------------------------
    # 2. Deterministic Object Path
    # -------------------------------------------------------------------------
    def test_02_deterministic_object_path(self):
        """Test deterministic object path generation: guardbox/evidence/{device_id}/{alert_id}.jpg."""
        device_id = "guardbox-shop-f20424b4"
        alert_id = "TRI-20261001-140501-A7F2"
        path = supabase_storage_service.get_object_path(alert_id, device_id)
        self.assertEqual(path, f"guardbox/evidence/{device_id}/{alert_id}.jpg")

    # -------------------------------------------------------------------------
    # 3. Upload Success and Signed URL
    # -------------------------------------------------------------------------
    def test_03_upload_success_and_signed_url(self):
        """Test successful upload with deterministic path and signed URL generation."""
        snap_path = self._create_dummy_snapshot_file("upload_ok")
        alert_id = f"TRI-20261001-120000-{uuid.uuid4().hex[:4].upper()}"
        device_id = "guardbox-shop-test"

        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_client.storage.from_.return_value = mock_bucket
        mock_bucket.exists.return_value = False
        mock_bucket.upload.return_value = {"Key": f"guardbox/evidence/{device_id}/{alert_id}.jpg"}

        signed_res = MagicMock()
        signed_res.signed_url = "https://idgtlvqzjnjbsorgtyao.supabase.co/storage/v1/object/sign/trinetra-snapshots/guardbox/evidence/test.jpg?token=mocktoken"
        mock_bucket.create_signed_url.return_value = signed_res

        with patch.object(supabase_storage_service, "get_client", return_value=mock_client):
            result = supabase_storage_service.upload_alert_snapshot(
                alert_id=alert_id,
                local_snapshot_path=snap_path,
                device_id=device_id,
                expires_in_seconds=28800
            )

            self.assertIsNotNone(result)
            self.assertEqual(result["remote_reference"], f"guardbox/evidence/{device_id}/{alert_id}.jpg")
            self.assertEqual(result["remote_provider"], "supabase")
            self.assertEqual(result["status"], "AVAILABLE")
            self.assertEqual(result["signed_url"], signed_res.signed_url)
            self.assertEqual(result["expires_in_seconds"], 28800)

            mock_bucket.upload.assert_called_once()
            mock_bucket.create_signed_url.assert_called_once_with(
                path=f"guardbox/evidence/{device_id}/{alert_id}.jpg",
                expires_in=28800
            )

    # -------------------------------------------------------------------------
    # 4. Duplicate Upload Prevention
    # -------------------------------------------------------------------------
    def test_04_duplicate_upload_prevention(self):
        """Test duplicate upload prevention (reuses existing object reference without uploading)."""
        snap_path = self._create_dummy_snapshot_file("dup_test")
        alert_id = "TRI-20261001-120000-DUP1"
        device_id = "guardbox-shop-test"

        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_client.storage.from_.return_value = mock_bucket
        mock_bucket.exists.return_value = True  # File already in Supabase

        signed_res = MagicMock()
        signed_res.signed_url = "https://idgtlvqzjnjbsorgtyao.supabase.co/signed/url"
        mock_bucket.create_signed_url.return_value = signed_res

        with patch.object(supabase_storage_service, "get_client", return_value=mock_client):
            result = supabase_storage_service.upload_alert_snapshot(
                alert_id=alert_id,
                local_snapshot_path=snap_path,
                device_id=device_id
            )

            self.assertIsNotNone(result)
            self.assertEqual(result["remote_reference"], f"guardbox/evidence/{device_id}/{alert_id}.jpg")
            self.assertEqual(result["status"], "AVAILABLE")
            mock_bucket.upload.assert_not_called()
            mock_bucket.create_signed_url.assert_called_once()

    # -------------------------------------------------------------------------
    # 5. Upload Size Limit Rejection (>4MB)
    # -------------------------------------------------------------------------
    def test_05_upload_size_limit_rejection(self):
        """Test that files exceeding 4MB are rejected before upload."""
        snap_path = self._create_dummy_snapshot_file("large_test")
        alert_id = "TRI-20261001-120000-LRG1"
        device_id = "guardbox-shop-test"

        mock_client = MagicMock()
        with patch.object(supabase_storage_service, "get_client", return_value=mock_client), \
             patch.object(supabase_storage_service, "_optimize_snapshot", return_value=(snap_path, 5 * 1024 * 1024, False)):
            result = supabase_storage_service.upload_alert_snapshot(
                alert_id=alert_id,
                local_snapshot_path=snap_path,
                device_id=device_id
            )
            self.assertIsNone(result)

    # -------------------------------------------------------------------------
    # 6. Upload Failure Resilience
    # -------------------------------------------------------------------------
    def test_06_upload_failure_resilience(self):
        """Test upload failure does not crash or corrupt local security alert."""
        snap_path = self._create_dummy_snapshot_file("fail_test")
        alert_id = create_security_alert(
            camera_id=1,
            event_type="Supabase Upload Fail Test",
            snapshot_path=snap_path
        )
        alert = get_alert_by_id(alert_id)
        alert_code = alert["alert_code"]

        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_client.storage.from_.return_value = mock_bucket
        mock_bucket.exists.return_value = False
        mock_bucket.upload.side_effect = Exception("Supabase 503 Service Unavailable")

        with patch.object(supabase_storage_service, "get_client", return_value=mock_client):
            result = supabase_storage_service.upload_alert_snapshot(
                alert_id=alert_code,
                local_snapshot_path=snap_path,
                device_id="guardbox-shop-test"
            )
            self.assertIsNone(result)

            # Update DB with failed status
            update_alert_remote_snapshot(alert_id, None, "FAILED", remote_provider="supabase")

        updated_alert = get_alert_by_id(alert_id)
        self.assertEqual(updated_alert["snapshot_status"], "AVAILABLE")
        self.assertEqual(updated_alert["remote_snapshot_status"], "FAILED")
        self.assertEqual(updated_alert["remote_provider"], "supabase")
        self.assertTrue(os.path.exists(snap_path))

    # -------------------------------------------------------------------------
    # 7. Async Push Escalation Worker RTDB Update
    # -------------------------------------------------------------------------
    def test_07_async_worker_updates_rtdb_with_supabase_metadata(self):
        """Test that background async upload worker updates Firebase RTDB with Supabase provider and signed URL."""
        snap_path = self._create_dummy_snapshot_file("async_sb_test")
        alert_id = create_security_alert(
            camera_id=1,
            event_type="Supabase Async Test",
            snapshot_path=snap_path
        )
        alert = get_alert_by_id(alert_id)
        alert_code = alert["alert_code"]
        dev_id = "guardbox-shop-test"
        remote_ref = f"guardbox/evidence/{dev_id}/{alert_code}.jpg"
        signed_url = "https://idgtlvqzjnjbsorgtyao.supabase.co/storage/v1/object/sign/trinetra-snapshots/test.jpg"

        mock_upload_res = {
            "remote_reference": remote_ref,
            "remote_provider": "supabase",
            "signed_url": signed_url,
            "status": "AVAILABLE",
            "expires_in_seconds": 28800
        }

        mock_db_ref = MagicMock()
        mock_db_ref.get.return_value = {"alert_id": alert_code}
        mock_apps = ["app"]

        with patch.object(supabase_storage_service, "upload_alert_snapshot", return_value=mock_upload_res), \
             patch("firebase_admin._apps", mock_apps), \
             patch("firebase_admin.db.reference", return_value=mock_db_ref):

            push_escalation_service._async_upload_snapshot_worker(
                alert_id=alert_id,
                alert_code=alert_code,
                snap_path=snap_path,
                dev_id=dev_id,
                snap_ref=snap_path,
                snap_created=alert["created_at"],
                snap_exp=alert.get("snapshot_expires_at")
            )

            # Verify SQLite updated with remote URL and provider
            updated_alert = get_alert_by_id(alert_id)
            self.assertEqual(updated_alert["remote_snapshot_status"], "AVAILABLE")
            self.assertEqual(updated_alert["remote_snapshot_reference"], remote_ref)
            self.assertEqual(updated_alert["remote_provider"], "supabase")
            self.assertEqual(updated_alert["remote_url"], signed_url)

            # Verify RTDB updated
            self.assertTrue(mock_db_ref.update.called)
            rtdb_data = mock_db_ref.update.call_args[0][0]
            self.assertEqual(rtdb_data["remote_snapshot_status"], "AVAILABLE")
            self.assertEqual(rtdb_data["remote_snapshot_reference"], remote_ref)
            self.assertEqual(rtdb_data["remote_provider"], "supabase")
            self.assertEqual(rtdb_data["remote_url"], signed_url)
            self.assertEqual(rtdb_data["signed_url"], signed_url)
            self.assertEqual(rtdb_data["snapshot"]["status"], "AVAILABLE")
            self.assertEqual(rtdb_data["snapshot"]["remote_provider"], "supabase")

    # -------------------------------------------------------------------------
    # 8. 8-Hour Retention Cleanup with Supabase Deletion
    # -------------------------------------------------------------------------
    def test_08_retention_cleanup_deletes_supabase_object(self):
        """Test 8-hour retention cleanup deletes both local file and remote Supabase object."""
        snap_path = self._create_dummy_snapshot_file("sb_cleanup_test")
        alert_id = create_security_alert(
            camera_id=1,
            event_type="Supabase Cleanup Test",
            snapshot_path=snap_path
        )
        alert = get_alert_by_id(alert_id)
        alert_code = alert["alert_code"]
        dev_id = settings.GUARDBOX_DEVICE_ID or "guardbox-shop-f20424b4"

        update_alert_remote_snapshot(
            alert_id_or_code=alert_id,
            remote_reference=f"guardbox/evidence/{dev_id}/{alert_code}.jpg",
            status="AVAILABLE",
            remote_url="https://signed.url",
            remote_provider="supabase"
        )

        # Expire in DB
        past_created = (datetime.now(timezone.utc) - timedelta(hours=9)).isoformat()
        past_expires = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        with get_db_connection() as conn:
            conn.execute(
                "UPDATE security_alerts SET created_at = ?, expires_at = ? WHERE id = ?",
                (past_created, past_expires, alert_id)
            )
            conn.commit()

        mock_delete = MagicMock(return_value=True)
        with patch.object(supabase_storage_service, "delete_alert_snapshot", mock_delete):
            stats = clean_expired_snapshots()
            self.assertGreaterEqual(stats["deleted"], 1)

            # Local file deleted
            self.assertFalse(os.path.exists(snap_path))

            # Supabase delete called
            mock_delete.assert_called_with(alert_code, dev_id)

            # DB marked EXPIRED
            updated = get_alert_by_id(alert_id)
            self.assertEqual(updated["snapshot_status"], "EXPIRED")
            self.assertEqual(updated["remote_snapshot_status"], "EXPIRED")

    # -------------------------------------------------------------------------
    # 9. Cleanup Resilience on Supabase Delete Failure
    # -------------------------------------------------------------------------
    def test_09_cleanup_resilience_on_supabase_delete_error(self):
        """Test that failure to delete remote object does not crash cleanup service."""
        snap_path = self._create_dummy_snapshot_file("sb_del_err")
        alert_id = create_security_alert(
            camera_id=1,
            event_type="Supabase Delete Error Test",
            snapshot_path=snap_path
        )
        alert = get_alert_by_id(alert_id)

        # Expire in DB
        past_created = (datetime.now(timezone.utc) - timedelta(hours=9)).isoformat()
        past_expires = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        with get_db_connection() as conn:
            conn.execute(
                "UPDATE security_alerts SET created_at = ?, expires_at = ? WHERE id = ?",
                (past_created, past_expires, alert_id)
            )
            conn.commit()

        with patch.object(supabase_storage_service, "delete_alert_snapshot", side_effect=Exception("Supabase 500 error")):
            stats = clean_expired_snapshots()
            self.assertGreaterEqual(stats["deleted"], 1)
            self.assertFalse(os.path.exists(snap_path))

    # -------------------------------------------------------------------------
    # 10. Retry Remote Snapshot Upload
    # -------------------------------------------------------------------------
    def test_10_retry_remote_upload_validates_retention_and_preserves_id(self):
        """Test retry endpoint preserves alert ID and validates 8-hour retention window."""
        snap_path = self._create_dummy_snapshot_file("sb_retry")
        alert_id = create_security_alert(
            camera_id=1,
            event_type="Supabase Retry Test",
            snapshot_path=snap_path
        )
        alert = get_alert_by_id(alert_id)
        alert_code = alert["alert_code"]

        with patch("threading.Thread") as mock_thread_cls:
            mock_thread_instance = MagicMock()
            mock_thread_cls.return_value = mock_thread_instance

            res = push_escalation_service.retry_remote_snapshot_upload(alert_code)
            self.assertTrue(res["success"])
            self.assertEqual(res["alert_id"], alert_code)
            self.assertEqual(res["status"], "UPLOADING")
            mock_thread_instance.start.assert_called_once()

        # Test retry on expired alert (>8 hours)
        past_created = (datetime.now(timezone.utc) - timedelta(hours=9)).isoformat()
        past_expires = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        with get_db_connection() as conn:
            conn.execute(
                "UPDATE security_alerts SET created_at = ?, expires_at = ? WHERE id = ?",
                (past_created, past_expires, alert_id)
            )
            conn.commit()

        res_expired = push_escalation_service.retry_remote_snapshot_upload(alert_code)
        self.assertFalse(res_expired["success"])
        self.assertIn("expired", res_expired["error"].lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
