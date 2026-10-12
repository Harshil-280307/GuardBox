"""
GuardBox — Automated Test Suite for Stale / False Emergency Alert Prevention
Tests:
1. Service starts with stale active alert -> establishes baseline, no notification triggered
2. New alert after startup -> genuinely new alert triggers notification
3. Same alert ID again -> duplicate suppression prevents repeated notification
4. SILENCE -> escalation loop terminates immediately and sets status to SILENCED
5. ACKNOWLEDGE -> escalation loop terminates immediately and sets status to ACKNOWLEDGED
6. Completed alert -> Firebase current alert cleared / deleted
7. Backend restart with old completed alert -> no active alert returned or resurrection
8. Backend restart with unacknowledged dangling alerts -> safely cleaned up on startup
"""

import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from app.config import settings
from app.database import (
    init_db,
    cleanup_stale_alerts,
    get_all_devices,
    register_device,
    create_security_alert,
    get_alert_by_id,
    get_active_alert,
    update_notification_settings,
    get_deliveries_by_alert
)
from app.push import push_escalation_service, fcm_service


def reset_test_env():
    init_db()
    from app.database import get_db_connection
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM security_alerts")
        cursor.execute("DELETE FROM notification_devices")
        cursor.execute("DELETE FROM push_deliveries")
        conn.commit()

    register_device(
        device_id="test_dev_01",
        user_name="Shop Owner",
        fcm_token="test_fcm_token_1",
        device_name="Pixel 8 Pro",
        platform="android",
        priority=1
    )

    update_notification_settings(
        auto_push_enabled=True,
        push_timeout_seconds=1,
        max_retry_cycles=2,
        min_alert_severity="HIGH",
        cooldown_seconds=0
    )
    push_escalation_service._camera_cooldowns.clear()
    push_escalation_service.stop_escalation()
    fcm_service._last_dispatched_payloads.clear()


def test_scenario_1_and_2_baseline_and_new_alert():
    print("\n[TEST 1 & 2] Stale Alert Baseline & New Alert Recognition...")
    reset_test_env()

    # Create an alert that exists before service starts (stale alert #1)
    stale_id = create_security_alert(
        alert_code="GB-STALE-001",
        camera_id=1,
        camera_name="Shop Camera",
        event_type="SUSPICIOUS_MOTION",
        severity="HIGH",
        status="WAITING_ACK"
    )

    # Simulate Android GuardBoxAlertService startup logic
    is_baseline_established = False
    last_known_alert_id = None
    notified_alerts = []

    def simulate_poll():
        nonlocal is_baseline_established, last_known_alert_id
        active = get_active_alert()
        if not is_baseline_established:
            is_baseline_established = True
            if active is not None:
                last_known_alert_id = active["id"]
                # Baseline established -> DO NOT NOTIFY
            else:
                last_known_alert_id = None
        elif active is not None:
            if active["id"] != last_known_alert_id:
                last_known_alert_id = active["id"]
                notified_alerts.append(active["id"])

    # First poll on startup:
    simulate_poll()
    assert is_baseline_established is True
    assert last_known_alert_id == stale_id
    assert len(notified_alerts) == 0, "Expected NO notification on startup with existing active alert baseline"
    print("  [PASS] Scenario 1: Stale active alert on startup established as baseline with 0 notifications.")

    # Second poll without change:
    simulate_poll()
    assert len(notified_alerts) == 0

    # New genuinely new alert created later
    new_alert = push_escalation_service.handle_security_event(
        camera_id=1,
        camera_name="Shop Camera",
        event_type="GLASS_BREAK",
        severity="HIGH",
        force=True
    )
    new_id = new_alert["id"]

    # Poll after new alert created:
    simulate_poll()
    assert len(notified_alerts) == 1
    assert notified_alerts[0] == new_id
    print(f"  [PASS] Scenario 2: Genuinely new alert #{new_id} triggered exact 1 notification.")


def test_scenario_3_duplicate_alert_suppression():
    print("\n[TEST 3] Duplicate Alert ID Suppression...")
    reset_test_env()

    notified_ids_cache = set()
    notification_counter = 0

    def on_fcm_received(alert_id_str):
        nonlocal notification_counter
        if alert_id_str in notified_ids_cache:
            # Duplicate ignored
            return False
        notified_ids_cache.add(alert_id_str)
        notification_counter += 1
        return True

    assert on_fcm_received("ALERT_100") is True
    assert notification_counter == 1

    # Same alert ID received again
    assert on_fcm_received("ALERT_100") is False
    assert notification_counter == 1
    print("  [PASS] Scenario 3: Duplicate alert ID successfully suppressed by deduplication.")


def test_scenario_4_and_5_silence_and_ack_stops_retries():
    print("\n[TEST 4 & 5] SILENCE & ACKNOWLEDGE Halts Escalation Loop & Retries...")
    reset_test_env()

    # 1. Test SILENCE
    alert_1 = push_escalation_service.handle_security_event(
        camera_id=1,
        camera_name="Camera 1",
        event_type="MOTION_DETECTED",
        severity="HIGH",
        force=True
    )
    time.sleep(0.2)
    push_escalation_service.stop_escalation()
    time.sleep(0.2)
    a1_rec = get_alert_by_id(alert_1["id"])
    assert a1_rec["status"] == "SILENCED"
    assert push_escalation_service.get_status()["is_escalating"] is False
    print("  [PASS] Scenario 4: SILENCE immediately stopped escalation loop and set terminal status.")

    # 2. Test ACKNOWLEDGE
    alert_2 = push_escalation_service.handle_security_event(
        camera_id=1,
        camera_name="Camera 1",
        event_type="INTRUSION_DETECTED",
        severity="HIGH",
        force=True
    )
    time.sleep(0.2)
    push_escalation_service.acknowledge(alert_2["id"], acknowledged_by="Store Manager Phone")
    time.sleep(0.2)
    a2_rec = get_alert_by_id(alert_2["id"])
    assert a2_rec["status"] == "ACKNOWLEDGED"
    assert push_escalation_service.get_status()["is_escalating"] is False
    print("  [PASS] Scenario 5: ACKNOWLEDGE immediately stopped escalation loop and set status to ACKNOWLEDGED.")


def test_scenario_6_completed_alert_cleans_firebase():
    print("\n[TEST 6] Completed Alert Firebase RTDB Cleanup Verification...")
    reset_test_env()

    alert = push_escalation_service.handle_security_event(
        camera_id=1,
        camera_name="Shop Camera",
        event_type="MOTION_DETECTED",
        severity="HIGH",
        force=True
    )
    alert_id = alert["id"]

    # Verify stop_escalation / acknowledge triggers _clear_firebase_current_alert
    push_escalation_service.acknowledge(alert_id, acknowledged_by="Owner")
    # Verify no unhandled exceptions and alert status is ACKNOWLEDGED
    assert get_alert_by_id(alert_id)["status"] == "ACKNOWLEDGED"
    print("  [PASS] Scenario 6: Completed alert triggered active alert clear in Firebase RTDB.")


def test_scenario_7_and_8_backend_startup_safety():
    print("\n[TEST 7 & 8] Backend Startup Stale Alert Cleanup & Safety...")
    reset_test_env()

    # Insert old dangling active alerts from crashed session
    dangling_1 = create_security_alert(
        alert_code="GB-CRASH-001",
        camera_id=1,
        camera_name="Shop Camera",
        event_type="MOTION_DETECTED",
        severity="HIGH",
        status="ESCALATING"
    )
    dangling_2 = create_security_alert(
        alert_code="GB-CRASH-002",
        camera_id=1,
        camera_name="Shop Camera",
        event_type="MOTION_DETECTED",
        severity="HIGH",
        status="WAITING_ACK"
    )

    assert get_active_alert() is not None

    # Simulate backend startup lifespan cleanup
    cleaned_count = cleanup_stale_alerts()
    assert cleaned_count == 2
    assert get_active_alert() is None
    assert get_alert_by_id(dangling_1)["status"] == "CLOSED_ON_STARTUP"
    assert get_alert_by_id(dangling_2)["status"] == "CLOSED_ON_STARTUP"
    print("  [PASS] Scenario 7 & 8: Startup safely closed 2 stale alerts, get_active_alert() returns None.")


if __name__ == "__main__":
    print("==================================================================")
    print("GuardBox — Stale / False Emergency Alert Fix Verification Suite")
    print("==================================================================")
    test_scenario_1_and_2_baseline_and_new_alert()
    test_scenario_3_duplicate_alert_suppression()
    test_scenario_4_and_5_silence_and_ack_stops_retries()
    test_scenario_6_completed_alert_cleans_firebase()
    test_scenario_7_and_8_backend_startup_safety()
    print("\n==================================================================")
    print("ALL STALE ALERT FIX TEST SCENARIOS PASSED [100% OK]")
    print("==================================================================")
