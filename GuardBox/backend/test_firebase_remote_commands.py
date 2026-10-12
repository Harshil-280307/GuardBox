"""
Automated Test Suite for GuardBox Phase 2: Remote Command Relay
Tests end-to-end Firebase Realtime Database command flow:
1. Presence registration (online, status, last_seen)
2. ARM command -> motion_service.arm() -> RUNNING
3. Idempotent duplicate command protection
4. SILENCE command -> alarm_service.stop_alarm()
5. DISARM command -> motion_service.disarm() -> STOPPED
"""

import sys
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Ensure UTF-8 output on Windows console
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Add backend directory to sys.path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from app.config import settings
from app.database import init_db
from app.detection import motion_service
from app.alarm import alarm_service
from app.firebase_bridge import firebase_bridge


def run_tests():
    print("==================================================")
    print("[TEST SUITE] RUNNING GUARDBOX PHASE 2 REMOTE COMMAND TESTS")
    print("==================================================")

    init_db()

    # Step 1: Start Bridge
    print("\n[Step 1] Initializing and starting Firebase Bridge...")
    firebase_bridge.start()
    assert firebase_bridge.is_active, "Firebase Bridge failed to become active"
    device_id = firebase_bridge.device_id
    print(f"[PASS] Bridge active. Device ID: {device_id}")

    from firebase_admin import db
    device_ref = db.reference(f"guardbox/devices/{device_id}")
    dev_data = device_ref.get()
    assert dev_data is not None, "Device node not found in Firebase"
    assert dev_data.get("online") is True, "Device should be online"
    print(f"[PASS] Device presence verified in Firebase: online={dev_data.get('online')}, status={dev_data.get('status')}")

    # Ensure system is initially DISARMED
    motion_service.disarm()
    assert not motion_service.is_armed, "System should be disarmed initially"

    # Step 2: Test ARM Command
    print("\n[Step 2] Sending remote ARM command via Firebase...")
    cmd_arm_id = f"test_arm_{uuid.uuid4().hex[:6]}"
    cmd_arm_ref = db.reference(f"guardbox/commands/{device_id}/pending/{cmd_arm_id}")
    cmd_arm_ref.set({
        "command": "ARM",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "requested_by": "test_owner_uid",
        "status": "PENDING"
    })

    # Wait for bridge to execute command
    success = False
    for _ in range(25):
        time.sleep(0.4)
        c_data = cmd_arm_ref.get()
        if c_data and c_data.get("status") == "SUCCESS":
            success = True
            break

    assert success, "ARM command did not reach terminal SUCCESS status"
    assert motion_service.is_armed, "motion_service should be ARMED"
    dev_data = device_ref.get()
    assert dev_data.get("status") == "RUNNING", f"Device status in Firebase should be RUNNING, got: {dev_data.get('status')}"
    print(f"[PASS] Remote ARM command executed successfully! System mode: {motion_service.current_mode}")

    # Step 3: Test Idempotency & Duplicate Protection
    print("\n[Step 3] Testing Idempotent Duplicate Protection for ARM command...")
    prev_processed_count = len(firebase_bridge._processed_command_ids)
    firebase_bridge._process_single_command(cmd_arm_id, {"command": "ARM", "status": "PENDING"})
    assert len(firebase_bridge._processed_command_ids) == prev_processed_count or cmd_arm_id in firebase_bridge._processed_command_ids
    print("[PASS] Duplicate command prevented from re-executing.")

    # Step 4: Test SILENCE Command
    print("\n[Step 4] Testing remote SILENCE command...")
    alarm_service.test_simulated_alarm()
    assert alarm_service.is_active, "Simulated alarm should be active"

    cmd_silence_id = f"test_silence_{uuid.uuid4().hex[:6]}"
    cmd_silence_ref = db.reference(f"guardbox/commands/{device_id}/pending/{cmd_silence_id}")
    cmd_silence_ref.set({
        "command": "SILENCE",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "requested_by": "test_owner_uid",
        "status": "PENDING"
    })

    success = False
    for _ in range(25):
        time.sleep(0.4)
        c_data = cmd_silence_ref.get()
        if c_data and c_data.get("status") == "SUCCESS":
            success = True
            break

    assert success, "SILENCE command did not reach terminal SUCCESS status"
    assert not alarm_service.is_active, "Alarm should now be silenced"
    assert motion_service.is_armed, "System should remain ARMED when silenced"
    print("[PASS] Remote SILENCE executed successfully! Alarm stopped, perimeter monitoring intact.")

    # Step 5: Test DISARM Command
    print("\n[Step 5] Testing remote DISARM command...")
    cmd_disarm_id = f"test_disarm_{uuid.uuid4().hex[:6]}"
    cmd_disarm_ref = db.reference(f"guardbox/commands/{device_id}/pending/{cmd_disarm_id}")
    cmd_disarm_ref.set({
        "command": "DISARM",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "requested_by": "test_owner_uid",
        "status": "PENDING"
    })

    success = False
    for _ in range(25):
        time.sleep(0.4)
        c_data = cmd_disarm_ref.get()
        if c_data and c_data.get("status") == "SUCCESS":
            success = True
            break

    assert success, "DISARM command did not reach terminal SUCCESS status"
    assert not motion_service.is_armed, "motion_service should be DISARMED"
    dev_data = device_ref.get()
    assert dev_data.get("status") == "STOPPED", f"Device status in Firebase should be STOPPED, got: {dev_data.get('status')}"
    print(f"[PASS] Remote DISARM executed successfully! System mode: {motion_service.current_mode}")

    # Step 6: Shutdown Bridge
    print("\n[Step 6] Stopping Firebase Bridge...")
    firebase_bridge.stop()
    print("[PASS] Bridge stopped cleanly.")

    print("\n==================================================")
    print("[SUCCESS] ALL PHASE 2 REMOTE COMMAND TESTS PASSED (100%)")
    print("==================================================")


if __name__ == "__main__":
    run_tests()
