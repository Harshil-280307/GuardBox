package com.veronic.guardbox.ui

import android.annotation.SuppressLint
import android.content.Context
import android.os.Build
import android.provider.Settings
import android.util.Log
import androidx.core.app.NotificationManagerCompat
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.google.firebase.messaging.FirebaseMessaging
import com.veronic.guardbox.data.GuardBoxRepository
import com.veronic.guardbox.data.RealGuardBoxRepository
import com.veronic.guardbox.data.SystemStatus
import com.veronic.guardbox.data.api.ApiClient
import com.veronic.guardbox.data.api.ConnectionMode
import com.veronic.guardbox.data.firebase.FirebaseBridgeManager
import com.veronic.guardbox.data.firebase.FirebaseRemoteRepository
import com.veronic.guardbox.notification.NotificationHelper
import com.veronic.guardbox.service.GuardBoxAlertService
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

enum class DeviceRegistrationStatus {
    NOT_REGISTERED,
    REGISTERING,
    REGISTERED,
    FAILED
}

class MainViewModel(
    private val localRepository: RealGuardBoxRepository = RealGuardBoxRepository(),
    private val remoteRepository: FirebaseRemoteRepository = FirebaseRemoteRepository()
) : ViewModel() {

    private val TAG = "MainViewModel"

    private val _connectionMode = MutableStateFlow(ConnectionMode.LOCAL)
    val connectionMode: StateFlow<ConnectionMode> = _connectionMode.asStateFlow()

    private val _systemStatus = MutableStateFlow(SystemStatus.SYNCING)
    val systemStatus: StateFlow<SystemStatus> = _systemStatus.asStateFlow()

    private val _isServerConnected = MutableStateFlow(true)
    val isServerConnected: StateFlow<Boolean> = _isServerConnected.asStateFlow()

    private val _remoteLastSeen = MutableStateFlow("")
    val remoteLastSeen: StateFlow<String> = _remoteLastSeen.asStateFlow()

    private val _targetDeviceId = MutableStateFlow(FirebaseBridgeManager.DEFAULT_TARGET_DEVICE_ID)
    val targetDeviceId: StateFlow<String> = _targetDeviceId.asStateFlow()

    private val _deviceName = MutableStateFlow("TRINETRA Jewellery Security")
    val deviceName: StateFlow<String> = _deviceName.asStateFlow()

    private val _softwareVersion = MutableStateFlow("1.0.0")
    val softwareVersion: StateFlow<String> = _softwareVersion.asStateFlow()

    private val _shopId = MutableStateFlow("SHOP-RK-001")
    val shopId: StateFlow<String> = _shopId.asStateFlow()

    private val _shopName = MutableStateFlow("Rajkot Jewellery")
    val shopName: StateFlow<String> = _shopName.asStateFlow()

    private val _remoteConnectionStatus = MutableStateFlow(com.veronic.guardbox.data.RemoteConnectionStatus.SYNCING)
    val remoteConnectionStatus: StateFlow<com.veronic.guardbox.data.RemoteConnectionStatus> = _remoteConnectionStatus.asStateFlow()

    private val _registrationStatus = MutableStateFlow(DeviceRegistrationStatus.NOT_REGISTERED)
    val registrationStatus: StateFlow<DeviceRegistrationStatus> = _registrationStatus.asStateFlow()

    private val _showSetupGuide = MutableStateFlow(false)
    val showSetupGuide: StateFlow<Boolean> = _showSetupGuide.asStateFlow()

    private val _activeAlert = MutableStateFlow<com.veronic.guardbox.data.api.ActiveAlertData?>(null)
    val activeAlert: StateFlow<com.veronic.guardbox.data.api.ActiveAlertData?> = _activeAlert.asStateFlow()

    private val _alertHistory = MutableStateFlow<List<com.veronic.guardbox.data.api.ActiveAlertData>>(emptyList())
    val alertHistory: StateFlow<List<com.veronic.guardbox.data.api.ActiveAlertData>> = _alertHistory.asStateFlow()

    private val _isHistoryLoading = MutableStateFlow(false)
    val isHistoryLoading: StateFlow<Boolean> = _isHistoryLoading.asStateFlow()

    private val _historyError = MutableStateFlow<String?>(null)
    val historyError: StateFlow<String?> = _historyError.asStateFlow()

    private val _commandFeedback = MutableStateFlow<String?>(null)
    val commandFeedback: StateFlow<String?> = _commandFeedback.asStateFlow()

    private val _notificationsEnabled = MutableStateFlow(true)
    val notificationsEnabled: StateFlow<Boolean> = _notificationsEnabled.asStateFlow()

    private val _isLoading = MutableStateFlow(false)
    val isLoading: StateFlow<Boolean> = _isLoading.asStateFlow()

    private val _actionError = MutableStateFlow<String?>(null)
    val actionError: StateFlow<String?> = _actionError.asStateFlow()

    private val _alarmVolumeRatio = MutableStateFlow(0.8f)
    val alarmVolumeRatio: StateFlow<Float> = _alarmVolumeRatio.asStateFlow()

    private val _isSilencing = MutableStateFlow(false)
    val isSilencing: StateFlow<Boolean> = _isSilencing.asStateFlow()

    private val _activeBaseUrl = MutableStateFlow(ApiClient.DEFAULT_LOCAL_URL)
    val activeBaseUrl: StateFlow<String> = _activeBaseUrl.asStateFlow()

    private val _remoteUrl = MutableStateFlow("")
    val remoteUrl: StateFlow<String> = _remoteUrl.asStateFlow()

    private val _apiKey = MutableStateFlow("")
    val apiKey: StateFlow<String> = _apiKey.asStateFlow()

    private var lastAttemptedAction: (() -> Unit)? = null
    private var cachedDeviceId: String = "android_device_${Build.MODEL.replace(" ", "_")}"
    private var appContext: Context? = null

    init {
        Log.i(TAG, "[TRINETRA STATUS]\nstate=SYNCING")

        // Observe local repository status
        viewModelScope.launch {
            localRepository.systemStatus.collect { status ->
                if (_connectionMode.value == ConnectionMode.LOCAL) {
                    _systemStatus.value = status
                    Log.i(TAG, "[TRINETRA STATUS]\nstate=${status.name}")
                    syncAlertService(status)
                }
            }
        }

        // Observe local repository server connection
        viewModelScope.launch {
            localRepository.serverConnected.collect { connected ->
                if (_connectionMode.value == ConnectionMode.LOCAL) {
                    _isServerConnected.value = connected
                }
            }
        }

        // Observe remote repository status
        viewModelScope.launch {
            remoteRepository.systemStatus.collect { status ->
                if (_connectionMode.value == ConnectionMode.REMOTE) {
                    _systemStatus.value = status
                    Log.i(TAG, "[TRINETRA STATUS]\nstate=${status.name}")
                    syncAlertService(status)
                }
            }
        }

        // Observe remote repository active alert
        viewModelScope.launch {
            remoteRepository.activeAlert.collect { alert ->
                if (_connectionMode.value == ConnectionMode.REMOTE) {
                    if (alert != null) {
                        val isExpired = com.veronic.guardbox.notification.AlertLifecycleHelper.isAlertExpired(alert.effectiveCreatedAt, alert.expiresAt)
                        _activeAlert.value = if (!isExpired) alert else null
                    } else {
                        // If null received, check if existing active alert is still within 60s visibility
                        val current = _activeAlert.value
                        if (current != null && !com.veronic.guardbox.notification.AlertLifecycleHelper.isAlertExpired(current.effectiveCreatedAt, current.expiresAt)) {
                            // Retain current active alert until 60-second lifecycle completes
                        } else {
                            _activeAlert.value = null
                        }
                    }
                }
            }
        }

        // Observe remote repository online state
        viewModelScope.launch {
            remoteRepository.isDeviceOnline.collect { online ->
                if (_connectionMode.value == ConnectionMode.REMOTE) {
                    _isServerConnected.value = online
                }
            }
        }

        // Observe remote repository last seen timestamp
        viewModelScope.launch {
            remoteRepository.lastSeen.collect { lastSeen ->
                _remoteLastSeen.value = lastSeen
            }
        }

        // Observe remote repository device name
        viewModelScope.launch {
            remoteRepository.deviceName.collect { name ->
                if (name.isNotBlank()) {
                    _deviceName.value = name
                }
            }
        }

        // Observe remote repository software version
        viewModelScope.launch {
            remoteRepository.deviceVersion.collect { ver ->
                if (ver.isNotBlank()) {
                    _softwareVersion.value = ver
                }
            }
        }

        // Observe remote repository shop ID & Name
        viewModelScope.launch {
            remoteRepository.shopId.collect { sId ->
                if (sId.isNotBlank()) {
                    _shopId.value = sId
                }
            }
        }
        viewModelScope.launch {
            remoteRepository.shopName.collect { sName ->
                if (sName.isNotBlank()) {
                    _shopName.value = sName
                }
            }
        }

        // Observe remote repository connection status
        viewModelScope.launch {
            remoteRepository.connectionStatus.collect { status ->
                _remoteConnectionStatus.value = status
            }
        }

        // Background LOCAL system status & alert polling loop (disabled when in REMOTE mode)
        viewModelScope.launch {
            while (isActive) {
                if (_connectionMode.value == ConnectionMode.LOCAL) {
                    try {
                        val status = localRepository.getSystemStatus()
                        _systemStatus.value = status
                        _isServerConnected.value = true
                        val alert = localRepository.getActiveAlert()
                        if (alert != null) {
                            val isExpired = com.veronic.guardbox.notification.AlertLifecycleHelper.isAlertExpired(alert.effectiveCreatedAt, alert.expiresAt)
                            _activeAlert.value = if (!isExpired) alert else null
                        } else {
                            val current = _activeAlert.value
                            if (current != null && !com.veronic.guardbox.notification.AlertLifecycleHelper.isAlertExpired(current.effectiveCreatedAt, current.expiresAt)) {
                                // Retain current active alert until 60-second lifecycle completes
                            } else {
                                _activeAlert.value = null
                            }
                        }
                        syncAlertService(status)
                    } catch (e: Exception) {
                        _isServerConnected.value = false
                        Log.w(TAG, "Local backend sync notice: ${e.message}")
                    }
                }
                delay(3000)
            }
        }

        // 60-Second Active Alert Expiration Watcher
        viewModelScope.launch {
            while (isActive) {
                val current = _activeAlert.value
                if (current != null) {
                    if (com.veronic.guardbox.notification.AlertLifecycleHelper.isAlertExpired(current.effectiveCreatedAt, current.expiresAt)) {
                        Log.i(TAG, "[TRINETRA ALERT 60S LIFECYCLE COMPLETED] alert_id=${current.effectiveAlertId}")
                        _activeAlert.value = null
                    }
                }
                delay(1000)
            }
        }
    }

    private fun syncAlertService(status: SystemStatus) {
        appContext?.let { ctx ->
            if (status == SystemStatus.RUNNING && !GuardBoxAlertService.isRunning) {
                GuardBoxAlertService.start(ctx)
            } else if (status == SystemStatus.STOPPED && GuardBoxAlertService.isRunning) {
                GuardBoxAlertService.stop(ctx)
            }
        }
    }

    fun checkNotificationPermission(context: Context) {
        appContext = context.applicationContext
        val enabled = NotificationManagerCompat.from(context).areNotificationsEnabled()
        _notificationsEnabled.value = enabled
    }

    @SuppressLint("HardwareIds")
    fun initialize(context: Context) {
        appContext = context.applicationContext
        ApiClient.initialize(context)
        FirebaseBridgeManager.initialize(context)

        _connectionMode.value = ApiClient.connectionMode
        _activeBaseUrl.value = ApiClient.baseUrl
        _remoteUrl.value = ApiClient.remoteUrl
        _apiKey.value = ApiClient.apiKey
        _targetDeviceId.value = FirebaseBridgeManager.targetDeviceId

        val sp = context.getSharedPreferences("trinetra_device_prefs", Context.MODE_PRIVATE)
        val isRegistered = sp.getBoolean("pref_device_registered", false)
        if (isRegistered) {
            _registrationStatus.value = DeviceRegistrationStatus.REGISTERED
        }
        val hasCompletedSetup = sp.getBoolean("pref_has_completed_setup", false)
        _showSetupGuide.value = !hasCompletedSetup

        checkNotificationPermission(context)
        refreshAlarmVolume(context)
        initializeDeviceRegistration(context)

        // If previously saved in REMOTE mode, connect safely
        if (ApiClient.connectionMode == ConnectionMode.REMOTE) {
            setConnectionMode(ConnectionMode.REMOTE)
        }
    }

    fun openSetupGuide() {
        _showSetupGuide.value = true
    }

    fun dismissSetupGuide() {
        _showSetupGuide.value = false
        appContext?.getSharedPreferences("trinetra_device_prefs", Context.MODE_PRIVATE)
            ?.edit()
            ?.putBoolean("pref_has_completed_setup", true)
            ?.apply()
    }

    /**
     * Switch connection mode safely without crashing.
     * Verifies remote connection first before enabling REMOTE state.
     */
    fun setConnectionMode(mode: ConnectionMode) {
        if (mode == ConnectionMode.LOCAL) {
            remoteRepository.stopObserving()
            ApiClient.setConnectionMode(ConnectionMode.LOCAL)
            _connectionMode.value = ConnectionMode.LOCAL
            _activeBaseUrl.value = ApiClient.baseUrl
            _systemStatus.value = SystemStatus.SYNCING
            _actionError.value = null
            _commandFeedback.value = null

            Log.i(TAG, "[TRINETRA STATUS]\nstate=SYNCING")
            viewModelScope.launch {
                try {
                    _systemStatus.value = localRepository.getSystemStatus()
                } catch (e: Exception) {
                    Log.w(TAG, "Switched to LOCAL notice: ${e.message}")
                }
            }
        } else {
            val deviceId = _targetDeviceId.value.trim()
            ApiClient.setConnectionMode(ConnectionMode.REMOTE)
            _connectionMode.value = ConnectionMode.REMOTE
            _activeBaseUrl.value = ApiClient.baseUrl
            _actionError.value = null
            _commandFeedback.value = null

            if (deviceId.isBlank()) {
                _systemStatus.value = SystemStatus.NOT_CONFIGURED
                _remoteConnectionStatus.value = com.veronic.guardbox.data.RemoteConnectionStatus.NOT_CONFIGURED
                _actionError.value = "DEVICE NOT CONFIGURED"
                Log.w(TAG, "[TRINETRA CONNECTION]\nconfigured_device_id=\nfirebase_device_id=\nconnection=NOT_CONFIGURED")
                return
            }

            _systemStatus.value = SystemStatus.SYNCING
            Log.i(TAG, "[TRINETRA STATUS]\nstate=SYNCING")
            viewModelScope.launch {
                val connectResult = remoteRepository.startObserving(deviceId)
                if (connectResult.isFailure) {
                    val err = connectResult.exceptionOrNull()?.message ?: "Failed to start cloud observation"
                    _actionError.value = err
                }
            }
        }
    }

    fun updateRemoteConfig(url: String, key: String, targetDevice: String) {
        val cleanDevice = targetDevice.trim()
        ApiClient.updateRemoteUrl(url)
        ApiClient.updateApiKey(key)
        FirebaseBridgeManager.updateTargetDeviceId(cleanDevice)

        _remoteUrl.value = ApiClient.remoteUrl
        _apiKey.value = ApiClient.apiKey
        _activeBaseUrl.value = ApiClient.baseUrl
        _targetDeviceId.value = cleanDevice

        if (cleanDevice.isNotBlank()) {
            FirebaseMessaging.getInstance().token.addOnCompleteListener { task ->
                if (task.isSuccessful && !task.result.isNullOrBlank()) {
                    val token = task.result!!
                    val tokenLength = token.length
                    Log.d(TAG, "FCM TOKEN GENERATED\ntoken_exists=true\ntoken_length=$tokenLength")
                    FirebaseBridgeManager.registerFcmToken(token, clientDeviceId = cleanDevice)
                }
            }
        }

        // If in REMOTE mode, reconnect with new device identity
        if (_connectionMode.value == ConnectionMode.REMOTE) {
            setConnectionMode(ConnectionMode.REMOTE)
        }
    }

    fun updateLocalUrl(url: String) {
        ApiClient.updateLocalUrl(url)
        _activeBaseUrl.value = ApiClient.baseUrl
    }

    fun refreshAlarmVolume(context: Context) {
        try {
            val audioManager = context.getSystemService(Context.AUDIO_SERVICE) as? android.media.AudioManager
            if (audioManager != null) {
                val current = audioManager.getStreamVolume(android.media.AudioManager.STREAM_ALARM)
                val max = audioManager.getStreamMaxVolume(android.media.AudioManager.STREAM_ALARM)
                if (max > 0) {
                    _alarmVolumeRatio.value = (current.toFloat() / max.toFloat()).coerceIn(0f, 1f)
                }
            }
        } catch (e: Exception) {
            Log.w(TAG, "Could not read alarm volume: ${e.message}")
        }
    }

    fun setAlarmVolume(context: Context, ratio: Float) {
        val clamped = ratio.coerceIn(0f, 1f)
        _alarmVolumeRatio.value = clamped
        try {
            val audioManager = context.getSystemService(Context.AUDIO_SERVICE) as? android.media.AudioManager
            if (audioManager != null) {
                val max = audioManager.getStreamMaxVolume(android.media.AudioManager.STREAM_ALARM)
                val targetIndex = (clamped * max).toInt().coerceIn(0, max)
                audioManager.setStreamVolume(android.media.AudioManager.STREAM_ALARM, targetIndex, 0)
            }
        } catch (e: Exception) {
            Log.w(TAG, "Could not set alarm stream volume: ${e.message}")
        }
    }

    fun silenceAlarm(context: Context) {
        _isSilencing.value = true
        _commandFeedback.value = "Silencing alarm..."
        NotificationHelper.cancelEmergencyAlert(context.applicationContext)

        viewModelScope.launch {
            try {
                val activeRepo: GuardBoxRepository = if (_connectionMode.value == ConnectionMode.REMOTE) {
                    remoteRepository
                } else {
                    localRepository
                }

                val res = activeRepo.silenceAlarm()
                if (res.isSuccess) {
                    _commandFeedback.value = "Alarm Silenced"
                    delay(2500)
                    if (_commandFeedback.value == "Alarm Silenced") {
                        _commandFeedback.value = null
                    }
                } else {
                    _commandFeedback.value = "Silence Failed"
                    _actionError.value = res.exceptionOrNull()?.message ?: "Unable to silence alarm."
                }
            } catch (e: Exception) {
                _commandFeedback.value = "Silence Failed"
                Log.w(TAG, "Silence alarm notice: ${e.message}")
            } finally {
                _isSilencing.value = false
            }
        }
    }

    @SuppressLint("HardwareIds")
    fun initializeDeviceRegistration(context: Context) {
        retryDeviceRegistration(context)
    }

    @SuppressLint("HardwareIds")
    fun retryDeviceRegistration(context: Context? = appContext) {
        val ctx = context ?: appContext ?: return
        appContext = ctx.applicationContext
        _registrationStatus.value = DeviceRegistrationStatus.REGISTERING

        try {
            val androidId = Settings.Secure.getString(ctx.contentResolver, Settings.Secure.ANDROID_ID)
            if (!androidId.isNullOrBlank()) {
                cachedDeviceId = androidId
            }

            Log.d("GuardBoxFCM", "FCM TOKEN REQUEST START")
            FirebaseMessaging.getInstance().token.addOnCompleteListener { task ->
                if (task.isSuccessful && !task.result.isNullOrBlank()) {
                    val token = task.result!!
                    val tokenLength = token.length
                    Log.d("GuardBoxFCM", "FCM TOKEN GENERATED\ntoken_exists=true\ntoken_length=$tokenLength")
                    
                    viewModelScope.launch {
                        var cloudSuccess = false
                        var localSuccess = false

                        // 1. Register in Firebase Cloud RTDB (works everywhere via Internet)
                        try {
                            FirebaseBridgeManager.registerFcmToken(token)
                            cloudSuccess = true
                        } catch (e: Exception) {
                            Log.w(TAG, "Firebase cloud token registration notice: ${e.message}")
                        }

                        // 2. Register with local Windows backend if reachable on LAN
                        try {
                            val localRes = localRepository.registerDevice(
                                deviceId = cachedDeviceId,
                                fcmToken = token,
                                userName = "TRINETRA Customer Client",
                                deviceName = "${Build.MANUFACTURER} ${Build.MODEL}"
                            )
                            localSuccess = localRes.isSuccess
                        } catch (e: Exception) {
                            Log.d(TAG, "Local backend token registration notice (normal in Remote mode): ${e.message}")
                        }

                        if (cloudSuccess || localSuccess) {
                            _registrationStatus.value = DeviceRegistrationStatus.REGISTERED
                            ctx.getSharedPreferences("trinetra_device_prefs", Context.MODE_PRIVATE)
                                .edit()
                                .putBoolean("pref_device_registered", true)
                                .apply()
                            Log.i(TAG, "Device registration completed successfully (cloud=$cloudSuccess, local=$localSuccess)")
                        } else {
                            _registrationStatus.value = DeviceRegistrationStatus.FAILED
                        }
                    }
                } else {
                    Log.d("GuardBoxFCM", "FCM TOKEN RESULT\ntoken_exists=false\ntoken_length=0")
                    _registrationStatus.value = DeviceRegistrationStatus.FAILED
                }
            }
        } catch (e: Exception) {
            Log.d("GuardBoxFCM", "Device registration notice: ${e.message}")
            _registrationStatus.value = DeviceRegistrationStatus.FAILED
        }
    }

    fun startSystem() {
        _actionError.value = null
        lastAttemptedAction = { startSystem() }

        if (_connectionMode.value == ConnectionMode.REMOTE) {
            val status = _remoteConnectionStatus.value
            when (status) {
                com.veronic.guardbox.data.RemoteConnectionStatus.MISMATCH -> {
                    _actionError.value = "DEVICE ID MISMATCH: Cannot ARM mismatched device."
                    _commandFeedback.value = "Failed"
                    return
                }
                com.veronic.guardbox.data.RemoteConnectionStatus.NOT_FOUND -> {
                    _actionError.value = "DEVICE NOT FOUND: Configured TRINETRA device was not found."
                    _commandFeedback.value = "Failed"
                    return
                }
                com.veronic.guardbox.data.RemoteConnectionStatus.NOT_AUTHORIZED -> {
                    _actionError.value = "NOT AUTHORIZED: Insufficient permissions to ARM this device."
                    _commandFeedback.value = "Failed"
                    return
                }
                com.veronic.guardbox.data.RemoteConnectionStatus.NOT_CONFIGURED -> {
                    _actionError.value = "DEVICE NOT CONFIGURED"
                    _commandFeedback.value = "Failed"
                    return
                }
                com.veronic.guardbox.data.RemoteConnectionStatus.OFFLINE -> {
                    _actionError.value = "DEVICE OFFLINE: Target TRINETRA device is currently offline."
                    _commandFeedback.value = "Failed"
                    return
                }
                else -> {}
            }
        }

        _isLoading.value = true
        _commandFeedback.value = "Sending START..."

        viewModelScope.launch {
            val activeRepo: GuardBoxRepository = if (_connectionMode.value == ConnectionMode.REMOTE) {
                remoteRepository
            } else {
                localRepository
            }

            val result = activeRepo.startSystem()
            _isLoading.value = false

            if (result.isFailure) {
                _commandFeedback.value = "Failed"
                _actionError.value = result.exceptionOrNull()?.localizedMessage ?: "Unable to start TRINETRA."
            } else {
                _commandFeedback.value = "Command Confirmed"
                _actionError.value = null
                delay(2000)
                if (_commandFeedback.value == "Command Confirmed") {
                    _commandFeedback.value = null
                }
            }
        }
    }

    fun stopSystem() {
        _actionError.value = null
        lastAttemptedAction = { stopSystem() }

        if (_connectionMode.value == ConnectionMode.REMOTE) {
            val status = _remoteConnectionStatus.value
            when (status) {
                com.veronic.guardbox.data.RemoteConnectionStatus.MISMATCH -> {
                    _actionError.value = "DEVICE ID MISMATCH: Cannot DISARM mismatched device."
                    _commandFeedback.value = "Failed"
                    return
                }
                com.veronic.guardbox.data.RemoteConnectionStatus.NOT_FOUND -> {
                    _actionError.value = "DEVICE NOT FOUND: Configured TRINETRA device was not found."
                    _commandFeedback.value = "Failed"
                    return
                }
                com.veronic.guardbox.data.RemoteConnectionStatus.NOT_AUTHORIZED -> {
                    _actionError.value = "NOT AUTHORIZED: Insufficient permissions to DISARM this device."
                    _commandFeedback.value = "Failed"
                    return
                }
                com.veronic.guardbox.data.RemoteConnectionStatus.NOT_CONFIGURED -> {
                    _actionError.value = "DEVICE NOT CONFIGURED"
                    _commandFeedback.value = "Failed"
                    return
                }
                com.veronic.guardbox.data.RemoteConnectionStatus.OFFLINE -> {
                    _actionError.value = "DEVICE OFFLINE: Target TRINETRA device is currently offline."
                    _commandFeedback.value = "Failed"
                    return
                }
                else -> {}
            }
        }

        _isLoading.value = true
        _commandFeedback.value = "Sending STOP..."

        viewModelScope.launch {
            val activeRepo: GuardBoxRepository = if (_connectionMode.value == ConnectionMode.REMOTE) {
                remoteRepository
            } else {
                localRepository
            }

            val result = activeRepo.stopSystem()
            _isLoading.value = false

            if (result.isFailure) {
                _commandFeedback.value = "Failed"
                _actionError.value = result.exceptionOrNull()?.localizedMessage ?: "Unable to stop TRINETRA."
            } else {
                _commandFeedback.value = "Command Confirmed"
                _actionError.value = null
                delay(2000)
                if (_commandFeedback.value == "Command Confirmed") {
                    _commandFeedback.value = null
                }
            }
        }
    }

    fun retryLastAction() {
        _actionError.value = null
        _commandFeedback.value = null
        lastAttemptedAction?.invoke()
    }

    fun clearError() {
        _actionError.value = null
        _commandFeedback.value = null
    }

    fun triggerTestAlert(context: Context) {
        val testId = "TRI-TEST-${System.currentTimeMillis()}"
        NotificationHelper.triggerSecurityAlert(
            context = context,
            alertId = testId,
            cameraName = "Main Gate",
            reason = "TEST: Security alert delivery verified"
        )

        if (_connectionMode.value == ConnectionMode.LOCAL) {
            viewModelScope.launch {
                localRepository.sendTestAlert(cachedDeviceId)
            }
        }
    }

    fun refreshAlertHistory() {
        viewModelScope.launch(kotlinx.coroutines.Dispatchers.IO) {
            _isHistoryLoading.value = true
            _historyError.value = null
            try {
                if (_connectionMode.value == ConnectionMode.REMOTE) {
                    val remoteResult = remoteRepository.getAlertHistory(limit = 50)
                    if (remoteResult.isSuccess) {
                        val list = remoteResult.getOrNull() ?: emptyList()
                        _alertHistory.value = list
                    } else {
                        val ex = remoteResult.exceptionOrNull()
                        _alertHistory.value = emptyList()
                        _historyError.value = ex?.message ?: "Failed to load remote alert history from Firebase Bridge"
                    }
                    return@launch
                }

                val response = ApiClient.api.getRecentAlerts(limit = 50)
                if (response.isSuccessful && response.body() != null) {
                    _alertHistory.value = response.body()!!
                } else {
                    _historyError.value = "Failed to load alert history (HTTP ${response.code()})"
                }
            } catch (e: Exception) {
                val errorMsg = when {
                    e is java.net.ConnectException || e.message?.contains("failed to connect", ignoreCase = true) == true ->
                        "Cannot connect to TRINETRA backend at ${_activeBaseUrl.value}. Check Wi-Fi connection and backend IP address."
                    e is java.net.SocketTimeoutException ->
                        "Connection timed out while reaching TRINETRA backend at ${_activeBaseUrl.value}."
                    else -> e.message ?: "Connection error while loading alert history"
                }
                _historyError.value = errorMsg
            } finally {
                _isHistoryLoading.value = false
            }
        }
    }

    override fun onCleared() {
        super.onCleared()
        remoteRepository.stopObserving()
    }
}
