import React, { useRef, useState } from 'react';
import DetectionZoneOverlay from './DetectionZoneOverlay';

export default function CameraCard({
  apiBase,
  activeCamera,
  cameras = [],
  onSelectCamera,
  systemStatus,
  isDrawingMode,
  isEditingMode,
  draftPoints = [],
  setDraftPoints,
  isDraftClosed,
  setIsDraftClosed,
  savedZones = [],
  selectedZoneId,
  onSelectZone,
  onFinishDraft
}) {
  const cardRef = useRef(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [streamError, setStreamError] = useState(false);

  const isOnline = Boolean(activeCamera?.connected || activeCamera?.status === 'online');
  const isAlarmActive = Boolean(systemStatus?.alarm_simulation?.is_active);

  const toggleFullscreen = () => {
    if (!cardRef.current) return;
    if (!document.fullscreenElement) {
      cardRef.current.requestFullscreen().then(() => setIsFullscreen(true)).catch(() => {});
    } else {
      document.exitFullscreen().then(() => setIsFullscreen(false)).catch(() => {});
    }
  };

  const streamUrl = activeCamera?.id
    ? `${apiBase}/cameras/${activeCamera.id}/stream`
    : `${apiBase}/camera/stream`;

  return (
    <div ref={cardRef} className={`camera-card ${isFullscreen ? 'fullscreen' : ''}`}>
      {/* Top Camera Header */}
      <div className="camera-card-header">
        <div className="camera-header-left">
          {/* Camera Selection Dropdown / Tag */}
          {cameras.length > 1 ? (
            <div className="camera-select-dropdown-wrap">
              <select
                className="camera-dropdown-select"
                value={activeCamera?.id || 1}
                onChange={(e) => onSelectCamera && onSelectCamera(Number(e.target.value))}
              >
                {cameras.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} ({c.model || 'Tapo C100'})
                  </option>
                ))}
              </select>
            </div>
          ) : (
            <div className="camera-name-wrap">
              <span className="camera-title">{activeCamera?.name || 'Main Shop Camera'}</span>
              <span className="camera-model-badge">{activeCamera?.model || 'Tapo C100'}</span>
            </div>
          )}

          <span className="camera-ip-badge">{activeCamera?.camera_ip || activeCamera?.ip_address || '192.168.31.108'}</span>

          <div className={`camera-status-pill ${isOnline ? 'online' : 'offline'}`}>
            <span className="status-dot"></span>
            <span>{isOnline ? 'Online' : 'Offline'}</span>
          </div>
        </div>

        <div className="camera-header-right">
          {isOnline && (
            <div className="live-badge">
              <span className="live-dot"></span>
              <span>LIVE</span>
            </div>
          )}

          <button
            type="button"
            className="camera-tool-btn"
            onClick={toggleFullscreen}
            title={isFullscreen ? 'Exit Fullscreen' : 'Fullscreen'}
            aria-label="Toggle Fullscreen"
          >
            {isFullscreen ? (
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 9L4 4m0 0h4m-4 0v4m6 6l5 5m0 0h-4m4 0v-4" />
              </svg>
            ) : (
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 3.75v4.5m0-4.5h4.5m-4.5 0L9 9M3.75 20.25v-4.5m0 4.5h4.5m-4.5 0L9 15M20.25 3.75h-4.5m4.5 0v4.5m0-4.5L15 9m5.25 11.25h-4.5m4.5 0v-4.5m0 4.5L15 15" />
              </svg>
            )}
          </button>
        </div>
      </div>

      {/* Video Viewport Container */}
      <div className="camera-viewport">
        {/* Drawing / Editing Mode Helper Banner */}
        {isDrawingMode && !isDraftClosed && (
          <div className="drawing-mode-banner">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M15.042 21.672L13.684 16.6m0 0l-2.51 2.225.569-9.47 5.227 7.917-3.286-.672zM12 2.25V4.5m5.303 1.197l-1.591 1.591M21.75 12h-2.25m-1.197 5.303l-1.591-1.591" />
            </svg>
            <span>Click around required area to place polygon points. Double-click or click first point to close.</span>
          </div>
        )}

        {(isDrawingMode && isDraftClosed || isEditingMode) && (
          <div className="drawing-mode-banner edit-hint">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0115.75 21H5.25A2.25 2.25 0 013 18.75V8.25A2.25 2.25 0 015.25 6H10" />
            </svg>
            <span>Drag the numbered vertex handles to fine-tune polygon boundaries.</span>
          </div>
        )}

        {/* Simulated Alarm Warning Banner */}
        {isAlarmActive && (
          <div className="alarm-active-banner">
            <span className="alarm-pulse-dot"></span>
            <span>SIMULATED ALARM ACTIVE — NO PHYSICAL SIREN CONNECTED</span>
          </div>
        )}

        {/* Live Stream or Offline Fallback */}
        {isOnline && !streamError ? (
          <img
            key={activeCamera?.id || 'cam1'}
            src={streamUrl}
            alt={`Live Stream ${activeCamera?.name || 'Camera'}`}
            className="camera-stream-image"
            onError={() => setStreamError(true)}
            onLoad={() => setStreamError(false)}
          />
        ) : (
          <div className="camera-offline-view">
            <div className="offline-icon-wrap">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 10.5l4.72-4.72a.75.75 0 011.28.53v11.38a.75.75 0 01-1.28.53l-4.72-4.72M4.5 18.75h9a2.25 2.25 0 002.25-2.25v-9a2.25 2.25 0 00-2.25-2.25h-9A2.25 2.25 0 002.25 7.5v9a2.25 2.25 0 002.25 2.25z" />
                <line x1="2" y1="2" x2="22" y2="22" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              </svg>
            </div>
            <div className="offline-text-wrap">
              <span className="offline-heading">{activeCamera?.name || 'Camera'} Disconnected</span>
              <span className="offline-subtext">Connecting to {activeCamera?.model || 'Tapo C100'} at {activeCamera?.camera_ip || activeCamera?.ip_address || '192.168.31.108'}...</span>
            </div>
          </div>
        )}

        {/* Multi-Zone Custom Polygon Interactive Overlay */}
        <DetectionZoneOverlay
          isDrawingMode={isDrawingMode}
          isEditingMode={isEditingMode}
          draftPoints={draftPoints}
          setDraftPoints={setDraftPoints}
          isDraftClosed={isDraftClosed}
          setIsDraftClosed={setIsDraftClosed}
          savedZones={savedZones}
          selectedZoneId={selectedZoneId}
          onSelectZone={onSelectZone}
          onFinishDraft={onFinishDraft}
        />

        {/* Bottom Left Camera Tag */}
        <div className="camera-bottom-tag">
          <span>{activeCamera?.name || 'Main Shop Camera'} ({activeCamera?.model || 'Tapo C100'})</span>
        </div>
      </div>
    </div>
  );
}
