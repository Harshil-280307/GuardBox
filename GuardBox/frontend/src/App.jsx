import React, { useState, useEffect, useCallback } from 'react';
import TopBar from './components/TopBar';
import CameraCard from './components/CameraCard';
import SystemStatus from './components/SystemStatus';
import ZoneControls from './components/ZoneControls';
import SystemControls from './components/SystemControls';
import QuickInfo from './components/QuickInfo';
import SecurityLogs from './components/SecurityLogs';
import CamerasManager from './components/CamerasManager';
import DeviceInformationCard from './components/DeviceInformationCard';
import { formatEventName, formatEventTime, formatEventDate } from './utils/formatters';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

export default function App() {
  // Navigation: 'monitor' | 'cameras' | 'settings'
  const [activeTab, setActiveTab] = useState('monitor');

  // Cameras State - Guaranteed array
  const [cameras, setCameras] = useState([]);
  const [selectedCameraId, setSelectedCameraId] = useState(1);

  // System State
  const [systemStatus, setSystemStatus] = useState({
    system_mode: 'DISARMED',
    armed: false,
    is_arming: false,
    is_test_mode: false,
    exit_countdown_remaining: 0,
    camera_connected: false,
    camera_ip: '192.168.31.108',
    camera_model: 'Tapo C100',
    camera_health: { fps: 0, warmed_up: false, reconnect_count: 0, consecutive_failures: 0 },
    cameras: [],
    motion_detection_enabled: false,
    last_event_timestamp: null,
    alarm_simulation: { is_active: false, triggered_at: null, trigger_reason: null, is_simulation: true }
  });

  // Detection Zones State (for selected camera)
  const [savedZones, setSavedZones] = useState([]);
  const [selectedZoneId, setSelectedZoneId] = useState(null);
  const [draftPoints, setDraftPoints] = useState([]);
  const [isDraftClosed, setIsDraftClosed] = useState(false);
  const [isDrawingMode, setIsDrawingMode] = useState(false);
  const [isEditingMode, setIsEditingMode] = useState(false);
  const [validationError, setValidationError] = useState(null);

  // Recent Events & Active Security Alert State
  const [recentEvents, setRecentEvents] = useState([]);
  const [activeAlert, setActiveAlert] = useState(null);

  // Settings State
  const [settings, setSettings] = useState({
    motion_sensitivity: 35,
    min_motion_area: 200,
    motion_cooldown_seconds: 3.0,
    motion_persistence_seconds: 0.5,
    camera_warmup_seconds: 3.0,
    blur_size: 5,
    frame_scale: 0.5,
    entry_delay_seconds: 15,
    exit_delay_seconds: 15
  });

  const [schedule, setSchedule] = useState({
    enabled: false,
    opening_time: '09:00',
    closing_time: '20:00',
    auto_arm: true,
    auto_disarm: true
  });

  // UI State
  const [loading, setLoading] = useState(false);
  const [toastMsg, setToastMsg] = useState(null);
  const [selectedSnapshot, setSelectedSnapshot] = useState(null);

  const showToast = (msg) => {
    setToastMsg(msg);
    setTimeout(() => setToastMsg(null), 3500);
  };

  // Safe camera array handling to prevent any .find/.filter crash
  const safeCameras = Array.isArray(cameras) ? cameras : [];

  // Active camera object
  const activeCamera = safeCameras.find((c) => c.id === selectedCameraId) || safeCameras[0] || {
    id: 1,
    name: 'Main Shop Camera',
    brand: 'TP-Link',
    model: 'Tapo C100',
    camera_ip: '192.168.31.108',
    status: 'offline',
    connected: false
  };

  // --------------------------------------------------------------------------
  // Data Fetching
  // --------------------------------------------------------------------------

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/system/status`);
      if (res.ok) {
        const data = await res.json();
        setSystemStatus(data);
      }
    } catch {
      // Backend temporarily offline
    }
  }, []);

  const fetchCameras = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/cameras`);
      if (res.ok) {
        const list = await res.json();
        if (Array.isArray(list)) {
          setCameras(list);
          // If selectedCameraId not in list, fallback to first
          if (list.length > 0 && !list.some((c) => c.id === selectedCameraId)) {
            setSelectedCameraId(list[0].id);
          }
        } else {
          setCameras([]);
        }
      }
    } catch {
      // Network error
    }
  }, [selectedCameraId]);

  const fetchZonesForCamera = useCallback(async (camId) => {
    if (!camId) return;
    try {
      const res = await fetch(`${API_BASE}/cameras/${camId}/zones`);
      if (res.ok) {
        const list = await res.json();
        setSavedZones(Array.isArray(list) ? list : []);
      }
    } catch {
      // Network error
    }
  }, []);

  const fetchRecentEvents = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/events?page=1&page_size=10`);
      if (res.ok) {
        const data = await res.json();
        setRecentEvents(data.items || []);
      }
    } catch {
      // Network error
    }
  }, []);

  const fetchActiveAlert = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/alerts/active`);
      if (res.ok) {
        const data = await res.json();
        const incomingAlert = data.active_alert || null;
        if (incomingAlert) {
          setActiveAlert(incomingAlert);
        } else {
          // Do not erase an active alert if still within its 60s visibility period
          setActiveAlert((prev) => {
            if (!prev) return null;
            const created = prev.created_at ? new Date(prev.created_at).getTime() : 0;
            const expires = prev.expires_at ? new Date(prev.expires_at).getTime() : (created + 60000);
            const now = Date.now();
            if (expires > now) {
              return prev;
            }
            return null;
          });
        }
      }
    } catch {
      // Network error: preserve current active alert if within visibility window
    }
  }, []);

  const fetchSettingsAndSchedule = useCallback(async () => {
    try {
      const [setRes, schRes] = await Promise.all([
        fetch(`${API_BASE}/settings`),
        fetch(`${API_BASE}/schedule`)
      ]);
      if (setRes.ok) setSettings(await setRes.json());
      if (schRes.ok) setSchedule(await schRes.json());
    } catch {
      // Network error
    }
  }, []);

  // 60-second Active Alert Expiration Watcher for Windows Dashboard
  useEffect(() => {
    const timer = setInterval(() => {
      setActiveAlert((prev) => {
        if (!prev) return null;
        const created = prev.created_at ? new Date(prev.created_at).getTime() : 0;
        const expires = prev.expires_at ? new Date(prev.expires_at).getTime() : (created + 60000);
        if (Date.now() >= expires) {
          return null;
        }
        return prev;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  // Polling Effect
  useEffect(() => {
    fetchStatus();
    fetchCameras();
    fetchZonesForCamera(selectedCameraId);
    fetchRecentEvents();
    fetchActiveAlert();

    const interval = setInterval(() => {
      fetchStatus();
      fetchCameras();
      fetchActiveAlert();
      if (activeTab === 'monitor') {
        fetchRecentEvents();
        fetchZonesForCamera(selectedCameraId);
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [fetchStatus, fetchCameras, fetchZonesForCamera, fetchRecentEvents, fetchActiveAlert, selectedCameraId, activeTab]);

  // Tab switch load
  useEffect(() => {
    if (activeTab === 'settings') {
      fetchSettingsAndSchedule();
    }
  }, [activeTab, fetchSettingsAndSchedule]);

  // --------------------------------------------------------------------------
  // Camera Selection & Actions
  // --------------------------------------------------------------------------

  const handleSelectCamera = (camId) => {
    setSelectedCameraId(camId);
    setDraftPoints([]);
    setIsDraftClosed(false);
    setIsDrawingMode(false);
    setIsEditingMode(false);
    setSelectedZoneId(null);
    fetchZonesForCamera(camId);
  };

  const handleSelectCameraForMonitor = (camId) => {
    handleSelectCamera(camId);
    setActiveTab('monitor');
  };

  const handleAddCamera = async (camData) => {
    try {
      setLoading(true);
      const res = await fetch(`${API_BASE}/cameras`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(camData)
      });
      if (res.ok) {
        const created = await res.json();
        showToast(`Camera '${created.name}' added successfully`);
        fetchCameras();
        setSelectedCameraId(created.id);
      } else {
        const err = await res.json();
        showToast(`Failed to add camera: ${err.detail || 'Error'}`);
      }
    } catch {
      showToast('Network error adding camera');
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateCamera = async (camId, camData) => {
    try {
      setLoading(true);
      const res = await fetch(`${API_BASE}/cameras/${camId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(camData)
      });
      if (res.ok) {
        showToast('Camera profile updated');
        fetchCameras();
      } else {
        showToast('Failed to update camera');
      }
    } catch {
      showToast('Network error updating camera');
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteCamera = async (camId) => {
    const targetCam = safeCameras.find((c) => c.id === camId);
    const camName = targetCam ? targetCam.name : `Camera #${camId}`;
    if (!window.confirm(`Are you sure you want to delete camera '${camName}' and all its detection zones?`)) {
      return;
    }
    try {
      setLoading(true);
      const res = await fetch(`${API_BASE}/cameras/${camId}`, { method: 'DELETE' });
      if (res.ok) {
        showToast(`Camera '${camName}' deleted successfully`);
        const camRes = await fetch(`${API_BASE}/cameras`);
        if (camRes.ok) {
          const list = await camRes.json();
          const safeList = Array.isArray(list) ? list : [];
          setCameras(safeList);
          if (selectedCameraId === camId) {
            if (safeList.length > 0) {
              setSelectedCameraId(safeList[0].id);
              fetchZonesForCamera(safeList[0].id);
            } else {
              setSelectedCameraId(1);
            }
          }
        }
      } else {
        const err = await res.json().catch(() => ({}));
        showToast(`Failed to delete camera: ${err.detail || 'Error'}`);
      }
    } catch {
      showToast('Failed to delete camera due to network error');
    } finally {
      setLoading(false);
    }
  };

  const handleToggleCamera = async (camId, enabled) => {
    try {
      const res = await fetch(`${API_BASE}/cameras/${camId}/toggle?enabled=${enabled}`, {
        method: 'POST'
      });
      if (res.ok) {
        showToast(enabled ? 'Camera enabled' : 'Camera disabled');
        fetchCameras();
      } else {
        showToast('Failed to toggle camera state');
      }
    } catch {
      showToast('Failed to toggle camera state due to network error');
    }
  };

  // --------------------------------------------------------------------------
  // Detection Zone Actions
  // --------------------------------------------------------------------------

  const handleFinishDraft = () => {
    if (draftPoints.length < 3) {
      setValidationError('Polygon zone must have at least 3 points.');
    } else {
      setValidationError(null);
    }
  };

  const handleSaveZone = async ({ id, name, points }) => {
    const pts = points || draftPoints;
    if (!pts || pts.length < 3) {
      setValidationError('Polygon zone must have at least 3 points.');
      return;
    }
    const zoneName = (name && name.trim()) || `Zone ${savedZones.length + 1}`;

    try {
      setLoading(true);
      const isUpdate = Boolean(id);
      const url = isUpdate
        ? `${API_BASE}/zones/${id}`
        : `${API_BASE}/cameras/${selectedCameraId}/zones`;
      const method = isUpdate ? 'PUT' : 'POST';

      const payload = {
        name: zoneName,
        points: pts,
        enabled: true
      };
      if (!isUpdate) {
        payload.camera_id = selectedCameraId;
        payload.color = '#FF3B30';
      }

      const res = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (res.ok) {
        const result = await res.json();
        setDraftPoints([]);
        setIsDraftClosed(false);
        setIsDrawingMode(false);
        setIsEditingMode(false);
        setValidationError(null);
        showToast(isUpdate ? `Zone '${result.name || zoneName}' updated` : `Zone '${result.name || zoneName}' saved`);
        fetchZonesForCamera(selectedCameraId);
        fetchRecentEvents();
      } else {
        const err = await res.json();
        showToast(`Failed to save zone: ${err.detail || 'Error'}`);
      }
    } catch {
      showToast('Network error saving detection zone');
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteZone = async (zoneId) => {
    try {
      setLoading(true);
      const res = await fetch(`${API_BASE}/zones/${zoneId}`, { method: 'DELETE' });
      if (res.ok) {
        showToast('Detection zone deleted');
        if (selectedZoneId === zoneId) setSelectedZoneId(null);
        fetchZonesForCamera(selectedCameraId);
      }
    } catch {
      showToast('Failed to delete detection zone');
    } finally {
      setLoading(false);
    }
  };

  const handleToggleZone = async (zoneId) => {
    try {
      const targetZone = savedZones.find((z) => z.id === zoneId);
      const nextState = targetZone ? !targetZone.enabled : undefined;
      const url = nextState !== undefined
        ? `${API_BASE}/zones/${zoneId}/toggle?enabled=${nextState}`
        : `${API_BASE}/zones/${zoneId}/toggle`;
      const res = await fetch(url, { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        const finalEnabled = data.enabled !== undefined ? data.enabled : nextState;
        setSavedZones((prev) =>
          prev.map((z) => (z.id === zoneId ? { ...z, enabled: finalEnabled } : z))
        );
        showToast(`Zone ${finalEnabled ? 'enabled' : 'disabled'}`);
        fetchZonesForCamera(selectedCameraId);
      } else {
        showToast('Failed to toggle detection zone');
      }
    } catch {
      showToast('Failed to toggle detection zone');
    }
  };

  const handleClearAllZones = async () => {
    if (!window.confirm('Clear all detection zones for this camera?')) return;
    try {
      setLoading(true);
      const res = await fetch(`${API_BASE}/cameras/${selectedCameraId}/zones`, { method: 'DELETE' });
      if (res.ok) {
        setSavedZones([]);
        setDraftPoints([]);
        setIsDraftClosed(false);
        setIsDrawingMode(false);
        setIsEditingMode(false);
        setSelectedZoneId(null);
        showToast('All detection zones cleared for this camera');
      }
    } catch {
      showToast('Failed to clear zones');
    } finally {
      setLoading(false);
    }
  };

  const handleCancelDraft = () => {
    setDraftPoints([]);
    setIsDraftClosed(false);
    setIsDrawingMode(false);
    setIsEditingMode(false);
    setValidationError(null);
  };

  // --------------------------------------------------------------------------
  // System Controls Actions
  // --------------------------------------------------------------------------

  const handleArmSystem = async () => {
    try {
      setLoading(true);
      const res = await fetch(`${API_BASE}/system/arm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ exit_delay_seconds: settings.exit_delay_seconds || 15 })
      });
      if (res.ok) {
        showToast('System arming initiated');
        fetchStatus();
        fetchRecentEvents();
      }
    } catch {
      showToast('Failed to arm system');
    } finally {
      setLoading(false);
    }
  };

  const handleCancelArming = async () => {
    try {
      setLoading(true);
      const res = await fetch(`${API_BASE}/system/cancel-arming`, { method: 'POST' });
      if (res.ok) {
        showToast('Arming countdown cancelled');
        fetchStatus();
      }
    } catch {
      showToast('Failed to cancel arming');
    } finally {
      setLoading(false);
    }
  };

  const handleDisarmSystem = async () => {
    try {
      setLoading(true);
      const res = await fetch(`${API_BASE}/system/disarm`, { method: 'POST' });
      if (res.ok) {
        showToast('System disarmed');
        fetchStatus();
        fetchRecentEvents();
      }
    } catch {
      showToast('Failed to disarm system');
    } finally {
      setLoading(false);
    }
  };

  const handleTestAlarm = async () => {
    try {
      setLoading(true);
      const res = await fetch(`${API_BASE}/alarm/test`, { method: 'POST' });
      if (res.ok) {
        showToast('Simulated alarm triggered (No physical siren)');
        fetchStatus();
        fetchRecentEvents();
      }
    } catch {
      showToast('Failed to trigger test alarm');
    } finally {
      setLoading(false);
    }
  };

  const handleSilenceAlarm = async () => {
    try {
      setLoading(true);
      const res = await fetch(`${API_BASE}/alarm/silence`, { method: 'POST' });
      if (res.ok) {
        showToast('Simulated alarm silenced');
        fetchStatus();
      }
    } catch {
      showToast('Failed to silence alarm');
    } finally {
      setLoading(false);
    }
  };

  const handleAcknowledgeEvent = async (eventId) => {
    try {
      const res = await fetch(`${API_BASE}/events/${eventId}/acknowledge`, { method: 'POST' });
      if (res.ok) {
        showToast(`Event #${eventId} acknowledged`);
        fetchRecentEvents();
      }
    } catch {
      showToast('Failed to acknowledge event');
    }
  };

  // --------------------------------------------------------------------------
  // Settings Actions
  // --------------------------------------------------------------------------

  const handleSaveSettings = async (e) => {
    e.preventDefault();
    try {
      setLoading(true);
      const res = await fetch(`${API_BASE}/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings)
      });
      if (res.ok) {
        showToast('Detection parameters updated');
      }
    } catch {
      showToast('Failed to update settings');
    } finally {
      setLoading(false);
    }
  };

  const handleSaveSchedule = async (e) => {
    e.preventDefault();
    try {
      setLoading(true);
      const res = await fetch(`${API_BASE}/schedule`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(schedule)
      });
      if (res.ok) {
        showToast('Shop schedule saved');
      }
    } catch {
      showToast('Failed to update schedule');
    } finally {
      setLoading(false);
    }
  };

  // --------------------------------------------------------------------------
  // Render Main Layout
  // --------------------------------------------------------------------------

  return (
    <div className="app-layout">
      {/* Top Navigation */}
      <TopBar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        cameras={safeCameras}
        systemStatus={systemStatus}
      />

      <main className="main-content-wrap">
        {/* TAB 1: LIVE MONITOR */}
        {activeTab === 'monitor' && (
          <div className="dashboard-grid">
            {/* Left Column: Live Camera + Recent Events */}
            <div className="dashboard-col-left">
              <CameraCard
                apiBase={API_BASE}
                activeCamera={activeCamera}
                cameras={safeCameras}
                onSelectCamera={handleSelectCamera}
                systemStatus={systemStatus}
                isDrawingMode={isDrawingMode}
                isEditingMode={isEditingMode}
                draftPoints={draftPoints}
                setDraftPoints={setDraftPoints}
                isDraftClosed={isDraftClosed}
                setIsDraftClosed={setIsDraftClosed}
                savedZones={savedZones}
                selectedZoneId={selectedZoneId}
                onSelectZone={(z) => setSelectedZoneId(z.id)}
                onFinishDraft={handleFinishDraft}
              />

              <SecurityLogs
                events={recentEvents}
                onAcknowledge={handleAcknowledgeEvent}
                onViewSnapshot={(ev) => setSelectedSnapshot(ev)}
                compact={true}
              />
            </div>

            {/* Right Column: Status + Detection Areas + System Controls + Quick Info */}
            <div className="dashboard-col-right">
              <SystemStatus
                systemStatus={systemStatus}
                activeCamera={activeCamera}
                savedZones={savedZones}
                activeAlert={activeAlert}
              />

              <ZoneControls
                isDrawingMode={isDrawingMode}
                setIsDrawingMode={setIsDrawingMode}
                isEditingMode={isEditingMode}
                setIsEditingMode={setIsEditingMode}
                draftPoints={draftPoints}
                setDraftPoints={setDraftPoints}
                isDraftClosed={isDraftClosed}
                setIsDraftClosed={setIsDraftClosed}
                savedZones={savedZones}
                selectedZoneId={selectedZoneId}
                onSelectZone={(z) => setSelectedZoneId(z.id)}
                onSaveZone={handleSaveZone}
                onDeleteZone={handleDeleteZone}
                onToggleZone={handleToggleZone}
                onClearAllZones={handleClearAllZones}
                onCancelDraft={handleCancelDraft}
                validationError={validationError}
                loading={loading}
              />

              <SystemControls
                systemStatus={systemStatus}
                onArm={handleArmSystem}
                onCancelArming={handleCancelArming}
                onDisarm={handleDisarmSystem}
                onTestAlarm={handleTestAlarm}
                onSilenceAlarm={handleSilenceAlarm}
                loading={loading}
              />

              <QuickInfo
                activeCamera={activeCamera}
                systemStatus={systemStatus}
                savedZones={savedZones}
              />
            </div>
          </div>
        )}

        {/* TAB 2: CAMERAS MANAGEMENT */}
        {activeTab === 'cameras' && (
          <CamerasManager
            cameras={safeCameras}
            onSelectCameraForMonitor={handleSelectCameraForMonitor}
            onAddCamera={handleAddCamera}
            onUpdateCamera={handleUpdateCamera}
            onDeleteCamera={handleDeleteCamera}
            onToggleCamera={handleToggleCamera}
            apiBase={API_BASE}
            loading={loading}
          />
        )}

        {/* TAB 3: SETTINGS */}
        {activeTab === 'settings' && (
          <div className="dashboard-grid">
            {/* Device Identity & Veronic Protected Management (Phase 5.9) */}
            <DeviceInformationCard apiBase={API_BASE} showToast={showToast} />

            {/* Shop Schedule */}
            <div className="dashboard-card">
              <div className="card-header">
                <h3 className="card-title">Shop Schedule & Auto-Arm</h3>
              </div>
              <div className="card-body">
                <form onSubmit={handleSaveSchedule} className="settings-form-grid">
                  <div className="form-group">
                    <label className="form-label">Auto Schedule Enabled</label>
                    <select
                      className="form-input"
                      value={schedule.enabled ? 'true' : 'false'}
                      onChange={(e) => setSchedule({ ...schedule, enabled: e.target.value === 'true' })}
                    >
                      <option value="false">Disabled</option>
                      <option value="true">Enabled</option>
                    </select>
                  </div>

                  <div className="form-group">
                    <label className="form-label">Opening Time (HH:MM)</label>
                    <input
                      type="time"
                      className="form-input"
                      value={schedule.opening_time}
                      onChange={(e) => setSchedule({ ...schedule, opening_time: e.target.value })}
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">Closing Time (HH:MM)</label>
                    <input
                      type="time"
                      className="form-input"
                      value={schedule.closing_time}
                      onChange={(e) => setSchedule({ ...schedule, closing_time: e.target.value })}
                    />
                  </div>

                  <div className="form-group" style={{ gridColumn: '1 / -1', marginTop: '10px' }}>
                    <button type="submit" className="btn btn-primary" disabled={loading}>
                      Save Schedule
                    </button>
                  </div>
                </form>
              </div>
            </div>

            {/* Global Detection Parameters */}
            <div className="dashboard-card">
              <div className="card-header">
                <h3 className="card-title">Default Detection Parameters</h3>
              </div>
              <div className="card-body">
                <form onSubmit={handleSaveSettings} className="settings-form-grid">
                  <div className="form-group">
                    <label className="form-label">Sensitivity ({settings.motion_sensitivity})</label>
                    <input
                      type="range"
                      min="5"
                      max="100"
                      className="form-range"
                      value={settings.motion_sensitivity}
                      onChange={(e) => setSettings({ ...settings, motion_sensitivity: Number(e.target.value) })}
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">Min Motion Area ({settings.min_motion_area} px)</label>
                    <input
                      type="number"
                      className="form-input"
                      value={settings.min_motion_area}
                      onChange={(e) => setSettings({ ...settings, min_motion_area: Number(e.target.value) })}
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">Motion Cooldown ({settings.motion_cooldown_seconds}s)</label>
                    <input
                      type="number"
                      step="0.5"
                      className="form-input"
                      value={settings.motion_cooldown_seconds}
                      onChange={(e) => setSettings({ ...settings, motion_cooldown_seconds: Number(e.target.value) })}
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">Exit Delay ({settings.exit_delay_seconds}s)</label>
                    <input
                      type="number"
                      className="form-input"
                      value={settings.exit_delay_seconds}
                      onChange={(e) => setSettings({ ...settings, exit_delay_seconds: Number(e.target.value) })}
                    />
                  </div>

                  <div className="form-group" style={{ gridColumn: '1 / -1', marginTop: '10px' }}>
                    <button type="submit" className="btn btn-primary" disabled={loading}>
                      Save Detection Parameters
                    </button>
                  </div>
                </form>
              </div>
            </div>
          </div>
        )}
      </main>

      {/* Snapshot Preview Modal */}
      {selectedSnapshot && (
        <div className="modal-overlay" onClick={() => setSelectedSnapshot(null)}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h4 className="card-title">
                Event Snapshot — {formatEventName(selectedSnapshot.event_type)} (#{selectedSnapshot.id})
              </h4>
              <button
                type="button"
                className="btn-table-icon"
                onClick={() => setSelectedSnapshot(null)}
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="modal-body">
              <img
                src={`${API_BASE}/${selectedSnapshot.snapshot_path}`}
                alt="Motion Snapshot"
                className="snapshot-preview-img"
              />
              <div style={{ marginTop: '12px', display: 'flex', justifyContent: 'space-between', fontSize: '12px', color: 'var(--glacier-blue)' }}>
                <span>Camera: {selectedSnapshot.camera_name || 'Main Shop Camera'}</span>
                <span>Area: {selectedSnapshot.zone_name || 'Main Area'}</span>
                <span>Timestamp: {formatEventTime(selectedSnapshot.timestamp)} {formatEventDate(selectedSnapshot.timestamp)}</span>
              </div>
            </div>
            <div className="modal-footer">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setSelectedSnapshot(null)}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Toast Notice */}
      {toastMsg && (
        <div className="toast-notice">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ width: 16, height: 16, color: '#10B981' }}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
          </svg>
          <span>{toastMsg}</span>
        </div>
      )}
    </div>
  );
}
