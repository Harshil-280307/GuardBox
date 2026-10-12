"""
TRINETRA - 8-Hour Snapshot Retention & Cleanup Service (Phase 3)
Periodically cleans up server snapshot files older than their 8-hour expiration
associated with security alerts, while preserving the full alert database history.
"""

import os
import time
import logging
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List

from app.config import settings, BASE_DIR
from app.database import get_db_connection, log_system_event

logger = logging.getLogger("guardbox.cleanup")


class SnapshotCleanupService:
    def __init__(self, interval_seconds: int = 300):
        self.interval_seconds = interval_seconds
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._is_running = False

    def start(self) -> None:
        if self._is_running:
            return
        self._stop_event.clear()
        self._is_running = True
        self._thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name="SnapshotCleanupThread"
        )
        self._thread.start()
        logger.info(f"Snapshot cleanup service started (interval: {self.interval_seconds}s)")

    def stop(self) -> None:
        if not self._is_running:
            return
        self._stop_event.set()
        self._is_running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info("Snapshot cleanup service stopped")

    def _run_loop(self) -> None:
        # Run an initial cleanup pass on startup
        try:
            self.clean_expired_snapshots()
        except Exception as e:
            logger.error(f"Error during initial snapshot cleanup pass: {e}")

        while not self._stop_event.is_set():
            if self._stop_event.wait(timeout=self.interval_seconds):
                break
            try:
                self.clean_expired_snapshots()
            except Exception as e:
                logger.error(f"Error during periodic snapshot cleanup pass: {e}")

    def clean_expired_snapshots(self) -> Dict[str, Any]:
        """
        Safely scans security_alerts for records whose 8-hour retention has expired.
        Deletes the physical snapshot file from disk while leaving the alert record intact.
        Returns stats dict with deleted count.
        """
        now_utc = datetime.now(timezone.utc)
        deleted_count = 0
        inspected_count = 0

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, alert_code, snapshot_path, created_at, snapshot_status, remote_snapshot_reference, remote_snapshot_status
                FROM security_alerts
                WHERE (snapshot_path IS NOT NULL OR remote_snapshot_reference IS NOT NULL)
                  AND (snapshot_status IS NULL OR snapshot_status != 'EXPIRED' OR remote_snapshot_status != 'EXPIRED')
            """)
            alerts = cursor.fetchall()

            for row in alerts:
                alert_id = row["id"]
                alert_code = row["alert_code"]
                snapshot_path = row["snapshot_path"]
                created_at_str = row["created_at"]

                inspected_count += 1
                is_expired = False
                try:
                    if created_at_str:
                        clean_ts = created_at_str.replace("Z", "+00:00")
                        crt_dt = datetime.fromisoformat(clean_ts)
                        if crt_dt.tzinfo is None:
                            crt_dt = crt_dt.replace(tzinfo=timezone.utc)
                        exp_dt = crt_dt + timedelta(hours=8)
                        if now_utc >= exp_dt:
                            is_expired = True
                except Exception as ex:
                    logger.warning(f"Could not parse expiration for alert {alert_code}: {ex}")
                    continue

                if not is_expired:
                    continue

                # 1. Local disk file cleanup
                if snapshot_path:
                    filename = os.path.basename(snapshot_path)
                    target_file = os.path.join(settings.SNAPSHOT_DIRECTORY, filename)
                    alt_file = os.path.join(str(BASE_DIR), snapshot_path.replace("/", os.sep))

                    file_to_delete = target_file if os.path.exists(target_file) else (alt_file if os.path.exists(alt_file) else None)

                    if file_to_delete and os.path.exists(file_to_delete):
                        try:
                            os.remove(file_to_delete)
                            deleted_count += 1
                            logger.info(
                                f"[TRINETRA SNAPSHOT CLEANUP]\n"
                                f"alert_id={alert_code}\n"
                                f"action=DELETED\n"
                                f"path={snapshot_path}"
                            )
                        except Exception as err:
                            logger.error(
                                f"[TRINETRA SNAPSHOT CLEANUP]\n"
                                f"alert_id={alert_code}\n"
                                f"action=ERROR\n"
                                f"error={err}"
                            )
                    else:
                        logger.info(
                            f"[TRINETRA SNAPSHOT CLEANUP]\n"
                            f"alert_id={alert_code}\n"
                            f"action=ALREADY_MISSING\n"
                            f"path={snapshot_path}"
                        )

                # 2. Remote Supabase Storage evidence cleanup
                try:
                    from app.supabase_storage import supabase_storage_service
                    dev_id = settings.GUARDBOX_DEVICE_ID or "guardbox-shop-f20424b4"
                    supabase_storage_service.delete_alert_snapshot(alert_code, dev_id)
                except Exception as sbe:
                    logger.warning(f"Supabase Storage snapshot cleanup notice for alert {alert_code}: {sbe}")

                # 3. Update database record status without deleting the alert row
                cursor.execute("""
                    UPDATE security_alerts
                    SET snapshot_status = 'EXPIRED',
                        remote_snapshot_status = 'EXPIRED',
                        remote_url = NULL
                    WHERE id = ?
                """, (alert_id,))
                conn.commit()

                # 4. If this alert is currently published in Firebase RTDB or alert_history, reflect expired snapshot state
                try:
                    import firebase_admin
                    from firebase_admin import db
                    if firebase_admin._apps:
                        dev_id = settings.GUARDBOX_DEVICE_ID or "guardbox-shop-f20424b4"
                        ref = db.reference(f"guardbox/alerts/{dev_id}/current")
                        curr = ref.get()
                        if curr and isinstance(curr, dict) and curr.get("alert_id") == alert_code:
                            ref.update({
                                "snapshot_status": "EXPIRED",
                                "remote_snapshot_status": "EXPIRED",
                                "remote_url": None,
                                "signed_url": None,
                                "snapshot/status": "EXPIRED",
                                "snapshot/remote_status": "EXPIRED",
                                "snapshot/remote_snapshot_status": "EXPIRED",
                                "snapshot/remote_url": None,
                                "snapshot/signed_url": None
                            })
                        # Update alert_history record
                        hist_ref = db.reference(f"guardbox/alert_history/{dev_id}/{alert_code}")
                        hist_ref.update({
                            "snapshot_status": "EXPIRED",
                            "remote_snapshot_status": "EXPIRED",
                            "remote_url": None,
                            "signed_url": None
                        })
                except Exception as rtdb_ex:
                    logger.debug(f"RTDB cleanup notification notice: {rtdb_ex}")

        if deleted_count > 0:
            log_system_event("CLEANUP", f"Purged {deleted_count} expired snapshot(s) older than 8 hours")

        return {"deleted": deleted_count, "inspected": inspected_count}


snapshot_cleanup_service = SnapshotCleanupService(interval_seconds=300)


def clean_expired_snapshots() -> Dict[str, Any]:
    """Convenience module function for manual or test cleanup execution."""
    return snapshot_cleanup_service.clean_expired_snapshots()

