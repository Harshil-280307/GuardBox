import React, { useRef, useState, useCallback, useEffect } from 'react';

/**
 * DetectionZoneOverlay
 * Provides interactive custom polygon drawing, vertex dragging, and multi-zone rendering
 * using normalized coordinates [0.0 - 1.0] relative to the camera viewport.
 */

const ZONE_COLORS = [
  { border: '#2563EB', bg: 'rgba(37, 99, 235, 0.22)', text: '#93C5FD', dot: '#3B82F6', handle: '#60A5FA' },
  { border: '#06B6D4', bg: 'rgba(6, 182, 212, 0.22)', text: '#67E8F9', dot: '#06B6D4', handle: '#22D3EE' },
  { border: '#10B981', bg: 'rgba(16, 185, 129, 0.22)', text: '#6EE7B7', dot: '#10B981', handle: '#34D399' },
  { border: '#F59E0B', bg: 'rgba(245, 158, 11, 0.22)', text: '#FDE68A', dot: '#F59E0B', handle: '#FBBF24' },
  { border: '#8B5CF6', bg: 'rgba(139, 92, 246, 0.22)', text: '#DDD6FE', dot: '#8B5CF6', handle: '#A78BFA' }
];

export default function DetectionZoneOverlay({
  isDrawingMode,
  isEditingMode,
  draftPoints = [],
  setDraftPoints,
  isDraftClosed,
  setIsDraftClosed,
  savedZones = [],
  selectedZoneId = null,
  onSelectZone,
  onFinishDraft,
  onPointAdded
}) {
  const overlayRef = useRef(null);
  const [hoverPoint, setHoverPoint] = useState(null);
  const [draggingVertexIndex, setDraggingVertexIndex] = useState(null);

  // Normalize mouse/touch client coordinates to [0.0 - 1.0]
  const getNormalizedPoint = useCallback((e) => {
    if (!overlayRef.current) return { x: 0, y: 0 };
    const rect = overlayRef.current.getBoundingClientRect();
    const clientX = e.clientX ?? (e.touches && e.touches[0]?.clientX) ?? 0;
    const clientY = e.clientY ?? (e.touches && e.touches[0]?.clientY) ?? 0;

    const rawX = (clientX - rect.left) / rect.width;
    const rawY = (clientY - rect.top) / rect.height;

    return {
      x: Math.max(0.0, Math.min(1.0, rawX)),
      y: Math.max(0.0, Math.min(1.0, rawY))
    };
  }, []);

  // Check if click is close to first point to auto-close polygon
  const isNearFirstPoint = useCallback((p, points) => {
    if (!points || points.length < 3) return false;
    const first = points[0];
    const dx = p.x - first[0];
    const dy = p.y - first[1];
    const distSq = dx * dx + dy * dy;
    return distSq < 0.0016; // ~4% distance threshold
  }, []);

  // Handle overlay click to add vertex
  const handleOverlayClick = useCallback((e) => {
    if (!isDrawingMode || isDraftClosed) return;
    if (draggingVertexIndex !== null) return;
    if (e.button !== undefined && e.button !== 0) return;

    const p = getNormalizedPoint(e);

    // If near first point and has >= 3 points, close the polygon
    if (draftPoints.length >= 3 && isNearFirstPoint(p, draftPoints)) {
      setIsDraftClosed(true);
      if (onFinishDraft) onFinishDraft();
      return;
    }

    const nextPoints = [...draftPoints, [Number(p.x.toFixed(4)), Number(p.y.toFixed(4))]];
    setDraftPoints(nextPoints);
    if (onPointAdded) onPointAdded(nextPoints);
  }, [isDrawingMode, isDraftClosed, draggingVertexIndex, getNormalizedPoint, draftPoints, isNearFirstPoint, setDraftPoints, setIsDraftClosed, onFinishDraft, onPointAdded]);

  // Handle double-click to close polygon
  const handleDoubleClick = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    if (isDrawingMode && !isDraftClosed && draftPoints.length >= 3) {
      setIsDraftClosed(true);
      if (onFinishDraft) onFinishDraft();
    }
  }, [isDrawingMode, isDraftClosed, draftPoints, setIsDraftClosed, onFinishDraft]);

  // Handle pointer move for guideline or vertex dragging
  const handlePointerMove = useCallback((e) => {
    const p = getNormalizedPoint(e);

    if (draggingVertexIndex !== null && setDraftPoints) {
      e.preventDefault();
      setDraftPoints((prev) => {
        const next = [...prev];
        next[draggingVertexIndex] = [Number(p.x.toFixed(4)), Number(p.y.toFixed(4))];
        return next;
      });
    } else if (isDrawingMode && !isDraftClosed) {
      setHoverPoint(p);
    }
  }, [getNormalizedPoint, draggingVertexIndex, isDrawingMode, isDraftClosed, setDraftPoints]);

  const handlePointerUp = useCallback(() => {
    if (draggingVertexIndex !== null) {
      setDraggingVertexIndex(null);
    }
  }, [draggingVertexIndex]);

  useEffect(() => {
    const handleGlobalUp = () => {
      setDraggingVertexIndex(null);
    };
    window.addEventListener('pointerup', handleGlobalUp);
    return () => window.removeEventListener('pointerup', handleGlobalUp);
  }, []);

  // Compute centroid for zone label positioning
  const getCentroid = (points) => {
    if (!points || points.length === 0) return { x: 0.5, y: 0.5 };
    let sumX = 0;
    let sumY = 0;
    points.forEach((p) => {
      sumX += p[0];
      sumY += p[1];
    });
    return {
      x: sumX / points.length,
      y: sumY / points.length
    };
  };

  const isInteractive = isDrawingMode || isEditingMode;

  return (
    <div
      ref={overlayRef}
      className={`detection-zone-overlay ${isInteractive ? 'drawing-active' : ''}`}
      onClick={handleOverlayClick}
      onDoubleClick={handleDoubleClick}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      role="presentation"
    >
      <svg
        className="zone-svg-viewport"
        viewBox="0 0 1000 1000"
        preserveAspectRatio="none"
      >
        {/* Render Saved Zones */}
        {savedZones.map((z, idx) => {
          const color = ZONE_COLORS[idx % ZONE_COLORS.length];
          const isSelected = selectedZoneId === z.id;
          const isEnabled = Boolean(z.enabled);
          const points = z.points || (z.x !== undefined ? [
            [z.x, z.y],
            [z.x + z.width, z.y],
            [z.x + z.width, z.y + z.height],
            [z.x, z.y + z.height]
          ] : []);

          if (!points || points.length < 3) return null;

          const pointsStr = points.map((p) => `${p[0] * 1000},${p[1] * 1000}`).join(' ');

          return (
            <g key={z.id} className={`saved-zone-group ${isSelected ? 'selected' : ''}`}>
              <polygon
                points={pointsStr}
                fill={isEnabled ? color.bg : 'rgba(157, 180, 198, 0.08)'}
                stroke={isEnabled ? (isSelected ? '#60A5FA' : color.border) : 'rgba(157, 180, 198, 0.4)'}
                strokeWidth={isSelected ? '3' : '2'}
                strokeDasharray={isEnabled ? 'none' : '4 4'}
                style={{ cursor: 'pointer' }}
                onClick={(e) => {
                  e.stopPropagation();
                  if (onSelectZone) onSelectZone(z);
                }}
              />
            </g>
          );
        })}

        {/* Render Active Draft / Editing Polygon */}
        {draftPoints.length > 0 && (
          <g className="draft-zone-group">
            {/* Filled Polygon or Open Polyline */}
            {isDraftClosed && draftPoints.length >= 3 ? (
              <polygon
                points={draftPoints.map((p) => `${p[0] * 1000},${p[1] * 1000}`).join(' ')}
                fill="rgba(37, 99, 235, 0.28)"
                stroke="#3B82F6"
                strokeWidth="2.5"
              />
            ) : (
              <>
                <polyline
                  points={draftPoints.map((p) => `${p[0] * 1000},${p[1] * 1000}`).join(' ')}
                  fill="none"
                  stroke="#3B82F6"
                  strokeWidth="2.5"
                  strokeDasharray="6 4"
                />
                {/* Active Guideline to Mouse Cursor */}
                {hoverPoint && draftPoints.length > 0 && (
                  <line
                    x1={draftPoints[draftPoints.length - 1][0] * 1000}
                    y1={draftPoints[draftPoints.length - 1][1] * 1000}
                    x2={hoverPoint.x * 1000}
                    y2={hoverPoint.y * 1000}
                    stroke="#60A5FA"
                    strokeWidth="2"
                    strokeDasharray="4 4"
                  />
                )}
              </>
            )}

            {/* Polygon Outline Lines */}
            {isDraftClosed && draftPoints.map((p, idx) => {
              const nextP = draftPoints[(idx + 1) % draftPoints.length];
              return (
                <line
                  key={`line-${idx}`}
                  x1={p[0] * 1000}
                  y1={p[1] * 1000}
                  x2={nextP[0] * 1000}
                  y2={nextP[1] * 1000}
                  stroke="#60A5FA"
                  strokeWidth="2"
                />
              );
            })}
          </g>
        )}
      </svg>

      {/* HTML DOM Overlays for Zone Labels and Interactive Handles */}
      {/* 1. Saved Zone Labels */}
      {savedZones.map((z, idx) => {
        const color = ZONE_COLORS[idx % ZONE_COLORS.length];
        const isSelected = selectedZoneId === z.id;
        const isEnabled = Boolean(z.enabled);
        const points = z.points || (z.x !== undefined ? [
          [z.x, z.y],
          [z.x + z.width, z.y],
          [z.x + z.width, z.y + z.height],
          [z.x, z.y + z.height]
        ] : []);

        if (!points || points.length < 3) return null;
        const centroid = getCentroid(points);

        return (
          <div
            key={`label-${z.id}`}
            className={`polygon-zone-tag ${isSelected ? 'selected' : ''} ${!isEnabled ? 'disabled' : ''}`}
            style={{
              left: `${centroid.x * 100}%`,
              top: `${centroid.y * 100}%`,
              transform: 'translate(-50%, -50%)',
              borderColor: isEnabled ? color.border : 'rgba(157, 180, 198, 0.4)',
              color: isEnabled ? color.text : '#9DB4C6'
            }}
            onClick={(e) => {
              e.stopPropagation();
              if (onSelectZone) onSelectZone(z);
            }}
          >
            <span className="zone-tag-dot" style={{ backgroundColor: isEnabled ? color.dot : '#9DB4C6' }}></span>
            <span className="zone-tag-text">{z.name ? z.name.toUpperCase() : `ZONE ${idx + 1}`}</span>
          </div>
        );
      })}

      {/* 2. Draft / Edit Draggable Vertex Handles */}
      {draftPoints.map((p, idx) => {
        const isFirst = idx === 0;
        const isNearFirst = !isDraftClosed && draftPoints.length >= 3 && hoverPoint && isNearFirstPoint(hoverPoint, draftPoints);

        return (
          <div
            key={`vertex-${idx}`}
            className={`polygon-vertex-handle ${isFirst && isNearFirst ? 'snap-target' : ''} ${draggingVertexIndex === idx ? 'dragging' : ''}`}
            style={{
              left: `${p[0] * 100}%`,
              top: `${p[1] * 100}%`
            }}
            onPointerDown={(e) => {
              e.stopPropagation();
              e.preventDefault();
              setDraggingVertexIndex(idx);
            }}
            title={isFirst && !isDraftClosed && draftPoints.length >= 3 ? 'Click to close polygon' : `Vertex #${idx + 1} (Drag to adjust)`}
          >
            <span className="vertex-dot">{idx + 1}</span>
          </div>
        );
      })}

      {/* 3. Draft Zone Centroid Label */}
      {isDraftClosed && draftPoints.length >= 3 && (
        <div
          className="polygon-zone-tag draft-tag"
          style={{
            left: `${getCentroid(draftPoints).x * 100}%`,
            top: `${getCentroid(draftPoints).y * 100}%`,
            transform: 'translate(-50%, -50%)'
          }}
        >
          <span className="zone-tag-dot pulse"></span>
          <span className="zone-tag-text">CUSTOM POLYGON ZONE</span>
        </div>
      )}
    </div>
  );
}
