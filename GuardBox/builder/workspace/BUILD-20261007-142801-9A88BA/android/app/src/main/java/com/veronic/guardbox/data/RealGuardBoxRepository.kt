package com.veronic.guardbox.data

import android.os.Build
import android.util.Log
import com.veronic.guardbox.data.api.ApiClient
import com.veronic.guardbox.data.api.DeviceRegisterRequest
import com.veronic.guardbox.data.api.SystemArmRequest
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.withContext

/**
 * Real GuardBox Repository communicating directly with the GuardBox FastAPI backend.
 * Adheres strictly to the existing server state machine.
 */
class RealGuardBoxRepository(
    private val api: com.veronic.guardbox.data.api.GuardBoxApiService = ApiClient.api
) : GuardBoxRepository {

    private val TAG = "GuardBoxRepository"

    private val _systemStatus = MutableStateFlow(SystemStatus.SYNCING)
    override val systemStatus: StateFlow<SystemStatus> = _systemStatus.asStateFlow()

    private val _serverConnected = MutableStateFlow(false)
    val serverConnected: StateFlow<Boolean> = _serverConnected.asStateFlow()

    private var registeredDeviceId: String? = null

    override suspend fun startSystem(): Result<Unit> = withContext(Dispatchers.IO) {
        try {
            Log.d(TAG, "Sending START (arm) request to GuardBox server...")
            val response = api.armSystem(SystemArmRequest(exitDelaySeconds = 0))
            if (response.isSuccessful && response.body() != null) {
                val body = response.body()!!
                val isRunning = body.armed || body.systemMode.equals("ARMED", ignoreCase = true)
                val newStatus = if (isRunning) SystemStatus.RUNNING else SystemStatus.STOPPED
                _systemStatus.value = newStatus
                _serverConnected.value = true
                Log.i(TAG, "[TRINETRA STATUS]\nstate=${newStatus.name}")
                Log.d(TAG, "Server ARMED successfully. Mode: ${body.systemMode}")
                Result.success(Unit)
            } else {
                val errCode = response.code()
                val errBody = response.errorBody()?.string()
                Log.e(TAG, "Failed to start GuardBox. HTTP $errCode: $errBody")
                Result.failure(Exception("Unable to start GuardBox (HTTP $errCode)"))
            }
        } catch (e: Exception) {
            Log.e(TAG, "Network exception starting GuardBox: ${e.message}", e)
            _serverConnected.value = false
            Result.failure(Exception("Unable to start GuardBox: ${e.localizedMessage ?: "Connection error"}"))
        }
    }

    override suspend fun stopSystem(): Result<Unit> = withContext(Dispatchers.IO) {
        try {
            Log.d(TAG, "Sending STOP (disarm) request to GuardBox server...")
            val response = api.disarmSystem()
            if (response.isSuccessful && response.body() != null) {
                val body = response.body()!!
                val isStopped = !body.armed && body.systemMode.equals("DISARMED", ignoreCase = true)
                val newStatus = if (isStopped) SystemStatus.STOPPED else SystemStatus.RUNNING
                _systemStatus.value = newStatus
                _serverConnected.value = true
                Log.i(TAG, "[TRINETRA STATUS]\nstate=${newStatus.name}")
                Log.d(TAG, "Server DISARMED successfully. Mode: ${body.systemMode}")
                Result.success(Unit)
            } else {
                val errCode = response.code()
                val errBody = response.errorBody()?.string()
                Log.e(TAG, "Failed to stop GuardBox. HTTP $errCode: $errBody")
                Result.failure(Exception("Unable to stop GuardBox (HTTP $errCode)"))
            }
        } catch (e: Exception) {
            Log.e(TAG, "Network exception stopping GuardBox: ${e.message}", e)
            _serverConnected.value = false
            Result.failure(Exception("Unable to stop GuardBox: ${e.localizedMessage ?: "Connection error"}"))
        }
    }

    override suspend fun silenceAlarm(): Result<Unit> = withContext(Dispatchers.IO) {
        try {
            Log.d(TAG, "Sending SILENCE ALARM request to GuardBox server...")
            val response = api.silenceAlarm()
            if (response.isSuccessful) {
                Log.d(TAG, "Simulated alarm silenced successfully on server.")
                _serverConnected.value = true
                Result.success(Unit)
            } else {
                val errCode = response.code()
                val errBody = response.errorBody()?.string()
                Log.e(TAG, "Failed to silence alarm. HTTP $errCode: $errBody")
                Result.failure(Exception("Unable to silence alarm (HTTP $errCode)"))
            }
        } catch (e: Exception) {
            Log.e(TAG, "Network exception silencing alarm: ${e.message}", e)
            Result.failure(Exception("Unable to silence alarm: ${e.localizedMessage ?: "Connection error"}"))
        }
    }

    override suspend fun getSystemStatus(): SystemStatus = withContext(Dispatchers.IO) {
        try {
            val response = api.getSystemStatus()
            if (response.isSuccessful && response.body() != null) {
                val body = response.body()!!
                val isRunning = body.armed || body.systemMode.equals("ARMED", ignoreCase = true)
                val prevStatus = _systemStatus.value
                val status = if (isRunning) SystemStatus.RUNNING else SystemStatus.STOPPED
                _systemStatus.value = status
                _serverConnected.value = true
                Log.i(TAG, "[TRINETRA STATUS]\nstate=${status.name}")
                Log.i(TAG, "[GUARDBOX STATUS RECEIVED]\nsource=LOCAL_API\nstatus=${body.systemMode}")
                if (prevStatus != status) {
                    Log.i(TAG, "[GUARDBOX STATUS SYNC]\nprevious=$prevStatus\ncurrent=$status")
                }
                return@withContext status
            }
        } catch (e: Exception) {
            Log.w(TAG, "Could not fetch system status: ${e.message}")
            _serverConnected.value = false
        }
        return@withContext _systemStatus.value
    }

    /**
     * Register Android device and its FCM registration token with the backend.
     */
    suspend fun registerDevice(
        deviceId: String,
        fcmToken: String,
        userName: String = "GuardBox Android Client",
        deviceName: String = "${Build.MANUFACTURER} ${Build.MODEL}"
    ): Result<Unit> = withContext(Dispatchers.IO) {
        try {
            registeredDeviceId = deviceId
            val req = DeviceRegisterRequest(
                deviceId = deviceId,
                userName = userName,
                fcmToken = fcmToken,
                deviceName = deviceName,
                platform = "android"
            )
            Log.d(TAG, "Registering device with backend: $deviceId")
            val resp = api.registerDevice(req)
            if (resp.isSuccessful && resp.body()?.success == true) {
                Log.d(TAG, "Device registered successfully with backend.")
                _serverConnected.value = true
                Result.success(Unit)
            } else {
                val err = resp.errorBody()?.string() ?: "Registration failed"
                Log.w(TAG, "Device registration failed: $err")
                Result.failure(Exception(err))
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error registering device: ${e.message}", e)
            Result.failure(e)
        }
    }

    /**
     * Dispatch a non-emergency test push notification to this device via backend.
     */
    suspend fun sendTestAlert(deviceId: String? = null): Result<Unit> = withContext(Dispatchers.IO) {
        val targetId = deviceId ?: registeredDeviceId ?: "android_device_primary"
        try {
            Log.d(TAG, "Requesting backend test push notification for device: $targetId")
            val resp = api.sendTestPush(targetId)
            if (resp.isSuccessful && resp.body()?.success == true) {
                Log.d(TAG, "Backend test push sent successfully.")
                Result.success(Unit)
            } else {
                val err = resp.body()?.error ?: resp.errorBody()?.string() ?: "Test push failed"
                Log.w(TAG, "Test push failed: $err")
                Result.failure(Exception(err))
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error requesting test push: ${e.message}", e)
            Result.failure(e)
        }
    }

    /**
     * Poll currently active security alert over local LAN from GET /api/alerts/active
     */
    suspend fun getActiveAlert(): com.veronic.guardbox.data.api.ActiveAlertData? = withContext(Dispatchers.IO) {
        try {
            val response = api.getActiveAlert()
            if (response.isSuccessful && response.body() != null) {
                return@withContext response.body()?.activeAlert
            }
        } catch (e: Exception) {
            Log.w(TAG, "Could not fetch active alert: ${e.message}")
        }
        return@withContext null
    }
}
