# Veronic GuardBox — Phase 2: Reliable Local Monitoring & Advanced Event Handling

A local-first security monitoring prototype engineered for jewellery shops and high-value retail stores running on Windows.

> [!WARNING]
> **PROTOTYPE NOTICE & SECURITY DISCLAIMER**
> - This software is a **Phase 2 development prototype** running locally on a Windows PC.
> - It is **not** certified security hardware and must not be marketed as a complete security system yet.
> - **No physical sirens or external GSM/cellular dispatchers are connected** in Phase 2; all alarms and notifications are simulated in software.
> - Laptop sleep, OS power savings, or Wi-Fi drops will interrupt camera monitoring.
> - Never expose backend or video streaming ports to the public internet without an encrypted VPN tunnel.

---

## 1. Project Overview & Architecture

Veronic GuardBox interfaces directly with a **TP-Link Tapo C100 Wi-Fi IP Camera** via local RTSP, converts frames into a browser-friendly MJPEG live stream, enforces rectangular **Detection Zones (Region of Interest - ROI)**, reduces false alarms via **motion persistence and warmup guards**, manages arming lifecycles with **exit countdown delays**, tracks **event statuses (`NEW`, `ACKNOWLEDGED`, `FALSE_ALARM`, `RESOLVED`)**, automates store hours via a **Shop Schedule**, and logs all activities to an embedded SQLite database.

```
+-----------------------------------------------------------------------------------------+
|                                    LOCAL AREA NETWORK (LAN)                             |
|                                                                                         |
|  +--------------------+             RTSP Stream             +-------------------------+ |
|  |  TP-Link Tapo C100 |====================================>| OpenCV Background Worker| |
|  |   192.168.31.108   |     (rtsp://...:554/stream1)        | (Buffer=1, FPS Monitor) | |
|  +--------------------+                                     +------------+------------+ |
|                                                                          |              |
|                                         +--------------------------------+              |
|                                         |                                               |
|                                         v                                               |
|                       +-----------------------------------+                             |
|                       |   Motion Engine (OpenCV MOG2)     |                             |
|                       |  - Detection Zones (ROI Masks)    |                             |
|                       |  - Persistence Duration Filter    |                             |
|                       |  - Camera Warmup Guard (3s)       |                             |
|                       |  - Gaussian Noise Reduction       |                             |
|                       +-----------------+-----------------+                             |
|                                         |                                               |
|              +--------------------------+-------------------------+                     |
|              |                          |                         |                     |
|              v                          v                         v                     |
|     +------------------+      +--------------------+      +----------------+            |
|     | Snapshots Disk   |      | SQLite Database    |      | Simulated      |            |
|     | (Watermarked     |      | - events (Status)  |      | Alarm & Logs   |            |
|     |  with Zone info) |      | - detection_zones  |      | (Phase 2 audit)|            |
|     |                  |      | - schedule_config  |      |                |            |
|     |                  |      | - system_logs      |      |                |            |
|     +------------------+      +--------------------+      +----------------+            |
|                                         |                                               |
|                               HTTP MJPEG & REST API                                     |
|                                         |                                               |
|                                         v                                               |
|                              +----------------------+                                   |
|                              | React 19 / Vite UI   |                                   |
|                              | (127.0.0.1:5173)     |                                   |
|                              +----------------------+                                   |
+-----------------------------------------------------------------------------------------+
```

---

## 2. Key Phase 2 Features

### A. Rectangular Detection Zones (Region of Interest - ROI)
- Define and toggle multiple custom monitoring zones (e.g., **"Cash Counter"**, **"Jewellery Showcase"**, **"Shop Entrance"**).
- Coordinates are stored in SQLite and normalized (`0.0` to `1.0`), ensuring seamless scaling across display resolutions.
- Motion outside enabled zones is automatically filtered out to eliminate false triggers from overhead ceiling fans or outside street lights.
- Active zones are visually rendered directly over the live camera preview.

### B. False Alarm Reduction
- **Motion Persistence Duration**: Motion must continuously exceed the pixel threshold for a minimum duration (default `1.0s`) before firing an event.
- **Camera Warmup Guard**: Skips motion detection for the first `3.0s` after camera connection/reconnection to ignore sensor auto-exposure adjustments.
- **Noise Filtering & Scaling**: Gaussian blurring and morphological operations eliminate single-frame camera noise.

### C. Flexible Arming Modes & Exit Delay
- **`DISARMED`**: System standby, camera feed active, no alarms or security events recorded.
- **`ARMING`**: Exit delay countdown (e.g., `15s`) allows store staff to leave without triggering false alarms.
- **`ARMED`**: Full security monitoring. Movement inside active zones triggers events and simulated sirens.
- **`TEST_MODE`**: Allows realistic walkthrough testing. Events are recorded with `event_type='TEST_EVENT'` and `system_mode='TEST_MODE'`, without triggering real alarms.

### D. Advanced Event Management
- Complete status lifecycle: `NEW` $\rightarrow$ `ACKNOWLEDGED` $\rightarrow$ `FALSE_ALARM` $\rightarrow$ `RESOLVED`.
- Filter events by status, event type, detection zone, and date range.
- Paginated table view with instant snapshot preview.
- **Export CSV**: One-click download of sanitized event records without credentials or RTSP URLs.
- **Clear Test Events**: Safely purges only `TEST_EVENT` records without deleting real security logs.

### E. Camera Health & Outage Detection
- Real-time FPS monitoring and frame latency tracking.
- If the camera disconnects while armed, a single `CAMERA_OFFLINE` event is recorded.
- When connection returns, a `CAMERA_RECONNECTED` event is recorded.

### F. Shop Operating Schedule
- Local background scheduler automatically arms the system after store closing (e.g., `20:00`) and disarms before opening (e.g., `09:00`).
- Manual overrides and enable/disable toggles.

---

## 3. Technology Stack

- **Backend**: Python 3.10+, FastAPI, Uvicorn, OpenCV (`opencv-python`), SQLite, Pydantic, python-dotenv
- **Frontend**: React 19, Vite, Vanilla CSS (Obsidian/Arctic Navy Security Console theme)
- **Camera Compatibility**: TP-Link Tapo C100 Wi-Fi Camera (and standard RTSP H.264 IP cameras)
- **Storage**: `guardbox.db` (SQLite) + `snapshots/` (watermarked JPEG evidence)

---

## 4. Installation & Setup (Windows)

### Prerequisites
- **Python 3.10+** installed and added to Windows PATH.
- **Node.js 18+** & npm installed.
- Camera and laptop connected to the **same Wi-Fi network** (`192.168.31.x`).

### Step 1: Camera Configuration (Tapo App)
1. Open the **TP-Link Tapo App** on your smartphone.
2. Select your **Tapo C100** camera.
3. Tap **Settings Gear** $\rightarrow$ **Advanced Settings** $\rightarrow$ **Camera Account**.
4. Create a local username (e.g. `office`) and password (e.g. `office123`).

### Step 2: Backend Setup
Open PowerShell:

```powershell
cd E:\GuardBox\backend
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Ensure `backend\.env` contains:
```ini
RTSP_URL=rtsp://office:office123@192.168.31.108:554/stream1
MOTION_SENSITIVITY=25
MIN_MOTION_AREA=500
MOTION_COOLDOWN_SECONDS=5
MOTION_PERSISTENCE_SECONDS=1.0
CAMERA_WARMUP_SECONDS=3.0
BLUR_SIZE=9
FRAME_SCALE=0.5
ENTRY_DELAY_SECONDS=15
EXIT_DELAY_SECONDS=15
SNAPSHOT_DIRECTORY=snapshots
DATABASE_PATH=guardbox.db
HOST=127.0.0.1
PORT=8000
```

> [!IMPORTANT]
> **Password URL Encoding**: If your password contains special characters (`@`, `:`, `/`, `#`, `%`), URL-encode them (e.g. `@` becomes `%40`, `:` becomes `%3A`).

### Step 3: Frontend Setup
In a second PowerShell terminal:

```powershell
cd E:\GuardBox\frontend
npm install
copy .env.example .env
```

Ensure `frontend\.env` contains:
```ini
VITE_API_BASE_URL=http://127.0.0.1:8000
```

---

## 5. How to Run

### Start Backend (Terminal 1)
```powershell
cd E:\GuardBox\backend
.venv\Scripts\activate
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### Start Frontend (Terminal 2)
```powershell
cd E:\GuardBox\frontend
npm run dev
```
Open **http://localhost:5173** in your browser.

---

## 6. Backend API Endpoints (Phase 2)

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Backend health check and ISO timestamp |
| `GET` | `/camera/status` | Sanitized camera connectivity, IP, model, and FPS |
| `GET` | `/camera/health` | Detailed camera diagnostics (FPS, latency, drop count) |
| `GET` | `/camera/stream` | Multipart MJPEG live video stream |
| `GET` | `/zones` | List all configured detection zones |
| `POST` | `/zones` | Create a new rectangular detection zone |
| `PUT` | `/zones/{id}` | Update detection zone coordinates or enabled state |
| `DELETE` | `/zones/{id}` | Delete a detection zone |
| `GET` | `/system/status` | System mode (`DISARMED`, `ARMING`, `ARMED`, `TEST_MODE`) |
| `POST` | `/system/arm` | Arm system with optional exit delay |
| `POST` | `/system/cancel-arming` | Cancel exit countdown delay |
| `POST` | `/system/disarm` | Disarm system and silence alarms |
| `POST` | `/system/test-mode` | Enter test mode |
| `POST` | `/system/exit-test-mode` | Exit test mode |
| `GET` | `/events` | Paginated & filtered security events |
| `GET` | `/events/{id}` | Retrieve individual event details |
| `POST` | `/events/{id}/acknowledge` | Mark event as `ACKNOWLEDGED` |
| `POST` | `/events/{id}/mark-false-alarm` | Mark event as `FALSE_ALARM` |
| `POST` | `/events/{id}/resolve` | Mark event as `RESOLVED` |
| `DELETE` | `/events/{id}` | Delete individual event record |
| `POST` | `/events/clear-test-data` | Purge ONLY `TEST_EVENT` records |
| `GET` | `/events/export.csv` | Export sanitized event records to CSV |
| `GET` | `/logs` | Paginated system activity audit logs |
| `GET` | `/schedule` | Get shop operating hours schedule |
| `POST` | `/schedule` | Update shop operating hours schedule |
| `GET` | `/settings` | Get safe motion parameters |
| `POST` | `/settings` | Update motion sensitivity, persistence, cooldown |
| `POST` | `/alarm/test` | Trigger simulated alarm test |
| `POST` | `/alarm/silence` | Silence active simulated alarm |

---

## 7. Manual Testing Checklist (Phase 2)

- [x] **Camera Connects**: Tapo C100 stream connects and renders in dashboard.
- [x] **Camera Disconnect / Reconnect**: Offline banner appears gracefully; reconnects automatically without server crash.
- [x] **Camera Health Metrics**: FPS counter and drop counters display in dashboard.
- [x] **Detection Zones**: Create "Showcase" and "Counter" zones; verify overlays render on video.
- [x] **Motion Inside vs Outside Zone**: Movement inside zone creates event; movement outside zone is ignored.
- [x] **Motion Persistence**: Brief single-frame noise does not trigger event; motion persisting $\ge 1.0\text{s}$ triggers event.
- [x] **Exit Delay Countdown**: Arm with 15s delay $\rightarrow$ countdown displays $\rightarrow$ transitions to ARMED after 15s.
- [x] **Cancel Arming**: Clicking Cancel during countdown aborts back to DISARMED.
- [x] **Test Mode**: Activating Test Mode records events marked `TEST_EVENT` and `TEST_MODE`.
- [x] **Event Lifecycle**: Acknowledge, Mark False Alarm, Resolve, and Delete functions update SQLite.
- [x] **Snapshot Modal**: Clicking thumbnail opens high-res evidence with timestamp & zone tags.
- [x] **CSV Export**: Clicking "Export CSV" downloads `guardbox_events_*.csv` without credentials.
- [x] **Clear Test Data**: Purges test events while preserving real security records.
- [x] **Activity Logs**: All actions (arm, disarm, zones, schedule, alarms) log to SQLite.
- [x] **Shop Schedule**: Automated arming at close and disarming at open.
- [x] **Security Isolation**: Zero RTSP credentials exposed in frontend network requests or server logs.

---

## 8. Phase 3 Roadmap: Physical Hardware & Cellular Deterrence

1. **ESP32 USB/MQTT Siren & Strobe Bridge**:
   - ESP32 microcontroller connected to laptop via USB Serial (`COM` port) or local Wi-Fi MQTT.
   - Activates an optocoupled relay connected to a **12V 110dB physical siren** and high-visibility flashing LED beacon.
2. **GSM / Cellular Modem (SIM800L / SIM7600)**:
   - Dedicated cellular modem transmitting emergency SMS messages and telephone voice dials if the store broadband/Wi-Fi is disconnected.
3. **Physical Arming Counter Keypad / RFID Reader**:
   - Physical keypad and RFID card scanner mounted near the store exit counter for quick shopkeeper authentication.
