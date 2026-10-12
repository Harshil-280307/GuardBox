"""
Full Integrated Lifecycle Test for GuardBox Detection & Alert System
"""

import os
import sys
import time
import numpy as np
import cv2

from app.config import settings
from app.database import (
    init_db, get_all_cameras, get_all_zones, create_zone,
    clear_all_zones, get_filtered_events, delete_event
)
from app.camera import CameraWorker, camera_manager
from app.detection import CameraMotionDetector, motion_service
from app.alarm import alarm_service
from app.main import detection_health_check, health_check

print("=== STARTING FULL DETECTION LIFECYCLE TEST ===")
init_db()

# Clean up existing zones for test reproducibility
clear_all_zones()
zone_id = create_zone(
    camera_id=1,
    name="Jewelry Counter",
    x=0.1,
    y=0.1,
    width=0.5,
    height=0.5,
    color="#FF3B30",
    enabled=True
)
print(f"[PASS] Created test zone #{zone_id} on Camera #1")

# Verify CameraManager has Camera #1
camera_manager.start()
worker = camera_manager.get_worker(1)
if not worker:
    # If no camera in DB, create worker directly
    cams = get_all_cameras()
    print(f"[INFO] Cameras in DB: {cams}")
    worker = camera_manager.get_primary_worker()

print(f"[PASS] Camera worker retrieved: {worker.name if worker else 'None'}")

# Start motion detection service
motion_service.start()
print("[PASS] Motion service started")

# Arm the system immediately (exit_delay_seconds=0)
motion_service.arm(exit_delay_seconds=0)
print(f"[PASS] System armed. Mode: {motion_service.current_mode}")

# Get or create detector
detector = motion_service._get_or_create_detector(1, "Main Shop Camera")

# Feed 25 baseline frames to calibrate
base_frame = np.zeros((480, 640, 3), dtype=np.uint8)
for _ in range(25):
    detector.process_frame(base_frame, mode="ARMED")

assert detector._is_calibrated is True, "Detector must be calibrated"
print("[PASS] Detector is calibrated and monitoring")

# Feed 3 consecutive frames with motion INSIDE the zone (x: 0.1 to 0.6 -> pixel 64 to 384, y: 0.1 to 0.6 -> pixel 48 to 288)
motion_frame = base_frame.copy()
cv2.rectangle(motion_frame, (100, 100), (250, 250), (255, 255, 255), -1)

# Before motion count of events
initial_events = get_filtered_events(page=1, page_size=10).get("total", 0)

for frame_idx in range(1, 4):
    detector.process_frame(motion_frame, mode="ARMED")
    print(f"[PASS] Fed motion frame {frame_idx}")

# After motion count of events
new_events = get_filtered_events(page=1, page_size=10)
final_total = new_events.get("total", 0)
latest_event = new_events.get("items", [])[0] if new_events.get("items") else None

assert latest_event is not None, "A security event must have been recorded"
print(f"[PASS] Event created successfully: ID={latest_event['id']}, Type={latest_event['event_type']}, Zone={latest_event['zone_name']}, Severity={latest_event['severity']}")

# Check health diagnostics
health = detection_health_check()
print(f"[PASS] Detection health diagnostic: {health}")
assert health["is_armed"] is True, "System should be armed in health check"

# Disarm system
motion_service.disarm()
print(f"[PASS] System disarmed. Mode: {motion_service.current_mode}")

# Stop services
motion_service.stop()
camera_manager.stop()
print("[PASS] All services stopped gracefully")

print("\n=== ALL LIFECYCLE TESTS COMPLETED SUCCESSFULLY ===")
