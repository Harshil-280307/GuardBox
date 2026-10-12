"""
Veronic GuardBox - Multi-Camera RTSP Stream Worker & Manager (Phase 2)
Manages controlled background threads per enabled camera, automatic reconnection,
thread-safe frame sharing, real-time FPS/health metrics, and MJPEG live streaming.
Stops infinite reconnect loops with max 3 retries and exponential backoff.
Never exposes RTSP credentials in logs or API responses.
"""

import os
import time
import threading
import logging
import re
from urllib.parse import urlparse
from datetime import datetime, timezone
from typing import Optional, Tuple, Dict, Any, Generator, List
import cv2
import numpy as np

# Configure OpenCV FFmpeg backend to use TCP transport and 4s connection timeout
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|stimeout;4000000"

from app.config import settings
from app.database import (
    log_system_event,
    create_security_event,
    get_all_cameras,
    get_camera_by_id,
    create_camera,
    update_camera,
    delete_camera,
    toggle_camera
)

logger = logging.getLogger("guardbox.camera")

MAX_AUTO_RETRIES = 3
INITIAL_BACKOFF = 2.0
MAX_BACKOFF = 8.0


def parse_safe_ip(rtsp_url: str) -> str:
    """Extract host / IP from RTSP URL without credentials."""
    try:
        parsed = urlparse(rtsp_url)
        if parsed.hostname:
            return parsed.hostname
        match = re.search(r"@([^:/]+)", rtsp_url)
        if match:
            return match.group(1)
        match_no_auth = re.search(r"rtsp://([^:/]+)", rtsp_url)
        if match_no_auth:
            return match_no_auth.group(1)
    except Exception:
        pass
    return "192.168.31.108"


def mask_rtsp_url(rtsp_url: str) -> str:
    """Mask credentials in RTSP URL for safe internal logging."""
    try:
        parsed = urlparse(rtsp_url)
        if parsed.scheme and parsed.hostname:
            port_part = f":{parsed.port}" if parsed.port else ""
            path_part = parsed.path if parsed.path else ""
            return f"{parsed.scheme}://***:***@{parsed.hostname}{port_part}{path_part}"
    except Exception:
        pass
    return "rtsp://***:***@CAMERA/stream"


class CameraWorker:
    """Independent background RTSP capture worker for a single camera with controlled reconnects."""

    def __init__(
        self,
        camera_id: int,
        name: str,
        brand: str,
        model: str,
        rtsp_url: str,
        enabled: bool = True
    ):
        self.camera_id = camera_id
        self.name = name
        self.brand = brand
        self.model = model
        self._rtsp_url = rtsp_url
        self.enabled = enabled

        self._lock = threading.RLock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._retry_event = threading.Event()

        # Connectivity & Preview State
        self._connected = False
        self._preview_available = False
        self._latest_frame: Optional[np.ndarray] = None
        self._last_frame_time: Optional[float] = None
        self._last_frame_timestamp_iso: Optional[str] = None
        self._connect_time: Optional[float] = None
        
        # Controlled Reconnect Tracking
        self._retry_count = 0
        self._max_auto_retries = MAX_AUTO_RETRIES
        self._auto_retry_exhausted = False
        self._consecutive_failures = 0
        self._total_frames_received = 0
        self._last_error: Optional[str] = None

        # Separated Status Fields
        self._connection_status = "offline"  # online | offline | connecting
        self._preview_status = "stopped"      # live | preview_unavailable | connecting | stopped
        self._detection_status = "stopped"    # running | stopped

        # FPS metrics
        self._frame_count = 0
        self._fps_start_time = time.time()
        self._current_fps = 0.0

        # Outage tracking
        self._was_offline_event_triggered = False
        self._warmup_seconds = settings.CAMERA_WARMUP_SECONDS

    @property
    def safe_ip(self) -> str:
        return parse_safe_ip(self._rtsp_url)

    @property
    def sanitized_url(self) -> str:
        return mask_rtsp_url(self._rtsp_url)

    def start(self) -> None:
        """Start the background reading thread if enabled."""
        if not self.enabled:
            return
        if self._running:
            return
        self._running = True
        self._auto_retry_exhausted = False
        self._retry_count = 0
        self._retry_event.clear()
        self._thread = threading.Thread(
            target=self._capture_loop,
            name=f"GuardBoxCamWorker-{self.camera_id}",
            daemon=True
        )
        self._thread.start()
        logger.info(f"CameraWorker #{self.camera_id} ('{self.name}') started at {self.safe_ip}")
        log_system_event("CAMERA", f"Camera #{self.camera_id} ('{self.name}') worker started")

    def stop(self) -> None:
        """Gracefully stop background thread."""
        self._running = False
        self._retry_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        with self._lock:
            self._connected = False
            self._preview_available = False
            self._latest_frame = None
            self._connection_status = "offline"
            self._preview_status = "stopped"
            self._detection_status = "stopped"
        logger.info(f"CameraWorker #{self.camera_id} stopped")

    def update_config(self, name: str, brand: str, model: str, rtsp_url: str, enabled: bool) -> None:
        """Update runtime camera profile configuration."""
        url_changed = (self._rtsp_url != rtsp_url)
        enabled_changed = (self.enabled != enabled)

        self.name = name
        self.brand = brand
        self.model = model
        self._rtsp_url = rtsp_url
        self.enabled = enabled

        if not enabled and self._running:
            self.stop()
        elif enabled and not self._running:
            self.start()
        elif enabled and url_changed and self._running:
            self.stop()
            self.start()

    def retry_preview(self) -> Dict[str, Any]:
        """Manually reset retries and trigger immediate connection attempt."""
        print(f"[BACKEND LOG] MANUAL RETRY REQUESTED: Camera #{self.camera_id} ('{self.name}')")
        with self._lock:
            self._retry_count = 0
            self._auto_retry_exhausted = False
            self._last_error = None
            self._connection_status = "connecting"
            self._preview_status = "connecting"
        
        self._retry_event.set()
        if not self._running and self.enabled:
            self.start()
        return self.get_preview_status()

    def _open_capture(self) -> Optional[cv2.VideoCapture]:
        """Attempt to open cv2.VideoCapture with FFmpeg backend."""
        try:
            cap = cv2.VideoCapture(self._rtsp_url, cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            if cap.isOpened():
                return cap
            else:
                cap.release()
                return None
        except Exception as e:
            with self._lock:
                self._last_error = f"VideoCapture error: {type(e).__name__}"
            return None

    def _capture_loop(self) -> None:
        """Controlled capture loop: max 3 auto retries with backoff, then waits for manual retry."""
        print(f"[BACKEND LOG] PREVIEW WORKER STARTED: Camera #{self.camera_id} ('{self.name}') at {self.safe_ip}")
        first_frame_logged = False

        while self._running:
            # Check if auto retry attempts were exhausted
            if self._auto_retry_exhausted:
                with self._lock:
                    self._connected = False
                    self._preview_available = False
                    self._connection_status = "offline"
                    self._preview_status = "preview_unavailable"
                    self._detection_status = "stopped"
                    if not self._last_error:
                        self._last_error = f"No video frames received after {self._max_auto_retries} retries"

                # Wait for manual retry signal or stop
                self._retry_event.wait(timeout=1.0)
                if self._retry_event.is_set():
                    self._retry_event.clear()
                    self._auto_retry_exhausted = False
                    self._retry_count = 0
                    print(f"[BACKEND LOG] RESUMING CAPTURE LOOP ON MANUAL RETRY: Camera #{self.camera_id}")
                continue

            # Update status to connecting
            with self._lock:
                self._connection_status = "connecting"
                self._preview_status = "connecting"

            cap = self._open_capture()

            if cap is None or not cap.isOpened():
                self._retry_count += 1
                with self._lock:
                    self._connected = False
                    self._preview_available = False
                    self._connect_time = None
                    self._consecutive_failures += 1
                    self._last_error = f"Unable to open RTSP stream from {self.safe_ip}"

                print(f"[BACKEND LOG] PREVIEW ATTEMPT {self._retry_count}/{self._max_auto_retries} FAILED: Camera #{self.camera_id} at {self.safe_ip}")
                self._check_and_trigger_outage_event()

                if self._retry_count >= self._max_auto_retries:
                    self._auto_retry_exhausted = True
                    with self._lock:
                        self._connection_status = "offline"
                        self._preview_status = "preview_unavailable"
                        self._last_error = f"No video frames received after {self._max_auto_retries} retries"
                    print(f"[BACKEND LOG] PREVIEW RETRIES EXHAUSTED: Camera #{self.camera_id}. Status set to preview_unavailable. Stopping auto-reconnect.")
                    continue

                # Controlled Exponential Backoff: 2s, 4s, 8s
                backoff = min(INITIAL_BACKOFF * (2 ** (self._retry_count - 1)), MAX_BACKOFF)
                self._retry_event.wait(timeout=backoff)
                if self._retry_event.is_set():
                    self._retry_event.clear()
                    self._retry_count = 0
                continue

            # Connected successfully
            now = time.time()
            with self._lock:
                self._connected = True
                self._connect_time = now
                self._consecutive_failures = 0
                self._retry_count = 0
                self._last_error = None
                self._fps_start_time = now
                self._frame_count = 0
                self._connection_status = "online"
                self._preview_status = "live"
                self._detection_status = "running" if self.enabled else "stopped"

            print(f"[BACKEND LOG] RTSP CONNECTION SUCCESSFUL: Camera #{self.camera_id} ('{self.name}') at {self.safe_ip}")
            logger.info(f"Connected to camera #{self.camera_id} ('{self.name}') at {self.safe_ip}")
            log_system_event("CAMERA", f"Camera #{self.camera_id} ('{self.name}') connected")
            self._handle_reconnected_event()

            # Active frame reading loop
            first_frame_in_session = True
            while self._running:
                try:
                    ret, frame = cap.read()
                    if not ret or frame is None:
                        with self._lock:
                            self._connected = False
                            self._preview_available = False
                            self._connect_time = None
                            self._consecutive_failures += 1
                            self._last_error = "Frame read dropped by camera"
                            self._connection_status = "offline"
                        print(f"[BACKEND LOG] PREVIEW ERROR: Camera #{self.camera_id} frame read dropped")
                        self._check_and_trigger_outage_event()
                        break

                    now_frame_time = time.time()
                    now_iso = datetime.now(timezone.utc).isoformat()

                    if first_frame_in_session:
                        first_frame_in_session = False
                        h, w = frame.shape[:2]
                        print(f"[BACKEND LOG] FIRST FRAME RECEIVED: Camera #{self.camera_id} ({w}x{h} px)")

                    with self._lock:
                        self._latest_frame = frame
                        self._last_frame_time = now_frame_time
                        self._last_frame_timestamp_iso = now_iso
                        self._connected = True
                        self._preview_available = True
                        self._total_frames_received += 1
                        self._frame_count += 1
                        self._connection_status = "online"
                        self._preview_status = "live"
                        self._detection_status = "running" if self.enabled else "stopped"

                        # Update FPS
                        elapsed = now_frame_time - self._fps_start_time
                        if elapsed >= 2.0:
                            self._current_fps = round(self._frame_count / elapsed, 1)
                            self._frame_count = 0
                            self._fps_start_time = now_frame_time

                    time.sleep(0.005)

                except Exception as e:
                    with self._lock:
                        self._connected = False
                        self._preview_available = False
                        self._last_error = f"Capture exception: {str(e)}"
                        self._connection_status = "offline"
                    print(f"[BACKEND LOG] PREVIEW ERROR: Camera #{self.camera_id} capture exception: {e}")
                    break

            try:
                cap.release()
            except Exception:
                pass

            # If still running, increment retry counter
            if self._running:
                self._retry_count += 1
                if self._retry_count >= self._max_auto_retries:
                    self._auto_retry_exhausted = True
                    with self._lock:
                        self._connection_status = "offline"
                        self._preview_status = "preview_unavailable"
                        self._detection_status = "stopped"
                        self._last_error = f"Stream disconnected after {self._max_auto_retries} frame drop retries"
                    print(f"[BACKEND LOG] PREVIEW RETRIES EXHAUSTED: Camera #{self.camera_id} after stream drop.")
                else:
                    backoff = min(INITIAL_BACKOFF * (2 ** (self._retry_count - 1)), MAX_BACKOFF)
                    self._retry_event.wait(timeout=backoff)
                    if self._retry_event.is_set():
                        self._retry_event.clear()
                        self._retry_count = 0

        print(f"[BACKEND LOG] PREVIEW WORKER STOPPED: Camera #{self.camera_id}")

    def _check_and_trigger_outage_event(self) -> None:
        """Trigger CAMERA_OFFLINE event when consecutive read drops occur."""
        with self._lock:
            should_trigger = not self._was_offline_event_triggered and (self._consecutive_failures >= 3 or self._auto_retry_exhausted)
            if should_trigger:
                self._was_offline_event_triggered = True

        if should_trigger:
            logger.warning(f"Camera #{self.camera_id} ('{self.name}') is OFFLINE")
            create_security_event(
                event_type="CAMERA_OFFLINE",
                camera_id=self.camera_id,
                camera_name=self.name,
                motion_area=0.0,
                snapshot_path=None,
                notes=f"Camera #{self.camera_id} ({self.name}) connection lost at {self.safe_ip}",
                system_mode="SYSTEM",
                status="NEW",
                message=f"Camera '{self.name}' offline"
            )

    def _handle_reconnected_event(self) -> None:
        """Trigger CAMERA_RECONNECTED event after recovering from outage."""
        with self._lock:
            had_outage = self._was_offline_event_triggered
            self._was_offline_event_triggered = False

        if had_outage:
            logger.info(f"Camera #{self.camera_id} ('{self.name}') RECONNECTED")
            create_security_event(
                event_type="CAMERA_RECONNECTED",
                camera_id=self.camera_id,
                camera_name=self.name,
                motion_area=0.0,
                snapshot_path=None,
                notes=f"Camera #{self.camera_id} ({self.name}) reconnected at {self.safe_ip}",
                system_mode="SYSTEM",
                status="RESOLVED",
                message=f"Camera '{self.name}' reconnected"
            )
            try:
                from app.detection import motion_service
                det = motion_service._detectors.get(self.camera_id)
                if det:
                    det.reset_baseline()
            except Exception:
                pass

    def get_latest_frame(self) -> Tuple[bool, Optional[np.ndarray], Optional[str]]:
        """Return (connected, latest_frame_copy, timestamp_iso)."""
        with self._lock:
            if not self._connected or self._latest_frame is None:
                return False, None, None
            return True, self._latest_frame.copy(), self._last_frame_timestamp_iso

    def is_warmed_up(self) -> bool:
        """Check if camera has passed the initial warmup period."""
        with self._lock:
            if not self._connected or self._connect_time is None:
                return False
            return (time.time() - self._connect_time) >= self._warmup_seconds

    def get_preview_status(self) -> Dict[str, Any]:
        """Direct preview status diagnostics matching user requirement #6."""
        now = time.time()
        with self._lock:
            connected = self._connected
            running = self._running
            frames_rec = self._total_frames_received
            preview_avail = self._preview_available and (self._latest_frame is not None)
            retry_cnt = self._retry_count
            max_ret = self._max_auto_retries
            exhausted = self._auto_retry_exhausted
            last_err = self._last_error
            fps = self._current_fps
            conn_status = self._connection_status
            prev_status = self._preview_status
            det_status = self._detection_status

        if not self.enabled:
            status_str = "disabled"
            conn_status = "offline"
            prev_status = "stopped"
            det_status = "stopped"
        elif connected and preview_avail:
            status_str = "live"
        elif not running:
            status_str = "stopped"
        elif exhausted:
            status_str = "preview_unavailable"
        elif retry_cnt > 0:
            status_str = "connecting"
        else:
            status_str = "preview_unavailable"

        return {
            "camera_id": self.camera_id,
            "camera_saved": True,
            "name": self.name,
            "brand": self.brand,
            "model": self.model,
            "camera_brand": self.brand,
            "camera_model": self.model,
            "camera_ip": self.safe_ip,
            "ip_address": self.safe_ip,
            "rtsp_reachable": connected,
            "stream_worker_running": running,
            "frames_received": frames_rec,
            "preview_available": preview_avail,
            "status": status_str,
            "connection_status": conn_status,
            "preview_status": prev_status,
            "detection_status": det_status,
            "error": last_err or ("No frames received from RTSP stream" if not connected else None),
            "retry_count": retry_cnt,
            "max_retries": max_ret,
            "safe_ip": self.safe_ip,
            "fps": fps if connected else 0.0
        }

    def get_status(self) -> Dict[str, Any]:
        """Return safe, non-secret camera metadata, separated statuses, and connectivity metrics."""
        now = time.time()
        with self._lock:
            connected = self._connected
            last_frame_iso = self._last_frame_timestamp_iso
            fps = self._current_fps
            retry_cnt = self._retry_count
            max_ret = self._max_auto_retries
            consec_fails = self._consecutive_failures
            frames_rec = self._total_frames_received
            last_err = self._last_error
            warmed_up = (now - self._connect_time) >= self._warmup_seconds if (connected and self._connect_time) else False
            time_since_frame = round(now - self._last_frame_time, 2) if self._last_frame_time else None
            conn_status = self._connection_status
            prev_status = self._preview_status
            det_status = self._detection_status
            exhausted = self._auto_retry_exhausted

        if not self.enabled:
            status_label = "disabled"
            conn_status = "offline"
            prev_status = "stopped"
            det_status = "stopped"
        elif connected:
            status_label = "online"
            conn_status = "online"
            prev_status = "live"
        elif not exhausted and self._running and retry_cnt > 0:
            status_label = "connecting"
            conn_status = "connecting"
            prev_status = "connecting"
        else:
            status_label = "offline"
            conn_status = "offline"
            prev_status = "preview_unavailable"

        return {
            "id": self.camera_id,
            "camera_id": self.camera_id,
            "name": self.name,
            "brand": self.brand,
            "model": self.model,
            "camera_brand": self.brand,
            "camera_model": self.model,
            "camera_ip": self.safe_ip,
            "ip_address": self.safe_ip,
            "enabled": self.enabled,
            "camera_saved": True,
            "connected": connected,
            "status": status_label,
            "connection_status": conn_status,
            "preview_status": prev_status,
            "detection_status": det_status,
            "last_frame_timestamp": last_frame_iso,
            "time_since_last_frame_seconds": time_since_frame,
            "fps": fps if connected else 0.0,
            "frames_received": frames_rec,
            "reconnect_count": retry_cnt,
            "retry_count": retry_cnt,
            "max_retries": max_ret,
            "consecutive_failures": consec_fails,
            "warmed_up": warmed_up,
            "error_message": last_err
        }

    def generate_mjpeg_stream(self) -> Generator[bytes, None, None]:
        """Yield multipart MJPEG frames directly for browser <img> tags."""
        blank_frame = np.zeros((360, 640, 3), dtype=np.uint8)
        blank_frame[:] = (15, 20, 24)
        cv2.putText(blank_frame, "VERONIC GUARDBOX", (30, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (105, 145, 197), 2)
        cv2.putText(blank_frame, f"Camera: {self.name}", (30, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (248, 250, 252), 1)
        cv2.putText(blank_frame, f"IP: {self.safe_ip}", (30, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (157, 180, 198), 1)
        cv2.putText(blank_frame, "Preview Unavailable / Reconnecting", (30, 210), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (239, 68, 68), 2)
        cv2.putText(blank_frame, "Click [Retry Preview] to reconnect", (30, 250), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (157, 180, 198), 1)
        _, blank_jpeg = cv2.imencode('.jpg', blank_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
        blank_bytes = blank_jpeg.tobytes()

        try:
            while True:
                connected, frame, _ = self.get_latest_frame()
                if connected and frame is not None:
                    ret, jpeg = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
                    frame_bytes = jpeg.tobytes() if ret else blank_bytes
                else:
                    frame_bytes = blank_bytes

                yield (
                    b'--frame\r\n'
                    b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n'
                )
                time.sleep(0.04)
        except (GeneratorExit, ConnectionResetError, BrokenPipeError):
            pass
        except Exception as e:
            logger.debug(f"Stream client disconnected for Camera #{self.camera_id}: {e}")

    @staticmethod
    def test_rtsp_connection(rtsp_url: str, timeout_seconds: float = 6.0) -> Tuple[bool, str, Dict[str, Any]]:
        """Test RTSP URL connectivity and return detailed metrics."""
        if not rtsp_url or not rtsp_url.startswith("rtsp://"):
            return False, "Invalid RTSP URL format. Must start with rtsp://", {}

        safe_ip = parse_safe_ip(rtsp_url)
        cap = None
        try:
            cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            start_t = time.time()
            opened = False
            while (time.time() - start_t) < timeout_seconds:
                if cap.isOpened():
                    opened = True
                    break
                time.sleep(0.3)

            if not opened:
                return False, f"Could not connect to RTSP stream at {safe_ip} (Timeout after {int(timeout_seconds)}s)", {}

            ret, frame = cap.read()
            if ret and frame is not None:
                h, w = frame.shape[:2]
                fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
                return True, f"RTSP connection successful. Frames received: 1, Resolution: {w}x{h}, FPS: {fps}", {
                    "frames_received": 1,
                    "resolution": f"{w}x{h}",
                    "width": w,
                    "height": h,
                    "fps": round(fps, 1),
                    "safe_ip": safe_ip
                }
            else:
                return False, f"RTSP connection failed. Reason: Stream opened at {safe_ip} but failed to capture a valid frame.", {}
        except Exception as e:
            return False, f"RTSP connection failed. Reason: {type(e).__name__}", {}
        finally:
            if cap:
                try:
                    cap.release()
                except Exception:
                    pass


# ==============================================================================
# Camera Manager (Multi-Camera Supervisor)
# ==============================================================================

class CameraManager:
    """Manages collection of CameraWorkers mapped to database records."""

    def __init__(self):
        self._lock = threading.RLock()
        self._workers: Dict[int, CameraWorker] = {}
        self._started = False

    def start(self) -> None:
        """Start workers for all enabled cameras in database."""
        with self._lock:
            if self._started:
                return
            self._started = True

        cameras = get_all_cameras()
        for cam in cameras:
            self._init_worker(cam)

    def stop(self) -> None:
        """Stop all camera workers gracefully."""
        with self._lock:
            self._started = False
            workers = list(self._workers.values())
            self._workers.clear()

        for worker in workers:
            worker.stop()
        logger.info("CameraManager stopped all workers")

    def _init_worker(self, cam_data: Dict[str, Any]) -> CameraWorker:
        """Instantiate and start a worker for a camera."""
        cam_id = cam_data["id"]
        worker = CameraWorker(
            camera_id=cam_id,
            name=cam_data["name"],
            brand=cam_data["brand"],
            model=cam_data["model"],
            rtsp_url=cam_data["rtsp_url"],
            enabled=bool(cam_data["enabled"])
        )
        with self._lock:
            self._workers[cam_id] = worker

        if worker.enabled and self._started:
            worker.start()
        return worker

    def get_worker(self, camera_id: int) -> Optional[CameraWorker]:
        """Retrieve active worker by camera ID."""
        with self._lock:
            return self._workers.get(camera_id)

    def get_primary_worker(self) -> Optional[CameraWorker]:
        """Return primary / first camera worker."""
        with self._lock:
            if 1 in self._workers:
                return self._workers[1]
            if self._workers:
                return next(iter(self._workers.values()))
            return None

    def get_all_workers(self) -> List[CameraWorker]:
        """Return list of all camera workers."""
        with self._lock:
            return list(self._workers.values())

    def reload_camera(self, camera_id: int) -> Optional[CameraWorker]:
        """Sync worker with latest DB state."""
        cam_data = get_camera_by_id(camera_id)
        if not cam_data:
            self.remove_camera(camera_id)
            return None

        with self._lock:
            worker = self._workers.get(camera_id)

        if worker:
            worker.update_config(
                name=cam_data["name"],
                brand=cam_data["brand"],
                model=cam_data["model"],
                rtsp_url=cam_data["rtsp_url"],
                enabled=bool(cam_data["enabled"])
            )
            return worker
        else:
            return self._init_worker(cam_data)

    def remove_camera(self, camera_id: int) -> bool:
        """Stop and remove a camera worker, release detector resources, and delete from DB."""
        with self._lock:
            worker = self._workers.pop(camera_id, None)
        if worker:
            worker.stop()

        # Clean up detector resources
        try:
            from app.detection import motion_service
            motion_service.remove_camera(camera_id)
        except Exception as e:
            logger.warning(f"Error removing detector for camera #{camera_id}: {e}")

        # Clean up database record and associated zones
        from app.database import delete_camera
        return delete_camera(camera_id)

    def get_all_statuses(self) -> List[Dict[str, Any]]:
        """Return safe status summaries for all database cameras."""
        db_cams = get_all_cameras()
        statuses = []
        for cam in db_cams:
            worker = self.get_worker(cam["id"])
            if worker:
                st = worker.get_status()
                st["zone_count"] = cam.get("zone_count", 0)
                statuses.append(st)
            else:
                statuses.append({
                    "id": cam["id"],
                    "camera_id": cam["id"],
                    "name": cam["name"],
                    "brand": cam["brand"],
                    "model": cam["model"],
                    "camera_brand": cam["brand"],
                    "camera_model": cam["model"],
                    "camera_ip": parse_safe_ip(cam["rtsp_url"]),
                    "ip_address": parse_safe_ip(cam["rtsp_url"]),
                    "enabled": bool(cam["enabled"]),
                    "camera_saved": True,
                    "connected": False,
                    "status": "disabled" if not cam["enabled"] else "offline",
                    "connection_status": "offline",
                    "preview_status": "stopped",
                    "detection_status": "stopped",
                    "zone_count": cam.get("zone_count", 0),
                    "fps": 0.0,
                    "frames_received": 0,
                    "retry_count": 0,
                    "max_retries": MAX_AUTO_RETRIES,
                    "warmed_up": False
                })
        return statuses

    def add_camera(self, name: str, brand: str, model: str, rtsp_url: str, enabled: bool = True) -> int:
        """Add a camera to database and start worker."""
        cam_id = create_camera(name=name, brand=brand, model=model, rtsp_url=rtsp_url, enabled=enabled)
        cam_data = get_camera_by_id(cam_id)
        if cam_data:
            self._init_worker(cam_data)
        return cam_id

    def update_camera(self, camera_id: int, name: Optional[str] = None, brand: Optional[str] = None, model: Optional[str] = None, rtsp_url: Optional[str] = None, enabled: Optional[bool] = None) -> bool:
        """Update camera configuration in database and reload worker."""
        success = update_camera(camera_id=camera_id, name=name, brand=brand, model=model, rtsp_url=rtsp_url, enabled=enabled)
        if success:
            self.reload_camera(camera_id)
        return success

    def toggle_camera(self, camera_id: int, enabled: bool) -> bool:
        """Toggle camera enabled state and update worker."""
        success = toggle_camera(camera_id=camera_id, enabled=enabled)
        if success:
            self.reload_camera(camera_id)
        return success

    def get_camera_status(self, camera_id: int) -> Optional[Dict[str, Any]]:
        """Get safe status of a specific camera."""
        cam = get_camera_by_id(camera_id)
        if not cam:
            return None
        worker = self.get_worker(camera_id)
        if worker:
            st = worker.get_status()
            st["zone_count"] = cam.get("zone_count", 0)
            return st
        return {
            "id": cam["id"],
            "camera_id": cam["id"],
            "name": cam["name"],
            "brand": cam["brand"],
            "model": cam["model"],
            "camera_brand": cam["brand"],
            "camera_model": cam["model"],
            "camera_ip": parse_safe_ip(cam["rtsp_url"]),
            "ip_address": parse_safe_ip(cam["rtsp_url"]),
            "enabled": bool(cam["enabled"]),
            "camera_saved": True,
            "connected": False,
            "status": "disabled" if not cam["enabled"] else "offline",
            "connection_status": "offline",
            "preview_status": "stopped",
            "detection_status": "stopped",
            "zone_count": cam.get("zone_count", 0),
            "fps": 0.0,
            "frames_received": 0,
            "retry_count": 0,
            "max_retries": MAX_AUTO_RETRIES,
            "warmed_up": False
        }

    def get_preview_status(self, camera_id: int) -> Dict[str, Any]:
        """Get preview status for specified camera."""
        worker = self.get_worker(camera_id)
        if worker:
            return worker.get_preview_status()
        cam = get_camera_by_id(camera_id)
        if cam:
            safe_ip = parse_safe_ip(cam["rtsp_url"])
            return {
                "camera_id": camera_id,
                "camera_saved": True,
                "name": cam["name"],
                "brand": cam["brand"],
                "model": cam["model"],
                "camera_brand": cam["brand"],
                "camera_model": cam["model"],
                "camera_ip": safe_ip,
                "ip_address": safe_ip,
                "rtsp_reachable": False,
                "stream_worker_running": False,
                "frames_received": 0,
                "preview_available": False,
                "status": "preview_unavailable",
                "connection_status": "offline",
                "preview_status": "stopped",
                "detection_status": "stopped",
                "error": "Worker not initialized or disabled",
                "retry_count": 0,
                "max_retries": MAX_AUTO_RETRIES,
                "safe_ip": safe_ip,
                "fps": 0.0
            }
        return {
            "camera_id": camera_id,
            "camera_saved": False,
            "name": f"Camera #{camera_id}",
            "brand": "Generic",
            "model": "RTSP",
            "camera_brand": "Generic",
            "camera_model": "RTSP",
            "camera_ip": "127.0.0.1",
            "ip_address": "127.0.0.1",
            "rtsp_reachable": False,
            "stream_worker_running": False,
            "frames_received": 0,
            "preview_available": False,
            "status": "preview_unavailable",
            "connection_status": "offline",
            "preview_status": "stopped",
            "detection_status": "stopped",
            "error": "Camera not found in database",
            "retry_count": 0,
            "max_retries": MAX_AUTO_RETRIES,
            "safe_ip": "127.0.0.1",
            "fps": 0.0
        }

    def retry_preview(self, camera_id: int) -> Dict[str, Any]:
        """Trigger reconnection attempt for camera preview."""
        worker = self.get_worker(camera_id)
        if not worker:
            worker = self.reload_camera(camera_id)
        if worker:
            return worker.retry_preview()
        return self.get_preview_status(camera_id)

    def generate_mjpeg_stream(self, camera_id: int = 1, stream_type: str = "annotated") -> Generator[bytes, None, None]:
        """Generate continuous MJPEG stream for camera or placeholder if offline."""
        worker = self.get_worker(camera_id)
        if worker:
            return worker.generate_mjpeg_stream()
        blank_frame = np.zeros((360, 640, 3), dtype=np.uint8)
        blank_frame[:] = (15, 20, 24)
        cv2.putText(blank_frame, "VERONIC GUARDBOX", (30, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (105, 145, 197), 2)
        cv2.putText(blank_frame, f"Camera #{camera_id} Stream Unavailable", (30, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (248, 250, 252), 1)
        cv2.putText(blank_frame, "Worker offline or camera not configured", (30, 160), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (157, 180, 198), 1)
        _, blank_jpeg = cv2.imencode('.jpg', blank_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
        blank_bytes = blank_jpeg.tobytes()

        def _fallback():
            try:
                while True:
                    yield (
                        b'--frame\r\n'
                        b'Content-Type: image/jpeg\r\n\r\n' + blank_bytes + b'\r\n'
                    )
                    time.sleep(0.5)
            except (GeneratorExit, ConnectionResetError, BrokenPipeError):
                pass
        return _fallback()

    # Alias for backward compatibility
    get_camera_statuses = get_all_statuses


# Global CameraManager singleton
camera_manager = CameraManager()


# Backward-compatible proxy for camera_service
class CameraServiceProxy:
    """Proxy providing backward compatibility for camera_service references."""

    def start(self) -> None:
        camera_manager.start()

    def stop(self) -> None:
        camera_manager.stop()

    def get_latest_frame(self) -> Tuple[bool, Optional[np.ndarray], Optional[str]]:
        worker = camera_manager.get_primary_worker()
        if worker:
            return worker.get_latest_frame()
        return False, None, None

    def get_status(self) -> Dict[str, Any]:
        worker = camera_manager.get_primary_worker()
        if worker:
            return worker.get_status()
        return {
            "connected": False,
            "camera_saved": True,
            "status": "offline",
            "connection_status": "offline",
            "preview_status": "preview_unavailable",
            "detection_status": "stopped",
            "camera_brand": settings.CAMERA_BRAND,
            "camera_model": settings.CAMERA_MODEL,
            "camera_ip": settings.get_safe_camera_ip(),
            "ip_address": settings.get_safe_camera_ip(),
            "fps": 0,
            "warmed_up": False,
            "reconnect_count": 0,
            "retry_count": 0,
            "max_retries": MAX_AUTO_RETRIES,
            "consecutive_failures": 0,
            "error_message": "Camera service initializing"
        }

    def is_warmed_up(self) -> bool:
        worker = camera_manager.get_primary_worker()
        return worker.is_warmed_up() if worker else False

    def generate_mjpeg_stream(self) -> Generator[bytes, None, None]:
        worker = camera_manager.get_primary_worker()
        if worker:
            return worker.generate_mjpeg_stream()
        blank = np.zeros((360, 640, 3), dtype=np.uint8)
        _, jpeg = cv2.imencode('.jpg', blank)
        b = jpeg.tobytes()
        try:
            while True:
                yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + b + b'\r\n'
                time.sleep(0.1)
        except (GeneratorExit, ConnectionResetError, BrokenPipeError):
            pass

    def test_rtsp_connection(self, rtsp_url: str, timeout_seconds: float = 6.0) -> Dict[str, Any]:
        success, message, metrics = CameraWorker.test_rtsp_connection(rtsp_url, timeout_seconds)
        return {"success": success, "message": message, **metrics}


camera_service = CameraServiceProxy()
