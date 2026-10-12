import React from 'react';
import { formatEventName, formatEventTime, formatEventDate } from '../utils/formatters';

export default function SecurityLogs({
  events = [],
  onAcknowledge,
  onViewSnapshot,
  compact = true
}) {
  const getStatusBadge = (status) => {
    switch (status) {
      case 'NEW':
        return <span className="status-badge badge-red">New event</span>;
      case 'ACKNOWLEDGED':
        return <span className="status-badge badge-blue">Acknowledged</span>;
      case 'WARNING':
        return <span className="status-badge badge-amber">Warning</span>;
      case 'FALSE_ALARM':
        return <span className="status-badge badge-neutral">False Alarm</span>;
      case 'RESOLVED':
        return <span className="status-badge badge-green">Resolved</span>;
      default:
        return <span className="status-badge badge-blue">{status || 'Info'}</span>;
    }
  };

  return (
    <div className="dashboard-card security-logs-card">
      <div className="card-header">
        <div className="card-header-left">
          <h3 className="card-title">Recent Security Events</h3>
          <span className="event-count-tag">{events.length}</span>
        </div>
      </div>

      <div className="card-body p-0">
        {events.length === 0 ? (
          <div className="empty-events-state">
            <div className="empty-icon-wrap">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <h4 className="empty-title">No security events yet</h4>
            <p className="empty-subtitle">Your recent system activity and motion alerts will appear here.</p>
          </div>
        ) : (
          <div className="table-responsive">
            <table className="security-events-table">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Camera</th>
                  <th>Area</th>
                  <th>Event</th>
                  <th>Status</th>
                  <th className="text-right">Action</th>
                </tr>
              </thead>
              <tbody>
                {events.map((ev) => {
                  const isNew = ev.status === 'NEW';
                  const hasSnapshot = Boolean(ev.snapshot_path);

                  return (
                    <tr key={ev.id} className={isNew ? 'row-new-alert' : ''}>
                      {/* Time */}
                      <td className="col-time">
                        <span className="time-primary">{formatEventTime(ev.timestamp)}</span>
                        {!compact && <span className="time-secondary">{formatEventDate(ev.timestamp)}</span>}
                      </td>

                      {/* Camera */}
                      <td className="col-camera">
                        <span className="camera-label-text">{ev.camera_name || 'Main Shop Camera'}</span>
                      </td>

                      {/* Area */}
                      <td className="col-area">
                        <span className="area-text">
                          {ev.zone_name || 'Main Area'}
                        </span>
                      </td>

                      {/* Event Title */}
                      <td className="col-event">
                        <div className="event-cell-wrap">
                          <span className="event-name">{formatEventName(ev.event_type)}</span>
                          {ev.system_mode === 'TEST_MODE' && (
                            <span className="test-flag-badge">TEST</span>
                          )}
                        </div>
                      </td>

                      {/* Status */}
                      <td className="col-status">
                        {getStatusBadge(ev.status)}
                      </td>

                      {/* Action */}
                      <td className="col-action text-right">
                        <div className="action-buttons-group">
                          {hasSnapshot && (
                            <button
                              type="button"
                              className="btn-table-icon"
                              title="View Snapshot"
                              onClick={() => onViewSnapshot && onViewSnapshot(ev)}
                            >
                              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.409a2.25 2.25 0 013.182 0l2.909 2.909m-18 3.75h16.5a1.5 1.5 0 001.5-1.5V6a1.5 1.5 0 00-1.5-1.5H3.75A1.5 1.5 0 002.25 6v12a1.5 1.5 0 001.5 1.5zm10.5-11.25h.008v.008h-.008V8.25zm.375 0a.375.375 0 11-.75 0 .375.375 0 01.75 0z" />
                              </svg>
                            </button>
                          )}

                          {isNew ? (
                            <button
                              type="button"
                              className="btn-table-action btn-ack"
                              onClick={() => onAcknowledge && onAcknowledge(ev.id)}
                            >
                              Acknowledge
                            </button>
                          ) : (
                            <span className="action-placeholder">—</span>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
