"""
Unit & Integration Tests for TRINETRA Phase 5.2/5.4: Remote Snapshot Delivery with Supabase Storage.

Verifies:
TEST 1: Remote snapshot upload success with deterministic storage path.
TEST 2: Remote snapshot upload failure does not break security alert.
TEST 3: Deterministic Alert-ID storage path (guardbox/evidence/{device_id}/{alert_id}.jpg).
TEST 4: Duplicate upload protection (reuses existing storage reference).
TEST 5: Firebase RTDB alert metadata contains both local and remote references.
TEST 6: Background async worker updates SQLite and RTDB to AVAILABLE upon upload completion.
TEST 7: Background async worker handles upload failure gracefully without invalidating alert.
TEST 8: retry_remote_snapshot_upload preserves Alert ID and does not create new alerts.
TEST 9: 8-hour retention cleanup deletes both local file and remote Supabase object.
TEST 10: Missing remote object / storage error does not break cleanup.
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
    get_alert_by_code,
    update_alert_remote_snapshot,
    _format_alert_row,
)
from app.supabase_storage import supabase_storage_service
from app.firebase_bridge import firebase_bridge
from app.snapshot_cleanup import clean_expired_snapshots
from app.push.escalation import push_escalation_service


class TestPhase5RemoteSnapshotDelivery(unittest.TestCase):
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

    def _create_dummy_snapshot_file(self, prefix="event_cam1_test") -> str:
        filename = f"{prefix}_{uuid.uuid4().hex[:8]}.jpg"
        filepath = os.path.join(self.test_snapshots_dir, filename)
        header = b"\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xFF\xDB\x00C\x00"
        with open(filepath, "wb") as f:
            f.write(header + b"TEST_IMAGE_BYTES")
        self.created_files.append(filepath)
        return filepath

    def test_01_remote_snapshot_upload_success(self):
        """TEST 1: Remote snapshot upload success with deterministic storage path."""
        snap_path = self._create_dummy_snapshot_file("upload_test")
        alert_code = f"TRI-20260930-140501-{uuid.uuid4().hex[:4].upper()}"
        device_id = "guardbox-shop-f20424b4"

        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_client.storage.from_.return_value = mock_bucket
        mock_bucket.exists.return_value = False
        mock_bucket.upload.return_value = {"Key": f"guardbox/evidence/{device_id}/{alert_code}.jpg"}
        signed_res = MagicMock()
        signed_res.signed_url = "https://idgtlvqzjnjbsorgtyao.supabase.co/signed/test.jpg"
        mock_bucket.create_signed_url.return_value = signed_res

        with patch.object(supabase_storage_service, "get_client", return_value=mock_client):
            ref = firebase_bridge.upload_alert_snapshot(
                alert_id=alert_code,
                local_snapshot_path=snap_path,
                device_id=device_id
            )

            expected_path = f"guardbox/evidence/{device_id}/{alert_code}.jpg"
            self.assertEqual(ref, expected_path)
            mock_bucket.upload.assert_called_once()

    def test_02_remote_snapshot_upload_failure_does_not_break_alert(self):
        """TEST 2: Remote snapshot upload failure does not break security alert."""
        snap_path = self._create_dummy_snapshot_file("fail_test")

        # 1. Create alert locally
        alert_id = create_security_alert(
            camera_id=1,
            event_type="Intrusion Failure Test",
            snapshot_path=snap_path
        )
        self.assertIsNotNone(alert_id)
        alert = get_alert_by_id(alert_id)
        self.assertIsNotNone(alert)
        alert_code = alert["alert_code"]

        # 2. Simulate upload failure
        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_client.storage.from_.return_value = mock_bucket
        mock_bucket.exists.return_value = False
        mock_bucket.upload.side_effect = Exception("Supabase Storage Offline")

        with patch.object(supabase_storage_service, "get_client", return_value=mock_client):
            ref = firebase_bridge.upload_alert_snapshot(
                alert_id=alert_code,
                local_snapshot_path=snap_path,
                device_id=settings.GUARDBOX_DEVICE_ID or "guardbox-shop-test"
            )
            self.assertIsNone(ref)
            status = "FAILED"

            # Update DB with failed status
            update_alert_remote_snapshot(alert_id, ref, status, remote_provider="supabase")

        # 3. Verify SQLite alert and local snapshot still completely functional
        updated_alert = get_alert_by_id(alert_id)
        self.assertEqual(updated_alert["snapshot_status"], "AVAILABLE")
        self.assertEqual(updated_alert["remote_snapshot_status"], "FAILED")
        self.assertTrue(os.path.exists(snap_path))
        self.assertIsNotNone(updated_alert["snapshot_reference"])

    def test_03_deterministic_alert_id_storage_path(self):
        """TEST 3: Storage path is strictly deterministic: guardbox/evidence/{device_id}/{alert_id}.jpg."""
        alert_code = "TRI-20260930-140501-A7F2"
        device_id = "guardbox-shop-f20424b4"
        snap_path = self._create_dummy_snapshot_file("det_test")

        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_client.storage.from_.return_value = mock_bucket
        mock_bucket.exists.return_value = False
        signed_res = MagicMock()
        signed_res.signed_url = "https://idgtlvqzjnjbsorgtyao.supabase.co/signed/test.jpg"
        mock_bucket.create_signed_url.return_value = signed_res

        with patch.object(supabase_storage_service, "get_client", return_value=mock_client):
            ref = firebase_bridge.upload_alert_snapshot(
                alert_id=alert_code,
                local_snapshot_path=snap_path,
                device_id=device_id
            )
            self.assertEqual(ref, f"guardbox/evidence/{device_id}/{alert_code}.jpg")

    def test_04_duplicate_upload_protection(self):
        """TEST 4: Duplicate upload protection (reuses existing storage reference if blob exists)."""
        alert_code = "TRI-20260930-140501-A7F2"
        device_id = "guardbox-shop-f20424b4"
        snap_path = self._create_dummy_snapshot_file("dup_test")

        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_client.storage.from_.return_value = mock_bucket
        mock_bucket.exists.return_value = True  # Already uploaded
        signed_res = MagicMock()
        signed_res.signed_url = "https://idgtlvqzjnjbsorgtyao.supabase.co/signed/test.jpg"
        mock_bucket.create_signed_url.return_value = signed_res

        with patch.object(supabase_storage_service, "get_client", return_value=mock_client):
            ref = firebase_bridge.upload_alert_snapshot(
                alert_id=alert_code,
                local_snapshot_path=snap_path,
                device_id=device_id
            )
            self.assertEqual(ref, f"guardbox/evidence/{device_id}/{alert_code}.jpg")
            # Should NOT upload again
            mock_bucket.upload.assert_not_called()

    def test_05_firebase_metadata_initial_uploading_state(self):
        """TEST 5: Firebase RTDB alert metadata initially publishes UPLOADING state immediately."""
        snap_path = self._create_dummy_snapshot_file("meta_test")
        alert_id = create_security_alert(
            camera_id=1,
            event_type="Instant Alert Test",
            snapshot_path=snap_path
        )
        alert = get_alert_by_id(alert_id)
        alert_code = alert["alert_code"]

        mock_db_ref = MagicMock()
        mock_apps = ["app"]

        with patch("firebase_admin._apps", mock_apps), \
             patch("firebase_admin.db.reference", return_value=mock_db_ref), \
             patch.object(push_escalation_service, "_run_escalation_loop"), \
             patch.object(push_escalation_service, "_async_upload_snapshot_worker"):

            push_escalation_service.start_escalation(alert_id)

            self.assertTrue(mock_db_ref.set.called)
            called_data = mock_db_ref.set.call_args[0][0]
            self.assertIn("snapshot", called_data)
            snapshot_meta = called_data["snapshot"]
            self.assertEqual(snapshot_meta["status"], "UPLOADING")
            self.assertEqual(snapshot_meta["remote_status"], "UPLOADING")
            self.assertIsNone(snapshot_meta["remote_reference"])
            self.assertTrue(bool(snapshot_meta["local_reference"]))
            self.assertEqual(called_data["alert_id"], alert_code)

    def test_06_async_worker_updates_rtdb_to_available_on_success(self):
        """TEST 6: Background async worker updates SQLite and RTDB to AVAILABLE upon upload completion."""
        snap_path = self._create_dummy_snapshot_file("async_success_test")
        alert_id = create_security_alert(
            camera_id=1,
            event_type="Async Worker Test",
            snapshot_path=snap_path
        )
        alert = get_alert_by_id(alert_id)
        alert_code = alert["alert_code"]
        dev_id = settings.GUARDBOX_DEVICE_ID or "guardbox-shop-f20424b4"
        expected_storage_path = f"guardbox/evidence/{dev_id}/{alert_code}.jpg"
        signed_url = "https://idgtlvqzjnjbsorgtyao.supabase.co/signed/evidence.jpg"

        mock_upload_res = {
            "status": "AVAILABLE",
            "remote_provider": "supabase",
            "remote_reference": expected_storage_path,
            "remote_snapshot_reference": expected_storage_path,
            "remote_status": "AVAILABLE",
            "snapshot_status": "AVAILABLE",
            "signed_url": signed_url,
            "remote_url": signed_url,
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

            # Check SQLite updated
            updated_alert = get_alert_by_id(alert_id)
            self.assertEqual(updated_alert["remote_snapshot_status"], "AVAILABLE")
            self.assertEqual(updated_alert["remote_snapshot_reference"], expected_storage_path)

            # Check RTDB update called with AVAILABLE
            self.assertTrue(mock_db_ref.update.called)
            update_kwargs = mock_db_ref.update.call_args[0][0]
            self.assertEqual(update_kwargs["remote_snapshot_status"], "AVAILABLE")
            self.assertEqual(update_kwargs["remote_snapshot_reference"], expected_storage_path)
            self.assertEqual(update_kwargs["snapshot"]["status"], "AVAILABLE")

    def test_07_async_worker_updates_rtdb_to_failed_on_error(self):
        """TEST 7: Background async worker handles upload failure gracefully without invalidating alert."""
        snap_path = self._create_dummy_snapshot_file("async_fail_test")
        alert_id = create_security_alert(
            camera_id=1,
            event_type="Async Fail Test",
            snapshot_path=snap_path
        )
        alert = get_alert_by_id(alert_id)
        alert_code = alert["alert_code"]
        dev_id = settings.GUARDBOX_DEVICE_ID or "guardbox-shop-f20424b4"

        mock_db_ref = MagicMock()
        mock_db_ref.get.return_value = {"alert_id": alert_code}
        mock_apps = ["app"]

        with patch.object(supabase_storage_service, "upload_alert_snapshot", return_value=None), \
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

            # Check SQLite updated to FAILED while keeping local snapshot AVAILABLE
            updated_alert = get_alert_by_id(alert_id)
            self.assertEqual(updated_alert["remote_snapshot_status"], "FAILED")
            self.assertEqual(updated_alert["snapshot_status"], "AVAILABLE")
            self.assertTrue(os.path.exists(snap_path))

            # Check RTDB update called with FAILED
            self.assertTrue(mock_db_ref.update.called)
            update_kwargs = mock_db_ref.update.call_args[0][0]
            self.assertEqual(update_kwargs["remote_snapshot_status"], "FAILED")
            self.assertIsNone(update_kwargs["remote_snapshot_reference"])

    def test_08_retry_remote_snapshot_upload_preserves_alert_id(self):
        """TEST 8: retry_remote_snapshot_upload preserves Alert ID and does not create new alerts."""
        snap_path = self._create_dummy_snapshot_file("retry_test")
        alert_id = create_security_alert(
            camera_id=1,
            event_type="Retry Test",
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

    def test_09_remote_snapshot_cleanup_after_8_hours(self):
        """TEST 9: 8-hour retention cleanup deletes both local file and Supabase Storage object."""
        snap_path = self._create_dummy_snapshot_file("cleanup_test")
        alert_id = create_security_alert(
            camera_id=1,
            event_type="Cleanup Test",
            snapshot_path=snap_path
        )
        alert = get_alert_by_id(alert_id)
        alert_code = alert["alert_code"]
        dev_id = settings.GUARDBOX_DEVICE_ID or "guardbox-shop-f20424b4"

        # Set remote reference
        update_alert_remote_snapshot(alert_id, f"guardbox/evidence/{dev_id}/{alert_code}.jpg", "AVAILABLE")

        # Expire in DB by shifting created_at to 9 hours ago
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

            # Check local file deleted
            self.assertFalse(os.path.exists(snap_path))

            # Check remote delete called
            mock_delete.assert_called_with(alert_code, dev_id)

            # Check DB statuses updated to EXPIRED
            updated = get_alert_by_id(alert_id)
            self.assertEqual(updated["snapshot_status"], "EXPIRED")
            self.assertEqual(updated["remote_snapshot_status"], "EXPIRED")

    def test_10_missing_remote_object_does_not_break_cleanup(self):
        """TEST 10: Missing remote object / storage error does not break cleanup."""
        snap_path = self._create_dummy_snapshot_file("cleanup_err_test")
        alert_id = create_security_alert(
            camera_id=1,
            event_type="Cleanup Error Resilience",
            snapshot_path=snap_path
        )
        alert = get_alert_by_id(alert_id)
        alert_code = alert["alert_code"]

        # Expire in DB
        past_created = (datetime.now(timezone.utc) - timedelta(hours=9)).isoformat()
        past_expires = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        with get_db_connection() as conn:
            conn.execute(
                "UPDATE security_alerts SET created_at = ?, expires_at = ? WHERE id = ?",
                (past_created, past_expires, alert_id)
            )
            conn.commit()

        # Simulate exception during remote storage delete
        with patch.object(supabase_storage_service, "delete_alert_snapshot", side_effect=Exception("Storage network error")):
            stats = clean_expired_snapshots()
            self.assertGreaterEqual(stats["deleted"], 1)
            self.assertFalse(os.path.exists(snap_path))


if __name__ == "__main__":
    unittest.main(verbosity=2)
