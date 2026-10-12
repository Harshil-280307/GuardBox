"""
Test Live Camera Frame Capture and Detection
"""

import time
import numpy as np
from app.database import init_db, get_all_cameras, get_filtered_events
from app.camera import CameraWorker, camera_manager
from app.detection import CameraMotionDetector, motion_service

print("=== TESTING REAL CAMERA FRAME INGESTION & PIPELINE ===")
init_db()

cams = get_all_cameras()
print(f"Cameras in DB: {len(cams)}")
for c in cams:
    print(f" - ID: {c['id']}, Name: {c['name']}, Brand: {c['brand']}, Model: {c['model']}, Enabled: {c['enabled']}")

camera_manager.start()
worker = camera_manager.get_primary_worker()
assert worker is not None, "Primary camera worker must exist"

print(f"Waiting for camera worker connection (Camera #{worker.camera_id})...")
frames_read = 0
for attempt in range(12):
    time.sleep(0.5)
    connected, frame, ts = worker.get_latest_frame()
    if connected and frame is not None:
        h, w = frame.shape[:2]
        fps = worker._current_fps
        print(f"[CAMERA {worker.camera_id}] Connection State: CONNECTED, Frame Received: YES, Width: {w}, Height: {h}, FPS: {fps:.1f}")
        frames_read += 1
        break
    else:
        print(f"Attempt {attempt+1}/12: Camera connected={worker._connected}, waiting for frame...")

if frames_read == 0:
    print(f"[CAMERA {worker.camera_id}] State: {getattr(worker, '_preview_status', 'UNKNOWN')}, reason: {getattr(worker, '_last_error_reason', 'None')}")

camera_manager.stop()
print("=== CAMERA INGESTION TEST COMPLETE ===")
