"""
Veronic GuardBox — Push Alert Escalation State Machine (Phase 3)
Manages sequential emergency notification escalation across registered Android devices,
anti-spam camera cooldowns, FCM dispatching, acknowledgement handling, and retry cycles.
"""

import time
import uuid
import logging
import threading
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List, Tuple, Union

from app.config import settings
from app.database import (
    get_all_devices,
    get_device_by_id,
    create_security_alert,
    get_alert_by_id,
    get_alert_by_code,
    get_alert_by_id_or_code,
    get_active_alert,
    get_recent_alerts,
    get_latest_alert_for_camera,
    update_alert_status,
    acknowledge_alert,
    record_push_delivery,
    update_push_delivery,
    get_deliveries_by_alert,
    get_notification_settings,
    log_system_event
)
from app.push.fcm_service import fcm_service

logger = logging.getLogger("guardbox.push_escalation")


def generate_alert_code() -> str:
    """Generate standardized unique Alert ID: e.g. TRI-20260929-125430-A7F2"""
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y%m%d-%H%M%S")
    random_suffix = uuid.uuid4().hex[:4].upper()
    return f"TRI-{date_str}-{random_suffix}"


class PushEscalationService:
    """
    Supervisor for sequential emergency push alert escalation and lifecycle management.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._camera_cooldowns: Dict[int, float] = {}
        self._active_alert_id: Optional[int] = None
        self._active_thread: Optional[threading.Thread] = None
        self._stop_escalation_flag: bool = False
        self._current_delivery_id: Optional[int] = None

    def get_status(self) -> Dict[str, Any]:
        """Return live escalation state for dashboard and Android telemetry."""
        with self._lock:
            active_alert = get_active_alert()
            is_escalating = (
                self._active_thread is not None
                and self._active_thread.is_alive()
                and active_alert is not None
            )
            devices = get_all_devices(active_only=True)
            deliveries = []
            if active_alert:
                deliveries = get_deliveries_by_alert(active_alert["id"])

            return {
                "is_escalating": is_escalating,
                "active_alert_id": active_alert["alert_code"] if active_alert else None,
                "active_alert_internal_id": active_alert["id"] if active_alert else None,
                "active_alert": active_alert,
                "registered_devices_count": len(devices),
                "recent_deliveries": deliveries,
                "fcm_configured": fcm_service.is_configured
            }

    def is_in_cooldown(self, camera_id: int) -> Tuple[bool, float]:
        """Check if camera is within anti-spam cooldown window."""
        cfg = get_notification_settings()
        cooldown_sec = cfg.get("cooldown_seconds", settings.ALERT_COOLDOWN_SECONDS)
        with self._lock:
            last_time = self._camera_cooldowns.get(camera_id, 0.0)
            elapsed = time.time() - last_time
            if elapsed < cooldown_sec:
                return True, round(cooldown_sec - elapsed, 1)
            return False, 0.0

    def handle_security_event(
        self,
        camera_id: int,
        camera_name: str,
        event_type: str,
        severity: str = "HIGH",
        snapshot_path: Optional[str] = None,
        motion_area: float = 0.0,
        force: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Entry point called when motion detector creates a confirmed event in ARMED mode.
        Checks severity thresholds, anti-spam cooldown, and starts push sequence.
        """
        cfg = get_notification_settings()
        if not cfg.get("auto_push_enabled", True) and not force:
            logger.info(f"Automatic push alerts are disabled in settings (Camera #{camera_id})")
            return None

        # Severity check (HIGH or CRITICAL)
        min_sev = cfg.get("min_alert_severity", "HIGH").upper()
        if severity.upper() != "CRITICAL" and severity.upper() != min_sev and not force:
            logger.info(f"Event severity '{severity}' is below threshold '{min_sev}' — skipping push escalation")
            return None

        # Cooldown check
        in_cooldown, remaining = self.is_in_cooldown(camera_id)
        if in_cooldown and not force:
            logger.info(f"Camera #{camera_id} is in escalation cooldown ({remaining}s remaining). Suppressing duplicate alert.")
            log_system_event("ANTI_SPAM", f"Suppressed duplicate alert for Camera #{camera_id} (Cooldown active: {remaining}s remaining)")
            return None

        with self._lock:
            self._camera_cooldowns[camera_id] = time.time()

        # Generate unique Alert Code: TRI-YYYYMMDD-HHMMSS-XXXX
        alert_code = generate_alert_code()
        now_dt = datetime.now(timezone.utc)
        created_at = now_dt.isoformat()
        expires_at = (now_dt + timedelta(seconds=60)).isoformat()

        alert_id = create_security_alert(
            alert_code=alert_code,
            camera_id=camera_id,
            camera_name=camera_name,
            event_type=event_type,
            severity=severity,
            status="WAITING_ACK",
            snapshot_path=snapshot_path,
            motion_area=motion_area,
            created_at=created_at,
            expires_at=expires_at
        )

        logger.info(
            f"[TRINETRA ALERT CREATED]\n"
            f"alert_id={alert_code}\n"
            f"camera={camera_name}\n"
            f"reason={event_type}\n"
            f"created_at={created_at}\n"
            f"expires_at={expires_at}"
        )

        logger.info(f"Starting Automatic Push Escalation for Alert {alert_code} (Camera: {camera_name})")
        self.start_escalation(alert_id)
        return get_alert_by_id(alert_id)

    def cleanup_stale_alerts_on_startup(self) -> int:
        """Close dangling active alerts on startup and ensure Firebase RTDB current alert is empty."""
        with self._lock:
            self._stop_escalation_flag = True
            self._active_alert_id = None
            self._active_thread = None

        from app.database import cleanup_stale_alerts
        cleaned = cleanup_stale_alerts()
        self._clear_firebase_current_alert()
        self.sync_recent_alerts_to_firebase_history()
        logger.info(f"[TRINETRA STARTUP CLEANUP] Cleaned {cleaned} dangling alerts, cleared Firebase active alert.")
        return cleaned

    def sync_recent_alerts_to_firebase_history(self, limit: int = 50) -> None:
        """Sync recent alerts from local SQLite to Firebase RTDB alert_history path."""
        try:
            import firebase_admin
            from firebase_admin import db
            if not firebase_admin._apps:
                return

            dev_id = settings.GUARDBOX_DEVICE_ID or "guardbox-shop-f20424b4"
            recent = get_recent_alerts(limit=limit)
            if not recent:
                return

            hist_ref = db.reference(f"guardbox/alert_history/{dev_id}")
            for a in recent:
                code = a.get("alert_code") or str(a.get("id"))
                if not code:
                    continue

                snap_ref = a.get("snapshot_reference") or a.get("snapshot_path")
                snap_path = a.get("snapshot_path")
                snap_created = a.get("snapshot_created_at") or a.get("created_at")
                snap_exp = a.get("snapshot_expires_at")
                snap_status = a.get("snapshot_status") or ("AVAILABLE" if snap_path else "UNAVAILABLE")
                rem_ref = a.get("remote_snapshot_reference")
                rem_status = a.get("remote_snapshot_status") or snap_status
                rem_url = a.get("remote_url")
                rem_prov = a.get("remote_provider") or "supabase"

                record = {
                    "alert_id": code,
                    "alert_code": code,
                    "device_id": dev_id,
                    "camera": a.get("camera_name", "Shop Camera"),
                    "camera_name": a.get("camera_name", "Shop Camera"),
                    "camera_id": str(a.get("camera_id", 1)),
                    "reason": str(a.get("event_type", "Motion detected")).replace("_", " ").title(),
                    "event_type": a.get("event_type", "SUSPICIOUS_MOTION"),
                    "severity": a.get("severity", "HIGH"),
                    "status": a.get("status", "ACTIVE"),
                    "created_at": a.get("created_at"),
                    "expires_at": a.get("expires_at"),
                    "snapshot_status": snap_status,
                    "snapshot_path": snap_path or "",
                    "snapshot_reference": snap_ref or "",
                    "snapshot_created_at": snap_created,
                    "snapshot_expires_at": snap_exp or "",
                    "remote_snapshot_reference": rem_ref,
                    "remote_reference": rem_ref,
                    "remote_snapshot_status": rem_status,
                    "remote_status": rem_status,
                    "remote_url": rem_url,
                    "signed_url": rem_url,
                    "remote_provider": rem_prov
                }
                hist_ref.child(code).update(record)
            logger.info(f"[TRINETRA HISTORY SYNC] Synced {len(recent)} alerts to Firebase RTDB alert_history")
        except Exception as e:
            logger.debug(f"Firebase RTDB alert_history sync notice: {e}")

    def start_escalation(self, alert_id: int) -> None:
        """Spawn background escalation thread."""
        with self._lock:
            self._stop_escalation_flag = False
            self._active_alert_id = alert_id
            self._active_thread = threading.Thread(
                target=self._run_escalation_loop,
                args=(alert_id,),
                daemon=True,
                name=f"PushEscalation-{alert_id}"
            )
            self._active_thread.start()

        # 2. Update current alert AND alert_history in Firebase Realtime Database IMMEDIATELY with initial state
        try:
            alert = get_alert_by_id(alert_id)
            if alert:
                dev_id = settings.GUARDBOX_DEVICE_ID or "guardbox-shop-f20424b4"
                alert_code = alert.get("alert_code", str(alert_id))
                created_at = alert.get("created_at", datetime.now(timezone.utc).isoformat())
                expires_at = alert.get("expires_at", (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat())

                snap_ref = alert.get("snapshot_reference") or alert.get("snapshot_path")
                snap_path = alert.get("snapshot_path")
                snap_created = alert.get("snapshot_created_at") or created_at
                snap_exp = alert.get("snapshot_expires_at")
                initial_remote_status = "UPLOADING" if snap_path else "NONE"

                logger.info(
                    f"[TRINETRA ACTIVE ALERT WRITE]\n"
                    f"alert_id={alert_code}\n"
                    f"device_id={dev_id}\n"
                    f"snapshot_ref={snap_ref}\n"
                    f"remote_ref=None\n"
                    f"remote_status={initial_remote_status}"
                )

                import firebase_admin
                from firebase_admin import db
                if firebase_admin._apps:
                    snapshot_obj = {
                        "status": "UPLOADING" if snap_path else "UNAVAILABLE",
                        "local_reference": snap_ref or "",
                        "remote_reference": None,
                        "reference": snap_ref or "",
                        "path": snap_path or "",
                        "created_at": snap_created,
                        "expires_at": snap_exp or "",
                        "alert_id": alert_code,
                        "remote_status": initial_remote_status,
                        "remote_snapshot_status": initial_remote_status
                    }

                    # Current active alert node
                    db.reference(f"guardbox/alerts/{dev_id}/current").set({
                        "alert_id": alert_code,
                        "alert_code": alert_code,
                        "device_id": dev_id,
                        "camera_id": str(alert.get("camera_id", 1)),
                        "camera_name": alert.get("camera_name", "Shop Camera"),
                        "reason": str(alert.get("event_type", "Motion detected")).replace("_", " ").title(),
                        "type": "SECURITY_ALERT",
                        "severity": alert.get("severity", "HIGH"),
                        "created_at": created_at,
                        "expires_at": expires_at,
                        "status": "ACTIVE",
                        "snapshot_reference": snap_ref or "",
                        "snapshot_path": snap_path or "",
                        "snapshot_created_at": snap_created,
                        "snapshot_expires_at": snap_exp or "",
                        "remote_snapshot_reference": None,
                        "remote_snapshot_status": initial_remote_status,
                        "snapshot": snapshot_obj
                    })

                    # Historical archive index node
                    db.reference(f"guardbox/alert_history/{dev_id}/{alert_code}").set({
                        "alert_id": alert_code,
                        "alert_code": alert_code,
                        "device_id": dev_id,
                        "camera": alert.get("camera_name", "Shop Camera"),
                        "camera_name": alert.get("camera_name", "Shop Camera"),
                        "camera_id": str(alert.get("camera_id", 1)),
                        "reason": str(alert.get("event_type", "Motion detected")).replace("_", " ").title(),
                        "event_type": alert.get("event_type", "SUSPICIOUS_MOTION"),
                        "severity": alert.get("severity", "HIGH"),
                        "status": "ACTIVE",
                        "created_at": created_at,
                        "expires_at": expires_at,
                        "snapshot_status": initial_remote_status,
                        "snapshot_path": snap_path or "",
                        "snapshot_reference": snap_ref or "",
                        "snapshot_created_at": snap_created,
                        "snapshot_expires_at": snap_exp or "",
                        "remote_snapshot_reference": None,
                        "remote_reference": None,
                        "remote_snapshot_status": initial_remote_status,
                        "remote_status": initial_remote_status,
                        "remote_url": None,
                        "signed_url": None,
                        "remote_provider": "supabase",
                        "snapshot": snapshot_obj
                    })

                # 3. Asynchronously upload snapshot copy to Supabase Storage in the background
                if snap_path:
                    threading.Thread(
                        target=self._async_upload_snapshot_worker,
                        args=(alert_id, alert_code, snap_path, dev_id, snap_ref, snap_created, snap_exp),
                        daemon=True,
                        name=f"SnapUpload-{alert_code}"
                    ).start()

                # 4. Asynchronously dispatch branded TRINETRA alert email with embedded logo
                try:
                    from app.email_service import email_alert_service
                    if email_alert_service.is_configured():
                        threading.Thread(
                            target=email_alert_service.send_security_alert_email,
                            kwargs={
                                "alert_code": alert_code,
                                "camera_name": alert.get("camera_name", "Shop Camera"),
                                "event_type": alert.get("event_type", "SUSPICIOUS_MOTION"),
                                "severity": alert.get("severity", "HIGH"),
                                "timestamp": alert.get("created_at"),
                                "motion_area": float(alert.get("motion_area", 0.0) or 0.0),
                                "snapshot_path": snap_path
                            },
                            daemon=True,
                            name=f"EmailAlert-{alert_code}"
                        ).start()
                except Exception as ee:
                    logger.debug(f"Email alert dispatch notice: {ee}")

        except Exception as e:
            logger.debug(f"Firebase RTDB alert sync notice: {e}")

    def _async_upload_snapshot_worker(
        self,
        alert_id: int,
        alert_code: str,
        snap_path: str,
        dev_id: str,
        snap_ref: Optional[str],
        snap_created: str,
        snap_exp: Optional[str]
    ) -> None:
        """Asynchronous background worker to optimize and upload snapshot to Supabase Storage."""
        remote_ref = None
        remote_status = "FAILED"
        remote_url = None

        # Calculate remaining retention duration for signed URL (up to 8 hours)
        remaining_sec = 28800
        if snap_exp:
            try:
                exp_dt = datetime.fromisoformat(snap_exp.replace("Z", "+00:00"))
                if exp_dt.tzinfo is None:
                    exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                diff = (exp_dt - datetime.now(timezone.utc)).total_seconds()
                if diff > 0:
                    remaining_sec = max(60, int(diff))
            except Exception:
                remaining_sec = 28800

        try:
            from app.supabase_storage import supabase_storage_service
            upload_res = supabase_storage_service.upload_alert_snapshot(
                alert_id=alert_code,
                local_snapshot_path=snap_path,
                device_id=dev_id,
                expires_in_seconds=remaining_sec
            )
            if upload_res and upload_res.get("remote_reference"):
                remote_ref = upload_res["remote_reference"]
                remote_status = "AVAILABLE"
                remote_url = upload_res.get("signed_url")
            else:
                remote_status = "FAILED"
        except Exception as e:
            logger.error(f"[TRINETRA SUPABASE ERROR]\nalert_id={alert_code}\nreason={e}")
            remote_status = "FAILED"

        # 1. Update SQLite record
        try:
            from app.database import update_alert_remote_snapshot
            update_alert_remote_snapshot(
                alert_id_or_code=alert_id,
                remote_reference=remote_ref,
                status=remote_status,
                remote_url=remote_url,
                remote_provider="supabase"
            )
        except Exception as dbe:
            logger.warning(f"Error persisting remote snapshot info in DB: {dbe}")

        # 2. Update Firebase RTDB current alert AND alert_history
        try:
            import firebase_admin
            from firebase_admin import db
            if firebase_admin._apps:
                ref = db.reference(f"guardbox/alerts/{dev_id}/current")
                curr = ref.get()
                if curr and isinstance(curr, dict) and curr.get("alert_id") == alert_code:
                    snapshot_obj = {
                        "status": "AVAILABLE" if remote_status == "AVAILABLE" else ("AVAILABLE" if snap_path else "UNAVAILABLE"),
                        "local_reference": snap_ref or "",
                        "remote_reference": remote_ref,
                        "reference": snap_ref or "",
                        "path": snap_path or "",
                        "created_at": snap_created,
                        "expires_at": snap_exp or "",
                        "alert_id": alert_code,
                        "remote_provider": "supabase",
                        "remote_status": remote_status,
                        "remote_snapshot_status": remote_status,
                        "remote_url": remote_url,
                        "signed_url": remote_url
                    }
                    ref.update({
                        "remote_provider": "supabase",
                        "remote_reference": remote_ref,
                        "remote_snapshot_reference": remote_ref,
                        "remote_snapshot_status": remote_status,
                        "remote_url": remote_url,
                        "signed_url": remote_url,
                        "snapshot": snapshot_obj
                    })
                    logger.info(f"[TRINETRA ASYNC SNAPSHOT UPDATED] alert_id={alert_code} remote_status={remote_status} remote_ref={remote_ref}")

                # Update history record in Firebase RTDB
                hist_ref = db.reference(f"guardbox/alert_history/{dev_id}/{alert_code}")
                snapshot_obj = {
                    "status": "AVAILABLE" if remote_status == "AVAILABLE" else ("AVAILABLE" if snap_path else "UNAVAILABLE"),
                    "local_reference": snap_ref or "",
                    "remote_reference": remote_ref,
                    "reference": snap_ref or "",
                    "path": snap_path or "",
                    "created_at": snap_created,
                    "expires_at": snap_exp or "",
                    "alert_id": alert_code,
                    "remote_provider": "supabase",
                    "remote_status": remote_status,
                    "remote_snapshot_status": remote_status,
                    "remote_url": remote_url,
                    "signed_url": remote_url
                }
                hist_ref.update({
                    "snapshot_status": remote_status,
                    "remote_snapshot_status": remote_status,
                    "remote_reference": remote_ref,
                    "remote_snapshot_reference": remote_ref,
                    "remote_url": remote_url,
                    "signed_url": remote_url,
                    "remote_provider": "supabase",
                    "snapshot": snapshot_obj
                })
        except Exception as rtdb_err:
            logger.debug(f"RTDB async snapshot update notice: {rtdb_err}")

    def retry_remote_snapshot_upload(self, alert_id_or_code: Union[int, str]) -> Dict[str, Any]:
        """Safe retry mechanism for failed remote snapshot uploads without creating new alerts or FCM."""
        logger.info(f"[TRINETRA SUPABASE] Retry started: alert_id={alert_id_or_code}")
        alert = get_alert_by_id_or_code(alert_id_or_code)
        if not alert:
            return {"success": False, "error": "Alert not found", "alert_id": str(alert_id_or_code)}

        # Retention check: verify snapshot is within 8-hour retention window
        snap_exp = alert.get("snapshot_expires_at")
        if snap_exp:
            try:
                exp_dt = datetime.fromisoformat(snap_exp.replace("Z", "+00:00"))
                if exp_dt.tzinfo is None:
                    exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) >= exp_dt:
                    return {
                        "success": False,
                        "error": "Snapshot has expired (8-hour retention period exceeded)",
                        "alert_id": alert.get("alert_code", str(alert_id_or_code))
                    }
            except Exception:
                pass

        if alert.get("snapshot_status") == "EXPIRED" or alert.get("remote_snapshot_status") == "EXPIRED":
            return {
                "success": False,
                "error": "Snapshot has expired (8-hour retention period exceeded)",
                "alert_id": alert.get("alert_code", str(alert_id_or_code))
            }

        snap_path = alert.get("snapshot_path")
        if not snap_path:
            return {"success": False, "error": "No local snapshot exists for this alert", "alert_id": alert.get("alert_code")}

        alert_id = alert["id"]
        alert_code = alert.get("alert_code", str(alert_id))
        dev_id = settings.GUARDBOX_DEVICE_ID or "guardbox-shop-f20424b4"
        snap_ref = alert.get("snapshot_reference") or snap_path
        snap_created = alert.get("snapshot_created_at") or alert.get("created_at") or datetime.now(timezone.utc).isoformat()

        # Mark UPLOADING in DB
        from app.database import update_alert_remote_snapshot
        update_alert_remote_snapshot(alert_id, None, "UPLOADING", remote_url=None, remote_provider="supabase")

        # Update RTDB if active and history
        try:
            import firebase_admin
            from firebase_admin import db
            if firebase_admin._apps:
                ref = db.reference(f"guardbox/alerts/{dev_id}/current")
                curr = ref.get()
                if curr and isinstance(curr, dict) and curr.get("alert_id") == alert_code:
                    ref.update({
                        "remote_snapshot_status": "UPLOADING",
                        "snapshot/remote_snapshot_status": "UPLOADING",
                        "snapshot/remote_status": "UPLOADING",
                        "snapshot/status": "UPLOADING",
                        "snapshot/remote_provider": "supabase"
                    })
                db.reference(f"guardbox/alert_history/{dev_id}/{alert_code}").update({
                    "snapshot_status": "UPLOADING",
                    "remote_snapshot_status": "UPLOADING",
                    "remote_status": "UPLOADING"
                })
        except Exception as ex:
            logger.debug(f"RTDB retry notice: {ex}")

        # Spawn background thread
        threading.Thread(
            target=self._async_upload_snapshot_worker,
            args=(alert_id, alert_code, snap_path, dev_id, snap_ref, snap_created, snap_exp),
            daemon=True,
            name=f"SnapRetryUpload-{alert_code}"
        ).start()

        return {"success": True, "alert_id": alert_code, "status": "UPLOADING"}

    def _clear_firebase_current_alert(self, alert_id_or_code: Optional[Any] = None) -> None:
        """Safely delete guardbox/alerts/{device_id}/current node in Firebase RTDB ONLY IF matching alert_id."""
        try:
            import firebase_admin
            from firebase_admin import db
            if firebase_admin._apps:
                dev_id = settings.GUARDBOX_DEVICE_ID or "guardbox-shop-f20424b4"
                ref = db.reference(f"guardbox/alerts/{dev_id}/current")
                if alert_id_or_code is not None:
                    curr = ref.get()
                    if curr and isinstance(curr, dict):
                        expected_str = str(alert_id_or_code)
                        curr_id = str(curr.get("alert_id", ""))
                        curr_code = str(curr.get("alert_code", ""))
                        if (curr_id and curr_id != expected_str) and (curr_code and curr_code != expected_str):
                            logger.info(
                                f"[TRINETRA ALERT FIREBASE CLEAR SKIPPED]\n"
                                f"reason=MISMATCH\n"
                                f"requested_id={expected_str}\n"
                                f"current_in_firebase={curr_id or curr_code}"
                            )
                            return
                ref.delete()
                target_log_id = str(alert_id_or_code) if alert_id_or_code is not None else "NONE"
                logger.info(
                    f"[TRINETRA ALERT FIREBASE CLEARED]\n"
                    f"alert_id={target_log_id}"
                )
        except Exception as e:
            logger.debug(f"Firebase RTDB alert clear notice: {e}")

    def stop_escalation(self, mark_status: Optional[str] = "SILENCED") -> None:
        """Signal active escalation loop to stop FCM dispatching."""
        stopped_id = None
        alert_code = None
        with self._lock:
            self._stop_escalation_flag = True
            stopped_id = self._active_alert_id

        if stopped_id:
            curr = get_alert_by_id(stopped_id)
            alert_code = curr.get("alert_code", str(stopped_id)) if curr else str(stopped_id)
            if mark_status and curr and curr.get("status") in ("WAITING_ACK", "ESCALATING", "NOTIFYING"):
                update_alert_status(stopped_id, status=mark_status)
            logger.info(
                f"[TRINETRA ALERT COMPLETED]\n"
                f"alert_id={alert_code}\n"
                f"reason={mark_status or 'STOPPED'}"
            )
            try:
                import firebase_admin
                from firebase_admin import db
                if firebase_admin._apps and mark_status:
                    dev_id = settings.GUARDBOX_DEVICE_ID or "guardbox-shop-f20424b4"
                    ref = db.reference(f"guardbox/alerts/{dev_id}/current")
                    curr_val = ref.get()
                    if curr_val and isinstance(curr_val, dict) and curr_val.get("alert_id") == alert_code:
                        ref.update({"status": mark_status})
                    db.reference(f"guardbox/alert_history/{dev_id}/{alert_code}").update({"status": mark_status})
            except Exception as rtdb_err:
                logger.debug(f"RTDB stop escalation notice: {rtdb_err}")

    def acknowledge(self, alert_id: int, acknowledged_by: str = "Android App") -> bool:
        """Mark alert as ACKNOWLEDGED and immediately stop active escalation loop."""
        curr = get_alert_by_id(alert_id)
        alert_code = curr.get("alert_code", str(alert_id)) if curr else str(alert_id)
        with self._lock:
            self._stop_escalation_flag = True
        success = acknowledge_alert(alert_id, acknowledged_by=acknowledged_by)
        if success:
            logger.info(f"Alert {alert_code} acknowledged by '{acknowledged_by}'. Escalation halted.")
            logger.info(
                f"[GUARDBOX ALERT COMPLETED]\n"
                f"alert_id={alert_code}\n"
                f"reason=ACKNOWLEDGED_BY_{acknowledged_by.upper().replace(' ', '_')}"
            )
            # Update Firebase RTDB current alert status to ACKNOWLEDGED to keep it visible for full 60s
            try:
                import firebase_admin
                from firebase_admin import db
                if firebase_admin._apps:
                    dev_id = settings.GUARDBOX_DEVICE_ID or "guardbox-shop-f20424b4"
                    ref = db.reference(f"guardbox/alerts/{dev_id}/current")
                    curr_val = ref.get()
                    if curr_val and isinstance(curr_val, dict) and curr_val.get("alert_id") == alert_code:
                        ref.update({
                            "status": "ACKNOWLEDGED",
                            "acknowledged_by": acknowledged_by,
                            "acknowledged_at": datetime.now(timezone.utc).isoformat()
                        })
                    db.reference(f"guardbox/alert_history/{dev_id}/{alert_code}").update({
                        "status": "ACKNOWLEDGED",
                        "acknowledged_by": acknowledged_by,
                        "acknowledged_at": datetime.now(timezone.utc).isoformat()
                    })
            except Exception as rtdb_err:
                logger.debug(f"RTDB ack status notice: {rtdb_err}")
        return success

    def send_test_push(self, device_id: str) -> Dict[str, Any]:
        """Dispatch a safe, non-emergency test push notification to a registered device."""
        device = get_device_by_id(device_id)
        if not device:
            raise ValueError(f"Device '{device_id}' not found")

        delivery_id = record_push_delivery(
            device_id=device["device_id"],
            user_name=device["user_name"],
            device_name=device["device_name"],
            alert_id=None,
            alert_code="TEST-PUSH",
            status="INITIATED",
            is_test=True
        )

        dev_id = settings.GUARDBOX_DEVICE_ID or "guardbox-shop-f20424b4"
        logger.info(
            f"[GUARDBOX FCM DISPATCH]\n"
            f"alert_id=test_push\n"
            f"device_id={dev_id}\n"
            f"reason=TEST_PUSH\n"
            f"token_count=1"
        )

        res = fcm_service.send_test_notification(
            fcm_token=device["fcm_token"],
            device_name=device["device_name"]
        )

        status_str = "DELIVERED" if res.get("success") else "FAILED"
        update_push_delivery(
            delivery_id=delivery_id,
            status=status_str,
            error_message=res.get("error")
        )

        log_system_event("TEST_PUSH", f"Sent test push notification to {device['user_name']} ({device['device_name']})")
        return {
            "success": res.get("success", False),
            "delivery_id": delivery_id,
            "device_id": device["device_id"],
            "device_name": device["device_name"],
            "user_name": device["user_name"],
            "status": status_str,
            "fcm_message_id": res.get("fcm_message_id", ""),
            "error": res.get("error")
        }

    def _run_escalation_loop(self, alert_id: int) -> None:
        """Sequential push notification loop executed in background with strict 60s visibility window."""
        alert = get_alert_by_id(alert_id)
        if not alert:
            logger.error(f"Cannot escalate non-existent Alert #{alert_id}")
            return

        alert_code = alert.get("alert_code", str(alert_id))
        start_epoch = time.time()
        max_duration = 60.0

        cfg = get_notification_settings()
        timeout_sec = cfg.get("push_timeout_seconds", 30)
        max_cycles = cfg.get("max_retry_cycles", 2)

        update_alert_status(alert_id, status="ESCALATING")
        log_system_event("ESCALATION_START", f"Push Escalation started for Alert {alert_code}")

        # FCM Notification Dispatch Loop
        for cycle in range(1, max_cycles + 1):
            if self._stop_escalation_flag:
                break

            if time.time() - start_epoch >= max_duration:
                break

            curr_alert = get_alert_by_id(alert_id)
            if not curr_alert or curr_alert.get("status") not in ("WAITING_ACK", "ESCALATING", "NOTIFYING"):
                logger.info(f"Escalation stopping for Alert {alert_code}: terminal status reached ({curr_alert.get('status') if curr_alert else 'DELETED'})")
                break

            # Discover registered notification devices
            devices = []
            seen_tokens = set()

            # 1. Remotely registered FCM tokens from Firebase RTDB
            try:
                import firebase_admin
                from firebase_admin import db
                if firebase_admin._apps:
                    tokens_tree = db.reference("guardbox/notification_tokens").get()
                    if isinstance(tokens_tree, dict):
                        for uid, token_entry in tokens_tree.items():
                            if isinstance(token_entry, dict):
                                direct_tok = token_entry.get("token")
                                if direct_tok and isinstance(direct_tok, str) and direct_tok not in seen_tokens:
                                    seen_tokens.add(direct_tok)
                                    devices.append({
                                        "device_id": token_entry.get("device_id", f"remote_{uid[:8]}"),
                                        "user_name": "GuardBox Remote User",
                                        "device_name": "Android Mobile Device",
                                        "fcm_token": direct_tok,
                                        "platform": token_entry.get("platform", "android"),
                                        "updated_at": token_entry.get("updated_at", ""),
                                        "priority": len(devices) + 1
                                    })
                                else:
                                    for tid, tdata in token_entry.items():
                                        if isinstance(tdata, dict):
                                            tok = tdata.get("token")
                                            if tok and isinstance(tok, str) and tok not in seen_tokens:
                                                seen_tokens.add(tok)
                                                devices.append({
                                                    "device_id": tdata.get("device_id", f"remote_{uid[:8]}"),
                                                    "user_name": "GuardBox Remote User",
                                                    "device_name": "Android Mobile Device",
                                                    "fcm_token": tok,
                                                    "platform": tdata.get("platform", "android"),
                                                    "updated_at": tdata.get("updated_at", ""),
                                                    "priority": len(devices) + 1
                                                })
            except Exception as e:
                logger.debug(f"Firebase token lookup notice: {e}")

            # 2. Local database devices
            local_devices = get_all_devices(active_only=True)
            for ld in local_devices:
                tok = ld.get("fcm_token")
                if tok and tok not in seen_tokens and not tok.startswith("local_lan_"):
                    seen_tokens.add(tok)
                    devices.append(ld)

            logger.info(f"FCM TOKENS FOUND = {len(devices)}")
            for idx, d in enumerate(devices):
                tok = d.get("fcm_token", "")
                logger.info(
                    f"Token #{idx + 1}: token_length={len(tok)}, device_id={d.get('device_id')}, "
                    f"platform={d.get('platform')}, updated_at={d.get('updated_at', '')}"
                )

            if not devices:
                logger.info(
                    f"No active notification devices registered for Alert {alert_code}. "
                    f"Alert remains active in Windows dashboard and Firebase RTDB for 60s lifecycle."
                )
                break

            logger.info(f"Escalation Cycle {cycle}/{max_cycles} for Alert {alert_code} ({len(devices)} devices)")

            for device in devices:
                if self._stop_escalation_flag:
                    break

                if time.time() - start_epoch >= max_duration:
                    break

                curr_alert = get_alert_by_id(alert_id)
                if not curr_alert or curr_alert.get("status") not in ("WAITING_ACK", "ESCALATING", "NOTIFYING"):
                    logger.info(f"Alert {alert_code} is in terminal status '{curr_alert.get('status') if curr_alert else 'DELETED'}'. Suppressing FCM dispatch.")
                    break

                # Record delivery
                delivery_id = record_push_delivery(
                    device_id=device["device_id"],
                    user_name=device["user_name"],
                    device_name=device["device_name"],
                    alert_id=alert_id,
                    alert_code=alert_code,
                    status="SENDING",
                    is_test=False
                )
                self._current_delivery_id = delivery_id

                # Dispatch FCM Emergency Alert
                logger.info(
                    f"[TRINETRA FCM DISPATCH]\n"
                    f"alert_id={alert_code}"
                )
                push_res = fcm_service.send_emergency_alert(
                    fcm_token=device["fcm_token"],
                    alert_id=alert_id,
                    alert_code=alert_code,
                    camera_name=alert.get("camera_name", "Shop Camera"),
                    event_type=alert.get("event_type", "SUSPICIOUS_MOTION"),
                    severity=alert.get("severity", "HIGH"),
                    timestamp=alert.get("created_at", datetime.now(timezone.utc).isoformat()),
                    expires_at=alert.get("expires_at"),
                    snapshot_url=alert.get("snapshot_path")
                )

                if push_res.get("success"):
                    update_push_delivery(
                        delivery_id=delivery_id,
                        status="DELIVERED",
                        error_message=None
                    )
                else:
                    update_push_delivery(
                        delivery_id=delivery_id,
                        status="FAILED",
                        error_message=push_res.get("error")
                    )

                # Wait for timeout window or acknowledgement (respecting 60s total ceiling)
                start_wait = time.time()
                while time.time() - start_wait < timeout_sec:
                    if self._stop_escalation_flag:
                        break
                    if time.time() - start_epoch >= max_duration:
                        break
                    curr_alert = get_alert_by_id(alert_id)
                    if curr_alert and curr_alert.get("status") in ("ACKNOWLEDGED", "SILENCED", "RESOLVED", "ESCALATION_FAILED", "EXPIRED"):
                        logger.info(f"Alert {alert_code} completed with status '{curr_alert.get('status')}'. Halting FCM push loop, maintaining 60s visibility.")
                        update_push_delivery(delivery_id=delivery_id, status=curr_alert.get("status"), acknowledged=(curr_alert.get("status") == "ACKNOWLEDGED"))
                        break
                    time.sleep(0.5)

                if self._stop_escalation_flag or (time.time() - start_epoch >= max_duration):
                    break

            update_alert_status(alert_id, status="ESCALATING", retry_count=cycle)

        # MANDATORY 60-SECOND VISIBILITY LIFECYCLE ENFORCEMENT
        # Alert MUST remain accessible in get_active_alert() and Firebase RTDB for full 60s
        logger.info(f"Escalation notification cycle completed for Alert {alert_code}. Maintaining active visibility for full 60s...")
        while time.time() - start_epoch < max_duration:
            with self._lock:
                if self._active_alert_id is not None and self._active_alert_id != alert_id:
                    logger.info(f"Newer alert #{self._active_alert_id} is active; yielding 60s visibility watcher for Alert #{alert_code}")
                    return
            time.sleep(0.5)

        # Authoritative 60-second window elapsed
        curr_alert = get_alert_by_id(alert_id)
        if curr_alert and curr_alert.get("status") in ("WAITING_ACK", "ESCALATING", "NOTIFYING", "ACTIVE"):
            update_alert_status(alert_id, status="EXPIRED")
            log_system_event("ALERT_EXPIRED", f"Alert {alert_code} reached 60-second limit without acknowledgment (EXPIRED).")
            logger.info(
                f"[TRINETRA ALERT EXPIRED]\n"
                f"alert_id={alert_code}"
            )
            try:
                import firebase_admin
                from firebase_admin import db
                if firebase_admin._apps:
                    dev_id = settings.GUARDBOX_DEVICE_ID or "guardbox-shop-f20424b4"
                    db.reference(f"guardbox/alert_history/{dev_id}/{alert_code}").update({"status": "EXPIRED"})
            except Exception:
                pass

        # Clear Firebase RTDB current alert node if it matches this alert
        self._clear_firebase_current_alert(alert_code)


push_escalation_service = PushEscalationService()

