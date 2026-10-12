package com.veronic.guardbox.data.api

import com.google.gson.annotations.SerializedName

/**
 * Server system status response from GET /system/status
 */
data class SystemStatusResponse(
    @SerializedName("system_mode")
    val systemMode: String? = "DISARMED",

    @SerializedName("armed")
    val armed: Boolean = false,

    @SerializedName("is_arming")
    val isArming: Boolean = false,

    @SerializedName("is_test_mode")
    val isTestMode: Boolean = false,

    @SerializedName("exit_countdown_remaining")
    val exitCountdownRemaining: Int = 0,

    @SerializedName("camera_connected")
    val cameraConnected: Boolean = false,

    @SerializedName("camera_ip")
    val cameraIp: String? = null,

    @SerializedName("camera_model")
    val cameraModel: String? = null,

    @SerializedName("motion_detection_enabled")
    val motionDetectionEnabled: Boolean = false
)

/**
 * System arming request for POST /system/arm
 */
data class SystemArmRequest(
    @SerializedName("exit_delay_seconds")
    val exitDelaySeconds: Int = 0
)

/**
 * Device registration request for POST /api/devices/register
 */
data class DeviceRegisterRequest(
    @SerializedName("device_id")
    val deviceId: String,

    @SerializedName("user_name")
    val userName: String = "GuardBox Android Client",

    @SerializedName("fcm_token")
    val fcmToken: String,

    @SerializedName("device_name")
    val deviceName: String,

    @SerializedName("platform")
    val platform: String = "android",

    @SerializedName("priority")
    val priority: Int? = null
)

/**
 * Device registration response from POST /api/devices/register
 */
data class DeviceRegisterResponse(
    @SerializedName("success")
    val success: Boolean,

    @SerializedName("message")
    val message: String? = null
)

/**
 * Response from POST /api/devices/{device_id}/test-push
 */
data class TestPushResponse(
    @SerializedName("success")
    val success: Boolean,

    @SerializedName("delivery_id")
    val deliveryId: Int? = null,

    @SerializedName("device_id")
    val deviceId: String? = null,

    @SerializedName("device_name")
    val deviceName: String? = null,

    @SerializedName("status")
    val status: String? = null,

    @SerializedName("fcm_message_id")
    val fcmMessageId: String? = null,

    @SerializedName("error")
    val error: String? = null
)

/**
 * Snapshot metadata associated with a security alert
 */
data class SnapshotMetadata(
    @SerializedName("reference")
    val reference: String? = null,

    @SerializedName("local_reference")
    val localReference: String? = null,

    @SerializedName("remote_reference")
    val remoteReference: String? = null,

    @SerializedName("remote_provider")
    val remoteProvider: String? = "supabase",

    @SerializedName("remote_url")
    val remoteUrl: String? = null,

    @SerializedName("signed_url")
    val signedUrl: String? = null,

    @SerializedName("path")
    val path: String? = null,

    @SerializedName("created_at")
    val createdAt: String? = null,

    @SerializedName("expires_at")
    val expiresAt: String? = null,

    @SerializedName("status")
    val status: String? = null,

    @SerializedName("remote_status")
    val remoteStatus: String? = null
)

/**
 * Single active alert data from GET /api/alerts/active or Firebase current node
 */
data class ActiveAlertData(
    @SerializedName("id")
    val id: Int,

    @SerializedName("alert_id")
    val alertId: String? = null,

    @SerializedName("alert_code")
    val alertCode: String? = null,

    @SerializedName("camera_id")
    val cameraId: Int? = null,

    @SerializedName("camera_name")
    val cameraName: String? = null,

    @SerializedName("reason")
    val reason: String? = null,

    @SerializedName("event_type")
    val eventType: String? = null,

    @SerializedName("severity")
    val severity: String? = "HIGH",

    @SerializedName("status")
    val status: String? = null,

    @SerializedName("created_at")
    val createdAt: String? = null,

    @SerializedName("expires_at")
    val expiresAt: String? = null,

    @SerializedName("snapshot_path")
    val snapshotPath: String? = null,

    @SerializedName("snapshot_reference")
    val snapshotReference: String? = null,

    @SerializedName("remote_snapshot_reference")
    val remoteSnapshotReference: String? = null,

    @SerializedName("remote_snapshot_status")
    val remoteSnapshotStatus: String? = null,

    @SerializedName("remote_provider")
    val remoteProvider: String? = "supabase",

    @SerializedName("remote_url")
    val remoteUrl: String? = null,

    @SerializedName("signed_url")
    val signedUrl: String? = null,

    @SerializedName("snapshot_created_at")
    val snapshotCreatedAt: String? = null,

    @SerializedName("snapshot_expires_at")
    val snapshotExpiresAt: String? = null,

    @SerializedName("snapshot_status")
    val snapshotStatus: String? = null,

    @SerializedName("snapshot")
    val snapshot: SnapshotMetadata? = null
) {
    val effectiveAlertId: String?
        get() = alertId?.takeIf { it.isNotBlank() } ?: alertCode?.takeIf { it.isNotBlank() }

    val effectiveSnapshotReference: String?
        get() = snapshot?.localReference?.takeIf { it.isNotBlank() }
            ?: snapshot?.reference?.takeIf { it.isNotBlank() }
            ?: snapshotReference?.takeIf { it.isNotBlank() }
            ?: snapshotPath?.takeIf { it.isNotBlank() }
            ?: snapshot?.path?.takeIf { it.isNotBlank() }

    val effectiveRemoteReference: String?
        get() = snapshot?.remoteReference?.takeIf { it.isNotBlank() }
            ?: remoteSnapshotReference?.takeIf { it.isNotBlank() }

    val effectiveRemoteStatus: String?
        get() = snapshot?.remoteStatus?.takeIf { it.isNotBlank() }
            ?: remoteSnapshotStatus?.takeIf { it.isNotBlank() }

    val effectiveRemoteUrl: String?
        get() = snapshot?.remoteUrl?.takeIf { it.isNotBlank() }
            ?: snapshot?.signedUrl?.takeIf { it.isNotBlank() }
            ?: remoteUrl?.takeIf { it.isNotBlank() }
            ?: signedUrl?.takeIf { it.isNotBlank() }

    val effectiveRemoteProvider: String
        get() = snapshot?.remoteProvider?.takeIf { it.isNotBlank() }
            ?: remoteProvider?.takeIf { it.isNotBlank() }
            ?: "supabase"

    val effectiveReason: String
        get() = reason?.takeIf { it.isNotBlank() }
            ?: eventType?.replace("_", " ")?.lowercase()?.replaceFirstChar { it.uppercase() }
            ?: "Motion Detected"

    val effectiveCreatedAt: String?
        get() = snapshotCreatedAt?.takeIf { it.isNotBlank() }
            ?: snapshot?.createdAt?.takeIf { it.isNotBlank() }
            ?: createdAt?.takeIf { it.isNotBlank() }

    val effectiveSnapshotExpiresAt: String?
        get() = snapshotExpiresAt?.takeIf { it.isNotBlank() }
            ?: snapshot?.expiresAt?.takeIf { it.isNotBlank() }

    fun getFullSnapshotUrl(baseUrl: String = ApiClient.baseUrl): String? {
        return ApiClient.resolveSnapshotUrl(effectiveSnapshotReference, baseUrl)
    }

    val isSnapshotExpired: Boolean
        get() = com.veronic.guardbox.notification.AlertLifecycleHelper.isSnapshotExpired(effectiveSnapshotExpiresAt)
}

/**
 * Response model from GET /api/alerts/active
 */
data class ActiveAlertResponse(
    @SerializedName("active_alert")
    val activeAlert: ActiveAlertData? = null,

    @SerializedName("is_escalating")
    val isEscalating: Boolean = false
)

/**
 * Response model from POST /alarm/silence and GET /alarm/status
 */
data class AlarmStatusResponse(
    @SerializedName("is_active")
    val isActive: Boolean = false,

    @SerializedName("triggered_at")
    val triggeredAt: String? = null,

    @SerializedName("trigger_reason")
    val triggerReason: String? = null,

    @SerializedName("is_simulation")
    val isSimulation: Boolean = true,

    @SerializedName("disclaimer")
    val disclaimer: String? = null
)

