package com.veronic.guardbox.util

import android.content.ContentValues
import android.content.Context
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone

object SnapshotStorageHelper {
    private const val TAG = "SnapshotStorage"
    private const val PREFS_NAME = "trinetra_saved_snapshots_prefs"
    private const val KEY_PREFIX = "saved_snapshot_"

    data class SavedSnapshotRecord(
        val alertId: String,
        val localUri: String,
        val savedAt: String
    )

    fun getLocalSavedRecord(context: Context, alertId: String): SavedSnapshotRecord? {
        if (alertId.isBlank()) return null
        val sp = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        val rawJson = sp.getString("$KEY_PREFIX$alertId", null) ?: return null
        return try {
            val obj = JSONObject(rawJson)
            val uriStr = obj.optString("local_uri", "")
            // Verify if local URI is still accessible
            if (uriStr.isNotBlank() && isUriAccessible(context, uriStr)) {
                SavedSnapshotRecord(
                    alertId = obj.optString("alert_id", alertId),
                    localUri = uriStr,
                    savedAt = obj.optString("saved_at", "")
                )
            } else {
                null
            }
        } catch (e: Exception) {
            null
        }
    }

    fun isSnapshotSavedLocally(context: Context, alertId: String): Boolean {
        return getLocalSavedRecord(context, alertId) != null
    }

    private fun isUriAccessible(context: Context, uriStr: String): Boolean {
        return try {
            val uri = Uri.parse(uriStr)
            if (uriStr.startsWith("content://")) {
                context.contentResolver.openInputStream(uri)?.use { true } ?: false
            } else if (uriStr.startsWith("file://")) {
                val file = File(uri.path ?: return false)
                file.exists() && file.length() > 0
            } else {
                val file = File(uriStr)
                file.exists() && file.length() > 0
            }
        } catch (_: Exception) {
            false
        }
    }

    suspend fun saveSnapshotToDevice(
        context: Context,
        alertId: String,
        snapshotUrl: String
    ): Result<SavedSnapshotRecord> = withContext(Dispatchers.IO) {
        try {
            // 1. Check if already saved and valid
            val existing = getLocalSavedRecord(context, alertId)
            if (existing != null) {
                return@withContext Result.success(existing)
            }

            // 2. Download bytes from URL
            val url = URL(snapshotUrl)
            val connection = (url.openConnection() as HttpURLConnection).apply {
                connectTimeout = 10_000
                readTimeout = 10_000
                instanceFollowRedirects = true
            }

            if (connection.responseCode != HttpURLConnection.HTTP_OK) {
                return@withContext Result.failure(Exception("HTTP ${connection.responseCode}: ${connection.responseMessage}"))
            }

            val imageBytes = connection.inputStream.use { it.readBytes() }
            if (imageBytes.isEmpty()) {
                return@withContext Result.failure(Exception("Downloaded snapshot is empty"))
            }

            // 3. Construct safe filename with Alert ID
            val sanitizedAlertId = alertId.replace(Regex("[^a-zA-Z0-9_-]"), "_")
            val filename = "TRINETRA_$sanitizedAlertId.jpg"

            // 4. Save to MediaStore (Pictures/TRINETRA) or App External Storage
            val savedUriString: String = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                val values = ContentValues().apply {
                    put(MediaStore.Images.Media.DISPLAY_NAME, filename)
                    put(MediaStore.Images.Media.MIME_TYPE, "image/jpeg")
                    put(MediaStore.Images.Media.RELATIVE_PATH, "${Environment.DIRECTORY_PICTURES}/TRINETRA")
                    put(MediaStore.Images.Media.IS_PENDING, 1)
                }

                val collection = MediaStore.Images.Media.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY)
                val itemUri = context.contentResolver.insert(collection, values)
                    ?: return@withContext Result.failure(Exception("Failed to create MediaStore entry"))

                context.contentResolver.openOutputStream(itemUri)?.use { out ->
                    out.write(imageBytes)
                    out.flush()
                } ?: return@withContext Result.failure(Exception("Failed to write snapshot bytes"))

                values.clear()
                values.put(MediaStore.Images.Media.IS_PENDING, 0)
                context.contentResolver.update(itemUri, values, null, null)

                itemUri.toString()
            } else {
                val picturesDir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_PICTURES)
                val trinetraDir = File(picturesDir, "TRINETRA").apply { mkdirs() }
                val targetFile = File(trinetraDir, filename)
                FileOutputStream(targetFile).use { out ->
                    out.write(imageBytes)
                    out.flush()
                }
                Uri.fromFile(targetFile).toString()
            }

            // 5. Persist local save record
            val nowIso = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US).apply {
                timeZone = TimeZone.getTimeZone("UTC")
            }.format(Date())

            val recordJson = JSONObject().apply {
                put("alert_id", alertId)
                put("local_uri", savedUriString)
                put("saved_at", nowIso)
            }.toString()

            val sp = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            sp.edit().putString("$KEY_PREFIX$alertId", recordJson).apply()

            val record = SavedSnapshotRecord(alertId = alertId, localUri = savedUriString, savedAt = nowIso)
            Log.i(TAG, "[TRINETRA SNAPSHOT SAVED]\nalert_id=$alertId\nlocal_uri=$savedUriString")
            Result.success(record)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to save snapshot for alert $alertId: ${e.message}", e)
            Result.failure(e)
        }
    }
}
