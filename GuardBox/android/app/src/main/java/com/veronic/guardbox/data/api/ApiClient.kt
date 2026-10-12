package com.veronic.guardbox.data.api

import android.content.Context
import android.content.SharedPreferences
import android.util.Log
import com.veronic.guardbox.BuildConfig
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.Interceptor
import okhttp3.OkHttpClient
import okhttp3.Response
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.util.concurrent.TimeUnit

enum class ConnectionMode {
    LOCAL,
    REMOTE
}

/**
 * Singleton Retrofit HTTP client for GuardBox Backend Communication.
 * Supports switching dynamically between LOCAL (LAN Wi-Fi) and REMOTE (HTTPS Outbound Tunnel).
 * Injects authentication header (X-GuardBox-Key) securely without hardcoded credentials.
 */
object ApiClient {

    private const val TAG = "ApiClient"
    private const val PREFS_NAME = "guardbox_connection_prefs"
    private const val PREF_MODE = "pref_connection_mode"
    private const val PREF_LOCAL_URL = "pref_local_url"
    private const val PREF_REMOTE_URL = "pref_remote_url"
    private const val PREF_API_KEY = "pref_api_key"

    val DEFAULT_LOCAL_URL: String = BuildConfig.DEFAULT_LOCAL_URL
    val DEFAULT_REMOTE_URL: String = BuildConfig.DEFAULT_REMOTE_URL

    @Volatile
    var connectionMode: ConnectionMode = ConnectionMode.LOCAL
        private set

    @Volatile
    var localUrl: String = DEFAULT_LOCAL_URL
        private set

    @Volatile
    var remoteUrl: String = DEFAULT_REMOTE_URL
        private set

    @Volatile
    var apiKey: String = ""
        private set

    @Volatile
    var baseUrl: String = DEFAULT_LOCAL_URL
        private set

    private var prefs: SharedPreferences? = null

    fun initialize(context: Context) {
        val sp = context.applicationContext.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        prefs = sp

        val savedMode = sp.getString(PREF_MODE, ConnectionMode.LOCAL.name) ?: ConnectionMode.LOCAL.name
        connectionMode = try {
            ConnectionMode.valueOf(savedMode)
        } catch (e: Exception) {
            ConnectionMode.LOCAL
        }

        localUrl = sp.getString(PREF_LOCAL_URL, DEFAULT_LOCAL_URL) ?: DEFAULT_LOCAL_URL
        remoteUrl = sp.getString(PREF_REMOTE_URL, "") ?: ""
        apiKey = sp.getString(PREF_API_KEY, "") ?: ""

        updateActiveBaseUrl()
        rebuildApi()
        Log.i(TAG, "Initialized ApiClient with Mode: $connectionMode, URL: $baseUrl")
    }

    fun setConnectionMode(mode: ConnectionMode) {
        connectionMode = mode
        prefs?.edit()?.putString(PREF_MODE, mode.name)?.apply()
        updateActiveBaseUrl()
        rebuildApi()
        Log.i(TAG, "Switched connection mode to $mode -> $baseUrl")
    }

    fun updateLocalUrl(url: String) {
        val formatted = formatUrl(url)
        localUrl = formatted
        prefs?.edit()?.putString(PREF_LOCAL_URL, formatted)?.apply()
        if (connectionMode == ConnectionMode.LOCAL) {
            updateActiveBaseUrl()
            rebuildApi()
        }
    }

    fun updateRemoteUrl(url: String) {
        val formatted = formatUrl(url)
        remoteUrl = formatted
        prefs?.edit()?.putString(PREF_REMOTE_URL, formatted)?.apply()
        if (connectionMode == ConnectionMode.REMOTE) {
            updateActiveBaseUrl()
            rebuildApi()
        }
    }

    fun updateApiKey(key: String) {
        apiKey = key.trim()
        prefs?.edit()?.putString(PREF_API_KEY, apiKey)?.apply()
        rebuildApi()
    }

    private fun formatUrl(url: String): String {
        val trimmed = url.trim()
        if (trimmed.isBlank()) return ""
        return if (trimmed.endsWith("/")) trimmed else "$trimmed/"
    }

    private fun updateActiveBaseUrl() {
        val validRemoteUrl = if (remoteUrl.isNotBlank()) {
            val testUrl = if (remoteUrl.startsWith("http://") || remoteUrl.startsWith("https://")) remoteUrl else "http://$remoteUrl"
            if (testUrl.toHttpUrlOrNull() != null && !testUrl.endsWith("://") && !testUrl.endsWith(":///")) {
                testUrl
            } else {
                null
            }
        } else {
            null
        }

        baseUrl = if (connectionMode == ConnectionMode.REMOTE && validRemoteUrl != null) {
            validRemoteUrl
        } else {
            if (localUrl.isNotBlank() && localUrl.toHttpUrlOrNull() != null) localUrl else DEFAULT_LOCAL_URL
        }
    }

    /**
     * Unified snapshot URL resolver for TRINETRA.
     * Handles absolute URLs, relative URLs, bare filenames, Windows backslashes, and base URL normalization.
     */
    fun resolveSnapshotUrl(snapshotRef: String?, customBaseUrl: String? = null): String? {
        if (snapshotRef.isNullOrBlank()) return null
        val cleanRef = snapshotRef.trim()
        if (cleanRef.startsWith("http://", ignoreCase = true) || cleanRef.startsWith("https://", ignoreCase = true)) {
            Log.d("TRINETRA_SNAPSHOT", "[TRINETRA SNAPSHOT] alertReference=$snapshotRef resolvedUrl=$cleanRef mode=$connectionMode (absolute)")
            return cleanRef
        }

        val targetBase = (customBaseUrl ?: baseUrl).trim().trimEnd('/')
        val normalized = cleanRef.replace("\\", "/")
        val relativePath = if (normalized.contains("snapshots/")) {
            normalized.substring(normalized.indexOf("snapshots/"))
        } else {
            val filename = normalized.substringAfterLast("/")
            "snapshots/$filename"
        }

        val cleanPath = relativePath.trimStart('/')
        val resolved = "$targetBase/$cleanPath"
        Log.d("TRINETRA_SNAPSHOT", "[TRINETRA SNAPSHOT] reference=$snapshotRef baseUrl=$targetBase resolvedUrl=$resolved mode=$connectionMode")
        return resolved
    }

    fun getSnapshotFullUrl(snapshotRef: String?): String? {
        return resolveSnapshotUrl(snapshotRef, baseUrl)
    }

    private val authInterceptor = Interceptor { chain ->
        val original = chain.request()
        val builder = original.newBuilder()

        // Inject X-GuardBox-Key header if configured
        if (apiKey.isNotBlank()) {
            builder.addHeader("X-GuardBox-Key", apiKey)
        }

        chain.proceed(builder.build())
    }

    private val loggingInterceptor = HttpLoggingInterceptor().apply {
        level = HttpLoggingInterceptor.Level.BODY
    }

    private val okHttpClient = OkHttpClient.Builder()
        .addInterceptor(authInterceptor)
        .addInterceptor(loggingInterceptor)
        .connectTimeout(8, TimeUnit.SECONDS)
        .readTimeout(8, TimeUnit.SECONDS)
        .writeTimeout(8, TimeUnit.SECONDS)
        .retryOnConnectionFailure(true)
        .build()

    @Volatile
    private var _api: GuardBoxApiService = createService(baseUrl)

    val api: GuardBoxApiService
        get() = _api

    private fun rebuildApi() {
        _api = createService(baseUrl)
    }

    private fun createService(url: String): GuardBoxApiService {
        val trimmed = url.trim()
        val withScheme = if (trimmed.startsWith("http://") || trimmed.startsWith("https://")) trimmed else "http://$trimmed"
        val normalizedUrl = if (withScheme.endsWith("/")) withScheme else "$withScheme/"
        val finalUrl = if (normalizedUrl.toHttpUrlOrNull() != null) {
            normalizedUrl
        } else {
            DEFAULT_LOCAL_URL
        }

        return Retrofit.Builder()
            .baseUrl(finalUrl)
            .client(okHttpClient)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
            .create(GuardBoxApiService::class.java)
    }
}
