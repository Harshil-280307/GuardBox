import React from 'react';

export default function TopBar({
  activeTab,
  setActiveTab,
  cameras = [],
  systemStatus
}) {
  const isArmed = systemStatus?.armed || systemStatus?.system_mode === 'ARMED';
  const isArming = systemStatus?.is_arming || systemStatus?.system_mode === 'ARMING';
  const isTestMode = systemStatus?.is_test_mode || systemStatus?.system_mode === 'TEST_MODE';

  const onlineCamerasCount = cameras.filter((c) => c.status === 'online' || c.connected).length;
  const totalCamerasCount = cameras.length || 1;

  const getSystemBadge = () => {
    if (isTestMode) {
      return { text: 'TEST MODE', className: 'status-pill pill-purple' };
    }
    if (isArming) {
      return {
        text: `ARMING (${systemStatus?.exit_countdown_remaining || 0}s)`,
        className: 'status-pill pill-amber'
      };
    }
    if (isArmed) {
      return { text: 'SYSTEM ARMED', className: 'status-pill pill-green' };
    }
    return { text: 'SYSTEM DISARMED', className: 'status-pill pill-neutral' };
  };

  const sysBadge = getSystemBadge();

  return (
    <header className="topbar-container">
      {/* Brand & Subtitle */}
      <div className="topbar-left">
        <div className="brand-logo-wrap">
          <img src="/trinetra-emblem.png" alt="TRINETRA" className="brand-logo-img" />
        </div>
        <div className="brand-text">
          <div className="brand-title-row">
            <span className="brand-title">TRINETRA</span>
            <span className="phase-badge">SYSTEM ACTIVE</span>
          </div>
          <span className="brand-subtitle">Security System</span>
        </div>
      </div>

      {/* Navigation Tabs (Live Monitor, Cameras, Settings) */}
      <nav className="topbar-nav" aria-label="Main Navigation">
        <button
          type="button"
          className={`nav-tab-btn ${activeTab === 'monitor' ? 'active' : ''}`}
          onClick={() => setActiveTab('monitor')}
        >
          <svg className="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
            <line x1="8" y1="21" x2="16" y2="21" />
            <line x1="12" y1="17" x2="12" y2="21" />
          </svg>
          <span>Live Monitor</span>
        </button>

        <button
          type="button"
          className={`nav-tab-btn ${activeTab === 'cameras' ? 'active' : ''}`}
          onClick={() => setActiveTab('cameras')}
        >
          <svg className="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 10.5l4.72-4.72a.75.75 0 011.28.53v11.38a.75.75 0 01-1.28.53l-4.72-4.72M4.5 18.75h9a2.25 2.25 0 002.25-2.25v-9a2.25 2.25 0 00-2.25-2.25h-9A2.25 2.25 0 002.25 7.5v9a2.25 2.25 0 002.25 2.25z" />
          </svg>
          <span>Cameras ({cameras.length})</span>
        </button>

        <button
          type="button"
          className={`nav-tab-btn ${activeTab === 'settings' ? 'active' : ''}`}
          onClick={() => setActiveTab('settings')}
        >
          <svg className="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path strokeLinecap="round" strokeLinejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.24-.438.613-.431.992a6.759 6.759 0 010 .255c-.007.378.138.75.43.99l1.005.828c.424.35.534.954.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.57 6.57 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.28c-.09.543-.56.941-1.11.941h-2.594c-.55 0-1.02-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.992a6.932 6.932 0 010-.255c.007-.378-.138-.75-.43-.99l-1.004-.828a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.087.22-.128.332-.183.582-.495.644-.869l.214-1.281z" />
            <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>
          <span>Settings</span>
        </button>
      </nav>

      {/* Right Indicators */}
      <div className="topbar-right">
        <div className={`camera-indicator ${onlineCamerasCount > 0 ? 'online' : 'offline'}`}>
          <span className="indicator-dot"></span>
          <span className="indicator-label">
            {onlineCamerasCount > 0
              ? `${onlineCamerasCount}/${totalCamerasCount} Online`
              : 'All Cameras Offline'}
          </span>
        </div>

        <div className={sysBadge.className}>
          <span className="pill-dot"></span>
          <span>{sysBadge.text}</span>
        </div>
      </div>
    </header>
  );
}
