"""
Veronic GuardBox - Alarm Service Abstraction (Phase 1 Simulated)
Simulates security alarm state without activating physical hardware.
Clearly marks all triggers as simulated prototypes.
"""

from datetime import datetime, timezone
from typing import Dict, Any, Optional
from app.database import log_system_event


class AlarmService:
    def __init__(self):
        self._is_active: bool = False
        self._triggered_at: Optional[str] = None
        self._trigger_reason: Optional[str] = None
        self._is_simulation: bool = True
        self._notice: str = "SIMULATED ALARM — NO PHYSICAL SIREN CONNECTED"

    @property
    def is_active(self) -> bool:
        return self._is_active

    def get_status(self) -> Dict[str, Any]:
        """Return current simulated alarm status."""
        return {
            "is_active": self._is_active,
            "triggered_at": self._triggered_at,
            "trigger_reason": self._trigger_reason,
            "is_simulation": True,
            "disclaimer": self._notice
        }

    def trigger_simulated_alarm(self, reason: str = "Motion threshold exceeded") -> Dict[str, Any]:
        """Trigger simulated alarm in software only."""
        self._is_active = True
        self._triggered_at = datetime.now(timezone.utc).isoformat()
        self._trigger_reason = f"[SIMULATION] {reason}"
        
        log_system_event(
            log_type="ALARM_SIMULATION",
            message=f"{self._notice}: Triggered by '{reason}'"
        )
        
        return self.get_status()

    def stop_alarm(self) -> Dict[str, Any]:
        """Silence/stop the simulated alarm."""
        was_active = self._is_active
        self._is_active = False
        self._triggered_at = None
        self._trigger_reason = None
        
        if was_active:
            log_system_event(
                log_type="ALARM_SIMULATION",
                message=f"{self._notice}: Silenced/Reset by user"
            )
            
        return self.get_status()

    def test_simulated_alarm(self) -> Dict[str, Any]:
        """Execute a manual simulated alarm test."""
        return self.trigger_simulated_alarm(reason="Manual test via dashboard /alarm/test")


# Global Alarm Service singleton
alarm_service = AlarmService()
