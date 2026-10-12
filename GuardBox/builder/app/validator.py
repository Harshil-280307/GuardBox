"""
TRINETRA Builder - Input Validator
Strict validation rules preventing path traversal, malformed JSON, and improper configuration.
"""

import re
import json
from urllib.parse import urlparse
from typing import Dict, Any, List
from .schemas import CustomerBuildConfig, ValidationResult


SAFE_IDENTIFIER_REGEX = re.compile(r"^[a-zA-Z0-9_-]+$")
DANGEROUS_PATTERNS = ["..", "/", "\\", "\x00", "*", "?", "<", ">", "|", ":", '"']


def sanitize_folder_name(name: str) -> str:
    """Produces a clean filesystem-safe folder name from a shop name."""
    sanitized = re.sub(r"[^a-zA-Z0-9_-]+", "-", name.strip())
    sanitized = re.sub(r"-+", "-", sanitized).strip("-")
    return sanitized or "TRINETRA-CUSTOMER"


def validate_json_content(content: str, label: str) -> (bool, str, Dict[str, Any]):
    """Validates raw JSON string or JSON file content."""
    if not content or not content.strip():
        return False, f"{label} is empty or not provided.", {}
    
    try:
        data = json.loads(content.strip())
        if not isinstance(data, dict):
            return False, f"{label} must be a valid JSON object.", {}
        return True, "", data
    except Exception as e:
        return False, f"{label} is not valid JSON: {str(e)}", {}


def validate_customer_config(config: CustomerBuildConfig) -> ValidationResult:
    """Validates full customer build configuration without exposing secrets."""
    errors: List[str] = []
    warnings: List[str] = []
    sanitized_summary: Dict[str, Any] = {}

    # 1. Customer Identity Validation
    if not config.shop_name or len(config.shop_name.strip()) < 2:
        errors.append("Shop Name is required (minimum 2 characters).")
    else:
        for p in ["..", "\x00", "<", ">", "|"]:
            if p in config.shop_name:
                errors.append(f"Shop Name contains unsafe characters: '{p}'")

    if not config.shop_id or not SAFE_IDENTIFIER_REGEX.match(config.shop_id.strip()):
        errors.append("Shop ID is required and must contain only alphanumeric characters, underscores, and hyphens (e.g. SHOP-RK-001).")
    elif any(p in config.shop_id for p in DANGEROUS_PATTERNS):
        errors.append("Shop ID contains dangerous path traversal characters.")

    if not config.device_id or not SAFE_IDENTIFIER_REGEX.match(config.device_id.strip()):
        errors.append("Device ID is required and must contain only alphanumeric characters, underscores, and hyphens (e.g. TRI-7F29A8C4).")
    elif any(p in config.device_id for p in DANGEROUS_PATTERNS):
        errors.append("Device ID contains dangerous path traversal characters.")

    if not config.device_name or len(config.device_name.strip()) < 2:
        errors.append("Device Name is required (minimum 2 characters).")

    # 2. Firebase Database URL Validation
    if not config.firebase_db_url or not config.firebase_db_url.strip():
        errors.append("Firebase Database URL is required.")
    else:
        try:
            parsed = urlparse(config.firebase_db_url.strip())
            if parsed.scheme not in ["http", "https"] or not parsed.netloc:
                errors.append(f"Firebase Database URL is invalid: '{config.firebase_db_url}'. Must start with http:// or https://")
        except Exception:
            errors.append("Firebase Database URL could not be parsed.")

    # 3. Supabase URL Validation
    if not config.supabase_url or not config.supabase_url.strip():
        errors.append("Supabase URL is required.")
    else:
        try:
            parsed = urlparse(config.supabase_url.strip())
            if parsed.scheme not in ["http", "https"] or not parsed.netloc:
                errors.append(f"Supabase URL is invalid: '{config.supabase_url}'. Must start with http:// or https://")
        except Exception:
            errors.append("Supabase URL could not be parsed.")

    if not config.supabase_bucket or not config.supabase_bucket.strip():
        errors.append("Supabase Bucket is required.")

    # 4. Target Specific Requirements
    if not config.build_windows and not config.build_android:
        errors.append("At least one build target (Windows or Android) must be selected.")

    # Windows Build Specific Requirements
    if config.build_windows:
        if not config.firebase_service_account_json or not config.firebase_service_account_json.strip():
            errors.append("Firebase service account JSON is required for Windows build.")
        else:
            is_valid_sa, sa_err, sa_data = validate_json_content(config.firebase_service_account_json, "Firebase service account JSON")
            if not is_valid_sa:
                errors.append(sa_err)
            else:
                # Verify basic service account schema without printing secrets
                if "project_id" not in sa_data or "private_key" not in sa_data or "client_email" not in sa_data:
                    errors.append("Firebase service account JSON is missing required fields (project_id, private_key, or client_email).")

        if not config.supabase_secret_key or len(config.supabase_secret_key.strip()) < 8:
            errors.append("Supabase Secret Key is required for Windows build.")

        if not config.veronic_admin_user or not config.veronic_admin_user.strip():
            errors.append("Veronic Admin User is required for Windows build.")

        if not config.veronic_admin_secret or len(config.veronic_admin_secret.strip()) < 8:
            errors.append("Veronic Admin Secret is required for Windows build (minimum 8 characters).")

    # Android Build Specific Requirements
    if config.build_android:
        if not config.google_services_json or not config.google_services_json.strip():
            errors.append("google-services.json is required for Android build.")
        else:
            is_valid_gs, gs_err, gs_data = validate_json_content(config.google_services_json, "google-services.json")
            if not is_valid_gs:
                errors.append(gs_err)
            else:
                if "project_info" not in gs_data or "client" not in gs_data:
                    errors.append("google-services.json is missing required Android client sections (project_info or client).")

    # Build Sanitized Summary (No Secrets)
    sanitized_summary = {
        "shop_name": config.shop_name,
        "shop_id": config.shop_id,
        "device_id": config.device_id,
        "device_name": config.device_name,
        "firebase_db_url": config.firebase_db_url,
        "supabase_url": config.supabase_url,
        "supabase_bucket": config.supabase_bucket,
        "build_windows": config.build_windows,
        "build_android": config.build_android,
        "windows_service_account_configured": bool(config.firebase_service_account_json and config.firebase_service_account_json.strip()),
        "android_google_services_configured": bool(config.google_services_json and config.google_services_json.strip()),
        "supabase_secret_configured": bool(config.supabase_secret_key and config.supabase_secret_key.strip()),
        "veronic_admin_configured": bool(config.veronic_admin_secret and config.veronic_admin_secret.strip())
    }

    return ValidationResult(
        is_valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        sanitized_summary=sanitized_summary
    )
