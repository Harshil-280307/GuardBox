import React from 'react';

export default function SystemControls({
  systemStatus,
  onArm,
  onCancelArming,
  onDisarm,
  onTestAlarm,
  onSilenceAlarm,
  loading
}) {
  const isArmed = systemStatus?.armed || systemStatus?.system_mode === 'ARMED';
  const isArming = systemStatus?.is_arming || systemStatus?.system_mode === 'ARMING';
  const isAlarmActive = Boolean(systemStatus?.alarm_simulation?.is_active);

  return (
    <div className="dashboard-card system-controls-card">
      <div className="card-header">
        <h3 className="card-title">System Controls</h3>
      </div>

      <div className="card-body">
        {/* Arming / Disarming Buttons */}
        <div className="control-buttons-stack">
          {isArming ? (
            <button
              type="button"
              className="btn btn-warning btn-full"
              onClick={onCancelArming}
              disabled={loading}
            >
              <svg className="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
              <span>Cancel Arming ({systemStatus?.exit_countdown_remaining || 0}s)</span>
            </button>
          ) : (
            <button
              type="button"
              className={`btn btn-green btn-full ${isArmed ? 'btn-disabled-active' : ''}`}
              onClick={onArm}
              disabled={isArmed || loading}
            >
              <svg className="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" />
              </svg>
              <span>{isArmed ? 'System is Armed' : 'Arm System'}</span>
            </button>
          )}

          <button
            type="button"
            className={`btn btn-secondary btn-full ${!isArmed && !isArming ? 'btn-disabled-active' : ''}`}
            onClick={onDisarm}
            disabled={(!isArmed && !isArming && !isAlarmActive) || loading}
          >
            <svg className="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 10.5V6.75a4.5 4.5 0 10-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 002.25-2.25v-6.75a2.25 2.25 0 00-2.25-2.25H3.75a2.25 2.25 0 00-2.25 2.25v6.75a2.25 2.25 0 002.25 2.25z" />
            </svg>
            <span>Disarm System</span>
          </button>

          {/* Alarm Test / Silence */}
          {isAlarmActive ? (
            <button
              type="button"
              className="btn btn-danger btn-full alarm-pulse-btn"
              onClick={onSilenceAlarm}
              disabled={loading}
            >
              <svg className="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M17.25 9.75L19.5 12m0 0l2.25 2.25M19.5 12l2.25-2.25M19.5 12l-2.25 2.25m-10.5-6l4.72-4.72a.75.75 0 011.28.53v15.88a.75.75 0 01-1.28.53l-4.72-4.72H4.51c-.414 0-.75-.336-.75-.75V10.5c0-.414.336-.75.75-.75h4.24z" />
              </svg>
              <span>Silence Simulated Alarm</span>
            </button>
          ) : (
            <button
              type="button"
              className="btn btn-outline-warning btn-full"
              onClick={onTestAlarm}
              disabled={loading}
            >
              <svg className="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75v-.7V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0" />
              </svg>
              <span>Test Alarm</span>
            </button>
          )}
        </div>

        {/* Disclaimer Notice */}
        <div className="simulation-notice-box">
          <svg className="notice-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path strokeLinecap="round" strokeLinejoin="round" d="M11.25 11.25l.041-.02a.75.75 0 011.063.852l-.708 2.836a.75.75 0 001.063.853l.041-.021M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9-3.75h.008v.008H12V8.25z" />
          </svg>
          <span className="notice-text">
            SIMULATED ALARM — NO PHYSICAL SIREN CONNECTED
          </span>
        </div>
      </div>
    </div>
  );
}
