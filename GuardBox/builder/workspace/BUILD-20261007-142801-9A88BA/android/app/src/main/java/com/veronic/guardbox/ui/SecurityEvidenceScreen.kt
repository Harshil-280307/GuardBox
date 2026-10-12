package com.veronic.guardbox.ui

import android.util.Log
import android.widget.Toast
import coil.request.ImageRequest
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Download
import androidx.compose.material.icons.filled.HourglassEmpty
import androidx.compose.material.icons.filled.ImageNotSupported
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.SaveAlt
import androidx.compose.material.icons.filled.Security
import androidx.compose.material.icons.filled.Visibility
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import coil.compose.SubcomposeAsyncImage
import coil.compose.SubcomposeAsyncImageContent
import com.veronic.guardbox.data.api.ActiveAlertData
import com.veronic.guardbox.data.api.ConnectionMode
import com.veronic.guardbox.notification.AlertLifecycleHelper
import com.veronic.guardbox.ui.theme.CyanAccent
import com.veronic.guardbox.ui.theme.DarkBg
import com.veronic.guardbox.ui.theme.DarkCard
import com.veronic.guardbox.ui.theme.DarkCardBorder
import com.veronic.guardbox.ui.theme.DarkSurface
import com.veronic.guardbox.ui.theme.EmergencyRed
import com.veronic.guardbox.ui.theme.EmergencyRedBg
import com.veronic.guardbox.ui.theme.SuccessGreen
import com.veronic.guardbox.ui.theme.TextMuted
import com.veronic.guardbox.ui.theme.TextPrimary
import com.veronic.guardbox.ui.theme.TextSecondary
import com.veronic.guardbox.ui.theme.WarningYellow
import com.veronic.guardbox.util.SnapshotStorageHelper
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale
import java.util.TimeZone

enum class EvidenceFilter(val label: String) {
    ALL("ALL"),
    TODAY("TODAY"),
    THIS_WEEK("THIS WEEK"),
    SAVED("SAVED"),
    RECENT("ACTIVE/RECENT")
}

@Composable
fun SecurityEvidenceScreen(
    viewModel: MainViewModel,
    onBack: () -> Unit,
    modifier: Modifier = Modifier
) {
    val context = LocalContext.current
    val coroutineScope = rememberCoroutineScope()
    val alertHistory by viewModel.alertHistory.collectAsState()
    val isHistoryLoading by viewModel.isHistoryLoading.collectAsState()
    val historyError by viewModel.historyError.collectAsState()
    val activeBaseUrl by viewModel.activeBaseUrl.collectAsState()
    val connectionMode by viewModel.connectionMode.collectAsState()

    var selectedFilter by remember { mutableStateOf(EvidenceFilter.ALL) }
    var selectedAlertForDetail by remember { mutableStateOf<ActiveAlertData?>(null) }
    var selectedAlertForFullScreen by remember { mutableStateOf<ActiveAlertData?>(null) }

    // Fetch history when screen is opened
    LaunchedEffect(Unit) {
        viewModel.refreshAlertHistory()
    }

    // Filter alerts locally
    val filteredAlerts = remember(alertHistory, selectedFilter) {
        val now = System.currentTimeMillis()
        val calendar = Calendar.getInstance()

        // Beginning of today (local time)
        calendar.set(Calendar.HOUR_OF_DAY, 0)
        calendar.set(Calendar.MINUTE, 0)
        calendar.set(Calendar.SECOND, 0)
        calendar.set(Calendar.MILLISECOND, 0)
        val todayStartMs = calendar.timeInMillis

        // Beginning of this week (7 days ago)
        val weekStartMs = now - (7L * 24 * 3600 * 1000)

        alertHistory.filter { alert ->
            val alertTimeMs = parseIsoToMillis(alert.effectiveCreatedAt)
            when (selectedFilter) {
                EvidenceFilter.ALL -> true
                EvidenceFilter.TODAY -> alertTimeMs >= todayStartMs
                EvidenceFilter.THIS_WEEK -> alertTimeMs >= weekStartMs
                EvidenceFilter.SAVED -> SnapshotStorageHelper.isSnapshotSavedLocally(context, alert.effectiveAlertId ?: "")
                EvidenceFilter.RECENT -> {
                    val isExpired = alert.isSnapshotExpired
                    !isExpired || (alert.status == "WAITING_ACK" || alert.status == "ACTIVE")
                }
            }
        }
    }

    Surface(
        modifier = modifier.fillMaxSize(),
        color = DarkBg
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(horizontal = 16.dp, vertical = 12.dp)
        ) {
            // Top Bar
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(bottom = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    IconButton(onClick = onBack) {
                        Icon(
                            imageVector = Icons.AutoMirrored.Filled.ArrowBack,
                            contentDescription = "Back",
                            tint = Color.White
                        )
                    }
                    Spacer(modifier = Modifier.width(4.dp))
                    Column {
                        Text(
                            text = "SECURITY EVIDENCE",
                            color = Color.White,
                            fontSize = 18.sp,
                            fontWeight = FontWeight.Bold,
                            letterSpacing = 1.sp
                        )
                        Text(
                            text = "Recent security events",
                            color = TextMuted,
                            fontSize = 12.sp
                        )
                    }
                }

                IconButton(
                    onClick = { viewModel.refreshAlertHistory() },
                    enabled = !isHistoryLoading
                ) {
                    if (isHistoryLoading) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(20.dp),
                            color = CyanAccent,
                            strokeWidth = 2.dp
                        )
                    } else {
                        Icon(
                            imageVector = Icons.Default.Refresh,
                            contentDescription = "Refresh",
                            tint = CyanAccent
                        )
                    }
                }
            }

            // Filter Chips
            LazyRow(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(vertical = 6.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                items(EvidenceFilter.values()) { filter ->
                    val isSelected = selectedFilter == filter
                    FilterChip(
                        selected = isSelected,
                        onClick = { selectedFilter = filter },
                        label = {
                            Text(
                                text = filter.label,
                                fontSize = 11.sp,
                                fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Normal
                            )
                        },
                        colors = FilterChipDefaults.filterChipColors(
                            containerColor = DarkSurface,
                            labelColor = TextSecondary,
                            selectedContainerColor = CyanAccent.copy(alpha = 0.2f),
                            selectedLabelColor = CyanAccent
                        ),
                        border = FilterChipDefaults.filterChipBorder(
                            enabled = true,
                            selected = isSelected,
                            borderColor = DarkCardBorder,
                            selectedBorderColor = CyanAccent
                        ),
                        shape = RoundedCornerShape(16.dp)
                    )
                }
            }

            Spacer(modifier = Modifier.height(8.dp))

            // Error Banner if history loading failed
            historyError?.let { err ->
                Card(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(bottom = 12.dp),
                    shape = RoundedCornerShape(10.dp),
                    colors = CardDefaults.cardColors(containerColor = EmergencyRedBg),
                    border = BorderStroke(1.dp, EmergencyRed.copy(alpha = 0.5f))
                ) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(12.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(
                            imageVector = Icons.Default.ImageNotSupported,
                            contentDescription = "Error",
                            tint = EmergencyRed,
                            modifier = Modifier.size(20.dp)
                        )
                        Spacer(modifier = Modifier.width(8.dp))
                        Text(
                            text = err,
                            color = Color.White,
                            fontSize = 12.sp,
                            modifier = Modifier.weight(1f)
                        )
                        TextButton(onClick = { viewModel.refreshAlertHistory() }) {
                            Text("Retry", color = CyanAccent, fontSize = 12.sp)
                        }
                    }
                }
            }

            // Evidence Cards List
            if (filteredAlerts.isEmpty()) {
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .weight(1f),
                    contentAlignment = Alignment.Center
                ) {
                    Column(
                        horizontalAlignment = Alignment.CenterHorizontally,
                        modifier = Modifier.padding(horizontal = 24.dp)
                    ) {
                        if (isHistoryLoading) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(36.dp),
                                color = CyanAccent,
                                strokeWidth = 3.dp
                            )
                            Spacer(modifier = Modifier.height(14.dp))
                            Text(
                                text = "Loading security evidence...",
                                color = TextSecondary,
                                fontSize = 14.sp,
                                fontWeight = FontWeight.Medium
                            )
                        } else if (historyError != null) {
                            Icon(
                                imageVector = Icons.Default.Warning,
                                contentDescription = "Connection Error",
                                tint = WarningYellow,
                                modifier = Modifier.size(48.dp)
                            )
                            Spacer(modifier = Modifier.height(12.dp))
                            Text(
                                text = "Evidence History Unavailable",
                                color = Color.White,
                                fontSize = 15.sp,
                                fontWeight = FontWeight.Bold
                            )
                            Spacer(modifier = Modifier.height(6.dp))
                            Text(
                                text = historyError ?: "Backend service is not reachable",
                                color = TextMuted,
                                fontSize = 12.sp,
                                textAlign = androidx.compose.ui.text.style.TextAlign.Center
                            )
                            Spacer(modifier = Modifier.height(14.dp))
                            Button(
                                onClick = { viewModel.refreshAlertHistory() },
                                colors = ButtonDefaults.buttonColors(
                                    containerColor = CyanAccent,
                                    contentColor = Color.Black
                                ),
                                shape = RoundedCornerShape(8.dp)
                            ) {
                                Icon(
                                    imageVector = Icons.Default.Refresh,
                                    contentDescription = "Retry",
                                    modifier = Modifier.size(16.dp)
                                )
                                Spacer(modifier = Modifier.width(6.dp))
                                Text("RETRY CONNECTION", fontSize = 12.sp, fontWeight = FontWeight.Bold)
                            }
                        } else {
                            Icon(
                                imageVector = Icons.Default.Security,
                                contentDescription = "No Events",
                                tint = TextMuted,
                                modifier = Modifier.size(48.dp)
                            )
                            Spacer(modifier = Modifier.height(12.dp))
                            Text(
                                text = "No security events found",
                                color = Color.White,
                                fontSize = 15.sp,
                                fontWeight = FontWeight.SemiBold
                            )
                            Spacer(modifier = Modifier.height(4.dp))
                            Text(
                                text = "No events match the '${selectedFilter.label}' filter criteria.",
                                color = TextMuted,
                                fontSize = 12.sp,
                                textAlign = androidx.compose.ui.text.style.TextAlign.Center
                            )
                        }
                    }
                }
            } else {
                LazyColumn(
                    modifier = Modifier
                        .fillMaxWidth()
                        .weight(1f),
                    verticalArrangement = Arrangement.spacedBy(14.dp),
                    contentPadding = PaddingValues(bottom = 16.dp)
                ) {
                    items(filteredAlerts, key = { it.effectiveAlertId ?: it.id.toString() }) { alert ->
                        EvidenceAlertCard(
                            alert = alert,
                            baseUrl = activeBaseUrl,
                            connectionMode = connectionMode,
                            onCardClick = { selectedAlertForDetail = alert },
                            onSnapshotClick = { selectedAlertForFullScreen = alert }
                        )
                    }
                }
            }
        }
    }

    // Alert Detail Modal
    selectedAlertForDetail?.let { alert ->
        AlertDetailDialog(
            alert = alert,
            baseUrl = activeBaseUrl,
            connectionMode = connectionMode,
            onDismiss = { selectedAlertForDetail = null },
            onViewFullSnapshot = {
                selectedAlertForDetail = null
                selectedAlertForFullScreen = alert
            }
        )
    }

    // Full Screen Snapshot Viewer
    selectedAlertForFullScreen?.let { alert ->
        FullScreenSnapshotViewer(
            alert = alert,
            baseUrl = activeBaseUrl,
            connectionMode = connectionMode,
            onDismiss = { selectedAlertForFullScreen = null }
        )
    }
}

@Composable
fun EvidenceAlertCard(
    alert: ActiveAlertData,
    baseUrl: String,
    connectionMode: ConnectionMode = ConnectionMode.LOCAL,
    onCardClick: () -> Unit,
    onSnapshotClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    val context = LocalContext.current
    val coroutineScope = rememberCoroutineScope()
    val effectiveId = alert.effectiveAlertId ?: "UNKNOWN"
    val fullSnapshotUrl = alert.getFullSnapshotUrl(baseUrl)
    val isExpired = alert.isSnapshotExpired
    val detectedTime = AlertLifecycleHelper.formatDisplayTime(alert.effectiveCreatedAt)
    val expiryTime = AlertLifecycleHelper.formatDisplayTime(alert.effectiveSnapshotExpiresAt)

    var isSavedLocally by remember(effectiveId) {
        mutableStateOf(SnapshotStorageHelper.isSnapshotSavedLocally(context, effectiveId))
    }
    var isSaving by remember(effectiveId) { mutableStateOf(false) }
    var snapshotRetryKey by remember(effectiveId, fullSnapshotUrl) { mutableStateOf(0) }

    val localRecord = remember(effectiveId, isSavedLocally) {
        SnapshotStorageHelper.getLocalSavedRecord(context, effectiveId)
    }

    // Resolve remote snapshot URL via Supabase Storage signed URL when in REMOTE mode
    var remoteDownloadUrl by remember(alert.effectiveRemoteUrl, alert.effectiveRemoteReference, snapshotRetryKey) {
        mutableStateOf<String?>(com.veronic.guardbox.util.RemoteEvidenceHelper.resolveRemoteUrl(alert))
    }
    var isResolvingRemote by remember(alert.effectiveRemoteUrl, alert.effectiveRemoteReference, snapshotRetryKey) {
        mutableStateOf(false)
    }

    LaunchedEffect(alert.effectiveRemoteUrl, alert.effectiveRemoteReference, connectionMode, snapshotRetryKey) {
        if (connectionMode == ConnectionMode.REMOTE && localRecord == null) {
            remoteDownloadUrl = com.veronic.guardbox.util.RemoteEvidenceHelper.resolveRemoteUrl(alert)
        } else {
            remoteDownloadUrl = null
        }
        isResolvingRemote = false
    }

    val effectiveImageModel: Any? = localRecord?.localUri
        ?: if (connectionMode == ConnectionMode.REMOTE) remoteDownloadUrl else fullSnapshotUrl

    val activeDownloadUrl: String? = (localRecord?.localUri
        ?: if (connectionMode == ConnectionMode.REMOTE) remoteDownloadUrl else fullSnapshotUrl)?.toString()

    val imageRequest = remember(effectiveImageModel, snapshotRetryKey, effectiveId) {
        effectiveImageModel?.let { model ->
            ImageRequest.Builder(context)
                .data(model)
                .memoryCacheKey("alert_${effectiveId}_${snapshotRetryKey}")
                .diskCacheKey("alert_${effectiveId}_${snapshotRetryKey}")
                .crossfade(true)
                .setParameter("retry", snapshotRetryKey, memoryCacheKey = null)
                .listener(
                    onStart = {
                        Log.i("TRINETRA_SNAPSHOT", "[TRINETRA SNAPSHOT EVIDENCE START] alertId=$effectiveId reference=${alert.effectiveSnapshotReference} remoteRef=${alert.effectiveRemoteReference} resolvedModel=$model mode=$connectionMode")
                    },
                    onSuccess = { _, result ->
                        Log.i("TRINETRA_SNAPSHOT", "[TRINETRA SNAPSHOT EVIDENCE SUCCESS] alertId=$effectiveId model=$model dataSource=${result.dataSource}")
                    },
                    onError = { _, result ->
                        Log.e("TRINETRA_SNAPSHOT", "[TRINETRA SNAPSHOT EVIDENCE ERROR] alertId=$effectiveId model=$model error=${result.throwable.message}")
                    }
                )
                .build()
        }
    }

    Card(
        modifier = modifier
            .fillMaxWidth()
            .clickable { onCardClick() },
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = DarkCard),
        border = BorderStroke(1.dp, DarkCardBorder)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(14.dp)
        ) {
            // Card Top Row: Reason badge + Detection Time
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(
                        modifier = Modifier
                            .size(8.dp)
                            .clip(CircleShape)
                            .background(if (isExpired && !isSavedLocally) WarningYellow else EmergencyRed)
                    )
                    Spacer(modifier = Modifier.width(6.dp))
                    Text(
                        text = alert.effectiveReason,
                        color = Color.White,
                        fontSize = 14.sp,
                        fontWeight = FontWeight.Bold
                    )
                }

                Text(
                    text = detectedTime,
                    color = TextMuted,
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Medium
                )
            }

            Spacer(modifier = Modifier.height(10.dp))

            // Snapshot Thumbnail Area
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(140.dp)
                    .clip(RoundedCornerShape(10.dp))
                    .background(Color.Black.copy(alpha = 0.5f))
                    .border(BorderStroke(0.5.dp, DarkCardBorder), RoundedCornerShape(10.dp)),
                contentAlignment = Alignment.Center
            ) {
                if (isExpired && !isSavedLocally) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Icon(
                            imageVector = Icons.Default.HourglassEmpty,
                            contentDescription = "Expired",
                            tint = WarningYellow,
                            modifier = Modifier.size(28.dp)
                        )
                        Spacer(modifier = Modifier.height(6.dp))
                        Text(
                            text = "SNAPSHOT EXPIRED",
                            color = WarningYellow,
                            fontSize = 11.sp,
                            fontWeight = FontWeight.Bold,
                            letterSpacing = 0.5.sp
                        )
                    }
                } else if (connectionMode == ConnectionMode.REMOTE && !isSavedLocally && (alert.effectiveRemoteStatus == "UPLOADING" || alert.snapshot?.status == "UPLOADING")) {
                    Column(
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.Center,
                        modifier = Modifier.fillMaxSize().padding(8.dp)
                    ) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(20.dp),
                            color = CyanAccent,
                            strokeWidth = 2.dp
                        )
                        Spacer(modifier = Modifier.height(4.dp))
                        Text(
                            text = "Evidence uploading...",
                            color = CyanAccent,
                            fontSize = 10.sp,
                            fontWeight = FontWeight.SemiBold
                        )
                    }
                } else if (connectionMode == ConnectionMode.REMOTE && !isSavedLocally && alert.effectiveRemoteStatus == "FAILED") {
                    Column(
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.Center,
                        modifier = Modifier.fillMaxSize().padding(8.dp)
                    ) {
                        Icon(
                            imageVector = Icons.Default.Warning,
                            contentDescription = "Failed",
                            tint = WarningYellow,
                            modifier = Modifier.size(24.dp)
                        )
                        Spacer(modifier = Modifier.height(4.dp))
                        Text(
                            text = "Evidence upload failed",
                            color = WarningYellow,
                            fontSize = 10.sp,
                            fontWeight = FontWeight.SemiBold
                        )
                    }
                } else if (isResolvingRemote) {
                    Column(
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.Center,
                        modifier = Modifier.fillMaxSize()
                    ) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(20.dp),
                            color = CyanAccent,
                            strokeWidth = 2.dp
                        )
                        Spacer(modifier = Modifier.height(4.dp))
                        Text(
                            text = "Loading remote...",
                            color = TextMuted,
                            fontSize = 10.sp
                        )
                    }
                } else if (connectionMode == ConnectionMode.REMOTE && alert.effectiveRemoteReference.isNullOrBlank() && !isSavedLocally) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Icon(
                            imageVector = Icons.Default.ImageNotSupported,
                            contentDescription = "Unavailable",
                            tint = TextMuted,
                            modifier = Modifier.size(28.dp)
                        )
                        Spacer(modifier = Modifier.height(6.dp))
                        Text(
                            text = "REMOTE EVIDENCE UNAVAILABLE",
                            color = TextMuted,
                            fontSize = 10.sp,
                            fontWeight = FontWeight.Medium
                        )
                    }
                } else if (imageRequest == null) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Icon(
                            imageVector = Icons.Default.ImageNotSupported,
                            contentDescription = "Unavailable",
                            tint = TextMuted,
                            modifier = Modifier.size(28.dp)
                        )
                        Spacer(modifier = Modifier.height(6.dp))
                        Text(
                            text = "EVIDENCE UNAVAILABLE",
                            color = TextMuted,
                            fontSize = 11.sp,
                            fontWeight = FontWeight.Medium
                        )
                    }
                } else {
                    SubcomposeAsyncImage(
                        model = imageRequest,
                        contentDescription = "Evidence Snapshot",
                        modifier = Modifier
                            .fillMaxSize()
                            .clip(RoundedCornerShape(10.dp))
                            .clickable { onSnapshotClick() },
                        contentScale = ContentScale.Crop,
                        loading = {
                            Box(
                                modifier = Modifier.fillMaxSize(),
                                contentAlignment = Alignment.Center
                            ) {
                                CircularProgressIndicator(
                                    modifier = Modifier.size(20.dp),
                                    color = CyanAccent,
                                    strokeWidth = 2.dp
                                )
                            }
                        },
                        error = {
                            Column(
                                horizontalAlignment = Alignment.CenterHorizontally,
                                verticalArrangement = Arrangement.Center,
                                modifier = Modifier.fillMaxSize().padding(8.dp)
                            ) {
                                Icon(
                                    imageVector = Icons.Default.Warning,
                                    contentDescription = "Error",
                                    tint = WarningYellow,
                                    modifier = Modifier.size(24.dp)
                                )
                                Spacer(modifier = Modifier.height(4.dp))
                                Text(
                                    text = "Unable to load evidence",
                                    color = WarningYellow,
                                    fontSize = 11.sp,
                                    fontWeight = FontWeight.SemiBold
                                )
                                Spacer(modifier = Modifier.height(4.dp))
                                OutlinedButton(
                                    onClick = { snapshotRetryKey++ },
                                    shape = RoundedCornerShape(6.dp),
                                    contentPadding = PaddingValues(horizontal = 8.dp, vertical = 2.dp),
                                    border = BorderStroke(1.dp, CyanAccent),
                                    colors = ButtonDefaults.outlinedButtonColors(contentColor = CyanAccent),
                                    modifier = Modifier.height(26.dp)
                                ) {
                                    Icon(
                                        imageVector = Icons.Default.Refresh,
                                        contentDescription = "Retry",
                                        modifier = Modifier.size(12.dp)
                                    )
                                    Spacer(modifier = Modifier.width(4.dp))
                                    Text(text = "RETRY", fontSize = 10.sp, fontWeight = FontWeight.Bold)
                                }
                            }
                        },
                        success = {
                            SubcomposeAsyncImageContent()
                        }
                    )
                }
            }

            Spacer(modifier = Modifier.height(10.dp))

            // Metadata summary
            Text(
                text = "Camera: ${alert.cameraName ?: "Main Shop Camera"}",
                color = TextSecondary,
                fontSize = 12.sp
            )

            Spacer(modifier = Modifier.height(2.dp))

            Text(
                text = "Alert ID: $effectiveId",
                color = TextPrimary,
                fontSize = 12.sp,
                fontWeight = FontWeight.Bold,
                fontFamily = FontFamily.Monospace
            )

            Spacer(modifier = Modifier.height(8.dp))

            // Status badges row: Snapshot Status + Local Phone Save Status
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                // Snapshot server status
                if (isSavedLocally) {
                    Text(
                        text = "Snapshot: Saved on phone",
                        color = SuccessGreen,
                        fontSize = 11.sp,
                        fontWeight = FontWeight.SemiBold
                    )
                } else if (isExpired) {
                    Text(
                        text = "Snapshot: Expired",
                        color = WarningYellow,
                        fontSize = 11.sp,
                        fontWeight = FontWeight.Medium
                    )
                } else {
                    Text(
                        text = "Snapshot: Available until $expiryTime",
                        color = TextMuted,
                        fontSize = 11.sp
                    )
                }

                // Phone saved status
                if (isSavedLocally) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(
                            imageVector = Icons.Default.Check,
                            contentDescription = "Saved",
                            tint = SuccessGreen,
                            modifier = Modifier.size(13.dp)
                        )
                        Spacer(modifier = Modifier.width(3.dp))
                        Text(
                            text = "Saved to phone",
                            color = SuccessGreen,
                            fontSize = 11.sp,
                            fontWeight = FontWeight.Bold
                        )
                    }
                } else if (!isExpired && !activeDownloadUrl.isNullOrBlank()) {
                    TextButton(
                        onClick = {
                            if (!isSaving) {
                                isSaving = true
                                Toast.makeText(context, "Saving snapshot...", Toast.LENGTH_SHORT).show()
                                coroutineScope.launch {
                                    val res = SnapshotStorageHelper.saveSnapshotToDevice(context, effectiveId, activeDownloadUrl)
                                    isSaving = false
                                    if (res.isSuccess) {
                                        isSavedLocally = true
                                        Toast.makeText(context, "Snapshot saved to phone", Toast.LENGTH_SHORT).show()
                                    } else {
                                        Toast.makeText(context, "Could not save snapshot", Toast.LENGTH_SHORT).show()
                                    }
                                }
                            }
                        },
                        contentPadding = PaddingValues(horizontal = 6.dp, vertical = 0.dp),
                        modifier = Modifier.height(28.dp)
                    ) {
                        Icon(
                            imageVector = Icons.Default.Download,
                            contentDescription = "Save",
                            tint = CyanAccent,
                            modifier = Modifier.size(14.dp)
                        )
                        Spacer(modifier = Modifier.width(4.dp))
                        Text("SAVE", color = CyanAccent, fontSize = 11.sp, fontWeight = FontWeight.Bold)
                    }
                } else {
                    Text(
                        text = "Not saved",
                        color = TextMuted,
                        fontSize = 11.sp
                    )
                }
            }
        }
    }
}

@Composable
fun AlertDetailDialog(
    alert: ActiveAlertData,
    baseUrl: String,
    connectionMode: ConnectionMode = ConnectionMode.LOCAL,
    onDismiss: () -> Unit,
    onViewFullSnapshot: () -> Unit
) {
    val context = LocalContext.current
    val coroutineScope = rememberCoroutineScope()
    val effectiveId = alert.effectiveAlertId ?: "UNKNOWN"
    val fullSnapshotUrl = alert.getFullSnapshotUrl(baseUrl)
    val isExpired = alert.isSnapshotExpired
    val detectedTime = AlertLifecycleHelper.formatDisplayTime(alert.effectiveCreatedAt)
    val expiryTime = AlertLifecycleHelper.formatDisplayTime(alert.effectiveSnapshotExpiresAt)

    var isSavedLocally by remember(effectiveId) {
        mutableStateOf(SnapshotStorageHelper.isSnapshotSavedLocally(context, effectiveId))
    }
    var isSaving by remember(effectiveId) { mutableStateOf(false) }
    var snapshotRetryKey by remember(effectiveId, fullSnapshotUrl) { mutableStateOf(0) }

    val localRecord = remember(effectiveId, isSavedLocally) {
        SnapshotStorageHelper.getLocalSavedRecord(context, effectiveId)
    }

    // Resolve remote snapshot URL via Supabase Storage signed URL when in REMOTE mode
    var remoteDownloadUrl by remember(alert.effectiveRemoteUrl, alert.effectiveRemoteReference, snapshotRetryKey) {
        mutableStateOf<String?>(com.veronic.guardbox.util.RemoteEvidenceHelper.resolveRemoteUrl(alert))
    }
    var isResolvingRemote by remember(alert.effectiveRemoteUrl, alert.effectiveRemoteReference, snapshotRetryKey) {
        mutableStateOf(false)
    }

    LaunchedEffect(alert.effectiveRemoteUrl, alert.effectiveRemoteReference, connectionMode, snapshotRetryKey) {
        if (connectionMode == ConnectionMode.REMOTE && localRecord == null) {
            remoteDownloadUrl = com.veronic.guardbox.util.RemoteEvidenceHelper.resolveRemoteUrl(alert)
        } else {
            remoteDownloadUrl = null
        }
        isResolvingRemote = false
    }

    val effectiveImageModel: Any? = localRecord?.localUri
        ?: if (connectionMode == ConnectionMode.REMOTE) remoteDownloadUrl else fullSnapshotUrl

    val activeDownloadUrl: String? = (localRecord?.localUri
        ?: if (connectionMode == ConnectionMode.REMOTE) remoteDownloadUrl else fullSnapshotUrl)?.toString()

    val imageRequest = remember(effectiveImageModel, snapshotRetryKey, effectiveId) {
        effectiveImageModel?.let { model ->
            ImageRequest.Builder(context)
                .data(model)
                .memoryCacheKey("alert_${effectiveId}_${snapshotRetryKey}")
                .diskCacheKey("alert_${effectiveId}_${snapshotRetryKey}")
                .crossfade(true)
                .setParameter("retry", snapshotRetryKey, memoryCacheKey = null)
                .listener(
                    onStart = {
                        Log.i("TRINETRA_SNAPSHOT", "[TRINETRA SNAPSHOT DETAIL START] alertId=$effectiveId reference=${alert.effectiveSnapshotReference} remoteRef=${alert.effectiveRemoteReference} resolvedModel=$model mode=$connectionMode")
                    },
                    onSuccess = { _, result ->
                        Log.i("TRINETRA_SNAPSHOT", "[TRINETRA SNAPSHOT DETAIL SUCCESS] alertId=$effectiveId model=$model dataSource=${result.dataSource}")
                    },
                    onError = { _, result ->
                        Log.e("TRINETRA_SNAPSHOT", "[TRINETRA SNAPSHOT DETAIL ERROR] alertId=$effectiveId model=$model error=${result.throwable.message}")
                    }
                )
                .build()
        }
    }

    Dialog(
        onDismissRequest = onDismiss,
        properties = DialogProperties(usePlatformDefaultWidth = false)
    ) {
        Surface(
            modifier = Modifier
                .fillMaxWidth(0.92f)
                .clip(RoundedCornerShape(20.dp)),
            color = DarkSurface,
            border = BorderStroke(1.dp, DarkCardBorder)
        ) {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(20.dp)
            ) {
                // Header
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Text(
                        text = "SECURITY ALERT",
                        color = Color.White,
                        fontSize = 16.sp,
                        fontWeight = FontWeight.Bold,
                        letterSpacing = 1.sp
                    )
                    IconButton(onClick = onDismiss, modifier = Modifier.size(28.dp)) {
                        Icon(
                            imageVector = Icons.Default.Close,
                            contentDescription = "Close",
                            tint = TextMuted
                        )
                    }
                }

                Spacer(modifier = Modifier.height(12.dp))

                // Snapshot preview Box
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(160.dp)
                        .clip(RoundedCornerShape(12.dp))
                        .background(Color.Black.copy(alpha = 0.6f))
                        .border(BorderStroke(0.5.dp, DarkCardBorder), RoundedCornerShape(12.dp)),
                    contentAlignment = Alignment.Center
                ) {
                    if (isExpired && !isSavedLocally) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Icon(
                                imageVector = Icons.Default.HourglassEmpty,
                                contentDescription = "Expired",
                                tint = WarningYellow,
                                modifier = Modifier.size(32.dp)
                            )
                            Spacer(modifier = Modifier.height(6.dp))
                            Text(
                                text = "Snapshot expired",
                                color = WarningYellow,
                                fontSize = 12.sp,
                                fontWeight = FontWeight.SemiBold
                            )
                        }
                    } else if (connectionMode == ConnectionMode.REMOTE && !isSavedLocally && (alert.effectiveRemoteStatus == "UPLOADING" || alert.snapshot?.status == "UPLOADING")) {
                        Column(
                            horizontalAlignment = Alignment.CenterHorizontally,
                            verticalArrangement = Arrangement.Center,
                            modifier = Modifier.fillMaxSize().padding(12.dp)
                        ) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(26.dp),
                                color = CyanAccent,
                                strokeWidth = 2.dp
                            )
                            Spacer(modifier = Modifier.height(8.dp))
                            Text(
                                text = "Evidence uploading...",
                                color = CyanAccent,
                                fontSize = 12.sp,
                                fontWeight = FontWeight.SemiBold
                            )
                        }
                    } else if (connectionMode == ConnectionMode.REMOTE && !isSavedLocally && alert.effectiveRemoteStatus == "FAILED") {
                        Column(
                            horizontalAlignment = Alignment.CenterHorizontally,
                            verticalArrangement = Arrangement.Center,
                            modifier = Modifier.fillMaxSize().padding(12.dp)
                        ) {
                            Icon(
                                imageVector = Icons.Default.Warning,
                                contentDescription = "Failed",
                                tint = WarningYellow,
                                modifier = Modifier.size(28.dp)
                            )
                            Spacer(modifier = Modifier.height(6.dp))
                            Text(
                                text = "Evidence upload failed",
                                color = WarningYellow,
                                fontSize = 12.sp,
                                fontWeight = FontWeight.SemiBold
                            )
                            Spacer(modifier = Modifier.height(6.dp))
                            OutlinedButton(
                                onClick = { snapshotRetryKey++ },
                                shape = RoundedCornerShape(6.dp),
                                contentPadding = PaddingValues(horizontal = 12.dp, vertical = 2.dp),
                                border = BorderStroke(1.dp, CyanAccent),
                                colors = ButtonDefaults.outlinedButtonColors(contentColor = CyanAccent),
                                modifier = Modifier.height(28.dp)
                            ) {
                                Icon(
                                    imageVector = Icons.Default.Refresh,
                                    contentDescription = "Retry",
                                    modifier = Modifier.size(12.dp)
                                )
                                Spacer(modifier = Modifier.width(4.dp))
                                Text(text = "RETRY", fontSize = 10.sp, fontWeight = FontWeight.Bold)
                            }
                        }
                    } else if (isResolvingRemote) {
                        Column(
                            horizontalAlignment = Alignment.CenterHorizontally,
                            verticalArrangement = Arrangement.Center,
                            modifier = Modifier.fillMaxSize()
                        ) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(24.dp),
                                color = CyanAccent,
                                strokeWidth = 2.dp
                            )
                            Spacer(modifier = Modifier.height(6.dp))
                            Text(
                                text = "Fetching remote evidence...",
                                color = TextMuted,
                                fontSize = 11.sp
                            )
                        }
                    } else if (connectionMode == ConnectionMode.REMOTE && alert.effectiveRemoteReference.isNullOrBlank() && !isSavedLocally) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Icon(
                                imageVector = Icons.Default.ImageNotSupported,
                                contentDescription = "Unavailable",
                                tint = TextMuted,
                                modifier = Modifier.size(32.dp)
                            )
                            Spacer(modifier = Modifier.height(6.dp))
                            Text(
                                text = "Remote evidence unavailable",
                                color = TextMuted,
                                fontSize = 12.sp
                            )
                        }
                    } else if (imageRequest == null) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Icon(
                                imageVector = Icons.Default.ImageNotSupported,
                                contentDescription = "Unavailable",
                                tint = TextMuted,
                                modifier = Modifier.size(32.dp)
                            )
                            Spacer(modifier = Modifier.height(6.dp))
                            Text(
                                text = "Evidence unavailable",
                                color = TextMuted,
                                fontSize = 12.sp
                            )
                        }
                    } else {
                        SubcomposeAsyncImage(
                            model = imageRequest,
                            contentDescription = "Alert Snapshot",
                            modifier = Modifier
                                .fillMaxSize()
                                .clip(RoundedCornerShape(12.dp))
                                .clickable { onViewFullSnapshot() },
                            contentScale = ContentScale.Crop,
                            loading = {
                                Box(
                                    modifier = Modifier.fillMaxSize(),
                                    contentAlignment = Alignment.Center
                                ) {
                                    CircularProgressIndicator(
                                        modifier = Modifier.size(24.dp),
                                        color = CyanAccent,
                                        strokeWidth = 2.dp
                                    )
                                }
                            },
                            error = {
                                Column(
                                    horizontalAlignment = Alignment.CenterHorizontally,
                                    verticalArrangement = Arrangement.Center,
                                    modifier = Modifier.fillMaxSize().padding(8.dp)
                                ) {
                                    Icon(
                                        imageVector = Icons.Default.Warning,
                                        contentDescription = "Error",
                                        tint = WarningYellow,
                                        modifier = Modifier.size(28.dp)
                                    )
                                    Spacer(modifier = Modifier.height(4.dp))
                                    Text(
                                        text = "Unable to load evidence",
                                        color = WarningYellow,
                                        fontSize = 12.sp,
                                        fontWeight = FontWeight.SemiBold
                                    )
                                    Spacer(modifier = Modifier.height(6.dp))
                                    OutlinedButton(
                                        onClick = { snapshotRetryKey++ },
                                        shape = RoundedCornerShape(6.dp),
                                        contentPadding = PaddingValues(horizontal = 10.dp, vertical = 2.dp),
                                        border = BorderStroke(1.dp, CyanAccent),
                                        colors = ButtonDefaults.outlinedButtonColors(contentColor = CyanAccent),
                                        modifier = Modifier.height(28.dp)
                                    ) {
                                        Icon(
                                            imageVector = Icons.Default.Refresh,
                                            contentDescription = "Retry",
                                            modifier = Modifier.size(12.dp)
                                        )
                                        Spacer(modifier = Modifier.width(4.dp))
                                        Text(text = "RETRY", fontSize = 11.sp, fontWeight = FontWeight.Bold)
                                    }
                                }
                            },
                            success = {
                                SubcomposeAsyncImageContent()
                            }
                        )
                    }
                }

                Spacer(modifier = Modifier.height(14.dp))

                // Metadata Details
                DetailRow("Alert ID", effectiveId, isMonospace = true)
                DetailRow("Camera", alert.cameraName ?: "Main Shop Camera")
                DetailRow("Reason", alert.effectiveReason)
                DetailRow("Detected", detectedTime)
                DetailRow("Alert Status", alert.status ?: "WAITING_ACK")
                DetailRow(
                    "Snapshot Status",
                    if (isSavedLocally) "Saved on phone" else if (isExpired) "Expired" else "Available"
                )
                DetailRow(
                    "Server Retention",
                    if (isExpired) "Expired after 8 hours" else "Available until $expiryTime"
                )
                DetailRow(
                    "Local Copy",
                    if (isSavedLocally) "Saved on phone" else "Not saved",
                    valueColor = if (isSavedLocally) SuccessGreen else TextMuted
                )

                Spacer(modifier = Modifier.height(16.dp))

                // Actions
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    if (effectiveImageModel != null) {
                        OutlinedButton(
                            onClick = onViewFullSnapshot,
                            modifier = Modifier
                                .weight(1f)
                                .height(40.dp),
                            shape = RoundedCornerShape(10.dp),
                            border = BorderStroke(1.dp, CyanAccent)
                        ) {
                            Icon(
                                imageVector = Icons.Default.Visibility,
                                contentDescription = "View",
                                tint = CyanAccent,
                                modifier = Modifier.size(16.dp)
                            )
                            Spacer(modifier = Modifier.width(6.dp))
                            Text(
                                text = if (isSavedLocally && isExpired) "VIEW SAVED" else "VIEW",
                                color = CyanAccent,
                                fontSize = 12.sp,
                                fontWeight = FontWeight.Bold
                            )
                        }
                    }

                    if (isSavedLocally) {
                        Button(
                            onClick = {},
                            enabled = false,
                            modifier = Modifier
                                .weight(1f)
                                .height(40.dp),
                            shape = RoundedCornerShape(10.dp),
                            colors = ButtonDefaults.buttonColors(
                                disabledContainerColor = SuccessGreen.copy(alpha = 0.2f),
                                disabledContentColor = SuccessGreen
                            )
                        ) {
                            Icon(
                                imageVector = Icons.Default.Check,
                                contentDescription = "Saved",
                                tint = SuccessGreen,
                                modifier = Modifier.size(16.dp)
                            )
                            Spacer(modifier = Modifier.width(6.dp))
                            Text(
                                text = "SAVED",
                                color = SuccessGreen,
                                fontSize = 12.sp,
                                fontWeight = FontWeight.Bold
                            )
                        }
                    } else if (!isExpired && !activeDownloadUrl.isNullOrBlank()) {
                        Button(
                            onClick = {
                                if (!isSaving) {
                                    isSaving = true
                                    Toast.makeText(context, "Saving snapshot...", Toast.LENGTH_SHORT).show()
                                    coroutineScope.launch {
                                        val res = SnapshotStorageHelper.saveSnapshotToDevice(context, effectiveId, activeDownloadUrl)
                                        isSaving = false
                                        if (res.isSuccess) {
                                            isSavedLocally = true
                                            Toast.makeText(context, "Snapshot saved to phone", Toast.LENGTH_SHORT).show()
                                        } else {
                                            Toast.makeText(context, "Could not save snapshot", Toast.LENGTH_SHORT).show()
                                        }
                                    }
                                }
                            },
                            enabled = !isSaving,
                            modifier = Modifier
                                .weight(1f)
                                .height(40.dp),
                            shape = RoundedCornerShape(10.dp),
                            colors = ButtonDefaults.buttonColors(
                                containerColor = CyanAccent,
                                contentColor = Color.Black
                            )
                        ) {
                            if (isSaving) {
                                CircularProgressIndicator(
                                    modifier = Modifier.size(16.dp),
                                    color = Color.Black,
                                    strokeWidth = 2.dp
                                )
                            } else {
                                Icon(
                                    imageVector = Icons.Default.Download,
                                    contentDescription = "Save",
                                    tint = Color.Black,
                                    modifier = Modifier.size(16.dp)
                                )
                                Spacer(modifier = Modifier.width(6.dp))
                                Text(
                                    text = "SAVE TO PHONE",
                                    fontSize = 11.sp,
                                    fontWeight = FontWeight.Bold
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun DetailRow(
    label: String,
    value: String,
    isMonospace: Boolean = false,
    valueColor: Color = TextPrimary
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 3.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(
            text = label,
            color = TextMuted,
            fontSize = 12.sp
        )
        Text(
            text = value,
            color = valueColor,
            fontSize = 12.sp,
            fontWeight = FontWeight.SemiBold,
            fontFamily = if (isMonospace) FontFamily.Monospace else FontFamily.Default
        )
    }
}

private fun parseIsoToMillis(isoString: String?): Long {
    if (isoString.isNullOrBlank()) return 0L
    return try {
        val clean = isoString.replace("Z", "+00:00")
        val sdf = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", Locale.US).apply {
            timeZone = TimeZone.getTimeZone("UTC")
        }
        sdf.parse(clean)?.time ?: 0L
    } catch (_: Exception) {
        0L
    }
}
