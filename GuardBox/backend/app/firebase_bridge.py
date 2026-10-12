"""
Veronic GuardBox - Firebase Cloud Bridge (Phase 2: Remote Command Relay)
Manages Firebase Admin SDK initialization, persistent device identity,
Realtime Database presence (guardbox/devices/{device_id}), and
idempotent remote command execution (guardbox/commands/{device_id}/pending).
"""

import os
import json
import uuid
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, Set

from app.config import settings, BASE_DIR

logger = logging.getLogger("guardbox.firebase_bridge")

# Data directory for persistent identity and processed command IDs
DATA_DIR = BASE_DIR / "data"
IDENTITY_FILE = DATA_DIR / "device_identity.json"
PROCESSED_COMMANDS_FILE = DATA_DIR / "processed_commands.json"


class FirebaseBridge:
    def __init__(self):
        self._app: Optional[Any] = None
        self._db_ref: Optional[Any] = None
        self._device_id: str = ""
        self._is_initialized: bool = False
        self._running: bool = False
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._command_poller_thread: Optional[threading.Thread] = None
        self._listener_stream: Optional[Any] = None
        self._lock = threading.Lock()
        self._processed_lock = threading.Lock()

        # In-memory and persistent idempotent command tracking
        self._processed_command_ids: Set[str] = set()

        # Load persistent Device ID and processed command history
        self._device_id = self._load_or_create_device_id()
        self._load_processed_commands()

    @property
    def device_id(self) -> str:
        return self._device_id

    @property
    def is_active(self) -> bool:
        return self._is_initialized and self._running

    def _load_or_create_device_id(self) -> str:
        """Load persistent device_id from device_identity_manager."""
        from app.device_identity import device_identity_manager
        ident = device_identity_manager.load_identity()
        return ident["device_id"]

    def _load_processed_commands(self) -> None:
        """Load previously executed command IDs from disk to prevent duplicate execution on restart."""
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            if PROCESSED_COMMANDS_FILE.exists():
                with open(PROCESSED_COMMANDS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    ids = data.get("processed_ids", [])
                    with self._processed_lock:
                        self._processed_command_ids = set(ids)
                logger.info(f"Loaded {len(self._processed_command_ids)} processed command IDs for idempotency protection")
        except Exception as e:
            logger.warning(f"Could not load processed commands file: {e}")

    def _save_processed_command(self, command_id: str) -> None:
        """Persist processed command ID to disk."""
        with self._processed_lock:
            self._processed_command_ids.add(command_id)
            # Prune old IDs if set gets excessively large (keep last 1000)
            id_list = list(self._processed_command_ids)
            if len(id_list) > 1000:
                id_list = id_list[-1000:]
                self._processed_command_ids = set(id_list)

        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            with open(PROCESSED_COMMANDS_FILE, "w", encoding="utf-8") as f:
                json.dump({"processed_ids": id_list, "updated_at": datetime.now(timezone.utc).isoformat()}, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not persist processed command ID {command_id}: {e}")

    def initialize(self) -> bool:
        """Initialize Firebase Admin SDK with service account credentials."""
        with self._lock:
            if self._is_initialized:
                return True

            cred_path = getattr(settings, "resolved_firebase_credentials_path", settings.FIREBASE_CREDENTIALS_PATH) or settings.FIREBASE_CREDENTIALS_PATH
            db_url = settings.FIREBASE_DATABASE_URL

            if not cred_path or not os.path.exists(cred_path):
                logger.info(
                    "Firebase Admin credentials not configured or file not found "
                    "(FIREBASE_CREDENTIALS_PATH). Firebase Cloud Bridge running in standby mode."
                )
                return False

            try:
                import firebase_admin
                from firebase_admin import credentials, db

                cred = credentials.Certificate(cred_path)
                options = {}
                if db_url:
                    options["databaseURL"] = db_url

                # Initialize default Firebase app if not already initialized
                if not firebase_admin._apps:
                    self._app = firebase_admin.initialize_app(cred, options)
                else:
                    self._app = firebase_admin.get_app()

                self._db_ref = db.reference()
                self._is_initialized = True
                logger.info(f"Firebase Admin SDK initialized successfully for GuardBox Device: {self._device_id}")
                return True
            except Exception as e:
                logger.error(f"Failed to initialize Firebase Admin SDK: {e}", exc_info=True)
                return False

    def start(self) -> None:
        """Start Firebase presence registration, command listener, and heartbeat loop."""
        if not self._is_initialized:
            if not self.initialize():
                return

        with self._lock:
            if self._running:
                return
            self._running = True

        # Register authoritative state change listener with motion supervisor
        try:
            from app.detection import motion_service
            motion_service.register_state_change_listener(self._on_motion_service_state_change)
            logger.info("Registered Firebase bridge state change listener with motion_service")
        except Exception as e:
            logger.warning(f"Could not register motion_service state change listener: {e}")

        # Initial presence registration with current Windows system status
        current_status = self._get_current_system_status_str()
        try:
            from app.detection import motion_service
            raw_state = motion_service.current_mode
        except Exception:
            raw_state = "DISARMED"
        logger.info(
            f"[TRINETRA DEVICE]\n"
            f"device_id={self._device_id}\n"
            f"state={raw_state}\n"
            f"firebase_status={current_status}"
        )
        self.update_presence(online=True, status_str=current_status, async_publish=False)

        # Start 30-second heartbeat thread
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            daemon=True,
            name="guardbox-firebase-heartbeat"
        )
        self._heartbeat_thread.start()

        # Start Realtime Database Command Listener & Poller
        self._start_command_listener()
        logger.info("Firebase Cloud Bridge started (presence & remote command relay active)")

    def update_device_id(self, new_device_id: str) -> None:
        """Update active device_id, restart command listener on new path, and publish presence."""
        clean_id = new_device_id.strip()
        if not clean_id or clean_id == self._device_id:
            return

        logger.info(f"FirebaseBridge switching active Device ID: {self._device_id} -> {clean_id}")
        with self._lock:
            self._device_id = clean_id
            if self._listener_stream:
                try:
                    self._listener_stream.close()
                except Exception:
                    pass
                self._listener_stream = None

        if self._running and self._is_initialized:
            current_status = self._get_current_system_status_str()
            self.update_presence(online=True, status_str=current_status, async_publish=False)
            self._start_command_listener()

    def stop(self) -> None:
        """Gracefully stop command listeners, heartbeat, and mark device offline."""
        with self._lock:
            if not self._running:
                return
            self._running = False

        if self._listener_stream:
            try:
                self._listener_stream.close()
            except Exception:
                pass
            self._listener_stream = None

        try:
            current_status = self._get_current_system_status_str()
            self.update_presence(online=False, status_str=current_status, async_publish=False)
        except Exception as e:
            logger.warning(f"Error updating offline presence: {e}")
        logger.info("Firebase Cloud Bridge stopped")

    def _on_motion_service_state_change(self, new_mode: str, prev_mode: str) -> None:
        """Callback invoked whenever Windows motion_service changes state."""
        status_str = "RUNNING" if new_mode in ("ARMED", "ARMING", "TEST_MODE") else "STOPPED"
        logger.info(
            f"[TRINETRA DEVICE]\n"
            f"device_id={self._device_id}\n"
            f"state={new_mode}\n"
            f"firebase_status={status_str}"
        )
        self.update_presence(online=True, status_str=status_str, async_publish=True)

    def _get_current_system_status_str(self) -> str:
        """Determine whether system is currently RUNNING or STOPPED based on motion detector."""
        try:
            from app.detection import motion_service
            if motion_service.current_mode in ("ARMED", "ARMING", "TEST_MODE"):
                return "RUNNING"
        except Exception:
            pass
        return "STOPPED"

    def update_presence(self, online: bool = True, status_str: Optional[str] = None, async_publish: bool = False) -> None:
        """Update guardbox/devices/{device_id} node in Firebase Realtime Database."""
        if not self._is_initialized or self._db_ref is None:
            return

        def _do_update():
            try:
                from firebase_admin import db
                from app.device_identity import device_identity_manager
                ident = device_identity_manager.get_identity()
                device_node = db.reference(f"guardbox/devices/{self._device_id}")
                current_st = status_str if status_str is not None else self._get_current_system_status_str()
                payload = {
                    "name": ident.get("device_name", settings.GUARDBOX_DEVICE_NAME),
                    "shop_id": ident.get("shop_id", "SHOP-RK-001"),
                    "shop_name": ident.get("shop_name", "Rajkot Jewellery"),
                    "owner_id": ident.get("owner_id"),
                    "online": online,
                    "status": current_st,
                    "last_seen": datetime.now(timezone.utc).isoformat(),
                    "device_id": self._device_id,
                    "version": ident.get("version", "1.0.0"),
                    "registered": True
                }
                device_node.update(payload)

                # Maintain shop device index
                shop_id = ident.get("shop_id", "SHOP-RK-001")
                if shop_id and shop_id != "NOT_CONFIGURED":
                    db.reference(f"guardbox/shops/{shop_id}/devices/{self._device_id}").set(True)
                    db.reference(f"guardbox/shops/{shop_id}/shop_name").set(ident.get("shop_name", "Rajkot Jewellery"))
                logger.info(
                    f"[TRINETRA STATUS PUBLISH]\n"
                    f"device_id={self._device_id}\n"
                    f"status={current_st}\n"
                    f"online={online}"
                )
            except Exception as e:
                logger.warning(f"Failed to update Firebase Realtime Database presence: {e}")

        if async_publish:
            t = threading.Thread(target=_do_update, daemon=True, name="guardbox-presence-update")
            t.start()
        else:
            _do_update()

    def _heartbeat_loop(self) -> None:
        """Background thread updating last_seen timestamp and presence every 30 seconds."""
        while self._running:
            try:
                time.sleep(30)
                if self._running and self._is_initialized:
                    self.update_presence(online=True)
            except Exception as e:
                logger.debug(f"Firebase heartbeat cycle notice: {e}")

    # ==========================================================================
    # Remote Command Listener & Idempotent Execution Relay
    # ==========================================================================

    def _start_command_listener(self) -> None:
        """Launch SSE listener stream and backup polling worker for pending commands."""
        try:
            from firebase_admin import db
            cmd_ref = db.reference(f"guardbox/commands/{self._device_id}/pending")

            def on_command_event(event):
                if not self._running:
                    return
                try:
                    self._handle_firebase_command_event(event)
                except Exception as ex:
                    logger.error(f"Error handling Firebase command event: {ex}", exc_info=True)

            try:
                self._listener_stream = cmd_ref.listen(on_command_event)
                logger.info(f"Listening for remote commands on guardbox/commands/{self._device_id}/pending")
            except Exception as e:
                logger.warning(f"Firebase SSE stream listen notice (will rely on polling relay): {e}")

            # Background poller to catch any missed updates or re-connections
            self._command_poller_thread = threading.Thread(
                target=self._command_polling_loop,
                daemon=True,
                name="guardbox-firebase-command-poller"
            )
            self._command_poller_thread.start()

        except Exception as e:
            logger.error(f"Failed to initialize Firebase command listener: {e}", exc_info=True)

    def _command_polling_loop(self) -> None:
        """Periodic poller scanning for unhandled PENDING commands every 3 seconds."""
        while self._running:
            try:
                time.sleep(3)
                if not self._running or not self._is_initialized:
                    continue
                self._scan_and_process_pending_commands()
            except Exception as e:
                logger.debug(f"Firebase command poll cycle notice: {e}")

    def _scan_and_process_pending_commands(self) -> None:
        """Fetch pending command tree and process any unhandled PENDING commands."""
        if not self._is_initialized:
            return

        try:
            from firebase_admin import db
            cmd_ref = db.reference(f"guardbox/commands/{self._device_id}/pending")
            pending_data = cmd_ref.get()
            if isinstance(pending_data, dict):
                for cmd_id, cmd_payload in pending_data.items():
                    if isinstance(cmd_payload, dict):
                        self._process_single_command(cmd_id, cmd_payload)
        except Exception as e:
            logger.debug(f"Error scanning pending commands: {e}")

    def _handle_firebase_command_event(self, event) -> None:
        """Process incoming Firebase SSE stream event."""
        if event is None or event.data is None:
            return

        path = event.path or "/"
        data = event.data

        # Root level update (dictionary of commands)
        if path == "/" and isinstance(data, dict):
            for cmd_id, cmd_payload in data.items():
                if isinstance(cmd_payload, dict):
                    self._process_single_command(cmd_id, cmd_payload)
            return

        # Child update (e.g. /<command_id>)
        parts = [p for p in path.strip("/").split("/") if p]
        if len(parts) == 1:
            cmd_id = parts[0]
            if isinstance(data, dict):
                self._process_single_command(cmd_id, data)
        elif len(parts) > 1:
            # Subfield update on an existing command, trigger check
            cmd_id = parts[0]
            self._check_and_process_command_by_id(cmd_id)

    def _check_and_process_command_by_id(self, command_id: str) -> None:
        """Fetch and process a specific command node if status is PENDING."""
        with self._processed_lock:
            if command_id in self._processed_command_ids:
                return

        try:
            from firebase_admin import db
            ref = db.reference(f"guardbox/commands/{self._device_id}/pending/{command_id}")
            cmd_data = ref.get()
            if isinstance(cmd_data, dict):
                self._process_single_command(command_id, cmd_data)
        except Exception as e:
            logger.debug(f"Error fetching command {command_id}: {e}")

    def _process_single_command(self, command_id: str, cmd_data: Dict[str, Any], path_device_id: Optional[str] = None) -> None:
        """
        Execute an incoming command idempotently and update its terminal status in Firebase.
        Verifies Device ID, ensures exact-once execution, and updates authoritative device presence.
        """
        if not command_id or not isinstance(cmd_data, dict):
            return

        status = cmd_data.get("status", "").upper()

        # If already terminal in Firebase, record ID and skip
        if status in ("SUCCESS", "FAILED"):
            with self._processed_lock:
                self._processed_command_ids.add(command_id)
            return

        # Only process if status is PENDING
        if status != "PENDING":
            return

        # Idempotency check: has this command already been executed in this application session?
        with self._processed_lock:
            if command_id in self._processed_command_ids:
                logger.debug(f"Command '{command_id}' already processed. Skipping duplicate execution.")
                return
            # Mark processed locally immediately to prevent concurrent race conditions
            self._processed_command_ids.add(command_id)

        # Persist ID to disk for crash/restart recovery
        self._save_processed_command(command_id)

        # Requirement 4: Device ID Verification
        active_device_id = self._device_id
        cmd_target_id = (
            cmd_data.get("device_id")
            or cmd_data.get("target_device_id")
            or path_device_id
            or active_device_id
        )

        if str(cmd_target_id).strip() != active_device_id:
            logger.warning(
                f"[TRINETRA DEVICE MISMATCH]\n"
                f"configured={cmd_target_id}\n"
                f"actual={active_device_id}"
            )
            try:
                from firebase_admin import db
                target_cmd_ref = db.reference(f"guardbox/commands/{self._device_id}/pending/{command_id}")
                target_cmd_ref.update({
                    "status": "FAILED",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "result": f"DEVICE ID MISMATCH: Target '{cmd_target_id}' does not match physical device '{active_device_id}'"
                })
            except Exception as ex:
                logger.error(f"Failed to record rejected command status: {ex}")
            return

        command_type = str(cmd_data.get("command", "")).strip().upper()
        requested_by = cmd_data.get("requested_by", "unknown")
        created_at = cmd_data.get("created_at", "")

        logger.info(
            f"⚡ Processing Remote Command: ID={command_id}, Command={command_type}, "
            f"RequestedBy={requested_by}, CreatedAt={created_at}"
        )

        success = False
        result_message = ""
        new_status_str = None
        actual_state = "UNKNOWN"

        try:
            from app.detection import motion_service
            from app.alarm import alarm_service

            if command_type == "ARM":
                # START SYSTEM: Arm system immediately with 0s exit delay for remote actions
                motion_service.arm(exit_delay_seconds=0)
                actual_state = motion_service.current_mode
                success = actual_state in ("ARMED", "ARMING", "TEST_MODE")
                new_status_str = "RUNNING" if success else "STOPPED"
                result_message = "GuardBox security perimeter ARMED successfully" if success else "Failed to arm motion service"

            elif command_type == "DISARM":
                # STOP SYSTEM: Disarm security system and silence active alarms
                motion_service.disarm()
                actual_state = motion_service.current_mode
                success = actual_state not in ("ARMED", "ARMING", "TEST_MODE")
                new_status_str = "STOPPED" if success else "RUNNING"
                result_message = "GuardBox security perimeter DISARMED successfully" if success else "Failed to disarm motion service"

            elif command_type == "SILENCE":
                # SILENCE ALARM: Stop simulated siren while leaving monitoring state intact
                alarm_service.stop_alarm()
                actual_state = motion_service.current_mode
                new_status_str = "RUNNING" if actual_state in ("ARMED", "ARMING", "TEST_MODE") else "STOPPED"
                success = True
                result_message = "Active alarm silenced successfully"

            else:
                success = False
                result_message = f"Unsupported command action: {command_type}"
                actual_state = getattr(motion_service, "current_mode", "UNKNOWN")

        except Exception as e:
            success = False
            result_message = f"Command execution error: {str(e)}"
            try:
                from app.detection import motion_service
                actual_state = motion_service.current_mode
            except Exception:
                actual_state = "ERROR"

        # Diagnostic log for command result (Requirement 15)
        logger.info(
            f"[TRINETRA COMMAND]\n"
            f"device_id={self._device_id}\n"
            f"command={command_type}\n"
            f"result={'SUCCESS' if success else 'FAILED'}\n"
            f"actual_state={actual_state}"
        )

        # Update terminal status in Firebase Realtime Database
        terminal_status = "SUCCESS" if success else "FAILED"
        completed_at = datetime.now(timezone.utc).isoformat()

        try:
            from firebase_admin import db
            target_cmd_ref = db.reference(f"guardbox/commands/{self._device_id}/pending/{command_id}")
            update_payload = {
                "status": terminal_status,
                "completed_at": completed_at,
                "result": result_message
            }
            target_cmd_ref.update(update_payload)
            logger.info(f"Updated command '{command_id}' terminal status: {terminal_status} ({result_message})")
        except Exception as e:
            logger.error(f"Failed to update command '{command_id}' status in Firebase: {e}")

        # Update device presence status to immediately reflect changes to remote phones
        if new_status_str:
            try:
                self.update_presence(online=True, status_str=new_status_str)
            except Exception as e:
                logger.debug(f"Error updating presence after command: {e}")

    def upload_alert_snapshot(
        self,
        alert_id: str,
        local_snapshot_path: str,
        device_id: Optional[str] = None
    ) -> Optional[str]:
        """
        Legacy bridge method delegating evidence snapshot upload to SupabaseStorageService.
        Returns deterministic storage path string or None.
        """
        try:
            from app.supabase_storage import supabase_storage_service
            res = supabase_storage_service.upload_alert_snapshot(alert_id, local_snapshot_path, device_id)
            if res and isinstance(res, dict):
                return res.get("remote_reference")
            return None
        except Exception as e:
            logger.error(f"[TRINETRA REMOTE SNAPSHOT ERROR]\nalert_id={alert_id}\nreason={e}")
            return None

    def delete_alert_snapshot(
        self,
        alert_id: str,
        device_id: Optional[str] = None
    ) -> bool:
        """
        Legacy bridge method delegating remote evidence snapshot deletion to SupabaseStorageService.
        """
        try:
            from app.supabase_storage import supabase_storage_service
            return supabase_storage_service.delete_alert_snapshot(alert_id, device_id)
        except Exception as e:
            logger.warning(f"[TRINETRA REMOTE SNAPSHOT CLEANUP ERROR]\nalert_id={alert_id}\nreason={e}")
            return False


# Global Firebase Bridge Singleton
firebase_bridge = FirebaseBridge()


