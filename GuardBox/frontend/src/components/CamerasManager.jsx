import React, { useState } from 'react';

export default function CamerasManager({
  cameras = [],
  onSelectCameraForMonitor,
  onAddCamera,
  onUpdateCamera,
  onDeleteCamera,
  onToggleCamera,
  apiBase,
  loading
}) {
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingCamera, setEditingCamera] = useState(null);

  // Per-camera stream error tracking & retry key
  const [streamErrors, setStreamErrors] = useState({});
  const [retryTokens, setRetryTokens] = useState({});

  // Form State
  const [formData, setFormData] = useState({
    name: '',
    brand: 'TP-Link',
    model: 'Tapo C100',
    rtsp_url: '',
    enabled: true
  });

  const [testResult, setTestResult] = useState(null);
  const [testingConnection, setTestingConnection] = useState(false);

  // Safe camera array guard
  const safeCameras = Array.isArray(cameras) ? cameras : [];

  // Summary Metrics
  const totalCameras = safeCameras.length;
  const onlineCameras = safeCameras.filter((c) => Boolean(c.enabled !== false && (c.connected || c.status === 'online'))).length;
  const offlineCameras = safeCameras.filter((c) => Boolean(c.enabled !== false && !c.connected && c.status !== 'online')).length;
  const activeCameras = safeCameras.filter((c) => c.enabled !== false).length;

  const handleStreamError = (camId) => {
    setStreamErrors((prev) => ({ ...prev, [camId]: true }));
  };

  const handleStreamLoad = (camId) => {
    setStreamErrors((prev) => ({ ...prev, [camId]: false }));
  };

  const handleRetryStream = (camId) => {
    setStreamErrors((prev) => ({ ...prev, [camId]: false }));
    setRetryTokens((prev) => ({ ...prev, [camId]: Date.now() }));
  };

  const openAddModal = () => {
    setEditingCamera(null);
    setFormData({
      name: `Camera ${safeCameras.length + 1}`,
      brand: 'TP-Link',
      model: 'Tapo C100',
      rtsp_url: '',
      enabled: true
    });
    setTestResult(null);
    setIsModalOpen(true);
  };

  const openEditModal = (cam) => {
    setEditingCamera(cam);
    setFormData({
      name: cam.name,
      brand: cam.brand || 'TP-Link',
      model: cam.model || 'Tapo C100',
      rtsp_url: '', // Leave blank unless user wishes to update
      enabled: Boolean(cam.enabled !== false)
    });
    setTestResult(null);
    setIsModalOpen(true);
  };

  const handleTest = async () => {
    if (!formData.rtsp_url || !formData.rtsp_url.trim()) {
      setTestResult({ success: false, message: 'Please enter an RTSP URL to test.' });
      return;
    }
    setTestingConnection(true);
    setTestResult(null);
    try {
      const res = await fetch(`${apiBase}/cameras/test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rtsp_url: formData.rtsp_url.trim() })
      });
      const data = await res.json();
      setTestResult(data);
    } catch {
      setTestResult({ success: false, message: 'Network error communicating with backend server.' });
    } finally {
      setTestingConnection(false);
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!formData.name.trim()) return;

    if (editingCamera) {
      onUpdateCamera(editingCamera.id, formData);
    } else {
      if (!formData.rtsp_url.trim()) {
        setTestResult({ success: false, message: 'RTSP URL is required to add a camera.' });
        return;
      }
      onAddCamera(formData);
    }
    setIsModalOpen(false);
  };

  return (
    <div className="cameras-mgmt-page">
      {/* 1. Page Header */}
      <div className="cameras-header-row">
        <div className="cameras-header-text">
          <h2 className="section-title">Camera Management</h2>
          <p className="section-subtitle">
            Monitor and manage all connected security cameras.
          </p>
        </div>
        <button
          type="button"
          className="btn btn-primary btn-add-cam"
          onClick={openAddModal}
          disabled={loading}
        >
          <svg className="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
          <span>Add Camera</span>
        </button>
      </div>

      {/* 2. Summary Metric Cards */}
      <div className="cameras-summary-grid">
        <div className="summary-stat-card">
          <div className="stat-card-icon-wrap icon-blue">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 10.5l4.72-4.72a.75.75 0 011.28.53v11.38a.75.75 0 01-1.28.53l-4.72-4.72M4.5 18.75h9a2.25 2.25 0 002.25-2.25v-9a2.25 2.25 0 00-2.25-2.25h-9A2.25 2.25 0 002.25 7.5v9a2.25 2.25 0 002.25 2.25z" />
            </svg>
          </div>
          <div className="stat-card-content">
            <span className="stat-card-val">{totalCameras}</span>
            <span className="stat-card-lbl">Total Cameras</span>
          </div>
        </div>

        <div className="summary-stat-card">
          <div className="stat-card-icon-wrap icon-green">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <div className="stat-card-content">
            <span className="stat-card-val val-green">{onlineCameras}</span>
            <span className="stat-card-lbl">Online</span>
          </div>
        </div>

        <div className="summary-stat-card">
          <div className="stat-card-icon-wrap icon-red">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
            </svg>
          </div>
          <div className="stat-card-content">
            <span className="stat-card-val val-red">{offlineCameras}</span>
            <span className="stat-card-lbl">Offline</span>
          </div>
        </div>

        <div className="summary-stat-card">
          <div className="stat-card-icon-wrap icon-cyan">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z" />
            </svg>
          </div>
          <div className="stat-card-content">
            <span className="stat-card-val val-cyan">{activeCameras}</span>
            <span className="stat-card-lbl">Active</span>
          </div>
        </div>
      </div>

      {/* 3. Empty State or Camera List */}
      {safeCameras.length === 0 ? (
        <div className="dashboard-card cameras-empty-card">
          <div className="empty-icon-box">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 10.5l4.72-4.72a.75.75 0 011.28.53v11.38a.75.75 0 01-1.28.53l-4.72-4.72M4.5 18.75h9a2.25 2.25 0 002.25-2.25v-9a2.25 2.25 0 00-2.25-2.25h-9A2.25 2.25 0 002.25 7.5v9a2.25 2.25 0 002.25 2.25z" />
              <line x1="3" y1="3" x2="21" y2="21" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
          </div>
          <h3 className="empty-title">No cameras configured</h3>
          <p className="empty-subtitle">Connect your first security camera to start monitoring.</p>
          <button type="button" className="btn btn-primary" onClick={openAddModal}>
            <svg className="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
            </svg>
            <span>Add Camera</span>
          </button>
        </div>
      ) : (
        <div className="cameras-list-container">
          {safeCameras.map((cam) => {
            const isEnabled = cam.enabled !== false;
            const isOnline = isEnabled && Boolean(cam.connected || cam.status === 'online');
            const hasStreamError = Boolean(streamErrors[cam.id]);
            const retryToken = retryTokens[cam.id] || '';
            const streamUrl = `${apiBase}/cameras/${cam.id}/stream${retryToken ? `?t=${retryToken}` : ''}`;

            return (
              <div key={cam.id} className="camera-panel-card">
                <div className="camera-panel-body">
                  {/* Left Column: Live Camera Preview */}
                  <div className="camera-preview-col">
                    <div className="camera-preview-box">
                      {isOnline && !hasStreamError ? (
                        <>
                          <img
                            src={streamUrl}
                            alt={`Preview ${cam.name}`}
                            className="camera-preview-stream"
                            onError={() => handleStreamError(cam.id)}
                            onLoad={() => handleStreamLoad(cam.id)}
                          />
                          <div className="preview-live-tag">
                            <span className="live-dot-pulse"></span>
                            <span>LIVE</span>
                          </div>
                        </>
                      ) : (
                        <div className="camera-preview-offline">
                          <div className="offline-symbol-wrap">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                              <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 10.5l4.72-4.72a.75.75 0 011.28.53v11.38a.75.75 0 01-1.28.53l-4.72-4.72M4.5 18.75h9a2.25 2.25 0 002.25-2.25v-9a2.25 2.25 0 00-2.25-2.25h-9A2.25 2.25 0 002.25 7.5v9a2.25 2.25 0 002.25 2.25z" />
                              <line x1="2" y1="2" x2="22" y2="22" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                            </svg>
                          </div>
                          <span className="offline-title">
                            {!isEnabled ? 'CAMERA DISABLED' : 'CAMERA OFFLINE'}
                          </span>
                          <span className="offline-desc">
                            {!isEnabled ? 'Enable camera to start live preview' : 'Unable to load stream'}
                          </span>
                          {isEnabled && (
                            <button
                              type="button"
                              className="btn btn-secondary btn-xs btn-retry"
                              onClick={() => handleRetryStream(cam.id)}
                            >
                              <svg className="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99" />
                              </svg>
                              <span>Retry</span>
                            </button>
                          )}
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Right Column: Camera Details & Scannable Specs */}
                  <div className="camera-details-col">
                    {/* Header */}
                    <div className="cam-details-header">
                      <div className="cam-title-meta">
                        <h3 className="cam-main-name">{cam.name}</h3>
                        <span className="cam-model-tag">
                          {cam.brand || 'TP-Link'} {cam.model || 'Tapo C100'}
                        </span>
                      </div>

                      <div className={`cam-status-pill ${!isEnabled ? 'disabled' : isOnline ? 'online' : 'offline'}`}>
                        <span className="status-indicator-dot"></span>
                        <span>{!isEnabled ? 'DISABLED' : isOnline ? 'ONLINE' : 'OFFLINE'}</span>
                      </div>
                    </div>

                    {/* Scannable Spec Items Grid */}
                    <div className="cam-spec-grid-v2">
                      <div className="cam-spec-item">
                        <span className="spec-item-label">IP ADDRESS</span>
                        <span className="spec-item-value font-mono">
                          {cam.camera_ip || cam.ip_address || '192.168.31.108'}
                        </span>
                      </div>

                      <div className="cam-spec-item">
                        <span className="spec-item-label">DETECTION AREA</span>
                        <span className="spec-item-value">
                          {cam.zone_count !== undefined ? `${cam.zone_count} configured` : '0 configured'}
                        </span>
                      </div>

                      <div className="cam-spec-item">
                        <span className="spec-item-label">FRAME RATE</span>
                        <span className="spec-item-value font-mono">
                          {cam.fps !== undefined ? `${cam.fps} FPS` : (isOnline ? '15.0 FPS' : '0.0 FPS')}
                        </span>
                      </div>

                      <div className="cam-spec-item">
                        <span className="spec-item-label">STATUS</span>
                        <span className={`spec-item-value ${isEnabled ? 'val-green' : 'val-neutral'}`}>
                          {isEnabled ? 'Enabled' : 'Disabled'}
                        </span>
                      </div>
                    </div>

                    {/* Action Buttons Row */}
                    <div className="cam-actions-footer">
                      <button
                        type="button"
                        className="btn btn-primary btn-sm btn-view-monitor"
                        onClick={() => onSelectCameraForMonitor(cam.id)}
                      >
                        <svg className="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
                          <line x1="8" y1="21" x2="16" y2="21" />
                          <line x1="12" y1="17" x2="12" y2="21" />
                        </svg>
                        <span>View in Monitor</span>
                      </button>

                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={() => openEditModal(cam)}
                      >
                        <svg className="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0115.75 21H5.25A2.25 2.25 0 013 18.75V8.25A2.25 2.25 0 015.25 6H10" />
                        </svg>
                        <span>Edit</span>
                      </button>

                      <button
                        type="button"
                        className={`btn btn-sm ${isEnabled ? 'btn-outline-warning' : 'btn-green'}`}
                        onClick={() => onToggleCamera(cam.id, !isEnabled)}
                      >
                        {isEnabled ? 'Disable' : 'Enable'}
                      </button>

                      <button
                        type="button"
                        className="btn btn-danger btn-sm"
                        onClick={() => onDeleteCamera(cam.id)}
                        title="Delete camera profile"
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* 4. Add / Edit Camera Modal */}
      {isModalOpen && (
        <div className="modal-overlay" onClick={() => setIsModalOpen(false)}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h4 className="card-title">
                {editingCamera ? `Edit Camera #${editingCamera.id}` : 'Add New Camera'}
              </h4>
              <button
                type="button"
                className="btn-table-icon"
                onClick={() => setIsModalOpen(false)}
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <form onSubmit={handleSubmit}>
              <div className="modal-body">
                <div className="form-group">
                  <label className="form-label">Camera Label / Location</label>
                  <input
                    type="text"
                    className="form-input"
                    placeholder="e.g. Main Shop Camera, Display Counter, Safe Vault"
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    required
                  />
                </div>

                <div className="form-grid-2">
                  <div className="form-group">
                    <label className="form-label">Brand</label>
                    <input
                      type="text"
                      className="form-input"
                      value={formData.brand}
                      onChange={(e) => setFormData({ ...formData, brand: e.target.value })}
                      required
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Model</label>
                    <input
                      type="text"
                      className="form-input"
                      value={formData.model}
                      onChange={(e) => setFormData({ ...formData, model: e.target.value })}
                      required
                    />
                  </div>
                </div>

                <div className="form-group">
                  <label className="form-label">
                    RTSP Stream URL {editingCamera ? '(Leave blank to keep existing URL)' : ''}
                  </label>
                  <input
                    type="text"
                    className="form-input"
                    placeholder="rtsp://username:password@192.168.31.108:554/stream1"
                    value={formData.rtsp_url}
                    onChange={(e) => setFormData({ ...formData, rtsp_url: e.target.value })}
                    required={!editingCamera}
                  />
                  <span className="field-hint">
                    Credentials are encrypted in local SQLite and never sent to browser clients.
                  </span>
                </div>

                {/* Test Connection Button */}
                <div className="test-connection-row">
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={handleTest}
                    disabled={testingConnection || !formData.rtsp_url}
                  >
                    {testingConnection ? 'Testing Connection...' : 'Test RTSP Connection'}
                  </button>

                  {testResult && (
                    <span className={`test-result-badge ${testResult.success ? 'success' : 'failure'}`}>
                      {testResult.message}
                    </span>
                  )}
                </div>

                <div className="form-checkbox-row">
                  <label className="checkbox-label">
                    <input
                      type="checkbox"
                      checked={formData.enabled}
                      onChange={(e) => setFormData({ ...formData, enabled: e.target.checked })}
                    />
                    <span>Enable camera for live monitoring and motion detection</span>
                  </label>
                </div>
              </div>

              <div className="modal-footer">
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setIsModalOpen(false)}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={loading}
                >
                  {editingCamera ? 'Save Changes' : 'Add Camera'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
