"""
Veronic GuardBox - Backend Verification Test Suite
Tests configuration, database operations, motion detection logic, and alarm simulation.
"""

import os
import sys
import numpy as np
import cv2

from app.config import settings
from app.database import (
    init_db,
    create_security_event,
    get_recent_events,
    get_event_by_id,
    acknowledge_event,
    log_system_event
)
from app.alarm import alarm_service
from app.notifications import notification_service
from app.detection import motion_service
from app.camera import camera_service


def test_configuration():
    print("[TEST 1] Testing Configuration & Privacy Masking...")
    safe_ip = settings.get_safe_camera_ip()
    sanitized_url = settings.get_sanitized_rtsp_url()
    
    assert "office123" not in safe_ip, "Password leaked in safe IP!"
    assert "office123" not in sanitized_url, "Password leaked in sanitized URL!"
    assert safe_ip == "192.168.31.108", f"Unexpected IP: {safe_ip}"
    assert "192.168.31.108" in sanitized_url, f"IP missing in sanitized URL: {sanitized_url}"
    print(f"  [PASS] Safe IP: {safe_ip}")
    print(f"  [PASS] Sanitized URL: {sanitized_url}")


def test_database():
    print("[TEST 2] Testing Database Tables & Operations...")
    init_db()
    
    # Create test event
    event_id = create_security_event(
        event_type="TEST_MOTION",
        motion_area=1250.5,
        snapshot_path="snapshots/test.jpg",
        notes="Automated test event"
    )
    assert event_id > 0, "Failed to create security event"
    
    # Retrieve event
    event = get_event_by_id(event_id)
    assert event is not None, f"Event {event_id} not found"
    assert event["event_type"] == "TEST_MOTION"
    assert event["motion_area"] == 1250.5
    assert event["acknowledged"] == 0
    
    # Acknowledge event
    ack_res = acknowledge_event(event_id, notes="Verified during test")
    assert ack_res is True, "Failed to acknowledge event"
    
    event_updated = get_event_by_id(event_id)
    assert event_updated["acknowledged"] == 1
    assert event_updated["notes"] == "Verified during test"
    
    # List recent events
    recent = get_recent_events(limit=5)
    assert len(recent) > 0, "No events returned in get_recent_events"
    print(f"  [PASS] Database operations successful. Verified event #{event_id}")


def test_alarm_service():
    print("[TEST 3] Testing Alarm Simulation Service...")
    alarm_service.stop_alarm()
    status_idle = alarm_service.get_status()
    assert status_idle["is_active"] is False
    assert "SIMULATED" in status_idle["disclaimer"]
    
    # Trigger simulation
    trig_status = alarm_service.trigger_simulated_alarm("Test motion")
    assert trig_status["is_active"] is True
    assert "SIMULATED" in trig_status["disclaimer"]
    
    # Reset
    stop_status = alarm_service.stop_alarm()
    assert stop_status["is_active"] is False
    print("  [PASS] Alarm simulation state transitions verified.")


def test_notifications():
    print("[TEST 4] Testing Notifications Abstraction...")
    notif = notification_service.notify_security_event(
        event_id=999,
        event_type="TEST_EVENT",
        motion_area=800.0,
        timestamp="2026-09-17T12:00:00Z"
    )
    assert notif["status"] == "simulated"
    assert "SIMULATED" in notif["message"] or "Phase 1" in notif["disclaimer"]
    print("  [PASS] Notification abstraction verified.")


def test_motion_detector():
    print("[TEST 5] Testing OpenCV Motion Detection Pipeline...")
    motion_service.arm()
    assert motion_service.is_armed is True
    
    # Synthetic blank frame
    frame1 = np.zeros((480, 640, 3), dtype=np.uint8)
    motion_service._process_frame(frame1, "2026-09-17T12:00:00Z")
    
    # Synthetic frame with a moving rectangle
    frame2 = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.rectangle(frame2, (200, 200), (350, 350), (255, 255, 255), -1)
    
    # Process moving frame
    motion_service._process_frame(frame2, "2026-09-17T12:00:01Z")
    
    motion_service.disarm()
    assert motion_service.is_armed is False
    print("  [PASS] Motion detection frame processing passed.")


if __name__ == "__main__":
    print("========================================")
    print("Veronic GuardBox - Backend Verification")
    print("========================================")
    test_configuration()
    test_database()
    test_alarm_service()
    test_notifications()
    test_motion_detector()
    print("========================================")
    print("ALL BACKEND TESTS PASSED SUCCESSFULLY! [OK]")
    print("========================================")
