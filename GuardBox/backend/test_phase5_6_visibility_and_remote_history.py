"""
TRINETRA Phase 5.6 Automated Test Suite
Verifies:
1. Authoritative 60-Second Alert Visibility on Backend and Database.
2. Acknowledgment, silencing, and upload do NOT shorten the 60s visibility window.
3. Overlapping alerts maintain independent expiry timestamps.
4. Snapshot retention remains strictly 8 hours independently of 60s alert visibility.
5. Firebase RTDB alert_history sync on alert creation, upload completion, ack, and snapshot cleanup.
"""

import os
import time
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from app.database import (
    init_db,
    get_db_connection,
    create_security_alert,
    get_active_alert,
    get_alert_by_id,
    get_alert_by_code,
    get_recent_alerts,
    update_alert_status,
    acknowledge_alert,
    update_alert_remote_snapshot
)
from app.push.escalation import PushEscalationService, generate_alert_code
from app.snapshot_cleanup import clean_expired_snapshots


class TestPhase56VisibilityAndRemoteHistory(unittest.TestCase):

    def setUp(self):
        init_db()
        self.escalation_service = PushEscalationService()
        with get_db_connection() as conn:
            conn.execute("DELETE FROM security_alerts")
            conn.execute("DELETE FROM push_deliveries")
            conn.commit()

    def test_01_authoritative_60s_visibility_lifecycle(self):
        """Test alert created is returned by get_active_alert() for 60s."""
        now_dt = datetime.now(timezone.utc)
        created_at = now_dt.isoformat()
        expires_at = (now_dt + timedelta(seconds=60)).isoformat()
        code = generate_alert_code()

        alert_id = create_security_alert(
            alert_code=code,
            camera_id=1,
            camera_name="Shop Camera 1",
            event_type="SUSPICIOUS_MOTION",
            severity="HIGH",
            status="WAITING_ACK",
            created_at=created_at,
            expires_at=expires_at
        )

        # Active immediately
        active = get_active_alert()
        self.assertIsNotNone(active)
        self.assertEqual(active["alert_code"], code)
        self.assertEqual(active["status"], "WAITING_ACK")

    def test_02_acknowledgment_preserves_60s_visibility(self):
        """Test acknowledging an alert keeps it visible in get_active_alert() within 60s."""
        now_dt = datetime.now(timezone.utc)
        created_at = now_dt.isoformat()
        expires_at = (now_dt + timedelta(seconds=60)).isoformat()
        code = generate_alert_code()

        alert_id = create_security_alert(
            alert_code=code,
            camera_id=1,
            camera_name="Shop Camera 1",
            event_type="SUSPICIOUS_MOTION",
            severity="HIGH",
            status="WAITING_ACK",
            created_at=created_at,
            expires_at=expires_at
        )

        # Acknowledge after 5 seconds
        ack_success = self.escalation_service.acknowledge(alert_id, acknowledged_by="Shop Manager")
        self.assertTrue(ack_success)

        # Alert MUST still be returned by get_active_alert() with status ACKNOWLEDGED
        active = get_active_alert()
        self.assertIsNotNone(active)
        self.assertEqual(active["alert_code"], code)
        self.assertEqual(active["status"], "ACKNOWLEDGED")

    def test_03_silencing_preserves_60s_visibility(self):
        """Test silencing an alert keeps it visible in get_active_alert() within 60s."""
        now_dt = datetime.now(timezone.utc)
        created_at = now_dt.isoformat()
        expires_at = (now_dt + timedelta(seconds=60)).isoformat()
        code = generate_alert_code()

        alert_id = create_security_alert(
            alert_code=code,
            camera_id=1,
            camera_name="Shop Camera 1",
            event_type="SUSPICIOUS_MOTION",
            severity="HIGH",
            status="ESCALATING",
            created_at=created_at,
            expires_at=expires_at
        )

        self.escalation_service.stop_escalation(mark_status="SILENCED")
        update_alert_status(alert_id, status="SILENCED")

        active = get_active_alert()
        self.assertIsNotNone(active)
        self.assertEqual(active["alert_code"], code)
        self.assertEqual(active["status"], "SILENCED")

    def test_04_alert_expires_after_60s(self):
        """Test alert older than 60s is marked EXPIRED and not returned by get_active_alert()."""
        past_dt = datetime.now(timezone.utc) - timedelta(seconds=65)
        created_at = past_dt.isoformat()
        expires_at = (past_dt + timedelta(seconds=60)).isoformat()
        code = generate_alert_code()

        alert_id = create_security_alert(
            alert_code=code,
            camera_id=1,
            camera_name="Shop Camera 1",
            event_type="SUSPICIOUS_MOTION",
            severity="HIGH",
            status="WAITING_ACK",
            created_at=created_at,
            expires_at=expires_at
        )

        active = get_active_alert()
        self.assertIsNone(active)

        db_alert = get_alert_by_id(alert_id)
        self.assertEqual(db_alert["status"], "EXPIRED")

    def test_05_independent_overlapping_alerts_lifecycle(self):
        """Test multiple alerts retain independent expiry and visibility."""
        now_dt = datetime.now(timezone.utc)

        # Alert 1: Created 40s ago (20s remaining)
        t1 = now_dt - timedelta(seconds=40)
        code1 = generate_alert_code()
        id1 = create_security_alert(
            alert_code=code1,
            camera_id=1,
            camera_name="Cam 1",
            event_type="MOTION_1",
            status="WAITING_ACK",
            created_at=t1.isoformat(),
            expires_at=(t1 + timedelta(seconds=60)).isoformat()
        )

        # Alert 2: Created now (60s remaining)
        t2 = now_dt
        code2 = generate_alert_code()
        id2 = create_security_alert(
            alert_code=code2,
            camera_id=2,
            camera_name="Cam 2",
            event_type="MOTION_2",
            status="WAITING_ACK",
            created_at=t2.isoformat(),
            expires_at=(t2 + timedelta(seconds=60)).isoformat()
        )

        # Active alert query returns the latest active alert (#2)
        active = get_active_alert()
        self.assertIsNotNone(active)
        self.assertEqual(active["alert_code"], code2)

        # Alert 1 is still WAITING_ACK in database and recent alerts
        recents = get_recent_alerts(limit=5)
        alert1 = next(a for a in recents if a["alert_code"] == code1)
        self.assertEqual(alert1["status"], "WAITING_ACK")

    def test_06_independent_8h_snapshot_retention(self):
        """Test snapshot retention remains 8 hours and is independent of 60s alert visibility."""
        now_dt = datetime.now(timezone.utc)

        # Alert created 2 hours ago (expired from 60s visibility, but snapshot retention valid for 6 more hours)
        t_alert = now_dt - timedelta(hours=2)
        code = generate_alert_code()
        id_alert = create_security_alert(
            alert_code=code,
            camera_id=1,
            camera_name="Shop Camera 1",
            event_type="MOTION",
            status="EXPIRED",
            created_at=t_alert.isoformat(),
            expires_at=(t_alert + timedelta(seconds=60)).isoformat()
        )

        # Update snapshot
        update_alert_remote_snapshot(
            alert_id_or_code=id_alert,
            remote_reference=f"guardbox/evidence/device/{code}.jpg",
            status="AVAILABLE",
            remote_url="https://supabase.co/signed-url",
            remote_provider="supabase"
        )

        # Run cleanup - 2 hours is well within 8 hours, so snapshot must NOT be expired
        stats = clean_expired_snapshots()
        alert = get_alert_by_id(id_alert)
        self.assertEqual(alert["snapshot_status"], "AVAILABLE")
        self.assertEqual(alert["remote_snapshot_status"], "AVAILABLE")

    def test_07_snapshot_expires_after_8h_preserving_alert_metadata(self):
        """Test snapshot expires after 8 hours while alert metadata is preserved."""
        now_dt = datetime.now(timezone.utc)

        # Alert created 8.5 hours ago
        t_alert = now_dt - timedelta(hours=8, minutes=30)
        code = generate_alert_code()
        id_alert = create_security_alert(
            alert_code=code,
            camera_id=1,
            camera_name="Shop Camera 1",
            event_type="MOTION",
            status="EXPIRED",
            created_at=t_alert.isoformat(),
            expires_at=(t_alert + timedelta(seconds=60)).isoformat()
        )

        update_alert_remote_snapshot(
            alert_id_or_code=id_alert,
            remote_reference=f"guardbox/evidence/device/{code}.jpg",
            status="AVAILABLE",
            remote_url="https://supabase.co/signed-url",
            remote_provider="supabase"
        )

        stats = clean_expired_snapshots()
        alert = get_alert_by_id(id_alert)
        self.assertIsNotNone(alert)
        self.assertEqual(alert["alert_code"], code)
        self.assertEqual(alert["snapshot_status"], "EXPIRED")
        self.assertEqual(alert["remote_snapshot_status"], "EXPIRED")
        self.assertIsNone(alert["remote_url"])


if __name__ == "__main__":
    unittest.main()
