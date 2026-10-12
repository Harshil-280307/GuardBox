import React from 'react';

export default function QuickInfo({
  activeCamera,
  systemStatus,
  savedZones = []
}) {
  const isArmed = systemStatus?.armed || systemStatus?.system_mode === 'ARMED';
  const isOnline = Boolean(activeCamera?.connected || activeCamera?.status === 'online');
  const activeZones = savedZones.filter(z => z.enabled);

  const getMonitoringState = () => {
    if (!isOnline) return { text: 'Stopped (Camera Offline)', color: 'val-red' };
    if (isArmed) return { text: 'Active (Armed)', color: 'val-green' };
    return { text: 'Standby (Disarmed)', color: 'val-neutral' };
  };

  const monState = getMonitoringState();

  return (
    <div className="dashboard-card quick-info-card">
      <div className="card-header">
        <h3 className="card-title">Quick Info</h3>
      </div>

      <div className="card-body">
        <div className="quick-info-list">
          <div className="quick-info-row">
            <span className="info-label">Camera</span>
            <span className="info-value">
              {activeCamera?.name || 'Main Shop Camera'} ({activeCamera?.model || 'Tapo C100'})
            </span>
          </div>

          <div className="quick-info-row">
            <span className="info-label">IP Address</span>
            <span className="info-value">
              {activeCamera?.camera_ip || activeCamera?.ip_address || '192.168.31.108'}
            </span>
          </div>

          <div className="quick-info-row">
            <span className="info-label">Detection Areas</span>
            <span className="info-value">
              {savedZones.length > 0
                ? `${savedZones.length} configured (${activeZones.length} active)`
                : 'Not Set'}
            </span>
          </div>

          <div className="quick-info-row">
            <span className="info-label">Monitoring</span>
            <span className={`info-value ${monState.color}`}>{monState.text}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
