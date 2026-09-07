"""
ALEX — Command Dispatcher
Maps short text commands to handler functions.
Falls through to None for unrecognized text so the LLM brain handles it.
"""

import datetime
import subprocess
import webbrowser
from typing import Callable

from utils.logger import log


class CommandDispatcher:
    """
    Lightweight command router for Alex.

    Registered handlers are tried in order against the user's text.
    If a handler matches, its result string is returned.
    If nothing matches, ``dispatch()`` returns ``None`` so the caller
    can fall through to the LLM pipeline.
    """

    def __init__(self, register_builtins: bool = True):
        # {canonical_name: (handler_fn, [aliases])}
        self._commands: dict[str, tuple[Callable[[str], str], list[str]]] = {}

        if register_builtins:
            self._register_builtins()

    # ─── PUBLIC API ──────────────────────────────────────────────────────────

    def register(
        self,
        name: str,
        handler: Callable[[str], str],
        aliases: list[str] | None = None,
    ) -> None:
        """
        Register a command handler.

        Args:
            name: Canonical command name (e.g. ``"say_time"``).
            handler: ``fn(arguments_text) -> result_string``.
                     The handler receives everything *after* the matched
                     command prefix, stripped.
            aliases: Optional alternative trigger words.
        """
        self._commands[name.lower()] = (handler, [a.lower() for a in (aliases or [])])
        log.debug(f"📋 Command registered: {name}")

    def dispatch(self, text: str) -> str | None:
        """
        Try to match *text* against registered commands.

        Returns:
            A result string if a command matched, or ``None`` if the text
            should be forwarded to the LLM.
        """
        text_lower = text.lower().strip()
        if not text_lower:
            return None

        for name, (handler, aliases) in self._commands.items():
            triggers = [name] + aliases
            for trigger in triggers:
                if text_lower == trigger or text_lower.startswith(trigger + " "):
                    # Extract the arguments portion after the trigger word
                    args_text = text[len(trigger):].strip() if len(text) > len(trigger) else ""
                    try:
                        result = handler(args_text)
                        log.info(f"⚡ Command dispatched: {name} → {result[:80] if result else '(empty)'}")
                        return result
                    except Exception as e:
                        log.error(f"Command '{name}' failed: {e}")
                        return f"Error running command '{name}': {e}"

        return None  # No command matched — fall through to LLM

    def list_commands(self) -> list[str]:
        """Return sorted list of registered command names."""
        return sorted(self._commands.keys())

    # ─── BUILT-IN HANDLERS ───────────────────────────────────────────────────

    def _register_builtins(self) -> None:
        """Register the default built-in command handlers."""
        self.register("say_time", self._handle_say_time, aliases=["time", "what time"])
        self.register("open_url", self._handle_open_url, aliases=["open url", "browse"])
        self.register("run", self._handle_run, aliases=["shell", "exec"])

    @staticmethod
    def _handle_say_time(_args: str) -> str:
        """Return the current date and time as a spoken sentence."""
        now = datetime.datetime.now()
        return now.strftime("It's %A, %B %d, %Y — %I:%M %p.")

    @staticmethod
    def _handle_open_url(args: str) -> str:
        """Open a URL in the default browser, and bring it to the front."""
        from tools.web_tools import open_url, _page_hint
        from utils.window_utils import focus_browser

        url = args.strip()
        if not url:
            return "Please provide a URL. Example: open_url https://google.com"
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        if not open_url(url):
            return f"I couldn't open {url} in a browser."
        focus_browser(_page_hint(url))
        return f"Opening {url} in your browser."

    @staticmethod
    def _handle_run(args: str) -> str:
        """Execute a shell command and return its output."""
        command = args.strip()
        if not command:
            return "Please provide a command to run. Example: run dir"
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            output = result.stdout.strip() or result.stderr.strip() or "(no output)"
            # Truncate long output for speech
            if len(output) > 500:
                output = output[:500] + "... (truncated)"
            return output
        except subprocess.TimeoutExpired:
            return f"Command timed out after 30 seconds: {command}"
        except Exception as e:
            return f"Error running command: {e}"
