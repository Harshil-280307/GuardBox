"""
Veronic GuardBox - SQLite Database Manager (Phase 3: Multi-Camera, FCM Push Escalation & Android Devices)
Provides robust SQLite migrations, Camera CRUD, Detection Zones CRUD per camera,
filtered event queries, status transitions (NEW, ACKNOWLEDGED, FALSE_ALARM, RESOLVED),
test data cleanup, schedule persistence, notification device management, FCM delivery logs, and audit logging.
"""

import sqlite3
import math
import uuid
import json
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any, Tuple, Union
from app.config import settings


def get_db_connection() -> sqlite3.Connection:
    """Create and return a thread-safe connection to the SQLite database."""
    conn = sqlite3.connect(settings.DATABASE_PATH, timeout=15.0)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Initialize database tables and run automatic safe migrations on startup."""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # 1. Cameras table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cameras (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                brand TEXT NOT NULL DEFAULT 'TP-Link',
                model TEXT NOT NULL DEFAULT 'Tapo C100',
                rtsp_url TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            )
        """)

        # Auto-seed default Primary Shop Camera if table is empty
        cursor.execute("SELECT COUNT(*) as cnt FROM cameras")
        if cursor.fetchone()["cnt"] == 0:
            now_iso = datetime.now(timezone.utc).isoformat()
            cursor.execute("""
                INSERT INTO cameras (name, brand, model, rtsp_url, enabled, created_at)
                VALUES (?, ?, ?, ?, 1, ?)
            """, ("Main Shop Camera", settings.CAMERA_BRAND, settings.CAMERA_MODEL, settings.RTSP_URL, now_iso))

        # 2. Detection zones table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS detection_zones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                camera_id INTEGER NOT NULL DEFAULT 1,
                name TEXT NOT NULL,
                x REAL NOT NULL,
                y REAL NOT NULL,
                width REAL NOT NULL,
                height REAL NOT NULL,
                points TEXT DEFAULT NULL,
                color TEXT NOT NULL DEFAULT '#EF4444',
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                FOREIGN KEY (camera_id) REFERENCES cameras (id) ON DELETE CASCADE
            )
        """)

        # Safe automatic column migrations for detection_zones
        cursor.execute("PRAGMA table_info(detection_zones)")
        dz_cols = [c[1] for c in cursor.fetchall()]
        if "color" not in dz_cols:
            cursor.execute("ALTER TABLE detection_zones ADD COLUMN color TEXT NOT NULL DEFAULT '#EF4444'")
        if "camera_id" not in dz_cols:
            cursor.execute("ALTER TABLE detection_zones ADD COLUMN camera_id INTEGER NOT NULL DEFAULT 1")
        if "points" not in dz_cols:
            cursor.execute("ALTER TABLE detection_zones ADD COLUMN points TEXT DEFAULT NULL")
        if "enabled" not in dz_cols:
            cursor.execute("ALTER TABLE detection_zones ADD COLUMN enabled INTEGER NOT NULL DEFAULT 1")
        if "created_at" not in dz_cols:
            now_iso = datetime.now(timezone.utc).isoformat()
            cursor.execute(f"ALTER TABLE detection_zones ADD COLUMN created_at TEXT NOT NULL DEFAULT '{now_iso}'")

        # 3. Events table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                camera_id INTEGER NOT NULL DEFAULT 1,
                camera_name TEXT NOT NULL DEFAULT 'Main Shop Camera',
                event_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                message TEXT DEFAULT '',
                timestamp TEXT NOT NULL,
                zone_id INTEGER DEFAULT NULL,
                zone_name TEXT DEFAULT NULL,
                motion_area REAL DEFAULT 0,
                snapshot_path TEXT,
                status TEXT DEFAULT 'NEW',
                acknowledged INTEGER DEFAULT 0,
                acknowledged_at TEXT DEFAULT NULL,
                notes TEXT DEFAULT '',
                system_mode TEXT DEFAULT 'ARMED',
                created_at TEXT DEFAULT ''
            )
        """)

        # Safe automatic column migrations for events
        cursor.execute("PRAGMA table_info(events)")
        ev_cols = [c[1] for c in cursor.fetchall()]
        if "camera_id" not in ev_cols:
            cursor.execute("ALTER TABLE events ADD COLUMN camera_id INTEGER NOT NULL DEFAULT 1")
        if "camera_name" not in ev_cols:
            cursor.execute("ALTER TABLE events ADD COLUMN camera_name TEXT NOT NULL DEFAULT 'Main Shop Camera'")
        if "severity" not in ev_cols:
            cursor.execute("ALTER TABLE events ADD COLUMN severity TEXT NOT NULL DEFAULT 'HIGH'")
        if "message" not in ev_cols:
            cursor.execute("ALTER TABLE events ADD COLUMN message TEXT NOT NULL DEFAULT ''")
        if "status" not in ev_cols:
            cursor.execute("ALTER TABLE events ADD COLUMN status TEXT NOT NULL DEFAULT 'NEW'")
        if "system_mode" not in ev_cols:
            cursor.execute("ALTER TABLE events ADD COLUMN system_mode TEXT NOT NULL DEFAULT 'ARMED'")
        if "created_at" not in ev_cols:
            now_iso = datetime.now(timezone.utc).isoformat()
            cursor.execute(f"ALTER TABLE events ADD COLUMN created_at TEXT NOT NULL DEFAULT '{now_iso}'")

        # 4. System audit logs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS system_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                log_type TEXT NOT NULL,
                message TEXT NOT NULL
            )
        """)

        # 5. Schedule Configuration table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schedule_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                enabled INTEGER NOT NULL DEFAULT 0,
                opening_time TEXT NOT NULL DEFAULT '09:00',
                closing_time TEXT NOT NULL DEFAULT '20:00',
                auto_arm INTEGER NOT NULL DEFAULT 1,
                auto_disarm INTEGER NOT NULL DEFAULT 1
            )
        """)
        cursor.execute("SELECT id FROM schedule_config WHERE id = 1")
        if not cursor.fetchone():
            cursor.execute("""
                INSERT INTO schedule_config (id, enabled, opening_time, closing_time, auto_arm, auto_disarm)
                VALUES (1, 0, '09:00', '20:00', 1, 1)
            """)

        # 6. Notification Devices table (Registered Android Devices)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notification_devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT UNIQUE NOT NULL,
                user_name TEXT NOT NULL,
                fcm_token TEXT NOT NULL,
                device_name TEXT NOT NULL,
                platform TEXT NOT NULL DEFAULT 'android',
                priority INTEGER NOT NULL DEFAULT 1,
                active INTEGER NOT NULL DEFAULT 1,
                last_seen TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        # Auto-seed initial default notification device if table is empty
        cursor.execute("SELECT COUNT(*) as cnt FROM notification_devices")
        if cursor.fetchone()["cnt"] == 0:
            now_iso = datetime.now(timezone.utc).isoformat()
            cursor.execute("""
                INSERT INTO notification_devices (
                    device_id, user_name, fcm_token, device_name, platform,
                    priority, active, last_seen, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                "device_owner_primary",
                "Shop Owner",
                "sample_fcm_token_owner_android_01",
                "Store Manager Phone",
                "android",
                1,
                1,
                now_iso,
                now_iso,
                now_iso
            ))

        # 7. Security Alerts table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS security_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_code TEXT UNIQUE NOT NULL,
                camera_id INTEGER NOT NULL DEFAULT 1,
                camera_name TEXT NOT NULL DEFAULT 'Main Shop Camera',
                event_type TEXT NOT NULL DEFAULT 'SUSPICIOUS_MOTION',
                severity TEXT NOT NULL DEFAULT 'HIGH',
                status TEXT NOT NULL DEFAULT 'WAITING_ACK',
                snapshot_path TEXT,
                motion_area REAL DEFAULT 0,
                created_at TEXT NOT NULL,
                expires_at TEXT DEFAULT NULL,
                acknowledged_at TEXT DEFAULT NULL,
                acknowledged_by TEXT DEFAULT NULL,
                retry_count INTEGER NOT NULL DEFAULT 0,
                last_attempt_at TEXT DEFAULT NULL
            )
        """)

        # Safe automatic column migrations for security_alerts
        cursor.execute("PRAGMA table_info(security_alerts)")
        sa_cols = [c[1] for c in cursor.fetchall()]
        if "expires_at" not in sa_cols:
            cursor.execute("ALTER TABLE security_alerts ADD COLUMN expires_at TEXT DEFAULT NULL")
        if "snapshot_status" not in sa_cols:
            cursor.execute("ALTER TABLE security_alerts ADD COLUMN snapshot_status TEXT DEFAULT 'AVAILABLE'")
        if "remote_snapshot_reference" not in sa_cols:
            cursor.execute("ALTER TABLE security_alerts ADD COLUMN remote_snapshot_reference TEXT DEFAULT NULL")
        if "remote_snapshot_status" not in sa_cols:
            cursor.execute("ALTER TABLE security_alerts ADD COLUMN remote_snapshot_status TEXT DEFAULT NULL")
        if "remote_url" not in sa_cols:
            cursor.execute("ALTER TABLE security_alerts ADD COLUMN remote_url TEXT DEFAULT NULL")
        if "remote_provider" not in sa_cols:
            cursor.execute("ALTER TABLE security_alerts ADD COLUMN remote_provider TEXT DEFAULT 'supabase'")

        # 8. Push Alert Deliveries table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS push_deliveries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_id INTEGER DEFAULT NULL,
                alert_code TEXT DEFAULT '',
                device_id TEXT NOT NULL,
                user_name TEXT NOT NULL,
                device_name TEXT NOT NULL,
                fcm_message_id TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'SENT',
                error_message TEXT DEFAULT '',
                sent_at TEXT NOT NULL,
                acknowledged INTEGER NOT NULL DEFAULT 0,
                acknowledged_at TEXT DEFAULT NULL,
                is_test INTEGER NOT NULL DEFAULT 0
            )
        """)

        # 9. Notification Settings table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notification_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                auto_push_enabled INTEGER NOT NULL DEFAULT 1,
                push_timeout_seconds INTEGER NOT NULL DEFAULT 30,
                max_retry_cycles INTEGER NOT NULL DEFAULT 2,
                min_alert_severity TEXT NOT NULL DEFAULT 'HIGH',
                cooldown_seconds INTEGER NOT NULL DEFAULT 60
            )
        """)

        cursor.execute("SELECT id FROM notification_settings WHERE id = 1")
        if not cursor.fetchone():
            cursor.execute("""
                INSERT INTO notification_settings (
                    id, auto_push_enabled, push_timeout_seconds, max_retry_cycles,
                    min_alert_severity, cooldown_seconds
                )
                VALUES (1, 1, 30, 2, 'HIGH', 60)
            """)

        conn.commit()
        print("[BACKEND LOG] Database connected")
        print("[BACKEND LOG] Camera table verified")
        print("[BACKEND LOG] Detection zone table verified")
        print("[BACKEND LOG] Notification devices & Push escalation tables verified")


# ==============================================================================
# Audit Logs
# ==============================================================================

def log_system_event(log_type: str, message: str) -> None:
    """Insert a system audit log into the database."""
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO system_logs (timestamp, log_type, message) VALUES (?, ?, ?)",
                (now_iso, log_type, message)
            )
            conn.commit()
    except Exception as e:
        print(f"[LOG ERROR] Failed to record system log: {e}")


def get_filtered_logs(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    log_type: Optional[str] = None,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """Retrieve system audit logs with optional filters."""
    where_clauses = []
    params: List[Any] = []

    if start_date:
        where_clauses.append("timestamp >= ?")
        params.append(start_date)
    if end_date:
        where_clauses.append("timestamp <= ?")
        params.append(end_date)
    if log_type and log_type != "ALL":
        where_clauses.append("log_type = ?")
        params.append(log_type)

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    params.append(limit)

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT id, timestamp, log_type, message FROM system_logs {where_sql} ORDER BY id DESC LIMIT ?",
            params
        )
        return [dict(row) for row in cursor.fetchall()]


# ==============================================================================
# Camera Management
# ==============================================================================

def get_all_cameras() -> List[Dict[str, Any]]:
    """Retrieve all cameras."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, brand, model, rtsp_url, enabled, created_at FROM cameras ORDER BY id ASC")
        return [dict(r) for r in cursor.fetchall()]


def get_camera_by_id(camera_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve camera by ID."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, brand, model, rtsp_url, enabled, created_at FROM cameras WHERE id = ?", (camera_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def create_camera(name: str, brand: str, model: str, rtsp_url: str, enabled: bool = True) -> int:
    """Create a new camera record."""
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(cameras)")
        cols = [c[1] for c in cursor.fetchall()]
        if "updated_at" in cols:
            cursor.execute(
                "INSERT INTO cameras (name, brand, model, rtsp_url, enabled, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (name, brand, model, rtsp_url, 1 if enabled else 0, now_iso, now_iso)
            )
        else:
            cursor.execute(
                "INSERT INTO cameras (name, brand, model, rtsp_url, enabled, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (name, brand, model, rtsp_url, 1 if enabled else 0, now_iso)
            )
        conn.commit()
        cam_id = cursor.lastrowid
        log_system_event("CAMERA", f"Created camera #{cam_id} ('{name}')")
        return cam_id



def update_camera(camera_id: int, name: Optional[str] = None, brand: Optional[str] = None, model: Optional[str] = None, rtsp_url: Optional[str] = None, enabled: Optional[bool] = None) -> bool:
    """Update camera properties."""
    current = get_camera_by_id(camera_id)
    if not current:
        return False
    new_name = name if name is not None else current["name"]
    new_brand = brand if brand is not None else current["brand"]
    new_model = model if model is not None else current["model"]
    new_url = rtsp_url if rtsp_url is not None else current["rtsp_url"]
    new_enabled = enabled if enabled is not None else bool(current["enabled"])

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE cameras SET name = ?, brand = ?, model = ?, rtsp_url = ?, enabled = ? WHERE id = ?",
            (new_name, new_brand, new_model, new_url, 1 if new_enabled else 0, camera_id)
        )
        conn.commit()
        updated = cursor.rowcount > 0
        if updated:
            log_system_event("CAMERA", f"Updated camera #{camera_id} ('{new_name}')")
        return updated


def delete_camera(camera_id: int) -> bool:
    """Delete a camera and its associated zones."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM detection_zones WHERE camera_id = ?", (camera_id,))
        cursor.execute("DELETE FROM cameras WHERE id = ?", (camera_id,))
        conn.commit()
        deleted = cursor.rowcount > 0
        if deleted:
            log_system_event("CAMERA", f"Deleted camera #{camera_id}")
        return deleted


def toggle_camera(camera_id: int, enabled: bool) -> bool:
    """Enable or disable camera."""
    return update_camera(camera_id, enabled=enabled)


# ==============================================================================
# Detection Zones Management
# ==============================================================================

def _format_zone_row(row: sqlite3.Row) -> Dict[str, Any]:
    """Format detection zone row ensuring polygon points and rect bbox are consistent."""
    d = dict(row)
    raw_points = d.get("points")
    points = None
    if raw_points:
        try:
            if isinstance(raw_points, str):
                parsed = json.loads(raw_points)
                if isinstance(parsed, list) and len(parsed) >= 3:
                    points = [[round(float(p[0]), 4), round(float(p[1]), 4)] for p in parsed if len(p) >= 2]
            elif isinstance(raw_points, list) and len(raw_points) >= 3:
                points = [[round(float(p[0]), 4), round(float(p[1]), 4)] for p in raw_points if len(p) >= 2]
        except Exception:
            points = None

    # Fallback to rectangular coordinates if points not present
    if not points:
        x = float(d.get("x", 0.0))
        y = float(d.get("y", 0.0))
        w = float(d.get("width", 0.5))
        h = float(d.get("height", 0.5))
        points = [
            [round(x, 4), round(y, 4)],
            [round(min(1.0, x + w), 4), round(y, 4)],
            [round(min(1.0, x + w), 4), round(min(1.0, y + h), 4)],
            [round(x, 4), round(min(1.0, y + h), 4)]
        ]

    d["points"] = points
    d["polygon_points"] = points  # alias for backwards compatibility

    # Ensure x, y, width, height are accurate bounding box
    if points and len(points) >= 3:
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        min_x = max(0.0, min(xs))
        min_y = max(0.0, min(ys))
        max_x = min(1.0, max(xs))
        max_y = min(1.0, max(ys))
        d["x"] = round(min_x, 4)
        d["y"] = round(min_y, 4)
        d["width"] = round(max(0.001, max_x - min_x), 4)
        d["height"] = round(max(0.001, max_y - min_y), 4)

    return d


def get_all_zones() -> List[Dict[str, Any]]:
    """Retrieve all zones across all cameras."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, camera_id, name, x, y, width, height, points, color, enabled, created_at FROM detection_zones ORDER BY id ASC")
        return [_format_zone_row(r) for r in cursor.fetchall()]


def get_zones_by_camera(camera_id: int) -> List[Dict[str, Any]]:
    """Retrieve zones for a specific camera."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, camera_id, name, x, y, width, height, points, color, enabled, created_at FROM detection_zones WHERE camera_id = ? ORDER BY id ASC", (camera_id,))
        return [_format_zone_row(r) for r in cursor.fetchall()]


def get_zone_by_id(zone_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve zone by ID."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, camera_id, name, x, y, width, height, points, color, enabled, created_at FROM detection_zones WHERE id = ?", (zone_id,))
        row = cursor.fetchone()
        return _format_zone_row(row) if row else None


def create_zone(
    camera_id: int = 1,
    name: str = "Zone",
    x: Optional[float] = None,
    y: Optional[float] = None,
    width: Optional[float] = None,
    height: Optional[float] = None,
    points: Optional[Union[List[List[float]], str]] = None,
    color: str = "#FF3B30",
    enabled: bool = True,
    **kwargs
) -> int:
    """Create a new detection zone (polygon or rectangle) on a camera."""
    parsed_points = None
    if points:
        if isinstance(points, str):
            try:
                points = json.loads(points)
            except Exception:
                points = None
        if isinstance(points, list) and len(points) >= 3:
            parsed_points = [[max(0.0, min(1.0, float(p[0]))), max(0.0, min(1.0, float(p[1])))] for p in points if len(p) >= 2]

    if parsed_points and len(parsed_points) >= 3:
        xs = [p[0] for p in parsed_points]
        ys = [p[1] for p in parsed_points]
        calc_x = max(0.0, min(xs))
        calc_y = max(0.0, min(ys))
        calc_w = max(0.001, min(1.0, max(xs)) - calc_x)
        calc_h = max(0.001, min(1.0, max(ys)) - calc_y)
        points_json = json.dumps(parsed_points)
    else:
        calc_x = float(x) if x is not None else 0.0
        calc_y = float(y) if y is not None else 0.0
        calc_w = float(width) if width is not None else 0.5
        calc_h = float(height) if height is not None else 0.5
        parsed_points = [
            [calc_x, calc_y],
            [min(1.0, calc_x + calc_w), calc_y],
            [min(1.0, calc_x + calc_w), min(1.0, calc_y + calc_h)],
            [calc_x, min(1.0, calc_y + calc_h)]
        ]
        points_json = json.dumps(parsed_points)

    now_iso = datetime.now(timezone.utc).isoformat()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO detection_zones (camera_id, name, x, y, width, height, points, color, enabled, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (camera_id, name, float(calc_x), float(calc_y), float(calc_w), float(calc_h), points_json, color, 1 if enabled else 0, now_iso)
        )
        conn.commit()
        zone_id = cursor.lastrowid
        log_system_event("ZONE", f"Created zone #{zone_id} ('{name}') on camera #{camera_id}")
        return zone_id


def update_zone(
    zone_id: int,
    name: Optional[str] = None,
    x: Optional[float] = None,
    y: Optional[float] = None,
    width: Optional[float] = None,
    height: Optional[float] = None,
    points: Optional[Union[List[List[float]], str]] = None,
    color: Optional[str] = None,
    enabled: Optional[bool] = None,
    **kwargs
) -> bool:
    """Update zone properties."""
    current = get_zone_by_id(zone_id)
    if not current:
        return False
    new_name = name if name is not None else current["name"]
    new_c = color if color is not None else current["color"]
    new_en = enabled if enabled is not None else bool(current["enabled"])

    parsed_points = None
    if points is not None:
        if isinstance(points, str):
            try:
                points = json.loads(points)
            except Exception:
                points = None
        if isinstance(points, list) and len(points) >= 3:
            parsed_points = [[max(0.0, min(1.0, float(p[0]))), max(0.0, min(1.0, float(p[1])))] for p in points if len(p) >= 2]

    if parsed_points and len(parsed_points) >= 3:
        xs = [p[0] for p in parsed_points]
        ys = [p[1] for p in parsed_points]
        new_x = max(0.0, min(xs))
        new_y = max(0.0, min(ys))
        new_w = max(0.001, min(1.0, max(xs)) - new_x)
        new_h = max(0.001, min(1.0, max(ys)) - new_y)
        points_json = json.dumps(parsed_points)
    else:
        new_x = float(x) if x is not None else current["x"]
        new_y = float(y) if y is not None else current["y"]
        new_w = float(width) if width is not None else current["width"]
        new_h = float(height) if height is not None else current["height"]
        if points is None and "points" in current and current["points"]:
            points_json = json.dumps(current["points"])
        else:
            points_json = json.dumps([
                [new_x, new_y],
                [min(1.0, new_x + new_w), new_y],
                [min(1.0, new_x + new_w), min(1.0, new_y + new_h)],
                [new_x, min(1.0, new_y + new_h)]
            ])

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE detection_zones SET name = ?, x = ?, y = ?, width = ?, height = ?, points = ?, color = ?, enabled = ? WHERE id = ?",
            (new_name, new_x, new_y, new_w, new_h, points_json, new_c, 1 if new_en else 0, zone_id)
        )
        conn.commit()
        updated = cursor.rowcount > 0
        if updated:
            log_system_event("ZONE", f"Updated zone #{zone_id} ('{new_name}')")
        return updated


def delete_zone(zone_id: int) -> bool:
    """Delete a detection zone."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM detection_zones WHERE id = ?", (zone_id,))
        conn.commit()
        deleted = cursor.rowcount > 0
        if deleted:
            log_system_event("ZONE", f"Deleted zone #{zone_id}")
        return deleted


def toggle_zone(zone_id: int, enabled: Optional[bool] = None) -> Optional[Dict[str, Any]]:
    """Toggle zone enabled state and return updated zone."""
    current = get_zone_by_id(zone_id)
    if not current:
        return None
    new_state = (not bool(current["enabled"])) if enabled is None else bool(enabled)
    update_zone(zone_id, enabled=new_state)
    return get_zone_by_id(zone_id)



def clear_zones_by_camera(camera_id: int) -> bool:
    """Clear all zones for a camera."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM detection_zones WHERE camera_id = ?", (camera_id,))
        conn.commit()
        log_system_event("ZONE", f"Cleared all zones for camera #{camera_id}")
        return True


def clear_all_zones() -> bool:
    """Clear all detection zones."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM detection_zones")
        conn.commit()
        log_system_event("ZONE", "Cleared all detection zones across all cameras")
        return True


# ==============================================================================
# Events Management
# ==============================================================================

def create_event(
    event_type: str = "MOTION_DETECTED",
    camera_id: int = 1,
    camera_name: str = "Main Shop Camera",
    severity: str = "HIGH",
    message: str = "",
    timestamp: Optional[str] = None,
    zone_id: Optional[int] = None,
    zone_name: Optional[str] = None,
    motion_area: float = 0.0,
    snapshot_path: Optional[str] = None,
    notes: str = "",
    system_mode: str = "ARMED",
    status: str = "NEW"
) -> int:
    """Record a detected motion / security event."""
    now_iso = datetime.now(timezone.utc).isoformat()
    ts = timestamp or now_iso
    msg = message or (f"{event_type} on {camera_name}" + (f" ({zone_name})" if zone_name else ""))
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO events (
                camera_id, camera_name, event_type, severity, message, timestamp,
                zone_id, zone_name, motion_area, snapshot_path, status, acknowledged,
                notes, system_mode, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
        """, (
            camera_id, camera_name, event_type, severity, msg, ts,
            zone_id, zone_name, float(motion_area), snapshot_path, status,
            notes, system_mode, now_iso
        ))
        conn.commit()
        event_id = cursor.lastrowid
        log_system_event("EVENT", f"New security event #{event_id} ({event_type}) on camera #{camera_id} [{severity}]")
        return event_id


# Alias for compatibility with camera and detection engines
create_security_event = create_event


def get_filtered_events(page: int = 1, page_size: int = 20, start_date: Optional[str] = None, end_date: Optional[str] = None, camera_id: Optional[int] = None, zone_id: Optional[int] = None, severity: Optional[str] = None, status: Optional[str] = None) -> Dict[str, Any]:
    """Retrieve paginated events with optional filters."""
    page = max(1, page)
    page_size = max(1, min(100, page_size))
    offset = (page - 1) * page_size

    where_clauses = []
    params: List[Any] = []

    if start_date:
        where_clauses.append("timestamp >= ?")
        params.append(start_date)
    if end_date:
        where_clauses.append("timestamp <= ?")
        params.append(end_date)
    if camera_id is not None:
        where_clauses.append("camera_id = ?")
        params.append(camera_id)
    if zone_id is not None:
        where_clauses.append("zone_id = ?")
        params.append(zone_id)
    if severity and severity != "ALL":
        where_clauses.append("severity = ?")
        params.append(severity)
    if status and status != "ALL":
        where_clauses.append("status = ?")
        params.append(status)

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT COUNT(*) as total FROM events {where_sql}", params)
        total = cursor.fetchone()["total"]

        cursor.execute(f"""
            SELECT id, camera_id, camera_name, event_type, severity, message, timestamp,
                   zone_id, zone_name, motion_area, snapshot_path, status, acknowledged,
                   acknowledged_at, notes, system_mode, created_at
            FROM events
            {where_sql}
            ORDER BY id DESC
            LIMIT ? OFFSET ?
        """, params + [page_size, offset])
        rows = [dict(r) for r in cursor.fetchall()]

        total_pages = max(1, math.ceil(total / page_size))
        return {
            "items": rows,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages
        }


def get_recent_events(limit: int = 10) -> List[Dict[str, Any]]:
    """Retrieve recent events list."""
    res = get_filtered_events(page=1, page_size=limit)
    return res.get("items", [])


def create_security_event(camera_id: int = 1, event_type: str = "MOTION_DETECTED", severity: str = "HIGH", zone_name: Optional[str] = None, motion_area: float = 0.0, snapshot_path: Optional[str] = None, **kwargs) -> int:
    """Create security event alias."""
    return create_event(
        event_type=event_type,
        camera_id=camera_id,
        severity=severity,
        zone_name=zone_name,
        motion_area=motion_area,
        snapshot_path=snapshot_path,
        **kwargs
    )




def get_event_by_id(event_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve single event by ID."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM events WHERE id = ?", (event_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def acknowledge_event(event_id: int, notes: str = "") -> bool:
    """Mark event as ACKNOWLEDGED."""
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE events
            SET status = 'ACKNOWLEDGED', acknowledged = 1, acknowledged_at = ?, notes = ?
            WHERE id = ?
        """, (now_iso, notes, event_id))
        conn.commit()
        updated = cursor.rowcount > 0
        if updated:
            log_system_event("EVENT_ACK", f"Event #{event_id} acknowledged")
        return updated


def mark_false_alarm(event_id: int, notes: str = "") -> bool:
    """Mark event as FALSE_ALARM."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE events SET status = 'FALSE_ALARM', notes = ? WHERE id = ?", (notes, event_id))
        conn.commit()
        updated = cursor.rowcount > 0
        if updated:
            log_system_event("EVENT_FALSE_ALARM", f"Event #{event_id} marked as False Alarm")
        return updated


def resolve_event(event_id: int, notes: str = "") -> bool:
    """Mark event as RESOLVED."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE events SET status = 'RESOLVED', notes = ? WHERE id = ?", (notes, event_id))
        conn.commit()
        updated = cursor.rowcount > 0
        if updated:
            log_system_event("EVENT_RESOLVE", f"Event #{event_id} resolved")
        return updated


def delete_event(event_id: int) -> bool:
    """Delete an event record."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM events WHERE id = ?", (event_id,))
        conn.commit()
        return cursor.rowcount > 0


def clear_test_events() -> int:
    """Clear simulated test events."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM events WHERE notes LIKE '%TEST%' OR message LIKE '%Simulation%'")
        conn.commit()
        return cursor.rowcount


def get_events_for_csv(start_date: Optional[str] = None, end_date: Optional[str] = None, camera_id: Optional[int] = None, severity: Optional[str] = None, status: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieve unfiltered events for CSV export."""
    res = get_filtered_events(page=1, page_size=10000, start_date=start_date, end_date=end_date, camera_id=camera_id, severity=severity, status=status)
    return res["items"]


# ==============================================================================
# Schedule Config
# ==============================================================================

def get_schedule_config() -> Dict[str, Any]:
    """Retrieve schedule configuration."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT enabled, opening_time, closing_time, auto_arm, auto_disarm FROM schedule_config WHERE id = 1")
        row = cursor.fetchone()
        if row:
            return {
                "enabled": bool(row["enabled"]),
                "opening_time": row["opening_time"],
                "closing_time": row["closing_time"],
                "auto_arm": bool(row["auto_arm"]),
                "auto_disarm": bool(row["auto_disarm"])
            }
        return {"enabled": False, "opening_time": "09:00", "closing_time": "20:00", "auto_arm": True, "auto_disarm": True}


def update_schedule_config(enabled: Optional[bool] = None, opening_time: Optional[str] = None, closing_time: Optional[str] = None, auto_arm: Optional[bool] = None, auto_disarm: Optional[bool] = None) -> Dict[str, Any]:
    """Update shop schedule config."""
    cur = get_schedule_config()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE schedule_config
            SET enabled = ?, opening_time = ?, closing_time = ?, auto_arm = ?, auto_disarm = ?
            WHERE id = 1
        """, (
            1 if (enabled if enabled is not None else cur["enabled"]) else 0,
            opening_time if opening_time is not None else cur["opening_time"],
            closing_time if closing_time is not None else cur["closing_time"],
            1 if (auto_arm if auto_arm is not None else cur["auto_arm"]) else 0,
            1 if (auto_disarm if auto_disarm is not None else cur["auto_disarm"]) else 0
        ))
        conn.commit()
        log_system_event("SCHEDULE", "Updated Shop Schedule Configuration")
        return get_schedule_config()


# ==============================================================================
# Notification Devices Management (Phase 3 Android FCM Devices)
# ==============================================================================

def mask_fcm_token(token: str) -> str:
    """Safely mask FCM token for dashboard display."""
    if not token:
        return "Not Set"
    if len(token) <= 12:
        return token[:3] + "••••"
    return f"{token[:6]}••••••••{token[-6:]}"


def register_device(
    device_id: str,
    user_name: str,
    fcm_token: str,
    device_name: str,
    platform: str = "android",
    priority: Optional[int] = None
) -> Dict[str, Any]:
    """Register or update an Android notification device with its latest FCM token."""
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, priority FROM notification_devices WHERE device_id = ?", (device_id,))
        existing = cursor.fetchone()

        if existing:
            # Update token and device information
            assigned_prio = priority if priority is not None else existing["priority"]
            cursor.execute("""
                UPDATE notification_devices
                SET user_name = ?, fcm_token = ?, device_name = ?, platform = ?,
                    priority = ?, active = 1, last_seen = ?, updated_at = ?
                WHERE device_id = ?
            """, (user_name, fcm_token, device_name, platform, assigned_prio, now_iso, now_iso, device_id))
            conn.commit()
            log_system_event("DEVICE", f"Updated notification device '{device_name}' ({user_name})")
        else:
            # New device: calculate default priority
            if priority is None:
                cursor.execute("SELECT COALESCE(MAX(priority), 0) + 1 as next_prio FROM notification_devices")
                assigned_prio = cursor.fetchone()["next_prio"]
            else:
                assigned_prio = priority

            cursor.execute("""
                INSERT INTO notification_devices (
                    device_id, user_name, fcm_token, device_name, platform,
                    priority, active, last_seen, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
            """, (device_id, user_name, fcm_token, device_name, platform, assigned_prio, now_iso, now_iso, now_iso))
            conn.commit()
            log_system_event("DEVICE", f"Registered new notification device '{device_name}' ({user_name}, Priority #{assigned_prio})")

        return get_device_by_id(device_id) or {}


def get_all_devices(active_only: bool = False) -> List[Dict[str, Any]]:
    """Retrieve all registered notification devices sorted by priority."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        where_sql = "WHERE active = 1" if active_only else ""
        cursor.execute(f"""
            SELECT id, device_id, user_name, fcm_token, device_name, platform,
                   priority, active, last_seen, created_at, updated_at
            FROM notification_devices
            {where_sql}
            ORDER BY priority ASC, id ASC
        """)
        rows = [dict(r) for r in cursor.fetchall()]
        for r in rows:
            r["masked_token"] = mask_fcm_token(r.get("fcm_token", ""))
        return rows


def get_device_by_id(device_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve a single device by its device_id string."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, device_id, user_name, fcm_token, device_name, platform,
                   priority, active, last_seen, created_at, updated_at
            FROM notification_devices
            WHERE device_id = ?
        """, (device_id,))
        row = cursor.fetchone()
        if row:
            d = dict(row)
            d["masked_token"] = mask_fcm_token(d.get("fcm_token", ""))
            return d
        return None


def delete_device(device_id: str) -> bool:
    """Delete a registered device."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM notification_devices WHERE device_id = ?", (device_id,))
        conn.commit()
        deleted = cursor.rowcount > 0
        if deleted:
            log_system_event("DEVICE", f"Deleted notification device '{device_id}'")
        return deleted


def reorder_devices(ordered_device_ids: List[str]) -> bool:
    """Update priority escalation order based on ordered list of device_ids."""
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        for idx, did in enumerate(ordered_device_ids, start=1):
            cursor.execute(
                "UPDATE notification_devices SET priority = ?, updated_at = ? WHERE device_id = ?",
                (idx, now_iso, did)
            )
        conn.commit()
        log_system_event("DEVICE", f"Reordered notification devices priorities: {ordered_device_ids}")
        return True


def touch_device_last_seen(device_id: str) -> bool:
    """Update last seen timestamp for heartbeat / network status."""
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE notification_devices SET last_seen = ? WHERE device_id = ?", (now_iso, device_id))
        conn.commit()
        return cursor.rowcount > 0


# ==============================================================================
# Notification Settings Management
# ==============================================================================

def get_notification_settings() -> Dict[str, Any]:
    """Retrieve push notification escalation settings."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT auto_push_enabled, push_timeout_seconds, max_retry_cycles,
                   min_alert_severity, cooldown_seconds
            FROM notification_settings WHERE id = 1
        """)
        row = cursor.fetchone()
        if row:
            return {
                "auto_push_enabled": bool(row["auto_push_enabled"]),
                "push_timeout_seconds": row["push_timeout_seconds"],
                "max_retry_cycles": row["max_retry_cycles"],
                "min_alert_severity": row["min_alert_severity"],
                "cooldown_seconds": row["cooldown_seconds"]
            }
        return {
            "auto_push_enabled": True,
            "push_timeout_seconds": 30,
            "max_retry_cycles": 2,
            "min_alert_severity": "HIGH",
            "cooldown_seconds": 60
        }


def update_notification_settings(
    auto_push_enabled: Optional[bool] = None,
    push_timeout_seconds: Optional[int] = None,
    max_retry_cycles: Optional[int] = None,
    min_alert_severity: Optional[str] = None,
    cooldown_seconds: Optional[int] = None
) -> Dict[str, Any]:
    """Update notification escalation settings."""
    cur = get_notification_settings()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE notification_settings
            SET auto_push_enabled = ?,
                push_timeout_seconds = ?,
                max_retry_cycles = ?,
                min_alert_severity = ?,
                cooldown_seconds = ?
            WHERE id = 1
        """, (
            1 if (auto_push_enabled if auto_push_enabled is not None else cur["auto_push_enabled"]) else 0,
            push_timeout_seconds if push_timeout_seconds is not None else cur["push_timeout_seconds"],
            max_retry_cycles if max_retry_cycles is not None else cur["max_retry_cycles"],
            min_alert_severity if min_alert_severity is not None else cur["min_alert_severity"],
            cooldown_seconds if cooldown_seconds is not None else cur["cooldown_seconds"]
        ))
        conn.commit()
        log_system_event("SETTINGS", "Updated notification escalation settings")
        return get_notification_settings()


# ==============================================================================
# Security Alerts Management
# ==============================================================================

def create_security_alert(
    alert_code: Optional[str] = None,
    camera_id: int = 1,
    camera_name: str = "Main Shop Camera",
    event_type: str = "SUSPICIOUS_ACTIVITY",
    severity: str = "HIGH",
    status: str = "WAITING_ACK",
    snapshot_path: Optional[str] = None,
    motion_area: float = 0.0,
    created_at: Optional[str] = None,
    expires_at: Optional[str] = None,
    remote_snapshot_reference: Optional[str] = None,
    remote_snapshot_status: Optional[str] = None
) -> int:
    """Create a new high-priority security alert record with 60-second lifecycle."""
    now_dt = datetime.now(timezone.utc)
    now_iso = created_at or now_dt.isoformat()
    exp_iso = expires_at or (now_dt + timedelta(seconds=60)).isoformat()
    if not alert_code:
        alert_code = f"TRI-{now_dt.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4].upper()}"
    
    if remote_snapshot_status is None:
        remote_snapshot_status = "UPLOADING" if snapshot_path else "NONE"

    with get_db_connection() as conn:
        cursor = conn.cursor()
        for attempt in range(5):
            code = alert_code if attempt == 0 else f"{alert_code}-{uuid.uuid4().hex[:4].upper()}"
            try:
                cursor.execute("""
                    INSERT INTO security_alerts (
                        alert_code, camera_id, camera_name, event_type, severity,
                        status, snapshot_path, motion_area, created_at, expires_at, last_attempt_at,
                        remote_snapshot_reference, remote_snapshot_status
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    code, camera_id, camera_name, event_type, severity,
                    status, snapshot_path, float(motion_area), now_iso, exp_iso, now_iso,
                    remote_snapshot_reference, remote_snapshot_status
                ))
                conn.commit()
                alert_id = cursor.lastrowid
                log_system_event("ALERT", f"Security Alert created: {code} ({severity}) on Camera #{camera_id}")
                return alert_id
            except sqlite3.IntegrityError:
                if attempt == 4:
                    raise


def update_alert_remote_snapshot(
    alert_id_or_code: Union[int, str],
    remote_reference: Optional[str],
    status: str = "AVAILABLE",
    remote_url: Optional[str] = None,
    remote_provider: str = "supabase"
) -> bool:
    """Update remote snapshot reference, status, URL and provider for an alert."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if isinstance(alert_id_or_code, int) or (isinstance(alert_id_or_code, str) and str(alert_id_or_code).isdigit()):
            cursor.execute("""
                UPDATE security_alerts
                SET remote_snapshot_reference = ?,
                    remote_snapshot_status = ?,
                    remote_url = ?,
                    remote_provider = ?
                WHERE id = ?
            """, (remote_reference, status, remote_url, remote_provider, int(alert_id_or_code)))
        else:
            cursor.execute("""
                UPDATE security_alerts
                SET remote_snapshot_reference = ?,
                    remote_snapshot_status = ?,
                    remote_url = ?,
                    remote_provider = ?
                WHERE alert_code = ?
            """, (remote_reference, status, remote_url, remote_provider, str(alert_id_or_code)))
        conn.commit()
        return cursor.rowcount > 0


def _format_alert_row(row: Union[sqlite3.Row, Dict[str, Any]]) -> Dict[str, Any]:
    """Format security alert dictionary with Alert ID and 8-hour snapshot metadata."""
    alert = dict(row)
    alert_code = alert.get("alert_code", "")
    alert["alert_id"] = alert_code
    alert["reason"] = alert.get("reason") or str(alert.get("event_type", "Motion detected")).replace("_", " ").title()

    snapshot_path = alert.get("snapshot_path")
    created_at = alert.get("created_at") or datetime.now(timezone.utc).isoformat()
    remote_reference = alert.get("remote_snapshot_reference")
    remote_status = alert.get("remote_snapshot_status") or ("AVAILABLE" if remote_reference else ("UPLOADING" if snapshot_path else None))
    remote_url = alert.get("remote_url")
    remote_provider = alert.get("remote_provider") or "supabase"

    if snapshot_path:
        snapshot_created_at = created_at
        try:
            snap_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            if snap_dt.tzinfo is None:
                snap_dt = snap_dt.replace(tzinfo=timezone.utc)
            snapshot_expires_at = (snap_dt + timedelta(hours=8)).isoformat()
        except Exception:
            snapshot_expires_at = (datetime.now(timezone.utc) + timedelta(hours=8)).isoformat()

        raw_status = alert.get("snapshot_status")
        if raw_status:
            snapshot_status = raw_status
        else:
            try:
                exp_dt = datetime.fromisoformat(snapshot_expires_at.replace("Z", "+00:00"))
                if datetime.now(timezone.utc) >= exp_dt:
                    snapshot_status = "EXPIRED"
                else:
                    snapshot_status = "AVAILABLE"
            except Exception:
                snapshot_status = "AVAILABLE"

        alert["snapshot_status"] = snapshot_status
        alert["snapshot_reference"] = snapshot_path
        alert["snapshot_created_at"] = snapshot_created_at
        alert["snapshot_expires_at"] = snapshot_expires_at
        alert["remote_provider"] = remote_provider
        alert["remote_reference"] = remote_reference
        alert["remote_snapshot_reference"] = remote_reference
        alert["remote_snapshot_status"] = remote_status
        alert["remote_url"] = remote_url
        alert["signed_url"] = remote_url
        alert["snapshot"] = {
            "reference": snapshot_path,
            "local_reference": snapshot_path,
            "remote_reference": remote_reference,
            "remote_provider": remote_provider,
            "remote_status": remote_status,
            "remote_snapshot_status": remote_status,
            "remote_url": remote_url,
            "signed_url": remote_url,
            "path": snapshot_path,
            "created_at": snapshot_created_at,
            "expires_at": snapshot_expires_at,
            "status": "UPLOADING" if remote_status == "UPLOADING" else snapshot_status,
            "alert_id": alert_code
        }
    else:
        try:
            snap_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            if snap_dt.tzinfo is None:
                snap_dt = snap_dt.replace(tzinfo=timezone.utc)
            snapshot_expires_at = (snap_dt + timedelta(hours=8)).isoformat()
        except Exception:
            snapshot_expires_at = (datetime.now(timezone.utc) + timedelta(hours=8)).isoformat()

        alert["snapshot_status"] = alert.get("snapshot_status") or "MISSING"
        alert["snapshot_reference"] = None
        alert["snapshot_created_at"] = created_at
        alert["snapshot_expires_at"] = snapshot_expires_at
        alert["remote_provider"] = remote_provider
        alert["remote_reference"] = remote_reference
        alert["remote_snapshot_reference"] = remote_reference
        alert["remote_snapshot_status"] = remote_status
        alert["remote_url"] = remote_url
        alert["signed_url"] = remote_url
        alert["snapshot"] = None

    return alert


def get_alert_by_id(alert_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve security alert by internal ID."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM security_alerts WHERE id = ?", (alert_id,))
        row = cursor.fetchone()
        return _format_alert_row(row) if row else None


def get_alert_by_code(alert_code: str) -> Optional[Dict[str, Any]]:
    """Retrieve security alert by code (e.g. TRI-20260929-125430-A7F2)."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM security_alerts WHERE alert_code = ?", (alert_code,))
        row = cursor.fetchone()
        return _format_alert_row(row) if row else None


def get_alert_by_id_or_code(identifier: Union[int, str]) -> Optional[Dict[str, Any]]:
    """Retrieve security alert by ID (int) or code (str)."""
    if isinstance(identifier, int) or (isinstance(identifier, str) and identifier.isdigit()):
        alert = get_alert_by_id(int(identifier))
        if alert:
            return alert
    return get_alert_by_code(str(identifier))


def cleanup_stale_alerts() -> int:
    """Mark any unacknowledged dangling alerts from a prior server run as CLOSED_ON_STARTUP."""
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE security_alerts
            SET status = 'CLOSED_ON_STARTUP', last_attempt_at = ?
            WHERE status IN ('WAITING_ACK', 'ESCALATING', 'NOTIFYING', 'ACTIVE')
        """, (now_iso,))
        conn.commit()
        cnt = cursor.rowcount
        if cnt > 0:
            log_system_event("ALERT_CLEANUP", f"Cleaned up {cnt} stale active alerts on startup")
        return cnt


def get_active_alert() -> Optional[Dict[str, Any]]:
    """
    Retrieve the most recent unresolved/in-progress security alert if any.
    Automatically enforces minimum 60-second visibility window from creation.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM security_alerts
            WHERE status IN ('WAITING_ACK', 'ESCALATING', 'NOTIFYING', 'ACTIVE', 'ACKNOWLEDGED', 'SILENCED')
            ORDER BY id DESC LIMIT 1
        """)
        row = cursor.fetchone()
        if not row:
            return None

        alert = dict(row)
        now_dt = datetime.now(timezone.utc)
        is_expired = False

        expires_at_str = alert.get("expires_at")
        if expires_at_str:
            try:
                clean_exp = expires_at_str.replace("Z", "+00:00")
                exp_dt = datetime.fromisoformat(clean_exp)
                if exp_dt.tzinfo is None:
                    exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                if now_dt >= exp_dt:
                    is_expired = True
            except Exception:
                pass
        else:
            created_at_str = alert.get("created_at")
            if created_at_str:
                try:
                    clean_crt = created_at_str.replace("Z", "+00:00")
                    crt_dt = datetime.fromisoformat(clean_crt)
                    if crt_dt.tzinfo is None:
                        crt_dt = crt_dt.replace(tzinfo=timezone.utc)
                    if (now_dt - crt_dt).total_seconds() >= 60.0:
                        is_expired = True
                except Exception:
                    pass

        if is_expired:
            if alert.get("status") in ('WAITING_ACK', 'ESCALATING', 'NOTIFYING', 'ACTIVE'):
                cursor.execute("""
                    UPDATE security_alerts
                    SET status = 'EXPIRED', last_attempt_at = ?
                    WHERE id = ?
                """, (now_dt.isoformat(), alert["id"]))
                conn.commit()
                log_system_event("ALERT_EXPIRED", f"Active alert {alert.get('alert_code')} auto-expired at query time")
            return None

        return _format_alert_row(alert)


def get_recent_alerts(limit: int = 20) -> List[Dict[str, Any]]:
    """Retrieve list of recent security alerts with push delivery summaries."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT a.*,
                   COUNT(p.id) as total_push_deliveries,
                   SUM(CASE WHEN p.acknowledged = 1 THEN 1 ELSE 0 END) as ack_count
            FROM security_alerts a
            LEFT JOIN push_deliveries p ON a.id = p.alert_id
            GROUP BY a.id
            ORDER BY a.id DESC LIMIT ?
        """, (limit,))
        return [_format_alert_row(r) for r in cursor.fetchall()]


def get_latest_alert_for_camera(camera_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve latest alert created for a camera to verify cooldown."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM security_alerts
            WHERE camera_id = ?
            ORDER BY id DESC LIMIT 1
        """, (camera_id,))
        row = cursor.fetchone()
        return _format_alert_row(row) if row else None



def update_alert_status(
    alert_id: int,
    status: str,
    retry_count: Optional[int] = None,
    last_attempt_at: Optional[str] = None
) -> bool:
    """Update security alert escalation state."""
    now_iso = last_attempt_at or datetime.now(timezone.utc).isoformat()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if retry_count is not None:
            cursor.execute("""
                UPDATE security_alerts
                SET status = ?, retry_count = ?, last_attempt_at = ?
                WHERE id = ?
            """, (status, retry_count, now_iso, alert_id))
        else:
            cursor.execute("""
                UPDATE security_alerts
                SET status = ?, last_attempt_at = ?
                WHERE id = ?
            """, (status, now_iso, alert_id))
        conn.commit()
        return cursor.rowcount > 0


def acknowledge_alert(
    alert_id: int,
    acknowledged_by: str
) -> bool:
    """Mark alert as ACKNOWLEDGED and record responder (Android Device or Dashboard)."""
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE security_alerts
            SET status = 'ACKNOWLEDGED', acknowledged_at = ?, acknowledged_by = ?
            WHERE id = ?
        """, (now_iso, acknowledged_by, alert_id))
        conn.commit()
        updated = cursor.rowcount > 0
        if updated:
            log_system_event("ALERT_ACK", f"Alert #{alert_id} ACKNOWLEDGED by {acknowledged_by}")
        return updated


# ==============================================================================
# Push Deliveries & Notification Logs
# ==============================================================================

def record_push_delivery(
    device_id: str,
    user_name: str,
    device_name: str,
    alert_id: Optional[int] = None,
    alert_code: str = "",
    fcm_message_id: str = "",
    status: str = "SENT",
    is_test: bool = False
) -> int:
    """Record an FCM push notification dispatch in database."""
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO push_deliveries (
                alert_id, alert_code, device_id, user_name, device_name,
                fcm_message_id, status, sent_at, acknowledged, is_test
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
        """, (
            alert_id, alert_code, device_id, user_name, device_name,
            fcm_message_id, status, now_iso, 1 if is_test else 0
        ))
        conn.commit()
        delivery_id = cursor.lastrowid
        test_tag = " (TEST NOTIFICATION)" if is_test else ""
        log_system_event("PUSH_DELIVERY", f"Push #{delivery_id} sent to {user_name} [{device_name}]{test_tag}")
        return delivery_id


def update_push_delivery(
    delivery_id: int,
    status: str,
    acknowledged: Optional[bool] = None,
    error_message: Optional[str] = None
) -> bool:
    """Update push delivery record."""
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        updates = ["status = ?"]
        params: List[Any] = [status]

        if acknowledged is not None:
            updates.append("acknowledged = ?")
            params.append(1 if acknowledged else 0)
            if acknowledged:
                updates.append("acknowledged_at = ?")
                params.append(now_iso)

        if error_message is not None:
            updates.append("error_message = ?")
            params.append(error_message)

        params.append(delivery_id)
        cursor.execute(f"UPDATE push_deliveries SET {', '.join(updates)} WHERE id = ?", params)
        conn.commit()
        return cursor.rowcount > 0


def get_deliveries_by_alert(alert_id: int) -> List[Dict[str, Any]]:
    """Retrieve all push deliveries for an alert."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM push_deliveries
            WHERE alert_id = ?
            ORDER BY id ASC
        """, (alert_id,))
        return [dict(r) for r in cursor.fetchall()]


def get_push_history(
    page: int = 1,
    page_size: int = 50,
    alert_id: Optional[int] = None,
    status: Optional[str] = None
) -> Dict[str, Any]:
    """Retrieve paginated push notification delivery logs."""
    page = max(1, page)
    page_size = max(1, min(100, page_size))
    offset = (page - 1) * page_size

    where_clauses = []
    params: List[Any] = []

    if alert_id is not None:
        where_clauses.append("alert_id = ?")
        params.append(alert_id)
    if status:
        where_clauses.append("status = ?")
        params.append(status)

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT COUNT(*) as total FROM push_deliveries {where_sql}", params)
        total = cursor.fetchone()["total"]

        cursor.execute(f"""
            SELECT id, alert_id, alert_code, device_id, user_name, device_name,
                   fcm_message_id, status, error_message, sent_at, acknowledged,
                   acknowledged_at, is_test
            FROM push_deliveries
            {where_sql}
            ORDER BY id DESC
            LIMIT ? OFFSET ?
        """, params + [page_size, offset])
        rows = [dict(r) for r in cursor.fetchall()]

        total_pages = max(1, math.ceil(total / page_size))
        return {
            "items": rows,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages
        }


# Automatically ensure database tables and migrations are initialized
try:
    init_db()
except Exception as _e:
    pass

