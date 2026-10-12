"""
Veronic GuardBox - Robust Multi-Camera & Multi-Zone Motion Detection Service (Phase 2)
Provides dual-layer noise-resistant motion analysis, precise polygon/rectangle zone masking,
minimum motion percentage thresholds, consecutive-frame temporal validation (eliminates false single-frame glitches),
startup calibration baseline, and comprehensive live debug telemetry.
"""

import os
import time
import uuid
import threading
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Tuple
import cv2
import numpy as np

from app.config import settings
from app.camera import camera_manager
from app.database import (
    create_security_event,
    log_system_event,
    get_zones_by_camera,
    get_all_zones,
    get_all_cameras
)
from app.alarm import alarm_service
from app.notifications import notification_service
from app.push.escalation import push_escalation_service

logger = logging.getLogger("guardbox.detection")

DEFAULT_REQUIRED_CONSECUTIVE_FRAMES = 3
DEFAULT_CALIBRATION_FRAMES = 20
DEFAULT_COOLDOWN_SECONDS = 8.0
DEFAULT_PIXEL_DIFF_THRESHOLD = 28


class CameraMotionDetector:
    """Independent noise-resistant motion detector for a single camera worker."""

    def __init__(self, camera_id: int, camera_name: str):
        self.camera_id = camera_id
        self.camera_name = camera_name

        self._lock = threading.RLock()
        
        # Background model & calibration
        self._bg_model: Optional[np.ndarray] = None
        self._calibration_count: int = 0
        self._required_calibration: int = DEFAULT_CALIBRATION_FRAMES
        self._last_frame_shape: Optional[Tuple[int, int]] = None
        self._is_calibrated: bool = False

        # Per-zone temporal validation & cooldown: zone_id -> state
        self._zone_consecutive_frames: Dict[int, int] = {}
        self._zone_cooldowns: Dict[int, float] = {}
        self._zone_debug_stats: Dict[int, Dict[str, Any]] = {}

        # Full frame temporal validation & cooldown
        self._full_frame_consecutive: int = 0
        self._full_frame_cooldown: float = 0.0
        self._full_frame_debug: Dict[str, Any] = {}

        # Snapshot evidence directory
        self._snapshot_dir = settings.SNAPSHOT_DIRECTORY
        os.makedirs(self._snapshot_dir, exist_ok=True)

    def reset_baseline(self) -> None:
        """Reset background model to force recalibration (e.g. on stream reconnect)."""
        with self._lock:
            self._bg_model = None
            self._calibration_count = 0
            self._is_calibrated = False
            self._zone_consecutive_frames.clear()
            self._full_frame_consecutive = 0
            logger.info(f"Motion detector #{self.camera_id} ('{self.camera_name}') baseline reset for recalibration")

    def process_frame(
        self,
        frame: Optional[np.ndarray],
        timestamp_iso: Optional[str] = None,
        mode: str = "ARMED"
    ) -> None:
        """Analyze frame across all enabled zones with strict noise filtering and consecutive frame confirmation."""
        if frame is None or frame.size == 0:
            return

        now_epoch = time.time()
        h, w = frame.shape[:2]
        if h < 60 or w < 60:
            return

        # Check for resolution changes
        with self._lock:
            if self._last_frame_shape != (h, w):
                self._last_frame_shape = (h, w)
                self._bg_model = None
                self._calibration_count = 0
                self._is_calibrated = False

        # Preprocessing: Grayscale + 9x9 Gaussian blur to eliminate high-frequency sensor & compression noise
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (9, 9), 0)

        # Baseline Calibration Phase
        with self._lock:
            if self._bg_model is None:
                self._bg_model = blurred.astype("float")
                self._calibration_count = 1
                self._is_calibrated = False
                return

            if self._calibration_count < self._required_calibration:
                cv2.accumulateWeighted(blurred, self._bg_model, 0.15)
                self._calibration_count += 1
                self._is_calibrated = False
                return

            self._is_calibrated = True

            # Compute difference against stable background accumulator
            bg_uint8 = cv2.convertScaleAbs(self._bg_model)
            frame_diff = cv2.absdiff(blurred, bg_uint8)

            # Threshold the difference image
            _, diff_thresh = cv2.threshold(frame_diff, DEFAULT_PIXEL_DIFF_THRESHOLD, 255, cv2.THRESH_BINARY)

            # Morphological noise removal:
            # 1. Opening (3x3) removes isolated noise pixels and compression block flicker
            # 2. Dilate (5x5) consolidates true moving contours
            kernel_open = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
            kernel_dilate = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
            clean_mask = cv2.morphologyEx(diff_thresh, cv2.MORPH_OPEN, kernel_open, iterations=1)
            clean_mask = cv2.dilate(clean_mask, kernel_dilate, iterations=1)

            # Adapt background model slowly (0.02) to adjust to ambient lighting changes
            cv2.accumulateWeighted(blurred, self._bg_model, 0.02)

        # Fetch configured zones for this camera
        zones = get_zones_by_camera(self.camera_id)
        enabled_zones = [z for z in zones if z.get("enabled")]

        if enabled_zones:
            for z in enabled_zones:
                self._evaluate_single_zone(
                    frame=frame,
                    clean_mask=clean_mask,
                    zone=z,
                    timestamp_iso=timestamp_iso,
                    mode=mode,
                    now_epoch=now_epoch,
                    frame_w=w,
                    frame_h=h
                )
        elif not zones:
            # ONLY evaluate full frame if NO zones are defined at all for this camera.
            # If zones are configured on this camera but are all disabled, do not trigger alerts on disabled areas.
            self._evaluate_full_frame(
                frame=frame,
                clean_mask=clean_mask,
                timestamp_iso=timestamp_iso,
                mode=mode,
                now_epoch=now_epoch,
                frame_w=w,
                frame_h=h
            )

    def _evaluate_single_zone(
        self,
        frame: np.ndarray,
        clean_mask: np.ndarray,
        zone: Dict[str, Any],
        timestamp_iso: Optional[str],
        mode: str,
        now_epoch: float,
        frame_w: int,
        frame_h: int
    ) -> None:
        """Evaluate motion strictly inside the specified polygon/rectangle zone mask."""
        zone_id = zone["id"]
        zone_name = zone.get("name", f"Zone {zone_id}")
        sensitivity = int(zone.get("sensitivity", 35))
        min_contour_area = max(150, int(zone.get("minimum_motion_area", 350)))
        cooldown_duration = float(zone.get("cooldown_seconds", DEFAULT_COOLDOWN_SECONDS))

        # Build clean binary mask matching the frame dimensions
        zone_mask = np.zeros((frame_h, frame_w), dtype=np.uint8)

        # Check for polygon points or rectangular bounding box
        polygon_points = zone.get("polygon_points") or zone.get("points")
        if polygon_points and isinstance(polygon_points, list) and len(polygon_points) >= 3:
            pts = []
            for p in polygon_points:
                if isinstance(p, (list, tuple)) and len(p) >= 2:
                    px = int(max(0.0, min(1.0, float(p[0]))) * frame_w)
                    py = int(max(0.0, min(1.0, float(p[1]))) * frame_h)
                    pts.append([px, py])
            if len(pts) >= 3:
                cv2.fillPoly(zone_mask, [np.array(pts, dtype=np.int32)], 255)
        else:
            zx = int(max(0.0, min(1.0, float(zone.get("x", 0.0)))) * frame_w)
            zy = int(max(0.0, min(1.0, float(zone.get("y", 0.0)))) * frame_h)
            zw = int(max(0.01, min(1.0 - float(zone.get("x", 0.0)), float(zone.get("width", 0.5)))) * frame_w)
            zh = int(max(0.01, min(1.0 - float(zone.get("y", 0.0)), float(zone.get("height", 0.5)))) * frame_h)
            cv2.rectangle(zone_mask, (zx, zy), (zx + zw, zy + zh), 255, -1)

        zone_pixels = cv2.countNonZero(zone_mask)
        if zone_pixels < 100:
            return

        # Restrict motion difference strictly to inside the zone mask
        zone_motion = cv2.bitwise_and(clean_mask, clean_mask, mask=zone_mask)
        changed_pixels = cv2.countNonZero(zone_motion)
        motion_pct = round((changed_pixels / float(zone_pixels)) * 100.0, 3)

        # Find external contours inside zone
        contours, _ = cv2.findContours(zone_motion, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        valid_contours = []
        significant_boxes = []
        max_contour_area = 0.0

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area >= min_contour_area:
                valid_contours.append(cnt)
                bx, by, bw, bh = cv2.boundingRect(cnt)
                significant_boxes.append((bx, by, bw, bh))
                if area > max_contour_area:
                    max_contour_area = area

        # Dynamic sensitivity thresholds
        # Sensitivity 1-100: higher sensitivity lowers required percentage slightly, but always requires substantial real movement
        required_motion_pct = max(0.4, 2.0 - (sensitivity * 0.015))
        required_consecutive = DEFAULT_REQUIRED_CONSECUTIVE_FRAMES

        # Check cooldown
        last_event_epoch = self._zone_cooldowns.get(zone_id, 0.0)
        in_cooldown = (now_epoch - last_event_epoch) < cooldown_duration
        cooldown_remaining = max(0.0, round(cooldown_duration - (now_epoch - last_event_epoch), 1)) if in_cooldown else 0.0

        # Motion Qualification Logic
        has_qualifying_motion = (
            motion_pct >= required_motion_pct and
            len(valid_contours) > 0 and
            max_contour_area >= min_contour_area
        )

        with self._lock:
            current_consecutive = self._zone_consecutive_frames.get(zone_id, 0)
            if has_qualifying_motion:
                current_consecutive += 1
            else:
                current_consecutive = 0
            self._zone_consecutive_frames[zone_id] = current_consecutive

            # Diagnostic telemetry
            if in_cooldown:
                detection_state = "COOLDOWN"
                trigger_reason = f"Event recorded. Cooling down ({cooldown_remaining}s remaining)"
            elif current_consecutive >= required_consecutive:
                detection_state = "MOTION_CONFIRMED"
                trigger_reason = f"Movement confirmed: {motion_pct}% area, max contour {int(max_contour_area)}px ({current_consecutive}/{required_consecutive} frames)"
            elif current_consecutive > 0:
                detection_state = "VERIFYING_CONSECUTIVE"
                trigger_reason = f"Verifying movement: frame {current_consecutive}/{required_consecutive}"
            else:
                detection_state = "MONITORING"
                trigger_reason = "No movement inside zone"

            self._zone_debug_stats[zone_id] = {
                "zone_id": zone_id,
                "zone_name": zone_name,
                "zone_pixels": zone_pixels,
                "changed_pixels": changed_pixels,
                "motion_percentage": motion_pct,
                "required_motion_percentage": round(required_motion_pct, 2),
                "largest_contour_area": round(max_contour_area, 1),
                "min_contour_area": min_contour_area,
                "consecutive_frames": current_consecutive,
                "required_consecutive_frames": required_consecutive,
                "in_cooldown": in_cooldown,
                "cooldown_remaining_seconds": cooldown_remaining,
                "detection_state": detection_state,
                "last_trigger_reason": trigger_reason
            }

        # Trigger event ONLY when motion is confirmed for consecutive frames and not in cooldown
        if current_consecutive >= required_consecutive and not in_cooldown:
            with self._lock:
                self._zone_cooldowns[zone_id] = now_epoch
                self._zone_consecutive_frames[zone_id] = 0

            print(f"[BACKEND LOG] MOTION CONFIRMED: Camera #{self.camera_id} in Zone '{zone_name}' ({motion_pct}%, {int(max_contour_area)}px)")
            self._record_motion_event(
                frame=frame,
                motion_area=max_contour_area,
                bounding_boxes=significant_boxes,
                matched_zone=zone,
                timestamp_iso=timestamp_iso,
                mode=mode,
                now_epoch=now_epoch
            )

    def _evaluate_full_frame(
        self,
        frame: np.ndarray,
        clean_mask: np.ndarray,
        timestamp_iso: Optional[str],
        mode: str,
        now_epoch: float,
        frame_w: int,
        frame_h: int
    ) -> None:
        """Fallback evaluation for full-frame monitoring when no zones are created."""
        total_pixels = frame_w * frame_h
        changed_pixels = cv2.countNonZero(clean_mask)
        motion_pct = round((changed_pixels / float(total_pixels)) * 100.0, 3)

        min_contour_area = settings.MIN_MOTION_AREA
        contours, _ = cv2.findContours(clean_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        valid_contours = []
        significant_boxes = []
        max_contour_area = 0.0

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area >= min_contour_area:
                valid_contours.append(cnt)
                bx, by, bw, bh = cv2.boundingRect(cnt)
                significant_boxes.append((bx, by, bw, bh))
                if area > max_contour_area:
                    max_contour_area = area

        required_motion_pct = 0.6
        required_consecutive = DEFAULT_REQUIRED_CONSECUTIVE_FRAMES
        cooldown_duration = settings.MOTION_COOLDOWN_SECONDS

        in_cooldown = (now_epoch - self._full_frame_cooldown) < cooldown_duration
        has_qualifying_motion = (
            motion_pct >= required_motion_pct and
            len(valid_contours) > 0 and
            max_contour_area >= min_contour_area
        )

        with self._lock:
            if has_qualifying_motion:
                self._full_frame_consecutive += 1
            else:
                self._full_frame_consecutive = 0

            current_consecutive = self._full_frame_consecutive

            self._full_frame_debug = {
                "zone_id": None,
                "zone_name": "Full View (No Zones)",
                "zone_pixels": total_pixels,
                "changed_pixels": changed_pixels,
                "motion_percentage": motion_pct,
                "required_motion_percentage": required_motion_pct,
                "largest_contour_area": round(max_contour_area, 1),
                "min_contour_area": min_contour_area,
                "consecutive_frames": current_consecutive,
                "required_consecutive_frames": required_consecutive,
                "in_cooldown": in_cooldown,
                "detection_state": "COOLDOWN" if in_cooldown else ("MOTION_CONFIRMED" if current_consecutive >= required_consecutive else "MONITORING"),
                "last_trigger_reason": "Full frame motion analysis"
            }

        if current_consecutive >= required_consecutive and not in_cooldown:
            with self._lock:
                self._full_frame_cooldown = now_epoch
                self._full_frame_consecutive = 0

            self._record_motion_event(
                frame=frame,
                motion_area=max_contour_area,
                bounding_boxes=significant_boxes,
                matched_zone=None,
                timestamp_iso=timestamp_iso,
                mode=mode,
                now_epoch=now_epoch
            )

    def _record_motion_event(
        self,
        frame: np.ndarray,
        motion_area: float,
        bounding_boxes: List[Tuple[int, int, int, int]],
        matched_zone: Optional[Dict[str, Any]],
        timestamp_iso: Optional[str],
        mode: str,
        now_epoch: float
    ) -> None:
        """Annotate snapshot, save evidence to SQLite, trigger simulated alarm, and broadcast."""
        now_iso = timestamp_iso or datetime.now(timezone.utc).isoformat()
        event_type = "TEST_EVENT" if mode == "TEST_MODE" else "MOTION_DETECTED"
        prefix = "test" if mode == "TEST_MODE" else "event"
        snapshot_filename = f"{prefix}_cam{self.camera_id}_{int(now_epoch)}_{uuid.uuid4().hex[:6]}.jpg"
        snapshot_rel_path = f"snapshots/{snapshot_filename}"
        snapshot_full_path = os.path.join(self._snapshot_dir, snapshot_filename)

        annotated_frame = frame.copy()
        h, w = frame.shape[:2]

        # Draw Zone outline
        if matched_zone:
            polygon_points = matched_zone.get("points") or matched_zone.get("polygon_points")
            if polygon_points and isinstance(polygon_points, list) and len(polygon_points) >= 3:
                pts = [
                    [int(float(p[0]) * w), int(float(p[1]) * h)]
                    for p in polygon_points if isinstance(p, (list, tuple)) and len(p) >= 2
                ]
                if len(pts) >= 3:
                    cv2.polylines(annotated_frame, [np.array(pts, dtype=np.int32)], True, (255, 165, 0), 2)
                    min_x = min(pt[0] for pt in pts)
                    min_y = min(pt[1] for pt in pts)
                    label_x = max(10, min_x + 5)
                    label_y = max(25, min_y - 8)
                else:
                    label_x, label_y = 30, 30
            else:
                zx = int(matched_zone.get("x", 0.0) * w)
                zy = int(matched_zone.get("y", 0.0) * h)
                zw = int(matched_zone.get("width", 0.5) * w)
                zh = int(matched_zone.get("height", 0.5) * h)
                cv2.rectangle(annotated_frame, (zx, zy), (zx + zw, zy + zh), (255, 165, 0), 2)
                label_x = max(10, zx + 5)
                label_y = max(25, zy - 8)

            zname = matched_zone.get("name", "Zone")
            cv2.putText(
                annotated_frame,
                f"ZONE: {zname}",
                (label_x, label_y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 165, 0),
                2,
                cv2.LINE_AA
            )

        # Draw motion bounding boxes
        box_color = (0, 255, 255) if mode == "TEST_MODE" else (34, 87, 255)
        for (bx, by, bw, bh) in bounding_boxes:
            cv2.rectangle(annotated_frame, (bx, by), (bx + bw, by + bh), box_color, 2)

        # Watermark
        mode_tag = f"[{mode}]"
        zone_tag = f" (Zone: {matched_zone['name']})" if matched_zone else ""
        cv2.putText(
            annotated_frame,
            f"GUARD BOX [{self.camera_name}] {mode_tag} {event_type}{zone_tag} - {now_iso}",
            (16, 26),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 0, 255) if mode == "ARMED" else (0, 200, 255),
            2,
            cv2.LINE_AA
        )

        try:
            cv2.imwrite(snapshot_full_path, annotated_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        except Exception as e:
            logger.error(f"Failed to write snapshot image: {e}")
            snapshot_rel_path = None

        zone_id = matched_zone["id"] if matched_zone else None
        zone_name = matched_zone["name"] if matched_zone else None

        event_id = create_security_event(
            event_type=event_type,
            camera_id=self.camera_id,
            camera_name=self.camera_name,
            motion_area=float(motion_area),
            snapshot_path=snapshot_rel_path,
            notes=f"Motion detected on '{self.camera_name}'" + (f" in zone '{zone_name}'" if zone_name else ""),
            zone_id=zone_id,
            zone_name=zone_name,
            system_mode=mode,
            status="NEW",
            message=f"Motion detected on {self.camera_name}" + (f" ({zone_name})" if zone_name else "")
        )

        logger.info(f"Security event #{event_id} ({event_type}) recorded for Camera #{self.camera_id} ('{self.camera_name}')")

        # Trigger simulated alarm
        alarm_reason = f"{event_type} on {self.camera_name}" + (f" [{zone_name}]" if zone_name else "")
        alarm_service.trigger_simulated_alarm(reason=alarm_reason)

        # Broadcast notification
        notification_service.notify_security_event(
            event_id=event_id,
            event_type=event_type,
            motion_area=motion_area,
            timestamp=now_iso
        )

        # Trigger automatic Security Alert Escalation (if ARMED)
        if mode == "ARMED":
            try:
                push_escalation_service.handle_security_event(
                    camera_id=self.camera_id,
                    camera_name=self.camera_name,
                    event_type=event_type,
                    severity="HIGH",
                    motion_area=motion_area,
                    snapshot_path=snapshot_rel_path
                )
            except Exception as e:
                logger.error(f"Error triggering push escalation: {e}")

    def get_debug_diagnostics(self) -> Dict[str, Any]:
        """Return live motion telemetry for this camera's zones."""
        with self._lock:
            zone_stats = list(self._zone_debug_stats.values())
            return {
                "camera_id": self.camera_id,
                "camera_name": self.camera_name,
                "is_calibrated": self._is_calibrated,
                "calibration_frames": self._calibration_count,
                "required_calibration_frames": self._required_calibration,
                "zones": zone_stats if zone_stats else [self._full_frame_debug] if self._full_frame_debug else []
            }


# ==============================================================================
# Motion Detection Service (Supervisor)
# ==============================================================================

class MotionDetectionService:
    """Supervisor coordinating motion detection across all enabled cameras."""

    def __init__(self):
        self._lock = threading.RLock()
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # System Modes: "DISARMED", "ARMING", "ARMED", "TEST_MODE"
        self._mode: str = "DISARMED"
        self._arming_start_epoch: Optional[float] = None
        self._exit_delay_duration: float = float(settings.EXIT_DELAY_SECONDS)
        self._entry_delay_duration: float = float(settings.ENTRY_DELAY_SECONDS)

        # Camera detector instances mapped by camera_id
        self._detectors: Dict[int, CameraMotionDetector] = {}

        # Authoritative state change listeners (e.g., Firebase Cloud Bridge)
        self._state_change_listeners = []

    def register_state_change_listener(self, listener) -> None:
        """Register a callback (new_mode: str, prev_mode: str) invoked whenever system state changes."""
        with self._lock:
            if listener not in self._state_change_listeners:
                self._state_change_listeners.append(listener)

    def _notify_state_change(self, new_mode: str, prev_mode: str) -> None:
        """Notify all registered listeners of an authoritative system state change."""
        if new_mode == prev_mode:
            return
        status_str = "RUNNING" if new_mode in ("ARMED", "ARMING", "TEST_MODE") else "STOPPED"
        logger.info(
            f"[TRINETRA STATUS SOURCE]\n"
            f"source=WINDOWS_MOTION_SERVICE\n"
            f"status={status_str}\n"
            f"mode={new_mode}"
        )
        with self._lock:
            listeners = list(self._state_change_listeners)
        for listener in listeners:
            try:
                listener(new_mode, prev_mode)
            except Exception as e:
                logger.error(f"Error in state change listener: {e}", exc_info=True)

    @property
    def is_armed(self) -> bool:
        with self._lock:
            return self._mode in ("ARMED", "ARMING")

    @property
    def current_mode(self) -> str:
        with self._lock:
            return self._mode

    def is_active_monitoring(self) -> bool:
        with self._lock:
            return self._mode in ("ARMED", "TEST_MODE")

    def arm(self, exit_delay_seconds: Optional[int] = None) -> Dict[str, Any]:
        """Initiate arming with optional exit delay countdown."""
        delay = exit_delay_seconds if exit_delay_seconds is not None else self._exit_delay_duration
        with self._lock:
            prev_mode = self._mode
            if delay > 0:
                self._mode = "ARMING"
                self._arming_start_epoch = time.time()
                self._exit_delay_duration = float(delay)
                log_system_event("SYSTEM", f"Exit delay started ({delay}s) before arming")
            else:
                self._mode = "ARMED"
                self._arming_start_epoch = None
                log_system_event("SYSTEM", "System ARMED immediately by user")
            new_mode = self._mode

        if new_mode != prev_mode:
            self._notify_state_change(new_mode, prev_mode)
        return self.get_system_status()

    def cancel_arming(self) -> Dict[str, Any]:
        """Cancel an in-progress exit delay countdown."""
        with self._lock:
            prev_mode = self._mode
            if self._mode == "ARMING":
                self._mode = "DISARMED"
                self._arming_start_epoch = None
                log_system_event("SYSTEM", "Arming countdown cancelled by user")
            new_mode = self._mode

        if new_mode != prev_mode:
            self._notify_state_change(new_mode, prev_mode)
        return self.get_system_status()

    def disarm(self) -> Dict[str, Any]:
        """Disarm the security system immediately and silence alarms."""
        with self._lock:
            prev_mode = self._mode
            self._mode = "DISARMED"
            self._arming_start_epoch = None
            new_mode = self._mode

        alarm_service.stop_alarm()
        if prev_mode != "DISARMED":
            logger.info("GuardBox system DISARMED")
            log_system_event("SYSTEM", "System DISARMED by user")

        if new_mode != prev_mode:
            self._notify_state_change(new_mode, prev_mode)
        return self.get_system_status()

    def enter_test_mode(self) -> Dict[str, Any]:
        """Switch system into TEST_MODE (events recorded as TEST_EVENT)."""
        with self._lock:
            prev_mode = self._mode
            self._mode = "TEST_MODE"
            self._arming_start_epoch = None
            new_mode = self._mode

        log_system_event("SYSTEM", "System switched to TEST_MODE")
        if new_mode != prev_mode:
            self._notify_state_change(new_mode, prev_mode)
        return self.get_system_status()

    def exit_test_mode(self) -> Dict[str, Any]:
        return self.disarm()

    def set_mode(self, mode: str) -> Dict[str, Any]:
        """Explicitly switch system security mode."""
        mode_upper = str(mode).strip().upper()
        if mode_upper in ("ARMED", "HOME"):
            return self.arm(exit_delay_seconds=0)
        elif mode_upper == "TEST_MODE":
            return self.enter_test_mode()
        else:
            return self.disarm()

    def start(self) -> None:
        """Start the background motion analysis thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._detection_loop, name="GuardBoxMotionSupervisor", daemon=True)
        self._thread.start()
        logger.info("Motion detection supervisor thread started")

    def stop(self) -> None:
        """Stop background motion analysis thread."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.5)
        logger.info("Motion detection supervisor thread stopped")

    def remove_camera(self, camera_id: int) -> None:
        """Safely remove camera detector instance and clear its resources."""
        with self._lock:
            self._detectors.pop(camera_id, None)

    def _get_or_create_detector(self, camera_id: int, camera_name: str) -> CameraMotionDetector:
        with self._lock:
            if camera_id not in self._detectors:
                self._detectors[camera_id] = CameraMotionDetector(camera_id, camera_name)
            return self._detectors[camera_id]

    def _process_frame(self, frame: np.ndarray, timestamp_iso: Optional[str] = None, mode: str = "ARMED") -> None:
        """Direct frame evaluation method for unit tests & single-camera verification."""
        detector = self._get_or_create_detector(1, "Main Shop Camera")
        detector.process_frame(frame, timestamp_iso, mode)

    def _detection_loop(self) -> None:
        """Continuous analysis loop evaluating frames from all active camera workers."""
        while self._running:
            try:
                # 1. Check current mode & exit delay countdown
                mode_changed = False
                with self._lock:
                    mode = self._mode
                    prev_mode = mode
                    if mode == "ARMING" and self._arming_start_epoch:
                        elapsed = time.time() - self._arming_start_epoch
                        if elapsed >= self._exit_delay_duration:
                            self._mode = "ARMED"
                            mode = "ARMED"
                            self._arming_start_epoch = None
                            log_system_event("SYSTEM", "Exit delay expired. System is now ARMED")
                            mode_changed = True

                if mode_changed:
                    self._notify_state_change("ARMED", "ARMING")

                if mode not in ("ARMED", "TEST_MODE"):
                    time.sleep(0.15)
                    continue

                # 2. Iterate all active camera workers
                workers = camera_manager.get_all_workers()
                for worker in workers:
                    if not worker.enabled:
                        continue
                    if not worker.is_warmed_up():
                        continue

                    connected, frame, ts_iso = worker.get_latest_frame()
                    if not connected or frame is None:
                        continue

                    detector = self._get_or_create_detector(worker.camera_id, worker.name)
                    detector.process_frame(frame, ts_iso, mode)

                time.sleep(0.065)

            except Exception as e:
                logger.error(f"Exception in motion detection supervisor: {e}")
                time.sleep(0.4)

    def get_motion_debug_diagnostics(self, camera_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Return live motion telemetry for all detectors or specific camera."""
        with self._lock:
            if camera_id is not None:
                det = self._detectors.get(camera_id)
                return [det.get_debug_diagnostics()] if det else []
            return [d.get_debug_diagnostics() for d in self._detectors.values()]

    def get_settings(self) -> Dict[str, Any]:
        """Return safe system motion settings."""
        with self._lock:
            return {
                "motion_sensitivity": settings.MOTION_SENSITIVITY,
                "min_motion_area": settings.MIN_MOTION_AREA,
                "motion_cooldown_seconds": settings.MOTION_COOLDOWN_SECONDS,
                "motion_persistence_seconds": settings.MOTION_PERSISTENCE_SECONDS,
                "camera_warmup_seconds": settings.CAMERA_WARMUP_SECONDS,
                "blur_size": settings.BLUR_SIZE,
                "frame_scale": settings.FRAME_SCALE,
                "entry_delay_seconds": int(self._entry_delay_duration),
                "exit_delay_seconds": int(self._exit_delay_duration),
                "required_consecutive_frames": DEFAULT_REQUIRED_CONSECUTIVE_FRAMES,
                "calibration_frames": DEFAULT_CALIBRATION_FRAMES
            }

    def update_settings(
        self,
        sensitivity: Optional[int] = None,
        min_motion_area: Optional[int] = None,
        cooldown_seconds: Optional[float] = None,
        persistence_seconds: Optional[float] = None,
        warmup_seconds: Optional[float] = None,
        blur_size: Optional[int] = None,
        frame_scale: Optional[float] = None,
        entry_delay_seconds: Optional[int] = None,
        exit_delay_seconds: Optional[int] = None
    ) -> Dict[str, Any]:
        with self._lock:
            if entry_delay_seconds is not None:
                self._entry_delay_duration = max(0, entry_delay_seconds)
            if exit_delay_seconds is not None:
                self._exit_delay_duration = max(0, exit_delay_seconds)

        return self.get_settings()

    # Aliases for compatibility
    get_parameters = get_settings
    update_parameters = update_settings

    def get_status(self) -> Dict[str, Any]:
        return self.get_system_status()

    def get_system_status(self) -> Dict[str, Any]:
        """Consolidated system status with cameras summary and mode state."""
        cam_statuses = camera_manager.get_all_statuses()
        primary_cam = camera_manager.get_primary_worker()
        primary_status = primary_cam.get_status() if primary_cam else {
            "connected": False,
            "camera_ip": settings.get_safe_camera_ip(),
            "camera_model": settings.CAMERA_MODEL,
            "fps": 0.0,
            "warmed_up": False
        }
        alarm_status = alarm_service.get_status()

        with self._lock:
            mode = self._mode
            exit_countdown_remaining = 0

            if mode == "ARMING" and self._arming_start_epoch:
                elapsed = time.time() - self._arming_start_epoch
                remaining = max(0.0, self._exit_delay_duration - elapsed)
                if remaining <= 0:
                    self._mode = "ARMED"
                    mode = "ARMED"
                    self._arming_start_epoch = None
                else:
                    exit_countdown_remaining = int(remaining)

            any_cam_connected = any(c.get("connected", False) for c in cam_statuses)
            motion_enabled = (mode in ("ARMED", "TEST_MODE")) and any_cam_connected

            return {
                "system_mode": mode,
                "armed": mode == "ARMED",
                "is_arming": mode == "ARMING",
                "is_test_mode": mode == "TEST_MODE",
                "exit_countdown_remaining": exit_countdown_remaining,
                "camera_connected": primary_status.get("connected", False),
                "camera_ip": primary_status.get("camera_ip", "192.168.31.108"),
                "camera_model": primary_status.get("camera_model", "Tapo C100"),
                "camera_health": {
                    "fps": primary_status.get("fps", 0),
                    "warmed_up": primary_status.get("warmed_up", False),
                    "reconnect_count": primary_status.get("reconnect_count", 0),
                    "consecutive_failures": primary_status.get("consecutive_failures", 0)
                },
                "cameras": cam_statuses,
                "motion_detection_enabled": motion_enabled,
                "alarm_simulation": alarm_status
            }

    def get_detection_health(self) -> Dict[str, Any]:
        """Return diagnostic health information for detection monitoring."""
        workers = camera_manager.get_all_workers()
        cams_info = []
        with self._lock:
            mode = self._mode
            is_armed = mode in ("ARMED", "TEST_MODE")
            is_running = self._running and (self._thread is not None and self._thread.is_alive())

        for w in workers:
            connected, frame, _ = w.get_latest_frame()
            has_frame = connected and (frame is not None)
            cams_info.append({
                "id": w.camera_id,
                "name": w.name,
                "connected": w._connected,
                "frame_capture": has_frame,
                "warmed_up": w.is_warmed_up(),
                "fps": w._current_fps,
                "detection_worker": is_running,
                "detection_enabled": w.enabled
            })

        return {
            "status": "running" if is_running else "stopped",
            "system_mode": mode,
            "is_armed": is_armed,
            "cameras": cams_info
        }


# Global motion detection service singleton
motion_service = MotionDetectionService()
