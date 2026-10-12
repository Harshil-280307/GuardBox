"""
TRINETRA Builder - Pydantic Schemas
Defines structured input validation models for customer build generation.
"""

from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, HttpUrl


class CustomerBuildConfig(BaseModel):
    # Customer Identity
    shop_name: str = Field(default="", max_length=100, description="Customer Shop Name")
    shop_id: str = Field(default="", max_length=50, description="Unique Shop ID (e.g. SHOP-RK-001)")
    device_id: str = Field(default="", max_length=50, description="Device Hardware / Identity ID (e.g. TRI-7F29A8C4)")
    device_name: str = Field(default="", max_length=100, description="Friendly Device Name")

    # Firebase Configuration
    firebase_db_url: str = Field(default="", description="Firebase Realtime Database URL")
    firebase_service_account_json: Optional[str] = Field(default=None, description="Raw JSON string or file path for Windows Firebase Admin SDK")
    google_services_json: Optional[str] = Field(default=None, description="Raw JSON string or file path for Android client")

    # Supabase Configuration
    supabase_url: str = Field(default="", description="Supabase project URL")
    supabase_bucket: str = Field(default="snapshots", max_length=100, description="Supabase Storage Bucket Name")
    supabase_secret_key: Optional[str] = Field(default=None, description="Supabase Service Role Secret Key (Windows backend only)")

    # Veronic Admin Configuration (Windows only)
    veronic_admin_user: str = Field(default="admin", max_length=100, description="Local administrator username")
    veronic_admin_secret: Optional[str] = Field(default=None, description="Local administrator password/secret (minimum 8 characters)")

    # Build targets
    build_windows: bool = Field(default=True, description="Whether to package Windows backend application")
    build_android: bool = Field(default=True, description="Whether to build Android client APK")


class ValidationResult(BaseModel):
    is_valid: bool
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    sanitized_summary: Dict[str, Any] = Field(default_factory=dict)


class BuildStageLog(BaseModel):
    stage: str
    message: str
    status: str  # "RUNNING", "SUCCESS", "FAILED", "SKIPPED"
    timestamp: str


class BuildExecutionResult(BaseModel):
    build_id: str = ""
    shop_id: str = ""
    shop_name: str = ""
    is_success: bool = False
    windows_status: str = "FAILED"  # "SUCCESS", "FAILED", "SKIPPED"
    android_status: str = "FAILED"  # "SUCCESS", "FAILED", "SKIPPED"
    installer_available: bool = False
    security_scan_status: str = "FAILED"
    output_directory: str = ""
    artifacts: List[str] = Field(default_factory=list)
    logs: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
