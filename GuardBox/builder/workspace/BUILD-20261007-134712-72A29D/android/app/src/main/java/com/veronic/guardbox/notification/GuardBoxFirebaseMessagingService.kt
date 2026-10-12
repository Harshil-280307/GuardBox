package com.veronic.guardbox.notification

import android.annotation.SuppressLint
import android.provider.Settings
import android.util.Log
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import com.veronic.guardbox.data.RealGuardBoxRepository
import com.veronic.guardbox.data.firebase.FirebaseBridgeManager
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

/**
 * Firebase Cloud Messaging Service for Veronic GuardBox.
 * Receives real-time push alerts and dispatches high-priority notifications with 60s lifecycle.
 */
class GuardBoxFirebaseMessagingService : FirebaseMessagingService() {

    private val TAG = "GuardBoxFCM"
    private val repository = RealGuardBoxRepository()
    private val serviceScope = CoroutineScope(Dispatchers.IO)

    @SuppressLint("HardwareIds")
    override fun onNewToken(token: String) {
        super.onNewToken(token)
        Log.d(TAG, "FCM TOKEN GENERATED\ntoken_exists=${token.isNotBlank()}")

        val deviceId = Settings.Secure.getString(contentResolver, Settings.Secure.ANDROID_ID)
            ?: "android_device"

        serviceScope.launch {
            repository.registerDevice(
                deviceId = deviceId,
                fcmToken = token
            )
            FirebaseBridgeManager.registerFcmToken(token)
        }
    }

    override fun onMessageReceived(remoteMessage: RemoteMessage) {
        super.onMessageReceived(remoteMessage)

        val data = remoteMessage.data

        val alertId = data["alert_id"] ?: data["alert_code"] ?: ""
        if (alertId.isBlank()) {
            Log.w(TAG, "[TRINETRA ALERT IGNORED]\nalert_id=UNKNOWN\nreason=MISSING_ALERT_ID")
            return
        }

        Log.i(TAG, "[TRINETRA FCM RECEIVED]\nalert_id=$alertId")

        val targetDeviceId = FirebaseBridgeManager.targetDeviceId.trim()
        val messageDeviceId = data["device_id"]?.trim()
        if (!messageDeviceId.isNullOrBlank() && targetDeviceId.isNotBlank() && !messageDeviceId.equals(targetDeviceId, ignoreCase = true)) {
            Log.i(TAG, "[TRINETRA ALERT IGNORED]\nalert_id=$alertId\nreason=DEVICE_MISMATCH")
            return
        }

        val type = data["type"] ?: "SECURITY_ALERT"
        if (type != "SECURITY_ALERT") {
            Log.i(TAG, "[TRINETRA ALERT IGNORED]\nalert_id=$alertId\nreason=INVALID_TYPE")
            return
        }

        val expiresAt = data["expires_at"]
        val remainingMillis = AlertLifecycleHelper.getRemainingMillis(expiresAt)
        if (remainingMillis <= 0) {
            Log.i(TAG, "[TRINETRA ALERT IGNORED]\nalert_id=$alertId\nreason=EXPIRED")
            return
        }

        if (AlertLifecycleHelper.isDuplicateOrHandled(applicationContext, alertId)) {
            Log.i(TAG, "[TRINETRA ALERT IGNORED]\nalert_id=$alertId\nreason=DUPLICATE")
            return
        }

        val cameraName = data["camera_name"] ?: remoteMessage.notification?.title?.let {
            if (it.contains("Camera:")) it.substringAfter("Camera:").trim() else "Main Gate"
        } ?: "Main Gate"

        val reason = data["reason"] ?: data["event_type"]?.replace("_", " ")?.lowercase()?.replaceFirstChar { it.uppercase() }
            ?: "Motion detected"

        NotificationHelper.triggerSecurityAlert(
            context = applicationContext,
            alertId = alertId,
            cameraName = cameraName,
            reason = reason,
            expiresAtIso = expiresAt
        )
    }
}
