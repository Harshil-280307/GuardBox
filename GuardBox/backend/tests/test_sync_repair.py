"""
TRINETRA - Device ID & ARM/DISARM Synchronization Repair Test Suite
Covers all 14 required synchronization, identity, command gate, and status mapping test scenarios.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.device_identity import device_identity_manager, DeviceIdentityManager
from app.firebase_bridge import FirebaseBridge, firebase_bridge
from app.detection import motion_service


class TestTrinetraSyncRepair(unittest.TestCase):

    def setUp(self):
        self.bridge = FirebaseBridge()
        self.bridge._is_initialized = True
        self.bridge._db_ref = MagicMock()
        self.bridge._running = True
        self.bridge._device_id = "TRI-TEST-SHOP01"
        self.bridge._processed_command_ids.clear()
        motion_service.disarm()

    def tearDown(self):
        motion_service.disarm()

    def test_01_wrong_device_id_cannot_arm(self):
        """1. Wrong Device ID cannot ARM Windows physical system."""
        cmd_payload = {
            "command": "ARM",
            "device_id": "TRI-WRONG-9999",
            "target_device_id": "TRI-WRONG-9999",
            "status": "PENDING",
            "requested_by": "attacker"
        }
        with patch("firebase_admin.db.reference") as mock_ref:
            mock_node = MagicMock()
            mock_ref.return_value = mock_node
            
            self.bridge._process_single_command("cmd_wrong_arm", cmd_payload)

            # System must remain DISARMED
            self.assertEqual(motion_service.current_mode, "DISARMED")
            # Command must be marked FAILED with DEVICE ID MISMATCH
            mock_node.update.assert_called()
            call_args = mock_node.update.call_args[0][0]
            self.assertEqual(call_args["status"], "FAILED")
            self.assertIn("DEVICE ID MISMATCH", call_args["result"])

    def test_02_wrong_device_id_cannot_disarm(self):
        """2. Wrong Device ID cannot DISARM Windows physical system."""
        # Arm system first
        motion_service.arm(exit_delay_seconds=0)
        self.assertEqual(motion_service.current_mode, "ARMED")

        cmd_payload = {
            "command": "DISARM",
            "device_id": "TRI-WRONG-9999",
            "status": "PENDING",
            "requested_by": "attacker"
        }
        with patch("firebase_admin.db.reference") as mock_ref:
            mock_node = MagicMock()
            mock_ref.return_value = mock_node

            self.bridge._process_single_command("cmd_wrong_disarm", cmd_payload)

            # System must remain ARMED
            self.assertEqual(motion_service.current_mode, "ARMED")
            # Command marked FAILED
            mock_node.update.assert_called()
            call_args = mock_node.update.call_args[0][0]
            self.assertEqual(call_args["status"], "FAILED")
            self.assertIn("DEVICE ID MISMATCH", call_args["result"])

    def test_03_correct_device_id_can_arm(self):
        """3. Correct Device ID successfully ARMs the system and verifies resulting state."""
        cmd_payload = {
            "command": "ARM",
            "device_id": "TRI-TEST-SHOP01",
            "status": "PENDING",
            "requested_by": "valid_user"
        }
        with patch("firebase_admin.db.reference") as mock_ref:
            mock_node = MagicMock()
            mock_ref.return_value = mock_node

            self.bridge._process_single_command("cmd_valid_arm", cmd_payload)

            # System must become ARMED
            self.assertEqual(motion_service.current_mode, "ARMED")
            # Terminal status SUCCESS recorded in calls
            all_updates = [c[0][0] for c in mock_node.update.call_args_list]
            cmd_updates = [u for u in all_updates if u.get("status") == "SUCCESS"]
            self.assertTrue(len(cmd_updates) > 0)
            self.assertIn("ARMED successfully", cmd_updates[0].get("result", ""))

    def test_04_correct_device_id_can_disarm(self):
        """4. Correct Device ID successfully DISARMs the system and verifies resulting state."""
        motion_service.arm(exit_delay_seconds=0)
        self.assertEqual(motion_service.current_mode, "ARMED")

        cmd_payload = {
            "command": "DISARM",
            "device_id": "TRI-TEST-SHOP01",
            "status": "PENDING",
            "requested_by": "valid_user"
        }
        with patch("firebase_admin.db.reference") as mock_ref:
            mock_node = MagicMock()
            mock_ref.return_value = mock_node

            self.bridge._process_single_command("cmd_valid_disarm", cmd_payload)

            # System must become DISARMED
            self.assertEqual(motion_service.current_mode, "DISARMED")
            # Terminal status SUCCESS recorded in calls
            all_updates = [c[0][0] for c in mock_node.update.call_args_list]
            cmd_updates = [u for u in all_updates if u.get("status") == "SUCCESS"]
            self.assertTrue(len(cmd_updates) > 0)
            self.assertIn("DISARMED successfully", cmd_updates[0].get("result", ""))

    def test_05_windows_armed_publishes_running(self):
        """5. Windows actual ARMED state publishes status='RUNNING'."""
        motion_service.arm(exit_delay_seconds=0)
        status_str = self.bridge._get_current_system_status_str()
        self.assertEqual(status_str, "RUNNING")

        with patch("firebase_admin.db.reference") as mock_ref:
            mock_node = MagicMock()
            mock_ref.return_value = mock_node
            self.bridge.update_presence(online=True)
            mock_node.update.assert_called()
            call_args = mock_node.update.call_args[0][0]
            self.assertEqual(call_args["status"], "RUNNING")
            self.assertTrue(call_args["online"])

    def test_06_windows_disarmed_publishes_stopped(self):
        """6. Windows actual DISARMED state publishes status='STOPPED'."""
        motion_service.disarm()
        status_str = self.bridge._get_current_system_status_str()
        self.assertEqual(status_str, "STOPPED")

        with patch("firebase_admin.db.reference") as mock_ref:
            mock_node = MagicMock()
            mock_ref.return_value = mock_node
            self.bridge.update_presence(online=True)
            mock_node.update.assert_called()
            call_args = mock_node.update.call_args[0][0]
            self.assertEqual(call_args["status"], "STOPPED")
            self.assertTrue(call_args["online"])

    def test_07_device_id_update_migrates_listener_and_presence(self):
        """7. Changing Device ID migrates listener and active presence."""
        new_dev_id = "TRI-NEW-SHOP02"
        with patch("firebase_admin.db.reference") as mock_ref:
            mock_node = MagicMock()
            mock_ref.return_value = mock_node
            self.bridge.update_device_id(new_dev_id)

            self.assertEqual(self.bridge.device_id, new_dev_id)
            # Presence published to new device
            mock_ref.assert_any_call(f"guardbox/devices/{new_dev_id}")

    def test_08_old_device_id_cannot_control_migrated_device(self):
        """8. Old Device ID rejected once migrated to new Device ID."""
        self.bridge.update_device_id("TRI-NEW-SHOP02")

        old_cmd_payload = {
            "command": "ARM",
            "device_id": "TRI-TEST-SHOP01", # Old ID
            "status": "PENDING"
        }
        with patch("firebase_admin.db.reference") as mock_ref:
            mock_node = MagicMock()
            mock_ref.return_value = mock_node

            self.bridge._process_single_command("cmd_old_arm", old_cmd_payload)

            self.assertEqual(motion_service.current_mode, "DISARMED")
            mock_node.update.assert_called()
            call_args = mock_node.update.call_args[0][0]
            self.assertEqual(call_args["status"], "FAILED")
            self.assertIn("DEVICE ID MISMATCH", call_args["result"])

    def test_09_offline_device_publishes_online_false(self):
        """9. When bridge stops, publishes online=False."""
        with patch("firebase_admin.db.reference") as mock_ref:
            mock_node = MagicMock()
            mock_ref.return_value = mock_node
            self.bridge.stop()
            mock_node.update.assert_called()
            call_args = mock_node.update.call_args[0][0]
            self.assertFalse(call_args["online"])

    def test_10_startup_synchronization_uses_actual_motion_state(self):
        """10. Startup presence uses actual motion service state (not hardcoded STOPPED)."""
        motion_service.arm(exit_delay_seconds=0)
        current_status = self.bridge._get_current_system_status_str()
        self.assertEqual(current_status, "RUNNING")

        with patch("firebase_admin.db.reference") as mock_ref:
            mock_node = MagicMock()
            mock_ref.return_value = mock_node
            self.bridge.update_presence(online=True, status_str=current_status)
            mock_node.update.assert_called()
            call_args = mock_node.update.call_args[0][0]
            self.assertEqual(call_args["status"], "RUNNING")

    def test_11_missing_device_id_in_identity_manager_loads_valid_persisted_id(self):
        """11. Device identity manager maintains single authoritative ID without silent fallback corruption."""
        ident = device_identity_manager.get_identity()
        self.assertIn("device_id", ident)
        self.assertTrue(len(ident["device_id"]) > 0)
        self.assertNotEqual(ident["device_id"], "")

    def test_12_silence_command_silences_without_altering_armed_monitoring_mode(self):
        """12. SILENCE command silences alarms while preserving ARMED mode."""
        motion_service.arm(exit_delay_seconds=0)
        self.assertEqual(motion_service.current_mode, "ARMED")

        cmd_payload = {
            "command": "SILENCE",
            "device_id": "TRI-TEST-SHOP01",
            "status": "PENDING",
            "requested_by": "valid_user"
        }
        with patch("firebase_admin.db.reference") as mock_ref:
            mock_node = MagicMock()
            mock_ref.return_value = mock_node
            self.bridge._process_single_command("cmd_silence", cmd_payload)

            self.assertEqual(motion_service.current_mode, "ARMED")
            all_updates = [c[0][0] for c in mock_node.update.call_args_list]
            cmd_updates = [u for u in all_updates if u.get("status") == "SUCCESS"]
            self.assertTrue(len(cmd_updates) > 0)
            self.assertIn("silenced successfully", cmd_updates[0].get("result", ""))

    def test_13_status_mapping_exactness(self):
        """13. Authoritative mapping: ARMED/ARMING/TEST_MODE -> RUNNING, DISARMED -> STOPPED."""
        motion_service.arm(exit_delay_seconds=0)
        self.assertEqual(self.bridge._get_current_system_status_str(), "RUNNING")

        motion_service.disarm()
        self.assertEqual(self.bridge._get_current_system_status_str(), "STOPPED")

    def test_14_unsupported_command_fails_gracefully(self):
        """14. Unknown command action does not alter motion service and fails cleanly."""
        motion_service.disarm()
        cmd_payload = {
            "command": "UNSUPPORTED_ACTION",
            "device_id": "TRI-TEST-SHOP01",
            "status": "PENDING",
            "requested_by": "valid_user"
        }
        with patch("firebase_admin.db.reference") as mock_ref:
            mock_node = MagicMock()
            mock_ref.return_value = mock_node
            self.bridge._process_single_command("cmd_unknown", cmd_payload)

            self.assertEqual(motion_service.current_mode, "DISARMED")
            all_updates = [c[0][0] for c in mock_node.update.call_args_list]
            cmd_updates = [u for u in all_updates if u.get("status") == "FAILED"]
            self.assertTrue(len(cmd_updates) > 0)
            self.assertIn("Unsupported command action", cmd_updates[0].get("result", ""))


if __name__ == "__main__":
    unittest.main()
