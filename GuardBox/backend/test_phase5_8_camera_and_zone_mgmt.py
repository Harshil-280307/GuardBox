"""
Phase 5.8 Regression & Unit Tests
Verifies:
1. Camera management CRUD, status sync, and deletion without affecting other cameras.
2. Independent detection zone controls:
   - Zone A disabled while Zone B enabled.
   - Motion inside disabled zone does not trigger alerts.
   - Motion inside enabled zone continues triggering alerts.
   - Zone state persists across database reloads.
   - Editing or toggling one zone does not alter other zones.
"""

import unittest
import numpy as np
import cv2
import time
from datetime import datetime, timezone
from app.database import (
    get_db_connection,
    create_camera,
    get_camera_by_id,
    get_all_cameras,
    update_camera,
    delete_camera,
    toggle_camera,
    create_zone,
    get_zone_by_id,
    get_zones_by_camera,
    update_zone,
    delete_zone,
    toggle_zone,
    clear_zones_by_camera,
    get_filtered_events
)
from app.camera import CameraManager, CameraWorker
from app.detection import CameraMotionDetector, MotionDetectionService


class Phase58CameraAndZoneManagementTests(unittest.TestCase):

    def setUp(self):
        # Clear any stale test zones on camera 1
        clear_zones_by_camera(1)

    def tearDown(self):
        clear_zones_by_camera(1)

    # --------------------------------------------------------------------------
    # 1. Camera Management & Status Synchronization Tests
    # --------------------------------------------------------------------------

    def test_camera_crud_and_status_sync(self):
        """Test creating, status reporting, toggling, and safely deleting a camera."""
        cm = CameraManager()

        # Add a secondary test camera
        cam2_id = create_camera(
            name="Test Backyard Cam",
            brand="Hikvision",
            model="DS-2CD",
            rtsp_url="rtsp://admin:pass@192.168.1.100:554/stream1",
            enabled=True
        )
        self.assertIsNotNone(cam2_id)

        # Retrieve camera status
        status = cm.get_camera_status(cam2_id)
        self.assertIsNotNone(status)
        self.assertEqual(status["id"], cam2_id)
        self.assertEqual(status["name"], "Test Backyard Cam")
        self.assertTrue(status["enabled"])
        self.assertEqual(status["status"], "offline")  # Not connected yet

        # Toggle camera to disabled
        toggle_camera(cam2_id, enabled=False)
        cam2_data = get_camera_by_id(cam2_id)
        self.assertFalse(bool(cam2_data["enabled"]))

        status_disabled = cm.get_camera_status(cam2_id)
        self.assertEqual(status_disabled["status"], "disabled")
        self.assertFalse(status_disabled["enabled"])

        # Test worker get_status when disabled
        worker = CameraWorker(
            camera_id=cam2_id,
            name="Test Backyard Cam",
            brand="Hikvision",
            model="DS-2CD",
            rtsp_url="rtsp://admin:pass@192.168.1.100:554/stream1",
            enabled=False
        )
        st = worker.get_status()
        self.assertEqual(st["status"], "disabled")
        self.assertFalse(st["enabled"])

        # Delete camera 2
        deleted = cm.remove_camera(cam2_id)
        self.assertTrue(deleted)

        # Confirm camera 2 is completely removed from DB
        self.assertIsNone(get_camera_by_id(cam2_id))

        # Confirm primary camera 1 is still present and unaffected
        cam1 = get_camera_by_id(1)
        self.assertIsNotNone(cam1)
        self.assertEqual(cam1["id"], 1)

    # --------------------------------------------------------------------------
    # 2. Independent Detection Zone Controls Tests
    # --------------------------------------------------------------------------

    def test_independent_zone_controls_and_persistence(self):
        """Test that multiple zones can be toggled independently and states persist."""
        # Create Zone A (Cash Counter)
        zone_a_id = create_zone(
            camera_id=1,
            name="Zone A - Cash Counter",
            points=[[0.1, 0.1], [0.4, 0.1], [0.4, 0.4], [0.1, 0.4]],
            color="#FF3B30",
            enabled=True
        )

        # Create Zone B (Display Showcase)
        zone_b_id = create_zone(
            camera_id=1,
            name="Zone B - Display Showcase",
            points=[[0.6, 0.6], [0.9, 0.6], [0.9, 0.9], [0.6, 0.9]],
            color="#2563EB",
            enabled=True
        )

        self.assertIsNotNone(zone_a_id)
        self.assertIsNotNone(zone_b_id)

        # Both zones start enabled
        za = get_zone_by_id(zone_a_id)
        zb = get_zone_by_id(zone_b_id)
        self.assertTrue(bool(za["enabled"]))
        self.assertTrue(bool(zb["enabled"]))

        # Disable Zone A
        updated_za = toggle_zone(zone_a_id, enabled=False)
        self.assertFalse(bool(updated_za["enabled"]))

        # Confirm Zone B is STILL enabled (independent!)
        zb_check = get_zone_by_id(zone_b_id)
        self.assertTrue(bool(zb_check["enabled"]))

        # Re-enable Zone A without explicitly specifying enabled (toggle invert)
        updated_za_2 = toggle_zone(zone_a_id)
        self.assertTrue(bool(updated_za_2["enabled"]))

        # Disable Zone B
        updated_zb = toggle_zone(zone_b_id, enabled=False)
        self.assertFalse(bool(updated_zb["enabled"]))

        # Confirm Zone A remains enabled
        za_check = get_zone_by_id(zone_a_id)
        self.assertTrue(bool(za_check["enabled"]))

        # Test persistence across new DB query
        zones = get_zones_by_camera(1)
        self.assertEqual(len(zones), 2)
        zone_map = {z["id"]: bool(z["enabled"]) for z in zones}
        self.assertTrue(zone_map[zone_a_id])
        self.assertFalse(zone_map[zone_b_id])

        # Delete Zone A and ensure Zone B remains
        delete_zone(zone_a_id)
        self.assertIsNone(get_zone_by_id(zone_a_id))
        self.assertIsNotNone(get_zone_by_id(zone_b_id))

    # --------------------------------------------------------------------------
    # 3. Detection Runtime Filtering Tests
    # --------------------------------------------------------------------------

    def test_disabled_zone_does_not_trigger_motion_alert(self):
        """Test that motion strictly inside a disabled zone does not trigger events, while enabled zone does."""
        # Create Zone A (Left side: x: 0.05-0.45, y: 0.05-0.45) - DISABLED
        zone_a_id = create_zone(
            camera_id=1,
            name="Zone A (Disabled)",
            points=[[0.05, 0.05], [0.45, 0.05], [0.45, 0.45], [0.05, 0.45]],
            color="#FF3B30",
            enabled=False
        )

        # Create Zone B (Right side: x: 0.55-0.95, y: 0.55-0.95) - ENABLED
        zone_b_id = create_zone(
            camera_id=1,
            name="Zone B (Enabled)",
            points=[[0.55, 0.55], [0.95, 0.55], [0.95, 0.95], [0.55, 0.95]],
            color="#10B981",
            enabled=True
        )

        detector = CameraMotionDetector(camera_id=1, camera_name="Test Shop Camera")

        # 1. Warm up & calibrate detector with static frames (640x480)
        base_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        base_frame[:] = (50, 50, 50)
        for _ in range(15):
            detector.process_frame(base_frame, mode="ARMED")

        # Get initial event count
        initial_events = get_filtered_events(camera_id=1)
        initial_count = initial_events.get("total", 0)

        # 2. Simulate significant movement inside Zone A (Disabled)
        zone_a_motion_frame = base_frame.copy()
        cv2.rectangle(zone_a_motion_frame, (60, 60), (240, 200), (255, 255, 255), -1)

        for _ in range(5):
            detector.process_frame(zone_a_motion_frame, mode="ARMED")

        events_after_a = get_filtered_events(camera_id=1)
        count_after_a = events_after_a.get("total", 0)

        # CONFIRM: No alerts were generated from motion in disabled Zone A
        self.assertEqual(count_after_a, initial_count, "Disabled zone must NOT generate security alerts!")

        # 3. Simulate movement inside Zone B (Enabled)
        # Reset background baseline
        for _ in range(15):
            detector.process_frame(base_frame, mode="ARMED")

        zone_b_motion_frame = base_frame.copy()
        cv2.rectangle(zone_b_motion_frame, (400, 300), (580, 440), (255, 255, 255), -1)

        for _ in range(6):
            detector.process_frame(zone_b_motion_frame, mode="ARMED")

        events_after_b = get_filtered_events(camera_id=1)
        count_after_b = events_after_b.get("total", 0)

        # CONFIRM: Alert WAS generated from motion in enabled Zone B
        self.assertGreater(count_after_b, initial_count, "Enabled zone MUST detect motion and generate alert!")


if __name__ == "__main__":
    unittest.main()
