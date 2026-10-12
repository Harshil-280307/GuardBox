"""
Veronic GuardBox - Configuration Module (Phase 3)
Manages environment variables, false alarm reduction parameters,
entry/exit delays, shop schedule, and FCM / Android Push Escalation parameters.
"""

import sys
import os
import re
from pathlib import Path
from urllib.parse import urlparse
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

# Base directory determination for frozen (PyInstaller executable) vs standard Python script
if getattr(sys, "frozen", False):
    # Standalone PyInstaller package root directory (where TRINETRA.exe, .env, config/ reside)
    BASE_DIR = Path(sys.executable).resolve().parent
    BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", BASE_DIR))
else:
    BASE_DIR = Path(__file__).resolve().parent.parent
    BUNDLE_DIR = BASE_DIR

# Determine .env location: check BASE_DIR, config subfolder, or current working dir
_env_candidates = [
    BASE_DIR / ".env",
    BASE_DIR / "config" / ".env",
    Path.cwd() / ".env"
]
ENV_FILE_PATH = next((p for p in _env_candidates if p.exists()), BASE_DIR / ".env")

# Load environment variables from .env file
load_dotenv(dotenv_path=ENV_FILE_PATH)


class Settings(BaseSettings):
    # RTSP stream URL (Keep private, never send credentials to client)
    RTSP_URL: str = os.getenv("RTSP_URL", "rtsp://username:password@192.168.31.108:554/stream1")

    # Motion Detection & False Alarm Reduction Parameters
    MOTION_SENSITIVITY: int = int(os.getenv("MOTION_SENSITIVITY", "25"))
    MIN_MOTION_AREA: int = int(os.getenv("MIN_MOTION_AREA", "500"))
    MOTION_COOLDOWN_SECONDS: float = float(os.getenv("MOTION_COOLDOWN_SECONDS", "5.0"))
    MOTION_PERSISTENCE_SECONDS: float = float(os.getenv("MOTION_PERSISTENCE_SECONDS", "1.0"))
    CAMERA_WARMUP_SECONDS: float = float(os.getenv("CAMERA_WARMUP_SECONDS", "3.0"))
    BLUR_SIZE: int = int(os.getenv("BLUR_SIZE", "9"))
    FRAME_SCALE: float = float(os.getenv("FRAME_SCALE", "0.5"))

    # Smart False-Alarm Reduction Filter (Phase 9)
    SMART_FILTER_ENABLED: bool = os.getenv("SMART_FILTER_ENABLED", "true").lower() in ("true", "1", "yes")
    SMART_FILTER_MIN_EDGE_DENSITY: float = float(os.getenv("SMART_FILTER_MIN_EDGE_DENSITY", "0.012"))
    SMART_FILTER_MAX_SPEED_RATIO: float = float(os.getenv("SMART_FILTER_MAX_SPEED_RATIO", "0.40"))
    SMART_FILTER_MIN_PERSON_HEIGHT_RATIO: float = float(os.getenv("SMART_FILTER_MIN_PERSON_HEIGHT_RATIO", "0.05"))
    SMART_FILTER_SHADOW_SUPPRESSION: bool = os.getenv("SMART_FILTER_SHADOW_SUPPRESSION", "true").lower() in ("true", "1", "yes")

    # Arming & Delay Configuration
    ENTRY_DELAY_SECONDS: int = int(os.getenv("ENTRY_DELAY_SECONDS", "15"))
    EXIT_DELAY_SECONDS: int = int(os.getenv("EXIT_DELAY_SECONDS", "15"))

    # File & Database Paths
    SNAPSHOT_DIRECTORY: str = os.getenv("SNAPSHOT_DIRECTORY", str(BASE_DIR / "snapshots"))
    DATABASE_PATH: str = os.getenv("DATABASE_PATH", str(BASE_DIR / "guardbox.db"))
    SNAPSHOT_RETENTION_DAYS: int = int(os.getenv("SNAPSHOT_RETENTION_DAYS", "30"))

    # Server Binding
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))

    # Camera Info (Static metadata for display)
    CAMERA_BRAND: str = "TP-Link Tapo"
    CAMERA_MODEL: str = "Tapo C100"

    # Firebase Cloud Bridge Configuration (Auth, Realtime Database, FCM)
    FIREBASE_CREDENTIALS_PATH: str = os.getenv("FIREBASE_CREDENTIALS_PATH", "")
    FIREBASE_DATABASE_URL: str = os.getenv("FIREBASE_DATABASE_URL", "")
    GUARDBOX_DEVICE_ID: str = os.getenv("GUARDBOX_DEVICE_ID", "")
    GUARDBOX_DEVICE_NAME: str = os.getenv("GUARDBOX_DEVICE_NAME", "Shop Security Appliance")
    GUARDBOX_SHOP_ID: str = os.getenv("GUARDBOX_SHOP_ID", "SHOP-RK-001")
    GUARDBOX_SHOP_NAME: str = os.getenv("GUARDBOX_SHOP_NAME", "Rajkot Jewellery")
    FCM_SERVER_KEY: str = os.getenv("FCM_SERVER_KEY", "")

    # Veronic Administrator Authentication (Phase 5.9)
    VERONIC_ADMIN_USER: str = os.getenv("VERONIC_ADMIN_USER", "veronic_admin")
    VERONIC_ADMIN_SECRET: str = os.getenv("VERONIC_ADMIN_SECRET", "VeronicSecureAdmin2026!")

    # Supabase Evidence Snapshot Storage Configuration (Phase 5.4)
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "https://idgtlvqzjnjbsorgtyao.supabase.co")
    SUPABASE_SECRET_KEY: str = os.getenv("SUPABASE_SECRET_KEY", "")
    SUPABASE_BUCKET: str = os.getenv("SUPABASE_BUCKET", "trinetra-snapshots")

    # Remote Access Authentication (X-GuardBox-Key)
    GUARDBOX_API_KEY: str = os.getenv("GUARDBOX_API_KEY", "")

    # Push Alert Escalation Defaults
    AUTO_PUSH_ENABLED: bool = os.getenv("AUTO_PUSH_ENABLED", "true").lower() in ("true", "1", "yes")
    PUSH_TIMEOUT_SECONDS: int = int(os.getenv("PUSH_TIMEOUT_SECONDS", "30"))
    MAX_RETRY_CYCLES: int = int(os.getenv("MAX_RETRY_CYCLES", "2"))
    MIN_ALERT_SEVERITY: str = os.getenv("MIN_ALERT_SEVERITY", "HIGH")
    ALERT_COOLDOWN_SECONDS: int = int(os.getenv("ALERT_COOLDOWN_SECONDS", "60"))

    # Email Alerting Configuration (Phase 6)
    EMAIL_NOTIFICATIONS_ENABLED: bool = os.getenv("EMAIL_NOTIFICATIONS_ENABLED", "false").lower() in ("true", "1", "yes")
    SMTP_HOST: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM: str = os.getenv("SMTP_FROM", "TRINETRA Security <alerts@trinetra-security.com>")
    SMTP_USE_TLS: bool = os.getenv("SMTP_USE_TLS", "true").lower() in ("true", "1", "yes")
    ALERT_RECIPIENT_EMAILS: str = os.getenv("ALERT_RECIPIENT_EMAILS", "")

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE_PATH),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def resolved_firebase_credentials_path(self) -> str:
        """Resolves the service account JSON path against BASE_DIR or config/ if relative."""
        raw_path = self.FIREBASE_CREDENTIALS_PATH.strip()
        if not raw_path:
            for cand in [BASE_DIR / "serviceAccountKey.json", BASE_DIR / "config" / "serviceAccountKey.json"]:
                if cand.exists():
                    return str(cand)
            return ""
        p = Path(raw_path)
        if p.is_absolute() and p.exists():
            return str(p)
        for cand in [BASE_DIR / raw_path, BASE_DIR / "config" / raw_path, Path.cwd() / raw_path]:
            if cand.exists():
                return str(cand)
        return str(BASE_DIR / raw_path)

    def is_fcm_configured(self) -> bool:
        """Check if Firebase Cloud Messaging credentials are configured."""
        return bool(self.FCM_SERVER_KEY or self.FIREBASE_CREDENTIALS_PATH)

    def is_supabase_configured(self) -> bool:
        """Check if Supabase Storage credentials and bucket are configured."""
        return bool(self.SUPABASE_URL and self.SUPABASE_SECRET_KEY and self.SUPABASE_BUCKET)

    def get_masked_fcm_key(self) -> str:
        """Mask FCM server key for safe diagnostics display."""
        key = self.FCM_SERVER_KEY
        if not key:
            return "Not Configured (Using Local Mock Dispatcher)"
        if len(key) <= 8:
            return key[:2] + "••••"
        return f"{key[:4]}••••••••{key[-4:]}"

    def get_masked_supabase_key(self) -> str:
        """Mask Supabase secret key for safe diagnostics display without leaking secrets."""
        key = self.SUPABASE_SECRET_KEY
        if not key:
            return "Not Configured"
        if len(key) <= 8:
            return key[:2] + "••••"
        return f"{key[:4]}••••••••{key[-4:]}"

    def get_safe_camera_ip(self) -> str:
        """Extract camera IP / hostname without revealing username or password."""
        try:
            parsed = urlparse(self.RTSP_URL)
            if parsed.hostname:
                return parsed.hostname
            match = re.search(r"@([^:/]+)", self.RTSP_URL)
            if match:
                return match.group(1)
            match_no_auth = re.search(r"rtsp://([^:/]+)", self.RTSP_URL)
            if match_no_auth:
                return match_no_auth.group(1)
        except Exception:
            pass
        return "192.168.31.108"

    def get_sanitized_rtsp_url(self) -> str:
        """Returns the RTSP URL with credentials masked for safe internal logging."""
        try:
            parsed = urlparse(self.RTSP_URL)
            if parsed.scheme and parsed.hostname:
                port_part = f":{parsed.port}" if parsed.port else ""
                path_part = parsed.path if parsed.path else ""
                return f"{parsed.scheme}://***:***@{parsed.hostname}{port_part}{path_part}"
        except Exception:
            pass
        return "rtsp://***:***@CAMERA_IP/stream"


# Global settings instance
settings = Settings()

# Ensure snapshot directory exists
os.makedirs(settings.SNAPSHOT_DIRECTORY, exist_ok=True)
