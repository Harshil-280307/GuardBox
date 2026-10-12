package com.veronic.guardbox.data

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * DEMO IMPLEMENTATION — REPLACE WITH REAL API IN PHASE 2
 *
 * This repository manages local in-memory system state for Phase 1 verification.
 * It is NOT connected to the real GuardBox server yet.
 */
class DemoGuardBoxRepository : GuardBoxRepository {

    private val _systemStatus = MutableStateFlow(SystemStatus.RUNNING)
    override val systemStatus: StateFlow<SystemStatus> = _systemStatus.asStateFlow()

    override suspend fun startSystem(): Result<Unit> {
        _systemStatus.value = SystemStatus.RUNNING
        return Result.success(Unit)
    }

    override suspend fun stopSystem(): Result<Unit> {
        _systemStatus.value = SystemStatus.STOPPED
        return Result.success(Unit)
    }

    override suspend fun silenceAlarm(): Result<Unit> {
        return Result.success(Unit)
    }

    override suspend fun getSystemStatus(): SystemStatus {
        return _systemStatus.value
    }
}
