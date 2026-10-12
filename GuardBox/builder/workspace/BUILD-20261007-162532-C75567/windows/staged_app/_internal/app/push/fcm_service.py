"""
Veronic GuardBox — Firebase Cloud Messaging (FCM) Service
Handles high-priority Android emergency push alert dispatching.
"""

import os
import json
import uuid
import logging
import urllib.request
import urllib.error
from typing import Dict, Any, Optional, List, Union
from datetime import datetime, timezone, timedelta
from app.config import settings

logger = logging.getLogger("guardbox.fcm")


def cleanup_invalid_token(fcm_token: str) -> None:
    """Safely removes an invalid or unregistered FCM token from Firebase and local database."""
    if not fcm_token or len(fcm_token) < 5:
        return
    # 1. Clean from Firebase RTDB guardbox/notification_tokens
    try:
        import firebase_admin
        from firebase_admin import db
        if firebase_admin._apps:
            tokens_tree = db.reference("guardbox/notification_tokens").get()
            if isinstance(tokens_tree, dict):
                for uid, token_map in tokens_tree.items():
                    if isinstance(token_map, dict):
                        for tid, tdata in token_map.items():
                            if isinstance(tdata, dict) and tdata.get("token") == fcm_token:
                                db.reference(f"guardbox/notification_tokens/{uid}/{tid}").delete()
                                logger.info(f"[FCM CLEANUP] Removed invalid token from Firebase (UID: {uid}, TokenID: {tid})")
    except Exception as e:
        logger.debug(f"[FCM CLEANUP] Firebase token deletion notice: {e}")

    # 2. Deactivate in local SQLite database
    try:
        from app.database import get_db_connection
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE notification_devices SET active = 0 WHERE fcm_token = ?", (fcm_token,))
            conn.commit()
            logger.info(f"[FCM CLEANUP] Deactivated invalid token in local database")
    except Exception as e:
        logger.debug(f"[FCM CLEANUP] Local DB token deactivation notice: {e}")


class FCMService:
    """
    Firebase Cloud Messaging Dispatcher.
    Constructs high-priority push payloads with wake-up signals, siren sound,
    vibration channels, and full-screen intent triggers for Android.
    """

    def __init__(self):
        self._last_dispatched_payloads: List[Dict[str, Any]] = []

    @property
    def is_configured(self) -> bool:
        return settings.is_fcm_configured()

    def send_emergency_alert(
        self,
        fcm_token: str,
        alert_id: Union[int, str],
        alert_code: str,
        camera_name: str,
        event_type: str,
        severity: str,
        timestamp: str,
        expires_at: Optional[str] = None,
        snapshot_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send a high-priority emergency security alert to an Android device.
        Wakes device, plays custom siren sound, and launches full-screen alert.
        """
        title = "🚨 TRINETRA SECURITY ALERT"
        body = f"Threat: {event_type.replace('_', ' ').title()} | Camera: {camera_name}"
        alert_id_str = alert_code if alert_code else str(alert_id)
        now_utc = datetime.now(timezone.utc)
        exp_at_str = expires_at or (now_utc + timedelta(seconds=60)).isoformat()
        snap_created = timestamp or now_utc.isoformat()
        try:
            clean_ts = snap_created.replace("Z", "+00:00")
            dt_ts = datetime.fromisoformat(clean_ts)
            if dt_ts.tzinfo is None:
                dt_ts = dt_ts.replace(tzinfo=timezone.utc)
            snap_exp = (dt_ts + timedelta(hours=8)).isoformat()
        except Exception:
            snap_exp = (now_utc + timedelta(hours=8)).isoformat()

        payload = {
            "to": fcm_token,
            "priority": "high",
            "time_to_live": 60,
            "notification": {
                "title": title,
                "body": body,
                "sound": "guardbox_emergency_alert",
                "android_channel_id": "guardbox_security_alerts",
                "click_action": "FLUTTER_NOTIFICATION_CLICK"
            },
            "data": {
                "type": "SECURITY_ALERT",
                "alert_id": alert_id_str,
                "alert_code": alert_code or alert_id_str,
                "device_id": settings.GUARDBOX_DEVICE_ID or "guardbox-shop-f20424b4",
                "camera_name": camera_name,
                "reason": event_type.replace('_', ' ').title(),
                "event_type": event_type,
                "severity": severity,
                "created_at": timestamp,
                "expires_at": exp_at_str,
                "timestamp": timestamp,
                "snapshot_url": snapshot_url or "",
                "snapshot_reference": snapshot_url or "",
                "snapshot_path": snapshot_url or "",
                "snapshot_created_at": snap_created,
                "snapshot_expires_at": snap_exp,
                "full_screen_intent": "true",
                "requires_ack": "true"
            }
        }

        return self._dispatch(fcm_token, payload, is_emergency=True)

    def send_test_notification(
        self,
        fcm_token: str,
        device_name: str
    ) -> Dict[str, Any]:
        """
        Send a safe, non-emergency test push notification to verify Android connectivity.
        """
        title = "GuardBox — Device Connection Test"
        body = f"Notification verified successfully on {device_name}. No security threat."

        payload = {
            "to": fcm_token,
            "priority": "normal",
            "notification": {
                "title": title,
                "body": body,
                "sound": "default",
                "android_channel_id": "guardbox_info_channel"
            },
            "data": {
                "type": "TEST_NOTIFICATION",
                "alert_id": "test_notification",
                "device_id": settings.GUARDBOX_DEVICE_ID or "guardbox-shop-f20424b4",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "device_name": device_name
            }
        }

        return self._dispatch(fcm_token, payload, is_emergency=False)

    def _dispatch(self, fcm_token: str, payload: Dict[str, Any], is_emergency: bool = True) -> Dict[str, Any]:
        """Internal dispatch mechanism with live FCM Admin SDK and safe mock fallback."""
        masked_token = fcm_token[:6] + "••••" if len(fcm_token) >= 10 else "••••"
        self._last_dispatched_payloads.append(payload)

        # 1. Live FCM Dispatch via Firebase Admin SDK (Recommended for Firebase v1 API)
        try:
            import firebase_admin
            from firebase_admin import messaging

            if firebase_admin._apps:
                data_dict = {str(k): str(v) for k, v in payload.get("data", {}).items()}
                channel_id = "guardbox_security_alerts" if is_emergency else "guardbox_info_channel"
                sound_name = "guardbox_emergency_alert" if is_emergency else "default"

                msg = messaging.Message(
                    token=fcm_token,
                    notification=messaging.Notification(
                        title=payload["notification"]["title"],
                        body=payload["notification"]["body"]
                    ),
                    data=data_dict,
                    android=messaging.AndroidConfig(
                        priority="high" if is_emergency else "normal",
                        ttl=timedelta(seconds=60) if is_emergency else timedelta(hours=24),
                        notification=messaging.AndroidNotification(
                            channel_id=channel_id,
                            sound=sound_name,
                            priority="max" if is_emergency else "default",
                            default_vibrate_timings=True
                        )
                    )
                )

                message_id = messaging.send(msg)
                logger.info(f"[FCM ADMIN] Push sent successfully to {masked_token} — Message ID: {message_id}")
                return {
                    "success": True,
                    "fcm_message_id": message_id,
                    "error": None,
                    "status": "SENT"
                }
        except Exception as admin_ex:
            err_str = str(admin_ex)
            logger.warning(f"[FCM ADMIN] Admin SDK push dispatch notice: {err_str}")

            is_invalid = any(k in err_str for k in [
                "NotRegistered",
                "not a valid FCM registration token",
                "InvalidArgumentError",
                "UnregisteredError",
                "invalid-registration-token",
                "registration-token-not-registered"
            ])
            if is_invalid:
                cleanup_invalid_token(fcm_token)

            return {
                "success": False,
                "fcm_message_id": "",
                "error": err_str,
                "status": "FAILED",
                "invalid_token": is_invalid
            }

        # 2. Live FCM Dispatch if Server Key is configured (Legacy HTTP API fallback)
        if settings.FCM_SERVER_KEY:
            try:
                headers = {
                    "Authorization": f"key={settings.FCM_SERVER_KEY}",
                    "Content-Type": "application/json"
                }
                req_data = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(
                    "https://fcm.googleapis.com/fcm/send",
                    data=req_data,
                    headers=headers,
                    method="POST"
                )

                with urllib.request.urlopen(req, timeout=10.0) as resp:
                    resp_json = json.loads(resp.read().decode("utf-8"))
                    message_id = resp_json.get("results", [{}])[0].get("message_id", f"fcm_msg_{uuid.uuid4().hex[:8]}")
                    logger.info(f"[FCM LIVE] Push sent to {masked_token} — Message ID: {message_id}")
                    return {
                        "success": True,
                        "fcm_message_id": message_id,
                        "error": None,
                        "status": "SENT"
                    }
            except urllib.error.HTTPError as he:
                err_msg = f"HTTP {he.code}: {he.reason}"
                try:
                    err_body = he.read().decode("utf-8")
                    err_msg = f"HTTP {he.code}: {err_body}"
                except Exception:
                    pass
                logger.error(f"[FCM ERROR] Failed to send push to {masked_token}: {err_msg}")
                return {
                    "success": False,
                    "fcm_message_id": "",
                    "error": err_msg,
                    "status": "FAILED"
                }
            except Exception as e:
                logger.error(f"[FCM ERROR] Connection error sending push to {masked_token}: {e}")
                return {
                    "success": False,
                    "fcm_message_id": "",
                    "error": str(e),
                    "status": "FAILED"
                }

        # 3. Local Mock Dispatcher (only when Firebase is completely unconfigured)
        mock_id = f"mock_fcm_msg_{uuid.uuid4().hex[:10]}"
        logger.info(f"[FCM MOCK] Simulated push delivery to {masked_token} — Mock ID: {mock_id} (Payload: {payload['notification']['title']})")
        return {
            "success": True,
            "fcm_message_id": mock_id,
            "error": None,
            "status": "SENT"
        }

    def get_last_dispatched_payload(self) -> Optional[Dict[str, Any]]:
        """Return the most recently dispatched FCM payload."""
        return self._last_dispatched_payloads[-1] if self._last_dispatched_payloads else None



fcm_service = FCMService()
