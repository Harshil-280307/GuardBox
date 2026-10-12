package com.veronic.guardbox.notification

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.media.AudioAttributes
import android.net.Uri
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.util.Log
import androidx.core.app.NotificationCompat
import com.veronic.guardbox.MainActivity
import com.veronic.guardbox.R
import java.util.concurrent.ConcurrentHashMap

object NotificationHelper {

    private const val TAG = "NotificationHelper"
    const val CHANNEL_ID = "guardbox_security_alerts"
    private const val NOTIFICATION_ID = 1001

    const val SERVICE_CHANNEL_ID = "guardbox_service_channel"
    const val SERVICE_NOTIFICATION_ID = 1000

    private val VIBRATION_PATTERN = longArrayOf(0, 600, 200, 600, 200, 1000)
    private val mainHandler = Handler(Looper.getMainLooper())
    private val activeAlertRunnables = ConcurrentHashMap<String, Runnable>()
    @Volatile
    private var currentActiveAlertId: String? = null

    fun createNotificationChannel(context: Context) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val notificationManager =
                context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

            val soundUri: Uri = Uri.parse(
                "android.resource://${context.packageName}/${R.raw.guardbox_emergency_alert}"
            )

            val audioAttributes = AudioAttributes.Builder()
                .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                .setUsage(AudioAttributes.USAGE_ALARM)
                .build()

            // 1. High-Priority Emergency Alert Channel
            val existingAlertChannel = notificationManager.getNotificationChannel(CHANNEL_ID)
            if (existingAlertChannel != null && existingAlertChannel.importance < NotificationManager.IMPORTANCE_DEFAULT) {
                try {
                    notificationManager.deleteNotificationChannel(CHANNEL_ID)
                } catch (e: Exception) {
                    // Ignore deletion error
                }
            }

            val alertChannel = NotificationChannel(
                CHANNEL_ID,
                context.getString(R.string.channel_emergency_name),
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = context.getString(R.string.channel_emergency_desc)
                enableLights(true)
                lightColor = Color.RED
                enableVibration(true)
                vibrationPattern = VIBRATION_PATTERN
                setSound(soundUri, audioAttributes)
                lockscreenVisibility = NotificationCompat.VISIBILITY_PUBLIC
                setBypassDnd(true)
            }

            // 2. Quiet Low-Priority Background Monitoring Service Channel
            val serviceChannel = NotificationChannel(
                SERVICE_CHANNEL_ID,
                "TRINETRA Background Monitoring",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Shows persistent status while TRINETRA security perimeter is armed"
                setShowBadge(false)
            }

            notificationManager.createNotificationChannel(alertChannel)
            notificationManager.createNotificationChannel(serviceChannel)
        }
    }

    fun buildServiceNotification(context: Context): android.app.Notification {
        val intent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP
        }
        val pendingIntent = PendingIntent.getActivity(
            context,
            0,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        return NotificationCompat.Builder(context, SERVICE_CHANNEL_ID)
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentTitle("TRINETRA Active")
            .setContentText("🟢 Perimeter security monitoring active")
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setOngoing(true)
            .setContentIntent(pendingIntent)
            .build()
    }

    fun triggerSecurityAlert(
        context: Context,
        alertId: String,
        cameraName: String = "Main Gate",
        reason: String = "Motion detected",
        expiresAtIso: String? = null
    ) {
        if (alertId.isBlank()) {
            Log.w(TAG, "[TRINETRA ALERT IGNORED]\nalert_id=UNKNOWN\nreason=MISSING_ALERT_ID")
            return
        }

        val remainingMillis = AlertLifecycleHelper.getRemainingMillis(expiresAtIso)
        if (remainingMillis <= 0) {
            Log.i(TAG, "[TRINETRA ALERT IGNORED]\nalert_id=$alertId\nreason=EXPIRED")
            return
        }

        if (AlertLifecycleHelper.isDuplicateOrHandled(context, alertId)) {
            Log.i(TAG, "[TRINETRA ALERT IGNORED]\nalert_id=$alertId\nreason=DUPLICATE")
            return
        }

        AlertLifecycleHelper.markHandled(context, alertId)

        val notificationManager =
            context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

        // Intent when tapped
        val intent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }

        val pendingIntent = PendingIntent.getActivity(
            context,
            NOTIFICATION_ID,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val soundUri: Uri = Uri.parse(
            "android.resource://${context.packageName}/${R.raw.guardbox_emergency_alert}"
        )

        val contentText = "$reason • Alert ID: $alertId"
        val bigText = "$reason\nCamera: $cameraName\nAlert ID: $alertId\nTap to view snapshot"

        val notification = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentTitle("TRINETRA")
            .setContentText(contentText)
            .setStyle(NotificationCompat.BigTextStyle().bigText(bigText))
            .setPriority(NotificationCompat.PRIORITY_MAX)
            .setCategory(NotificationCompat.CATEGORY_ALARM)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setAutoCancel(true)
            .setSound(soundUri)
            .setVibrate(VIBRATION_PATTERN)
            .setColor(Color.RED)
            .setContentIntent(pendingIntent)
            .setFullScreenIntent(pendingIntent, true)
            .build()

        notificationManager.notify(NOTIFICATION_ID, notification)
        currentActiveAlertId = alertId

        Log.i(TAG, "[TRINETRA ALERT DISPLAYED]\nalert_id=$alertId")
        Log.i(TAG, "[TRINETRA ALERT EXPIRES]\nalert_id=$alertId")

        // Cancel previous timer if any
        activeAlertRunnables[alertId]?.let { mainHandler.removeCallbacks(it) }

        val expiryRunnable = Runnable {
            cancelEmergencyAlert(context, alertId, reason = "AUTO_EXPIRED_60S")
        }
        activeAlertRunnables[alertId] = expiryRunnable
        mainHandler.postDelayed(expiryRunnable, remainingMillis.coerceAtLeast(1000L))
    }

    /**
     * Dismisses the active emergency notification on the phone and cancels ongoing sound/vibration.
     * If alertId is passed, only cancels if it matches current active alert or is null.
     */
    fun cancelEmergencyAlert(context: Context, alertId: String? = null, reason: String = "USER_DISMISSED") {
        if (alertId != null && currentActiveAlertId != null && alertId != currentActiveAlertId) {
            // Do not cancel a different newer alert
            return
        }

        val notificationManager =
            context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        notificationManager.cancel(NOTIFICATION_ID)

        val targetId = alertId ?: currentActiveAlertId ?: "UNKNOWN"
        activeAlertRunnables.remove(targetId)?.let { mainHandler.removeCallbacks(it) }
        currentActiveAlertId = null

        Log.i(TAG, "[TRINETRA ALERT CANCELLED]\nalert_id=$targetId\nreason=$reason")
    }
}
