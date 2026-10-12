package com.veronic.guardbox.ui

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import android.util.Log
import android.widget.Toast
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Image
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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.VolumeOff
import androidx.compose.material.icons.automirrored.filled.VolumeUp
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Download
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.HourglassEmpty
import androidx.compose.material.icons.filled.ImageNotSupported
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.NotificationsActive
import androidx.compose.material.icons.filled.NotificationsOff
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Security
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Slider
import androidx.compose.material3.SliderDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import coil.compose.SubcomposeAsyncImage
import coil.compose.SubcomposeAsyncImageContent
import coil.request.ImageRequest
import com.veronic.guardbox.R
import com.veronic.guardbox.data.SystemStatus
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

@Composable
fun MainScreen(
    viewModel: MainViewModel,
    modifier: Modifier = Modifier
) {
    val context = LocalContext.current
    val coroutineScope = rememberCoroutineScope()
    val lifecycleOwner = LocalLifecycleOwner.current
    val systemStatus by viewModel.systemStatus.collectAsState()
    val activeAlert by viewModel.activeAlert.collectAsState()
    val notificationsEnabled by viewModel.notificationsEnabled.collectAsState()
    val isLoading by viewModel.isLoading.collectAsState()
    val actionError by viewModel.actionError.collectAsState()
    val alarmVolumeRatio by viewModel.alarmVolumeRatio.collectAsState()
    val isSilencing by viewModel.isSilencing.collectAsState()

    val connectionMode by viewModel.connectionMode.collectAsState()
    val activeBaseUrl by viewModel.activeBaseUrl.collectAsState()
    val isServerConnected by viewModel.isServerConnected.collectAsState()
    val currentRemoteUrl by viewModel.remoteUrl.collectAsState()
    val currentApiKey by viewModel.apiKey.collectAsState()
    val targetDeviceId by viewModel.targetDeviceId.collectAsState()
    val remoteLastSeen by viewModel.remoteLastSeen.collectAsState()
    val commandFeedback by viewModel.commandFeedback.collectAsState()
    val showSetupGuide by viewModel.showSetupGuide.collectAsState()
    val registrationStatus by viewModel.registrationStatus.collectAsState()

    var showConfigDialog by remember { mutableStateOf(false) }
    var showFullScreenSnapshot by remember { mutableStateOf(false) }
    var showEvidenceScreen by remember { mutableStateOf(false) }
    var showDeviceInfoScreen by remember { mutableStateOf(false) }

    // Sync volume when screen opens or resumes
    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) {
                viewModel.refreshAlarmVolume(context)
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose {
            lifecycleOwner.lifecycle.removeObserver(observer)
        }
    }

    val isRunning = systemStatus == SystemStatus.RUNNING
    val isSyncing = systemStatus == SystemStatus.SYNCING

    // Pulse animation for active status
    val infiniteTransition = rememberInfiniteTransition(label = "pulse")
    val pulseAlpha by infiniteTransition.animateFloat(
        initialValue = 0.4f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(
            animation = tween(1000, easing = FastOutSlowInEasing),
            repeatMode = RepeatMode.Reverse
        ),
        label = "pulseAlpha"
    )

    val targetStatusColor = when (systemStatus) {
        SystemStatus.RUNNING -> SuccessGreen
        SystemStatus.STOPPED -> EmergencyRed
        SystemStatus.SYNCING -> CyanAccent
        SystemStatus.ARMING -> WarningYellow
        SystemStatus.TEST_MODE -> CyanAccent
        SystemStatus.MISMATCH, SystemStatus.NOT_FOUND, SystemStatus.NOT_AUTHORIZED -> EmergencyRed
        SystemStatus.NOT_CONFIGURED -> WarningYellow
        SystemStatus.OFFLINE, SystemStatus.ERROR, SystemStatus.UNKNOWN -> TextMuted
    }

    val statusColor by animateColorAsState(
        targetValue = targetStatusColor,
        animationSpec = tween(400),
        label = "statusColor"
    )

    if (showEvidenceScreen) {
        SecurityEvidenceScreen(
            viewModel = viewModel,
            onBack = { showEvidenceScreen = false }
        )
    } else if (showDeviceInfoScreen) {
        DeviceInformationScreen(
            viewModel = viewModel,
            onBack = { showDeviceInfoScreen = false }
        )
    } else {
        Surface(
            modifier = modifier.fillMaxSize(),
            color = DarkBg
        ) {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .verticalScroll(rememberScrollState())
                    .padding(horizontal = 16.dp, vertical = 12.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                // ==============================================================================
                // 1. TRINETRA COMPACT HEADER & SERVER SELECTOR (Phase 5.1 Compaction)
                // ==============================================================================
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(14.dp),
                    colors = CardDefaults.cardColors(containerColor = DarkCard),
                    border = BorderStroke(1.dp, DarkCardBorder)
                ) {
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(horizontal = 12.dp, vertical = 10.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        // Brand Row + Action Icons
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Box(
                                    contentAlignment = Alignment.Center,
                                    modifier = Modifier
                                        .size(32.dp)
                                        .clip(CircleShape)
                                        .background(DarkSurface)
                                        .border(BorderStroke(1.dp, statusColor.copy(alpha = 0.6f)), CircleShape)
                                ) {
                                    Image(
                                        painter = painterResource(id = R.drawable.trinetra_emblem),
                                        contentDescription = "TRINETRA Logo",
                                        modifier = Modifier.size(20.dp)
                                    )
                                }
                                Spacer(modifier = Modifier.width(8.dp))
                                Column {
                                    Row(verticalAlignment = Alignment.CenterVertically) {
                                        Text(
                                            text = "TRINETRA",
                                            color = Color.White,
                                            fontSize = 16.sp,
                                            fontWeight = FontWeight.Black,
                                            letterSpacing = 1.5.sp
                                        )
                                        Spacer(modifier = Modifier.width(6.dp))
                                        Box(
                                            modifier = Modifier
                                                .size(7.dp)
                                                .clip(CircleShape)
                                                .background(if (isServerConnected) SuccessGreen else EmergencyRed)
                                        )
                                    }
                                    Text(
                                        text = if (connectionMode == ConnectionMode.LOCAL) "LOCAL LAN" else "FIREBASE RELAY",
                                        color = if (connectionMode == ConnectionMode.LOCAL) CyanAccent else WarningYellow,
                                        fontSize = 10.sp,
                                        fontWeight = FontWeight.SemiBold
                                    )
                                }
                            }

                            // Quick Action Icons: Evidence Center, Device Info, Settings
                            Row(
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.spacedBy(4.dp)
                            ) {
                                IconButton(
                                    onClick = { showEvidenceScreen = true },
                                    modifier = Modifier.size(32.dp)
                                ) {
                                    Icon(
                                        imageVector = Icons.Default.History,
                                        contentDescription = "Evidence Center",
                                        tint = CyanAccent,
                                        modifier = Modifier.size(18.dp)
                                    )
                                }
                                IconButton(
                                    onClick = { showDeviceInfoScreen = true },
                                    modifier = Modifier.size(32.dp)
                                ) {
                                    Icon(
                                        imageVector = Icons.Default.Info,
                                        contentDescription = "Device Info",
                                        tint = CyanAccent,
                                        modifier = Modifier.size(18.dp)
                                    )
                                }
                                IconButton(
                                    onClick = { showConfigDialog = true },
                                    modifier = Modifier.size(32.dp)
                                ) {
                                    Icon(
                                        imageVector = Icons.Default.Settings,
                                        contentDescription = "Settings",
                                        tint = TextMuted,
                                        modifier = Modifier.size(18.dp)
                                    )
                                }
                            }
                        }

                        // Compact Segmented Control for Mode Switching
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .clip(RoundedCornerShape(8.dp))
                                .background(DarkSurface)
                                .padding(2.dp),
                            horizontalArrangement = Arrangement.spacedBy(2.dp)
                        ) {
                            // LOCAL Button
                            Box(
                                contentAlignment = Alignment.Center,
                                modifier = Modifier
                                    .weight(1f)
                                    .height(30.dp)
                                    .clip(RoundedCornerShape(6.dp))
                                    .background(
                                        if (connectionMode == ConnectionMode.LOCAL) CyanAccent else Color.Transparent
                                    )
                                    .clickable { viewModel.setConnectionMode(ConnectionMode.LOCAL) }
                            ) {
                                Row(
                                    verticalAlignment = Alignment.CenterVertically,
                                    horizontalArrangement = Arrangement.Center
                                ) {
                                    Text(
                                        text = "● LOCAL",
                                        color = if (connectionMode == ConnectionMode.LOCAL) Color.Black else TextSecondary,
                                        fontSize = 11.sp,
                                        fontWeight = FontWeight.Bold,
                                        letterSpacing = 0.5.sp
                                    )
                                }
                            }

                            // REMOTE Button
                            Box(
                                contentAlignment = Alignment.Center,
                                modifier = Modifier
                                    .weight(1f)
                                    .height(30.dp)
                                    .clip(RoundedCornerShape(6.dp))
                                    .background(
                                        if (connectionMode == ConnectionMode.REMOTE) WarningYellow else Color.Transparent
                                    )
                                    .clickable { viewModel.setConnectionMode(ConnectionMode.REMOTE) }
                            ) {
                                Row(
                                    verticalAlignment = Alignment.CenterVertically,
                                    horizontalArrangement = Arrangement.Center
                                ) {
                                    Text(
                                        text = "☁ REMOTE",
                                        color = if (connectionMode == ConnectionMode.REMOTE) Color.Black else TextSecondary,
                                        fontSize = 11.sp,
                                        fontWeight = FontWeight.Bold,
                                        letterSpacing = 0.5.sp
                                    )
                                }
                            }
                        }
                    }
                }

                // ==============================================================================
                // 2. ACTIVE SECURITY ALERT CARD (with Robust Snapshot URL Resolution & Retry)
                // ==============================================================================
                AnimatedVisibility(
                    visible = activeAlert != null,
                    enter = fadeIn(),
                    exit = fadeOut()
                ) {
                    activeAlert?.let { alert ->
                        val effectiveId = alert.effectiveAlertId ?: "UNKNOWN"
                        val fullSnapshotUrl = alert.getFullSnapshotUrl(activeBaseUrl)
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
                                            Log.i("TRINETRA_SNAPSHOT", "[TRINETRA SNAPSHOT START] alertId=$effectiveId reference=${alert.effectiveSnapshotReference} remoteRef=${alert.effectiveRemoteReference} resolvedModel=$model mode=$connectionMode")
                                        },
                                        onSuccess = { _, result ->
                                            Log.i("TRINETRA_SNAPSHOT", "[TRINETRA SNAPSHOT SUCCESS] alertId=$effectiveId model=$model dataSource=${result.dataSource}")
                                        },
                                        onError = { _, result ->
                                            Log.e("TRINETRA_SNAPSHOT", "[TRINETRA SNAPSHOT ERROR] alertId=$effectiveId model=$model error=${result.throwable.message}")
                                        }
                                    )
                                    .build()
                            }
                        }

                        Card(
                            modifier = Modifier.fillMaxWidth(),
                            shape = RoundedCornerShape(14.dp),
                            colors = CardDefaults.cardColors(containerColor = EmergencyRedBg),
                            border = BorderStroke(1.5.dp, EmergencyRed.copy(alpha = 0.8f))
                        ) {
                            Column(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(14.dp)
                            ) {
                                Row(
                                    verticalAlignment = Alignment.CenterVertically,
                                    horizontalArrangement = Arrangement.SpaceBetween,
                                    modifier = Modifier.fillMaxWidth()
                                ) {
                                    Row(verticalAlignment = Alignment.CenterVertically) {
                                        Box(
                                            modifier = Modifier
                                                .size(9.dp)
                                                .clip(CircleShape)
                                                .background(EmergencyRed)
                                        )
                                        Spacer(modifier = Modifier.width(6.dp))
                                        Text(
                                            text = "SECURITY ALERT",
                                            color = EmergencyRed,
                                            fontSize = 12.sp,
                                            fontWeight = FontWeight.Bold,
                                            letterSpacing = 1.sp
                                        )
                                    }
                                    Text(
                                        text = alert.status ?: "ACTIVE",
                                        color = EmergencyRed,
                                        fontSize = 11.sp,
                                        fontWeight = FontWeight.Bold
                                    )
                                }

                                Spacer(modifier = Modifier.height(10.dp))

                                // Snapshot Image Box (Responsive, height 180dp)
                                Box(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .height(180.dp)
                                        .clip(RoundedCornerShape(10.dp))
                                        .background(Color.Black.copy(alpha = 0.7f))
                                        .border(BorderStroke(1.dp, EmergencyRed.copy(alpha = 0.4f)), RoundedCornerShape(10.dp)),
                                    contentAlignment = Alignment.Center
                                ) {
                                    if (isExpired && !isSavedLocally) {
                                        Column(
                                            horizontalAlignment = Alignment.CenterHorizontally,
                                            verticalArrangement = Arrangement.Center,
                                            modifier = Modifier.padding(12.dp)
                                        ) {
                                            Icon(
                                                imageVector = Icons.Default.HourglassEmpty,
                                                contentDescription = "Expired",
                                                tint = WarningYellow,
                                                modifier = Modifier.size(28.dp)
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
                                                modifier = Modifier.size(24.dp),
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
                                                modifier = Modifier.size(22.dp),
                                                color = CyanAccent,
                                                strokeWidth = 2.dp
                                            )
                                            Spacer(modifier = Modifier.height(6.dp))
                                            Text(
                                                text = "Loading evidence...",
                                                color = TextMuted,
                                                fontSize = 11.sp
                                            )
                                        }
                                    } else if (connectionMode == ConnectionMode.REMOTE && alert.effectiveRemoteReference.isNullOrBlank() && !isSavedLocally) {
                                        Column(
                                            horizontalAlignment = Alignment.CenterHorizontally,
                                            verticalArrangement = Arrangement.Center,
                                            modifier = Modifier.padding(12.dp)
                                        ) {
                                            Icon(
                                                imageVector = Icons.Default.ImageNotSupported,
                                                contentDescription = "Unavailable",
                                                tint = TextMuted,
                                                modifier = Modifier.size(28.dp)
                                            )
                                            Spacer(modifier = Modifier.height(6.dp))
                                            Text(
                                                text = "Remote evidence unavailable",
                                                color = TextMuted,
                                                fontSize = 12.sp,
                                                fontWeight = FontWeight.Medium
                                            )
                                        }
                                    } else if (imageRequest == null) {
                                        Column(
                                            horizontalAlignment = Alignment.CenterHorizontally,
                                            verticalArrangement = Arrangement.Center,
                                            modifier = Modifier.padding(12.dp)
                                        ) {
                                            Icon(
                                                imageVector = Icons.Default.ImageNotSupported,
                                                contentDescription = "Unavailable",
                                                tint = TextMuted,
                                                modifier = Modifier.size(28.dp)
                                            )
                                            Spacer(modifier = Modifier.height(6.dp))
                                            Text(
                                                text = "Evidence unavailable",
                                                color = TextMuted,
                                                fontSize = 12.sp,
                                                fontWeight = FontWeight.Medium
                                            )
                                        }
                                    } else {
                                        SubcomposeAsyncImage(
                                            model = imageRequest,
                                            contentDescription = "Security Alert Snapshot",
                                            modifier = Modifier
                                                .fillMaxSize()
                                                .clip(RoundedCornerShape(10.dp))
                                                .clickable { showFullScreenSnapshot = true },
                                            contentScale = ContentScale.Crop,
                                            loading = {
                                                Column(
                                                    horizontalAlignment = Alignment.CenterHorizontally,
                                                    verticalArrangement = Arrangement.Center,
                                                    modifier = Modifier.fillMaxSize()
                                                ) {
                                                    CircularProgressIndicator(
                                                        modifier = Modifier.size(22.dp),
                                                        color = CyanAccent,
                                                        strokeWidth = 2.dp
                                                    )
                                                    Spacer(modifier = Modifier.height(6.dp))
                                                    Text(
                                                        text = "Loading evidence...",
                                                        color = TextMuted,
                                                        fontSize = 11.sp
                                                    )
                                                }
                                            },
                                            error = {
                                                Column(
                                                    horizontalAlignment = Alignment.CenterHorizontally,
                                                    verticalArrangement = Arrangement.Center,
                                                    modifier = Modifier
                                                        .fillMaxSize()
                                                        .padding(10.dp)
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
                                                        fontWeight = FontWeight.SemiBold,
                                                        textAlign = TextAlign.Center
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

                                Spacer(modifier = Modifier.height(8.dp))

                                // Save to Phone Action / Status
                                if (isSavedLocally) {
                                    Row(
                                        modifier = Modifier
                                            .fillMaxWidth()
                                            .clip(RoundedCornerShape(6.dp))
                                            .background(SuccessGreen.copy(alpha = 0.15f))
                                            .padding(vertical = 6.dp, horizontal = 10.dp),
                                        verticalAlignment = Alignment.CenterVertically,
                                        horizontalArrangement = Arrangement.Center
                                    ) {
                                        Icon(
                                            imageVector = Icons.Default.Check,
                                            contentDescription = "Saved",
                                            tint = SuccessGreen,
                                            modifier = Modifier.size(14.dp)
                                        )
                                        Spacer(modifier = Modifier.width(6.dp))
                                        Text(
                                            text = "SAVED TO PHONE",
                                            color = SuccessGreen,
                                            fontSize = 11.sp,
                                            fontWeight = FontWeight.Bold,
                                            letterSpacing = 0.5.sp
                                        )
                                    }
                                } else if (!isExpired && !activeDownloadUrl.isNullOrBlank()) {
                                    Button(
                                        onClick = {
                                            if (!isSaving) {
                                                isSaving = true
                                                Toast.makeText(context, "Saving snapshot...", Toast.LENGTH_SHORT).show()
                                                coroutineScope.launch {
                                                    val result = SnapshotStorageHelper.saveSnapshotToDevice(context, effectiveId, activeDownloadUrl)
                                                    isSaving = false
                                                    if (result.isSuccess) {
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
                                            .fillMaxWidth()
                                            .height(34.dp),
                                        shape = RoundedCornerShape(6.dp),
                                        colors = ButtonDefaults.buttonColors(
                                            containerColor = CyanAccent.copy(alpha = 0.85f),
                                            contentColor = Color.Black
                                        )
                                    ) {
                                        if (isSaving) {
                                            CircularProgressIndicator(
                                                modifier = Modifier.size(14.dp),
                                                color = Color.Black,
                                                strokeWidth = 2.dp
                                            )
                                            Spacer(modifier = Modifier.width(6.dp))
                                            Text(
                                                text = "Saving...",
                                                fontSize = 11.sp,
                                                fontWeight = FontWeight.Bold
                                            )
                                        } else {
                                            Icon(
                                                imageVector = Icons.Default.Download,
                                                contentDescription = "Save",
                                                tint = Color.Black,
                                                modifier = Modifier.size(14.dp)
                                            )
                                            Spacer(modifier = Modifier.width(6.dp))
                                            Text(
                                                text = "SAVE TO PHONE",
                                                fontSize = 11.sp,
                                                fontWeight = FontWeight.Bold,
                                                letterSpacing = 0.5.sp
                                            )
                                        }
                                    }
                                }

                                Spacer(modifier = Modifier.height(10.dp))

                                // Alert Metadata
                                Text(
                                    text = "Alert ID: $effectiveId",
                                    color = TextPrimary,
                                    fontSize = 12.sp,
                                    fontWeight = FontWeight.Bold,
                                    fontFamily = FontFamily.Monospace
                                )

                                Spacer(modifier = Modifier.height(2.dp))

                                Text(
                                    text = "Camera: ${alert.cameraName ?: "Main Shop Camera"}",
                                    color = TextSecondary,
                                    fontSize = 12.sp
                                )

                                Spacer(modifier = Modifier.height(2.dp))

                                Text(
                                    text = "Reason: ${alert.effectiveReason}",
                                    color = TextSecondary,
                                    fontSize = 12.sp
                                )

                                Spacer(modifier = Modifier.height(2.dp))

                                Row(
                                    modifier = Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.SpaceBetween
                                ) {
                                    Text(
                                        text = "Detected: $detectedTime",
                                        color = TextMuted,
                                        fontSize = 11.sp
                                    )
                                    Text(
                                        text = "Evidence until: $expiryTime",
                                        color = TextMuted,
                                        fontSize = 11.sp
                                    )
                                }
                            }
                        }
                    }
                }

                // ==============================================================================
                // 3. SYSTEM STATUS CARD (Compact & Responsive)
                // ==============================================================================
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(14.dp),
                    colors = CardDefaults.cardColors(containerColor = DarkSurface),
                    border = BorderStroke(
                        1.dp,
                        when (systemStatus) {
                            SystemStatus.RUNNING -> SuccessGreen.copy(alpha = 0.5f)
                            SystemStatus.STOPPED -> EmergencyRed.copy(alpha = 0.5f)
                            SystemStatus.SYNCING -> CyanAccent.copy(alpha = 0.5f)
                            SystemStatus.ARMING -> WarningYellow.copy(alpha = 0.5f)
                            SystemStatus.TEST_MODE -> CyanAccent.copy(alpha = 0.5f)
                            SystemStatus.MISMATCH, SystemStatus.NOT_FOUND, SystemStatus.NOT_AUTHORIZED -> EmergencyRed.copy(alpha = 0.6f)
                            SystemStatus.NOT_CONFIGURED -> WarningYellow.copy(alpha = 0.6f)
                            SystemStatus.OFFLINE, SystemStatus.ERROR, SystemStatus.UNKNOWN -> TextMuted.copy(alpha = 0.3f)
                        }
                    )
                ) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(horizontal = 14.dp, vertical = 12.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.weight(1f)) {
                            Box(
                                modifier = Modifier
                                    .size(10.dp)
                                    .clip(CircleShape)
                                    .background(statusColor)
                                    .alpha(if (isRunning || isSyncing) pulseAlpha else 1f)
                            )
                            Spacer(modifier = Modifier.width(8.dp))
                            Column {
                                Text(
                                    text = when (systemStatus) {
                                        SystemStatus.RUNNING -> "SYSTEM RUNNING"
                                        SystemStatus.STOPPED -> "SYSTEM STOPPED"
                                        SystemStatus.SYNCING -> "SYNCHRONIZING..."
                                        SystemStatus.ARMING -> "ARMING PERIMETER"
                                        SystemStatus.TEST_MODE -> "TEST MODE ACTIVE"
                                        SystemStatus.MISMATCH -> "DEVICE ID MISMATCH"
                                        SystemStatus.NOT_FOUND -> "DEVICE NOT FOUND"
                                        SystemStatus.NOT_AUTHORIZED -> "NOT AUTHORIZED"
                                        SystemStatus.NOT_CONFIGURED -> "DEVICE NOT CONFIGURED"
                                        SystemStatus.OFFLINE -> "PERIMETER OFFLINE"
                                        SystemStatus.ERROR -> "CONNECTION ERROR"
                                        SystemStatus.UNKNOWN -> "STATUS UNKNOWN"
                                    },
                                    color = statusColor,
                                    fontSize = 14.sp,
                                    fontWeight = FontWeight.Bold,
                                    letterSpacing = 1.sp
                                )
                                Text(
                                    text = when (systemStatus) {
                                        SystemStatus.RUNNING -> "Perimeter monitoring active"
                                        SystemStatus.STOPPED -> "Perimeter monitoring offline"
                                        SystemStatus.SYNCING -> "Synchronizing security status..."
                                        SystemStatus.ARMING -> "Arming countdown in progress..."
                                        SystemStatus.TEST_MODE -> "Diagnostic test mode enabled"
                                        SystemStatus.MISMATCH -> "Configured Device ID does not match appliance"
                                        SystemStatus.NOT_FOUND -> "Configured Device ID not found on cloud"
                                        SystemStatus.NOT_AUTHORIZED -> "Access not authorized for this device"
                                        SystemStatus.NOT_CONFIGURED -> "No TRINETRA Device ID configured"
                                        SystemStatus.OFFLINE -> "Device disconnected"
                                        SystemStatus.ERROR -> "Cloud sync interrupted"
                                        SystemStatus.UNKNOWN -> "Waiting for status update..."
                                    },
                                    color = TextMuted,
                                    fontSize = 11.sp
                                )
                            }
                        }

                        // Status mode badge
                        Box(
                            modifier = Modifier
                                .clip(RoundedCornerShape(20.dp))
                                .background(statusColor.copy(alpha = 0.15f))
                                .padding(horizontal = 10.dp, vertical = 4.dp)
                        ) {
                            Text(
                                text = when (systemStatus) {
                                    SystemStatus.RUNNING -> "ARMED"
                                    SystemStatus.STOPPED -> "DISARMED"
                                    SystemStatus.SYNCING -> "SYNC"
                                    SystemStatus.ARMING -> "ARMING"
                                    SystemStatus.TEST_MODE -> "TEST"
                                    SystemStatus.MISMATCH -> "MISMATCH"
                                    SystemStatus.NOT_FOUND -> "NOT FOUND"
                                    SystemStatus.NOT_AUTHORIZED -> "UNAUTHORIZED"
                                    SystemStatus.NOT_CONFIGURED -> "UNCONFIGURED"
                                    SystemStatus.OFFLINE -> "OFFLINE"
                                    SystemStatus.ERROR -> "ERROR"
                                    SystemStatus.UNKNOWN -> "UNKNOWN"
                                },
                                color = statusColor,
                                fontSize = 11.sp,
                                fontWeight = FontWeight.Bold
                            )
                        }
                    }
                }

                // ==============================================================================
                // 4. START / STOP SYSTEM (Primary Action Button)
                // ==============================================================================
                if (isSyncing) {
                    Button(
                        onClick = { },
                        enabled = false,
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(52.dp),
                        shape = RoundedCornerShape(14.dp),
                        colors = ButtonDefaults.buttonColors(
                            disabledContainerColor = DarkCard,
                            disabledContentColor = TextMuted
                        )
                    ) {
                        Icon(
                            imageVector = Icons.Default.Security,
                            contentDescription = "Synchronizing",
                            tint = CyanAccent,
                            modifier = Modifier.size(22.dp)
                        )
                        Spacer(modifier = Modifier.width(8.dp))
                        Text(
                            text = "SYNCHRONIZING...",
                            color = CyanAccent,
                            fontSize = 15.sp,
                            fontWeight = FontWeight.Bold,
                            letterSpacing = 1.sp
                        )
                    }
                } else if (systemStatus == SystemStatus.MISMATCH) {
                    Button(
                        onClick = { showConfigDialog = true },
                        enabled = true,
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(52.dp),
                        shape = RoundedCornerShape(14.dp),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = EmergencyRed.copy(alpha = 0.2f),
                            contentColor = EmergencyRed
                        ),
                        border = BorderStroke(1.dp, EmergencyRed)
                    ) {
                        Icon(
                            imageVector = Icons.Default.Warning,
                            contentDescription = "Device ID Mismatch",
                            tint = EmergencyRed,
                            modifier = Modifier.size(22.dp)
                        )
                        Spacer(modifier = Modifier.width(8.dp))
                        Text(
                            text = "DEVICE ID MISMATCH",
                            color = EmergencyRed,
                            fontSize = 14.sp,
                            fontWeight = FontWeight.Bold,
                            letterSpacing = 1.sp
                        )
                    }
                } else if (systemStatus == SystemStatus.NOT_FOUND) {
                    Button(
                        onClick = { showConfigDialog = true },
                        enabled = true,
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(52.dp),
                        shape = RoundedCornerShape(14.dp),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = EmergencyRed.copy(alpha = 0.2f),
                            contentColor = EmergencyRed
                        ),
                        border = BorderStroke(1.dp, EmergencyRed)
                    ) {
                        Icon(
                            imageVector = Icons.Default.Warning,
                            contentDescription = "Device Not Found",
                            tint = EmergencyRed,
                            modifier = Modifier.size(22.dp)
                        )
                        Spacer(modifier = Modifier.width(8.dp))
                        Text(
                            text = "DEVICE NOT FOUND",
                            color = EmergencyRed,
                            fontSize = 14.sp,
                            fontWeight = FontWeight.Bold,
                            letterSpacing = 1.sp
                        )
                    }
                } else if (systemStatus == SystemStatus.NOT_AUTHORIZED) {
                    Button(
                        onClick = { showConfigDialog = true },
                        enabled = true,
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(52.dp),
                        shape = RoundedCornerShape(14.dp),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = EmergencyRed.copy(alpha = 0.2f),
                            contentColor = EmergencyRed
                        ),
                        border = BorderStroke(1.dp, EmergencyRed)
                    ) {
                        Icon(
                            imageVector = Icons.Default.Warning,
                            contentDescription = "Not Authorized",
                            tint = EmergencyRed,
                            modifier = Modifier.size(22.dp)
                        )
                        Spacer(modifier = Modifier.width(8.dp))
                        Text(
                            text = "NOT AUTHORIZED",
                            color = EmergencyRed,
                            fontSize = 14.sp,
                            fontWeight = FontWeight.Bold,
                            letterSpacing = 1.sp
                        )
                    }
                } else if (systemStatus == SystemStatus.NOT_CONFIGURED) {
                    Button(
                        onClick = { showConfigDialog = true },
                        enabled = true,
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(52.dp),
                        shape = RoundedCornerShape(14.dp),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = WarningYellow.copy(alpha = 0.2f),
                            contentColor = WarningYellow
                        ),
                        border = BorderStroke(1.dp, WarningYellow)
                    ) {
                        Icon(
                            imageVector = Icons.Default.Warning,
                            contentDescription = "Device Not Configured",
                            tint = WarningYellow,
                            modifier = Modifier.size(22.dp)
                        )
                        Spacer(modifier = Modifier.width(8.dp))
                        Text(
                            text = "DEVICE NOT CONFIGURED",
                            color = WarningYellow,
                            fontSize = 14.sp,
                            fontWeight = FontWeight.Bold,
                            letterSpacing = 1.sp
                        )
                    }
                } else if (systemStatus == SystemStatus.OFFLINE) {
                    Button(
                        onClick = { },
                        enabled = false,
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(52.dp),
                        shape = RoundedCornerShape(14.dp),
                        colors = ButtonDefaults.buttonColors(
                            disabledContainerColor = DarkCard,
                            disabledContentColor = TextMuted
                        )
                    ) {
                        Icon(
                            imageVector = Icons.Default.Warning,
                            contentDescription = "Device Offline",
                            tint = TextMuted,
                            modifier = Modifier.size(22.dp)
                        )
                        Spacer(modifier = Modifier.width(8.dp))
                        Text(
                            text = "DEVICE OFFLINE",
                            color = TextMuted,
                            fontSize = 14.sp,
                            fontWeight = FontWeight.Bold,
                            letterSpacing = 1.sp
                        )
                    }
                } else if (isRunning) {
                    Button(
                        onClick = { viewModel.stopSystem() },
                        enabled = !isLoading,
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(52.dp),
                        shape = RoundedCornerShape(14.dp),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = EmergencyRed,
                            contentColor = Color.White
                        ),
                        elevation = ButtonDefaults.buttonElevation(defaultElevation = 4.dp)
                    ) {
                        Icon(
                            imageVector = Icons.Default.Stop,
                            contentDescription = "Stop System",
                            modifier = Modifier.size(22.dp)
                        )
                        Spacer(modifier = Modifier.width(8.dp))
                        Text(
                            text = if (isLoading) "STOPPING..." else "STOP SYSTEM",
                            fontSize = 15.sp,
                            fontWeight = FontWeight.Bold,
                            letterSpacing = 1.sp
                        )
                    }
                } else {
                    Button(
                        onClick = { viewModel.startSystem() },
                        enabled = !isLoading,
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(52.dp),
                        shape = RoundedCornerShape(14.dp),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = SuccessGreen,
                            contentColor = Color.Black
                        ),
                        elevation = ButtonDefaults.buttonElevation(defaultElevation = 4.dp)
                    ) {
                        Icon(
                            imageVector = Icons.Default.PlayArrow,
                            contentDescription = "Start System",
                            modifier = Modifier.size(22.dp)
                        )
                        Spacer(modifier = Modifier.width(8.dp))
                        Text(
                            text = if (isLoading) "STARTING..." else "START SYSTEM",
                            fontSize = 15.sp,
                            fontWeight = FontWeight.Bold,
                            letterSpacing = 1.sp
                        )
                    }
                }

                // Command Feedback Badge
                AnimatedVisibility(
                    visible = commandFeedback != null,
                    enter = fadeIn(),
                    exit = fadeOut()
                ) {
                    Text(
                        text = commandFeedback ?: "",
                        color = if (commandFeedback?.contains("Fail", ignoreCase = true) == true) EmergencyRed else CyanAccent,
                        fontSize = 11.sp,
                        fontWeight = FontWeight.SemiBold,
                        textAlign = TextAlign.Center
                    )
                }

                // ==============================================================================
                // 5. SILENCE ALARM BUTTON
                // ==============================================================================
                Button(
                    onClick = { viewModel.silenceAlarm(context) },
                    enabled = !isSilencing,
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(48.dp),
                    shape = RoundedCornerShape(14.dp),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = EmergencyRed.copy(alpha = 0.85f),
                        contentColor = Color.White
                    ),
                    border = BorderStroke(1.dp, EmergencyRed)
                ) {
                    Icon(
                        imageVector = Icons.AutoMirrored.Filled.VolumeOff,
                        contentDescription = "Silence Alarm",
                        modifier = Modifier.size(20.dp)
                    )
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(
                        text = if (isSilencing) "SILENCING ALARM..." else "SILENCE ALARM",
                        fontSize = 14.sp,
                        fontWeight = FontWeight.Bold,
                        letterSpacing = 1.sp
                    )
                }

                // ==============================================================================
                // 6. ALERT VOLUME SLIDER CARD
                // ==============================================================================
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(14.dp),
                    colors = CardDefaults.cardColors(containerColor = DarkCard),
                    border = BorderStroke(1.dp, DarkCardBorder)
                ) {
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(horizontal = 14.dp, vertical = 10.dp)
                    ) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Icon(
                                    imageVector = Icons.AutoMirrored.Filled.VolumeUp,
                                    contentDescription = "Alert Volume",
                                    tint = CyanAccent,
                                    modifier = Modifier.size(16.dp)
                                )
                                Spacer(modifier = Modifier.width(6.dp))
                                Text(
                                    text = "ALERT VOLUME",
                                    color = TextPrimary,
                                    fontSize = 12.sp,
                                    fontWeight = FontWeight.Bold,
                                    letterSpacing = 0.5.sp
                                )
                            }
                            Text(
                                text = "${(alarmVolumeRatio * 100).toInt()}%",
                                color = CyanAccent,
                                fontSize = 13.sp,
                                fontWeight = FontWeight.Bold
                            )
                        }

                        Slider(
                            value = alarmVolumeRatio,
                            onValueChange = { newRatio ->
                                viewModel.setAlarmVolume(context, newRatio)
                            },
                            valueRange = 0f..1f,
                            colors = SliderDefaults.colors(
                                thumbColor = CyanAccent,
                                activeTrackColor = CyanAccent,
                                inactiveTrackColor = DarkCardBorder
                            ),
                            modifier = Modifier.fillMaxWidth()
                        )
                    }
                }

                // ==============================================================================
                // 7. TEST SECURITY ALERT BUTTON
                // ==============================================================================
                OutlinedButton(
                    onClick = { viewModel.triggerTestAlert(context) },
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(48.dp),
                    shape = RoundedCornerShape(14.dp),
                    border = BorderStroke(1.2.dp, WarningYellow),
                    colors = ButtonDefaults.outlinedButtonColors(
                        contentColor = WarningYellow
                    )
                ) {
                    Icon(
                        imageVector = Icons.Default.NotificationsActive,
                        contentDescription = "Test Alert",
                        tint = WarningYellow,
                        modifier = Modifier.size(18.dp)
                    )
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(
                        text = "TEST SECURITY ALERT",
                        fontSize = 13.sp,
                        fontWeight = FontWeight.SemiBold,
                        letterSpacing = 0.5.sp
                    )
                }

                // Action Error Banner (if communication error occurs)
                AnimatedVisibility(
                    visible = actionError != null,
                    enter = fadeIn(),
                    exit = fadeOut()
                ) {
                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(12.dp),
                        colors = CardDefaults.cardColors(containerColor = EmergencyRedBg),
                        border = BorderStroke(1.dp, EmergencyRed.copy(alpha = 0.6f))
                    ) {
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(12.dp),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            Row(
                                verticalAlignment = Alignment.CenterVertically,
                                modifier = Modifier.weight(1f)
                            ) {
                                Icon(
                                    imageVector = Icons.Default.Warning,
                                    contentDescription = "Error",
                                    tint = EmergencyRed,
                                    modifier = Modifier.size(18.dp)
                                )
                                Spacer(modifier = Modifier.width(8.dp))
                                Text(
                                    text = actionError ?: "Unable to communicate with TRINETRA.",
                                    color = Color.White,
                                    fontSize = 12.sp,
                                    fontWeight = FontWeight.SemiBold
                                )
                            }
                            Spacer(modifier = Modifier.width(6.dp))
                            Button(
                                onClick = { viewModel.retryLastAction() },
                                shape = RoundedCornerShape(6.dp),
                                contentPadding = PaddingValues(horizontal = 10.dp, vertical = 4.dp),
                                colors = ButtonDefaults.buttonColors(
                                    containerColor = EmergencyRed,
                                    contentColor = Color.White
                                )
                            ) {
                                Text(text = "Retry", fontSize = 11.sp, fontWeight = FontWeight.Bold)
                            }
                        }
                    }
                }

                // Notification Permission Warning Banner (if disabled)
                AnimatedVisibility(
                    visible = !notificationsEnabled,
                    enter = fadeIn(),
                    exit = fadeOut()
                ) {
                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(12.dp),
                        colors = CardDefaults.cardColors(containerColor = EmergencyRedBg),
                        border = BorderStroke(1.dp, EmergencyRed.copy(alpha = 0.6f))
                    ) {
                        Column(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(12.dp),
                            horizontalAlignment = Alignment.CenterHorizontally
                        ) {
                            Row(
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.Center
                            ) {
                                Icon(
                                    imageVector = Icons.Default.NotificationsOff,
                                    contentDescription = "Warning",
                                    tint = EmergencyRed,
                                    modifier = Modifier.size(18.dp)
                                )
                                Spacer(modifier = Modifier.width(6.dp))
                                Text(
                                    text = "Notifications are disabled.",
                                    color = Color.White,
                                    fontSize = 13.sp,
                                    fontWeight = FontWeight.Bold
                                )
                            }
                            Spacer(modifier = Modifier.height(4.dp))
                            Text(
                                text = "Enable notifications to receive TRINETRA security alerts.",
                                color = TextSecondary,
                                fontSize = 11.sp,
                                textAlign = TextAlign.Center
                            )
                            Spacer(modifier = Modifier.height(8.dp))
                            Button(
                                onClick = { openNotificationSettings(context) },
                                shape = RoundedCornerShape(8.dp),
                                colors = ButtonDefaults.buttonColors(
                                    containerColor = EmergencyRed,
                                    contentColor = Color.White
                                )
                            ) {
                                Text(
                                    text = "OPEN NOTIFICATION SETTINGS",
                                    fontSize = 11.sp,
                                    fontWeight = FontWeight.Bold
                                )
                            }
                        }
                    }
                }

                // ==============================================================================
                // 8. SERVER / FIREBASE CONNECTION INFO (Compact Footer)
                // ==============================================================================
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(14.dp),
                    colors = CardDefaults.cardColors(containerColor = DarkCard),
                    border = BorderStroke(1.dp, DarkCardBorder)
                ) {
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(12.dp),
                        horizontalAlignment = Alignment.CenterHorizontally
                    ) {
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.Center
                        ) {
                            Text(
                                text = "Server",
                                color = TextSecondary,
                                fontSize = 12.sp,
                                fontWeight = FontWeight.Medium
                            )
                            Spacer(modifier = Modifier.width(6.dp))
                            Box(
                                modifier = Modifier
                                    .size(7.dp)
                                    .clip(CircleShape)
                                    .background(if (isServerConnected) SuccessGreen else EmergencyRed)
                            )
                            Spacer(modifier = Modifier.width(6.dp))
                            Text(
                                text = if (isServerConnected) "Connected" else "Disconnected",
                                color = if (isServerConnected) SuccessGreen else EmergencyRed,
                                fontSize = 12.sp,
                                fontWeight = FontWeight.SemiBold
                            )
                        }

                        Spacer(modifier = Modifier.height(4.dp))

                        Text(
                            text = if (connectionMode == ConnectionMode.LOCAL)
                                "LOCAL LAN INTEGRATION ACTIVE"
                            else
                                "FIREBASE CLOUD RELAY ACTIVE",
                            color = CyanAccent,
                            fontSize = 10.sp,
                            fontWeight = FontWeight.Bold,
                            textAlign = TextAlign.Center,
                            letterSpacing = 0.5.sp
                        )

                        Spacer(modifier = Modifier.height(2.dp))

                        Text(
                            text = if (connectionMode == ConnectionMode.LOCAL)
                                "Local Subnet: $activeBaseUrl"
                            else
                                "Device: $targetDeviceId" + (if (remoteLastSeen.isNotBlank()) " • Last Seen: ${remoteLastSeen.take(19).replace("T", " ")}" else ""),
                            color = TextMuted,
                            fontSize = 10.sp,
                            textAlign = TextAlign.Center
                        )
                    }
                }
            }

            // Connection Configuration Dialog
            if (showConfigDialog) {
                ConnectionConfigDialog(
                    currentMode = connectionMode,
                    currentRemoteUrl = currentRemoteUrl,
                    currentApiKey = currentApiKey,
                    currentTargetDeviceId = targetDeviceId,
                    onDismiss = { showConfigDialog = false },
                    onSave = { mode, remoteUrl, apiKey, deviceId ->
                        viewModel.updateRemoteConfig(remoteUrl, apiKey, deviceId)
                        viewModel.setConnectionMode(mode)
                    }
                )
            }

            // Full Screen Security Alert Snapshot Viewer
            if (showFullScreenSnapshot && activeAlert != null) {
                activeAlert?.let { alert ->
                    FullScreenSnapshotViewer(
                        alert = alert,
                        baseUrl = activeBaseUrl,
                        connectionMode = connectionMode,
                        onDismiss = { showFullScreenSnapshot = false }
                    )
                }
            }

            // Customer Setup Walkthrough Dialog
            if (showSetupGuide) {
                CustomerSetupDialog(
                    targetDeviceId = targetDeviceId,
                    registrationStatus = registrationStatus,
                    isServerConnected = isServerConnected,
                    systemStatus = systemStatus,
                    connectionMode = connectionMode,
                    onDismiss = { viewModel.dismissSetupGuide() },
                    onRetryRegistration = { viewModel.retryDeviceRegistration(context) }
                )
            }
        }
    }
}

@Composable
fun ConnectionConfigDialog(
    currentMode: ConnectionMode,
    currentRemoteUrl: String,
    currentApiKey: String,
    currentTargetDeviceId: String,
    onDismiss: () -> Unit,
    onSave: (mode: ConnectionMode, remoteUrl: String, apiKey: String, deviceId: String) -> Unit
) {
    var selectedMode by remember { mutableStateOf(currentMode) }
    var remoteUrlInput by remember { mutableStateOf(currentRemoteUrl) }
    var apiKeyInput by remember { mutableStateOf(currentApiKey) }
    var deviceIdInput by remember { mutableStateOf(currentTargetDeviceId) }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = {
            Text(
                text = "Connection Mode",
                color = TextPrimary,
                fontWeight = FontWeight.Bold,
                fontSize = 18.sp
            )
        },
        text = {
            Column(
                modifier = Modifier.fillMaxWidth(),
                verticalArrangement = Arrangement.spacedBy(14.dp)
            ) {
                Text(
                    text = "Select whether this phone connects over local Wi-Fi or Firebase Cloud Relay:",
                    color = TextSecondary,
                    fontSize = 13.sp
                )

                // Mode Selector Buttons
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(10.dp))
                        .background(DarkSurface)
                        .padding(4.dp),
                    horizontalArrangement = Arrangement.spacedBy(4.dp)
                ) {
                    Button(
                        onClick = { selectedMode = ConnectionMode.LOCAL },
                        modifier = Modifier.weight(1f),
                        shape = RoundedCornerShape(8.dp),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = if (selectedMode == ConnectionMode.LOCAL) CyanAccent else Color.Transparent,
                            contentColor = if (selectedMode == ConnectionMode.LOCAL) Color.Black else TextSecondary
                        ),
                        elevation = null
                    ) {
                        Text(
                            text = "LOCAL (LAN)",
                            fontSize = 12.sp,
                            fontWeight = FontWeight.Bold
                        )
                    }

                    Button(
                        onClick = { selectedMode = ConnectionMode.REMOTE },
                        modifier = Modifier.weight(1f),
                        shape = RoundedCornerShape(8.dp),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = if (selectedMode == ConnectionMode.REMOTE) WarningYellow else Color.Transparent,
                            contentColor = if (selectedMode == ConnectionMode.REMOTE) Color.Black else TextSecondary
                        ),
                        elevation = null
                    ) {
                        Text(
                            text = "REMOTE",
                            fontSize = 12.sp,
                            fontWeight = FontWeight.Bold
                        )
                    }
                }

                if (selectedMode == ConnectionMode.LOCAL) {
                    Text(
                        text = "🟢 LAN Target: http://192.168.31.188:8000/",
                        color = TextMuted,
                        fontSize = 12.sp
                    )
                } else {
                    OutlinedTextField(
                        value = deviceIdInput,
                        onValueChange = { deviceIdInput = it },
                        label = { Text("TRINETRA Device ID") },
                        placeholder = { Text("trinetra-shop-f20424b4") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedBorderColor = CyanAccent,
                            unfocusedBorderColor = DarkCardBorder,
                            focusedTextColor = Color.White,
                            unfocusedTextColor = Color.White
                        )
                    )

                    Text(
                        text = "☁️ Firebase Cloud Relay operates seamlessly across any cellular network without port forwarding.",
                        color = TextMuted,
                        fontSize = 11.sp
                    )
                }
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    onSave(selectedMode, remoteUrlInput, apiKeyInput, deviceIdInput)
                    onDismiss()
                },
                colors = ButtonDefaults.buttonColors(containerColor = CyanAccent, contentColor = Color.Black)
            ) {
                Text("Save & Connect", fontWeight = FontWeight.Bold)
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text("Cancel", color = TextSecondary)
            }
        },
        containerColor = DarkCard,
        shape = RoundedCornerShape(18.dp)
    )
}

fun openNotificationSettings(context: Context) {
    val intent = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
        Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS).apply {
            putExtra(Settings.EXTRA_APP_PACKAGE, context.packageName)
        }
    } else {
        Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).apply {
            data = Uri.fromParts("package", context.packageName, null)
        }
    }
    intent.flags = Intent.FLAG_ACTIVITY_NEW_TASK
    try {
        context.startActivity(intent)
    } catch (_: Exception) {
        val fallbackIntent = Intent(Settings.ACTION_SETTINGS).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK
        }
        context.startActivity(fallbackIntent)
    }
}

@Composable
fun FullScreenSnapshotViewer(
    alert: ActiveAlertData,
    baseUrl: String,
    connectionMode: ConnectionMode = ConnectionMode.LOCAL,
    onDismiss: () -> Unit
) {
    val context = LocalContext.current
    val coroutineScope = rememberCoroutineScope()
    val fullSnapshotUrl = alert.getFullSnapshotUrl(baseUrl)
    val effectiveId = alert.effectiveAlertId ?: "UNKNOWN"
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
                        Log.i("TRINETRA_SNAPSHOT", "[TRINETRA SNAPSHOT FULL START] alertId=$effectiveId reference=${alert.effectiveSnapshotReference} remoteRef=${alert.effectiveRemoteReference} resolvedModel=$model mode=$connectionMode")
                    },
                    onSuccess = { _, result ->
                        Log.i("TRINETRA_SNAPSHOT", "[TRINETRA SNAPSHOT FULL SUCCESS] alertId=$effectiveId model=$model dataSource=${result.dataSource}")
                    },
                    onError = { _, result ->
                        Log.e("TRINETRA_SNAPSHOT", "[TRINETRA SNAPSHOT FULL ERROR] alertId=$effectiveId model=$model error=${result.throwable.message}")
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
            modifier = Modifier.fillMaxSize(),
            color = Color.Black
        ) {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(16.dp)
            ) {
                // Top Action Bar
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(top = 8.dp, bottom = 12.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        IconButton(onClick = onDismiss) {
                            Icon(
                                imageVector = Icons.AutoMirrored.Filled.ArrowBack,
                                contentDescription = "Back",
                                tint = Color.White
                            )
                        }
                        Spacer(modifier = Modifier.width(8.dp))
                        Text(
                            text = "SECURITY EVIDENCE",
                            color = Color.White,
                            fontSize = 16.sp,
                            fontWeight = FontWeight.Bold,
                            letterSpacing = 1.sp
                        )
                    }

                    IconButton(onClick = onDismiss) {
                        Icon(
                            imageVector = Icons.Default.Close,
                            contentDescription = "Close",
                            tint = Color.White
                        )
                    }
                }

                // Image Viewer Area
                Box(
                    modifier = Modifier
                        .weight(1f)
                        .fillMaxWidth(),
                    contentAlignment = Alignment.Center
                ) {
                    if (isExpired && !isSavedLocally) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Icon(
                                imageVector = Icons.Default.HourglassEmpty,
                                contentDescription = "Expired",
                                tint = WarningYellow,
                                modifier = Modifier.size(48.dp)
                            )
                            Spacer(modifier = Modifier.height(12.dp))
                            Text(
                                text = "Snapshot expired",
                                color = WarningYellow,
                                fontSize = 15.sp,
                                fontWeight = FontWeight.Bold
                            )
                        }
                    } else if (isResolvingRemote) {
                        Column(
                            horizontalAlignment = Alignment.CenterHorizontally,
                            verticalArrangement = Arrangement.Center,
                            modifier = Modifier.fillMaxSize()
                        ) {
                            CircularProgressIndicator(
                                color = CyanAccent,
                                modifier = Modifier.size(36.dp)
                            )
                            Spacer(modifier = Modifier.height(12.dp))
                            Text(
                                text = "Fetching remote evidence...",
                                color = TextMuted,
                                fontSize = 13.sp
                            )
                        }
                    } else if (connectionMode == ConnectionMode.REMOTE && alert.effectiveRemoteReference.isNullOrBlank() && !isSavedLocally) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Icon(
                                imageVector = Icons.Default.ImageNotSupported,
                                contentDescription = "Unavailable",
                                tint = TextMuted,
                                modifier = Modifier.size(48.dp)
                            )
                            Spacer(modifier = Modifier.height(12.dp))
                            Text(
                                text = "Remote evidence unavailable",
                                color = TextMuted,
                                fontSize = 15.sp,
                                fontWeight = FontWeight.Medium
                            )
                        }
                    } else if (imageRequest == null) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Icon(
                                imageVector = Icons.Default.ImageNotSupported,
                                contentDescription = "Unavailable",
                                tint = TextMuted,
                                modifier = Modifier.size(48.dp)
                            )
                            Spacer(modifier = Modifier.height(12.dp))
                            Text(
                                text = "Evidence unavailable",
                                color = TextMuted,
                                fontSize = 15.sp,
                                fontWeight = FontWeight.Medium
                            )
                        }
                    } else {
                        SubcomposeAsyncImage(
                            model = imageRequest,
                            contentDescription = "Full Snapshot Image",
                            modifier = Modifier.fillMaxSize(),
                            contentScale = ContentScale.Fit,
                            loading = {
                                Column(
                                    horizontalAlignment = Alignment.CenterHorizontally,
                                    verticalArrangement = Arrangement.Center,
                                    modifier = Modifier.fillMaxSize()
                                ) {
                                    CircularProgressIndicator(
                                        color = CyanAccent,
                                        modifier = Modifier.size(36.dp)
                                    )
                                    Spacer(modifier = Modifier.height(12.dp))
                                    Text(
                                        text = "Loading evidence...",
                                        color = TextMuted,
                                        fontSize = 13.sp
                                    )
                                }
                            },
                            error = {
                                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                    Icon(
                                        imageVector = Icons.Default.Warning,
                                        contentDescription = "Error",
                                        tint = WarningYellow,
                                        modifier = Modifier.size(40.dp)
                                    )
                                    Spacer(modifier = Modifier.height(8.dp))
                                    Text(
                                        text = "Unable to load evidence",
                                        color = WarningYellow,
                                        fontSize = 14.sp,
                                        fontWeight = FontWeight.SemiBold
                                    )
                                    Spacer(modifier = Modifier.height(10.dp))
                                    OutlinedButton(
                                        onClick = { snapshotRetryKey++ },
                                        shape = RoundedCornerShape(8.dp),
                                        border = BorderStroke(1.dp, CyanAccent),
                                        colors = ButtonDefaults.outlinedButtonColors(contentColor = CyanAccent)
                                    ) {
                                        Icon(
                                            imageVector = Icons.Default.Refresh,
                                            contentDescription = "Retry",
                                            modifier = Modifier.size(16.dp)
                                        )
                                        Spacer(modifier = Modifier.width(6.dp))
                                        Text(text = "RETRY", fontSize = 12.sp, fontWeight = FontWeight.Bold)
                                    }
                                }
                            },
                            success = {
                                SubcomposeAsyncImageContent()
                            }
                        )
                    }
                }

                Spacer(modifier = Modifier.height(12.dp))

                // Metadata Footer Panel with Save Button
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(14.dp),
                    colors = CardDefaults.cardColors(containerColor = DarkSurface),
                    border = BorderStroke(1.dp, DarkCardBorder)
                ) {
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(14.dp)
                    ) {
                        Text(
                            text = "Alert ID: $effectiveId",
                            color = TextPrimary,
                            fontSize = 13.sp,
                            fontWeight = FontWeight.Bold,
                            fontFamily = FontFamily.Monospace
                        )
                        Spacer(modifier = Modifier.height(2.dp))
                        Text(
                            text = "Camera: ${alert.cameraName ?: "Main Shop Camera"}",
                            color = TextSecondary,
                            fontSize = 12.sp
                        )
                        Spacer(modifier = Modifier.height(2.dp))
                        Text(
                            text = "Reason: ${alert.effectiveReason}",
                            color = TextSecondary,
                            fontSize = 12.sp
                        )
                        Spacer(modifier = Modifier.height(4.dp))
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            Text(
                                text = "Detected: $detectedTime",
                                color = TextMuted,
                                fontSize = 11.sp
                            )
                            Text(
                                text = "Available until: $expiryTime",
                                color = TextMuted,
                                fontSize = 11.sp
                            )
                        }

                        Spacer(modifier = Modifier.height(10.dp))

                        // Save action in footer
                        if (isSavedLocally) {
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .clip(RoundedCornerShape(8.dp))
                                    .background(SuccessGreen.copy(alpha = 0.15f))
                                    .padding(vertical = 8.dp, horizontal = 12.dp),
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.Center
                            ) {
                                Icon(
                                    imageVector = Icons.Default.Check,
                                    contentDescription = "Saved",
                                    tint = SuccessGreen,
                                    modifier = Modifier.size(16.dp)
                                )
                                Spacer(modifier = Modifier.width(6.dp))
                                Text(
                                    text = "SAVED TO PHONE",
                                    color = SuccessGreen,
                                    fontSize = 12.sp,
                                    fontWeight = FontWeight.Bold,
                                    letterSpacing = 0.5.sp
                                )
                            }
                        } else if (!isExpired && !activeDownloadUrl.isNullOrBlank()) {
                            Button(
                                onClick = {
                                    if (!isSaving) {
                                        isSaving = true
                                        Toast.makeText(context, "Saving snapshot...", Toast.LENGTH_SHORT).show()
                                        coroutineScope.launch {
                                            val result = SnapshotStorageHelper.saveSnapshotToDevice(context, effectiveId, activeDownloadUrl)
                                            isSaving = false
                                            if (result.isSuccess) {
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
                                    .fillMaxWidth()
                                    .height(36.dp),
                                shape = RoundedCornerShape(8.dp),
                                colors = ButtonDefaults.buttonColors(
                                    containerColor = CyanAccent.copy(alpha = 0.85f),
                                    contentColor = Color.Black
                                )
                            ) {
                                if (isSaving) {
                                    CircularProgressIndicator(
                                        modifier = Modifier.size(14.dp),
                                        color = Color.Black,
                                        strokeWidth = 2.dp
                                    )
                                    Spacer(modifier = Modifier.width(6.dp))
                                    Text(
                                        text = "Saving...",
                                        fontSize = 11.sp,
                                        fontWeight = FontWeight.Bold
                                    )
                                } else {
                                    Icon(
                                        imageVector = Icons.Default.Download,
                                        contentDescription = "Save",
                                        tint = Color.Black,
                                        modifier = Modifier.size(14.dp)
                                    )
                                    Spacer(modifier = Modifier.width(6.dp))
                                    Text(
                                        text = "SAVE TO PHONE",
                                        fontSize = 11.sp,
                                        fontWeight = FontWeight.Bold,
                                        letterSpacing = 0.5.sp
                                    )
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

