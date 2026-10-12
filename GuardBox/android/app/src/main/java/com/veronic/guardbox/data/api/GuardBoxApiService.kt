package com.veronic.guardbox.data.api

import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Path

/**
 * Retrofit API interface connecting directly to the real GuardBox FastAPI backend.
 */
interface GuardBoxApiService {

    @GET("/system/status")
    suspend fun getSystemStatus(): Response<SystemStatusResponse>

    @POST("/system/arm")
    suspend fun armSystem(@Body request: SystemArmRequest = SystemArmRequest(exitDelaySeconds = 0)): Response<SystemStatusResponse>

    @POST("/system/disarm")
    suspend fun disarmSystem(@Body emptyBody: Map<String, String> = emptyMap()): Response<SystemStatusResponse>

    @POST("/api/devices/register")
    suspend fun registerDevice(@Body request: DeviceRegisterRequest): Response<DeviceRegisterResponse>

    @POST("/api/devices/{device_id}/test-push")
    suspend fun sendTestPush(@Path("device_id") deviceId: String): Response<TestPushResponse>

    @GET("/api/alerts/active")
    suspend fun getActiveAlert(): Response<ActiveAlertResponse>

    @GET("/api/alerts")
    suspend fun getRecentAlerts(@retrofit2.http.Query("limit") limit: Int = 50): Response<List<ActiveAlertData>>

    @POST("/alarm/silence")
    suspend fun silenceAlarm(@Body emptyBody: Map<String, String> = emptyMap()): Response<AlarmStatusResponse>
}
