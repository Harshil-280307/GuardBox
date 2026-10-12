"""
Veronic GuardBox - FastAPI Main Application (Phase 3: Multi-Camera, FCM Push Escalation & Android Devices)
Provides REST endpoints, multi-camera MJPEG streaming, multi-zone configuration,
event status lifecycle, CSV export, Shop Schedule, Alarm Simulation,
Notification Device Registration (Android FCM), and Push Alert Escalation.
"""

import io
import csv
import os
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

logger = logging.getLogger("guardbox.api")

from fastapi import FastAPI, HTTPException, status, Query, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

from app.config import settings, BASE_DIR
from app.database import (
    init_db,
    log_system_event,
    get_all_cameras,
    get_camera_by_id,
    create_camera,
    update_camera,
    delete_camera,
    toggle_camera,
    get_all_zones,
    get_zones_by_camera,
    get_zone_by_id,
    create_zone,
    update_zone,
    delete_zone,
    toggle_zone,
    clear_zones_by_camera,
    clear_all_zones,
    get_filtered_events,
    get_event_by_id,
    acknowledge_event,
    mark_false_alarm,
    resolve_event,
    delete_event,
    clear_test_events,
    get_events_for_csv,
    get_filtered_logs,
    get_schedule_config,
    update_schedule_config,
    get_all_devices,
    get_device_by_id,
    register_device,
    delete_device,
    reorder_devices,
    touch_device_last_seen,
    get_notification_settings,
    update_notification_settings,
    get_recent_alerts,
    get_alert_by_id,
    get_alert_by_code,
    get_alert_by_id_or_code,
    get_active_alert,
    acknowledge_alert,
    get_push_history,
    get_deliveries_by_alert
)
from app.camera import camera_manager, camera_service, CameraWorker, parse_safe_ip
from app.detection import motion_service
from app.alarm import alarm_service
from app.schedule import schedule_service
from app.push import push_escalation_service, fcm_service
from app.snapshot_cleanup import snapshot_cleanup_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for multi-camera workers, detection & database."""
    # Startup
    init_db()
    try:
        push_escalation_service.cleanup_stale_alerts_on_startup()
    except Exception as e:
        logger.warning(f"Startup stale alert cleanup notice: {e}")
    log_system_event("SYSTEM", "TRINETRA backend server initialized")
    camera_manager.start()
    motion_service.start()
    schedule_service.start()
    snapshot_cleanup_service.start()
    try:
        from app.supabase_storage import supabase_storage_service
        supabase_storage_service.validate_configuration()
    except Exception as e:
        logger.warning(f"Supabase Storage validation notice: {e}")
    try:
        from app.firebase_bridge import firebase_bridge
        firebase_bridge.start()
    except Exception as e:
        logger.warning(f"Firebase Bridge startup notice: {e}")
    yield
    # Shutdown
    try:
        from app.firebase_bridge import firebase_bridge
        firebase_bridge.stop()
    except Exception:
        pass
    snapshot_cleanup_service.stop()
    schedule_service.stop()
    motion_service.stop()
    camera_manager.stop()
    log_system_event("SYSTEM", "GuardBox backend server shut down gracefully")


app = FastAPI(
    title="Veronic GuardBox API",
    description="Local-first Security Monitoring & Android Push Alert Platform for High-Value Retail",
    version="3.0.0",
    lifespan=lifespan
)

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

# CORS configuration for Vite frontend origins & local Android testing
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "*"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


import ipaddress


def _is_trusted_local_or_lan(client_host: str) -> bool:
    """Check if client IP is localhost, loopback, or a private RFC 1918 LAN address."""
    if not client_host or client_host in ("localhost", "::1", "127.0.0.1", "testclient"):
        return True
    try:
        ip = ipaddress.ip_address(client_host)
        return ip.is_loopback or ip.is_private or ip.is_link_local
    except ValueError:
        return False


class GuardBoxSecurityMiddleware(BaseHTTPMiddleware):
    """
    Phase 1 Remote Access Security Middleware.
    Validates X-GuardBox-Key or Authorization Bearer header when GUARDBOX_API_KEY is configured.
    Permits loopback and private LAN Wi-Fi traffic (192.168.x.x, 10.x.x.x, 172.16-31.x.x) freely.
    """
    async def dispatch(self, request: Request, call_next):
        expected_key = getattr(settings, "GUARDBOX_API_KEY", "").strip()
        if expected_key:
            path = request.url.path
            # Allow public docs, static assets, and CORS preflight OPTIONS
            if request.method == "OPTIONS" or path in ("/docs", "/redoc", "/openapi.json", "/favicon.ico"):
                return await call_next(request)

            provided_key = request.headers.get("X-GuardBox-Key")
            if not provided_key:
                auth_header = request.headers.get("Authorization", "")
                if auth_header.startswith("Bearer "):
                    provided_key = auth_header[7:].strip()

            client_host = request.client.host if request.client else ""
            # Fallback to X-Forwarded-For or X-Real-IP if present
            forwarded_for = request.headers.get("X-Forwarded-For")
            if forwarded_for:
                client_host = forwarded_for.split(",")[0].strip()
            elif request.headers.get("X-Real-IP"):
                client_host = request.headers.get("X-Real-IP", "").strip()

            is_local = _is_trusted_local_or_lan(client_host)

            if provided_key != expected_key and not is_local:
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": "Unauthorized: Missing or invalid X-GuardBox-Key header"}
                )

        return await call_next(request)


app.add_middleware(GuardBoxSecurityMiddleware)

# Snapshots directory
snapshot_dir = settings.SNAPSHOT_DIRECTORY
os.makedirs(snapshot_dir, exist_ok=True)
app.mount("/snapshots", StaticFiles(directory=snapshot_dir), name="snapshots")


# ==============================================================================
# Pydantic Request Models
# ==============================================================================

class CameraCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Camera label, e.g., 'Main Shop Camera'")
    brand: str = Field("TP-Link", min_length=1, max_length=50)
    model: str = Field("Tapo C100", min_length=1, max_length=50)
    rtsp_url: str = Field(..., min_length=5, description="RTSP URL with credentials")
    enabled: bool = Field(True, description="Whether camera is active")


class CameraUpdateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    brand: str = Field("TP-Link", min_length=1, max_length=50)
    model: str = Field("Tapo C100", min_length=1, max_length=50)
    rtsp_url: Optional[str] = Field(None, description="Optional new RTSP URL")
    enabled: Optional[bool] = Field(None, description="Optional enable/disable toggle")


class CameraTestRequest(BaseModel):
    rtsp_url: str = Field(..., min_length=5, description="RTSP URL to test")


class ZoneCreateRequest(BaseModel):
    camera_id: Optional[int] = Field(1, description="Target camera ID")
    name: str = Field(..., min_length=1, max_length=100, description="Zone name, e.g., 'Jewellery Display'")
    points: Optional[List[List[float]]] = Field(None, description="List of [x, y] normalized coordinates (0.0 - 1.0), minimum 3 points")
    x: Optional[float] = Field(None, ge=0.0, le=1.0, description="Optional Top-left X (0.0 to 1.0)")
    y: Optional[float] = Field(None, ge=0.0, le=1.0, description="Optional Top-left Y (0.0 to 1.0)")
    width: Optional[float] = Field(None, ge=0.001, le=1.0, description="Optional Width (0.001 to 1.0)")
    height: Optional[float] = Field(None, ge=0.001, le=1.0, description="Optional Height (0.001 to 1.0)")
    color: str = Field("#FF3B30", description="Hex color code")
    enabled: bool = Field(True, description="Zone active state")

    @model_validator(mode="after")
    def validate_polygon_or_rect(self):
        if not self.name or not self.name.strip():
            raise ValueError("Zone name cannot be empty.")
        if self.points is not None:
            if len(self.points) < 3:
                raise ValueError("Polygon zone must have at least 3 points.")
            for idx, pt in enumerate(self.points):
                if not isinstance(pt, (list, tuple)) or len(pt) < 2:
                    raise ValueError(f"Point #{idx + 1} must be an [x, y] coordinate pair.")
                try:
                    px, py = float(pt[0]), float(pt[1])
                except (TypeError, ValueError):
                    raise ValueError(f"Point #{idx + 1} has non-numeric coordinates.")
                if px != px or py != py or px == float('inf') or px == float('-inf') or py == float('inf') or py == float('-inf'):
                    raise ValueError(f"Point #{idx + 1} contains NaN or infinite values.")
                if px < 0.0 or px > 1.0 or py < 0.0 or py > 1.0:
                    raise ValueError(f"Point #{idx + 1} ({px}, {py}) is outside normalized bounds [0.0, 1.0].")
        elif self.x is None or self.y is None or self.width is None or self.height is None:
            raise ValueError("Either 'points' (minimum 3 points) or rectangular 'x, y, width, height' must be provided.")
        return self


class ZoneUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    points: Optional[List[List[float]]] = Field(None, description="List of [x, y] coordinates")
    x: Optional[float] = Field(None, ge=0.0, le=1.0)
    y: Optional[float] = Field(None, ge=0.0, le=1.0)
    width: Optional[float] = Field(None, ge=0.001, le=1.0)
    height: Optional[float] = Field(None, ge=0.001, le=1.0)
    color: Optional[str] = None
    enabled: Optional[bool] = None

    @model_validator(mode="after")
    def validate_points(self):
        if self.name is not None and not self.name.strip():
            raise ValueError("Zone name cannot be empty.")
        if self.points is not None:
            if len(self.points) < 3:
                raise ValueError("Polygon zone must have at least 3 points.")
            for idx, pt in enumerate(self.points):
                if not isinstance(pt, (list, tuple)) or len(pt) < 2:
                    raise ValueError(f"Point #{idx + 1} must be an [x, y] coordinate pair.")
                try:
                    px, py = float(pt[0]), float(pt[1])
                except (TypeError, ValueError):
                    raise ValueError(f"Point #{idx + 1} has non-numeric coordinates.")
                if px != px or py != py or px == float('inf') or px == float('-inf') or py == float('inf') or py == float('-inf'):
                    raise ValueError(f"Point #{idx + 1} contains NaN or infinite values.")
                if px < 0.0 or px > 1.0 or py < 0.0 or py > 1.0:
                    raise ValueError(f"Point #{idx + 1} ({px}, {py}) is outside normalized bounds [0.0, 1.0].")
        return self


class ZoneToggleRequest(BaseModel):
    enabled: Optional[bool] = Field(None, description="Optional new enabled state. If omitted, toggles current state.")


class EventActionRequest(BaseModel):
    notes: Optional[str] = Field("", max_length=500, description="Optional user notes")


class ArmRequest(BaseModel):
    system_mode: str = Field("ARMED", description="'ARMED', 'DISARMED', or 'HOME'")


class ScheduleUpdateRequest(BaseModel):
    enabled: Optional[bool] = None
    opening_time: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    closing_time: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    auto_arm: Optional[bool] = None
    auto_disarm: Optional[bool] = None


class MotionSettingsUpdateRequest(BaseModel):
    motion_sensitivity: Optional[int] = Field(None, ge=1, le=100)
    min_motion_area: Optional[int] = Field(None, ge=50, le=100000)
    motion_cooldown_seconds: Optional[float] = Field(None, ge=0.5, le=60.0)
    motion_persistence_seconds: Optional[float] = Field(None, ge=0.1, le=10.0)
    camera_warmup_seconds: Optional[float] = Field(None, ge=0.0, le=30.0)
    blur_size: Optional[int] = Field(None, ge=3, le=31)
    frame_scale: Optional[float] = Field(None, ge=0.1, le=1.0)
    entry_delay_seconds: Optional[int] = Field(None, ge=0, le=300)
    exit_delay_seconds: Optional[int] = Field(None, ge=0, le=300)


# Phase 3 Device & Notification Request Models
class DeviceRegisterRequest(BaseModel):
    device_id: str = Field(..., min_length=2, max_length=100, description="Unique Android hardware or installation ID")
    user_name: str = Field(..., min_length=1, max_length=100, description="User name or role, e.g. 'Store Owner'")
    fcm_token: str = Field(..., min_length=5, description="Firebase Cloud Messaging Registration Token")
    device_name: str = Field("Android Device", min_length=1, max_length=100, description="Device model, e.g. 'Pixel 8 Pro'")
    platform: str = Field("android", description="Device platform ('android')")
    priority: Optional[int] = Field(None, ge=1, le=10, description="Escalation priority (1=Primary)")


class DeviceReorderRequest(BaseModel):
    ordered_device_ids: List[str] = Field(..., min_length=1, description="Ordered list of device_id strings")


class NotificationSettingsRequest(BaseModel):
    auto_push_enabled: Optional[bool] = None
    push_timeout_seconds: Optional[int] = Field(None, ge=5, le=600)
    max_retry_cycles: Optional[int] = Field(None, ge=1, le=10)
    min_alert_severity: Optional[str] = Field(None, description="'HIGH' or 'CRITICAL'")
    cooldown_seconds: Optional[int] = Field(None, ge=5, le=3600)


class AlertAcknowledgeRequest(BaseModel):
    acknowledged_by: Optional[str] = Field("Android App", description="Name of responder / device")
    device_id: Optional[str] = Field(None, description="Optional device ID")
    notes: Optional[str] = Field("", description="Optional responder remarks")


class SimulateAlertRequest(BaseModel):
    camera_id: int = Field(1, description="Camera ID")
    camera_name: Optional[str] = Field(None, description="Camera Name")
    event_type: str = Field("SUSPICIOUS_MOTION", description="Event type")
    severity: str = Field("HIGH", description="Severity (HIGH/CRITICAL)")
    motion_area: float = Field(850.0, description="Contour area in pixels")


class TestEmailRequest(BaseModel):
    recipient_email: str = Field(..., description="Target email address to receive test alert")
    camera_name: Optional[str] = Field("Shop Entrance (Tapo C100)", description="Camera name")
    event_type: Optional[str] = Field("SUSPICIOUS_MOTION", description="Event type")
    severity: Optional[str] = Field("HIGH", description="Alert severity")


class VeronicAuthRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=100, description="Administrator username")
    password: str = Field(..., min_length=1, max_length=200, description="Administrator password")


class DeviceIdentityUpdateRequest(BaseModel):
    device_id: Optional[str] = Field(None, min_length=3, max_length=64, description="Permanent Device ID")
    shop_id: Optional[str] = Field(None, min_length=2, max_length=64, description="Shop ID")
    shop_name: Optional[str] = Field(None, min_length=1, max_length=100, description="Shop Name")
    device_name: Optional[str] = Field(None, min_length=1, max_length=100, description="Device Name")
    owner_id: Optional[str] = Field(None, description="Optional Firebase Auth UID of shop owner")


class ShopTransferRequest(BaseModel):
    target_shop_id: str = Field(..., min_length=2, max_length=64, description="New target Shop ID")
    target_shop_name: Optional[str] = Field(None, min_length=1, max_length=100, description="New target Shop Name")


# ==============================================================================
# Health & Diagnostics Endpoints
# ==============================================================================

@app.get("/health", tags=["System"])
@app.get("/api/health", tags=["System"])
def health_check() -> Dict[str, Any]:
    """Overall system health check and status."""
    return {
        "status": "HEALTHY",
        "service": "Veronic GuardBox",
        "version": "3.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database": "CONNECTED",
        "fcm_configured": fcm_service.is_configured
    }


@app.get("/detection/health", tags=["System"])
def detection_health_check() -> Dict[str, Any]:
    """Detection diagnostic endpoint returning worker, camera, and pipeline status."""
    return motion_service.get_detection_health()



# ==============================================================================
# Multi-Camera Management Endpoints
# ==============================================================================

@app.get("/cameras", tags=["Cameras"])
def list_cameras() -> List[Dict[str, Any]]:
    """Retrieve all configured cameras with live connection status."""
    return camera_manager.get_camera_statuses()


@app.post("/cameras", tags=["Cameras"])
def add_camera(req: CameraCreateRequest) -> Dict[str, Any]:
    """Add a new camera and launch its background RTSP ingestion worker."""
    try:
        cam_id = camera_manager.add_camera(
            name=req.name,
            brand=req.brand,
            model=req.model,
            rtsp_url=req.rtsp_url,
            enabled=req.enabled
        )
        return {
            "id": cam_id,
            "name": req.name,
            "brand": req.brand,
            "model": req.model,
            "enabled": req.enabled,
            "message": f"Camera #{cam_id} added and worker spawned"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/cameras/{camera_id}", tags=["Cameras"])
def get_camera_detail(camera_id: int) -> Dict[str, Any]:
    """Get single camera details, configuration, and runtime statistics."""
    cam = camera_manager.get_camera_status(camera_id)
    if not cam:
        raise HTTPException(status_code=404, detail=f"Camera #{camera_id} not found")
    return cam


@app.put("/cameras/{camera_id}", tags=["Cameras"])
def update_camera_endpoint(camera_id: int, req: CameraUpdateRequest) -> Dict[str, Any]:
    """Update camera configuration and reconnect worker if RTSP URL changed."""
    success = camera_manager.update_camera(
        camera_id=camera_id,
        name=req.name,
        brand=req.brand,
        model=req.model,
        rtsp_url=req.rtsp_url,
        enabled=req.enabled
    )
    if not success:
        raise HTTPException(status_code=404, detail=f"Camera #{camera_id} not found")
    return {"success": True, "message": f"Camera #{camera_id} updated successfully"}


@app.delete("/cameras/{camera_id}", tags=["Cameras"])
def delete_camera_endpoint(camera_id: int) -> Dict[str, Any]:
    """Delete a camera, stop its worker, and remove associated zones."""
    success = camera_manager.remove_camera(camera_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Camera #{camera_id} not found")
    return {"success": True, "deleted_camera_id": camera_id}


@app.post("/cameras/{camera_id}/toggle", tags=["Cameras"])
def toggle_camera_endpoint(camera_id: int, enabled: Optional[bool] = Query(None)) -> Dict[str, Any]:
    """Enable or disable camera worker ingestion."""
    if enabled is None:
        cam = get_camera_by_id(camera_id)
        if not cam:
            raise HTTPException(status_code=404, detail=f"Camera #{camera_id} not found")
        enabled = not bool(cam["enabled"])
    success = camera_manager.toggle_camera(camera_id, enabled)
    if not success:
        raise HTTPException(status_code=404, detail=f"Camera #{camera_id} not found")
    return {"success": True, "camera_id": camera_id, "enabled": enabled}


@app.post("/camera/test", tags=["Cameras"])
@app.post("/cameras/test", tags=["Cameras"])
def test_camera_connection(req: CameraTestRequest) -> Dict[str, Any]:
    """Test RTSP credentials and stream reachability on an ad-hoc RTSP URL."""
    return camera_service.test_rtsp_connection(req.rtsp_url)


@app.get("/cameras/{camera_id}/preview-status", tags=["Streaming", "Cameras"])
def camera_preview_status(camera_id: int) -> Dict[str, Any]:
    """Retrieve detailed preview diagnostic metrics for a specific camera."""
    return camera_manager.get_preview_status(camera_id)


@app.post("/cameras/{camera_id}/retry", tags=["Streaming", "Cameras"])
def camera_retry_preview(camera_id: int) -> Dict[str, Any]:
    """Force re-initialize and reconnect camera preview worker."""
    return camera_manager.retry_preview(camera_id)


@app.get("/cameras/{camera_id}/status", tags=["Cameras"])
def get_camera_worker_status(camera_id: int) -> Dict[str, Any]:
    """Get single camera worker runtime status."""
    st = camera_manager.get_camera_status(camera_id)
    if not st:
        raise HTTPException(status_code=404, detail=f"Camera #{camera_id} not found")
    return st


# ==============================================================================
# Live Video Stream Endpoints
# ==============================================================================

@app.get("/video_feed", tags=["Streaming"])
@app.get("/cameras/{camera_id}/stream", tags=["Streaming"])
def video_feed(camera_id: Optional[int] = 1, stream_type: str = Query("annotated", description="'annotated', 'raw', or 'mask'")):
    """Continuous low-latency MJPEG video stream."""
    return StreamingResponse(
        camera_manager.generate_mjpeg_stream(camera_id=camera_id or 1, stream_type=stream_type),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


@app.get("/cameras/{camera_id}/snapshot", tags=["Streaming"])
def camera_snapshot(camera_id: int = 1):
    """Retrieve the latest live JPEG frame from the specified camera."""
    worker = camera_manager.get_worker(camera_id)
    if not worker or not worker.current_raw_frame is not None:
        raise HTTPException(status_code=503, detail="Camera stream unavailable")

    import cv2
    _, buffer = cv2.imencode('.jpg', worker.current_raw_frame)
    return Response(content=buffer.tobytes(), media_type="image/jpeg")


# ==============================================================================
# Detection Zones Management Endpoints
# ==============================================================================

@app.get("/zones", tags=["Detection Zones"])
def list_zones(camera_id: Optional[int] = Query(None, description="Filter zones by camera ID")) -> List[Dict[str, Any]]:
    """Retrieve all detection zones or zones for a specific camera."""
    if camera_id is not None:
        return get_zones_by_camera(camera_id)
    return get_all_zones()


@app.post("/zones", tags=["Detection Zones"])
def add_zone(req: ZoneCreateRequest) -> Dict[str, Any]:
    """Create a new detection zone."""
    try:
        zone_id = create_zone(
            camera_id=req.camera_id or 1,
            name=req.name.strip(),
            x=req.x,
            y=req.y,
            width=req.width,
            height=req.height,
            points=req.points,
            color=req.color,
            enabled=req.enabled
        )
        created = get_zone_by_id(zone_id)
        if not created:
            raise HTTPException(status_code=500, detail="Failed to retrieve created zone")
        return created
    except ValueError as ve:
        raise HTTPException(status_code=422, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/zones/{zone_id}", tags=["Detection Zones"])
def get_single_zone(zone_id: int) -> Dict[str, Any]:
    """Retrieve single zone by ID."""
    zone = get_zone_by_id(zone_id)
    if not zone:
        raise HTTPException(status_code=404, detail=f"Zone #{zone_id} not found")
    return zone


@app.put("/zones/{zone_id}", tags=["Detection Zones"])
def edit_zone(zone_id: int, req: ZoneUpdateRequest) -> Dict[str, Any]:
    """Update detection zone coordinates or parameters."""
    try:
        updated = update_zone(
            zone_id=zone_id,
            name=req.name.strip() if req.name is not None else None,
            x=req.x,
            y=req.y,
            width=req.width,
            height=req.height,
            points=req.points,
            color=req.color,
            enabled=req.enabled
        )
        if not updated:
            raise HTTPException(status_code=404, detail=f"Zone #{zone_id} not found")
        return get_zone_by_id(zone_id) or {"success": True, "updated_zone_id": zone_id}
    except ValueError as ve:
        raise HTTPException(status_code=422, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/zones/{zone_id}", tags=["Detection Zones"])
def remove_zone(zone_id: int) -> Dict[str, Any]:
    """Delete a detection zone."""
    success = delete_zone(zone_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Zone #{zone_id} not found")
    return {"success": True, "deleted_zone_id": zone_id}


@app.post("/zones/{zone_id}/toggle", tags=["Detection Zones"])
def toggle_zone_endpoint(
    zone_id: int,
    enabled: Optional[bool] = Query(None),
    body: Optional[ZoneToggleRequest] = None
) -> Dict[str, Any]:
    """Toggle zone active state independently."""
    target_enabled = enabled
    if target_enabled is None and body is not None and body.enabled is not None:
        target_enabled = body.enabled

    updated_zone = toggle_zone(zone_id, target_enabled)
    if not updated_zone:
        raise HTTPException(status_code=404, detail=f"Zone #{zone_id} not found")
    return {"success": True, "zone_id": zone_id, "enabled": bool(updated_zone["enabled"]), "zone": updated_zone}


@app.delete("/zones/camera/{camera_id}/clear", tags=["Detection Zones"])
def clear_camera_zones(camera_id: int) -> Dict[str, Any]:
    """Delete all zones configured on a specific camera."""
    clear_zones_by_camera(camera_id)
    return {"success": True, "camera_id": camera_id}


# ==============================================================================
# Security Events & Audit Log Endpoints
# ==============================================================================

@app.get("/events", tags=["Events"])
def list_events(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    camera_id: Optional[int] = None,
    zone_id: Optional[int] = None,
    severity: Optional[str] = None,
    status: Optional[str] = None
) -> Dict[str, Any]:
    """Retrieve filtered, paginated security detection events."""
    return get_filtered_events(
        page=page,
        page_size=page_size,
        start_date=start_date,
        end_date=end_date,
        camera_id=camera_id,
        zone_id=zone_id,
        severity=severity,
        status=status
    )


@app.get("/events/csv", tags=["Events"])
def export_events_csv(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    camera_id: Optional[int] = None,
    severity: Optional[str] = None,
    status: Optional[str] = None
):
    """Export filtered events as downloadable CSV spreadsheet."""
    items = get_events_for_csv(
        start_date=start_date,
        end_date=end_date,
        camera_id=camera_id,
        severity=severity,
        status=status
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Event ID", "Camera ID", "Camera Name", "Event Type", "Severity",
        "Timestamp", "Zone Name", "Motion Area", "Status", "Notes"
    ])

    for ev in items:
        writer.writerow([
            ev.get("id"),
            ev.get("camera_id"),
            ev.get("camera_name"),
            ev.get("event_type"),
            ev.get("severity"),
            ev.get("timestamp"),
            ev.get("zone_name") or "Whole Frame",
            ev.get("motion_area"),
            ev.get("status"),
            ev.get("notes") or ""
        ])

    output.seek(0)
    filename = f"guardbox_events_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@app.get("/events/{event_id}", tags=["Events"])
def get_event_detail(event_id: int) -> Dict[str, Any]:
    """Retrieve event details."""
    ev = get_event_by_id(event_id)
    if not ev:
        raise HTTPException(status_code=404, detail=f"Event #{event_id} not found")
    return ev


@app.post("/events/{event_id}/acknowledge", tags=["Events"])
def acknowledge_event_endpoint(event_id: int, req: Optional[EventActionRequest] = None) -> Dict[str, Any]:
    """Mark event as ACKNOWLEDGED."""
    notes = req.notes if req else ""
    success = acknowledge_event(event_id, notes=notes)
    if not success:
        raise HTTPException(status_code=404, detail=f"Event #{event_id} not found")
    return {"success": True, "event_id": event_id, "status": "ACKNOWLEDGED"}


@app.post("/events/{event_id}/false-alarm", tags=["Events"])
def mark_false_alarm_endpoint(event_id: int, req: Optional[EventActionRequest] = None) -> Dict[str, Any]:
    """Mark event as FALSE_ALARM."""
    notes = req.notes if req else ""
    success = mark_false_alarm(event_id, notes=notes)
    if not success:
        raise HTTPException(status_code=404, detail=f"Event #{event_id} not found")
    return {"success": True, "event_id": event_id, "status": "FALSE_ALARM"}


@app.post("/events/{event_id}/resolve", tags=["Events"])
def resolve_event_endpoint(event_id: int, req: Optional[EventActionRequest] = None) -> Dict[str, Any]:
    """Mark event as RESOLVED."""
    notes = req.notes if req else ""
    success = resolve_event(event_id, notes=notes)
    if not success:
        raise HTTPException(status_code=404, detail=f"Event #{event_id} not found")
    return {"success": True, "event_id": event_id, "status": "RESOLVED"}


@app.delete("/events/{event_id}", tags=["Events"])
def delete_event_endpoint(event_id: int) -> Dict[str, Any]:
    """Delete an event record."""
    success = delete_event(event_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Event #{event_id} not found")
    return {"success": True, "deleted_event_id": event_id}


@app.get("/logs", tags=["Audit Logs"])
def list_system_logs(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    log_type: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500)
) -> List[Dict[str, Any]]:
    """Retrieve system audit logs."""
    return get_filtered_logs(start_date=start_date, end_date=end_date, log_type=log_type, limit=limit)


# ==============================================================================
# ==============================================================================
# System State, Arming & Shop Schedule Endpoints
# ==============================================================================

@app.get("/system/status", tags=["System"])
def get_system_status_endpoint() -> Dict[str, Any]:
    """Consolidated status with arming mode (DISARMED, ARMING, ARMED, TEST_MODE)."""
    return motion_service.get_system_status()


class SystemArmRequest(BaseModel):
    exit_delay_seconds: Optional[int] = Field(15, ge=0, le=300)


@app.post("/system/arm", tags=["System"])
def system_arm_endpoint(req: Optional[SystemArmRequest] = None) -> Dict[str, Any]:
    """Arm the system with configurable exit delay."""
    delay = req.exit_delay_seconds if req else 15
    return motion_service.arm(exit_delay_seconds=delay)


@app.post("/system/cancel-arming", tags=["System"])
def system_cancel_arming_endpoint() -> Dict[str, Any]:
    """Cancel in-progress exit delay countdown."""
    return motion_service.cancel_arming()


@app.post("/system/disarm", tags=["System"])
def system_disarm_endpoint() -> Dict[str, Any]:
    """Disarm system and silence alarms."""
    return motion_service.disarm()


@app.get("/cameras/{camera_id}/zones", tags=["Detection Zones"])
def get_camera_zones_endpoint(camera_id: int) -> List[Dict[str, Any]]:
    """Retrieve detection zones configured on a specific camera."""
    return get_zones_by_camera(camera_id)


@app.post("/cameras/{camera_id}/zones", tags=["Detection Zones"])
def add_camera_zone_endpoint(camera_id: int, req: ZoneCreateRequest) -> Dict[str, Any]:
    """Create a new detection zone for a specific camera."""
    try:
        zone_id = create_zone(
            camera_id=camera_id,
            name=req.name.strip(),
            x=req.x,
            y=req.y,
            width=req.width,
            height=req.height,
            points=req.points,
            color=req.color,
            enabled=req.enabled
        )
        created = get_zone_by_id(zone_id)
        if not created:
            raise HTTPException(status_code=500, detail="Failed to retrieve created zone")
        return created
    except ValueError as ve:
        raise HTTPException(status_code=422, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/cameras/{camera_id}/zones", tags=["Detection Zones"])
def clear_camera_zones_endpoint(camera_id: int) -> Dict[str, Any]:
    """Delete all zones on a specific camera."""
    clear_zones_by_camera(camera_id)
    return {"success": True, "camera_id": camera_id}


@app.get("/arm-status", tags=["Arming & Mode"])
def get_arm_status() -> Dict[str, Any]:
    """Get current security arming state and entry/exit delay countdowns."""
    return motion_service.get_status()


@app.post("/arm", tags=["Arming & Mode"])
def set_arm_mode(req: ArmRequest) -> Dict[str, Any]:
    """Set system security mode ('ARMED', 'DISARMED', 'HOME')."""
    return motion_service.set_mode(req.system_mode)


@app.get("/schedule", tags=["Shop Schedule"])
def get_schedule() -> Dict[str, Any]:
    """Retrieve shop operating schedule configuration."""
    return schedule_service.get_config()


@app.put("/schedule", tags=["Shop Schedule"])
@app.post("/schedule", tags=["Shop Schedule"])
def update_schedule(req: ScheduleUpdateRequest) -> Dict[str, Any]:
    """Update shop schedule and automatic arming schedule."""
    return schedule_service.update_config(
        enabled=req.enabled,
        opening_time=req.opening_time,
        closing_time=req.closing_time,
        auto_arm=req.auto_arm,
        auto_disarm=req.auto_disarm
    )


@app.get("/settings", tags=["Settings"])
@app.get("/motion-settings", tags=["Motion Settings"])
def get_motion_settings() -> Dict[str, Any]:
    """Retrieve motion detection and delay parameters."""
    return motion_service.get_parameters()


@app.post("/settings", tags=["Settings"])
@app.post("/motion-settings", tags=["Motion Settings"])
def update_motion_settings(req: MotionSettingsUpdateRequest) -> Dict[str, Any]:
    """Update false alarm reduction and motion parameters."""
    return motion_service.update_parameters(
        sensitivity=req.motion_sensitivity,
        min_area=req.min_motion_area,
        cooldown_seconds=req.motion_cooldown_seconds,
        persistence_seconds=req.motion_persistence_seconds,
        warmup_seconds=req.camera_warmup_seconds,
        blur_size=req.blur_size,
        frame_scale=req.frame_scale,
        entry_delay_seconds=req.entry_delay_seconds,
        exit_delay_seconds=req.exit_delay_seconds
    )



# ==============================================================================
# Alarm Simulation Endpoints
# ==============================================================================

@app.post("/alarm/test", tags=["Alarm"])
def test_simulated_alarm() -> Dict[str, Any]:
    """Trigger a simulated alarm for testing (SIMULATED — NO PHYSICAL SIREN)."""
    return alarm_service.test_simulated_alarm()


@app.post("/alarm/silence", tags=["Alarm"])
def silence_alarm() -> Dict[str, Any]:
    """Silence any active simulated alarm."""
    return alarm_service.stop_alarm()


# ==============================================================================
# Phase 3: Android Notification Devices & FCM Registration Endpoints
# ==============================================================================

@app.get("/api/devices", tags=["Notification Devices"])
@app.get("/devices", tags=["Notification Devices"])
def list_notification_devices(active_only: bool = False) -> List[Dict[str, Any]]:
    """Retrieve registered Android notification devices sorted by escalation priority."""
    return get_all_devices(active_only=active_only)


@app.post("/api/devices/register", tags=["Notification Devices"])
@app.post("/devices/register", tags=["Notification Devices"])
def register_android_device(req: DeviceRegisterRequest) -> Dict[str, Any]:
    """
    Register or update an Android device and its FCM registration token.
    Supports multiple devices per user and updates priority automatically.
    """
    device = register_device(
        device_id=req.device_id,
        user_name=req.user_name,
        fcm_token=req.fcm_token,
        device_name=req.device_name,
        platform=req.platform,
        priority=req.priority
    )
    return {
        "success": True,
        "message": f"Device '{req.device_name}' registered successfully",
        "device": device
    }


@app.get("/api/devices/{device_id}", tags=["Notification Devices"])
def get_device_detail(device_id: str) -> Dict[str, Any]:
    """Retrieve single registered device by device ID."""
    dev = get_device_by_id(device_id)
    if not dev:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")
    return dev


@app.delete("/api/devices/{device_id}", tags=["Notification Devices"])
def remove_device_endpoint(device_id: str) -> Dict[str, Any]:
    """Unregister and remove an Android notification device."""
    success = delete_device(device_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")
    return {"success": True, "deleted_device_id": device_id}


@app.post("/api/devices/reorder", tags=["Notification Devices"])
def reorder_notification_devices(req: DeviceReorderRequest) -> List[Dict[str, Any]]:
    """Update priority escalation order across registered devices."""
    reorder_devices(req.ordered_device_ids)
    return get_all_devices()


@app.post("/api/devices/{device_id}/test-push", tags=["Notification Devices"])
def send_test_push_to_device(device_id: str) -> Dict[str, Any]:
    """Dispatch a safe, non-emergency test push notification to a specific device."""
    try:
        return push_escalation_service.send_test_push(device_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/test-security-alert", tags=["Notification Devices"])
@app.post("/test-security-alert", tags=["Notification Devices"])
def send_test_security_alert_endpoint(device_id: Optional[str] = None) -> Dict[str, Any]:
    """Safe test mechanism to dispatch an FCM test notification to registered Android devices without creating fake camera motion events."""
    devices = get_all_devices(active_only=True)
    if not devices:
        raise HTTPException(status_code=404, detail="No registered Android devices found to receive test alert")
    target_id = device_id if device_id else devices[0]["device_id"]
    return push_escalation_service.send_test_push(target_id)


@app.post("/api/devices/{device_id}/heartbeat", tags=["Notification Devices"])
def record_device_heartbeat(device_id: str) -> Dict[str, Any]:
    """Update device last_seen timestamp when Android app checks in."""
    success = touch_device_last_seen(device_id)
    return {"success": success, "device_id": device_id}


# ==============================================================================
# Phase 3: Push Notification Settings & Health Endpoints
# ==============================================================================

@app.get("/api/notifications/settings", tags=["Notifications"])
def get_notification_settings_endpoint() -> Dict[str, Any]:
    """Retrieve push escalation settings."""
    cfg = get_notification_settings()
    cfg["fcm_configured"] = fcm_service.is_configured
    cfg["fcm_key_masked"] = settings.get_masked_fcm_key()
    return cfg


@app.post("/api/notifications/settings", tags=["Notifications"])
def update_notification_settings_endpoint(req: NotificationSettingsRequest) -> Dict[str, Any]:
    """Update push escalation parameters."""
    return update_notification_settings(
        auto_push_enabled=req.auto_push_enabled,
        push_timeout_seconds=req.push_timeout_seconds,
        max_retry_cycles=req.max_retry_cycles,
        min_alert_severity=req.min_alert_severity,
        cooldown_seconds=req.cooldown_seconds
    )


@app.get("/api/notifications/history", tags=["Notifications"])
def get_push_history_endpoint(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    alert_id: Optional[int] = None,
    status: Optional[str] = None
) -> Dict[str, Any]:
    """Retrieve filtered, paginated push notification delivery logs."""
    return get_push_history(page=page, page_size=page_size, alert_id=alert_id, status=status)


@app.get("/api/notifications/health", tags=["Notifications"])
def get_notifications_health() -> Dict[str, Any]:
    """Diagnostics and health check for FCM push alerts."""
    devices = get_all_devices(active_only=True)
    return {
        "fcm_configured": fcm_service.is_configured,
        "fcm_server_key_masked": settings.get_masked_fcm_key(),
        "registered_devices_count": len(devices),
        "active_devices": [
            {
                "device_id": d["device_id"],
                "device_name": d["device_name"],
                "user_name": d["user_name"],
                "priority": d["priority"],
                "last_seen": d["last_seen"]
            }
            for d in devices
        ],
        "auto_push_enabled": settings.AUTO_PUSH_ENABLED,
        "push_timeout_seconds": settings.PUSH_TIMEOUT_SECONDS
    }


# ==============================================================================
# Phase 3: Security Alerts & Push Escalation Lifecycle Endpoints
# ==============================================================================

@app.get("/api/alerts", tags=["Security Alerts"])
def list_security_alerts(limit: int = Query(20, ge=1, le=100)) -> List[Dict[str, Any]]:
    """List recent security alerts with push delivery summaries."""
    return get_recent_alerts(limit=limit)


@app.get("/api/alerts/active", tags=["Security Alerts"])
def get_active_security_alert() -> Dict[str, Any]:
    """Get currently active in-progress security alert if any."""
    alert = get_active_alert()
    return {"active_alert": alert, "is_escalating": alert is not None}


@app.get("/api/alerts/status", tags=["Security Alerts"])
def get_escalation_status_endpoint() -> Dict[str, Any]:
    """Retrieve live push escalation state, active alert, and delivery logs."""
    return push_escalation_service.get_status()


@app.get("/api/alerts/{alert_id}", tags=["Security Alerts"])
def get_security_alert_detail(alert_id: str) -> Dict[str, Any]:
    """Get single security alert details and all FCM push deliveries."""
    alert = get_alert_by_id_or_code(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail=f"Alert #{alert_id} not found")
    deliveries = get_deliveries_by_alert(alert["id"])
    return {"alert": alert, "deliveries": deliveries}


@app.post("/api/alerts/{alert_id}/acknowledge", tags=["Security Alerts"])
def acknowledge_security_alert_endpoint(alert_id: str, req: Optional[AlertAcknowledgeRequest] = None) -> Dict[str, Any]:
    """
    Acknowledge a security alert from an Android app ('I'M HANDLING IT') or Web Dashboard.
    Immediately stops active push escalation sequence across all devices.
    """
    alert = get_alert_by_id_or_code(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail=f"Alert #{alert_id} not found")
    user = req.acknowledged_by if (req and req.acknowledged_by) else "Android App"
    success = push_escalation_service.acknowledge(alert["id"], acknowledged_by=user)
    if not success:
        raise HTTPException(status_code=404, detail=f"Alert #{alert_id} not found")
    return {
        "success": True,
        "alert_id": alert.get("alert_code", alert["id"]),
        "internal_id": alert["id"],
        "status": "ACKNOWLEDGED",
        "acknowledged_by": user,
        "message": "Alert acknowledged. Escalation stopped."
    }


@app.post("/api/alerts/{alert_id}/escalate", tags=["Security Alerts"])
def force_escalate_alert_endpoint(alert_id: str) -> Dict[str, Any]:
    """Manually advance escalation to the next registered priority device."""
    alert = get_alert_by_id_or_code(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail=f"Alert #{alert_id} not found")
    push_escalation_service.start_escalation(alert["id"])
    return {"success": True, "alert_id": alert.get("alert_code", alert["id"]), "status": "ESCALATING"}


@app.post("/api/alerts/{alert_id}/retry_remote_upload", tags=["Security Alerts"])
def retry_remote_upload_endpoint(alert_id: str) -> Dict[str, Any]:
    """Safe retry mechanism for background Supabase Storage snapshot upload."""
    result = push_escalation_service.retry_remote_snapshot_upload(alert_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Retry failed"))
    return result


@app.post("/api/alerts/simulate", tags=["Security Alerts"])
def simulate_security_alert_endpoint(req: SimulateAlertRequest) -> Dict[str, Any]:
    """Manually trigger a HIGH security alert to test the full Android push escalation sequence."""
    cam_name = req.camera_name
    if not cam_name:
        cam = get_camera_by_id(req.camera_id)
        cam_name = cam["name"] if cam else f"Shop Camera {req.camera_id}"

    alert = push_escalation_service.handle_security_event(
        camera_id=req.camera_id,
        camera_name=cam_name,
        event_type=req.event_type,
        severity=req.severity,
        motion_area=req.motion_area,
        force=True
    )
    if not alert:
        raise HTTPException(status_code=400, detail="Failed to create simulated security alert")
    return alert


@app.get("/api/debug/alert-state", tags=["Diagnostics"])
def get_debug_alert_state_endpoint() -> Dict[str, Any]:
    """Temporary diagnostic endpoint to inspect active alert state without exposing secrets."""
    dev_id = settings.GUARDBOX_DEVICE_ID or "guardbox-shop-f20424b4"
    active_alert = get_active_alert()
    return {
        "device_id": dev_id,
        "current_alert_id": active_alert["alert_code"] if active_alert else None,
        "current_alert_internal_id": active_alert["id"] if active_alert else None,
        "current_alert_created_at": active_alert["created_at"] if active_alert else None,
        "current_alert_expires_at": active_alert.get("expires_at") if active_alert else None,
        "current_alert_reason": active_alert["event_type"] if active_alert else None,
        "current_alert_exists": active_alert is not None
    }


@app.get("/api/notifications/email-status", tags=["Notifications"])
def get_email_status_endpoint() -> Dict[str, Any]:
    """Get status of TRINETRA Email Alerting and SMTP configuration."""
    from app.email_service import email_alert_service
    return {
        "enabled": settings.EMAIL_NOTIFICATIONS_ENABLED,
        "smtp_host": settings.SMTP_HOST,
        "smtp_port": settings.SMTP_PORT,
        "smtp_user": settings.SMTP_USER,
        "smtp_configured": email_alert_service.is_configured(),
        "from_address": settings.SMTP_FROM,
        "recipients_count": len(email_alert_service.recipients),
        "recipients": email_alert_service.recipients
    }


@app.post("/api/notifications/test-email", tags=["Notifications"])
def send_test_email_endpoint(req: TestEmailRequest) -> Dict[str, Any]:
    """Dispatch a test security alert email with the embedded TRINETRA logo to the given email."""
    from app.email_service import email_alert_service
    res = email_alert_service.send_security_alert_email(
        alert_code="TRI-TEST-LOGO-EMBEDDED",
        camera_name=req.camera_name or "Shop Entrance (Tapo C100)",
        event_type=req.event_type or "SUSPICIOUS_MOTION",
        severity=req.severity or "HIGH",
        timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        motion_area=1450.0,
        custom_recipients=[req.recipient_email]
    )
    if res.get("status") == "failed":
        raise HTTPException(status_code=500, detail=res.get("error", "Failed to dispatch test email"))
    return res


# ==============================================================================
# Phase 5.9: Device Identity, Shop Binding & Veronic Protected Administration
# ==============================================================================

def get_veronic_token_from_request(request: Request) -> Optional[str]:
    token = request.headers.get("X-Veronic-Token")
    if token:
        return token.strip()
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()
    return None


@app.get("/api/device/info", tags=["Device Identity"])
def get_device_identity_endpoint() -> Dict[str, Any]:
    """
    Public read-only device identity and shop binding information for Windows UI & Android.
    Device ID and Shop ID are locked by default.
    """
    from app.device_identity import device_identity_manager
    ident = device_identity_manager.get_identity()
    return {
        "device_id": ident["device_id"],
        "shop_id": ident.get("shop_id", "SHOP-RK-001"),
        "shop_name": ident.get("shop_name", "Rajkot Jewellery"),
        "device_name": ident.get("device_name", settings.GUARDBOX_DEVICE_NAME),
        "owner_id": ident.get("owner_id"),
        "registration_status": "REGISTERED",
        "connection_status": "ONLINE",
        "online": True,
        "version": ident.get("version", "1.0.0"),
        "is_locked": True,
        "is_configured": ident.get("is_configured", True)
    }


@app.post("/api/admin/veronic-auth", tags=["Veronic Administration"])
def veronic_admin_auth_endpoint(req: VeronicAuthRequest, request: Request) -> Dict[str, Any]:
    """
    Authenticate Veronic Administrator credentials.
    Issues a short-lived cryptographic token (5-minute expiry) to unlock protected device identity settings.
    """
    from app.device_identity import device_identity_manager
    client_ip = request.client.host if request.client else "127.0.0.1"
    success, token, msg = device_identity_manager.authenticate_veronic_admin(
        username=req.username,
        password=req.password,
        client_ip=client_ip
    )
    if not success or not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=msg)
    
    return {
        "success": True,
        "token": token,
        "expires_in": 300,
        "message": msg
    }


@app.post("/api/device/identity", tags=["Device Identity"])
def update_device_identity_endpoint(req: DeviceIdentityUpdateRequest, request: Request) -> Dict[str, Any]:
    """
    Protected endpoint to update physical Device ID, Shop ID, and customer binding.
    STRICTLY REQUIRES valid Veronic administrative token in X-Veronic-Token or Authorization header.
    """
    from app.device_identity import device_identity_manager
    token = get_veronic_token_from_request(request)
    if not device_identity_manager.verify_veronic_token(token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Veronic administrator authentication required to modify device identity."
        )

    try:
        updated = device_identity_manager.update_device_identity(
            new_device_id=req.device_id,
            new_shop_id=req.shop_id,
            new_shop_name=req.shop_name,
            new_device_name=req.device_name,
            owner_id=req.owner_id
        )
        return {
            "success": True,
            "message": "Device identity and shop binding updated successfully.",
            "identity": updated
        }
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to update identity: {e}")


@app.post("/api/device/transfer-shop", tags=["Device Identity"])
def transfer_device_shop_endpoint(req: ShopTransferRequest, request: Request) -> Dict[str, Any]:
    """
    Protected administrative endpoint to transfer a TRINETRA device to a new Shop ID.
    Requires valid Veronic administrator token.
    """
    from app.device_identity import device_identity_manager
    token = get_veronic_token_from_request(request)
    if not device_identity_manager.verify_veronic_token(token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Veronic administrator authentication required to transfer shop."
        )

    try:
        updated = device_identity_manager.update_device_identity(
            new_shop_id=req.target_shop_id,
            new_shop_name=req.target_shop_name
        )
        return {
            "success": True,
            "message": f"Device successfully transferred to Shop '{req.target_shop_id}'.",
            "identity": updated
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.get("/api/device/pairing-info", tags=["Device Identity"])
def get_device_pairing_info_endpoint() -> Dict[str, Any]:
    """
    Prepares sanitized pairing payload for future QR pairing.
    STRICTLY EXCLUDES Firebase Admin credentials, Supabase keys, and Veronic administrator secrets.
    """
    from app.device_identity import device_identity_manager
    ident = device_identity_manager.get_identity()
    return {
        "device_id": ident["device_id"],
        "shop_id": ident.get("shop_id", "SHOP-RK-001"),
        "shop_name": ident.get("shop_name", "Rajkot Jewellery"),
        "device_name": ident.get("device_name", settings.GUARDBOX_DEVICE_NAME),
        "protocol_version": "1.0",
        "pairing_type": "TRINETRA_QR_PAIR"
    }


# ==============================================================================
# Single Page Application (SPA) Frontend Mount
# ==============================================================================
# Resolve compiled React distribution directory (dev or packaged standalone executable)
import sys
from pathlib import Path

_frontend_candidates = [
    BASE_DIR / "dist",
    BASE_DIR / "frontend" / "dist",
    BASE_DIR.parent / "frontend" / "dist",
    Path(sys.executable).resolve().parent / "dist" if getattr(sys, "frozen", False) else None,
    Path(getattr(sys, "_MEIPASS", "")) / "dist" if getattr(sys, "frozen", False) else None,
]
FRONTEND_DIST_DIR = next(
    (str(p) for p in _frontend_candidates if p is not None and p.exists() and (p / "index.html").exists()),
    None
)

if FRONTEND_DIST_DIR and os.path.exists(FRONTEND_DIST_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIST_DIR, html=True), name="frontend_spa")
    logger.info(f"Mounted frontend SPA static distribution from: {FRONTEND_DIST_DIR}")



