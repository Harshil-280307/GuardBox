import React, { useState, useEffect } from 'react';

const ZONE_COLORS = [
  { border: '#2563EB', bg: 'rgba(37, 99, 235, 0.22)', dot: '#3B82F6' },
  { border: '#06B6D4', bg: 'rgba(6, 182, 212, 0.22)', dot: '#06B6D4' },
  { border: '#10B981', bg: 'rgba(16, 185, 129, 0.22)', dot: '#10B981' },
  { border: '#F59E0B', bg: 'rgba(245, 158, 11, 0.22)', dot: '#F59E0B' },
  { border: '#8B5CF6', bg: 'rgba(139, 92, 246, 0.22)', dot: '#8B5CF6' }
];

export default function ZoneControls({
  isDrawingMode,
  setIsDrawingMode,
  isEditingMode,
  setIsEditingMode,
  draftPoints = [],
  setDraftPoints,
  isDraftClosed,
  setIsDraftClosed,
  savedZones = [],
  selectedZoneId,
  onSelectZone,
  onSaveZone,
  onDeleteZone,
  onToggleZone,
  onClearAllZones,
  onCancelDraft,
  validationError,
  loading
}) {
  const [zoneNameInput, setZoneNameInput] = useState('');
  const [editingZoneId, setEditingZoneId] = useState(null);

  const selectedZone = savedZones.find((z) => z.id === selectedZoneId) || null;
  const isInteracting = isDrawingMode || isEditingMode;

  // Determine if polygon is valid and can be saved
  const canClose = draftPoints.length >= 3 && !isDraftClosed;
  const canSave = draftPoints.length >= 3 && isDraftClosed && zoneNameInput.trim().length > 0 && !validationError;

  // Start Drawing a new Polygon Zone
  const handleStartAddZone = () => {
    setIsEditingMode(false);
    setEditingZoneId(null);
    setIsDrawingMode(true);
    setDraftPoints([]);
    setIsDraftClosed(false);
    setZoneNameInput(`Zone ${savedZones.length + 1}`);
  };

  // Start Editing Selected Zone
  const handleStartEditZone = (zoneToEdit) => {
    const target = zoneToEdit || selectedZone;
    if (!target) return;
    const points = target.points || (target.x !== undefined ? [
      [target.x, target.y],
      [target.x + target.width, target.y],
      [target.x + target.width, target.y + target.height],
      [target.x, target.y + target.height]
    ] : []);

    if (points.length < 3) return;

    setEditingZoneId(target.id);
    setIsDrawingMode(false);
    setIsEditingMode(true);
    setDraftPoints(points.map((p) => [Number(p[0]), Number(p[1])]));
    setIsDraftClosed(true);
    setZoneNameInput(target.name || `Zone ${target.id}`);
  };

  // Close / Finish Polygon Shape
  const handleFinishShape = () => {
    if (draftPoints.length >= 3) {
      setIsDraftClosed(true);
    }
  };

  // Undo Last Vertex Point
  const handleUndoPoint = () => {
    if (draftPoints.length > 0 && !isDraftClosed) {
      setDraftPoints(draftPoints.slice(0, -1));
    }
  };

  // Clear all points in current draft
  const handleClearDraftPoints = () => {
    setDraftPoints([]);
    setIsDraftClosed(false);
  };

  // Cancel Drawing / Editing
  const handleCancel = () => {
    setIsDrawingMode(false);
    setIsEditingMode(false);
    setEditingZoneId(null);
    setDraftPoints([]);
    setIsDraftClosed(false);
    setZoneNameInput('');
    if (onCancelDraft) onCancelDraft();
  };

  // Save Polygon Zone
  const handleSave = () => {
    if (!canSave) return;
    const name = zoneNameInput.trim() || `Zone ${savedZones.length + 1}`;
    onSaveZone({
      id: editingZoneId,
      name,
      points: draftPoints
    });
    handleCancel();
  };

  // Delete Selected Zone
  const handleDeleteSelected = () => {
    if (!selectedZoneId) return;
    onDeleteZone(selectedZoneId);
  };

  return (
    <div className="dashboard-card zone-controls-card">
      <div className="card-header">
        <h3 className="card-title">Detection Zones ({savedZones.length})</h3>
        {isDrawingMode && (
          <span className="card-badge pill-amber">DRAWING POLYGON</span>
        )}
        {isEditingMode && (
          <span className="card-badge pill-cyan">EDITING SHAPE</span>
        )}
        {!isInteracting && savedZones.length > 0 && (
          <span className="card-badge pill-blue">
            {savedZones.filter((z) => z.enabled).length} ACTIVE
          </span>
        )}
      </div>

      <div className="card-body">
        <p className="card-description">
          {isDrawingMode
            ? !isDraftClosed
              ? `Click on the camera frame to place polygon points (${draftPoints.length}/3 placed). Double-click or click the first point to close the shape.`
              : 'Shape closed! Drag any numbered vertex handle to adjust the area before saving.'
            : isEditingMode
            ? 'Adjust vertices by dragging the numbered handles on the camera preview. Click Save when finished.'
            : savedZones.length > 0
            ? 'Custom polygon areas active. Only motion inside enabled detection zones triggers security alerts.'
            : 'No detection zones configured. Click "+ Add Zone" to draw custom polygon detection areas.'}
        </p>

        {validationError && (
          <div className="validation-error-banner">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
            </svg>
            <span>{validationError}</span>
          </div>
        )}

        {/* Zone Name Input when Drawing or Editing */}
        {isInteracting && (
          <div className="zone-name-input-row">
            <label className="form-label">Zone Name:</label>
            <input
              type="text"
              className="form-input"
              placeholder="e.g. Jewellery Display, Cash Counter"
              value={zoneNameInput}
              onChange={(e) => setZoneNameInput(e.target.value)}
              maxLength={50}
              autoFocus
            />
          </div>
        )}

        {/* Action Controls Toolbar */}
        <div className="zone-buttons-grid">
          {!isInteracting ? (
            <>
              {/* [ + Add Zone ] */}
              <button
                type="button"
                className="btn btn-primary"
                onClick={handleStartAddZone}
                disabled={loading}
              >
                <svg className="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
                </svg>
                <span>+ Add Zone</span>
              </button>

              {/* [ Edit ] */}
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => handleStartEditZone(selectedZone)}
                disabled={!selectedZone || loading}
                title={!selectedZone ? 'Select a zone below to edit' : 'Edit selected zone'}
              >
                <svg className="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0115.75 21H5.25A2.25 2.25 0 013 18.75V8.25A2.25 2.25 0 015.25 6H10" />
                </svg>
                <span>Edit</span>
              </button>

              {/* [ Delete ] */}
              <button
                type="button"
                className="btn btn-secondary btn-danger-hover"
                onClick={handleDeleteSelected}
                disabled={!selectedZone || loading}
                title={!selectedZone ? 'Select a zone below to delete' : 'Delete selected zone'}
              >
                <svg className="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" />
                </svg>
                <span>Delete</span>
              </button>

              {/* [ Clear ] */}
              <button
                type="button"
                className="btn btn-danger"
                onClick={onClearAllZones}
                disabled={savedZones.length === 0 || loading}
              >
                <svg className="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
                <span>Clear</span>
              </button>
            </>
          ) : (
            <>
              {/* Actively Drawing: Finish Shape button */}
              {isDrawingMode && !isDraftClosed && (
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={handleFinishShape}
                  disabled={!canClose}
                  title="Close polygon vertices (min 3 points)"
                >
                  <svg className="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <span>Finish Shape ({draftPoints.length} pts)</span>
                </button>
              )}

              {/* [ Save ] */}
              {isDraftClosed && (
                <button
                  type="button"
                  className="btn btn-primary active-glow"
                  onClick={handleSave}
                  disabled={!canSave || loading}
                >
                  <svg className="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                  </svg>
                  <span>Save Zone</span>
                </button>
              )}

              {/* Undo / Clear Draft Points */}
              {isDrawingMode && !isDraftClosed && (
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={handleUndoPoint}
                  disabled={draftPoints.length === 0}
                >
                  <svg className="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 15L3 9m0 0l6-6M3 9h12a6 6 0 010 12h-3" />
                  </svg>
                  <span>Undo Point</span>
                </button>
              )}

              {/* [ Cancel ] */}
              <button
                type="button"
                className="btn btn-secondary"
                onClick={handleCancel}
                disabled={loading}
              >
                <svg className="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
                <span>Cancel</span>
              </button>
            </>
          )}
        </div>

        {/* Configured Zones List */}
        {savedZones.length > 0 && (
          <div className="configured-zones-list">
            <span className="zones-list-title">DETECTION ZONES</span>
            {savedZones.map((z, idx) => {
              const color = ZONE_COLORS[idx % ZONE_COLORS.length];
              const isSelected = selectedZoneId === z.id;
              const isEnabled = Boolean(z.enabled);
              const pointCount = z.points ? z.points.length : 4;

              return (
                <div
                  key={z.id}
                  className={`zone-item-row ${isSelected ? 'selected' : ''} ${!isEnabled ? 'disabled' : ''}`}
                  onClick={() => onSelectZone && onSelectZone(z)}
                >
                  <div className="zone-item-left">
                    <span
                      className="zone-item-dot"
                      style={{ backgroundColor: isEnabled ? color.dot : '#546575' }}
                    ></span>
                    <div className="zone-item-info">
                      <span className="zone-item-name">{z.name}</span>
                      <span className="zone-item-meta">
                        {pointCount}-point Polygon | Sens: {z.sensitivity || 35} | Area: {z.minimum_motion_area || 200}px
                      </span>
                    </div>
                  </div>

                  <div className="zone-item-actions">
                    <button
                      type="button"
                      className="btn-zone-action-icon"
                      onClick={(e) => {
                        e.stopPropagation();
                        onSelectZone && onSelectZone(z);
                        handleStartEditZone(z);
                      }}
                      title="Edit polygon shape"
                    >
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0115.75 21H5.25A2.25 2.25 0 013 18.75V8.25A2.25 2.25 0 015.25 6H10" />
                      </svg>
                    </button>

                    <button
                      type="button"
                      className={`btn-zone-toggle ${isEnabled ? 'enabled' : 'disabled'}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        onToggleZone && onToggleZone(z.id);
                      }}
                      title={isEnabled ? 'Disable zone' : 'Enable zone'}
                    >
                      {isEnabled ? 'ON' : 'OFF'}
                    </button>

                    <button
                      type="button"
                      className="btn-zone-delete"
                      onClick={(e) => {
                        e.stopPropagation();
                        onDeleteZone && onDeleteZone(z.id);
                      }}
                      title="Delete zone"
                    >
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
