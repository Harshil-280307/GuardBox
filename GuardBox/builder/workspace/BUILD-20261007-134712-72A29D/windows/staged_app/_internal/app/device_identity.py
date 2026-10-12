"""
Veronic GuardBox / TRINETRA - Device Identity & Shop Binding Manager (Phase 5.9)
Manages persistent physical Device ID, Shop ID binding, Veronic administrator authentication,
and multi-shop Firebase RTDB presence & isolation.
"""

import os
import json
import time
import uuid
import hmac
import hashlib
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

from app.config import settings, BASE_DIR

logger = logging.getLogger("guardbox.device_identity")

DATA_DIR = BASE_DIR / "data"
IDENTITY_FILE = DATA_DIR / "device_identity.json"

# Secret salt for Veronic token generation (persisted in data dir if not set)
TOKEN_SECRET_FILE = DATA_DIR / "veronic_secret.key"


class DeviceIdentityManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._auth_failures: Dict[str, Tuple[int, float]] = {} # ip/user -> (attempts, last_attempt)
        self._active_tokens: Dict[str, float] = {} # token -> expires_at
        self._token_secret = self._load_or_create_token_secret()
        self._identity_cache = self.load_identity()

    def _load_or_create_token_secret(self) -> bytes:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if TOKEN_SECRET_FILE.exists():
            try:
                with open(TOKEN_SECRET_FILE, "rb") as f:
                    return f.read()
            except Exception:
                pass
        secret = uuid.uuid4().bytes + os.urandom(32)
        try:
            with open(TOKEN_SECRET_FILE, "wb") as f:
                f.write(secret)
        except Exception:
            pass
        return secret

    def load_identity(self) -> Dict[str, Any]:
        """
        Load persistent Device ID and Shop ID binding from disk.
        Preserves existing device_id if already present.
        """
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        default_device_id = settings.GUARDBOX_DEVICE_ID.strip() if settings.GUARDBOX_DEVICE_ID else ""
        default_shop_id = getattr(settings, "GUARDBOX_SHOP_ID", "SHOP-RK-001") or "SHOP-RK-001"
        default_shop_name = getattr(settings, "GUARDBOX_SHOP_NAME", "Rajkot Jewellery") or "Rajkot Jewellery"
        default_device_name = settings.GUARDBOX_DEVICE_NAME or "Shop Security Appliance"

        if IDENTITY_FILE.exists():
            try:
                with open(IDENTITY_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    device_id = data.get("device_id") or default_device_id
                    if not device_id:
                        device_id = f"guardbox-shop-{uuid.uuid4().hex[:8]}"
                    
                    identity = {
                        "device_id": device_id,
                        "shop_id": data.get("shop_id") or default_shop_id,
                        "shop_name": data.get("shop_name") or default_shop_name,
                        "device_name": data.get("device_name") or default_device_name,
                        "owner_id": data.get("owner_id", None),
                        "version": data.get("version", "1.0.0"),
                        "created_at": data.get("created_at") or datetime.now(timezone.utc).isoformat(),
                        "updated_at": data.get("updated_at") or datetime.now(timezone.utc).isoformat(),
                        "is_locked": True,
                        "is_configured": bool(data.get("shop_id") and data.get("shop_id") != "NOT_CONFIGURED")
                    }
                    return identity
            except Exception as e:
                logger.warning(f"Failed to read identity file: {e}")

        # If no identity file exists, generate or use existing configured ID
        if not default_device_id:
            default_device_id = f"guardbox-shop-{uuid.uuid4().hex[:8]}"

        identity = {
            "device_id": default_device_id,
            "shop_id": default_shop_id,
            "shop_name": default_shop_name,
            "device_name": default_device_name,
            "owner_id": None,
            "version": "1.0.0",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "is_locked": True,
            "is_configured": True
        }

        self.save_identity(identity)
        return identity

    def save_identity(self, identity: Dict[str, Any]) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        identity["updated_at"] = datetime.now(timezone.utc).isoformat()
        with open(IDENTITY_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "device_id": identity["device_id"],
                "shop_id": identity.get("shop_id", "SHOP-RK-001"),
                "shop_name": identity.get("shop_name", "Rajkot Jewellery"),
                "device_name": identity.get("device_name", settings.GUARDBOX_DEVICE_NAME),
                "owner_id": identity.get("owner_id"),
                "version": identity.get("version", "1.0.0"),
                "created_at": identity.get("created_at", datetime.now(timezone.utc).isoformat()),
                "updated_at": identity["updated_at"]
            }, f, indent=2)
        
        with self._lock:
            self._identity_cache = dict(identity)
            self._identity_cache["is_locked"] = True
            self._identity_cache["is_configured"] = bool(identity.get("shop_id") and identity.get("shop_id") != "NOT_CONFIGURED")

    def get_identity(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._identity_cache)

    # =========================================================================
    # Veronic Administrator Authentication (Phase 6)
    # =========================================================================

    def authenticate_veronic_admin(self, username: str, password: str, client_ip: str = "127.0.0.1") -> Tuple[bool, Optional[str], str]:
        """
        Verify administrator credentials against secure environment / Veronic secrets.
        Returns: (success: bool, token: Optional[str], message: str)
        """
        now = time.time()
        # Simple brute-force prevention: 5 failed attempts = 30-sec lockout
        with self._lock:
            attempts, last_time = self._auth_failures.get(client_ip, (0, 0.0))
            if attempts >= 5 and (now - last_time) < 30.0:
                remaining = int(30.0 - (now - last_time))
                return False, None, f"Too many failed authentication attempts. Please wait {remaining}s."

        admin_user = getattr(settings, "VERONIC_ADMIN_USER", "veronic_admin") or "veronic_admin"
        admin_secret = getattr(settings, "VERONIC_ADMIN_SECRET", "VeronicSecureAdmin2026!") or "VeronicSecureAdmin2026!"
        api_key = settings.GUARDBOX_API_KEY or ""

        # Check constant-time comparison for credentials
        user_valid = hmac.compare_digest(username.strip(), admin_user)
        pass_valid = hmac.compare_digest(password.strip(), admin_secret) or (bool(api_key) and hmac.compare_digest(password.strip(), api_key))

        if not (user_valid and pass_valid):
            with self._lock:
                self._auth_failures[client_ip] = (attempts + 1, now)
            logger.warning(f"Failed Veronic administrative authentication attempt from {client_ip} for user '{username}'")
            return False, None, "Invalid Administrator Username or Password."

        # Successful auth: reset failure counter and generate token
        with self._lock:
            self._auth_failures.pop(client_ip, None)
            
            # Generate temporary cryptographic token valid for 300s (5 minutes)
            expires_at = now + 300.0
            token_payload = f"{username}:{expires_at}:{uuid.uuid4().hex}"
            sig = hmac.new(self._token_secret, token_payload.encode("utf-8"), hashlib.sha256).hexdigest()
            token = f"VTK-{token_payload}-{sig[:16]}"
            self._active_tokens[token] = expires_at

        logger.info(f"Veronic administrative session authenticated successfully from {client_ip}. Session valid for 5 minutes.")
        return True, token, "Authentication successful."

    def verify_veronic_token(self, token: Optional[str]) -> bool:
        """Validate if the given Veronic admin token is active and not expired."""
        if not token:
            return False
        
        now = time.time()
        with self._lock:
            # Clean expired tokens
            self._active_tokens = {t: exp for t, exp in self._active_tokens.items() if exp > now}
            
            if token in self._active_tokens:
                return self._active_tokens[token] > now

        # Also support direct GUARDBOX_API_KEY if passed in header
        if settings.GUARDBOX_API_KEY and hmac.compare_digest(token.strip(), settings.GUARDBOX_API_KEY):
            return True

        return False

    def revoke_token(self, token: str) -> None:
        with self._lock:
            self._active_tokens.pop(token, None)

    # =========================================================================
    # Protected Identity Updates & Shop Binding (Phases 7, 9, 10)
    # =========================================================================

    def update_device_identity(
        self,
        new_device_id: Optional[str] = None,
        new_shop_id: Optional[str] = None,
        new_shop_name: Optional[str] = None,
        new_device_name: Optional[str] = None,
        owner_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Protected atomic update of Device Identity and Shop Binding.
        Updates local file, memory cache, and pushes to Firebase RTDB.
        """
        current = self.load_identity()
        old_device_id = current["device_id"]
        
        if new_device_id:
            clean_dev_id = new_device_id.strip()
            if len(clean_dev_id) < 3 or len(clean_dev_id) > 64:
                raise ValueError("Device ID must be between 3 and 64 characters.")
            current["device_id"] = clean_dev_id
        
        if new_shop_id:
            clean_shop_id = new_shop_id.strip()
            if len(clean_shop_id) < 2 or len(clean_shop_id) > 64:
                raise ValueError("Shop ID must be between 2 and 64 characters.")
            current["shop_id"] = clean_shop_id

        if new_shop_name:
            current["shop_name"] = new_shop_name.strip()

        if new_device_name:
            current["device_name"] = new_device_name.strip()

        if owner_id is not None:
            current["owner_id"] = owner_id.strip() if owner_id else None

        # Save to disk
        self.save_identity(current)
        
        # Update Firebase presence & shop mapping in background
        self._sync_identity_to_firebase(old_device_id, current)
        return self.get_identity()

    def _sync_identity_to_firebase(self, old_device_id: str, identity: Dict[str, Any]) -> None:
        """Publish updated identity and shop mapping to Firebase RTDB."""
        def _worker():
            try:
                import firebase_admin
                from firebase_admin import db
                if not firebase_admin._apps:
                    return

                dev_id = identity["device_id"]
                shop_id = identity.get("shop_id", "SHOP-RK-001")
                shop_name = identity.get("shop_name", "Rajkot Jewellery")
                owner_id = identity.get("owner_id")

                # 1. Update/Set device record at guardbox/devices/{dev_id} with actual system status
                from app.firebase_bridge import firebase_bridge
                current_st = firebase_bridge._get_current_system_status_str()
                dev_node = db.reference(f"guardbox/devices/{dev_id}")
                dev_payload = {
                    "device_id": dev_id,
                    "shop_id": shop_id,
                    "shop_name": shop_name,
                    "name": identity.get("device_name", "Shop Security Appliance"),
                    "owner_id": owner_id,
                    "online": True,
                    "status": current_st,
                    "last_seen": datetime.now(timezone.utc).isoformat(),
                    "version": identity.get("version", "1.0.0"),
                    "registered": True
                }
                dev_node.update(dev_payload)

                # 2. Update shop index mapping at guardbox/shops/{shop_id}
                shop_node = db.reference(f"guardbox/shops/{shop_id}")
                shop_node.child("devices").child(dev_id).set(True)
                shop_node.child("shop_name").set(shop_name)
                shop_node.child("shop_id").set(shop_id)
                if owner_id:
                    shop_node.child("owner_id").set(owner_id)

                # 3. If device_id changed, mark old device node as migrated and notify bridge
                if old_device_id and old_device_id != dev_id:
                    logger.info(f"Device ID transitioned from {old_device_id} to {dev_id}. Updating cloud presence.")
                    old_node = db.reference(f"guardbox/devices/{old_device_id}")
                    old_node.update({"online": False, "status": "MIGRATED", "migrated_to": dev_id})
                    firebase_bridge.update_device_id(dev_id)

                logger.info(f"[FIREBASE IDENTITY SYNC SUCCESS] device_id={dev_id}, shop_id={shop_id}, status={current_st}")
            except Exception as e:
                logger.warning(f"Firebase identity sync error: {e}")

        threading.Thread(target=_worker, daemon=True, name="firebase-identity-sync").start()


# Global Singleton
device_identity_manager = DeviceIdentityManager()
