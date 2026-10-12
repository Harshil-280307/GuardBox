package com.veronic.guardbox.notification

import android.content.Context
import android.util.Log
import java.text.SimpleDateFormat
import java.util.Locale
import java.util.TimeZone
import java.util.concurrent.ConcurrentHashMap

object AlertLifecycleHelper {
    private const val TAG = "AlertLifecycle"
    private const val PREFS_NAME = "trinetra_alert_lifecycle_prefs"
    private const val KEY_HANDLED_IDS = "handled_alert_ids"

    private val inMemoryHandled = ConcurrentHashMap.newKeySet<String>()

    fun parseExpiryEpochMs(isoStr: String?): Long? {
        if (isoStr.isNullOrBlank()) return null
        val cleanIso = isoStr.trim()
        
        // 1. Try modern Java 8+ java.time API (desugared on Android)
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.O) {
            try {
                return java.time.Instant.parse(cleanIso).toEpochMilli()
            } catch (_: Exception) {
                try {
                    return java.time.OffsetDateTime.parse(cleanIso).toInstant().toEpochMilli()
                } catch (_: Exception) {
                }
            }
        }

        // 2. Fallback to SimpleDateFormat with fractional-second normalization
        // Truncate sub-millisecond precision (.123456 -> .123) for SimpleDateFormat compatibility
        val normalized = cleanIso.replace(Regex("\\.(\\d{3})\\d+"), ".$1")
        val formats = listOf(
            "yyyy-MM-dd'T'HH:mm:ss.SSSXXX",
            "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'",
            "yyyy-MM-dd'T'HH:mm:ss.SSS",
            "yyyy-MM-dd'T'HH:mm:ssXXX",
            "yyyy-MM-dd'T'HH:mm:ss'Z'",
            "yyyy-MM-dd'T'HH:mm:ss"
        )
        for (pattern in formats) {
            try {
                val sdf = SimpleDateFormat(pattern, Locale.US).apply {
                    timeZone = TimeZone.getTimeZone("UTC")
                }
                val date = sdf.parse(normalized)
                if (date != null) {
                    return date.time
                }
            } catch (_: Exception) {
            }
        }
        return null
    }

    fun getRemainingMillis(expiresAtIso: String?): Long {
        if (expiresAtIso.isNullOrBlank()) return 60_000L
        val expiryMs = parseExpiryEpochMs(expiresAtIso) ?: return 60_000L
        return expiryMs - System.currentTimeMillis()
    }

    fun getRemainingVisibilityMillis(createdAtIso: String?, expiresAtIso: String?): Long {
        val expiryMs = parseExpiryEpochMs(expiresAtIso)
            ?: parseExpiryEpochMs(createdAtIso)?.let { it + 60_000L }
            ?: return 60_000L
        return expiryMs - System.currentTimeMillis()
    }

    fun isAlertExpired(createdAtIso: String?, expiresAtIso: String?): Boolean {
        return getRemainingVisibilityMillis(createdAtIso, expiresAtIso) <= 0
    }

    fun formatDisplayTime(isoStr: String?): String {
        if (isoStr.isNullOrBlank()) return "Unavailable"
        val epochMs = parseExpiryEpochMs(isoStr) ?: return isoStr
        val sdf = SimpleDateFormat("h:mm a", Locale.getDefault())
        return sdf.format(epochMs)
    }

    fun formatHumanDateTime(isoStr: String?): String {
        if (isoStr.isNullOrBlank()) return "Never"
        val epochMs = parseExpiryEpochMs(isoStr) ?: return isoStr
        val sdf = SimpleDateFormat("dd MMM yyyy, hh:mm a", Locale.getDefault())
        return sdf.format(epochMs)
    }

    fun isSnapshotExpired(expiresAtIso: String?): Boolean {
        if (expiresAtIso.isNullOrBlank()) return false
        val expiryMs = parseExpiryEpochMs(expiresAtIso) ?: return false
        return System.currentTimeMillis() >= expiryMs
    }

    fun isDuplicateOrHandled(context: Context, alertId: String): Boolean {
        if (alertId.isBlank()) return true
        if (inMemoryHandled.contains(alertId)) return true

        val sp = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        val persisted = sp.getStringSet(KEY_HANDLED_IDS, emptySet()) ?: emptySet()
        if (persisted.contains(alertId)) {
            inMemoryHandled.add(alertId)
            return true
        }
        return false
    }

    fun markHandled(context: Context, alertId: String) {
        if (alertId.isBlank()) return
        inMemoryHandled.add(alertId)
        try {
            val sp = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            val current = sp.getStringSet(KEY_HANDLED_IDS, emptySet())?.toMutableSet() ?: mutableSetOf()
            current.add(alertId)
            if (current.size > 200) {
                val pruned = current.toList().takeLast(100).toSet()
                sp.edit().putStringSet(KEY_HANDLED_IDS, pruned).apply()
            } else {
                sp.edit().putStringSet(KEY_HANDLED_IDS, current).apply()
            }
        } catch (e: Exception) {
            Log.w(TAG, "Error persisting handled alert ID: ${e.message}")
        }
    }
}
