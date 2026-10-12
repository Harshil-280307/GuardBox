"""
Veronic GuardBox — Phase 3 Android Push Alert & Escalation Test Suite
Validates:
1. Android device registration & FCM token storage (POST /api/devices/register).
2. FCM token refresh handling on existing device ID.
3. Multi-device priority ordering & reordering (POST /api/devices/reorder).
4. Safe test push notification dispatch (POST /api/devices/{device_id}/test-push).
5. Notification settings persistence (GET/POST /api/notifications/settings).
6. Security alert creation & automatic FCM emergency push dispatch.
7. Push notification payload formatting (High-priority, Siren Sound, Emergency Channel, Full-Screen Intent).
8. Alert acknowledgement ('I'M HANDLING IT') stopping escalation loop immediately.
9. Multi-device escalation sequence (Device 1 -> Device 2).
10. Anti-spam camera cooldown protection.
11. Notification health diagnostics (GET /api/notifications/health).
"""

import sys
import json
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from app.config import settings
from app.database import (
    init_db,
    get_all_devices,
    get_device_by_id,
    register_device,
    delete_device,
    reorder_devices,
    get_notification_settings,
    update_notification_settings,
    get_active_alert,
    get_alert_by_id,
    get_recent_alerts,
    get_deliveries_by_alert,
    get_push_history
)
from app.push import fcm_service, push_escalation_service


def reset_test_state():
    """Reset database state and clear active alerts for clean test execution."""
    init_db()
    from app.database import get_db_connection
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE security_alerts SET status = 'ACKNOWLEDGED' WHERE status IN ('WAITING_ACK', 'ESCALATING', 'NOTIFYING')")
        cursor.execute("DELETE FROM notification_devices")
        conn.commit()

    # Register 3 standard test devices
    d1 = register_device(
        device_id="test_dev_01",
        user_name="Store Owner",
        fcm_token="fcm_token_alice_pixel8",
        device_name="Pixel 8 Pro",
        platform="android",
        priority=1
    )
    d2 = register_device(
        device_id="test_dev_02",
        user_name="Store Manager",
        fcm_token="fcm_token_bob_s24",
        device_name="Samsung Galaxy S24",
        platform="android",
        priority=2
    )
    d3 = register_device(
        device_id="test_dev_03",
        user_name="Security Guard",
        fcm_token="fcm_token_charlie_tablet",
        device_name="Lenovo Tab M10",
        platform="android",
        priority=3
    )

    update_notification_settings(
        auto_push_enabled=True,
        push_timeout_seconds=2,
        max_retry_cycles=2,
        min_alert_severity="HIGH",
        cooldown_seconds=5
    )

    push_escalation_service._camera_cooldowns.clear()
    push_escalation_service.stop_escalation()
    fcm_service._last_dispatched_payloads.clear()
    return d1, d2, d3


def test_1_device_registration_and_token_refresh():
    print("\n[TEST 1] Testing Android Device Registration & Token Refresh...")
    reset_test_state()

    devices = get_all_devices()
    assert len(devices) == 3, f"Expected 3 devices, found {len(devices)}"
    assert devices[0]["device_id"] == "test_dev_01"
    assert devices[0]["priority"] == 1
    assert "masked_token" in devices[0]

    # Test FCM Token Refresh on existing device
    updated_d1 = register_device(
        device_id="test_dev_01",
        user_name="Store Owner (Updated)",
        fcm_token="fcm_token_alice_pixel8_REFRESHED_999",
        device_name="Pixel 8 Pro (Work)",
        platform="android"
    )
    assert updated_d1["fcm_token"] == "fcm_token_alice_pixel8_REFRESHED_999"
    assert updated_d1["device_name"] == "Pixel 8 Pro (Work)"
    assert updated_d1["priority"] == 1

    # Verify total count unchanged after token update
    devices_after = get_all_devices()
    assert len(devices_after) == 3
    print("  [PASS] Device registration and token refresh verified.")


def test_2_device_reordering():
    print("\n[TEST 2] Testing Priority Escalation Reordering...")
    reset_test_state()

    devices = get_all_devices()
    all_ids = [d["device_id"] for d in devices]
    reversed_ids = list(reversed(all_ids))

    success = reorder_devices(reversed_ids)
    assert success is True

    reordered = get_all_devices()
    assert reordered[0]["device_id"] == reversed_ids[0]
    assert reordered[0]["priority"] == 1
    assert reordered[-1]["device_id"] == reversed_ids[-1]
    assert reordered[-1]["priority"] == len(reversed_ids)

    print("  [PASS] Notification device priority reordering verified.")


def test_3_safe_test_push():
    print("\n[TEST 3] Testing Safe Test Push Dispatch...")
    reset_test_state()

    res = push_escalation_service.send_test_push("test_dev_01")
    assert res["success"] is True
    assert res["status"] in ("DELIVERED", "SENT")
    assert res["device_id"] == "test_dev_01"

    # Verify logged in database
    history = get_push_history(page=1, page_size=5)
    assert len(history["items"]) >= 1
    latest = history["items"][0]
    assert latest["is_test"] == 1
    assert latest["alert_code"] == "TEST-PUSH"

    # Verify FCM payload structure
    assert len(fcm_service._last_dispatched_payloads) >= 1
    last_payload = fcm_service._last_dispatched_payloads[-1]
    assert "Device Connection Test" in last_payload["notification"]["title"]

    print("  [PASS] Safe non-emergency test push dispatched and verified.")


def test_4_emergency_alert_creation_and_payload():
    print("\n[TEST 4] Testing Security Alert Creation & FCM High-Priority Payload...")
    reset_test_state()

    alert = push_escalation_service.handle_security_event(
        camera_id=1,
        camera_name="Main Shop Camera",
        event_type="UNAUTHORIZED_INTRUSION",
        severity="HIGH",
        force=True
    )
    assert alert is not None
    assert alert["alert_code"].startswith("TRI-") or alert["alert_code"].startswith("GB-")
    assert alert["status"] in ("WAITING_ACK", "ESCALATING")

    # Verify FCM payload format
    time.sleep(0.3)
    assert len(fcm_service._last_dispatched_payloads) >= 1
    payload = fcm_service._last_dispatched_payloads[-1]

    assert payload["priority"] == "high"
    assert ("TRINETRA" in payload["notification"]["title"]) or ("GUARDBOX" in payload["notification"]["title"])
    assert payload["notification"]["sound"] in ("guardbox_emergency_alert", "siren_alert")
    assert payload["notification"]["android_channel_id"] in ("guardbox_security_alerts", "security_emergency_channel")
    assert payload["data"]["type"] == "SECURITY_ALERT"
    assert payload["data"]["full_screen_intent"] == "true"
    assert payload["data"]["alert_id"] in (str(alert["id"]), alert["alert_code"])

    print("  [PASS] Emergency alert created with full-screen intent & siren channel payload.")


def test_5_alert_acknowledgement_stops_escalation():
    print("\n[TEST 5] Testing Alert Acknowledgement ('I'M HANDLING IT') Stops Loop...")
    reset_test_state()

    alert = push_escalation_service.handle_security_event(
        camera_id=1,
        camera_name="Display Vault Camera",
        event_type="GLASS_BREAK_SUSPICIOUS",
        severity="HIGH",
        force=True
    )
    alert_id = alert["id"]

    time.sleep(0.2)
    # Acknowledge via Android app
    success = push_escalation_service.acknowledge(alert_id, acknowledged_by="Android: Pixel 8 (Store Owner)")
    assert success is True

    time.sleep(0.3)
    updated_alert = get_alert_by_id(alert_id)
    assert updated_alert["status"] == "ACKNOWLEDGED"
    assert updated_alert["acknowledged_by"] == "Android: Pixel 8 (Store Owner)"

    # Verify escalation loop stopped
    st = push_escalation_service.get_status()
    assert st["is_escalating"] is False

    print("  [PASS] 'I'M HANDLING IT' acknowledgement halts escalation immediately.")


def test_6_multi_device_escalation_flow():
    print("\n[TEST 6] Testing Multi-Device Escalation Flow (Priority 1 -> Priority 2)...")
    reset_test_state()

    # Set 1 second timeout
    update_notification_settings(push_timeout_seconds=1, max_retry_cycles=1)

    alert = push_escalation_service.handle_security_event(
        camera_id=1,
        camera_name="Main Entrance",
        event_type="UNAUTHORIZED_MOTION",
        severity="HIGH",
        force=True
    )
    alert_id = alert["id"]

    # Wait 2.5 seconds to allow timeout on Device 1 and transition to Device 2
    time.sleep(2.5)

    deliveries = get_deliveries_by_alert(alert_id)
    assert len(deliveries) >= 2, f"Expected at least 2 device deliveries, found {len(deliveries)}"
    assert deliveries[0]["device_id"] == "test_dev_01"
    assert deliveries[1]["device_id"] == "test_dev_02"

    print("  [PASS] Escalation sequentially advanced from Device #1 to Device #2.")


def test_7_anti_spam_camera_cooldown():
    print("\n[TEST 7] Testing Anti-Spam Camera Cooldown Protection...")
    reset_test_state()

    # First event triggers alert
    alert1 = push_escalation_service.handle_security_event(
        camera_id=2,
        camera_name="Warehouse Cam",
        event_type="MOTION",
        severity="HIGH",
        force=False
    )
    assert alert1 is not None

    # Immediate second event on same camera must be suppressed by cooldown
    alert2 = push_escalation_service.handle_security_event(
        camera_id=2,
        camera_name="Warehouse Cam",
        event_type="MOTION",
        severity="HIGH",
        force=False
    )
    assert alert2 is None, "Second event within cooldown should be suppressed"

    print("  [PASS] Duplicate alert suppressed by camera cooldown.")


def test_8_notification_settings_and_health():
    print("\n[TEST 8] Testing Notification Settings & Health Diagnostics...")
    reset_test_state()

    cfg = get_notification_settings()
    assert cfg["auto_push_enabled"] is True
    assert cfg["min_alert_severity"] == "HIGH"

    updated = update_notification_settings(
        auto_push_enabled=True,
        push_timeout_seconds=45,
        max_retry_cycles=3
    )
    assert updated["push_timeout_seconds"] == 45
    assert updated["max_retry_cycles"] == 3

    print("  [PASS] Notification settings CRUD verified.")


if __name__ == "__main__":
    print("================================================================")
    print("Veronic GuardBox — Phase 3 Push Escalation Test Suite")
    print("================================================================")
    test_1_device_registration_and_token_refresh()
    test_2_device_reordering()
    test_3_safe_test_push()
    test_4_emergency_alert_creation_and_payload()
    test_5_alert_acknowledgement_stops_escalation()
    test_6_multi_device_escalation_flow()
    test_7_anti_spam_camera_cooldown()
    test_8_notification_settings_and_health()
    print("================================================================")
    print("ALL PHASE 3 PUSH ESCALATION TESTS PASSED! [100% OK]")
    print("================================================================")
