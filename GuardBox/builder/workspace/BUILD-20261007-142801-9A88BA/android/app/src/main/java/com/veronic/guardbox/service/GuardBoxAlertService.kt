package com.veronic.guardbox.service

import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.util.Log
import androidx.core.content.ContextCompat
import com.veronic.guardbox.data.RealGuardBoxRepository
import com.veronic.guardbox.notification.AlertLifecycleHelper
import com.veronic.guardbox.notification.NotificationHelper
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/**
 * Dedicated Foreground Service for GuardBox Security Alert Monitoring.
 * Runs continuously in background / screen locked / app closed to poll GET /api/alerts/active as fallback.
 */
class GuardBoxAlertService : Service() {

    private val TAG = "GuardBoxAlertService"

    private val repository = RealGuardBoxRepository()
    private val serviceScope = CoroutineScope(Dispatchers.IO)
    private var pollingJob: Job? = null
    private var lastKnownAlertId: String? = null
    private var isBaselineEstablished: Boolean = false

    companion object {
        const val ACTION_START = "com.veronic.guardbox.action.START_MONITORING"
        const val ACTION_STOP = "com.veronic.guardbox.action.STOP_MONITORING"

        @Volatile
        var isRunning: Boolean = false
            private set

        fun start(context: Context) {
            val intent = Intent(context, GuardBoxAlertService::class.java).apply {
                action = ACTION_START
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                ContextCompat.startForegroundService(context, intent)
            } else {
                context.startService(intent)
            }
        }

        fun stop(context: Context) {
            val intent = Intent(context, GuardBoxAlertService::class.java).apply {
                action = ACTION_STOP
            }
            context.startService(intent)
        }
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        Log.d(TAG, "GuardBoxAlertService created")
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> {
                Log.i(TAG, "Received ACTION_STOP -> stopping foreground monitoring service")
                isRunning = false
                stopMonitoring()
                stopForeground(true)
                stopSelf()
                return START_NOT_STICKY
            }
            else -> {
                Log.i(TAG, "Received ACTION_START -> launching foreground monitoring service")
                isRunning = true
                startForegroundNotification()
                startMonitoring()
                return START_STICKY
            }
        }
    }

    private fun startForegroundNotification() {
        val notification = NotificationHelper.buildServiceNotification(this)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(
                NotificationHelper.SERVICE_NOTIFICATION_ID,
                notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC
            )
        } else {
            startForeground(NotificationHelper.SERVICE_NOTIFICATION_ID, notification)
        }
    }

    private fun startMonitoring() {
        if (pollingJob != null && pollingJob?.isActive == true) return
        isBaselineEstablished = false

        pollingJob = serviceScope.launch {
            Log.i(TAG, "TRINETRA background alert monitoring active (2s polling)")
            while (isActive) {
                try {
                    val activeAlert = repository.getActiveAlert()
                    if (!isBaselineEstablished) {
                        isBaselineEstablished = true
                        if (activeAlert != null) {
                            val alertId = activeAlert.effectiveAlertId
                            if (!alertId.isNullOrBlank()) {
                                lastKnownAlertId = alertId
                                AlertLifecycleHelper.markHandled(applicationContext, alertId)
                                Log.i(TAG, "[TRINETRA ALERT BASELINE]\nalert_id=$alertId")
                            } else {
                                Log.w(TAG, "[TRINETRA ALERT IGNORED]\nalert_id=UNKNOWN\nreason=MISSING_ALERT_ID")
                            }
                        } else {
                            Log.i(TAG, "[TRINETRA ALERT BASELINE]\nalert_id=NONE")
                        }
                    } else if (activeAlert != null) {
                        val alertId = activeAlert.effectiveAlertId
                        if (alertId.isNullOrBlank()) {
                            Log.w(TAG, "[TRINETRA ALERT IGNORED]\nalert_id=UNKNOWN\nreason=MISSING_ALERT_ID")
                        } else if (alertId != lastKnownAlertId) {
                            lastKnownAlertId = alertId

                            if (AlertLifecycleHelper.isDuplicateOrHandled(applicationContext, alertId)) {
                                Log.i(TAG, "[TRINETRA ALERT IGNORED]\nalert_id=$alertId\nreason=DUPLICATE")
                            } else {
                                val remainingMillis = AlertLifecycleHelper.getRemainingMillis(activeAlert.expiresAt)
                                if (remainingMillis <= 0) {
                                    Log.i(TAG, "[TRINETRA ALERT IGNORED]\nalert_id=$alertId\nreason=EXPIRED")
                                } else {
                                    val camName = activeAlert.cameraName ?: "Main Gate"
                                    val reason = activeAlert.eventType?.replace("_", " ")?.lowercase()?.replaceFirstChar { it.uppercase() }
                                        ?: "Motion detected"

                                    NotificationHelper.triggerSecurityAlert(
                                        context = applicationContext,
                                        alertId = alertId,
                                        cameraName = camName,
                                        reason = reason,
                                        expiresAtIso = activeAlert.expiresAt
                                    )
                                }
                            }
                        }
                    }
                } catch (e: Exception) {
                    Log.w(TAG, "Background polling cycle notice: ${e.message}")
                }
                delay(2000)
            }
        }
    }

    private fun stopMonitoring() {
        pollingJob?.cancel()
        pollingJob = null
        isBaselineEstablished = false
    }

    override fun onDestroy() {
        super.onDestroy()
        isRunning = false
        stopMonitoring()
        Log.d(TAG, "GuardBoxAlertService destroyed")
    }
}
