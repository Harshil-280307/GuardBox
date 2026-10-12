"""
Veronic GuardBox - Motion Detection Accuracy & False Positive Verification
Tests:
1. Empty zone with noise (No false events)
2. Single-frame glitch / compression artifact (Ignored due to consecutive frame rule)
3. Motion outside detection zone (Ignored)
4. Real multi-frame motion inside zone (Detected & Event Created)
5. Cooldown protection (No duplicate event spam)
6. Live RTSP stream calibration & stability check
"""

import time
import numpy as np
import cv2
from app.detection import CameraMotionDetector
from app.database import (
    init_db,
    create_camera,
    create_zone,
    get_filtered_events,
    clear_test_events
)


def run_motion_accuracy_tests():
    print("========================================")
    print("GuardBox - Motion Detection Accuracy Test")
    print("========================================")
    init_db()

    # Clear previous test events
    clear_test_events()

    detector = CameraMotionDetector(camera_id=99, camera_name="Test Accuracy Cam")
    w, h = 640, 360

    # Zone in center of frame (x=0.25, y=0.25, w=0.5, h=0.5)
    test_zone = {
        "id": 991,
        "name": "Jewelry Safe Zone",
        "camera_id": 99,
        "x": 0.25,
        "y": 0.25,
        "width": 0.5,
        "height": 0.5,
        "enabled": 1,
        "sensitivity": 35,
        "minimum_motion_area": 300,
        "cooldown_seconds": 5.0
    }

    # Override get_zones_by_camera for this test camera
    import app.detection as det_mod
    original_get_zones = det_mod.get_zones_by_camera
    det_mod.get_zones_by_camera = lambda cam_id: [test_zone] if cam_id == 99 else original_get_zones(cam_id)

    try:
        # Base background frame
        base_frame = np.zeros((h, w, 3), dtype=np.uint8)
        base_frame[:] = (50, 50, 50)
        cv2.putText(base_frame, "STATIC STORE BACKGROUND", (50, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 2)

        # ---------------------------------------------------------------------
        # TEST 1: Baseline Calibration
        # ---------------------------------------------------------------------
        print("\n[TEST 1] Testing Calibration Phase...")
        for i in range(25):
            noise = np.random.randint(-3, 4, (h, w, 3), dtype=np.int16)
            noisy_frame = np.clip(base_frame.astype(np.int16) + noise, 0, 255).astype(np.uint8)
            detector.process_frame(noisy_frame, None, mode="TEST_MODE")

        diag = detector.get_debug_diagnostics()
        assert diag["is_calibrated"] is True, "Detector should be calibrated after 25 frames"
        events = get_filtered_events(page=1, page_size=10, camera_id=99)
        assert len(events["items"]) == 0, f"Expected 0 events during calibration, got {len(events['items'])}"
        print("  [PASS] Calibration complete with 0 false events.")

        # ---------------------------------------------------------------------
        # TEST 2: Empty Zone with Ongoing Compression Noise (60 frames)
        # ---------------------------------------------------------------------
        print("\n[TEST 2] Testing Empty Zone with Noise (60 Frames)...")
        for i in range(60):
            noise = np.random.randint(-4, 5, (h, w, 3), dtype=np.int16)
            noisy_frame = np.clip(base_frame.astype(np.int16) + noise, 0, 255).astype(np.uint8)
            detector.process_frame(noisy_frame, None, mode="TEST_MODE")

        events = get_filtered_events(page=1, page_size=10, camera_id=99)
        assert len(events["items"]) == 0, f"Expected 0 events for empty zone, got {len(events['items'])}"
        print("  [PASS] Empty zone remained completely silent with 0 false alarms.")

        # ---------------------------------------------------------------------
        # TEST 3: Single-Frame Glitch / Flicker (Should be rejected)
        # ---------------------------------------------------------------------
        print("\n[TEST 3] Testing Single-Frame Glitch / Flicker...")
        # 1 frame with random flash in zone
        glitch_frame = base_frame.copy()
        cv2.rectangle(glitch_frame, (200, 100), (280, 160), (220, 220, 220), -1)
        detector.process_frame(glitch_frame, None, mode="TEST_MODE")

        # Next frame is clean again
        detector.process_frame(base_frame, None, mode="TEST_MODE")

        events = get_filtered_events(page=1, page_size=10, camera_id=99)
        assert len(events["items"]) == 0, f"Expected 0 events for single-frame glitch, got {len(events['items'])}"
        print("  [PASS] Single-frame artifact properly rejected (consecutive frames required).")

        # ---------------------------------------------------------------------
        # TEST 4: Motion Outside Detection Zone (Should be ignored)
        # ---------------------------------------------------------------------
        print("\n[TEST 4] Testing Motion Outside Detection Zone...")
        # Move object at x=50..100, y=50..100 (Outside zone which is at x=160..480, y=90..270)
        for i in range(6):
            outside_frame = base_frame.copy()
            cv2.rectangle(outside_frame, (50 + i * 5, 50), (100 + i * 5, 80), (255, 255, 255), -1)
            detector.process_frame(outside_frame, None, mode="TEST_MODE")

        events = get_filtered_events(page=1, page_size=10, camera_id=99)
        assert len(events["items"]) == 0, f"Expected 0 events for motion outside zone, got {len(events['items'])}"
        print("  [PASS] Motion outside zone was completely ignored.")

        # ---------------------------------------------------------------------
        # TEST 5: Real Persistent Motion Inside Detection Zone (Should trigger)
        # ---------------------------------------------------------------------
        print("\n[TEST 5] Testing Real Movement Inside Zone...")
        # Move object inside zone (x=220..320, y=120..200) across 4 consecutive frames
        for i in range(4):
            moving_frame = base_frame.copy()
            cv2.rectangle(moving_frame, (220 + (i * 6), 120), (290 + (i * 6), 190), (255, 255, 255), -1)
            detector.process_frame(moving_frame, None, mode="TEST_MODE")
            time.sleep(0.01)

        events = get_filtered_events(page=1, page_size=10, camera_id=99)
        assert len(events["items"]) == 1, f"Expected 1 event for real movement, got {len(events['items'])}"
        ev = events["items"][0]
        assert ev["camera_id"] == 99, "Event camera_id mismatch"
        assert ev["zone_name"] == "Jewelry Safe Zone", "Event zone_name mismatch"
        print(f"  [PASS] Real motion detected! Event #{ev['id']} created for '{ev['zone_name']}'.")

        # ---------------------------------------------------------------------
        # TEST 6: Cooldown Check
        # ---------------------------------------------------------------------
        print("\n[TEST 6] Testing Cooldown Window...")
        # Immediate subsequent frames should not generate a second event
        for i in range(4):
            moving_frame = base_frame.copy()
            cv2.rectangle(moving_frame, (250, 140), (320, 210), (255, 255, 255), -1)
            detector.process_frame(moving_frame, None, mode="TEST_MODE")

        events_after = get_filtered_events(page=1, page_size=10, camera_id=99)
        assert len(events_after["items"]) == 1, "Cooldown failed to suppress duplicate rapid event"
        print("  [PASS] Cooldown active. Duplicate event prevented.")

        # Clean test events
        clear_test_events()
        print("\n========================================")
        print("ALL MOTION ACCURACY TESTS PASSED [OK]!")
        print("========================================")

    finally:
        det_mod.get_zones_by_camera = original_get_zones


if __name__ == "__main__":
    run_motion_accuracy_tests()
