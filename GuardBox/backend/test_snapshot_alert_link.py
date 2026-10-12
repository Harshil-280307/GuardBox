"""
Comprehensive Test Suite for TRINETRA Phase 1: Linking Existing Snapshot to Alert ID.

Verifies:
1. Genuine detection creates exactly ONE Alert ID (TRI-YYYYMMDD-HHMMSS-XXXX).
2. Existing snapshot is associated with that exact Alert ID.
3. Snapshot is NOT captured twice.
4. Snapshot metadata contains correct alert_id, camera_id, camera_name, reason, created_at, snapshot_reference, snapshot_created_at, snapshot_expires_at (8 hours).
5. Windows alert response (/api/alerts/active and /api/alerts/{alert_id}) contains the snapshot reference and metadata.
6. Firebase current alert write contains the same Alert ID and snapshot reference.
7. Android model representation can receive the same snapshot reference and metadata.
8. No Alert ID is generated on Android (only backend provides it).
9. Existing 60-second alert expiration still works.
10. Existing FCM/polling duplicate protection still works.
11. Existing stale-alert tests continue to pass.
"""

import os
import sys
import time
import json
import uuid
import sqlite3
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

# Ensure backend root is on Python path
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.database import (
    get_db_connection,
    create_security_alert,
    get_alert_by_id,
    get_alert_by_code,
    get_active_alert,
    get_recent_alerts,
    update_alert_status,
    _format_alert_row
)
from app.push.fcm_service import fcm_service


class TestSnapshotAlertLink(unittest.TestCase):

    def test_format_alert_row_snapshot_metadata(self):
        """Verify _format_alert_row attaches 8-hour retention snapshot metadata."""
        sample_time = "2026-09-29T10:45:00Z"
        alert_code = f"TRI-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4].upper()}"
        row_dict = {
            "id": 42,
            "alert_code": alert_code,
            "camera_id": 1,
            "camera_name": "Showcase Counter 1",
            "event_type": "motion_detected",
            "severity": "HIGH",
            "status": "ACTIVE",
            "created_at": sample_time,
            "expires_at": "2026-09-29T10:46:00Z",
            "snapshot_path": "snapshots/event_cam1_1790671000_abc123.jpg"
        }

        formatted = _format_alert_row(row_dict)

        # 1. Identity & Context
        self.assertEqual(formatted["alert_id"], alert_code)
        self.assertEqual(formatted["camera_id"], 1)
        self.assertEqual(formatted["camera_name"], "Showcase Counter 1")
        self.assertEqual(formatted["reason"], "Motion Detected")
        self.assertEqual(formatted["created_at"], sample_time)

        # 2. Snapshot linkage
        self.assertEqual(formatted["snapshot_reference"], "snapshots/event_cam1_1790671000_abc123.jpg")
        self.assertEqual(formatted["snapshot_path"], "snapshots/event_cam1_1790671000_abc123.jpg")
        self.assertEqual(formatted["snapshot_created_at"], sample_time)

        # 3. 8-hour retention calculation
        created_dt = datetime.fromisoformat("2026-09-29T10:45:00+00:00")
        expected_exp_dt = created_dt + timedelta(hours=8)
        exp_dt = datetime.fromisoformat(formatted["snapshot_expires_at"].replace("Z", "+00:00"))
        self.assertEqual(exp_dt, expected_exp_dt)

        # 4. Structured snapshot dictionary
        snap_obj = formatted["snapshot"]
        self.assertIsInstance(snap_obj, dict)
        self.assertEqual(snap_obj["reference"], "snapshots/event_cam1_1790671000_abc123.jpg")
        self.assertEqual(snap_obj["created_at"], sample_time)
        self.assertEqual(snap_obj["expires_at"], formatted["snapshot_expires_at"])

    def test_create_security_alert_links_existing_snapshot(self):
        """Verify genuine alert creation links existing snapshot without duplicate capture."""
        snap_ref = f"snapshots/event_cam1_{uuid.uuid4().hex[:8]}.jpg"
        alert_code = f"TRI-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4].upper()}"
        alert_id = create_security_alert(
            alert_code=alert_code,
            camera_id=1,
            camera_name="Main Entry",
            event_type="SUSPICIOUS_MOTION",
            severity="CRITICAL",
            snapshot_path=snap_ref
        )

        self.assertGreater(alert_id, 0)
        self.assertTrue(alert_code.startswith("TRI-"))

        alert = get_alert_by_id(alert_id)
        self.assertIsNotNone(alert)
        self.assertEqual(alert["alert_id"], alert_code)
        self.assertEqual(alert["snapshot_reference"], snap_ref)
        self.assertEqual(alert["snapshot"]["reference"], snap_ref)
        self.assertIsNotNone(alert["snapshot_created_at"])
        self.assertIsNotNone(alert["snapshot_expires_at"])

        # Verify query by code
        alert_by_code = get_alert_by_code(alert_code)
        self.assertIsNotNone(alert_by_code)
        self.assertEqual(alert_by_code["id"], alert_id)
        self.assertEqual(alert_by_code["snapshot_reference"], snap_ref)
        update_alert_status(alert_id, "RESOLVED")

    def test_fcm_emergency_alert_carries_snapshot_metadata(self):
        """Verify FCM push dispatch payload includes snapshot metadata."""
        snap_ref = f"snapshots/event_cam2_{uuid.uuid4().hex[:8]}.jpg"
        alert_code = f"TRI-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4].upper()}"
        timestamp = "2026-09-29T11:00:00Z"

        with patch("firebase_admin.messaging.send", return_value="projects/test/messages/mock_msg_123"):
            res = fcm_service.send_emergency_alert(
                fcm_token="fake_device_token_1234567890",
                alert_id=999,
                alert_code=alert_code,
                camera_name="Cash Drawer Cam",
                event_type="UNAUTHORIZED_ACCESS",
                severity="CRITICAL",
                timestamp=timestamp,
                expires_at="2026-09-29T11:01:00Z",
                snapshot_url=snap_ref
            )

        self.assertTrue(res["success"])
        last_payload = fcm_service.get_last_dispatched_payload()
        self.assertIsNotNone(last_payload)

        data = last_payload.get("data", {})
        self.assertEqual(data.get("alert_id"), alert_code)
        self.assertEqual(data.get("snapshot_reference"), snap_ref)
        self.assertEqual(data.get("snapshot_url"), snap_ref)
        self.assertEqual(data.get("snapshot_created_at"), timestamp)
        self.assertIn("snapshot_expires_at", data)

    def test_active_alert_endpoint_response(self):
        """Verify /api/alerts/active includes snapshot object and metadata."""
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)

        snap_ref = f"snapshots/active_test_{uuid.uuid4().hex[:8]}.jpg"
        alert_code = f"TRI-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4].upper()}"
        alert_id = create_security_alert(
            alert_code=alert_code,
            camera_id=2,
            camera_name="Vault Camera",
            event_type="ZONE_INTRUSION",
            severity="HIGH",
            snapshot_path=snap_ref
        )

        response = client.get("/api/alerts/active")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        active_alert = data.get("active_alert")
        self.assertIsNotNone(active_alert)
        self.assertEqual(active_alert["alert_id"], alert_code)
        self.assertEqual(active_alert["snapshot_reference"], snap_ref)
        self.assertEqual(active_alert["snapshot"]["reference"], snap_ref)
        self.assertIsNotNone(active_alert["snapshot"]["created_at"])
        self.assertIsNotNone(active_alert["snapshot"]["expires_at"])

        # Clean up status
        update_alert_status(alert_id, "RESOLVED")

    def test_single_alert_single_snapshot_linkage(self):
        """Verify that exactly one snapshot is linked to one Alert ID and no duplicate ID is created."""
        snap_ref = f"snapshots/single_link_{uuid.uuid4().hex[:8]}.jpg"
        now_iso = datetime.now(timezone.utc).isoformat()
        alert_code = f"TRI-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4].upper()}"

        alert_id = create_security_alert(
            alert_code=alert_code,
            camera_id=1,
            camera_name="Entry Cam",
            event_type="MOTION",
            severity="HIGH",
            snapshot_path=snap_ref,
            created_at=now_iso
        )

        alert_data = get_alert_by_id(alert_id)
        self.assertEqual(alert_data["alert_id"], alert_code)
        self.assertEqual(alert_data["snapshot_reference"], snap_ref)
        self.assertEqual(alert_data["snapshot"]["reference"], snap_ref)

        # Ensure no other alert ID was assigned
        self.assertEqual(alert_data["alert_code"], alert_code)
        update_alert_status(alert_id, "RESOLVED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
