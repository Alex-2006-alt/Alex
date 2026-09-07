"""
ALEX — Reminder Plugin
Set timers and reminders that alert you after a specified time.
"""

import threading
import time
from datetime import datetime, timedelta

from plugins.plugin_loader import PluginBase
from utils.logger import log


class ReminderPlugin(PluginBase):
    """Set and manage reminders."""

    name = "reminder"
    description = "Set timers and reminders that alert after a specified time"
    actions = ["set_reminder"]

    def __init__(self):
        self.active_reminders: list[dict] = []
        self._speaker = None

    def execute(self, params: dict) -> str:
        """
        Set a reminder.

        Params:
            message: Reminder message
            minutes: Minutes from now (default: 5)
        """
        message = params.get("message", "Time's up!")
        minutes = int(params.get("minutes", 5))

        trigger_time = datetime.now() + timedelta(minutes=minutes)

        reminder = {
            "message": message,
            "minutes": minutes,
            "trigger_time": trigger_time,
        }

        self.active_reminders.append(reminder)

        # Start a background timer
        timer = threading.Timer(minutes * 60, self._trigger_reminder, args=[reminder])
        timer.daemon = True
        timer.start()

        log.info(f"⏰ Reminder set: '{message}' in {minutes} minutes")

        if minutes == 1:
            return f"Got it! I'll remind you in 1 minute: {message}"
        else:
            return f"Got it! I'll remind you in {minutes} minutes: {message}"

    def _trigger_reminder(self, reminder: dict):
        """Called when a reminder is due."""
        message = reminder["message"]
        log.info(f"⏰ REMINDER: {message}")

        print(f"\n{'='*50}")
        print(f"  ⏰ REMINDER: {message}")
        print(f"{'='*50}\n")

        # Try to speak the reminder
        try:
            from core.speaker import Speaker
            speaker = Speaker()
            speaker.say(f"Reminder! {message}")
        except Exception as e:
            log.error(f"Could not speak reminder: {e}")

        # Remove from active list
        if reminder in self.active_reminders:
            self.active_reminders.remove(reminder)

    def get_active_reminders(self) -> list[dict]:
        """List all active reminders."""
        now = datetime.now()
        return [
            {
                "message": r["message"],
                "time_left": str(r["trigger_time"] - now).split(".")[0],
            }
            for r in self.active_reminders
            if r["trigger_time"] > now
        ]
