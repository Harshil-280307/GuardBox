"""
GuardBox - Phase 1 Custom Polygon Detection Zone Verification Test Suite
Tests all 11 required scenarios for polygon detection zones, coordinate normalization,
CRUD, multi-zone evaluation, point-in-polygon motion detection, and backwards compatibility.
"""

import unittest
import unittest.mock
import numpy as np
import cv2
import json
import os
import time

from app.database import (
    init_db,
    create_camera,
    get_all_cameras,
    create_zone,
    get_zone_by_id,
    get_zones_by_camera,
    update_zone,
    delete_zone,
    toggle_zone,
    clear_zones_by_camera,
    get_all_zones
)
from app.detection import CameraMotionDetector
from app.camera import camera_manager


class TestPolygonDetectionZones(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.test_cam_id = 999
        # Ensure test camera exists
        with unittest.mock.patch("app.database.log_system_event"):
            pass

    def setUp(self):
        clear_zones_by_camera(self.test_cam_id)

    def tearDown(self):
        clear_zones_by_camera(self.test_cam_id)

    # -------------------------------------------------------------------------
    # TEST 1: Create 3-point polygon (Triangle)
    # -------------------------------------------------------------------------
    def test_01_create_3_point_polygon(self):
        """TEST 1: Create 3-point polygon."""
        points = [[0.2, 0.2], [0.8, 0.2], [0.5, 0.8]]
        zone_id = create_zone(
            camera_id=self.test_cam_id,
            name="Triangle Zone",
            points=points
        )
        self.assertIsNotNone(zone_id)
        zone = get_zone_by_id(zone_id)
        self.assertEqual(zone["name"], "Triangle Zone")
        self.assertEqual(len(zone["points"]), 3)
        self.assertEqual(zone["points"], points)
        self.assertTrue(zone["enabled"])

    # -------------------------------------------------------------------------
    # TEST 2: Create irregular polygon (e.g. L-shaped / 6-point)
    # -------------------------------------------------------------------------
    def test_02_create_irregular_polygon(self):
        """TEST 2: Create irregular polygon."""
        points = [
            [0.1, 0.1],
            [0.5, 0.1],
            [0.5, 0.4],
            [0.9, 0.4],
            [0.9, 0.9],
            [0.1, 0.9]
        ]
        zone_id = create_zone(
            camera_id=self.test_cam_id,
            name="L-Shaped Counter",
            points=points
        )
        zone = get_zone_by_id(zone_id)
        self.assertEqual(len(zone["points"]), 6)
        self.assertEqual(zone["points"], points)
        # Bounding box should encompass the full extent
        self.assertAlmostEqual(zone["x"], 0.1, places=2)
        self.assertAlmostEqual(zone["y"], 0.1, places=2)
        self.assertAlmostEqual(zone["width"], 0.8, places=2)
        self.assertAlmostEqual(zone["height"], 0.8, places=2)

    # -------------------------------------------------------------------------
    # TEST 3: Save and reload polygon
    # -------------------------------------------------------------------------
    def test_03_save_and_reload_polygon(self):
        """TEST 3: Save and reload polygon from database."""
        points = [[0.18, 0.32], [0.72, 0.25], [0.85, 0.68], [0.32, 0.82]]
        zone_id = create_zone(
            camera_id=self.test_cam_id,
            name="Jewellery Display",
            points=points
        )
        # Reload fresh from database
        reloaded = get_zone_by_id(zone_id)
        self.assertIsNotNone(reloaded)
        self.assertEqual(reloaded["id"], zone_id)
        self.assertEqual(reloaded["name"], "Jewellery Display")
        self.assertEqual(reloaded["points"], points)

        # Update vertices
        new_points = [[0.20, 0.35], [0.75, 0.30], [0.88, 0.70], [0.35, 0.85]]
        updated = update_zone(zone_id, name="Jewellery Display Premium", points=new_points)
        self.assertTrue(updated)

        reloaded_updated = get_zone_by_id(zone_id)
        self.assertEqual(reloaded_updated["name"], "Jewellery Display Premium")
        self.assertEqual(reloaded_updated["points"], new_points)

    # -------------------------------------------------------------------------
    # TEST 4: Resize camera preview (Coordinate Normalization)
    # -------------------------------------------------------------------------
    def test_04_resize_camera_preview_coordinates(self):
        """TEST 4: Verify polygon points scale correctly across 1920x1080, 1280x720, 640x480."""
        norm_points = [[0.25, 0.25], [0.75, 0.25], [0.75, 0.75], [0.25, 0.75]]

        resolutions = [(1920, 1080), (1280, 720), (640, 480)]
        for w, h in resolutions:
            # Transform normalized points to pixel coordinates
            pixel_pts = np.array([[int(p[0] * w), int(p[1] * h)] for p in norm_points], dtype=np.int32)
            # Create mask
            mask = np.zeros((h, w), dtype=np.uint8)
            cv2.fillPoly(mask, [pixel_pts], 255)

            # Center point (0.5, 0.5) should ALWAYS be inside the mask
            cx, cy = int(0.5 * w), int(0.5 * h)
            self.assertEqual(mask[cy, cx], 255, f"Center point failed at {w}x{h}")

            # Top-left outer point (0.1, 0.1) should ALWAYS be outside the mask
            ox, oy = int(0.1 * w), int(0.1 * h)
            self.assertEqual(mask[oy, ox], 0, f"Outer point failed at {w}x{h}")

    # -------------------------------------------------------------------------
    # TEST 5: Enable / disable zone
    # -------------------------------------------------------------------------
    def test_05_enable_disable_zone(self):
        """TEST 5: Enable/disable zone."""
        points = [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]
        zone_id = create_zone(camera_id=self.test_cam_id, name="Toggle Zone", points=points, enabled=True)

        zone = get_zone_by_id(zone_id)
        self.assertTrue(zone["enabled"])

        # Disable
        toggle_zone(zone_id, False)
        zone_disabled = get_zone_by_id(zone_id)
        self.assertFalse(zone_disabled["enabled"])

        # Enable
        toggle_zone(zone_id, True)
        zone_enabled = get_zone_by_id(zone_id)
        self.assertTrue(zone_enabled["enabled"])

    # -------------------------------------------------------------------------
    # TEST 6: Delete zone
    # -------------------------------------------------------------------------
    def test_06_delete_zone(self):
        """TEST 6: Delete zone."""
        points = [[0.1, 0.1], [0.5, 0.1], [0.5, 0.5], [0.1, 0.5]]
        zone_id = create_zone(camera_id=self.test_cam_id, name="To Delete", points=points)

        self.assertIsNotNone(get_zone_by_id(zone_id))
        deleted = delete_zone(zone_id)
        self.assertTrue(deleted)
        self.assertIsNone(get_zone_by_id(zone_id))

    # -------------------------------------------------------------------------
    # TEST 7: Detection point INSIDE polygon -> detection accepted
    # -------------------------------------------------------------------------
    def test_07_detection_point_inside_polygon(self):
        """TEST 7: Detection point inside polygon -> motion accepted."""
        detector = CameraMotionDetector(camera_id=self.test_cam_id, camera_name="Test Polygon Cam")

        # Create diamond polygon zone in center [ (0.5, 0.2), (0.8, 0.5), (0.5, 0.8), (0.2, 0.5) ]
        points = [[0.5, 0.2], [0.8, 0.5], [0.5, 0.8], [0.2, 0.5]]
        zone_id = create_zone(camera_id=self.test_cam_id, name="Diamond Safe Zone", points=points, enabled=True)

        w, h = 640, 480
        # 1. Feed 25 baseline frames
        base_frame = np.zeros((h, w, 3), dtype=np.uint8)
        base_frame[:] = (50, 50, 50)
        for _ in range(25):
            detector.process_frame(base_frame, mode="ARMED")

        # 2. Inject movement strictly INSIDE diamond zone (center: 320, 240)
        events_recorded = []
        detector._record_motion_event = lambda **kwargs: events_recorded.append(kwargs)

        for _ in range(5):
            motion_frame = base_frame.copy()
            cv2.rectangle(motion_frame, (300, 220), (340, 260), (255, 255, 255), -1)
            detector.process_frame(motion_frame, mode="ARMED")

        self.assertTrue(len(events_recorded) >= 1, "Motion inside polygon zone was not accepted!")
        self.assertEqual(events_recorded[0]["matched_zone"]["name"], "Diamond Safe Zone")

    # -------------------------------------------------------------------------
    # TEST 8: Detection point OUTSIDE polygon -> zone does not trigger
    # -------------------------------------------------------------------------
    def test_08_detection_point_outside_polygon(self):
        """TEST 8: Detection point outside polygon -> zone does NOT trigger."""
        detector = CameraMotionDetector(camera_id=self.test_cam_id, camera_name="Test Polygon Cam")

        # Create polygon zone in top-left: [ (0.05, 0.05), (0.35, 0.05), (0.35, 0.35), (0.05, 0.35) ]
        points = [[0.05, 0.05], [0.35, 0.05], [0.35, 0.35], [0.05, 0.35]]
        create_zone(camera_id=self.test_cam_id, name="Top Left Zone", points=points, enabled=True)

        w, h = 640, 480
        # 1. Feed baseline calibration
        base_frame = np.zeros((h, w, 3), dtype=np.uint8)
        base_frame[:] = (50, 50, 50)
        for _ in range(25):
            detector.process_frame(base_frame, mode="ARMED")

        # 2. Inject movement completely in bottom-right (outside zone)
        events_recorded = []
        detector._record_motion_event = lambda **kwargs: events_recorded.append(kwargs)

        for _ in range(10):
            motion_frame = base_frame.copy()
            cv2.rectangle(motion_frame, (500, 380), (580, 440), (255, 255, 255), -1)
            detector.process_frame(motion_frame, mode="ARMED")

        self.assertEqual(len(events_recorded), 0, "Motion outside polygon zone triggered false alarm!")

    # -------------------------------------------------------------------------
    # TEST 9: Multiple zones on one camera
    # -------------------------------------------------------------------------
    def test_09_multiple_zones_on_one_camera(self):
        """TEST 9: Multiple custom polygon zones configured on single camera."""
        zone1_pts = [[0.05, 0.05], [0.45, 0.05], [0.45, 0.45], [0.05, 0.45]]
        zone2_pts = [[0.55, 0.05], [0.95, 0.05], [0.95, 0.45], [0.55, 0.45]]
        zone3_pts = [[0.20, 0.55], [0.80, 0.55], [0.80, 0.95], [0.20, 0.95]]

        z1 = create_zone(camera_id=self.test_cam_id, name="Main Entrance", points=zone1_pts)
        z2 = create_zone(camera_id=self.test_cam_id, name="Jewellery Display", points=zone2_pts)
        z3 = create_zone(camera_id=self.test_cam_id, name="Cash Counter", points=zone3_pts)

        zones = get_zones_by_camera(self.test_cam_id)
        self.assertEqual(len(zones), 3)
        names = [z["name"] for z in zones]
        self.assertIn("Main Entrance", names)
        self.assertIn("Jewellery Display", names)
        self.assertIn("Cash Counter", names)

    # -------------------------------------------------------------------------
    # TEST 10: Camera with no configured zones -> fallback full-frame monitoring
    # -------------------------------------------------------------------------
    def test_10_camera_no_zones_fallback(self):
        """TEST 10: Camera with NO configured zones preserves existing full-frame detection."""
        clear_zones_by_camera(self.test_cam_id)
        self.assertEqual(len(get_zones_by_camera(self.test_cam_id)), 0)

        detector = CameraMotionDetector(camera_id=self.test_cam_id, camera_name="No Zones Cam")
        w, h = 640, 480
        base_frame = np.zeros((h, w, 3), dtype=np.uint8)
        base_frame[:] = (50, 50, 50)
        for _ in range(25):
            detector.process_frame(base_frame, mode="ARMED")

        events_recorded = []
        detector._record_motion_event = lambda **kwargs: events_recorded.append(kwargs)

        for _ in range(5):
            motion_frame = base_frame.copy()
            cv2.rectangle(motion_frame, (200, 200), (350, 350), (255, 255, 255), -1)
            detector.process_frame(motion_frame, mode="ARMED")

        self.assertTrue(len(events_recorded) >= 1, "Full frame motion detection failed when 0 zones exist!")
        self.assertIsNone(events_recorded[0]["matched_zone"], "Matched zone should be None for full frame!")

    # -------------------------------------------------------------------------
    # TEST 11: Existing rectangular zone configuration continues working
    # -------------------------------------------------------------------------
    def test_11_rectangular_zone_backwards_compatibility(self):
        """TEST 11: Existing rectangular zones (x, y, width, height) continue working seamlessly."""
        # Create zone using rectangular parameters without points
        zone_id = create_zone(
            camera_id=self.test_cam_id,
            name="Legacy Rect Zone",
            x=0.2,
            y=0.3,
            width=0.4,
            height=0.5
        )
        zone = get_zone_by_id(zone_id)
        self.assertIsNotNone(zone)
        self.assertEqual(zone["name"], "Legacy Rect Zone")
        self.assertAlmostEqual(zone["x"], 0.2, places=2)
        self.assertAlmostEqual(zone["y"], 0.3, places=2)
        self.assertAlmostEqual(zone["width"], 0.4, places=2)
        self.assertAlmostEqual(zone["height"], 0.5, places=2)
        # points should be auto-populated as 4-corner polygon
        self.assertEqual(len(zone["points"]), 4)

    # -------------------------------------------------------------------------
    # TEST 12: API Validation & Endpoints (REST API)
    # -------------------------------------------------------------------------
    def test_12_api_polygon_endpoints_and_validation(self):
        """TEST 12: Test FastAPI endpoints for creating, updating, and validating polygon zones."""
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)

        # 1. Create polygon via API
        resp = client.post(f"/cameras/{self.test_cam_id}/zones", json={
            "camera_id": self.test_cam_id,
            "name": "API Polygon Zone",
            "points": [[0.1, 0.1], [0.8, 0.1], [0.8, 0.8], [0.1, 0.8]]
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["name"], "API Polygon Zone")
        self.assertEqual(len(data["points"]), 4)
        zone_id = data["id"]

        # 2. Reject polygon with < 3 points
        resp_invalid_points = client.post(f"/cameras/{self.test_cam_id}/zones", json={
            "camera_id": self.test_cam_id,
            "name": "Invalid Polygon",
            "points": [[0.1, 0.1], [0.8, 0.1]]
        })
        self.assertEqual(resp_invalid_points.status_code, 422)

        # 3. Reject empty name
        resp_empty_name = client.post(f"/cameras/{self.test_cam_id}/zones", json={
            "camera_id": self.test_cam_id,
            "name": "   ",
            "points": [[0.1, 0.1], [0.8, 0.1], [0.5, 0.8]]
        })
        self.assertEqual(resp_empty_name.status_code, 422)

        # 4. Reject out of bounds coordinates
        resp_oob = client.post(f"/cameras/{self.test_cam_id}/zones", json={
            "camera_id": self.test_cam_id,
            "name": "OOB Polygon",
            "points": [[-0.5, 0.1], [1.8, 0.1], [0.5, 0.8]]
        })
        self.assertEqual(resp_oob.status_code, 422)

        # 5. Update polygon vertices via API
        resp_update = client.put(f"/zones/{zone_id}", json={
            "name": "API Polygon Zone Updated",
            "points": [[0.15, 0.15], [0.85, 0.15], [0.85, 0.85], [0.15, 0.85]]
        })
        self.assertEqual(resp_update.status_code, 200)
        updated_data = resp_update.json()
        self.assertEqual(updated_data["name"], "API Polygon Zone Updated")
        self.assertEqual(updated_data["points"][0], [0.15, 0.15])

        # 6. Toggle zone via API
        resp_toggle = client.post(f"/zones/{zone_id}/toggle?enabled=false")
        self.assertEqual(resp_toggle.status_code, 200)

        # 7. Delete zone via API
        resp_del = client.delete(f"/zones/{zone_id}")
        self.assertEqual(resp_del.status_code, 200)


if __name__ == "__main__":
    unittest.main()

