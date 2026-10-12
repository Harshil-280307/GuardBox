package com.veronic.guardbox.ui

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
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
import androidx.compose.material.icons.automirrored.filled.HelpOutline
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.CloudDone
import androidx.compose.material.icons.filled.ContentCopy
import androidx.compose.material.icons.filled.Devices
import androidx.compose.material.icons.filled.HelpOutline
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Security
import androidx.compose.material.icons.filled.Speed
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material.icons.filled.Wifi
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.veronic.guardbox.R
import com.veronic.guardbox.data.RemoteConnectionStatus
import com.veronic.guardbox.data.SystemStatus
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

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DeviceInformationScreen(
    viewModel: MainViewModel,
    onBack: () -> Unit,
    modifier: Modifier = Modifier
) {
    val context = LocalContext.current
    val systemStatus by viewModel.systemStatus.collectAsState()
    val connectionMode by viewModel.connectionMode.collectAsState()
    val isServerConnected by viewModel.isServerConnected.collectAsState()
    val remoteConnectionStatus by viewModel.remoteConnectionStatus.collectAsState()
    val targetDeviceId by viewModel.targetDeviceId.collectAsState()
    val deviceName by viewModel.deviceName.collectAsState()
    val softwareVersion by viewModel.softwareVersion.collectAsState()
    val shopId by viewModel.shopId.collectAsState()
    val shopName by viewModel.shopName.collectAsState()
    val remoteLastSeen by viewModel.remoteLastSeen.collectAsState()
    val registrationStatus by viewModel.registrationStatus.collectAsState()

    var showSetupWizard by remember { mutableStateOf(false) }

    // Human-formatted last seen value
    val formattedLastSeen = remember(remoteLastSeen) {
        AlertLifecycleHelper.formatHumanDateTime(remoteLastSeen)
    }

    // Effective Connection status display text and color
    val connectionStatusText = when {
        connectionMode == ConnectionMode.LOCAL -> if (isServerConnected) "ONLINE" else "OFFLINE"
        remoteConnectionStatus == RemoteConnectionStatus.ONLINE -> "ONLINE"
        remoteConnectionStatus == RemoteConnectionStatus.SYNCING -> "SYNCING"
        remoteConnectionStatus == RemoteConnectionStatus.MISMATCH -> "MISMATCH"
        remoteConnectionStatus == RemoteConnectionStatus.NOT_FOUND -> "NOT FOUND"
        remoteConnectionStatus == RemoteConnectionStatus.NOT_AUTHORIZED -> "NOT AUTHORIZED"
        remoteConnectionStatus == RemoteConnectionStatus.NOT_CONFIGURED -> "NOT CONFIGURED"
        remoteConnectionStatus == RemoteConnectionStatus.ERROR -> "ERROR"
        else -> "OFFLINE"
    }

    val connectionStatusColor = when (connectionStatusText) {
        "ONLINE" -> SuccessGreen
        "SYNCING" -> CyanAccent
        "NOT CONFIGURED" -> WarningYellow
        else -> EmergencyRed
    }

    val systemStatusColor = when (systemStatus) {
        SystemStatus.RUNNING -> SuccessGreen
        SystemStatus.STOPPED -> EmergencyRed
        SystemStatus.ARMING -> WarningYellow
        SystemStatus.TEST_MODE -> CyanAccent
        SystemStatus.SYNCING -> CyanAccent
        SystemStatus.MISMATCH, SystemStatus.NOT_FOUND, SystemStatus.NOT_AUTHORIZED -> EmergencyRed
        SystemStatus.NOT_CONFIGURED -> WarningYellow
        else -> TextMuted
    }

    Scaffold(
        modifier = modifier.fillMaxSize(),
        containerColor = DarkBg,
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        text = "Device Information",
                        color = TextPrimary,
                        fontSize = 18.sp,
                        fontWeight = FontWeight.Bold,
                        letterSpacing = 0.5.sp
                    )
                },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(
                            imageVector = Icons.AutoMirrored.Filled.ArrowBack,
                            contentDescription = "Back",
                            tint = CyanAccent
                        )
                    }
                },
                actions = {
                    IconButton(onClick = { viewModel.retryDeviceRegistration(context) }) {
                        Icon(
                            imageVector = Icons.Default.Refresh,
                            contentDescription = "Refresh Registration & Status",
                            tint = CyanAccent
                        )
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = DarkSurface
                )
            )
        }
    ) { paddingValues ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 20.dp, vertical = 16.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            // HEADER HERO BADGE
            Column(
                horizontalAlignment = Alignment.CenterHorizontally,
                modifier = Modifier.padding(top = 4.dp, bottom = 8.dp)
            ) {
                Box(
                    contentAlignment = Alignment.Center,
                    modifier = Modifier
                        .size(72.dp)
                        .clip(CircleShape)
                        .background(
                            Brush.radialGradient(
                                colors = listOf(
                                    CyanAccent.copy(alpha = 0.2f),
                                    Color.Transparent
                                )
                            )
                        )
                        .border(BorderStroke(1.5.dp, CyanAccent.copy(alpha = 0.6f)), CircleShape)
                ) {
                    Image(
                        painter = painterResource(id = R.drawable.trinetra_emblem),
                        contentDescription = "TRINETRA Logo",
                        modifier = Modifier.size(48.dp)
                    )
                }

                Spacer(modifier = Modifier.height(10.dp))

                Text(
                    text = "TRINETRA",
                    color = TextPrimary,
                    fontSize = 24.sp,
                    fontWeight = FontWeight.Black,
                    letterSpacing = 3.sp,
                    fontFamily = FontFamily.SansSerif
                )

                Text(
                    text = "Security Device",
                    color = CyanAccent,
                    fontSize = 13.sp,
                    fontWeight = FontWeight.Medium,
                    letterSpacing = 1.sp
                )
            }

            // SECTION 1: DEVICE IDENTITY & REGISTRATION
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(16.dp),
                colors = CardDefaults.cardColors(containerColor = DarkCard),
                border = BorderStroke(1.dp, DarkCardBorder)
            ) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(14.dp)
                ) {
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.SpaceBetween,
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Text(
                            text = "DEVICE IDENTITY",
                            color = CyanAccent,
                            fontSize = 11.sp,
                            fontWeight = FontWeight.Bold,
                            letterSpacing = 1.sp
                        )

                        // Registration Status Badge
                        DeviceRegistrationBadge(
                            status = registrationStatus,
                            onRetry = { viewModel.retryDeviceRegistration(context) }
                        )
                    }

                    // Device Name
                    DeviceInfoRow(
                        label = "Device Name",
                        value = deviceName.ifBlank { "TRINETRA Jewellery Security" },
                        icon = Icons.Default.Devices
                    )

                    // Shop ID & Shop Name (Phase 5.9 Multi-Shop Architecture)
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text(
                                text = "Shop ID",
                                color = TextMuted,
                                fontSize = 11.sp,
                                fontWeight = FontWeight.Medium
                            )
                            Spacer(modifier = Modifier.height(2.dp))
                            Text(
                                text = shopId.ifBlank { "SHOP-RK-001" },
                                color = CyanAccent,
                                fontSize = 13.sp,
                                fontWeight = FontWeight.Bold,
                                fontFamily = FontFamily.Monospace
                            )
                        }

                        IconButton(
                            onClick = {
                                val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                                val clip = ClipData.newPlainText("TRINETRA Shop ID", shopId.ifBlank { "SHOP-RK-001" })
                                clipboard.setPrimaryClip(clip)
                                Toast.makeText(context, "Shop ID copied to clipboard", Toast.LENGTH_SHORT).show()
                            },
                            modifier = Modifier.size(32.dp)
                        ) {
                            Icon(
                                imageVector = Icons.Default.ContentCopy,
                                contentDescription = "Copy Shop ID",
                                tint = CyanAccent,
                                modifier = Modifier.size(16.dp)
                            )
                        }
                    }

                    DeviceInfoRow(
                        label = "Shop",
                        value = shopName.ifBlank { "Rajkot Jewellery" },
                        icon = Icons.Default.Security
                    )

                    // Device ID with Locked Indicator and Copy Button
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Column(modifier = Modifier.weight(1f)) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Text(
                                    text = "Device ID",
                                    color = TextMuted,
                                    fontSize = 11.sp,
                                    fontWeight = FontWeight.Medium
                                )
                                Spacer(modifier = Modifier.width(6.dp))
                                Box(
                                    modifier = Modifier
                                        .clip(RoundedCornerShape(4.dp))
                                        .background(Color.White.copy(alpha = 0.08f))
                                        .padding(horizontal = 6.dp, vertical = 2.dp)
                                ) {
                                    Text(
                                        text = "🔒 LOCKED",
                                        color = TextMuted,
                                        fontSize = 9.sp,
                                        fontWeight = FontWeight.Bold
                                    )
                                }
                            }
                            Spacer(modifier = Modifier.height(2.dp))
                            Text(
                                text = targetDeviceId,
                                color = TextPrimary,
                                fontSize = 13.sp,
                                fontWeight = FontWeight.SemiBold,
                                fontFamily = FontFamily.Monospace
                            )
                        }

                        IconButton(
                            onClick = {
                                val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                                val clip = ClipData.newPlainText("TRINETRA Device ID", targetDeviceId)
                                clipboard.setPrimaryClip(clip)
                                Toast.makeText(context, "Device ID copied to clipboard", Toast.LENGTH_SHORT).show()
                            },
                            modifier = Modifier.size(32.dp)
                        ) {
                            Icon(
                                imageVector = Icons.Default.ContentCopy,
                                contentDescription = "Copy Device ID",
                                tint = CyanAccent,
                                modifier = Modifier.size(16.dp)
                            )
                        }
                    }

                    // Software Version
                    DeviceInfoRow(
                        label = "Software Version",
                        value = softwareVersion.ifBlank { "1.0.0" },
                        icon = Icons.Default.Info
                    )
                }
            }

            // SECTION 2: OPERATIONAL & CONNECTION STATUS
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(16.dp),
                colors = CardDefaults.cardColors(containerColor = DarkCard),
                border = BorderStroke(1.dp, DarkCardBorder)
            ) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(14.dp)
                ) {
                    Text(
                        text = "SYSTEM & NETWORK STATUS",
                        color = CyanAccent,
                        fontSize = 11.sp,
                        fontWeight = FontWeight.Bold,
                        letterSpacing = 1.sp
                    )

                    // Physical Security System Status
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Column {
                            Text(
                                text = "System Status",
                                color = TextMuted,
                                fontSize = 11.sp,
                                fontWeight = FontWeight.Medium
                            )
                            Spacer(modifier = Modifier.height(2.dp))
                            Text(
                                text = "Physical Security State",
                                color = TextSecondary,
                                fontSize = 9.sp
                            )
                        }

                        Box(
                            modifier = Modifier
                                .clip(RoundedCornerShape(8.dp))
                                .background(systemStatusColor.copy(alpha = 0.15f))
                                .border(BorderStroke(1.dp, systemStatusColor.copy(alpha = 0.5f)), RoundedCornerShape(8.dp))
                                .padding(horizontal = 10.dp, vertical = 5.dp)
                        ) {
                            Text(
                                text = systemStatus.name,
                                color = systemStatusColor,
                                fontSize = 12.sp,
                                fontWeight = FontWeight.Bold,
                                letterSpacing = 0.5.sp
                            )
                        }
                    }

                    // Network Connection Status
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Column {
                            Text(
                                text = "Connection Status",
                                color = TextMuted,
                                fontSize = 11.sp,
                                fontWeight = FontWeight.Medium
                            )
                            Spacer(modifier = Modifier.height(2.dp))
                            Text(
                                text = if (connectionMode == ConnectionMode.LOCAL) "Local LAN Subnet" else "Firebase Cloud Relay",
                                color = TextSecondary,
                                fontSize = 9.sp
                            )
                        }

                        Box(
                            modifier = Modifier
                                .clip(RoundedCornerShape(8.dp))
                                .background(connectionStatusColor.copy(alpha = 0.15f))
                                .border(BorderStroke(1.dp, connectionStatusColor.copy(alpha = 0.5f)), RoundedCornerShape(8.dp))
                                .padding(horizontal = 10.dp, vertical = 5.dp)
                        ) {
                            Text(
                                text = connectionStatusText,
                                color = connectionStatusColor,
                                fontSize = 12.sp,
                                fontWeight = FontWeight.Bold,
                                letterSpacing = 0.5.sp
                            )
                        }
                    }

                    // Last Seen
                    DeviceInfoRow(
                        label = "Last Seen",
                        value = formattedLastSeen,
                        icon = Icons.Default.Speed
                    )
                }
            }

            // SECTION 3: CUSTOMER SETUP FLOW (4 STEPS)
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(16.dp),
                colors = CardDefaults.cardColors(containerColor = DarkSurface),
                border = BorderStroke(1.dp, CyanAccent.copy(alpha = 0.35f))
            ) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Text(
                            text = "DEPLOYMENT SETUP FLOW",
                            color = CyanAccent,
                            fontSize = 11.sp,
                            fontWeight = FontWeight.Bold,
                            letterSpacing = 1.sp
                        )

                        TextButton(
                            onClick = { showSetupWizard = true }
                        ) {
                            Icon(
                                imageVector = Icons.AutoMirrored.Filled.HelpOutline,
                                contentDescription = "Setup Guide",
                                tint = CyanAccent,
                                modifier = Modifier.size(14.dp)
                            )
                            Spacer(modifier = Modifier.width(4.dp))
                            Text(
                                text = "Setup Wizard",
                                color = CyanAccent,
                                fontSize = 11.sp,
                                fontWeight = FontWeight.Bold
                            )
                        }
                    }

                    // Step 1: TRINETRA device detected
                    SetupStepItem(
                        stepNumber = 1,
                        title = "TRINETRA device detected",
                        subtitle = "Hardware ID: $targetDeviceId",
                        isCompleted = targetDeviceId.isNotBlank()
                    )

                    // Step 2: Device registration
                    SetupStepItem(
                        stepNumber = 2,
                        title = "Device registration",
                        subtitle = if (registrationStatus == DeviceRegistrationStatus.REGISTERED) "FCM & Local Token Active" else "Registration Pending",
                        isCompleted = registrationStatus == DeviceRegistrationStatus.REGISTERED
                    )

                    // Step 3: Connection established
                    SetupStepItem(
                        stepNumber = 3,
                        title = "Connection established",
                        subtitle = if (isServerConnected) "Connected via ${if (connectionMode == ConnectionMode.LOCAL) "LAN" else "Cloud"}" else "Awaiting Server Link",
                        isCompleted = isServerConnected
                    )

                    // Step 4: Security system ready
                    SetupStepItem(
                        stepNumber = 4,
                        title = "Security system ready",
                        subtitle = if (systemStatus == SystemStatus.RUNNING) "Perimeter Armed & Active" else "Perimeter Disarmed / Ready",
                        isCompleted = isServerConnected && registrationStatus == DeviceRegistrationStatus.REGISTERED
                    )
                }
            }

            Spacer(modifier = Modifier.height(8.dp))
        }
    }

    // Customer Setup Wizard Dialog
    if (showSetupWizard) {
        CustomerSetupDialog(
            targetDeviceId = targetDeviceId,
            registrationStatus = registrationStatus,
            isServerConnected = isServerConnected,
            systemStatus = systemStatus,
            connectionMode = connectionMode,
            onDismiss = { showSetupWizard = false },
            onRetryRegistration = { viewModel.retryDeviceRegistration(context) }
        )
    }
}

@Composable
fun DeviceInfoRow(
    label: String,
    value: String,
    icon: ImageVector
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(
                imageVector = icon,
                contentDescription = label,
                tint = TextMuted,
                modifier = Modifier.size(16.dp)
            )
            Spacer(modifier = Modifier.width(8.dp))
            Text(
                text = label,
                color = TextMuted,
                fontSize = 12.sp,
                fontWeight = FontWeight.Medium
            )
        }

        Text(
            text = value,
            color = TextPrimary,
            fontSize = 13.sp,
            fontWeight = FontWeight.SemiBold
        )
    }
}

@Composable
fun DeviceRegistrationBadge(
    status: DeviceRegistrationStatus,
    onRetry: () -> Unit
) {
    when (status) {
        DeviceRegistrationStatus.REGISTERED -> {
            Box(
                modifier = Modifier
                    .clip(RoundedCornerShape(8.dp))
                    .background(SuccessGreen.copy(alpha = 0.15f))
                    .border(BorderStroke(1.dp, SuccessGreen.copy(alpha = 0.5f)), RoundedCornerShape(8.dp))
                    .padding(horizontal = 8.dp, vertical = 4.dp)
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(
                        imageVector = Icons.Default.CheckCircle,
                        contentDescription = "Registered",
                        tint = SuccessGreen,
                        modifier = Modifier.size(12.dp)
                    )
                    Spacer(modifier = Modifier.width(4.dp))
                    Text(
                        text = "✓ DEVICE REGISTERED",
                        color = SuccessGreen,
                        fontSize = 10.sp,
                        fontWeight = FontWeight.Bold
                    )
                }
            }
        }
        DeviceRegistrationStatus.REGISTERING -> {
            Box(
                modifier = Modifier
                    .clip(RoundedCornerShape(8.dp))
                    .background(CyanAccent.copy(alpha = 0.15f))
                    .padding(horizontal = 8.dp, vertical = 4.dp)
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(10.dp),
                        color = CyanAccent,
                        strokeWidth = 1.5.dp
                    )
                    Spacer(modifier = Modifier.width(4.dp))
                    Text(
                        text = "REGISTERING...",
                        color = CyanAccent,
                        fontSize = 10.sp,
                        fontWeight = FontWeight.Bold
                    )
                }
            }
        }
        DeviceRegistrationStatus.NOT_REGISTERED, DeviceRegistrationStatus.FAILED -> {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier
                    .clip(RoundedCornerShape(8.dp))
                    .background(WarningYellow.copy(alpha = 0.15f))
                    .border(BorderStroke(1.dp, WarningYellow.copy(alpha = 0.5f)), RoundedCornerShape(8.dp))
                    .clickable { onRetry() }
                    .padding(horizontal = 8.dp, vertical = 4.dp)
            ) {
                Text(
                    text = "DEVICE NOT REGISTERED (RETRY)",
                    color = WarningYellow,
                    fontSize = 10.sp,
                    fontWeight = FontWeight.Bold
                )
            }
        }
    }
}

@Composable
fun SetupStepItem(
    stepNumber: Int,
    title: String,
    subtitle: String,
    isCompleted: Boolean
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(10.dp))
            .background(DarkCard)
            .padding(10.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier.weight(1f)
        ) {
            Box(
                contentAlignment = Alignment.Center,
                modifier = Modifier
                    .size(24.dp)
                    .clip(CircleShape)
                    .background(if (isCompleted) SuccessGreen.copy(alpha = 0.2f) else DarkSurface)
                    .border(
                        BorderStroke(1.dp, if (isCompleted) SuccessGreen else TextMuted),
                        CircleShape
                    )
            ) {
                if (isCompleted) {
                    Icon(
                        imageVector = Icons.Default.CheckCircle,
                        contentDescription = "Step Complete",
                        tint = SuccessGreen,
                        modifier = Modifier.size(14.dp)
                    )
                } else {
                    Text(
                        text = stepNumber.toString(),
                        color = TextMuted,
                        fontSize = 11.sp,
                        fontWeight = FontWeight.Bold
                    )
                }
            }

            Spacer(modifier = Modifier.width(10.dp))

            Column {
                Text(
                    text = "STEP $stepNumber: $title",
                    color = if (isCompleted) TextPrimary else TextSecondary,
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Bold
                )
                Text(
                    text = subtitle,
                    color = if (isCompleted) SuccessGreen else TextMuted,
                    fontSize = 10.sp
                )
            }
        }

        Box(
            modifier = Modifier
                .clip(RoundedCornerShape(6.dp))
                .background(if (isCompleted) SuccessGreen.copy(alpha = 0.15f) else WarningYellow.copy(alpha = 0.15f))
                .padding(horizontal = 6.dp, vertical = 3.dp)
        ) {
            Text(
                text = if (isCompleted) "READY" else "PENDING",
                color = if (isCompleted) SuccessGreen else WarningYellow,
                fontSize = 9.sp,
                fontWeight = FontWeight.Bold
            )
        }
    }
}

@Composable
fun CustomerSetupDialog(
    targetDeviceId: String,
    registrationStatus: DeviceRegistrationStatus,
    isServerConnected: Boolean,
    systemStatus: SystemStatus,
    connectionMode: ConnectionMode,
    onDismiss: () -> Unit,
    onRetryRegistration: () -> Unit
) {
    var currentStep by remember { mutableIntStateOf(1) }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    imageVector = Icons.Default.Security,
                    contentDescription = "TRINETRA Setup",
                    tint = CyanAccent,
                    modifier = Modifier.size(20.dp)
                )
                Spacer(modifier = Modifier.width(8.dp))
                Text(
                    text = "Customer Setup Flow",
                    color = TextPrimary,
                    fontWeight = FontWeight.Bold,
                    fontSize = 17.sp
                )
            }
        },
        text = {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(14.dp)
            ) {
                // Step Indicator Pills
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(4.dp)
                ) {
                    (1..4).forEach { step ->
                        Box(
                            modifier = Modifier
                                .weight(1f)
                                .height(4.dp)
                                .clip(RoundedCornerShape(2.dp))
                                .background(
                                    if (step <= currentStep) CyanAccent else DarkCardBorder
                                )
                        )
                    }
                }

                when (currentStep) {
                    1 -> {
                        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            Text(
                                text = "STEP 1",
                                color = CyanAccent,
                                fontSize = 11.sp,
                                fontWeight = FontWeight.Bold,
                                letterSpacing = 1.sp
                            )
                            Text(
                                text = "TRINETRA Device Detected",
                                color = TextPrimary,
                                fontSize = 15.sp,
                                fontWeight = FontWeight.Bold
                            )
                            Text(
                                text = "The TRINETRA security appliance has been identified with its unique hardware-bound identity:",
                                color = TextSecondary,
                                fontSize = 12.sp
                            )
                            Card(
                                modifier = Modifier.fillMaxWidth(),
                                shape = RoundedCornerShape(8.dp),
                                colors = CardDefaults.cardColors(containerColor = DarkSurface)
                            ) {
                                Text(
                                    text = targetDeviceId,
                                    color = CyanAccent,
                                    fontSize = 12.sp,
                                    fontFamily = FontFamily.Monospace,
                                    fontWeight = FontWeight.Bold,
                                    modifier = Modifier.padding(10.dp)
                                )
                            }
                        }
                    }
                    2 -> {
                        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            Text(
                                text = "STEP 2",
                                color = CyanAccent,
                                fontSize = 11.sp,
                                fontWeight = FontWeight.Bold,
                                letterSpacing = 1.sp
                            )
                            Text(
                                text = "Device Registration",
                                color = TextPrimary,
                                fontSize = 15.sp,
                                fontWeight = FontWeight.Bold
                            )
                            Text(
                                text = "Registers this smartphone client for instant high-priority emergency notifications and secure command authorization.",
                                color = TextSecondary,
                                fontSize = 12.sp
                            )
                            DeviceRegistrationBadge(
                                status = registrationStatus,
                                onRetry = onRetryRegistration
                            )
                        }
                    }
                    3 -> {
                        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            Text(
                                text = "STEP 3",
                                color = CyanAccent,
                                fontSize = 11.sp,
                                fontWeight = FontWeight.Bold,
                                letterSpacing = 1.sp
                            )
                            Text(
                                text = "Connection Established",
                                color = TextPrimary,
                                fontSize = 15.sp,
                                fontWeight = FontWeight.Bold
                            )
                            Text(
                                text = "Real-time communication link is active across ${if (connectionMode == ConnectionMode.LOCAL) "Local Wi-Fi Subnet" else "Firebase Cloud Relay"}.",
                                color = TextSecondary,
                                fontSize = 12.sp
                            )
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Box(
                                    modifier = Modifier
                                        .size(8.dp)
                                        .clip(CircleShape)
                                        .background(if (isServerConnected) SuccessGreen else EmergencyRed)
                                )
                                Spacer(modifier = Modifier.width(6.dp))
                                Text(
                                    text = if (isServerConnected) "ONLINE & SYNCHRONIZED" else "OFFLINE / CONNECTING",
                                    color = if (isServerConnected) SuccessGreen else EmergencyRed,
                                    fontSize = 12.sp,
                                    fontWeight = FontWeight.Bold
                                )
                            }
                        }
                    }
                    4 -> {
                        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            Text(
                                text = "STEP 4",
                                color = CyanAccent,
                                fontSize = 11.sp,
                                fontWeight = FontWeight.Bold,
                                letterSpacing = 1.sp
                            )
                            Text(
                                text = "Security System Ready",
                                color = TextPrimary,
                                fontSize = 15.sp,
                                fontWeight = FontWeight.Bold
                            )
                            Text(
                                text = "TRINETRA optical perimeter defense is online and ready for full arming and 24/7 jewelry protection.",
                                color = TextSecondary,
                                fontSize = 12.sp
                            )
                            Box(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .clip(RoundedCornerShape(8.dp))
                                    .background(SuccessGreen.copy(alpha = 0.15f))
                                    .padding(10.dp)
                            ) {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Icon(
                                        imageVector = Icons.Default.CheckCircle,
                                        contentDescription = "Ready",
                                        tint = SuccessGreen,
                                        modifier = Modifier.size(16.dp)
                                    )
                                    Spacer(modifier = Modifier.width(8.dp))
                                    Text(
                                        text = "TRINETRA READY • Status: ${systemStatus.name}",
                                        color = SuccessGreen,
                                        fontSize = 12.sp,
                                        fontWeight = FontWeight.Bold
                                    )
                                }
                            }
                        }
                    }
                }
            }
        },
        confirmButton = {
            if (currentStep < 4) {
                Button(
                    onClick = { currentStep++ },
                    colors = ButtonDefaults.buttonColors(containerColor = CyanAccent, contentColor = Color.Black)
                ) {
                    Text("Next Step", fontWeight = FontWeight.Bold)
                }
            } else {
                Button(
                    onClick = onDismiss,
                    colors = ButtonDefaults.buttonColors(containerColor = SuccessGreen, contentColor = Color.Black)
                ) {
                    Text("Finish Setup", fontWeight = FontWeight.Bold)
                }
            }
        },
        dismissButton = {
            if (currentStep > 1) {
                TextButton(onClick = { currentStep-- }) {
                    Text("Previous", color = TextSecondary)
                }
            } else {
                TextButton(onClick = onDismiss) {
                    Text("Dismiss", color = TextSecondary)
                }
            }
        },
        containerColor = DarkCard,
        shape = RoundedCornerShape(18.dp)
    )
}
