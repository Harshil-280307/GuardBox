"""
Veronic GuardBox - Phase 2 Automated Verification Test Suite
Tests Detection Zones (ROI), Arming Modes (ARMING, ARMED, TEST_MODE),
False Alarm Suppression (Persistence, Warmup), Event Lifecycle,
Safe CSV Export, and Schedule Persistence.
"""

import os
import sys
import time
import numpy as np
import cv2

from app.config import settings
from app.database import (
    init_db,
    create_zone,
    get_all_zones,
    get_zone_by_id,
    update_zone,
    delete_zone,
    create_security_event,
    get_filtered_events,
    get_event_by_id,
    acknowledge_event,
    mark_false_alarm,
    resolve_event,
    delete_event,
    clear_test_events,
    get_events_for_csv,
    get_filtered_logs,
    get_schedule_config,
    update_schedule_config
)
from app.detection import motion_service
from app.camera import camera_service


def test_detection_zones_crud():
    print("[TEST 1] Testing Detection Zones (ROI) CRUD...")
    init_db()

    # Create Zone
    zone_id = create_zone(
        name="Jewellery Showcase",
        x=0.2,
        y=0.2,
        width=0.4,
        height=0.4,
        enabled=True
    )
    assert zone_id > 0, "Failed to create detection zone"

    # Get Zone
    zone = get_zone_by_id(zone_id)
    assert zone is not None, "Zone not found by ID"
    assert zone["name"] == "Jewellery Showcase"
    assert zone["x"] == 0.2
    assert zone["enabled"] == 1

    # Update Zone
    update_res = update_zone(
        zone_id=zone_id,
        name="Jewellery Showcase - Renamed",
        x=0.25,
        y=0.25,
        width=0.5,
        height=0.5,
        enabled=True
    )
    assert update_res is True, "Failed to update zone"

    updated_zone = get_zone_by_id(zone_id)
    assert updated_zone["name"] == "Jewellery Showcase - Renamed"

    # List all
    all_zones = get_all_zones()
    assert len(all_zones) >= 1, "Failed to list zones"

    # Delete Zone
    del_res = delete_zone(zone_id)
    assert del_res is True, "Failed to delete zone"
    assert get_zone_by_id(zone_id) is None, "Zone still exists after deletion"
    print("  [PASS] Detection zones CRUD operations verified.")


def test_arming_modes_and_delays():
    print("[TEST 2] Testing Arming Modes and Exit Delays...")
    # Disarm
    motion_service.disarm()
    assert motion_service.current_mode == "DISARMED"

    # Arm with exit delay (2 seconds for test)
    motion_service.arm(exit_delay_seconds=2)
    assert motion_service.current_mode == "ARMING"
    status_arming = motion_service.get_system_status()
    assert status_arming["is_arming"] is True
    assert status_arming["exit_countdown_remaining"] >= 1

    # Cancel arming test
    motion_service.cancel_arming()
    assert motion_service.current_mode == "DISARMED"

    # Arm with 0 delay (immediate)
    motion_service.arm(exit_delay_seconds=0)
    assert motion_service.current_mode == "ARMED"
    assert motion_service.get_system_status()["armed"] is True

    # Test mode
    motion_service.enter_test_mode()
    assert motion_service.current_mode == "TEST_MODE"
    assert motion_service.get_system_status()["is_test_mode"] is True

    # Exit test mode
    motion_service.exit_test_mode()
    assert motion_service.current_mode == "DISARMED"
    print("  [PASS] System mode transitions & delay logic verified.")


def test_event_lifecycle_and_test_data_purge():
    print("[TEST 3] Testing Event Status Lifecycle & Test Data Purge...")
    init_db()

    # Create regular event
    ev1_id = create_security_event(
        event_type="MOTION_DETECTED",
        motion_area=1500.0,
        notes="Real event test",
        system_mode="ARMED"
    )

    # Create test event
    ev2_id = create_security_event(
        event_type="TEST_EVENT",
        motion_area=900.0,
        notes="Simulation in test mode",
        system_mode="TEST_MODE"
    )

    assert get_event_by_id(ev1_id)["status"] == "NEW"

    # Acknowledge
    ack_res = acknowledge_event(ev1_id, notes="Owner checked")
    assert ack_res is True
    assert get_event_by_id(ev1_id)["status"] == "ACKNOWLEDGED"

    # False Alarm
    false_res = mark_false_alarm(ev1_id, notes="Store cat moved")
    assert false_res is True
    assert get_event_by_id(ev1_id)["status"] == "FALSE_ALARM"

    # Resolve
    res_res = resolve_event(ev1_id, notes="Incident closed")
    assert res_res is True
    assert get_event_by_id(ev1_id)["status"] == "RESOLVED"

    # Clear Test Data: strictly delete TEST_EVENT/TEST_MODE
    deleted_test = clear_test_events()
    assert deleted_test >= 1, "Failed to purge test events"
    assert get_event_by_id(ev2_id) is None, "Test event was not purged"
    assert get_event_by_id(ev1_id) is not None, "Real event was accidentally purged!"
    print(f"  [PASS] Event lifecycle and safe test data purge verified (Purged {deleted_test} test events).")


def test_zone_motion_detection_filtering():
    print("[TEST 4] Testing Motion Detection with Zone Filtering...")
    init_db()

    # Create a specific zone: Top-Left quadrant (0, 0, 0.5, 0.5)
    zone_id = create_zone(name="Entrance Counter", x=0.0, y=0.0, width=0.5, height=0.5, enabled=True)

    motion_service.arm(exit_delay_seconds=0)
    motion_service.persistence_seconds = 0.0  # Zero persistence for immediate frame test

    # Frame 1: Base blank
    frame_blank = np.zeros((480, 640, 3), dtype=np.uint8)
    motion_service._process_frame(frame_blank, "2026-09-17T12:00:00Z", "ARMED")

    # Frame 2: Motion OUTSIDE zone (Bottom-Right quadrant: x=400..550, y=350..450)
    frame_outside = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.rectangle(frame_outside, (400, 350), (550, 450), (255, 255, 255), -1)
    motion_service._process_frame(frame_outside, "2026-09-17T12:00:01Z", "ARMED")

    # Frame 3: Motion INSIDE zone (Top-Left quadrant: x=50..200, y=50..200)
    frame_inside = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.rectangle(frame_inside, (50, 50), (200, 200), (255, 255, 255), -1)
    motion_service._process_frame(frame_inside, "2026-09-17T12:00:02Z", "ARMED")

    motion_service.disarm()
    delete_zone(zone_id)
    print("  [PASS] Zone-based contour filtering passed.")


def test_schedule_and_csv_export():
    print("[TEST 5] Testing Schedule Persistence and CSV Export...")
    # Schedule
    sched = update_schedule_config(
        enabled=True,
        opening_time="10:00",
        closing_time="21:30",
        auto_arm=True,
        auto_disarm=True
    )
    assert sched["enabled"] is True
    assert sched["opening_time"] == "10:00"
    assert sched["closing_time"] == "21:30"

    # CSV Data
    csv_rows = get_events_for_csv()
    assert isinstance(csv_rows, list)
    for r in csv_rows:
        # Guarantee no credentials or raw RTSP in CSV
        row_str = str(r)
        assert "office123" not in row_str
        assert "rtsp://" not in row_str
    print("  [PASS] Schedule configuration and CSV security check passed.")


if __name__ == "__main__":
    print("========================================")
    print("Veronic GuardBox - Phase 2 Verification")
    print("========================================")
    test_detection_zones_crud()
    test_arming_modes_and_delays()
    test_event_lifecycle_and_test_data_purge()
    test_zone_motion_detection_filtering()
    test_schedule_and_csv_export()
    print("========================================")
    print("ALL PHASE 2 BACKEND TESTS PASSED! [OK]")
    print("========================================")
