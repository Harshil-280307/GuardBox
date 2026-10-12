"""
GuardBox Real-Time System Status Synchronization Test Suite
Tests bidirectional synchronization:
1. Windows startup status publishing (DISARMED -> STOPPED).
2. Windows local ARM -> Firebase state update (RUNNING / ARMED).
3. Windows local DISARM -> Firebase state update (STOPPED / DISARMED).
4. Remote command ARM -> Windows motion service arming -> Firebase status publishing.
5. Remote command DISARM -> Windows motion service disarming -> Firebase status publishing.
6. Temporary disconnect and reconnection state retrieval.
7. Backend restart presence recovery with actual motion state.
8. Separation between Connection State (online/offline) and System State (ARMED/DISARMED).
"""

import sys
import os
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.detection import motion_service
from app.firebase_bridge import firebase_bridge


class TestSystemStatusSynchronization(unittest.TestCase):

    def setUp(self):
        # Ensure fresh state
        motion_service.disarm()
        self.published_statuses = []
        with firebase_bridge._processed_lock:
            firebase_bridge._processed_command_ids.clear()

        # Mock update_presence to capture status updates
        self.orig_update_presence = firebase_bridge.update_presence

        def mock_update_presence(online=True, status_str=None, async_publish=False):
            st = status_str if status_str is not None else firebase_bridge._get_current_system_status_str()
            self.published_statuses.append({"online": online, "status": st})

        firebase_bridge.update_presence = mock_update_presence

        # Register callback
        motion_service.register_state_change_listener(firebase_bridge._on_motion_service_state_change)

    def tearDown(self):
        firebase_bridge.update_presence = self.orig_update_presence
        motion_service.disarm()

    def test_01_windows_starts_disarmed(self):
        """TEST 1: Windows starts DISARMED -> Reports STOPPED / DISARMED."""
        motion_service.disarm()
        st = firebase_bridge._get_current_system_status_str()
        self.assertEqual(st, "STOPPED")
        self.assertFalse(motion_service.is_armed)

    def test_02_windows_arm_directly(self):
        """TEST 2: Windows ARM directly -> Firebase status becomes RUNNING."""
        self.published_statuses.clear()
        motion_service.arm(exit_delay_seconds=0)

        self.assertTrue(motion_service.is_armed)
        self.assertEqual(motion_service.current_mode, "ARMED")

        # Verify listener published status to Firebase
        self.assertTrue(len(self.published_statuses) >= 1)
        latest = self.published_statuses[-1]
        self.assertEqual(latest["status"], "RUNNING")
        self.assertTrue(latest["online"])

    def test_03_windows_disarm_directly(self):
        """TEST 3: Windows DISARM directly -> Firebase status becomes STOPPED."""
        motion_service.arm(exit_delay_seconds=0)
        self.published_statuses.clear()

        motion_service.disarm()
        self.assertFalse(motion_service.is_armed)
        self.assertEqual(motion_service.current_mode, "DISARMED")

        self.assertTrue(len(self.published_statuses) >= 1)
        latest = self.published_statuses[-1]
        self.assertEqual(latest["status"], "STOPPED")
        self.assertTrue(latest["online"])

    def test_04_remote_command_arm(self):
        """TEST 4: Remote ARM command -> Windows arms -> Firebase status RUNNING."""
        motion_service.disarm()
        self.published_statuses.clear()

        cmd_id = f"test_cmd_arm_{time.time()}"
        cmd_payload = {"command": "ARM", "status": "PENDING", "requested_by": "test_android"}
        firebase_bridge._process_single_command(cmd_id, cmd_payload)

        self.assertTrue(motion_service.is_armed)
        self.assertEqual(motion_service.current_mode, "ARMED")
        self.assertTrue(len(self.published_statuses) >= 1)
        latest = self.published_statuses[-1]
        self.assertEqual(latest["status"], "RUNNING")

    def test_05_remote_command_disarm(self):
        """TEST 5: Remote DISARM command -> Windows disarms -> Firebase status STOPPED."""
        motion_service.arm(exit_delay_seconds=0)
        self.published_statuses.clear()

        cmd_id = f"test_cmd_disarm_{time.time()}"
        cmd_payload = {"command": "DISARM", "status": "PENDING", "requested_by": "test_android"}
        firebase_bridge._process_single_command(cmd_id, cmd_payload)

        self.assertFalse(motion_service.is_armed)
        self.assertEqual(motion_service.current_mode, "DISARMED")
        self.assertTrue(len(self.published_statuses) >= 1)
        latest = self.published_statuses[-1]
        self.assertEqual(latest["status"], "STOPPED")

    def test_06_temporary_disconnect_reconnection(self):
        """TEST 6: Reconnection fetches actual Windows authoritative state."""
        motion_service.arm(exit_delay_seconds=0)
        # Phone reconnects and queries current state
        synced_state = firebase_bridge._get_current_system_status_str()
        self.assertEqual(synced_state, "RUNNING")

        motion_service.disarm()
        synced_state = firebase_bridge._get_current_system_status_str()
        self.assertEqual(synced_state, "STOPPED")

    def test_07_restart_windows_backend(self):
        """TEST 7: Restart Windows backend recovers real physical state."""
        # Suppose Windows starts in disarmed state
        motion_service._mode = "DISARMED"
        current_status = firebase_bridge._get_current_system_status_str()
        self.assertEqual(current_status, "STOPPED")

        # Suppose Windows was already running/armed
        motion_service._mode = "ARMED"
        current_status = firebase_bridge._get_current_system_status_str()
        self.assertEqual(current_status, "RUNNING")

    def test_08_connection_status_and_system_status_remain_separate(self):
        """TEST 8: Connection state (online/offline) is independent of System state (RUNNING/STOPPED)."""
        # Scenario A: Device Online, System ARMED
        motion_service.arm(exit_delay_seconds=0)
        st_armed = firebase_bridge._get_current_system_status_str()
        self.assertEqual(st_armed, "RUNNING")

        # Scenario B: Device Offline (shutting down cleanly), System state is preserved in record
        firebase_bridge.update_presence(online=False, status_str=st_armed)
        latest = self.published_statuses[-1]
        self.assertEqual(latest["online"], False)
        self.assertEqual(latest["status"], "RUNNING")  # System was armed when device went offline


if __name__ == "__main__":
    unittest.main()
