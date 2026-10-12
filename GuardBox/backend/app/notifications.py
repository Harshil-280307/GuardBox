"""
Veronic GuardBox - Notification Abstraction Service
Handles notification dispatch placeholders for Phase 1.
Real GSM / SMS / WhatsApp / Email hardware & webhooks are scheduled for Phase 2.
"""

from typing import Dict, Any, Optional
from app.database import log_system_event


class NotificationService:
    def __init__(self):
        self.enabled = False  # Phase 1: No live cellular or internet notifications

    def notify_security_event(
        self,
        event_id: int,
        event_type: str,
        motion_area: float,
        timestamp: str
    ) -> Dict[str, Any]:
        """
        Placeholder for Phase 2 GSM / SMS / WhatsApp alert dispatch.
        
        Phase 2 Roadmap:
        1. Connect SIM800L / SIM7600 GSM cellular modem via USB UART on Windows COM port.
        2. Format AT+CMGS SMS commands with event timestamp and motion area.
        3. Trigger direct emergency dial / WhatsApp business webhook.
        """
        message = (
            f"[NOTIFICATION PLACEHOLDER] Event #{event_id} ({event_type}) detected. "
            f"No live GSM or SMS connected in Phase 1 prototype."
        )
        
        # Log to database for audit trail
        log_system_event("NOTIF_SIMULATION", message)
        
        return {
            "status": "simulated",
            "message": message,
            "disclaimer": "Phase 1 Prototype: No real GSM, SMS, or external alerts dispatched."
        }


# Global Notification Service singleton
notification_service = NotificationService()
