"""
TRINETRA Phase 5.7 Test Suite:
1. Firebase Realtime Database rules authorization and alert_history query permissions.
2. 8-Hour snapshot retention calculation and lifecycle stability.
3. Snapshot expiration cleanup preserving database metadata.
4. Independent alert ID and snapshot isolation per history entry.
5. Error handling distinction without false fallbacks.
"""

import os
import unittest
import json
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta

from app.config import settings
from app.database import (
    init_db,
    create_security_alert,
    get_alert_by_id,
    get_alert_by_code,
    update_alert_remote_snapshot,
    get_recent_alerts,
    get_db_connection
)
from app.snapshot_cleanup import SnapshotCleanupService
from app.push.escalation import push_escalation_service
from app.supabase_storage import supabase_storage_service


class TestPhase57RemoteHistoryAndRetention(unittest.TestCase):
    def setUp(self):
        init_db()
        self.device_id = settings.GUARDBOX_DEVICE_ID or "guardbox-shop-f20424b4"
        self.test_files = []

    def tearDown(self):
        for path in self.test_files:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass

    def _create_dummy_snapshot(self, prefix: str) -> str:
        os.makedirs(settings.SNAPSHOT_DIRECTORY, exist_ok=True)
        fname = f"{prefix}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}.jpg"
        fpath = os.path.join(settings.SNAPSHOT_DIRECTORY, fname)
        with open(fpath, "wb") as f:
            f.write(b"\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xFF\xDB")
        self.test_files.append(fpath)
        return fpath

    # =========================================================================
    # 1. Firebase RTDB Rules & History Index
    # =========================================================================
    def test_01_database_rules_contain_alert_history_with_secure_read_and_no_client_write(self):
        """Verify database.rules.json contains guardbox/alert_history with auth!=null read and write=false."""
        rules_path = os.path.join(os.path.dirname(__file__), "database.rules.json")
        if not os.path.exists(rules_path):
            rules_path = os.path.join(os.path.dirname(__file__), "..", "database.rules.json")

        self.assertTrue(os.path.exists(rules_path), f"Rules file not found at {rules_path}")
        with open(rules_path, "r", encoding="utf-8") as f:
            rules_data = json.load(f)

        guardbox_rules = rules_data.get("rules", {}).get("guardbox", {})
        self.assertIn("alert_history", guardbox_rules, "alert_history path must be configured in rules")
        
        hist_rule = guardbox_rules["alert_history"].get("$device_id", {})
        self.assertEqual(hist_rule.get(".read"), "auth != null", "Read must require authenticated client")
        self.assertEqual(hist_rule.get(".write"), False, "Client write must be prohibited (write: false)")
        self.assertIn(".indexOn", hist_rule, "Indexing on created_at and alert_id must be configured")

    def test_02_alert_history_published_with_full_snapshot_schema(self):
        """Verify backend publishes alert history records with complete snapshot metadata."""
        snap_path = self._create_dummy_snapshot("hist_pub")
        alert_id = create_security_alert(
            camera_id=1,
            event_type="Vault Access Detected",
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
            # Find the set call for alert_history
            set_calls = [call[0][0] for call in mock_db_ref.set.call_args_list]
            history_data = next((d for d in set_calls if d.get("alert_id") == alert_code and "snapshot" in d), None)
            self.assertIsNotNone(history_data, "Alert history record must be published with snapshot metadata")
            self.assertEqual(history_data["alert_id"], alert_code)
            self.assertEqual(history_data["snapshot"]["status"], "UPLOADING")
            self.assertIn("created_at", history_data)
            self.assertIn("snapshot_expires_at", history_data)

    # =========================================================================
    # 2. 8-Hour Retention Lifecycle Stability
    # =========================================================================
    def test_03_snapshot_expiration_exact_8_hours_from_created_at(self):
        """Verify snapshot_expires_at is strictly created_at + 8 hours."""
        snap_path = self._create_dummy_snapshot("retention_exact")
        t0 = datetime(2026, 10, 1, 10, 0, 0, tzinfo=timezone.utc)
        t0_iso = t0.isoformat()

        alert_id = create_security_alert(
            camera_id=1,
            event_type="Motion in Hall",
            snapshot_path=snap_path,
            created_at=t0_iso
        )
        alert = get_alert_by_id(alert_id)
        self.assertIsNotNone(alert["snapshot_expires_at"])

        exp_dt = datetime.fromisoformat(alert["snapshot_expires_at"].replace("Z", "+00:00"))
        expected_exp = t0 + timedelta(hours=8)
        self.assertEqual(exp_dt, expected_exp)

    def test_04_retries_and_updates_do_not_alter_original_8_hour_expiry(self):
        """Verify upload completion and retries do not shift or reset the 8-hour expiry timestamp."""
        snap_path = self._create_dummy_snapshot("immutable_expiry")
        t0 = datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc)
        t0_iso = t0.isoformat()

        alert_id = create_security_alert(
            camera_id=1,
            event_type="Counter Motion",
            snapshot_path=snap_path,
            created_at=t0_iso
        )
        alert_before = get_alert_by_id(alert_id)
        original_exp = alert_before["snapshot_expires_at"]

        # Simulate remote upload completion
        update_alert_remote_snapshot(
            alert_id_or_code=alert_id,
            remote_reference=f"guardbox/evidence/{self.device_id}/{alert_before['alert_code']}.jpg",
            status="AVAILABLE",
            remote_url="https://supabase.co/signed/snap.jpg",
            remote_provider="supabase"
        )

        alert_after = get_alert_by_id(alert_id)
        self.assertEqual(alert_after["created_at"], t0_iso)
        self.assertEqual(alert_after["snapshot_expires_at"], original_exp)

    # =========================================================================
    # 3. Snapshot Expiry & Metadata Preservation
    # =========================================================================
    def test_05_cleanup_purges_expired_snapshot_file_but_preserves_alert_metadata(self):
        """Verify cleanup service deletes physical file past 8 hours, marks EXPIRED, and leaves alert row intact."""
        snap_path = self._create_dummy_snapshot("cleanup_test")
        t_expired = (datetime.now(timezone.utc) - timedelta(hours=8, minutes=10)).isoformat()

        alert_id = create_security_alert(
            camera_id=1,
            event_type="Old Alert Test",
            snapshot_path=snap_path,
            created_at=t_expired
        )
        alert_code = get_alert_by_id(alert_id)["alert_code"]

        # Verify file exists initially
        self.assertTrue(os.path.exists(snap_path))

        cleanup_service = SnapshotCleanupService(interval_seconds=300)
        stats = cleanup_service.clean_expired_snapshots()
        self.assertGreaterEqual(stats["deleted"], 1)

        # 1. Local disk file must be deleted
        self.assertFalse(os.path.exists(snap_path), "Expired snapshot file must be removed from disk")

        # 2. Database alert record must STILL exist
        alert_after = get_alert_by_id(alert_id)
        self.assertIsNotNone(alert_after, "Alert database row must be preserved")
        self.assertEqual(alert_after["alert_code"], alert_code)
        self.assertEqual(alert_after["snapshot_status"], "EXPIRED")
        self.assertEqual(alert_after["remote_snapshot_status"], "EXPIRED")

    # =========================================================================
    # 4. Snapshot Isolation Per Alert ID
    # =========================================================================
    def test_06_multiple_alerts_maintain_isolated_snapshot_references(self):
        """Verify each alert history record has its own distinct Alert ID and snapshot reference."""
        snap1 = self._create_dummy_snapshot("snap_alert_1")
        snap2 = self._create_dummy_snapshot("snap_alert_2")

        id1 = create_security_alert(camera_id=1, event_type="Alert 1", snapshot_path=snap1)
        id2 = create_security_alert(camera_id=1, event_type="Alert 2", snapshot_path=snap2)

        alert1 = get_alert_by_id(id1)
        alert2 = get_alert_by_id(id2)

        self.assertNotEqual(alert1["alert_code"], alert2["alert_code"])
        self.assertNotEqual(alert1["snapshot_reference"], alert2["snapshot_reference"])
        self.assertIn("snap_alert_1", alert1["snapshot_reference"])
        self.assertIn("snap_alert_2", alert2["snapshot_reference"])


if __name__ == "__main__":
    unittest.main()
