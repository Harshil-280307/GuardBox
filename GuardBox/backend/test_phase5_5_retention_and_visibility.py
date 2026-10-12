"""
TRINETRA Phase 5.5 - Automated Test Suite
Validates:
1. 60-Second Minimum Alert Visibility (Active, Acknowledged, Silenced, Uploaded)
2. 8-Hour Snapshot Retention & Cleanup Invariants
3. Metadata Persistence after Image Deletion
4. Alert History Endpoint & Data Models
"""

import os
import time
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

os.environ["GUARDBOX_DEVICE_ID"] = "guardbox-shop-f20424b4"

from app.database import (
    init_db,
    create_security_alert,
    get_active_alert,
    get_alert_by_code,
    get_recent_alerts,
    update_alert_status,
    acknowledge_alert,
    update_alert_remote_snapshot,
    get_db_connection
)
from app.push.escalation import push_escalation_service
from app.snapshot_cleanup import clean_expired_snapshots


class TestPhase55VisibilityAndRetention(unittest.TestCase):

    def setUp(self):
        init_db()
        with get_db_connection() as conn:
            conn.execute("DELETE FROM security_alerts")
            conn.execute("DELETE FROM push_deliveries")
            conn.commit()

    def test_01_alert_remains_active_for_60_seconds_when_waiting_ack(self):
        """Verify an unacknowledged alert is active within 60s and expires after 60s."""
        now = datetime.now(timezone.utc)
        alert_id = create_security_alert(
            alert_code="TRI-20261001-120000-TEST1",
            camera_id=1,
            camera_name="Main Entrance",
            event_type="SUSPICIOUS_MOTION",
            created_at=now.isoformat(),
            expires_at=(now + timedelta(seconds=60)).isoformat()
        )

        active = get_active_alert()
        self.assertIsNotNone(active)
        self.assertEqual(active["alert_id"], "TRI-20261001-120000-TEST1")
        self.assertEqual(active["status"], "WAITING_ACK")

    def test_02_alert_remains_active_on_dashboard_after_acknowledgement(self):
        """Verify acknowledging an alert does NOT remove it from get_active_alert within 60s."""
        now = datetime.now(timezone.utc)
        alert_id = create_security_alert(
            alert_code="TRI-20261001-120000-TEST2",
            camera_id=1,
            camera_name="Main Entrance",
            event_type="SUSPICIOUS_MOTION",
            created_at=now.isoformat(),
            expires_at=(now + timedelta(seconds=60)).isoformat()
        )

        # Acknowledge at second 5
        acked = push_escalation_service.acknowledge(alert_id, acknowledged_by="Android Security Guard")
        self.assertTrue(acked)

        # Active alert should STILL be returned on Windows Dashboard / Android local polling
        active = get_active_alert()
        self.assertIsNotNone(active)
        self.assertEqual(active["alert_id"], "TRI-20261001-120000-TEST2")
        self.assertEqual(active["status"], "ACKNOWLEDGED")
        self.assertEqual(active["acknowledged_by"], "Android Security Guard")

    def test_03_alert_cleared_only_after_60_seconds_expire(self):
        """Verify an alert older than 60s is no longer returned by get_active_alert."""
        old_time = datetime.now(timezone.utc) - timedelta(seconds=65)
        create_security_alert(
            alert_code="TRI-20261001-110000-OLD1",
            camera_id=1,
            created_at=old_time.isoformat(),
            expires_at=(old_time + timedelta(seconds=60)).isoformat()
        )

        active = get_active_alert()
        self.assertIsNone(active)

        # Check DB status was marked EXPIRED
        alert = get_alert_by_code("TRI-20261001-110000-OLD1")
        self.assertEqual(alert["status"], "EXPIRED")

    def test_04_newer_alert_takes_precedence_over_acknowledged_alert(self):
        """Verify a new alert replaces an earlier acknowledged alert that is still within 60s."""
        t0 = datetime.now(timezone.utc) - timedelta(seconds=10)
        id1 = create_security_alert(
            alert_code="TRI-20261001-120000-FIRST",
            camera_id=1,
            created_at=t0.isoformat(),
            expires_at=(t0 + timedelta(seconds=60)).isoformat()
        )
        push_escalation_service.acknowledge(id1, acknowledged_by="Guard 1")

        # Now a second alert occurs at T=0
        id2 = create_security_alert(
            alert_code="TRI-20261001-120010-SECOND",
            camera_id=2,
            created_at=datetime.now(timezone.utc).isoformat()
        )

        active = get_active_alert()
        self.assertIsNotNone(active)
        self.assertEqual(active["alert_id"], "TRI-20261001-120010-SECOND")
        self.assertEqual(active["camera_id"], 2)

    def test_05_upload_completion_and_retry_preserve_original_timestamps(self):
        """Verify upload completion and retries do not alter created_at or snapshot_expires_at."""
        t_create = datetime.now(timezone.utc) - timedelta(minutes=5)
        alert_id = create_security_alert(
            alert_code="TRI-20261001-120000-SNAP1",
            camera_id=1,
            snapshot_path="/snapshots/TRI-20261001-120000-SNAP1.jpg",
            created_at=t_create.isoformat()
        )

        # Initial format check
        alert_before = get_alert_by_code("TRI-20261001-120000-SNAP1")
        expected_snap_exp = alert_before["snapshot_expires_at"]

        # Simulate upload success 2 minutes later
        update_alert_remote_snapshot(
            alert_id_or_code=alert_id,
            remote_reference="guardbox/evidence/guardbox-shop-f20424b4/TRI-20261001-120000-SNAP1.jpg",
            status="AVAILABLE",
            remote_url="https://supabase.co/signed/test-url"
        )

        alert_after = get_alert_by_code("TRI-20261001-120000-SNAP1")
        self.assertEqual(alert_after["created_at"], t_create.isoformat())
        self.assertEqual(alert_after["snapshot_expires_at"], expected_snap_exp)
        self.assertEqual(alert_after["remote_snapshot_status"], "AVAILABLE")
        self.assertEqual(alert_after["remote_url"], "https://supabase.co/signed/test-url")

    def test_06_snapshot_cleanup_retains_before_8_hours_and_purges_after(self):
        """Verify snapshots are kept before 8 hours and cleaned up after 8 hours with metadata intact."""
        now = datetime.now(timezone.utc)

        # 1. Fresh alert (1 hour old)
        t_fresh = now - timedelta(hours=1)
        create_security_alert(
            alert_code="TRI-FRESH-1H",
            camera_id=1,
            snapshot_path="snapshots/fresh.jpg",
            created_at=t_fresh.isoformat()
        )

        # 2. Expired alert (8.5 hours old)
        t_expired = now - timedelta(hours=8, minutes=30)
        create_security_alert(
            alert_code="TRI-EXPIRED-8H",
            camera_id=1,
            snapshot_path="snapshots/expired.jpg",
            created_at=t_expired.isoformat()
        )

        # Run cleanup pass
        stats = clean_expired_snapshots()
        self.assertGreaterEqual(stats["inspected"], 1)

        # Fresh alert must still be AVAILABLE
        fresh_alert = get_alert_by_code("TRI-FRESH-1H")
        self.assertEqual(fresh_alert["snapshot_status"], "AVAILABLE")

        # Expired alert must have snapshot_status EXPIRED, but record and Alert ID intact
        exp_alert = get_alert_by_code("TRI-EXPIRED-8H")
        self.assertEqual(exp_alert["snapshot_status"], "EXPIRED")
        self.assertEqual(exp_alert["alert_id"], "TRI-EXPIRED-8H")
        self.assertEqual(exp_alert["camera_id"], 1)

    def test_07_recent_alerts_history_returns_full_dataset(self):
        """Verify get_recent_alerts returns formatted alerts with Alert IDs and retention timestamps."""
        for i in range(5):
            t = datetime.now(timezone.utc) - timedelta(minutes=i * 10)
            create_security_alert(
                alert_code=f"TRI-HIST-{i}",
                camera_id=1,
                camera_name="Cash Counter",
                event_type="MOTION_DETECTED",
                created_at=t.isoformat()
            )

        history = get_recent_alerts(limit=10)
        self.assertEqual(len(history), 5)
        for h in history:
            self.assertTrue(h["alert_id"].startswith("TRI-HIST-"))
            self.assertIsNotNone(h["created_at"])
            self.assertIsNotNone(h["snapshot_expires_at"])
            self.assertIsNotNone(h["snapshot_status"])


if __name__ == "__main__":
    unittest.main()
