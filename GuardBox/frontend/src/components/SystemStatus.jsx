import React from 'react';
import { formatEventTime } from '../utils/formatters';

export default function SystemStatus({
  systemStatus,
  activeCamera,
  savedZones = [],
  activeAlert = null
}) {
  const isArmed = systemStatus?.armed || systemStatus?.system_mode === 'ARMED';
  const isArming = systemStatus?.is_arming || systemStatus?.system_mode === 'ARMING';
  const isTestMode = systemStatus?.is_test_mode || systemStatus?.system_mode === 'TEST_MODE';
  const isOnline = Boolean(activeCamera?.connected || activeCamera?.status === 'online');
  const activeZonesCount = savedZones.filter((z) => z.enabled).length;

  const getSystemDisplay = () => {
    if (isTestMode) return { label: 'TEST MODE', colorClass: 'val-purple' };
    if (isArming) return { label: `ARMING (${systemStatus?.exit_countdown_remaining || 0}s)`, colorClass: 'val-amber' };
    if (isArmed) return { label: 'ARMED', colorClass: 'val-green' };
    return { label: 'DISARMED', colorClass: 'val-neutral' };
  };

  const sysDisplay = getSystemDisplay();

  return (
    <div className="dashboard-card system-status-card">
      <div className="card-header">
        <h3 className="card-title">System Status</h3>
        <span className="card-badge">LIVE</span>
      </div>

      <div className="status-grid">
        {/* Box 1: System */}
        <div className="status-metric-box">
          <div className="metric-icon-wrap">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" />
            </svg>
          </div>
          <div className="metric-info">
            <span className="metric-label">System</span>
            <span className={`metric-value ${sysDisplay.colorClass}`}>{sysDisplay.label}</span>
          </div>
        </div>

        {/* Box 2: Camera */}
        <div className="status-metric-box">
          <div className="metric-icon-wrap">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 10.5l4.72-4.72a.75.75 0 011.28.53v11.38a.75.75 0 01-1.28.53l-4.72-4.72M4.5 18.75h9a2.25 2.25 0 002.25-2.25v-9a2.25 2.25 0 00-2.25-2.25h-9A2.25 2.25 0 002.25 7.5v9a2.25 2.25 0 002.25 2.25z" />
            </svg>
          </div>
          <div className="metric-info">
            <span className="metric-label">{activeCamera?.name ? 'Camera' : 'Active Cam'}</span>
            <span className={`metric-value ${isOnline ? 'val-green' : 'val-red'}`}>
              {isOnline ? 'Online' : 'Offline'}
            </span>
          </div>
        </div>

        {/* Box 3: Detection Areas */}
        <div className="status-metric-box">
          <div className="metric-icon-wrap">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M7.5 3.75H6A2.25 2.25 0 003.75 6v1.5M16.5 3.75H18A2.25 2.25 0 0120.25 6v1.5m0 9V18A2.25 2.25 0 0118 20.25h-1.5m-9 0H6A2.25 2.25 0 013.75 18v-1.5" />
            </svg>
          </div>
          <div className="metric-info">
            <span className="metric-label">Detection Areas</span>
            <span className={`metric-value ${activeZonesCount > 0 ? 'val-blue' : 'val-neutral'}`}>
              {activeZonesCount > 0 ? `${activeZonesCount} Active` : 'Not Set'}
            </span>
          </div>
        </div>
      </div>

      {/* Active Security Alert Banner */}
      {activeAlert && (
        <div className="active-alert-panel" style={{
          marginTop: '14px',
          padding: '12px 14px',
          borderRadius: '8px',
          backgroundColor: 'rgba(239, 68, 68, 0.12)',
          border: '1px solid rgba(239, 68, 68, 0.4)',
          display: 'flex',
          flexDirection: 'column',
          gap: '6px'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ color: '#EF4444', fontWeight: '700', fontSize: '13px', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span>🚨</span> SECURITY ALERT
            </span>
            <span className="status-badge badge-red">{activeAlert.status || 'ACTIVE'}</span>
          </div>
          <div style={{ fontSize: '12px', color: '#E5E7EB', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px', marginTop: '4px' }}>
            <div style={{ gridColumn: '1 / -1' }}>
              <strong style={{ color: '#9CA3AF' }}>Alert ID:</strong>{' '}
              <span style={{ fontFamily: 'monospace', color: '#38BDF8', fontWeight: '600' }}>
                {activeAlert.alert_code || activeAlert.id}
              </span>
            </div>
            <div>
              <strong style={{ color: '#9CA3AF' }}>Camera:</strong> {activeAlert.camera_name || activeCamera?.name || 'Camera 01'}
            </div>
            <div>
              <strong style={{ color: '#9CA3AF' }}>Reason:</strong> {activeAlert.event_type?.replace(/_/g, ' ') || 'Motion detected'}
            </div>
            <div>
              <strong style={{ color: '#9CA3AF' }}>Time:</strong> {formatEventTime(activeAlert.created_at)}
            </div>
            <div>
              <strong style={{ color: '#9CA3AF' }}>Status:</strong>{' '}
              <span style={{ color: activeAlert.status === 'ACTIVE' || activeAlert.status === 'WAITING_ACK' ? '#EF4444' : '#10B981', fontWeight: '600' }}>
                {activeAlert.status || 'ACTIVE'}
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
