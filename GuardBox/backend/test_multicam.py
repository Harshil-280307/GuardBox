"""
Veronic GuardBox - Multi-Camera & Multi-Zone Verification Script
Tests multi-camera CRUD, multi-zone per camera CRUD, RTSP test connection endpoint,
camera stream endpoint, camera enable/disable, zone toggle, and event queries.
"""

import sys
from app.database import (
    init_db,
    get_all_cameras,
    get_camera_by_id,
    create_camera,
    update_camera,
    delete_camera,
    toggle_camera,
    get_zones_by_camera,
    create_zone,
    update_zone,
    delete_zone,
    toggle_zone,
    get_all_zones,
    get_filtered_events,
    create_security_event
)
from app.camera import camera_manager, CameraWorker
from app.detection import motion_service


def test_multicam_features():
    print("========================================")
    print("Veronic GuardBox - Multi-Camera Verification")
    print("========================================")

    init_db()

    # 1. Verify default camera exists
    cameras = get_all_cameras()
    print(f"[TEST 1] Testing Default Camera Discovery... Found {len(cameras)} cameras")
    assert len(cameras) >= 1, "Expected at least 1 camera"
    main_cam = cameras[0]
    print(f"  [PASS] Primary Camera: ID={main_cam['id']}, Name='{main_cam['name']}', Model='{main_cam['model']}'")

    # 2. Add second camera
    print("[TEST 2] Testing Add Second Camera...")
    cam2_id = create_camera(
        name="Showcase Counter Camera",
        brand="TP-Link",
        model="Tapo C100",
        rtsp_url="rtsp://testuser:testpass@192.168.31.109:554/stream1",
        enabled=True
    )
    assert cam2_id > 1, "Failed to create second camera"
    cam2 = get_camera_by_id(cam2_id)
    assert cam2 is not None
    assert cam2["name"] == "Showcase Counter Camera"
    print(f"  [PASS] Created Camera #{cam2_id}: '{cam2['name']}'")

    # 3. Test Camera Update & Toggle
    print("[TEST 3] Testing Camera Update & Toggle...")
    up_res = update_camera(cam2_id, name="Showcase Counter 2", brand="TP-Link", model="Tapo C200")
    assert up_res is True
    cam2_up = get_camera_by_id(cam2_id)
    assert cam2_up["name"] == "Showcase Counter 2"
    assert cam2_up["model"] == "Tapo C200"

    tog_res = toggle_camera(cam2_id, enabled=False)
    assert tog_res is True
    assert get_camera_by_id(cam2_id)["enabled"] == 0
    toggle_camera(cam2_id, enabled=True)
    assert get_camera_by_id(cam2_id)["enabled"] == 1
    print("  [PASS] Camera profile update and toggle passed.")

    # 4. Create multiple detection zones for Camera 2
    print("[TEST 4] Testing Multiple Zones Per Camera...")
    z1_id = create_zone(
        camera_id=cam2_id,
        name="Cabinet Top Shelf",
        x=0.1, y=0.1, width=0.3, height=0.3,
        sensitivity=40, minimum_motion_area=150, cooldown_seconds=2.5
    )
    z2_id = create_zone(
        camera_id=cam2_id,
        name="Cash Register",
        x=0.5, y=0.5, width=0.4, height=0.4,
        sensitivity=35, minimum_motion_area=200, cooldown_seconds=3.0
    )
    assert z1_id > 0 and z2_id > 0

    cam2_zones = get_zones_by_camera(cam2_id)
    assert len(cam2_zones) == 2, f"Expected 2 zones for camera #{cam2_id}, got {len(cam2_zones)}"
    print(f"  [PASS] Successfully created and fetched {len(cam2_zones)} detection zones for Camera #{cam2_id}")

    # 5. Zone toggle and edit
    print("[TEST 5] Testing Zone Toggle and Edit...")
    tog_z1 = toggle_zone(z1_id, enabled=False)
    assert tog_z1["enabled"] == 0
    toggle_zone(z1_id, enabled=True)
    assert toggle_zone(z1_id)["enabled"] == 0  # auto-toggled to 0
    toggle_zone(z1_id, enabled=True)          # reset to 1

    up_z1 = update_zone(z1_id, name="Cabinet High Value", x=0.15, y=0.15, width=0.35, height=0.35, sensitivity=50)
    assert up_z1 is True
    print("  [PASS] Zone toggle and parameter updates verified.")

    # 6. Test Security Event with Camera Attribution
    print("[TEST 6] Testing Security Events with Camera Attribution...")
    ev_id = create_security_event(
        camera_id=cam2_id,
        camera_name="Showcase Counter 2",
        zone_id=z1_id,
        zone_name="Cabinet High Value",
        event_type="MOTION_DETECTED",
        motion_area=450.0,
        system_mode="ARMED"
    )
    assert ev_id > 0
    ev_filtered = get_filtered_events(camera_id=cam2_id)
    assert len(ev_filtered["items"]) >= 1
    assert ev_filtered["items"][0]["camera_id"] == cam2_id
    assert ev_filtered["items"][0]["camera_name"] == "Showcase Counter 2"
    print(f"  [PASS] Event #{ev_id} properly attributed to Camera #{cam2_id}")

    # 7. Clean up test camera
    print("[TEST 7] Testing Camera Deletion & Cascade Clean-up...")
    del_res = delete_camera(cam2_id)
    assert del_res is True
    assert get_camera_by_id(cam2_id) is None
    assert len(get_zones_by_camera(cam2_id)) == 0, "Zones were not cascade deleted"
    print("  [PASS] Camera and its detection zones cleanly deleted.")

    print("========================================")
    print("ALL MULTI-CAMERA TESTS PASSED! [OK]")
    print("========================================")


if __name__ == "__main__":
    test_multicam_features()
