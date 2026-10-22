"""
ALEX — Global Hotkey Listener
Registers a system-wide hotkey (default: Win+Shift+A) using the `keyboard`
library (works without admin rights on Windows).

When the hotkey fires:
  1. Take a screenshot of the active window
  2. Play an audio cue + show a brief toast so the user knows Alex is ready
  3. Listen for a voice question (or fall back to clipboard text)
  4. Pass the image + question to VisionBrain
  5. Speak and display the answer

The listener runs in a background daemon thread — it is started by
alex_service.pyw and by the tray app; it never blocks the main thread.
"""

import threading
import time

from utils.logger import log
import config


class HotkeyListener:
    """
    Registers a global hotkey and handles the screenshot → vision pipeline.

    Args:
        speaker   : A core.speaker.Speaker instance (for TTS output).
        listener  : A core.listener.Listener instance (for voice input).
        assistant : Optional Assistant reference (for process_text_full).
    """

    def __init__(self, speaker=None, listener=None, assistant=None):
        self._speaker = speaker
        self._listener = listener
        self._assistant = assistant
        self._hotkey = config.SCREEN_HOTKEY
        self._running = False
        self._thread: threading.Thread | None = None
        self._busy = threading.Event()  # prevents overlapping triggers

    # ─── Lifecycle ────────────────────────────────────────────────────────────

    def start(self):
        """Register the hotkey and start the listener thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._register_hotkey,
            name="AlexHotkeyListener",
            daemon=True,
        )
        self._thread.start()
        log.info(f"⌨️  Hotkey listener started ({self._hotkey})")

    def stop(self):
        """Unregister the hotkey."""
        self._running = False
        try:
            import keyboard
            keyboard.remove_hotkey(self._hotkey)
        except Exception:
            pass
        log.info("⌨️  Hotkey listener stopped")

    # ─── Internal ─────────────────────────────────────────────────────────────

    def _register_hotkey(self):
        try:
            import keyboard
        except ImportError:
            log.error(
                "keyboard package not installed — hotkey unavailable. "
                "Run: pip install keyboard"
            )
            return

        try:
            keyboard.add_hotkey(
                self._hotkey,
                callback=self._on_hotkey,
                suppress=False,
            )
            log.info(f"✅ Global hotkey registered: {self._hotkey}")
            keyboard.wait()          # blocks until keyboard.unhook_all() is called
        except Exception as e:
            log.error(f"Hotkey registration failed: {e}")

    def _on_hotkey(self):
        """Called by the keyboard library on each hotkey press."""
        if self._busy.is_set():
            log.debug("Hotkey ignored — already processing a screenshot request")
            return
        threading.Thread(
            target=self._handle_vision_request,
            name="AlexVisionRequest",
            daemon=True,
        ).start()

    def _handle_vision_request(self):
        """Full pipeline: screenshot → listen → vision → speak."""
        self._busy.set()
        try:
            self._run_vision_pipeline()
        finally:
            self._busy.clear()

    def _run_vision_pipeline(self):
        # 1. Notify user
        log.info("👁️  Hotkey triggered — starting vision pipeline")
        self._notify("Alex is looking at your screen...")
        if self._speaker:
            self._speaker.say("I can see your screen. What would you like to know?")

        # 2. Take screenshot (before the user starts talking to minimize delay)
        from tools.screen_tools import take_screenshot
        screenshot = take_screenshot(config.SCREEN_CAPTURE_MODE)

        if not screenshot:
            if self._speaker:
                self._speaker.say("Sorry, I couldn't capture the screen.")
            return

        # 3. Listen for question (voice preferred, clipboard fallback)
        question = self._get_question()
        if not question:
            if self._speaker:
                self._speaker.say("I didn't catch a question. Try again!")
            return

        log.info(f"👁️  Vision question: {question!r}")

        # 4. If an assistant is available, route through its full pipeline
        #    so memory, tool-use, etc. are available alongside the image.
        if self._assistant:
            # Inject the image into the conversation context
            answer = self._assistant.process_vision_request(
                question=question,
                image_b64=screenshot["image_b64"],
            )
        else:
            # Direct VisionBrain call (standalone / tray-only mode)
            try:
                from core.vision_brain import VisionBrain
                vb = VisionBrain()
                answer = vb.ask_about_image(screenshot["image_b64"], question)
            except Exception as e:
                answer = f"I had trouble analyzing the screen: {e}"

        # 5. Speak the answer
        log.info(f"👁️  Vision answer: {answer[:80]}...")
        if self._speaker:
            self._speaker.say(answer)

    def _get_question(self) -> str | None:
        """
        Try to get the user's question via voice; fall back to clipboard text.
        Returns None if neither produces anything useful.
        """
        # Voice input
        if self._listener:
            try:
                text = self._listener.listen()
                if text and text.strip():
                    return text.strip()
            except Exception as e:
                log.warning(f"Voice input failed in vision pipeline: {e}")

        # Clipboard fallback
        try:
            import pyperclip
            clip = pyperclip.paste()
            if clip and clip.strip() and len(clip.strip()) < 500:
                log.info("Using clipboard text as question")
                return clip.strip()
        except Exception:
            pass

        return None

    def _notify(self, message: str):
        """Show a desktop toast notification if possible."""
        try:
            from tools.notification_tools import notify
            notify({"title": "👁️ Alex Vision", "message": message})
        except Exception:
            pass
