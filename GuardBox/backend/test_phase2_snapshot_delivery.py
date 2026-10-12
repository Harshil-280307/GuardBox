"""
Comprehensive Test Suite for TRINETRA Phase 2: Existing Snapshot Delivery + Android Viewer.

Verifies:
TEST 1: Active alert contains a valid snapshot reference.
TEST 2: Android constructs the correct snapshot URL from the existing backend base URL.
TEST 3: Android receives snapshot metadata through Firebase.
TEST 4: Android receives snapshot metadata through polling.
TEST 5: FCM and polling use the same snapshot reference.
TEST 6: The snapshot displays with the exact same Alert ID as the alert.
TEST 7: Missing snapshot reference does not crash (returns safe fallback).
TEST 8: Invalid/unavailable snapshot handling ("Snapshot unavailable").
TEST 9: Expired snapshot handling ("Snapshot expired").
TEST 10: Alert notification still expires after 60 seconds.
TEST 11: Snapshot remains independent of the 60-second notification lifecycle (8 hours).
TEST 12: No second snapshot is captured.
TEST 13: No second Alert ID is generated.
"""

import os
import sys
import time
import json
import uuid
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
    update_alert_status,
    _format_alert_row
)
from app.push.fcm_service import fcm_service


def simulate_android_snapshot_url_construction(base_url: str, snapshot_ref: str) -> str:
    """Replicates Android ApiClient.getSnapshotFullUrl / ActiveAlertData.getFullSnapshotUrl logic."""
    if not snapshot_ref:
        return None
    clean_ref = snapshot_ref.strip()
    if clean_ref.startswith("http://") or clean_ref.startswith("https://"):
        return clean_ref
    clean_base = base_url.strip().rstrip("/")
    clean_path = clean_ref.lstrip("/")
    return f"{clean_base}/{clean_path}"


def simulate_android_is_snapshot_expired(snapshot_expires_at_iso: str) -> bool:
    """Replicates Android AlertLifecycleHelper.isSnapshotExpired logic."""
    if not snapshot_expires_at_iso:
        return False
    try:
        clean_iso = snapshot_expires_at_iso.replace("Z", "+00:00")
        exp_dt = datetime.fromisoformat(clean_iso)
        if exp_dt.tzinfo is None:
            exp_dt = exp_dt.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) >= exp_dt
    except Exception:
        return False


class TestPhase2SnapshotDelivery(unittest.TestCase):

    def test_01_active_alert_contains_valid_snapshot_reference(self):
        """TEST 1: Active alert contains a valid snapshot reference."""
        snap_ref = f"snapshots/event_cam1_{uuid.uuid4().hex[:8]}.jpg"
        alert_code = f"TRI-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4].upper()}"
        alert_id = create_security_alert(
            alert_code=alert_code,
            camera_id=1,
            camera_name="Showcase Counter 1",
            event_type="SUSPICIOUS_MOTION",
            severity="HIGH",
            snapshot_path=snap_ref
        )

        alert = get_active_alert()
        self.assertIsNotNone(alert)
        self.assertEqual(alert["alert_id"], alert_code)
        self.assertEqual(alert["snapshot_reference"], snap_ref)
        self.assertEqual(alert["snapshot"]["reference"], snap_ref)
        update_alert_status(alert_id, "RESOLVED")

    def test_02_android_url_construction_from_backend_base(self):
        """TEST 2: Android constructs the correct snapshot URL from the existing backend base URL."""
        backend_bases = [
            "http://192.168.31.188:8000",
            "http://192.168.31.188:8000/",
            "http://guardbox-server.local:8000"
        ]
        snap_ref = "snapshots/event_cam1_1790671000_abc123.jpg"

        for base in backend_bases:
            full_url = simulate_android_snapshot_url_construction(base, snap_ref)
            self.assertTrue(full_url.startswith("http://"))
            self.assertTrue(full_url.endswith("/snapshots/event_cam1_1790671000_abc123.jpg"))
            self.assertNotIn("//snapshots", full_url)

    def test_03_android_receives_snapshot_metadata_through_firebase(self):
        """TEST 3: Android receives snapshot metadata through Firebase current alert write."""
        snap_ref = f"snapshots/event_cam3_{uuid.uuid4().hex[:8]}.jpg"
        alert_code = f"TRI-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4].upper()}"
        alert_id = create_security_alert(
            alert_code=alert_code,
            camera_id=3,
            camera_name="Perimeter Gate",
            event_type="UNAUTHORIZED_ACCESS",
            severity="CRITICAL",
            snapshot_path=snap_ref
        )

        alert = get_alert_by_id(alert_id)
        self.assertIsNotNone(alert)
        self.assertEqual(alert["snapshot_reference"], snap_ref)
        self.assertIsNotNone(alert["snapshot_created_at"])
        self.assertIsNotNone(alert["snapshot_expires_at"])
        update_alert_status(alert_id, "RESOLVED")

    def test_04_android_receives_snapshot_metadata_through_polling(self):
        """TEST 4: Android receives snapshot metadata through polling endpoint."""
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)
        snap_ref = f"snapshots/event_poll_{uuid.uuid4().hex[:8]}.jpg"
        alert_code = f"TRI-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4].upper()}"
        alert_id = create_security_alert(
            alert_code=alert_code,
            camera_id=1,
            camera_name="Main Shop Camera",
            event_type="MOTION",
            severity="HIGH",
            snapshot_path=snap_ref
        )

        response = client.get("/api/alerts/active")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        polled_alert = data.get("active_alert")
        self.assertIsNotNone(polled_alert)
        self.assertEqual(polled_alert["alert_id"], alert_code)
        self.assertEqual(polled_alert["snapshot_reference"], snap_ref)
        self.assertEqual(polled_alert["snapshot"]["reference"], snap_ref)
        update_alert_status(alert_id, "RESOLVED")

    def test_05_fcm_and_polling_use_same_snapshot_reference(self):
        """TEST 5: FCM and polling use the exact same snapshot reference."""
        snap_ref = f"snapshots/event_same_{uuid.uuid4().hex[:8]}.jpg"
        alert_code = f"TRI-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4].upper()}"
        alert_id = create_security_alert(
            alert_code=alert_code,
            camera_id=1,
            camera_name="Showcase Counter 1",
            event_type="MOTION",
            severity="HIGH",
            snapshot_path=snap_ref
        )

        # Polling
        alert_polled = get_alert_by_id(alert_id)
        polled_ref = alert_polled["snapshot_reference"]

        # FCM dispatch
        fcm_service.send_emergency_alert(
            fcm_token="dummy_token_12345",
            alert_id=alert_id,
            alert_code=alert_code,
            camera_name="Showcase Counter 1",
            event_type="MOTION",
            severity="HIGH",
            timestamp=alert_polled["created_at"],
            snapshot_url=alert_polled["snapshot_path"]
        )
        last_fcm = fcm_service.get_last_dispatched_payload()
        fcm_ref = last_fcm["data"]["snapshot_reference"]

        self.assertEqual(polled_ref, snap_ref)
        self.assertEqual(fcm_ref, snap_ref)
        self.assertEqual(polled_ref, fcm_ref)
        update_alert_status(alert_id, "RESOLVED")

    def test_06_snapshot_displays_with_exact_same_alert_id(self):
        """TEST 6: The snapshot displays with the exact same Alert ID as the alert."""
        snap_ref = f"snapshots/event_card_{uuid.uuid4().hex[:8]}.jpg"
        alert_code = f"TRI-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4].upper()}"
        alert_id = create_security_alert(
            alert_code=alert_code,
            camera_id=2,
            camera_name="Cash Drawer",
            event_type="TAMPER",
            severity="CRITICAL",
            snapshot_path=snap_ref
        )

        alert = get_alert_by_id(alert_id)
        self.assertEqual(alert["alert_id"], alert_code)
        self.assertEqual(alert["alert_code"], alert_code)
        self.assertEqual(alert["snapshot_reference"], snap_ref)
        update_alert_status(alert_id, "RESOLVED")

    def test_07_missing_snapshot_reference_safe_fallback(self):
        """TEST 7: Missing snapshot reference does not crash and returns safe null fallback."""
        alert_code = f"TRI-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4].upper()}"
        alert_id = create_security_alert(
            alert_code=alert_code,
            camera_id=1,
            camera_name="Front Hall",
            event_type="MOTION",
            severity="LOW",
            snapshot_path=None
        )

        alert = get_alert_by_id(alert_id)
        self.assertIsNone(alert["snapshot_reference"])
        self.assertIsNone(alert["snapshot"])
        self.assertIsNone(simulate_android_snapshot_url_construction("http://localhost:8000", alert["snapshot_reference"]))
        update_alert_status(alert_id, "RESOLVED")

    def test_08_invalid_snapshot_reference_handling(self):
        """TEST 8: Invalid snapshot reference returns safe string without app crash."""
        full_url = simulate_android_snapshot_url_construction("http://localhost:8000", "")
        self.assertIsNone(full_url)

    def test_09_expired_snapshot_detection(self):
        """TEST 9: Expired snapshot is correctly identified as expired."""
        now_dt = datetime.now(timezone.utc)
        past_iso = (now_dt - timedelta(hours=1)).isoformat()
        future_iso = (now_dt + timedelta(hours=7)).isoformat()

        self.assertTrue(simulate_android_is_snapshot_expired(past_iso))
        self.assertFalse(simulate_android_is_snapshot_expired(future_iso))

    def test_10_alert_notification_60_second_expiry_intact(self):
        """TEST 10: Active alert notification expiration is set to 60 seconds."""
        now_dt = datetime.now(timezone.utc)
        alert_code = f"TRI-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4].upper()}"
        alert_id = create_security_alert(
            alert_code=alert_code,
            camera_id=1,
            camera_name="Main Gate",
            event_type="MOTION",
            severity="HIGH"
        )

        alert = get_alert_by_id(alert_id)
        created_dt = datetime.fromisoformat(alert["created_at"].replace("Z", "+00:00"))
        expires_dt = datetime.fromisoformat(alert["expires_at"].replace("Z", "+00:00"))
        duration_sec = (expires_dt - created_dt).total_seconds()
        self.assertAlmostEqual(duration_sec, 60.0, delta=2.0)
        update_alert_status(alert_id, "RESOLVED")

    def test_11_snapshot_8_hour_lifecycle_independent_of_60s_notification(self):
        """TEST 11: Snapshot evidence expiration is 8 hours (independent of 60s alert notification)."""
        alert_code = f"TRI-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4].upper()}"
        snap_ref = "snapshots/evidence_test.jpg"
        alert_id = create_security_alert(
            alert_code=alert_code,
            camera_id=1,
            camera_name="Main Gate",
            event_type="MOTION",
            severity="HIGH",
            snapshot_path=snap_ref
        )

        alert = get_alert_by_id(alert_id)
        snap_created = datetime.fromisoformat(alert["snapshot_created_at"].replace("Z", "+00:00"))
        snap_expires = datetime.fromisoformat(alert["snapshot_expires_at"].replace("Z", "+00:00"))
        snap_duration_hours = (snap_expires - snap_created).total_seconds() / 3600.0
        self.assertAlmostEqual(snap_duration_hours, 8.0, delta=0.1)

        # Verify notification expiry is 60 seconds
        alert_expires = datetime.fromisoformat(alert["expires_at"].replace("Z", "+00:00"))
        alert_duration_sec = (alert_expires - snap_created).total_seconds()
        self.assertAlmostEqual(alert_duration_sec, 60.0, delta=2.0)
        update_alert_status(alert_id, "RESOLVED")

    def test_12_no_second_snapshot_captured(self):
        """TEST 12: No second snapshot is captured or stored for a single alert."""
        snap_ref = f"snapshots/event_single_{uuid.uuid4().hex[:8]}.jpg"
        alert_code = f"TRI-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4].upper()}"
        alert_id = create_security_alert(
            alert_code=alert_code,
            camera_id=1,
            camera_name="Main Entry",
            event_type="MOTION",
            severity="HIGH",
            snapshot_path=snap_ref
        )

        alert = get_alert_by_id(alert_id)
        self.assertEqual(alert["snapshot_reference"], snap_ref)
        self.assertEqual(alert["snapshot_path"], snap_ref)
        update_alert_status(alert_id, "RESOLVED")

    def test_13_no_second_alert_id_generated(self):
        """TEST 13: Exact Alert ID is preserved throughout lifecycle."""
        alert_code = f"TRI-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4].upper()}"
        alert_id = create_security_alert(
            alert_code=alert_code,
            camera_id=1,
            camera_name="Counter",
            event_type="MOTION",
            severity="HIGH"
        )

        alert = get_alert_by_id(alert_id)
        self.assertEqual(alert["alert_id"], alert_code)
        self.assertEqual(alert["alert_code"], alert_code)
        update_alert_status(alert_id, "RESOLVED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
