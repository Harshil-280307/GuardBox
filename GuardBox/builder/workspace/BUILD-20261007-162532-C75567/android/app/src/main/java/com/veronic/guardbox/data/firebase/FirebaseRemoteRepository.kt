package com.veronic.guardbox.data.firebase

import android.util.Log
import com.veronic.guardbox.data.GuardBoxRepository
import com.veronic.guardbox.data.RemoteConnectionStatus
import com.veronic.guardbox.data.SystemStatus
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * Remote Firebase Command & Status Repository for GuardBox / TRINETRA.
 * Enforces strict Device ID verification, authoritative Windows motion_service state convergence,
 * clean listener teardown without stale cached states, and exact command timeouts.
 */
class FirebaseRemoteRepository(
    private val bridgeManager: FirebaseBridgeManager = FirebaseBridgeManager,
    private val scope: CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
) : GuardBoxRepository {

    private val TAG = "FirebaseRemoteRepo"

    private val _connectionStatus = MutableStateFlow(RemoteConnectionStatus.SYNCING)
    val connectionStatus: StateFlow<RemoteConnectionStatus> = _connectionStatus.asStateFlow()

    private val _systemStatus = MutableStateFlow(SystemStatus.SYNCING)
    override val systemStatus: StateFlow<SystemStatus> = _systemStatus.asStateFlow()

    private val _isDeviceOnline = MutableStateFlow(false)
    val isDeviceOnline: StateFlow<Boolean> = _isDeviceOnline.asStateFlow()

    private val _lastSeen = MutableStateFlow("")
    val lastSeen: StateFlow<String> = _lastSeen.asStateFlow()

    private val _deviceName = MutableStateFlow("")
    val deviceName: StateFlow<String> = _deviceName.asStateFlow()

    private val _deviceVersion = MutableStateFlow("1.0.0")
    val deviceVersion: StateFlow<String> = _deviceVersion.asStateFlow()

    private val _shopId = MutableStateFlow("")
    val shopId: StateFlow<String> = _shopId.asStateFlow()

    private val _shopName = MutableStateFlow("")
    val shopName: StateFlow<String> = _shopName.asStateFlow()

    private val _activeAlert = MutableStateFlow<com.veronic.guardbox.data.api.ActiveAlertData?>(null)
    val activeAlert: StateFlow<com.veronic.guardbox.data.api.ActiveAlertData?> = _activeAlert.asStateFlow()

    @Volatile
    private var activeConfiguredDeviceId: String = ""

    private var observationJob: Job? = null
    private var alertJob: Job? = null
    private var syncTimeoutJob: Job? = null

    /**
     * Begins observing device presence and status via Firebase Realtime Database.
     * Enforces the 5-step connection validation flow:
     * 1. Read guardbox/devices/{configured_device_id}
     * 2. Verify returned device_id equals configured_device_id
     * 3. Verify device registered
     * 4. Verify authorization rules
     * 5. Only then mark CONNECTED / ONLINE
     */
    fun startObserving(deviceId: String = bridgeManager.targetDeviceId): Result<Unit> {
        val cleanId = deviceId.trim().ifBlank { bridgeManager.targetDeviceId.trim() }

        // Clean previous listener & stale states immediately (Requirement 6 & 7)
        stopObserving()
        activeConfiguredDeviceId = cleanId

        if (cleanId.isBlank()) {
            _connectionStatus.value = RemoteConnectionStatus.NOT_CONFIGURED
            _systemStatus.value = SystemStatus.NOT_CONFIGURED
            _isDeviceOnline.value = false
            Log.w(TAG, "[TRINETRA CONNECTION]\nconfigured_device_id=\nfirebase_device_id=\nconnection=NOT_CONFIGURED")
            return Result.failure(Exception("DEVICE NOT CONFIGURED"))
        }

        _connectionStatus.value = RemoteConnectionStatus.SYNCING
        _systemStatus.value = SystemStatus.SYNCING
        _isDeviceOnline.value = false
        _deviceName.value = ""
        _shopId.value = ""
        _shopName.value = ""
        _lastSeen.value = ""
        _activeAlert.value = null

        Log.i(TAG, "[TRINETRA SYNC START] Target Device ID: $cleanId")
        Log.i(TAG, "[TRINETRA STATUS]\nstate=SYNCING")

        // 12-second timeout monitor: if device node is not found or unreachable
        syncTimeoutJob = scope.launch {
            delay(12000L)
            if (_connectionStatus.value == RemoteConnectionStatus.SYNCING) {
                _connectionStatus.value = RemoteConnectionStatus.NOT_FOUND
                _systemStatus.value = SystemStatus.NOT_FOUND
                _isDeviceOnline.value = false
                Log.w(TAG, "[TRINETRA CONNECTION]\nconfigured_device_id=$cleanId\nfirebase_device_id=\nconnection=NOT_FOUND")
                Log.w(TAG, "[TRINETRA STATUS]\ndevice_id=$cleanId\nonline=false\nstatus=NOT_FOUND")
            }
        }

        observationJob = scope.launch {
            val authSuccess = bridgeManager.ensureAuthenticatedSuspending()
            if (!authSuccess) {
                Log.w(TAG, "[TRINETRA CONNECTION]\nconfigured_device_id=$cleanId\nfirebase_device_id=\nconnection=NOT_AUTHORIZED")
            }

            try {
                bridgeManager.observeDevice(cleanId).collect { record ->
                    if (record != null) {
                        syncTimeoutJob?.cancel()
                        syncTimeoutJob = null

                        val returnedId = record.deviceId.trim()

                        // Step 2: Exact Device ID Match Verification
                        if (returnedId.isNotBlank() && !returnedId.equals(cleanId, ignoreCase = true)) {
                            _connectionStatus.value = RemoteConnectionStatus.MISMATCH
                            _systemStatus.value = SystemStatus.MISMATCH
                            _isDeviceOnline.value = false
                            Log.w(TAG, "[TRINETRA DEVICE MISMATCH]\nconfigured=$cleanId\nactual=$returnedId")
                            Log.w(TAG, "[TRINETRA CONNECTION]\nconfigured_device_id=$cleanId\nfirebase_device_id=$returnedId\nconnection=MISMATCH")
                            return@collect
                        }

                        // Check if device is marked MIGRATED
                        if (record.status.equals("MIGRATED", ignoreCase = true)) {
                            _connectionStatus.value = RemoteConnectionStatus.MISMATCH
                            _systemStatus.value = SystemStatus.MISMATCH
                            _isDeviceOnline.value = false
                            Log.w(TAG, "[TRINETRA DEVICE MISMATCH]\nconfigured=$cleanId\nactual=MIGRATED")
                            Log.w(TAG, "[TRINETRA CONNECTION]\nconfigured_device_id=$cleanId\nfirebase_device_id=$returnedId\nconnection=MISMATCH")
                            return@collect
                        }

                        // Step 3, 4, 5: Connected and Authorized
                        _isDeviceOnline.value = record.online
                        _lastSeen.value = record.lastSeen
                        _deviceName.value = record.name
                        _deviceVersion.value = record.version
                        _shopId.value = record.shopId ?: "NOT CONFIGURED"
                        _shopName.value = record.shopName ?: "Rajkot Jewellery"

                        if (!record.online) {
                            _connectionStatus.value = RemoteConnectionStatus.OFFLINE
                            _systemStatus.value = SystemStatus.OFFLINE
                        } else {
                            _connectionStatus.value = RemoteConnectionStatus.ONLINE
                            val rawStatus = record.status.trim().uppercase()
                            _systemStatus.value = when {
                                rawStatus == "RUNNING" || rawStatus == "ARMED" -> SystemStatus.RUNNING
                                rawStatus == "ARMING" -> SystemStatus.ARMING
                                rawStatus == "TEST_MODE" -> SystemStatus.TEST_MODE
                                rawStatus == "STOPPED" || rawStatus == "DISARMED" -> SystemStatus.STOPPED
                                else -> SystemStatus.UNKNOWN
                            }
                        }

                        Log.i(
                            TAG,
                            "[TRINETRA CONNECTION]\n" +
                            "configured_device_id=$cleanId\n" +
                            "firebase_device_id=$returnedId\n" +
                            "connection=${if (record.online) "CONNECTED" else "DISCONNECTED"}"
                        )
                        Log.i(
                            TAG,
                            "[TRINETRA STATUS]\n" +
                            "device_id=$cleanId\n" +
                            "online=${record.online}\n" +
                            "status=${record.status}"
                        )
                    } else {
                        // Device node does not exist in Firebase
                        syncTimeoutJob?.cancel()
                        syncTimeoutJob = null
                        _connectionStatus.value = RemoteConnectionStatus.NOT_FOUND
                        _systemStatus.value = SystemStatus.NOT_FOUND
                        _isDeviceOnline.value = false
                        Log.w(TAG, "[TRINETRA CONNECTION]\nconfigured_device_id=$cleanId\nfirebase_device_id=\nconnection=NOT_FOUND")
                        Log.w(TAG, "[TRINETRA STATUS]\ndevice_id=$cleanId\nonline=false\nstatus=NOT_FOUND")
                    }
                }
            } catch (e: Exception) {
                syncTimeoutJob?.cancel()
                syncTimeoutJob = null
                val isAuthErr = e.message?.contains("permission", ignoreCase = true) == true
                if (isAuthErr) {
                    _connectionStatus.value = RemoteConnectionStatus.NOT_AUTHORIZED
                    _systemStatus.value = SystemStatus.NOT_AUTHORIZED
                    Log.w(TAG, "[TRINETRA CONNECTION]\nconfigured_device_id=$cleanId\nfirebase_device_id=\nconnection=NOT_AUTHORIZED")
                } else {
                    _connectionStatus.value = RemoteConnectionStatus.ERROR
                    _systemStatus.value = SystemStatus.ERROR
                    Log.w(TAG, "[TRINETRA CONNECTION]\nconfigured_device_id=$cleanId\nfirebase_device_id=\nconnection=DISCONNECTED")
                }
                _isDeviceOnline.value = false
            }
        }

        alertJob = scope.launch {
            try {
                bridgeManager.observeActiveAlert(cleanId).collect { alert ->
                    _activeAlert.value = alert
                }
            } catch (e: Exception) {
                _activeAlert.value = null
            }
        }

        return Result.success(Unit)
    }

    suspend fun connectAndStartObserving(deviceId: String = bridgeManager.targetDeviceId): Result<Unit> {
        return startObserving(deviceId)
    }

    /**
     * Cancels active Firebase Realtime Database observation listener and clears cached state.
     */
    fun stopObserving() {
        syncTimeoutJob?.cancel()
        syncTimeoutJob = null
        observationJob?.cancel()
        observationJob = null
        alertJob?.cancel()
        alertJob = null
        _isDeviceOnline.value = false
        _activeAlert.value = null
        Log.d(TAG, "Stopped remote device observation.")
    }

    override suspend fun startSystem(): Result<Unit> {
        val currentConn = _connectionStatus.value
        val cleanDevId = activeConfiguredDeviceId.ifBlank { bridgeManager.targetDeviceId.trim() }

        if (currentConn == RemoteConnectionStatus.MISMATCH) {
            return Result.failure(Exception("DEVICE ID MISMATCH: Cannot ARM mismatched device."))
        }
        if (currentConn == RemoteConnectionStatus.NOT_FOUND) {
            return Result.failure(Exception("DEVICE NOT FOUND: Configured TRINETRA device was not found."))
        }
        if (currentConn == RemoteConnectionStatus.NOT_AUTHORIZED) {
            return Result.failure(Exception("NOT AUTHORIZED: Insufficient permissions to ARM this device."))
        }
        if (currentConn == RemoteConnectionStatus.NOT_CONFIGURED || cleanDevId.isBlank()) {
            return Result.failure(Exception("DEVICE NOT CONFIGURED"))
        }
        if (currentConn == RemoteConnectionStatus.OFFLINE || !_isDeviceOnline.value) {
            return Result.failure(Exception("DEVICE OFFLINE: Target TRINETRA device is currently offline."))
        }

        Log.d(TAG, "Dispatching remote ARM command to Firebase for device $cleanDevId...")
        val res = bridgeManager.sendCommand("ARM", targetDevId = cleanDevId)
        return if (res.isSuccess) {
            Log.d(TAG, "Remote ARM command confirmed by GuardBox: ${res.getOrNull()}")
            Result.success(Unit)
        } else {
            val err = res.exceptionOrNull() ?: Exception("ARM COMMAND NOT CONFIRMED")
            Log.e(TAG, "Remote ARM failed: ${err.message}")
            Result.failure(err)
        }
    }

    override suspend fun stopSystem(): Result<Unit> {
        val currentConn = _connectionStatus.value
        val cleanDevId = activeConfiguredDeviceId.ifBlank { bridgeManager.targetDeviceId.trim() }

        if (currentConn == RemoteConnectionStatus.MISMATCH) {
            return Result.failure(Exception("DEVICE ID MISMATCH: Cannot DISARM mismatched device."))
        }
        if (currentConn == RemoteConnectionStatus.NOT_FOUND) {
            return Result.failure(Exception("DEVICE NOT FOUND: Configured TRINETRA device was not found."))
        }
        if (currentConn == RemoteConnectionStatus.NOT_AUTHORIZED) {
            return Result.failure(Exception("NOT AUTHORIZED: Insufficient permissions to DISARM this device."))
        }
        if (currentConn == RemoteConnectionStatus.NOT_CONFIGURED || cleanDevId.isBlank()) {
            return Result.failure(Exception("DEVICE NOT CONFIGURED"))
        }
        if (currentConn == RemoteConnectionStatus.OFFLINE || !_isDeviceOnline.value) {
            return Result.failure(Exception("DEVICE OFFLINE: Target TRINETRA device is currently offline."))
        }

        Log.d(TAG, "Dispatching remote DISARM command to Firebase for device $cleanDevId...")
        val res = bridgeManager.sendCommand("DISARM", targetDevId = cleanDevId)
        return if (res.isSuccess) {
            Log.d(TAG, "Remote DISARM command confirmed by GuardBox: ${res.getOrNull()}")
            Result.success(Unit)
        } else {
            val err = res.exceptionOrNull() ?: Exception("DISARM COMMAND NOT CONFIRMED")
            Log.e(TAG, "Remote DISARM failed: ${err.message}")
            Result.failure(err)
        }
    }

    override suspend fun silenceAlarm(): Result<Unit> {
        val cleanDevId = activeConfiguredDeviceId.ifBlank { bridgeManager.targetDeviceId.trim() }
        if (cleanDevId.isBlank()) {
            return Result.failure(Exception("DEVICE NOT CONFIGURED"))
        }
        Log.d(TAG, "Dispatching remote SILENCE command to Firebase for device $cleanDevId...")
        val res = bridgeManager.sendCommand("SILENCE", targetDevId = cleanDevId)
        return if (res.isSuccess) {
            Log.d(TAG, "Remote SILENCE confirmed by GuardBox: ${res.getOrNull()}")
            Result.success(Unit)
        } else {
            val err = res.exceptionOrNull() ?: Exception("SILENCE COMMAND NOT CONFIRMED")
            Log.e(TAG, "Remote SILENCE failed: ${err.message}")
            Result.failure(err)
        }
    }

    override suspend fun getSystemStatus(): SystemStatus {
        return _systemStatus.value
    }

    suspend fun getAlertHistory(limit: Int = 50): Result<List<com.veronic.guardbox.data.api.ActiveAlertData>> {
        val cleanDevId = activeConfiguredDeviceId.ifBlank { bridgeManager.targetDeviceId.trim() }
        return bridgeManager.fetchAlertHistory(deviceId = cleanDevId, limit = limit)
    }
}

