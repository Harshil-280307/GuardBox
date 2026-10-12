# Veronic GuardBox — Backend Service & Push Escalation (Phase 3)

FastAPI-powered intelligent edge security engine with multi-camera RTSP/USB ingestion, dual-layer motion detection, polygon zone masking, and **Phase 3 Android Emergency Push Alert System (FCM)**.

---

## 1. Phase 3 Architecture: Android Emergency Alert Receiver

In Phase 3, Veronic GuardBox connects directly to registered **Android Security Devices** via **Firebase Cloud Messaging (FCM)**:

1. **Camera Detection Engine** triggers a HIGH/CRITICAL intrusion alert.
2. **Push Escalation Engine** (`app/push/escalation.py`) queries registered Android devices sorted by priority order (1, 2, 3...).
3. **High-Priority FCM Payload** is dispatched with:
   - Android Notification Priority `MAX`
   - Android Notification Channel `guardbox_emergency_channel` (High importance, Alarm siren sound & vibration)
   - Full-Screen Intent `EmergencyAlertActivity` (Wakes locked screen immediately)
4. If a guard taps **"I'M HANDLING IT"** (`POST /api/alerts/{id}/acknowledge`), the alert is resolved and all further escalations are immediately halted.
5. If an alert is unacknowledged after the timeout window (e.g. 45s) or a guard taps **"ESCALATE"**, the system automatically advances to Contact / Device #2.

---

## 2. Environment Variables & FCM Configuration

Configure your `backend/.env` file:

```ini
# Veronic GuardBox Backend Configuration
HOST=0.0.0.0
PORT=8000
DEBUG=True

# Database
DATABASE_PATH=guardbox.db

# Storage Directories
SNAPSHOT_DIR=storage/snapshots
RECORDING_DIR=storage/recordings
EXPORTS_DIR=storage/exports

# Phase 3 — Firebase Cloud Messaging (FCM) Emergency Push Notifications
# Set your Firebase Server Key or HTTP v1 service account credential
FCM_SERVER_KEY=your_fcm_server_key_here

# Push Escalation Parameters
AUTO_PUSH_ENABLED=True
PUSH_TIMEOUT_SECONDS=45
MIN_ALERT_SEVERITY=HIGH
ALERT_COOLDOWN_SECONDS=120
```

> **Note:** If `FCM_SERVER_KEY` is not provided, the backend operates in **Simulated Mock Dispatch Mode** for local testing. All push deliveries and device state transitions will continue to work seamlessly for local test suites.

---

## 3. Running Backend Services

```powershell
# Activate Python virtual environment
.\venv\Scripts\Activate.ps1

# Run FastAPI Server
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 4. Running the Phase 3 Push Escalation Test Suite

```powershell
.\venv\Scripts\python.exe test_push_escalation.py
```

All 8 tests test:
- Android device registration & token update
- Priority order reordering (Priority 1 -> Priority 2)
- Safe non-emergency test push dispatch
- High-priority security emergency dispatch with full-screen intent payloads
- "I'M HANDLING IT" single-touch acknowledgement & loop termination
- Multi-device sequential escalation flow
- Camera anti-spam cooldown protection
- Notification settings & FCM diagnostics

---

## 5. Android Application (Kotlin / Jetpack Compose)

The native Android app source code is located in `android/`:
- **Package:** `com.veronic.guardbox`
- **Minimum SDK:** 26 (Android 8.0 Oreo) | **Target SDK:** 34 (Android 14)
- **Features:**
  - Full-screen wake lock activity (`EmergencyAlertActivity`)
  - Jetpack Compose Material 3 UI (`DashboardScreen`, `AlertDetailScreen`, `SettingsScreen`)
  - Retrofit HTTP client with customizable backend server URL
  - Auto FCM token synchronization with backend
