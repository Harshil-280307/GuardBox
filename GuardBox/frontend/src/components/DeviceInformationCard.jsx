import React, { useState, useEffect } from 'react';

export default function DeviceInformationCard({ apiBase, showToast }) {
  const [deviceInfo, setDeviceInfo] = useState({
    device_id: 'guardbox-shop-f20424b4',
    shop_id: 'SHOP-RK-001',
    shop_name: 'Rajkot Jewellery',
    device_name: 'Shop Security Appliance',
    registration_status: 'REGISTERED',
    connection_status: 'ONLINE',
    version: '1.0.0',
    is_locked: true,
    is_configured: true
  });

  const [loading, setLoading] = useState(false);
  const [showAuthModal, setShowAuthModal] = useState(false);
  const [adminUsername, setAdminUsername] = useState('veronic_admin');
  const [adminPassword, setAdminPassword] = useState('');
  const [veronicToken, setVeronicToken] = useState(null);
  const [isEditMode, setIsEditMode] = useState(false);
  const [authError, setAuthError] = useState(null);

  // Form edit states
  const [editDeviceId, setEditDeviceId] = useState('');
  const [editShopId, setEditShopId] = useState('');
  const [editShopName, setEditShopName] = useState('');

  const fetchDeviceInfo = async () => {
    try {
      const res = await fetch(`${apiBase}/api/device/info`);
      if (res.ok) {
        const data = await res.json();
        setDeviceInfo(data);
        setEditDeviceId(data.device_id || '');
        setEditShopId(data.shop_id || 'SHOP-RK-001');
        setEditShopName(data.shop_name || 'Rajkot Jewellery');
      }
    } catch (err) {
      console.warn('Failed to fetch device info:', err);
    }
  };

  useEffect(() => {
    fetchDeviceInfo();
  }, [apiBase]);

  const handleOpenAuth = () => {
    setAuthError(null);
    setAdminPassword('');
    setShowAuthModal(true);
  };

  const handleAuthenticate = async (e) => {
    e.preventDefault();
    setAuthError(null);
    setLoading(true);

    try {
      const res = await fetch(`${apiBase}/api/admin/veronic-auth`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: adminUsername,
          password: adminPassword
        })
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Authentication failed');
      }

      setVeronicToken(data.token);
      setIsEditMode(true);
      setShowAuthModal(false);
      setAdminPassword('');
      showToast?.('Veronic administrator authenticated. Edit mode active.');
    } catch (err) {
      setAuthError(err.message || 'Invalid administrator credentials');
    } finally {
      setLoading(false);
    }
  };

  const handleSaveIdentity = async (e) => {
    e.preventDefault();
    if (!veronicToken) {
      setIsEditMode(false);
      return;
    }

    setLoading(true);
    try {
      const res = await fetch(`${apiBase}/api/device/identity`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Veronic-Token': veronicToken
        },
        body: JSON.stringify({
          device_id: editDeviceId,
          shop_id: editShopId,
          shop_name: editShopName
        })
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Failed to update identity');
      }

      showToast?.('Device identity and shop binding saved successfully.');
      setIsEditMode(false);
      setVeronicToken(null);
      await fetchDeviceInfo();
    } catch (err) {
      showToast?.(`Error: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleCancelEdit = () => {
    setIsEditMode(false);
    setVeronicToken(null);
    setEditDeviceId(deviceInfo.device_id || '');
    setEditShopId(deviceInfo.shop_id || '');
    setEditShopName(deviceInfo.shop_name || '');
  };

  return (
    <div className="dashboard-card" style={{ gridColumn: '1 / -1' }}>
      <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <h3 className="card-title" style={{ margin: 0 }}>DEVICE INFORMATION</h3>
          {isEditMode ? (
            <span className="status-pill pill-amber" style={{ fontSize: '11px', display: 'flex', alignItems: 'center', gap: '4px' }}>
              🔓 EDIT MODE (VERONIC AUTHENTICATED)
            </span>
          ) : (
            <span className="status-pill pill-green" style={{ fontSize: '11px', display: 'flex', alignItems: 'center', gap: '4px' }}>
              🔒 LOCKED
            </span>
          )}
        </div>

        {!isEditMode && (
          <button
            type="button"
            className="btn btn-secondary"
            onClick={handleOpenAuth}
            style={{ fontSize: '12px', padding: '6px 14px', borderColor: 'rgba(0, 202, 158, 0.4)', color: '#00CA9E' }}
          >
            UNLOCK WITH VERONIC AUTHENTICATION
          </button>
        )}
      </div>

      <div className="card-body">
        {isEditMode ? (
          <form onSubmit={handleSaveIdentity} className="settings-form-grid">
            <div className="form-group">
              <label className="form-label" style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>Device ID (Permanent Hardware Identifier)</span>
                <span style={{ color: '#F59E0B', fontSize: '11px' }}>🔓 EDITABLE</span>
              </label>
              <input
                type="text"
                className="form-input"
                style={{ fontFamily: 'monospace', fontWeight: 'bold' }}
                value={editDeviceId}
                onChange={(e) => setEditDeviceId(e.target.value)}
                placeholder="e.g. TRI-7F29A8C4"
                required
              />
            </div>

            <div className="form-group">
              <label className="form-label" style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>Shop ID (Customer / Branch Code)</span>
                <span style={{ color: '#F59E0B', fontSize: '11px' }}>🔓 EDITABLE</span>
              </label>
              <input
                type="text"
                className="form-input"
                style={{ fontFamily: 'monospace', fontWeight: 'bold' }}
                value={editShopId}
                onChange={(e) => setEditShopId(e.target.value)}
                placeholder="e.g. SHOP-RK-001"
                required
              />
            </div>

            <div className="form-group">
              <label className="form-label">Shop Name / Business Title</label>
              <input
                type="text"
                className="form-input"
                value={editShopName}
                onChange={(e) => setEditShopName(e.target.value)}
                placeholder="e.g. Rajkot Jewellery"
                required
              />
            </div>

            <div className="form-group">
              <label className="form-label">Software Version</label>
              <input
                type="text"
                className="form-input"
                value={deviceInfo.version || '1.0.0'}
                disabled
                style={{ opacity: 0.7 }}
              />
            </div>

            <div style={{ gridColumn: '1 / -1', display: 'flex', gap: '12px', marginTop: '14px' }}>
              <button type="submit" className="btn btn-primary" disabled={loading}>
                {loading ? 'Saving Identity...' : 'SAVE IDENTITY & LOCK'}
              </button>
              <button type="button" className="btn btn-secondary" onClick={handleCancelEdit} disabled={loading}>
                CANCEL & LOCK
              </button>
            </div>
          </form>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px' }}>
            <div className="quick-info-item">
              <span className="quick-info-label">Device ID</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '4px' }}>
                <span style={{ fontFamily: 'monospace', fontWeight: '700', fontSize: '14px', color: '#E1E7EC' }}>
                  {deviceInfo.device_id}
                </span>
                <span className="phase-badge" style={{ background: 'rgba(255,255,255,0.08)', color: '#94A3B8' }}>
                  🔒 LOCKED
                </span>
              </div>
            </div>

            <div className="quick-info-item">
              <span className="quick-info-label">Shop ID</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '4px' }}>
                <span style={{ fontFamily: 'monospace', fontWeight: '700', fontSize: '14px', color: '#00CA9E' }}>
                  {deviceInfo.shop_id || 'NOT CONFIGURED'}
                </span>
                <span className="phase-badge" style={{ background: 'rgba(255,255,255,0.08)', color: '#94A3B8' }}>
                  🔒 LOCKED
                </span>
              </div>
            </div>

            <div className="quick-info-item">
              <span className="quick-info-label">Shop Name</span>
              <span style={{ fontWeight: '600', fontSize: '14px', color: '#FFFFFF', marginTop: '4px', display: 'block' }}>
                {deviceInfo.shop_name || 'Rajkot Jewellery'}
              </span>
            </div>

            <div className="quick-info-item">
              <span className="quick-info-label">Registration Status</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '4px' }}>
                <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#10B981', display: 'inline-block' }} />
                <span style={{ fontWeight: '600', fontSize: '13px', color: '#10B981' }}>
                  {deviceInfo.registration_status || 'REGISTERED'}
                </span>
              </div>
            </div>

            <div className="quick-info-item">
              <span className="quick-info-label">Cloud Connection</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '4px' }}>
                <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#00CA9E', display: 'inline-block' }} />
                <span style={{ fontWeight: '600', fontSize: '13px', color: '#00CA9E' }}>
                  {deviceInfo.connection_status || 'ONLINE'}
                </span>
              </div>
            </div>

            <div className="quick-info-item">
              <span className="quick-info-label">Software Version</span>
              <span style={{ fontWeight: '600', fontSize: '14px', color: '#94A3B8', marginTop: '4px', display: 'block' }}>
                {deviceInfo.version || '1.0.0'}
              </span>
            </div>
          </div>
        )}
      </div>

      {/* VERONIC AUTHENTICATION MODAL */}
      {showAuthModal && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: 'rgba(0, 0, 0, 0.75)',
          backdropFilter: 'blur(4px)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 9999,
          padding: '20px'
        }}>
          <div style={{
            background: '#0D1B2A',
            border: '1px solid rgba(0, 202, 158, 0.3)',
            borderRadius: '12px',
            maxWidth: '440px',
            width: '100%',
            padding: '24px',
            boxShadow: '0 20px 50px rgba(0,0,0,0.8)'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '16px' }}>
              <span style={{ fontSize: '20px' }}>🛡️</span>
              <div>
                <h3 style={{ margin: 0, fontSize: '16px', color: '#FFFFFF', fontWeight: '700' }}>VERONIC AUTHENTICATION</h3>
                <p style={{ margin: '2px 0 0 0', fontSize: '12px', color: '#8C9BAE' }}>
                  Administrator authorization required to modify device identity.
                </p>
              </div>
            </div>

            {authError && (
              <div style={{
                background: 'rgba(239, 68, 68, 0.15)',
                border: '1px solid rgba(239, 68, 68, 0.4)',
                borderRadius: '6px',
                padding: '10px',
                color: '#F87171',
                fontSize: '13px',
                marginBottom: '16px'
              }}>
                {authError}
              </div>
            )}

            <form onSubmit={handleAuthenticate}>
              <div className="form-group" style={{ marginBottom: '14px' }}>
                <label className="form-label">Administrator Username</label>
                <input
                  type="text"
                  className="form-input"
                  value={adminUsername}
                  onChange={(e) => setAdminUsername(e.target.value)}
                  placeholder="veronic_admin"
                  required
                  autoFocus
                />
              </div>

              <div className="form-group" style={{ marginBottom: '20px' }}>
                <label className="form-label">Administrator Password</label>
                <input
                  type="password"
                  className="form-input"
                  value={adminPassword}
                  onChange={(e) => setAdminPassword(e.target.value)}
                  placeholder="••••••••••••••••"
                  required
                />
              </div>

              <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setShowAuthModal(false)}
                  disabled={loading}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={loading || !adminPassword}
                >
                  {loading ? 'Verifying...' : 'AUTHENTICATE'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
