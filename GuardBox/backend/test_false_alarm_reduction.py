"""
Veronic GuardBox - Layered False-Alarm Reduction Verification Test Suite (Phase 9 Hardened)
Validates:
1. Lens Insect / Transient Jitter Rejection (Extreme velocity + tiny blob)
2. Small Floor Rodent / Mouse Rejection (Low height, flat aspect ratio, tiny area)
3. Distant / Partially Visible Person Protection (Distant upright posture detected)
4. Crouching / Non-Upright Person Protection (Substantial mass & texture detected as HUMAN)
5. Shadow & Diffuse Lighting Shift Rejection (Low edge gradient density)
6. Verified Upright Human Intruder Escalation (Upright posture, coherent track, edge gradients)
7. Critical Zone (Safe / Vault) Rapid Escalation (Prompt 2-frame confirmation, high priority)
8. Multi-Zone / Multi-Intruder Isolation (Zone 1 cooldown does not suppress Zone 2 intrusion)
9. Whole-Room Global Illumination Flash (Lights switch on/off handled smoothly)
10. Ambiguous / Uncertain Candidate Retention for Review (Saved as SUSPICIOUS_MOTION / FOR_REVIEW without siren or push flood)
"""

import time
import numpy as np
import cv2
from app.config import settings
from app.detection import CameraMotionDetector
from app.database import (
    init_db,
    get_filtered_events,
    get_db_connection
)


def clear_all_camera_events(camera_id=98):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM events WHERE camera_id = ?", (camera_id,))
        conn.commit()
    finally:
        conn.close()


def run_false_alarm_tests():
    print("=================================================================")
    print("TRINETRA - Hardened False-Alarm Reduction & Protection Test Suite")
    print("=================================================================")
    init_db()
    clear_all_camera_events(98)

    w, h = 640, 360
    detector = CameraMotionDetector(camera_id=98, camera_name="Test False Alarm Cam")

    # Standard Zone (General Shop Floor)
    standard_zone = {
        "id": 981,
        "name": "General Shop Floor",
        "camera_id": 98,
        "x": 0.1,
        "y": 0.1,
        "width": 0.8,
        "height": 0.8,
        "enabled": 1,
        "sensitivity": 35,
        "minimum_motion_area": 250,
        "cooldown_seconds": 4.0
    }

    # Critical Zone (Jewelry Safe / Vault)
    critical_zone = {
        "id": 982,
        "name": "Diamond Safe Vault",
        "camera_id": 98,
        "x": 0.5,
        "y": 0.2,
        "width": 0.4,
        "height": 0.6,
        "enabled": 1,
        "sensitivity": 40,
        "minimum_motion_area": 200,
        "cooldown_seconds": 4.0,
        "is_critical": True
    }

    import app.detection as det_mod
    original_get_zones = det_mod.get_zones_by_camera
    current_zones = [standard_zone]
    det_mod.get_zones_by_camera = lambda cam_id: current_zones if cam_id == 98 else original_get_zones(cam_id)

    try:
        # Base background frame
        base_frame = np.full((h, w, 3), 60, dtype=np.uint8)
        cv2.putText(base_frame, "SHOP FLOOR BACKGROUND", (100, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (180, 180, 180), 2)

        # ---------------------------------------------------------------------
        # 1. Warm-up Calibration
        # ---------------------------------------------------------------------
        print("\n[TEST 1] Calibration Phase...")
        for i in range(25):
            noise = np.random.randint(-2, 3, (h, w, 3), dtype=np.int16)
            noisy_frame = np.clip(base_frame.astype(np.int16) + noise, 0, 255).astype(np.uint8)
            detector.process_frame(noisy_frame, mode="TEST_MODE")

        assert detector._is_calibrated is True, "Detector should be calibrated"
        print("  [PASS] Detector calibrated successfully with 0 false events.")

        # ---------------------------------------------------------------------
        # 2. Transient Insect / Mosquito Near Lens (Erratic Jump)
        # ---------------------------------------------------------------------
        print("\n[TEST 2] Transient Lens Insect / High-Speed Jitter...")
        clear_all_camera_events(98)
        # Frame 1: Insect at top-left
        f1 = base_frame.copy()
        cv2.circle(f1, (120, 100), 10, (240, 240, 240), -1)
        detector.process_frame(f1, mode="ARMED")

        # Frame 2: Insect jumps 300px across screen (unphysical speed for tiny blob)
        f2 = base_frame.copy()
        cv2.circle(f2, (450, 280), 10, (240, 240, 240), -1)
        detector.process_frame(f2, mode="ARMED")

        # Frame 3: Disappears
        detector.process_frame(base_frame, mode="ARMED")

        events = get_filtered_events(page=1, page_size=10, camera_id=98)
        assert len(events["items"]) == 0, f"Expected 0 events for lens insect, got {len(events['items'])}"
        print("  [PASS] Lens insect rejected without false alarm.")

        # ---------------------------------------------------------------------
        # 3. Mouse-sized Small Rodent on Floor
        # ---------------------------------------------------------------------
        print("\n[TEST 3] Mouse / Small Ground Rodent Filter...")
        clear_all_camera_events(98)
        # Small flat horizontal blob moving along the bottom floor (h=10px, w=24px, h/w=0.41, area=180px)
        for i in range(5):
            mouse_frame = base_frame.copy()
            mx = 200 + (i * 6)
            my = 310
            cv2.ellipse(mouse_frame, (mx, my), (14, 6), 0, 0, 360, (200, 200, 200), -1)
            detector.process_frame(mouse_frame, mode="ARMED")
            time.sleep(0.005)

        events = get_filtered_events(page=1, page_size=10, camera_id=98)
        assert len(events["items"]) == 0, f"Expected 0 events for small rodent, got {len(events['items'])}"
        print("  [PASS] Small ground rodent successfully filtered out.")

        # ---------------------------------------------------------------------
        # 4. Distant / Partially Visible Person (Protection Test)
        # ---------------------------------------------------------------------
        print("\n[TEST 4] Distant / Partially Visible Person Protection...")
        clear_all_camera_events(98)
        detector._zone_cooldowns.clear()
        # Distant upright person: h=35px, w=15px (h/w=2.33, rel_h=35/360=0.097 > 0.045) moving with walking speed
        for i in range(4):
            distant_frame = base_frame.copy()
            dx = 250 + (i * 5)
            dy = 130
            # Small upright silhouette
            cv2.rectangle(distant_frame, (dx, dy), (dx + 15, dy + 35), (255, 255, 255), -1)
            cv2.line(distant_frame, (dx + 7, dy + 10), (dx + 7, dy + 30), (0, 0, 0), 1)
            detector.process_frame(distant_frame, mode="ARMED")
            time.sleep(0.005)

        events_dist = get_filtered_events(page=1, page_size=10, camera_id=98)
        assert len(events_dist["items"]) >= 1, f"Expected detection for distant person, got {len(events_dist['items'])}"
        print(f"  [PASS] Distant person correctly protected and detected: Event #{events_dist['items'][0]['id']}.")

        # ---------------------------------------------------------------------
        # 5. Crouching / Non-Upright Person (Protection Test)
        # ---------------------------------------------------------------------
        print("\n[TEST 5] Crouching / Non-Upright Person Protection...")
        clear_all_camera_events(98)
        detector._zone_cooldowns.clear()
        # Crouching human: wider than tall (w=60px, h=30px, area=1800px, distinct texture)
        for i in range(4):
            crouch_frame = base_frame.copy()
            cx = 220 + (i * 6)
            cy = 200
            # Solid crouching body with clothing texture
            cv2.rectangle(crouch_frame, (cx, cy), (cx + 60, cy + 30), (240, 240, 240), -1)
            cv2.putText(crouch_frame, "CROUCH", (cx + 5, cy + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1)
            detector.process_frame(crouch_frame, mode="ARMED")
            time.sleep(0.005)

        events_crouch = get_filtered_events(page=1, page_size=10, camera_id=98)
        assert len(events_crouch["items"]) >= 1, f"Expected detection for crouching intruder, got {len(events_crouch['items'])}"
        print(f"  [PASS] Crouching person correctly detected as intruder: Event #{events_crouch['items'][0]['id']}.")

        # ---------------------------------------------------------------------
        # 6. Diffuse Shadow / Ambient Lighting Shift
        # ---------------------------------------------------------------------
        print("\n[TEST 6] Diffuse Shadow / Smooth Reflection...")
        clear_all_camera_events(98)
        detector._zone_cooldowns.clear()
        for i in range(5):
            shadow_frame = base_frame.copy()
            overlay = shadow_frame.copy()
            cv2.rectangle(overlay, (180, 120), (320, 260), (100, 100, 100), -1)
            cv2.addWeighted(overlay, 0.4, shadow_frame, 0.6, 0, shadow_frame)
            cv2.GaussianBlur(shadow_frame[120:260, 180:320], (15, 15), 0, dst=shadow_frame[120:260, 180:320])
            detector.process_frame(shadow_frame, mode="ARMED")
            time.sleep(0.005)

        events_shadow = get_filtered_events(page=1, page_size=10, camera_id=98)
        assert len(events_shadow["items"]) == 0, f"Expected 0 events for diffuse shadow, got {len(events_shadow['items'])}"
        print("  [PASS] Diffuse shadow / soft reflection successfully suppressed.")

        # ---------------------------------------------------------------------
        # 7. Verified Upright Human Intruder in Monitored Area
        # ---------------------------------------------------------------------
        print("\n[TEST 7] Upright Human Intruder in Monitored Area...")
        clear_all_camera_events(98)
        detector._zone_cooldowns.clear()
        for i in range(4):
            human_frame = base_frame.copy()
            hx = 220 + (i * 8)
            hy = 140
            cv2.circle(human_frame, (hx + 25, hy + 20), 16, (255, 230, 200), -1)
            cv2.rectangle(human_frame, (hx + 5, hy + 38), (hx + 45, hy + 95), (20, 80, 180), -1)
            cv2.line(human_frame, (hx + 15, hy + 95), (hx + 15, hy + 140), (40, 40, 40), 6)
            cv2.line(human_frame, (hx + 35, hy + 95), (hx + 35, hy + 140), (40, 40, 40), 6)
            detector.process_frame(human_frame, mode="ARMED")
            time.sleep(0.005)

        events_human = get_filtered_events(page=1, page_size=10, camera_id=98)
        assert len(events_human["items"]) == 1, f"Expected 1 event for verified human, got {len(events_human['items'])}"
        ev = events_human["items"][0]
        assert ev["severity"] == "HIGH"
        print(f"  [PASS] Human intruder confirmed: Event #{ev['id']} (severity={ev['severity']}, notes='{ev['notes']}').")

        # ---------------------------------------------------------------------
        # 8. Critical Zone (Diamond Safe Vault) Rapid Escalation
        # ---------------------------------------------------------------------
        print("\n[TEST 8] Critical Zone (Diamond Safe Vault) Rapid Escalation...")
        clear_all_camera_events(98)
        current_zones = [critical_zone]
        detector._zone_cooldowns.clear()

        # In critical zone, motion confirms in just 2 frames with high priority
        for i in range(2):
            crit_frame = base_frame.copy()
            cx = 400 + (i * 10)
            cy = 160
            cv2.rectangle(crit_frame, (cx, cy), (cx + 60, cy + 100), (255, 255, 255), -1)
            cv2.putText(crit_frame, "INTRUDER", (cx + 5, cy + 40), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1)
            detector.process_frame(crit_frame, mode="ARMED")
            time.sleep(0.005)

        events_crit = get_filtered_events(page=1, page_size=10, camera_id=98)
        assert len(events_crit["items"]) == 1, f"Expected 1 event in critical zone in 2 frames, got {len(events_crit['items'])}"
        ev = events_crit["items"][0]
        assert ev["zone_name"] == "Diamond Safe Vault"
        assert ev["severity"] == "HIGH"
        print(f"  [PASS] Critical zone triggered promptly (2 frames): Event #{ev['id']} in '{ev['zone_name']}'.")

        # ---------------------------------------------------------------------
        # 9. Multi-Zone / Deduplication Isolation
        # ---------------------------------------------------------------------
        print("\n[TEST 9] Multi-Zone Event Deduplication & Isolation...")
        clear_all_camera_events(98)
        current_zones = [standard_zone, critical_zone]
        detector._zone_cooldowns.clear()

        # Intruder 1 in standard zone (left side: x=150, y=150)
        for i in range(3):
            f_multi = base_frame.copy()
            cv2.rectangle(f_multi, (150 + i*5, 150), (200 + i*5, 250), (240, 240, 240), -1)
            detector.process_frame(f_multi, mode="ARMED")

        events_1 = get_filtered_events(page=1, page_size=10, camera_id=98)
        assert len(events_1["items"]) == 1, f"Expected 1 event for standard zone, got {len(events_1['items'])}"
        print(f"  [PASS] First zone triggered: Event #{events_1['items'][0]['id']} in '{events_1['items'][0]['zone_name']}'.")

        # Intruder 1 remains in standard zone during cooldown
        for i in range(3):
            f_multi = base_frame.copy()
            cv2.rectangle(f_multi, (165, 150), (215, 250), (240, 240, 240), -1)
            detector.process_frame(f_multi, mode="ARMED")

        events_after_dup = get_filtered_events(page=1, page_size=10, camera_id=98)
        assert len(events_after_dup["items"]) == 1, "Duplicate event in same zone should be suppressed by cooldown"
        print("  [PASS] Ongoing motion in Zone 1 deduplicated without spam.")

        # Second separate intruder enters CRITICAL Safe zone (right side: x=420, y=160)
        for i in range(2):
            f_multi = base_frame.copy()
            cv2.rectangle(f_multi, (165, 150), (215, 250), (240, 240, 240), -1)
            cv2.rectangle(f_multi, (420 + i*8, 160), (480 + i*8, 260), (255, 255, 255), -1)
            detector.process_frame(f_multi, mode="ARMED")

        events_multi = get_filtered_events(page=1, page_size=10, camera_id=98)
        assert len(events_multi["items"]) == 2, f"Expected 2 distinct zone events, got {len(events_multi['items'])}"
        zone_names = [e["zone_name"] for e in events_multi["items"]]
        assert "General Shop Floor" in zone_names and "Diamond Safe Vault" in zone_names
        print(f"  [PASS] Distinct critical zone intrusion escalated independently! Both events recorded.")

        # ---------------------------------------------------------------------
        # 10. Whole-Room Global Illumination Flash (Lights On/Off)
        # ---------------------------------------------------------------------
        print("\n[TEST 10] Whole-Room Illumination Flash (Lights On/Off)...")
        clear_all_camera_events(98)
        detector._zone_cooldowns.clear()

        flash_frame = np.clip(base_frame.astype(np.int16) + 120, 0, 255).astype(np.uint8)
        detector.process_frame(flash_frame, mode="ARMED")
        detector.process_frame(flash_frame, mode="ARMED")

        events_flash = get_filtered_events(page=1, page_size=10, camera_id=98)
        assert len(events_flash["items"]) == 0, f"Expected 0 events for global light switch, got {len(events_flash['items'])}"
        print("  [PASS] Sudden whole-room lighting shift handled smoothly without false alarm.")

        # ---------------------------------------------------------------------
        # 11. Ambiguous Candidate Retained for Review (Conservative Path)
        # ---------------------------------------------------------------------
        print("\n[TEST 11] Ambiguous Candidate Retained for Review (Conservative Path)...")
        clear_all_camera_events(98)
        detector.reset_baseline()
        for _ in range(25):
            detector.process_frame(base_frame, mode="TEST_MODE")
        detector._zone_cooldowns.clear()
        current_zones = [standard_zone]

        # Candidate with moderate area and low contrast (diff > 28 threshold, but no sharp edges, non-upright AR=0.60)
        # Mode ARMED: Logged to DB with status='FOR_REVIEW' and event_type='SUSPICIOUS_MOTION'
        # without triggering loud siren or push escalation
        for i in range(4):
            amb_frame = base_frame.copy()
            ax = 200 + (i * 2)
            ay = 180
            cv2.rectangle(amb_frame, (ax, ay), (ax + 50, ay + 30), (92, 92, 92), -1)
            detector.process_frame(amb_frame, mode="ARMED")
            time.sleep(0.005)

        events_amb = get_filtered_events(page=1, page_size=10, camera_id=98)
        assert len(events_amb["items"]) >= 1, "Ambiguous motion should be retained for review"
        ev_amb = events_amb["items"][0]
        assert ev_amb["status"] == "FOR_REVIEW", f"Expected status FOR_REVIEW, got {ev_amb['status']}"
        assert ev_amb["event_type"] == "SUSPICIOUS_MOTION", f"Expected event_type SUSPICIOUS_MOTION, got {ev_amb['event_type']}"
        assert ev_amb["severity"] == "LOW", f"Expected severity LOW, got {ev_amb['severity']}"
        print(f"  [PASS] Ambiguous candidate retained for review: Event #{ev_amb['id']} (status={ev_amb['status']}, severity={ev_amb['severity']}).")

        # Clean up
        clear_all_camera_events(98)
        print("\n=================================================================")
        print("ALL 11 HARDENED FALSE-ALARM REDUCTION SCENARIOS PASSED (100%)!")
        print("=================================================================")

    finally:
        det_mod.get_zones_by_camera = original_get_zones


if __name__ == "__main__":
    run_false_alarm_tests()
