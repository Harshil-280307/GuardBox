/**
 * Formatters and helper utilities for GuardBox UI
 */

// Format raw backend event keys into shop-friendly titles
export function formatEventName(eventType) {
  switch (eventType) {
    case 'MOTION_DETECTED':
      return 'Motion detected';
    case 'SYSTEM_ARMED':
      return 'System armed';
    case 'SYSTEM_DISARMED':
      return 'System disarmed';
    case 'CAMERA_OFFLINE':
      return 'Camera offline';
    case 'CAMERA_RECONNECTED':
      return 'Camera reconnected';
    case 'ZONE_SAVED':
      return 'Detection zone saved';
    case 'ZONE_CLEARED':
      return 'Detection zone cleared';
    case 'ALARM_TRIGGERED':
      return 'Simulated alarm triggered';
    case 'TEST_EVENT':
      return 'Test motion event';
    default:
      return eventType?.replace(/_/g, ' ') || 'Event';
  }
}

// Format timestamp into clean local time HH:MM:SS
export function formatEventTime(isoString) {
  if (!isoString) return '—';
  try {
    const d = new Date(isoString);
    return d.toLocaleTimeString([], { hour12: false });
  } catch {
    return isoString;
  }
}

// Format timestamp into clean local date
export function formatEventDate(isoString) {
  if (!isoString) return '';
  try {
    const d = new Date(isoString);
    return d.toLocaleDateString();
  } catch {
    return '';
  }
}
