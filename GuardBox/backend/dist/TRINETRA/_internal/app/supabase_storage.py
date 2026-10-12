"""
TRINETRA - Supabase Storage Service (Phase 5.4)
Manages optimized evidence snapshot uploads, deterministic object paths,
duplicate prevention, secure time-limited signed URLs, and retention cleanup
in private Supabase Storage.
"""

import os
import re
import uuid
import time
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple

from app.config import settings, BASE_DIR

logger = logging.getLogger("guardbox.supabase_storage")

# Maximum upload size permitted by the Supabase bucket configuration (4 MB)
MAX_SNAPSHOT_SIZE_BYTES = 4 * 1024 * 1024  # 4 MB
DEFAULT_SIGNED_URL_DURATION_SECONDS = 28800  # 8 hours


class SupabaseStorageService:
    """
    Dedicated storage provider integrating TRINETRA evidence snapshots with Supabase Storage.
    """

    def __init__(self):
        self._client = None
        self._is_initialized = False

    def validate_configuration(self) -> Tuple[bool, Optional[str]]:
        """
        Validates Supabase configuration at startup without raising unhandled exceptions.
        Never exposes the secret key in log output.
        """
        url = settings.SUPABASE_URL
        key = settings.SUPABASE_SECRET_KEY
        bucket = settings.SUPABASE_BUCKET

        if not url:
            msg = "Missing SUPABASE_URL configuration"
            logger.warning(f"[TRINETRA SUPABASE WARNING] {msg}")
            return False, msg

        if not key:
            msg = "Missing SUPABASE_SECRET_KEY configuration (Standby Mode)"
            logger.warning(f"[TRINETRA SUPABASE WARNING] {msg}")
            return False, msg

        if not bucket:
            msg = "Missing SUPABASE_BUCKET configuration"
            logger.warning(f"[TRINETRA SUPABASE WARNING] {msg}")
            return False, msg

        # Validate URL format
        if not (url.startswith("http://") or url.startswith("https://")):
            msg = f"Invalid SUPABASE_URL scheme: must start with https:// ({url[:15]}...)"
            logger.warning(f"[TRINETRA SUPABASE WARNING] {msg}")
            return False, msg

        logger.info(
            f"[TRINETRA SUPABASE] Configuration validated\n"
            f"Project URL: {url}\n"
            f"Bucket: {bucket}\n"
            f"Secret Key: {settings.get_masked_supabase_key()}"
        )
        return True, None

    def get_client(self):
        """
        Initializes and returns the Supabase client instance.
        Returns None safely if credentials are not configured or invalid.
        """
        if self._client is not None:
            return self._client

        if not settings.is_supabase_configured():
            logger.debug("[TRINETRA SUPABASE] Supabase credentials not configured; client in standby mode.")
            return None

        try:
            from supabase import create_client
            self._client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SECRET_KEY)
            self._is_initialized = True
            return self._client
        except Exception as e:
            logger.error(f"[TRINETRA SUPABASE] Client initialization error: {e}")
            return None

    def get_object_path(self, alert_id: str, device_id: Optional[str] = None) -> str:
        """
        Generates deterministic object path:
        guardbox/evidence/{device_id}/{alert_id}.jpg
        """
        dev_id = (device_id or settings.GUARDBOX_DEVICE_ID or "guardbox-shop-f20424b4").strip()
        # Clean alert_id and dev_id of invalid path characters
        clean_alert_id = re.sub(r"[^\w\-.]", "_", alert_id.strip())
        clean_dev_id = re.sub(r"[^\w\-.]", "_", dev_id)
        return f"guardbox/evidence/{clean_dev_id}/{clean_alert_id}.jpg"

    def _resolve_local_file(self, local_snapshot_path: str) -> Optional[str]:
        """Resolves existing physical snapshot file on Windows disk."""
        if not local_snapshot_path:
            return None

        filename = os.path.basename(local_snapshot_path)
        target_file = os.path.join(settings.SNAPSHOT_DIRECTORY, filename)
        alt_file = os.path.join(str(settings.SNAPSHOT_DIRECTORY), local_snapshot_path.replace("/", os.sep))
        root_alt_file = os.path.join(str(BASE_DIR), local_snapshot_path.replace("/", os.sep))

        for candidate in (target_file, alt_file, root_alt_file, local_snapshot_path):
            if candidate and os.path.exists(candidate) and os.path.isfile(candidate):
                return candidate
        return None

    def _optimize_snapshot(self, source_file: str, alert_id: str) -> Tuple[str, int, bool]:
        """
        Creates an optimized temporary upload copy (max width 1600px, quality 85, < 4MB limit).
        Returns (upload_file_path, file_size_bytes, is_temp_file).
        """
        original_size = os.path.getsize(source_file)
        temp_filename = f"temp_supabase_{alert_id}_{uuid.uuid4().hex[:6]}.jpg"
        temp_upload_file = os.path.join(settings.SNAPSHOT_DIRECTORY, temp_filename)

        try:
            import cv2
            img = cv2.imread(source_file)
            if img is not None:
                orig_h, orig_w = img.shape[:2]
                max_width = 1600
                if orig_w > max_width:
                    new_w = max_width
                    new_h = int(orig_h * (max_width / orig_w))
                    resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
                    cv2.imwrite(temp_upload_file, resized, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
                else:
                    cv2.imwrite(temp_upload_file, img, [int(cv2.IMWRITE_JPEG_QUALITY), 85])

                if os.path.exists(temp_upload_file) and os.path.getsize(temp_upload_file) > 0:
                    return temp_upload_file, os.path.getsize(temp_upload_file), True
        except Exception as cv_err:
            try:
                from PIL import Image
                with Image.open(source_file) as p_img:
                    orig_w, orig_h = p_img.size
                    max_width = 1600
                    if orig_w > max_width:
                        new_w = max_width
                        new_h = int(orig_h * (max_width / orig_w))
                        resized_img = p_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                        resized_img.save(temp_upload_file, format="JPEG", quality=85, optimize=True)
                    else:
                        p_img.save(temp_upload_file, format="JPEG", quality=85, optimize=True)

                if os.path.exists(temp_upload_file) and os.path.getsize(temp_upload_file) > 0:
                    return temp_upload_file, os.path.getsize(temp_upload_file), True
            except Exception as opt_err:
                logger.debug(f"Optimization fallback to original snapshot: {opt_err}")

        return source_file, original_size, False

    def upload_alert_snapshot(
        self,
        alert_id: str,
        local_snapshot_path: str,
        device_id: Optional[str] = None,
        expires_in_seconds: int = DEFAULT_SIGNED_URL_DURATION_SECONDS
    ) -> Optional[Dict[str, Any]]:
        """
        Uploads an optimized copy of the existing alert snapshot JPEG to Supabase Storage at:
        guardbox/evidence/{device_id}/{alert_id}.jpg

        - Validates file limit (4 MB) and MIME type (image/jpeg).
        - Idempotent: checks if object already exists in Supabase bucket.
        - Generates time-limited signed URL for secure authenticated remote viewing.
        - Non-fatal: returns None and logs structured failure if upload cannot be completed.
        """
        if not alert_id or not local_snapshot_path:
            return None

        client = self.get_client()
        if client is None:
            logger.warning(f"[TRINETRA SUPABASE] Storage not configured; skipping upload for alert {alert_id}")
            return None

        storage_path = self.get_object_path(alert_id, device_id)
        bucket_name = settings.SUPABASE_BUCKET
        start_time = time.time()

        resolved_file = self._resolve_local_file(local_snapshot_path)
        if not resolved_file:
            logger.error(
                f"[TRINETRA SUPABASE] Upload failed\n"
                f"alert_id={alert_id}\n"
                f"reason=Local snapshot file not found on disk ({local_snapshot_path})"
            )
            return None

        upload_file_path = resolved_file
        is_temp_file = False
        upload_size_bytes = os.path.getsize(resolved_file)

        logger.info(
            f"[TRINETRA SUPABASE] Upload started\n"
            f"alert_id={alert_id}\n"
            f"object_path={storage_path}\n"
            f"bucket={bucket_name}"
        )

        try:
            # Create optimized snapshot JPEG
            upload_file_path, upload_size_bytes, is_temp_file = self._optimize_snapshot(resolved_file, alert_id)

            # Enforce 4 MB file limit
            if upload_size_bytes > MAX_SNAPSHOT_SIZE_BYTES:
                logger.error(
                    f"[TRINETRA SUPABASE] Upload failed\n"
                    f"alert_id={alert_id}\n"
                    f"reason=Snapshot size ({upload_size_bytes} bytes) exceeds bucket limit of {MAX_SNAPSHOT_SIZE_BYTES} bytes"
                )
                return None

            bucket_ref = client.storage.from_(bucket_name)

            # Duplicate upload protection: Check if object already exists in bucket
            already_exists = False
            try:
                if hasattr(bucket_ref, "exists") and bucket_ref.exists(storage_path):
                    already_exists = True
                    logger.info(f"[TRINETRA SUPABASE] Object already exists in bucket ({storage_path}); reusing existing object.")
            except Exception as exist_err:
                logger.debug(f"Supabase exists check notice: {exist_err}")

            if not already_exists:
                with open(upload_file_path, "rb") as f:
                    file_bytes = f.read()

                # Upload to Supabase Storage with strict image/jpeg content type
                file_options = {"content-type": "image/jpeg", "upsert": "true"}
                bucket_ref.upload(path=storage_path, file=file_bytes, file_options=file_options)

            duration_ms = int((time.time() - start_time) * 1000)

            # Generate secure, time-limited signed URL
            signed_url = self.generate_signed_url(storage_path, expires_in_seconds=expires_in_seconds)

            logger.info(
                f"[TRINETRA SUPABASE] Upload successful\n"
                f"alert_id={alert_id}\n"
                f"object_path={storage_path}\n"
                f"upload_size_bytes={upload_size_bytes}\n"
                f"upload_duration_ms={duration_ms}\n"
                f"signed_url_generated={'YES' if signed_url else 'NO'}"
            )

            return {
                "status": "AVAILABLE",
                "remote_provider": "supabase",
                "remote_reference": storage_path,
                "remote_snapshot_reference": storage_path,
                "remote_status": "AVAILABLE",
                "snapshot_status": "AVAILABLE",
                "signed_url": signed_url,
                "remote_url": signed_url,
                "expires_in_seconds": expires_in_seconds,
                "upload_size_bytes": upload_size_bytes,
                "upload_duration_ms": duration_ms
            }

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                f"[TRINETRA SUPABASE] Upload failed\n"
                f"alert_id={alert_id}\n"
                f"upload_duration_ms={duration_ms}\n"
                f"reason={e}"
            )
            return None
        finally:
            if is_temp_file and upload_file_path and os.path.exists(upload_file_path):
                try:
                    os.remove(upload_file_path)
                except Exception:
                    pass

    def generate_signed_url(
        self,
        remote_reference: str,
        expires_in_seconds: int = DEFAULT_SIGNED_URL_DURATION_SECONDS
    ) -> Optional[str]:
        """
        Generates a secure, time-limited signed URL for viewing a private Supabase Storage snapshot.
        Lifetime defaults to 8 hours (28,800 seconds).
        Never logs the actual signature or URL token to prevent credential exposure.
        """
        if not remote_reference:
            return None

        client = self.get_client()
        if client is None:
            return None

        clean_path = remote_reference.strip().removeprefix("/")
        bucket_name = settings.SUPABASE_BUCKET

        try:
            bucket_ref = client.storage.from_(bucket_name)
            res = bucket_ref.create_signed_url(path=clean_path, expires_in=expires_in_seconds)

            signed_url = None
            if hasattr(res, "signed_url") and res.signed_url:
                signed_url = res.signed_url
            elif isinstance(res, dict):
                signed_url = res.get("signedURL") or res.get("signed_url") or res.get("signedUrl")

            if signed_url:
                logger.info(
                    f"[TRINETRA SUPABASE] Signed URL generated\n"
                    f"path={clean_path}\n"
                    f"expires_in_seconds={expires_in_seconds}"
                )
                return signed_url
            return None
        except Exception as e:
            logger.warning(f"[TRINETRA SUPABASE] Failed to generate signed URL for '{clean_path}': {e}")
            return None

    def delete_alert_snapshot(
        self,
        alert_id: str,
        device_id: Optional[str] = None
    ) -> bool:
        """
        Deletes the remote evidence snapshot from Supabase Storage upon 8-hour expiration.
        Handles missing object, temporary network error, or already-deleted file safely.
        """
        if not alert_id:
            return False

        client = self.get_client()
        if client is None:
            logger.warning(f"[TRINETRA SUPABASE] Client not configured; skipping remote delete for {alert_id}")
            return False

        storage_path = self.get_object_path(alert_id, device_id)
        bucket_name = settings.SUPABASE_BUCKET

        logger.info(
            f"[TRINETRA SUPABASE] Cleanup started\n"
            f"alert_id={alert_id}\n"
            f"object_path={storage_path}"
        )

        try:
            bucket_ref = client.storage.from_(bucket_name)
            res = bucket_ref.remove([storage_path])

            logger.info(
                f"[TRINETRA SUPABASE] Remote object deleted\n"
                f"alert_id={alert_id}\n"
                f"object_path={storage_path}\n"
                f"status=DELETED"
            )
            return True
        except Exception as e:
            logger.warning(
                f"[TRINETRA SUPABASE] Failed to delete remote snapshot for alert {alert_id}: {e}"
            )
            return False


# Global Supabase Storage Service Singleton
supabase_storage_service = SupabaseStorageService()
