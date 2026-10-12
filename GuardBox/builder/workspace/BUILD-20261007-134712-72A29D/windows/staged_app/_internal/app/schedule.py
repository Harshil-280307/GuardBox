"""
Veronic GuardBox - Automated Shop Operating Schedule Manager (Phase 2)
Runs a background scheduler loop using local PC time to automatically
arm after store closing and disarm before opening.
"""

import time
import threading
import logging
from datetime import datetime
from typing import Dict, Any, Optional

from app.database import get_schedule_config, log_system_event

logger = logging.getLogger("guardbox.schedule")


class ShopScheduleService:
    def __init__(self):
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_triggered_minute: Optional[str] = None

    def get_config(self) -> Dict[str, Any]:
        """Retrieve the current schedule configuration."""
        return get_schedule_config()

    def update_config(
        self,
        enabled: Optional[bool] = None,
        opening_time: Optional[str] = None,
        closing_time: Optional[str] = None,
        auto_arm: Optional[bool] = None,
        auto_disarm: Optional[bool] = None
    ) -> Dict[str, Any]:
        """Update the schedule configuration."""
        from app.database import update_schedule_config
        return update_schedule_config(
            enabled=enabled,
            opening_time=opening_time,
            closing_time=closing_time,
            auto_arm=auto_arm,
            auto_disarm=auto_disarm
        )

    def start(self) -> None:
        """Start the background schedule worker."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._scheduler_loop, name="GuardBoxScheduleWorker", daemon=True)
        self._thread.start()
        logger.info("Shop schedule worker thread started")

    def stop(self) -> None:
        """Stop the background schedule worker."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        logger.info("Shop schedule worker thread stopped")

    def _scheduler_loop(self) -> None:
        """Periodic evaluation of local store hours against configured schedule."""
        from app.detection import motion_service

        while self._running:
            try:
                config = get_schedule_config()
                if config.get("enabled", False):
                    now_dt = datetime.now()
                    current_hhmm = now_dt.strftime("%H:%M")
                    current_key = now_dt.strftime("%Y-%m-%d %H:%M")

                    open_time = config.get("opening_time", "09:00")
                    close_time = config.get("closing_time", "20:00")
                    auto_arm = config.get("auto_arm", True)
                    auto_disarm = config.get("auto_disarm", True)

                    # Only evaluate if we haven't triggered in this exact minute
                    if self._last_triggered_minute != current_key:
                        # Auto-Disarm at opening time
                        if auto_disarm and current_hhmm == open_time:
                            if motion_service.current_mode in ("ARMED", "ARMING"):
                                motion_service.disarm()
                                self._last_triggered_minute = current_key
                                log_system_event(
                                    "SCHEDULE",
                                    f"Automated schedule: System disarmed for shop opening ({open_time})"
                                )

                        # Auto-Arm at closing time
                        elif auto_arm and current_hhmm == close_time:
                            if motion_service.current_mode == "DISARMED":
                                motion_service.arm(exit_delay_seconds=30)
                                self._last_triggered_minute = current_key
                                log_system_event(
                                    "SCHEDULE",
                                    f"Automated schedule: System armed for shop closing ({close_time})"
                                )

                time.sleep(15.0)

            except Exception as e:
                logger.error(f"Error in schedule loop: {e}", exc_info=False)
                time.sleep(30.0)


# Global schedule service singleton
schedule_service = ShopScheduleService()
