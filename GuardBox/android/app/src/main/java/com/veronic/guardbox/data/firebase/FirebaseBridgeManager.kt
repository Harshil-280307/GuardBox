package com.veronic.guardbox.data.firebase

import android.content.Context
import android.content.SharedPreferences
import android.util.Log
import com.google.firebase.FirebaseApp
import com.google.firebase.FirebaseOptions
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.database.DataSnapshot
import com.google.firebase.database.DatabaseError
import com.google.firebase.database.DatabaseReference
import com.google.firebase.database.FirebaseDatabase
import com.google.firebase.database.ValueEventListener
import com.veronic.guardbox.BuildConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone
import java.util.UUID
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

/**
 * Represents the cloud status of a GuardBox device in Firebase Realtime Database.
 */
data class FirebaseDeviceRecord(
    val deviceId: String = "",
    val name: String = "Shop Security Appliance",
    val online: Boolean = false,
    val status: String = "STOPPED",
    val lastSeen: String = "",
    val version: String = "1.0.0",
    val ownerId: String? = null,
    val shopId: String? = null,
    val shopName: String? = null
)

/**
 * Isolated, crash-proof Firebase Bridge Client for Android.
 * Manages explicit Firebase initialization, authentication, presence discovery,
 * and remote command relay (ARM, DISARM, SILENCE).
 */
object FirebaseBridgeManager {

    private const val TAG = "FirebaseBridgeManager"
    private const val PREFS_NAME = "guardbox_firebase_prefs"
    private const val PREF_TARGET_DEVICE_ID = "pref_target_device_id"

    val DEFAULT_TARGET_DEVICE_ID: String = if (BuildConfig.DEFAULT_TARGET_DEVICE_ID.isNotBlank()) {
        BuildConfig.DEFAULT_TARGET_DEVICE_ID
    } else {
        "guardbox-shop-f20424b4"
    }
    val FIREBASE_DATABASE_URL: String = BuildConfig.FIREBASE_DATABASE_URL

    @Volatile
    var isFirebaseAvailable: Boolean = false
        private set

    @Volatile
    var targetDeviceId: String = if (DEFAULT_TARGET_DEVICE_ID.isNotBlank()) DEFAULT_TARGET_DEVICE_ID else "guardbox-shop-f20424b4"
        private set

    private var prefs: SharedPreferences? = null
    private var appContext: Context? = null

    fun initialize(context: Context) {
        val appCtx = context.applicationContext
        appContext = appCtx
        val sp = appCtx.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        prefs = sp
        val savedId = sp.getString(PREF_TARGET_DEVICE_ID, null)?.trim()
        targetDeviceId = if (!savedId.isNullOrBlank()) {
            savedId
        } else if (DEFAULT_TARGET_DEVICE_ID.isNotBlank()) {
            DEFAULT_TARGET_DEVICE_ID
        } else {
            "guardbox-shop-f20424b4"
        }
        if (savedId.isNullOrBlank() && targetDeviceId.isNotBlank()) {
            sp.edit().putString(PREF_TARGET_DEVICE_ID, targetDeviceId).apply()
        }

        ensureFirebaseApp(appCtx)
    }

    /**
     * Guarantees FirebaseApp is initialized using google-services configuration and target database URL.
     */
    private fun ensureFirebaseApp(context: Context): Boolean {
        try {
            val cleanDbUrl = FIREBASE_DATABASE_URL.trim().trimEnd('/')
            if (FirebaseApp.getApps(context).isEmpty()) {
                val defaultOptions = try {
                    FirebaseOptions.fromResource(context)
                } catch (e: Exception) {
                    null
                }
                if (defaultOptions != null) {
                    val builder = FirebaseOptions.Builder(defaultOptions)
                    if (cleanDbUrl.isNotBlank()) {
                        builder.setDatabaseUrl(cleanDbUrl)
                    }
                    FirebaseApp.initializeApp(context, builder.build())
                    Log.i(TAG, "FirebaseApp initialized from google-services resources with RTDB URL: $cleanDbUrl")
                } else {
                    FirebaseApp.initializeApp(context)
                    Log.i(TAG, "FirebaseApp initialized from default context resources")
                }
            }
            isFirebaseAvailable = true
            return true
        } catch (e: Exception) {
            Log.w(TAG, "Firebase initialization notice: ${e.message}")
            isFirebaseAvailable = FirebaseApp.getApps(context).isNotEmpty()
            return isFirebaseAvailable
        }
    }

    private fun getDatabaseInstance(): FirebaseDatabase? {
        val ctx = appContext
        if (ctx != null) {
            ensureFirebaseApp(ctx)
        }
        val cleanDbUrl = FIREBASE_DATABASE_URL.trim().trimEnd('/').ifBlank { null }
        return try {
            if (cleanDbUrl != null) {
                if (ctx != null && FirebaseApp.getApps(ctx).isNotEmpty()) {
                    FirebaseDatabase.getInstance(FirebaseApp.getInstance(), cleanDbUrl)
                } else {
                    FirebaseDatabase.getInstance(cleanDbUrl)
                }
            } else {
                FirebaseDatabase.getInstance()
            }
        } catch (e: Exception) {
            try {
                if (cleanDbUrl != null) {
                    FirebaseDatabase.getInstance(cleanDbUrl)
                } else {
                    FirebaseDatabase.getInstance()
                }
            } catch (ex: Exception) {
                try {
                    FirebaseDatabase.getInstance()
                } catch (ex2: Exception) {
                    Log.e(TAG, "Failed to obtain FirebaseDatabase instance: ${ex2.message}")
                    null
                }
            }
        }
    }

    fun updateTargetDeviceId(deviceId: String) {
        val cleaned = deviceId.trim()
        if (cleaned.isNotBlank()) {
            targetDeviceId = cleaned
            prefs?.edit()?.putString(PREF_TARGET_DEVICE_ID, cleaned)?.apply()
            Log.i(TAG, "Updated target GuardBox Device ID: $targetDeviceId")
        }
    }

    /**
     * Registers this Android client's FCM token in Firebase Realtime Database
     * under guardbox/notification_tokens/{owner_uid}/{token_id}
     */
    /**
     * Registers this Android client's FCM token in Firebase Realtime Database
     * under guardbox/notification_tokens/{owner_uid}/android_client
     */
    fun registerFcmToken(token: String, clientDeviceId: String = targetDeviceId) {
        val cleanToken = token.trim()
        val tokenExists = cleanToken.isNotBlank()
        val tokenLength = cleanToken.length
        Log.d("GuardBoxFCM", "FCM TOKEN RESULT\ntoken_exists=$tokenExists\ntoken_length=$tokenLength")
        if (!tokenExists) return

        ensureAuthenticated { authenticated ->
            val uid = FirebaseAuth.getInstance().currentUser?.uid
            Log.d("GuardBoxFCM", "FCM AUTH CHECK\nauthenticated=$authenticated\nuid=${uid ?: "null"}")
            if (!authenticated || uid.isNullOrBlank()) {
                Log.w("GuardBoxFCM", "FCM TOKEN WRITE FAILED\nerror_type=AuthException\nerror_message=Authentication required before token write")
                return@ensureAuthenticated
            }

            val db = getDatabaseInstance()
            if (db == null) {
                Log.w("GuardBoxFCM", "FCM TOKEN WRITE FAILED\nerror_type=DatabaseException\nerror_message=FirebaseDatabase instance is null")
                return@ensureAuthenticated
            }

            val targetDevId = if (targetDeviceId.isNotBlank()) targetDeviceId else DEFAULT_TARGET_DEVICE_ID
            val path = "guardbox/notification_tokens/$uid/android_client"
            Log.d("GuardBoxFCM", "FCM TOKEN WRITE START\npath=$path\ndevice_id=$targetDevId")

            // Use stable child 'android_client' under the authenticated user's UID
            val tokenNode = db.reference.child("guardbox/notification_tokens").child(uid).child("android_client")

            val isoFormat = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'", Locale.US).apply {
                timeZone = TimeZone.getTimeZone("UTC")
            }
            val payload = mapOf(
                "token" to cleanToken,
                "device_id" to targetDevId,
                "platform" to "android",
                "updated_at" to isoFormat.format(Date())
            )

            tokenNode.setValue(payload).addOnCompleteListener { task ->
                if (task.isSuccessful) {
                    Log.d("GuardBoxFCM", "FCM TOKEN WRITE SUCCESS")
                } else {
                    val ex = task.exception
                    Log.w("GuardBoxFCM", "FCM TOKEN WRITE FAILED\nerror_type=${ex?.javaClass?.simpleName ?: "DatabaseError"}\nerror_message=${ex?.message ?: "Unknown write failure"}")
                }
            }
        }
    }

    suspend fun ensureAuthenticatedSuspending(): Boolean = withContext(Dispatchers.IO) {
        suspendCancellableCoroutine { cont ->
            ensureAuthenticated { success ->
                if (cont.isActive) cont.resume(success)
            }
        }
    }

    /**
     * Authenticate client anonymously or with existing Firebase credentials.
     */
    fun ensureAuthenticated(onComplete: ((Boolean) -> Unit)? = null) {
        val ctx = appContext
        if (ctx != null) {
            ensureFirebaseApp(ctx)
        }

        if (!isFirebaseAvailable) {
            onComplete?.invoke(false)
            return
        }

        try {
            val auth = FirebaseAuth.getInstance()
            val user = auth.currentUser
            if (user != null) {
                user.getIdToken(false).addOnCompleteListener { tokenTask ->
                    if (tokenTask.isSuccessful) {
                        Log.d(TAG, "Firebase user authenticated & token validated: UID=${user.uid}")
                        onComplete?.invoke(true)
                    } else {
                        Log.w(TAG, "Firebase cached token validation failed, re-authenticating anonymously: ${tokenTask.exception?.message}")
                        auth.signInAnonymously().addOnCompleteListener { signInTask ->
                            if (signInTask.isSuccessful) {
                                Log.i(TAG, "Firebase client re-authenticated anonymously: UID=${auth.currentUser?.uid}")
                                onComplete?.invoke(true)
                            } else {
                                Log.w(TAG, "Firebase anonymous re-authentication failed: ${signInTask.exception?.message}")
                                onComplete?.invoke(false)
                            }
                        }
                    }
                }
            } else {
                auth.signInAnonymously().addOnCompleteListener { task ->
                    if (task.isSuccessful) {
                        Log.i(TAG, "Firebase client authenticated anonymously: UID=${auth.currentUser?.uid}")
                        onComplete?.invoke(true)
                    } else {
                        Log.w(TAG, "Firebase anonymous authentication failed: ${task.exception?.message}")
                        onComplete?.invoke(false)
                    }
                }
            }
        } catch (e: Exception) {
            Log.w(TAG, "Auth notice: ${e.message}")
            onComplete?.invoke(false)
        }
    }

    /**
     * Validates Firebase initialization and authentication asynchronously.
     */
    suspend fun verifyRemoteConnection(deviceId: String = targetDeviceId): Result<Unit> = withContext(Dispatchers.IO) {
        val ctx = appContext
        if (ctx != null) {
            ensureFirebaseApp(ctx)
        }

        if (!isFirebaseAvailable) {
            return@withContext Result.failure(Exception("Firebase is not initialized"))
        }

        val targetId = deviceId.trim().ifBlank { targetDeviceId }
        if (targetId.isBlank()) {
            return@withContext Result.failure(Exception("Invalid GuardBox Device ID"))
        }

        val authResult = suspendCancellableCoroutine<Boolean> { cont ->
            ensureAuthenticated { success ->
                if (cont.isActive) cont.resume(success)
            }
        }

        if (!authResult) {
            return@withContext Result.failure(Exception("Firebase Cloud Authentication Failed"))
        }

        Result.success(Unit)
    }

    /**
     * Observe presence and status of a specific GuardBox device from Firebase Realtime Database.
     */
    fun observeDevice(deviceId: String = targetDeviceId): Flow<FirebaseDeviceRecord?> = callbackFlow {
        val currentTarget = deviceId.trim().ifBlank { targetDeviceId.trim() }.ifBlank { DEFAULT_TARGET_DEVICE_ID.trim() }.ifBlank { "guardbox-shop-f20424b4" }
        val db = getDatabaseInstance()

        if (!isFirebaseAvailable || currentTarget.isBlank() || db == null) {
            close(Exception("Firebase is unavailable or Target Device ID is blank"))
            return@callbackFlow
        }

        try {
            val deviceRef = db.reference.child("guardbox/devices").child(currentTarget)

            val listener = object : ValueEventListener {
                override fun onDataChange(snapshot: DataSnapshot) {
                    try {
                        if (snapshot.exists()) {
                            val name = snapshot.child("name").getValue(String::class.java) ?: "Shop Security Appliance"
                            val online = snapshot.child("online").getValue(Boolean::class.java) ?: false
                            val status = snapshot.child("status").getValue(String::class.java) ?: "STOPPED"
                            val lastSeen = snapshot.child("last_seen").getValue(String::class.java) ?: ""
                            val version = snapshot.child("version").getValue(String::class.java) ?: "1.0.0"
                            val ownerId = snapshot.child("owner_id").getValue(String::class.java)
                            val shopId = snapshot.child("shop_id").getValue(String::class.java)
                            val shopName = snapshot.child("shop_name").getValue(String::class.java)

                            val record = FirebaseDeviceRecord(
                                deviceId = currentTarget,
                                name = name,
                                online = online,
                                status = status,
                                lastSeen = lastSeen,
                                version = version,
                                ownerId = ownerId,
                                shopId = shopId,
                                shopName = shopName
                            )
                            Log.d(TAG, "[GUARDBOX STATUS RECEIVED]\ndevice_id=$currentTarget\nstatus=$status\nonline=$online")
                            trySend(record)
                        } else {
                            trySend(null)
                        }
                    } catch (e: Exception) {
                        Log.w(TAG, "Error parsing device snapshot: ${e.message}")
                        close(e)
                    }
                }

                override fun onCancelled(error: DatabaseError) {
                    Log.w(TAG, "Realtime Database listener cancelled: ${error.message}")
                    close(Exception(error.message))
                }
            }

            deviceRef.addValueEventListener(listener)
            awaitClose {
                try {
                    deviceRef.removeEventListener(listener)
                } catch (e: Exception) {
                    Log.d(TAG, "Listener removal notice: ${e.message}")
                }
            }
        } catch (e: Exception) {
            Log.w(TAG, "Database observation notice: ${e.message}")
            close(e)
        }
    }

    /**
     * Observe current active security alert for a specific GuardBox device from Firebase Realtime Database.
     */
    fun observeActiveAlert(deviceId: String = targetDeviceId): Flow<com.veronic.guardbox.data.api.ActiveAlertData?> = callbackFlow {
        val currentTarget = deviceId.trim().ifBlank { targetDeviceId.trim() }.ifBlank { DEFAULT_TARGET_DEVICE_ID.trim() }.ifBlank { "guardbox-shop-f20424b4" }
        val db = getDatabaseInstance()

        if (!isFirebaseAvailable || currentTarget.isBlank() || db == null) {
            trySend(null)
            close()
            return@callbackFlow
        }

        try {
            val alertRef = db.reference.child("guardbox/alerts").child(currentTarget).child("current")

            val listener = object : ValueEventListener {
                override fun onDataChange(snapshot: DataSnapshot) {
                    try {
                        if (snapshot.exists()) {
                            val alertId = snapshot.child("alert_id").getValue(String::class.java)
                                ?: snapshot.child("alert_code").getValue(String::class.java)
                            val camName = snapshot.child("camera_name").getValue(String::class.java) ?: "Shop Camera"
                            val reason = snapshot.child("reason").getValue(String::class.java) ?: "Motion detected"
                            val status = snapshot.child("status").getValue(String::class.java) ?: "ACTIVE"
                            val createdAt = snapshot.child("created_at").getValue(String::class.java)
                            val expiresAt = snapshot.child("expires_at").getValue(String::class.java)

                            val snapRef = snapshot.child("snapshot_reference").getValue(String::class.java)
                                ?: snapshot.child("snapshot").child("local_reference").getValue(String::class.java)
                                ?: snapshot.child("snapshot").child("reference").getValue(String::class.java)
                                ?: snapshot.child("snapshot_path").getValue(String::class.java)
                            val snapPath = snapshot.child("snapshot_path").getValue(String::class.java)
                                ?: snapshot.child("snapshot").child("path").getValue(String::class.java)
                            val snapCreated = snapshot.child("snapshot_created_at").getValue(String::class.java)
                                ?: snapshot.child("snapshot").child("created_at").getValue(String::class.java)
                            val snapExpires = snapshot.child("snapshot_expires_at").getValue(String::class.java)
                                ?: snapshot.child("snapshot").child("expires_at").getValue(String::class.java)

                            val remoteRef = snapshot.child("remote_snapshot_reference").getValue(String::class.java)
                                ?: snapshot.child("snapshot").child("remote_reference").getValue(String::class.java)
                                ?: snapshot.child("snapshot_remote_reference").getValue(String::class.java)
                                ?: snapshot.child("remote_reference").getValue(String::class.java)
                            val remoteStatus = snapshot.child("remote_snapshot_status").getValue(String::class.java)
                                ?: snapshot.child("snapshot").child("remote_status").getValue(String::class.java)
                                ?: snapshot.child("snapshot").child("remote_snapshot_status").getValue(String::class.java)
                                ?: snapshot.child("snapshot").child("status").getValue(String::class.java)
                            val remoteUrl = snapshot.child("remote_url").getValue(String::class.java)
                                ?: snapshot.child("signed_url").getValue(String::class.java)
                                ?: snapshot.child("snapshot").child("remote_url").getValue(String::class.java)
                                ?: snapshot.child("snapshot").child("signed_url").getValue(String::class.java)
                            val remoteProvider = snapshot.child("remote_provider").getValue(String::class.java)
                                ?: snapshot.child("snapshot").child("remote_provider").getValue(String::class.java)
                                ?: "supabase"

                            val snapshotMetadata = if (snapRef != null || snapPath != null || remoteRef != null || remoteUrl != null) {
                                com.veronic.guardbox.data.api.SnapshotMetadata(
                                    reference = snapRef,
                                    localReference = snapRef,
                                    remoteReference = remoteRef,
                                    remoteProvider = remoteProvider,
                                    remoteUrl = remoteUrl,
                                    signedUrl = remoteUrl,
                                    path = snapPath,
                                    createdAt = snapCreated,
                                    expiresAt = snapExpires,
                                    status = snapshot.child("snapshot").child("status").getValue(String::class.java) ?: "AVAILABLE",
                                    remoteStatus = remoteStatus
                                )
                            } else null

                            val record = com.veronic.guardbox.data.api.ActiveAlertData(
                                id = 0,
                                alertId = alertId,
                                alertCode = alertId,
                                cameraName = camName,
                                reason = reason,
                                eventType = reason,
                                status = status,
                                createdAt = createdAt,
                                expiresAt = expiresAt,
                                snapshotPath = snapPath,
                                snapshotReference = snapRef,
                                remoteSnapshotReference = remoteRef,
                                remoteSnapshotStatus = remoteStatus,
                                remoteProvider = remoteProvider,
                                remoteUrl = remoteUrl,
                                signedUrl = remoteUrl,
                                snapshotCreatedAt = snapCreated,
                                snapshotExpiresAt = snapExpires,
                                snapshot = snapshotMetadata
                            )
                            trySend(record)
                        } else {
                            trySend(null)
                        }
                    } catch (e: Exception) {
                        trySend(null)
                    }
                }

                override fun onCancelled(error: DatabaseError) {
                    trySend(null)
                }
            }

            alertRef.addValueEventListener(listener)
            awaitClose {
                try {
                    alertRef.removeEventListener(listener)
                } catch (e: Exception) {
                }
            }
        } catch (e: Exception) {
            trySend(null)
            close()
        }
    }

    /**
     * Dispatches a remote command (ARM, DISARM, SILENCE) to Firebase Realtime Database
     * at guardbox/commands/{device_id}/pending/{command_id} and waits for terminal execution status.
     */
    suspend fun sendCommand(
        command: String,
        targetDevId: String = targetDeviceId,
        timeoutMs: Long = 12000L
    ): Result<String> = withContext(Dispatchers.IO) {
        val ctx = appContext
        if (ctx != null) {
            ensureFirebaseApp(ctx)
        }

        if (!isFirebaseAvailable) {
            return@withContext Result.failure(Exception("Firebase is not available on this client."))
        }

        val authSuccess = suspendCancellableCoroutine<Boolean> { cont ->
            ensureAuthenticated { success ->
                if (cont.isActive) cont.resume(success)
            }
        }

        if (!authSuccess) {
            return@withContext Result.failure(Exception("Could not authenticate with Firebase Cloud."))
        }

        val deviceId = targetDevId.trim().ifBlank { targetDeviceId.trim() }.ifBlank { DEFAULT_TARGET_DEVICE_ID.trim() }.ifBlank { "guardbox-shop-f20424b4" }
        if (deviceId.isBlank()) {
            return@withContext Result.failure(Exception("DEVICE NOT CONFIGURED"))
        }

        val db = getDatabaseInstance()
            ?: return@withContext Result.failure(Exception("Firebase Database unavailable."))

        val commandId = "cmd_${System.currentTimeMillis()}_${UUID.randomUUID().toString().take(6)}"
        val uid = FirebaseAuth.getInstance().currentUser?.uid ?: "android_user"
        val isoFormat = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'", Locale.US).apply {
            timeZone = TimeZone.getTimeZone("UTC")
        }
        val isoTimestamp = isoFormat.format(Date())

        val cmdType = command.trim().uppercase()
        val commandPayload = mapOf(
            "command" to cmdType,
            "device_id" to deviceId,
            "target_device_id" to deviceId,
            "created_at" to isoTimestamp,
            "requested_by" to uid,
            "status" to "PENDING"
        )

        val cmdRef = db.reference.child("guardbox/commands").child(deviceId).child("pending").child(commandId)

        try {
            Log.d(TAG, "Writing remote command $cmdType ($commandId) for target device $deviceId")

            val writeSuccess = suspendCancellableCoroutine<Boolean> { cont ->
                cmdRef.setValue(commandPayload).addOnCompleteListener { task ->
                    if (cont.isActive) {
                        if (task.isSuccessful) {
                            cont.resume(true)
                        } else {
                            cont.resumeWithException(task.exception ?: Exception("Failed to write command to Firebase"))
                        }
                    }
                }
            }

            if (!writeSuccess) {
                return@withContext Result.failure(Exception("Failed to dispatch command to cloud."))
            }

            // Wait for Windows Bridge to process and update status to SUCCESS or FAILED
            val executionResult = withTimeoutOrNull(timeoutMs) {
                suspendCancellableCoroutine<Result<String>> { cont ->
                    val listener = object : ValueEventListener {
                        override fun onDataChange(snapshot: DataSnapshot) {
                            if (!snapshot.exists()) return
                            val status = snapshot.child("status").getValue(String::class.java)?.uppercase()
                            val resultMsg = snapshot.child("result").getValue(String::class.java) ?: ""

                            if (status == "SUCCESS") {
                                cmdRef.removeEventListener(this)
                                if (cont.isActive) {
                                    cont.resume(Result.success(resultMsg.ifBlank { "Command executed successfully" }))
                                }
                            } else if (status == "FAILED") {
                                cmdRef.removeEventListener(this)
                                if (cont.isActive) {
                                    cont.resume(Result.failure(Exception(resultMsg.ifBlank { "Command failed on GuardBox" })))
                                }
                            }
                        }

                        override fun onCancelled(error: DatabaseError) {
                            cmdRef.removeEventListener(this)
                            if (cont.isActive) {
                                cont.resume(Result.failure(Exception("Database operation cancelled: ${error.message}")))
                            }
                        }
                    }

                    cmdRef.addValueEventListener(listener)
                    cont.invokeOnCancellation {
                        try {
                            cmdRef.removeEventListener(listener)
                        } catch (e: Exception) {
                            Log.d(TAG, "Error removing listener: ${e.message}")
                        }
                    }
                }
            }

            executionResult ?: Result.failure(Exception("$cmdType COMMAND NOT CONFIRMED"))
        } catch (e: Exception) {
            Log.e(TAG, "Error in sendCommand: ${e.message}", e)
            Result.failure(e)
        }
    }

    /**
     * Retrieve historical alert metadata from Firebase Realtime Database
     * at guardbox/alert_history/{device_id} ordered descending by creation date.
     */
    suspend fun fetchAlertHistory(
        deviceId: String = targetDeviceId,
        limit: Int = 50
    ): Result<List<com.veronic.guardbox.data.api.ActiveAlertData>> = withContext(Dispatchers.IO) {
        val ctx = appContext
        if (ctx != null) {
            ensureFirebaseApp(ctx)
        }

        if (!isFirebaseAvailable) {
            return@withContext Result.failure(Exception("Firebase is not initialized"))
        }

        val authSuccess = suspendCancellableCoroutine<Boolean> { cont ->
            ensureAuthenticated { success ->
                if (cont.isActive) cont.resume(success)
            }
        }

        if (!authSuccess) {
            return@withContext Result.failure(Exception("Firebase Cloud Authentication Failed"))
        }

        val targetId = deviceId.trim().ifBlank { targetDeviceId.trim() }.ifBlank { DEFAULT_TARGET_DEVICE_ID.trim() }.ifBlank { "guardbox-shop-f20424b4" }
        val db = getDatabaseInstance()
            ?: return@withContext Result.failure(Exception("Firebase Database unavailable"))

        try {
            val historyRef = db.reference.child("guardbox/alert_history").child(targetId)
                .limitToLast(limit)

            val snapshot = suspendCancellableCoroutine<DataSnapshot> { cont ->
                val listener = object : ValueEventListener {
                    override fun onDataChange(snapshot: DataSnapshot) {
                        if (cont.isActive) cont.resume(snapshot)
                    }

                    override fun onCancelled(error: DatabaseError) {
                        if (cont.isActive) cont.resumeWithException(Exception("Database query cancelled: ${error.message}"))
                    }
                }
                historyRef.addListenerForSingleValueEvent(listener)
            }

            val alertList = mutableListOf<com.veronic.guardbox.data.api.ActiveAlertData>()
            for (child in snapshot.children) {
                try {
                    val alertId = child.child("alert_id").getValue(String::class.java)
                        ?: child.child("alert_code").getValue(String::class.java)
                        ?: child.key ?: continue

                    val camName = child.child("camera_name").getValue(String::class.java)
                        ?: child.child("camera").getValue(String::class.java)
                        ?: "Shop Camera"
                    val reason = child.child("reason").getValue(String::class.java)
                        ?: child.child("event_type").getValue(String::class.java)?.replace("_", " ")?.replaceFirstChar { it.uppercase() }
                        ?: "Motion detected"
                    val status = child.child("status").getValue(String::class.java) ?: "ACTIVE"
                    val createdAt = child.child("created_at").getValue(String::class.java)
                    val expiresAt = child.child("expires_at").getValue(String::class.java)

                    val snapRef = child.child("snapshot_reference").getValue(String::class.java)
                        ?: child.child("snapshot_path").getValue(String::class.java)
                    val snapPath = child.child("snapshot_path").getValue(String::class.java)
                    val snapCreated = child.child("snapshot_created_at").getValue(String::class.java) ?: createdAt
                    val snapExpires = child.child("snapshot_expires_at").getValue(String::class.java)

                    val remoteRef = child.child("remote_snapshot_reference").getValue(String::class.java)
                        ?: child.child("remote_reference").getValue(String::class.java)
                    val remoteStatus = child.child("remote_snapshot_status").getValue(String::class.java)
                        ?: child.child("snapshot_status").getValue(String::class.java)
                        ?: child.child("remote_status").getValue(String::class.java)
                        ?: "AVAILABLE"
                    val remoteUrl = child.child("remote_url").getValue(String::class.java)
                        ?: child.child("signed_url").getValue(String::class.java)
                    val remoteProvider = child.child("remote_provider").getValue(String::class.java) ?: "supabase"

                    val snapshotMetadata = if (snapRef != null || snapPath != null || remoteRef != null || remoteUrl != null) {
                        com.veronic.guardbox.data.api.SnapshotMetadata(
                            reference = snapRef,
                            localReference = snapRef,
                            remoteReference = remoteRef,
                            remoteProvider = remoteProvider,
                            remoteUrl = remoteUrl,
                            signedUrl = remoteUrl,
                            path = snapPath,
                            createdAt = snapCreated,
                            expiresAt = snapExpires,
                            status = remoteStatus,
                            remoteStatus = remoteStatus
                        )
                    } else null

                    val alertData = com.veronic.guardbox.data.api.ActiveAlertData(
                        id = 0,
                        alertId = alertId,
                        alertCode = alertId,
                        cameraName = camName,
                        reason = reason,
                        eventType = child.child("event_type").getValue(String::class.java) ?: reason,
                        status = status,
                        createdAt = createdAt,
                        expiresAt = expiresAt,
                        snapshotPath = snapPath,
                        snapshotReference = snapRef,
                        remoteSnapshotReference = remoteRef,
                        remoteSnapshotStatus = remoteStatus,
                        remoteProvider = remoteProvider,
                        remoteUrl = remoteUrl,
                        signedUrl = remoteUrl,
                        snapshotCreatedAt = snapCreated,
                        snapshotExpiresAt = snapExpires,
                        snapshot = snapshotMetadata
                    )
                    alertList.add(alertData)
                } catch (e: Exception) {
                    Log.w(TAG, "Error parsing history alert child: ${e.message}")
                }
            }

            // Sort descending by creation date (newest first)
            val sorted = alertList.sortedByDescending { it.effectiveCreatedAt ?: "" }
            Log.i(TAG, "[TRINETRA REMOTE HISTORY FETCHED] count=${sorted.size}")
            Result.success(sorted)
        } catch (e: Exception) {
            Log.e(TAG, "Error fetching remote alert history: ${e.message}", e)
            Result.failure(e)
        }
    }
}
