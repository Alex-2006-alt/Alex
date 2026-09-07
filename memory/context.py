"""
ALEX — Context Awareness
Tracks current PC state (active window, time of day, recent actions)
to provide richer context to the AI brain.
"""

import os
import platform
from datetime import datetime

from utils.logger import log


class Context:
    """
    Provides contextual awareness about the current PC state.
    This helps the AI brain give more relevant responses.
    """

    def __init__(self):
        self.recent_actions: list[str] = []
        self.max_recent = 10

    def get_context(self) -> dict:
        """Get the current context snapshot."""
        return {
            "time_of_day": self._get_time_period(),
            "current_time": datetime.now().strftime("%H:%M"),
            "current_date": datetime.now().strftime("%A, %B %d, %Y"),
            "active_window": self._get_active_window(),
            "recent_actions": self.recent_actions[-5:],
            "username": os.getenv("USERNAME", os.getenv("USER", "User")),
        }

    def add_action(self, action: str):
        """Record a recent action."""
        self.recent_actions.append(f"[{datetime.now().strftime('%H:%M')}] {action}")
        if len(self.recent_actions) > self.max_recent:
            self.recent_actions.pop(0)

    def get_context_string(self) -> str:
        """Get context as a human-readable string for the LLM."""
        ctx = self.get_context()
        parts = [
            f"Current time: {ctx['current_time']} ({ctx['time_of_day']})",
            f"Date: {ctx['current_date']}",
            f"User: {ctx['username']}",
        ]

        if ctx["active_window"]:
            parts.append(f"Active window: {ctx['active_window']}")

        if ctx["recent_actions"]:
            parts.append(f"Recent actions: {'; '.join(ctx['recent_actions'][-3:])}")

        return " | ".join(parts)

    def _get_time_period(self) -> str:
        """Get friendly time period."""
        hour = datetime.now().hour
        if 5 <= hour < 12:
            return "morning"
        elif 12 <= hour < 17:
            return "afternoon"
        elif 17 <= hour < 21:
            return "evening"
        else:
            return "night"

    def _get_active_window(self) -> str | None:
        """Get the title of the currently active window."""
        try:
            if platform.system() == "Windows":
                import ctypes
                user32 = ctypes.windll.user32
                hwnd = user32.GetForegroundWindow()
                length = user32.GetWindowTextLengthW(hwnd)
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                return buf.value if buf.value else None
        except Exception:
            pass
        return None
