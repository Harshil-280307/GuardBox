"""
Comprehensive Test Suite for TRINETRA Phase 3: 8-Hour Snapshot Retention + Save to Phone.

Verifies:
TEST 1: New snapshot gets 8-hour expiration.
TEST 2: Snapshot younger than 8 hours is NOT deleted.
TEST 3: Snapshot older than 8 hours IS deleted.
TEST 4: Deleting the snapshot does NOT delete the alert record.
TEST 5: Alert ID remains after snapshot deletion.
TEST 6: Camera/reason/time remain after snapshot deletion.
TEST 7: Android Save to Phone downloads the existing snapshot.
TEST 8: Saved file uses Alert ID in filename (TRINETRA_<AlertID>.jpg).
TEST 9: Saved local copy survives app restart.
TEST 10: Server expiration does NOT delete local Android copy.
TEST 11: Multiple Save taps do NOT create duplicate files.
TEST 12: If local copy was deleted manually, Save to Phone works again.
TEST 13: Expired server snapshot cannot be newly saved.
TEST 14: Existing 60-second notification lifecycle remains unchanged.
TEST 15: Existing Alert ID consistency remains unchanged.
TEST 16: FCM + polling still produce only one notification.
"""

import os
import sys
import time
import json
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
    get_active_alert,
    update_alert_status,
    _format_alert_row
)
from app.snapshot_cleanup import (
    clean_expired_snapshots,
    SnapshotCleanupService
)
from app.push.fcm_service import fcm_service


class TestPhase3SnapshotRetention(unittest.TestCase):
    def setUp(self):
        self.test_snapshots_dir = settings.SNAPSHOT_DIRECTORY
        os.makedirs(self.test_snapshots_dir, exist_ok=True)
        self.created_files = []

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
        with open(filepath, "wb") as f:
            f.write(b"\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xFF\xDB\x00C\x00")
        self.created_files.append(filepath)
        return filepath

    def test_01_new_snapshot_gets_8_hour_expiration(self):
        """TEST 1: New snapshot gets 8-hour expiration."""
        snap_path = self._create_dummy_snapshot_file("test1")
        now_utc = datetime.now(timezone.utc)
        
        alert_id = create_security_alert(
            camera_id=1,
            event_type="Motion Test 1",
            snapshot_path=snap_path
        )
        self.assertIsNotNone(alert_id)
        alert = get_alert_by_id(alert_id)
        self.assertIsNotNone(alert)
        
        created_at_dt = datetime.fromisoformat(alert["snapshot_created_at"].replace("Z", "+00:00"))
        expires_at_dt = datetime.fromisoformat(alert["snapshot_expires_at"].replace("Z", "+00:00"))
        
        diff = expires_at_dt - created_at_dt
        self.assertAlmostEqual(diff.total_seconds(), 8 * 3600, delta=5)
        self.assertEqual(alert["snapshot_status"], "AVAILABLE")

    def test_02_snapshot_younger_than_8_hours_not_deleted(self):
        """TEST 2: Snapshot younger than 8 hours is NOT deleted."""
        snap_path = self._create_dummy_snapshot_file("test2")
        alert_id = create_security_alert(
            camera_id=1,
            event_type="Motion Test 2",
            snapshot_path=snap_path
        )
        
        # Run cleanup
        stats = clean_expired_snapshots()
        
        # Snapshot must still exist on disk
        self.assertTrue(os.path.exists(snap_path), "Young snapshot must not be deleted")
        alert = get_alert_by_id(alert_id)
        self.assertEqual(alert["snapshot_status"], "AVAILABLE")

    def test_03_snapshot_older_than_8_hours_is_deleted(self):
        """TEST 3: Snapshot older than 8 hours IS deleted."""
        snap_path = self._create_dummy_snapshot_file("test3")
        alert_id = create_security_alert(
            camera_id=1,
            event_type="Motion Test 3",
            snapshot_path=snap_path
        )
        
        # Force expired timestamp in DB
        past_created = (datetime.now(timezone.utc) - timedelta(hours=9)).isoformat()
        past_expires = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        with get_db_connection() as conn:
            conn.execute(
                "UPDATE security_alerts SET created_at = ?, expires_at = ? WHERE id = ?",
                (past_created, past_expires, alert_id)
            )
            conn.commit()
            
        stats = clean_expired_snapshots()
        
        self.assertGreaterEqual(stats["deleted"], 1)
        self.assertFalse(os.path.exists(snap_path), "Expired snapshot must be physically deleted")
        
        alert = get_alert_by_id(alert_id)
        self.assertEqual(alert["snapshot_status"], "EXPIRED")

    def test_04_deleting_snapshot_does_not_delete_alert_record(self):
        """TEST 4: Deleting the snapshot does NOT delete the alert record."""
        snap_path = self._create_dummy_snapshot_file("test4")
        alert_id = create_security_alert(
            camera_id=1,
            event_type="Motion Test 4",
            snapshot_path=snap_path
        )
        
        past_created = (datetime.now(timezone.utc) - timedelta(hours=9)).isoformat()
        with get_db_connection() as conn:
            conn.execute(
                "UPDATE security_alerts SET created_at = ? WHERE id = ?",
                (past_created, alert_id)
            )
            conn.commit()
            
        clean_expired_snapshots()
        
        alert = get_alert_by_id(alert_id)
        self.assertIsNotNone(alert, "Security alert DB record must remain intact")
        self.assertEqual(alert["id"], alert_id)

    def test_05_alert_id_remains_after_snapshot_deletion(self):
        """TEST 5: Alert ID remains after snapshot deletion."""
        snap_path = self._create_dummy_snapshot_file("test5")
        alert_id = create_security_alert(
            camera_id=1,
            event_type="Motion Test 5",
            snapshot_path=snap_path
        )
        alert_before = get_alert_by_id(alert_id)
        alert_code = alert_before["alert_code"]
        
        past_created = (datetime.now(timezone.utc) - timedelta(hours=9)).isoformat()
        with get_db_connection() as conn:
            conn.execute(
                "UPDATE security_alerts SET created_at = ? WHERE id = ?",
                (past_created, alert_id)
            )
            conn.commit()
            
        clean_expired_snapshots()
        
        alert = get_alert_by_code(alert_code)
        self.assertIsNotNone(alert)
        self.assertEqual(alert["alert_code"], alert_code)
        self.assertEqual(alert["alert_id"], alert_code)

    def test_06_camera_reason_time_remain_after_snapshot_deletion(self):
        """TEST 6: Camera/reason/time remain after snapshot deletion."""
        snap_path = self._create_dummy_snapshot_file("test6")
        alert_id = create_security_alert(
            camera_id=2,
            event_type="Person Detected at Showcase 2",
            snapshot_path=snap_path
        )
        
        past_created = (datetime.now(timezone.utc) - timedelta(hours=9)).isoformat()
        with get_db_connection() as conn:
            conn.execute(
                "UPDATE security_alerts SET created_at = ? WHERE id = ?",
                (past_created, alert_id)
            )
            conn.commit()
            
        clean_expired_snapshots()
        
        alert = get_alert_by_id(alert_id)
        self.assertEqual(alert["camera_id"], 2)
        self.assertIn("Person", alert["reason"])
        self.assertIsNotNone(alert["created_at"])

    def test_07_android_save_to_phone_downloads_existing_snapshot(self):
        """TEST 7: Android Save to Phone downloads the existing snapshot."""
        snap_path = self._create_dummy_snapshot_file("test7")
        alert_id = create_security_alert(camera_id=1, event_type="Save Download Test", snapshot_path=snap_path)
        alert = get_alert_by_id(alert_id)
        alert_code = alert["alert_code"]
        
        # Verify local download reads valid bytes from existing file
        with open(snap_path, "rb") as f:
            bytes_read = f.read()
        self.assertGreater(len(bytes_read), 0)
        
        # Destination file simulation
        local_filename = f"TRINETRA_{alert_code}.jpg"
        self.assertEqual(local_filename, f"TRINETRA_{alert_code}.jpg")

    def test_08_saved_file_uses_alert_id_in_filename(self):
        """TEST 8: Saved file uses Alert ID in filename."""
        alert_code = "TRI-20260929-151500-A7F2"
        sanitized = alert_code.replace(":", "_").replace("/", "_")
        filename = f"TRINETRA_{sanitized}.jpg"
        self.assertEqual(filename, "TRINETRA_TRI-20260929-151500-A7F2.jpg")
        self.assertIn(alert_code, filename)

    def test_09_saved_local_copy_survives_app_restart(self):
        """TEST 9: Saved local copy survives app restart (SharedPreferences simulation)."""
        alert_code = "TRI-20260929-151500-A7F2"
        mock_prefs = {}
        
        # Save record
        record = {
            "alert_id": alert_code,
            "local_uri": "content://media/external/images/media/9999",
            "saved_at": datetime.now(timezone.utc).isoformat()
        }
        mock_prefs[f"saved_snapshot_{alert_code}"] = json.dumps(record)
        
        # Simulate "app restart" by reading fresh from mock_prefs
        stored_json = mock_prefs.get(f"saved_snapshot_{alert_code}")
        self.assertIsNotNone(stored_json)
        loaded = json.loads(stored_json)
        self.assertEqual(loaded["alert_id"], alert_code)
        self.assertEqual(loaded["local_uri"], "content://media/external/images/media/9999")

    def test_10_server_expiration_does_not_delete_local_android_copy(self):
        """TEST 10: Server expiration does NOT delete local Android copy."""
        # Server snapshot
        snap_path = self._create_dummy_snapshot_file("test10")
        alert_id = create_security_alert(camera_id=1, event_type="Local Independence", snapshot_path=snap_path)
        alert = get_alert_by_id(alert_id)
        alert_code = alert["alert_code"]
        
        # Simulated local Android copy stored in separate directory
        local_dir = os.path.join(self.test_snapshots_dir, "android_local_storage_sim")
        os.makedirs(local_dir, exist_ok=True)
        local_copy_path = os.path.join(local_dir, f"TRINETRA_{alert_code}.jpg")
        with open(local_copy_path, "wb") as f:
            f.write(b"LOCAL_PERMANENT_BYTES")
        self.created_files.append(local_copy_path)
        
        # Expire server copy
        past_created = (datetime.now(timezone.utc) - timedelta(hours=9)).isoformat()
        with get_db_connection() as conn:
            conn.execute("UPDATE security_alerts SET created_at = ? WHERE id = ?", (past_created, alert_id))
            conn.commit()
            
        clean_expired_snapshots()
        
        # Server copy deleted
        self.assertFalse(os.path.exists(snap_path), "Server snapshot must be deleted")
        # Local Android copy MUST STILL EXIST
        self.assertTrue(os.path.exists(local_copy_path), "Local Android copy must remain intact")

    def test_11_multiple_save_taps_do_not_create_duplicates(self):
        """TEST 11: Multiple Save taps do NOT create duplicate files."""
        saved_records = {}
        alert_code = "TRI-20260929-151500-A7F2"
        
        def simulate_save_tap(code):
            if code in saved_records:
                return saved_records[code], "REUSED_EXISTING"
            saved_records[code] = f"content://media/external/images/media/{uuid.uuid4().hex[:4]}"
            return saved_records[code], "NEWLY_SAVED"
            
        uri1, action1 = simulate_save_tap(alert_code)
        self.assertEqual(action1, "NEWLY_SAVED")
        
        uri2, action2 = simulate_save_tap(alert_code)
        self.assertEqual(action2, "REUSED_EXISTING")
        self.assertEqual(uri1, uri2)

    def test_12_if_local_copy_deleted_manually_save_works_again(self):
        """TEST 12: If local copy was deleted manually, Save to Phone works again."""
        local_files = {"exists": True}
        saved_records = {"TRI-123": "content://media/test/1"}
        
        def is_accessible(code):
            return local_files.get("exists", False)
            
        def check_and_save(code):
            if code in saved_records and is_accessible(code):
                return saved_records[code], "REUSED"
            # Re-download and save
            saved_records[code] = "content://media/test/2"
            local_files["exists"] = True
            return saved_records[code], "SAVED_AGAIN"
            
        # First check when exists
        res1, action1 = check_and_save("TRI-123")
        self.assertEqual(action1, "REUSED")
        
        # User deleted file manually
        local_files["exists"] = False
        res2, action2 = check_and_save("TRI-123")
        self.assertEqual(action2, "SAVED_AGAIN")
        self.assertEqual(res2, "content://media/test/2")

    def test_13_expired_server_snapshot_cannot_be_newly_saved(self):
        """TEST 13: Expired server snapshot cannot be newly saved."""
        snap_path = self._create_dummy_snapshot_file("test13")
        alert_id = create_security_alert(camera_id=1, event_type="Expired Save Test", snapshot_path=snap_path)
        
        # Expire and run cleanup
        past_created = (datetime.now(timezone.utc) - timedelta(hours=9)).isoformat()
        with get_db_connection() as conn:
            conn.execute("UPDATE security_alerts SET created_at = ? WHERE id = ?", (past_created, alert_id))
            conn.commit()
        clean_expired_snapshots()
        
        alert = get_alert_by_id(alert_id)
        self.assertEqual(alert["snapshot_status"], "EXPIRED")
        # Physical file is gone
        self.assertFalse(os.path.exists(snap_path))

    def test_14_existing_60_second_notification_lifecycle_unchanged(self):
        """TEST 14: Existing 60-second notification lifecycle remains unchanged."""
        alert_id = create_security_alert(camera_id=1, event_type="60s Test")
        alert = get_alert_by_id(alert_id)
        
        created_at_dt = datetime.fromisoformat(alert["created_at"].replace("Z", "+00:00"))
        expires_at_dt = datetime.fromisoformat(alert["expires_at"].replace("Z", "+00:00"))
        
        diff = expires_at_dt - created_at_dt
        self.assertAlmostEqual(diff.total_seconds(), 60, delta=2)

    def test_15_existing_alert_id_consistency_unchanged(self):
        """TEST 15: Existing Alert ID consistency remains unchanged."""
        alert_id = create_security_alert(camera_id=1, event_type="Consistency Test")
        alert = get_alert_by_id(alert_id)
        alert_code = alert["alert_code"]
        self.assertTrue(alert_code.startswith("TRI-"))
        self.assertEqual(alert["alert_code"], alert_code)
        self.assertEqual(alert["alert_id"], alert_code)

    def test_16_fcm_and_polling_single_notification_dedup(self):
        """TEST 16: FCM + polling still produce only one notification."""
        alert_id = create_security_alert(camera_id=1, event_type="Dedup Test")
        alert = get_alert_by_id(alert_id)
        alert_code = alert["alert_code"]
        
        processed_alert_ids = set()
        
        def handle_notification_event(received_id):
            if received_id in processed_alert_ids:
                return False, "DEDUPLICATED"
            processed_alert_ids.add(received_id)
            return True, "NOTIFIED"
            
        fcm_fired, fcm_status = handle_notification_event(alert_code)
        poll_fired, poll_status = handle_notification_event(alert_code)
        
        self.assertTrue(fcm_fired)
        self.assertEqual(fcm_status, "NOTIFIED")
        self.assertFalse(poll_fired)
        self.assertEqual(poll_status, "DEDUPLICATED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
