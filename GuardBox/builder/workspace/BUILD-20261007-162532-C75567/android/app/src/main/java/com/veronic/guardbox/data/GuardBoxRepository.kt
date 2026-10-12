package com.veronic.guardbox.data

import kotlinx.coroutines.flow.StateFlow

/**
 * Represents the operational state of the GuardBox security perimeter.
 */
enum class SystemStatus {
    SYNCING,
    RUNNING,
    STOPPED,
    OFFLINE,
    ERROR,
    UNKNOWN,
    ARMING,
    TEST_MODE,
    MISMATCH,
    NOT_FOUND,
    NOT_AUTHORIZED,
    NOT_CONFIGURED
}

/**
 * Remote cloud connection states.
 */
enum class RemoteConnectionStatus {
    SYNCING,
    ONLINE,
    OFFLINE,
    ERROR,
    MISMATCH,
    NOT_FOUND,
    NOT_AUTHORIZED,
    NOT_CONFIGURED
}

/**
 * Repository interface for GuardBox System Control.
 */
interface GuardBoxRepository {
    val systemStatus: StateFlow<SystemStatus>

    suspend fun startSystem(): Result<Unit>
    suspend fun stopSystem(): Result<Unit>
    suspend fun silenceAlarm(): Result<Unit>
    suspend fun getSystemStatus(): SystemStatus
}
