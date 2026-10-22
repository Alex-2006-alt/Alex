"""
ALEX — System Tray Application
Shows a 🤖 icon in the Windows system tray.
Right-click menu lets the user control Alex without a visible window.

Requires:  pystray>=0.19   Pillow>=10.0

The tray app is the outer shell for background mode.  It owns:
  • The full Assistant (wake word + voice loop) running in a daemon thread
  • The HotkeyListener (Win+Shift+A → screenshot + vision)
"""

import sys
import threading
import time
import io
from pathlib import Path

from utils.logger import log
import config


# ─── Tray icon image ─────────────────────────────────────────────────────────

def _load_tray_icon():
    """
    Load the tray icon.  Tries gui/assets/tray_icon.png first, then
    synthesises a simple coloured circle so the app works without assets.
    """
    icon_path = Path(__file__).parent.parent / "gui" / "assets" / "tray_icon.png"

    if icon_path.exists():
        from PIL import Image
        return Image.open(str(icon_path)).resize((64, 64))

    # Fallback: draw a green circle with a white "A"
    try:
        from PIL import Image, ImageDraw, ImageFont
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse([2, 2, 62, 62], fill=(30, 180, 100), outline=(255, 255, 255), width=3)
        draw.text((22, 18), "A", fill=(255, 255, 255))
        return img
    except Exception:
        # Ultra-fallback: 16x16 green square
        from PIL import Image
        return Image.new("RGB", (16, 16), color=(30, 180, 100))


# ─── TrayApp ─────────────────────────────────────────────────────────────────

class TrayApp:
    """
    System-tray entry point for background mode.

    Usage::

        app = TrayApp()
        app.run()           # blocks until the user clicks Exit
    """

    def __init__(self):
        self._assistant = None
        self._hotkey_listener = None
        self._assistant_thread: threading.Thread | None = None
        self._paused = False
        self._icon = None

    # ─── Startup ──────────────────────────────────────────────────────────────

    def run(self):
        """Start everything and enter the pystray event loop (blocks)."""
        try:
            import pystray
        except ImportError:
            log.error(
                "pystray is not installed. Run: pip install pystray\n"
                "Falling back to headless mode (no tray icon)."
            )
            self._start_assistant()
            self._start_hotkey()
            try:
                while True:
                    time.sleep(60)
            except KeyboardInterrupt:
                self._shutdown()
            return

        log.info("🖥️  Starting tray app...")

        # Start assistant + hotkey in background
        self._start_assistant()
        self._start_hotkey()

        # Build tray menu
        menu = pystray.Menu(
            pystray.MenuItem("✅ Alex is running", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("🎤 Listen now",        self._menu_listen),
            pystray.MenuItem("📸 Screenshot + Ask",   self._menu_vision),
            pystray.MenuItem("⏸ Pause / Resume",     self._menu_toggle_pause),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("❌ Exit",               self._menu_exit),
        )

        self._icon = pystray.Icon(
            name="ALEX",
            icon=_load_tray_icon(),
            title=f"{config.ASSISTANT_NAME} — Running",
            menu=menu,
        )

        log.info(f"🤖 {config.ASSISTANT_NAME} tray icon active")
        self._icon.run()   # blocks

    # ─── Menu callbacks ───────────────────────────────────────────────────────

    def _menu_listen(self, icon, item):
        """Manually trigger one listen-think-speak cycle."""
        if self._paused:
            return
        threading.Thread(target=self._do_listen_cycle, daemon=True).start()

    def _menu_vision(self, icon, item):
        """Immediately trigger the screenshot + vision pipeline."""
        if self._hotkey_listener:
            threading.Thread(
                target=self._hotkey_listener._run_vision_pipeline,
                daemon=True,
            ).start()

    def _menu_toggle_pause(self, icon, item):
        self._paused = not self._paused
        state = "paused" if self._paused else "resumed"
        log.info(f"⏸ Alex {state} via tray menu")
        try:
            from core.speaker import Speaker
            Speaker().say(f"Alex is now {state}.")
        except Exception:
            pass

    def _menu_exit(self, icon, item):
        log.info("👋 Exit requested via tray menu")
        self._shutdown()
        icon.stop()

    # ─── Internal ─────────────────────────────────────────────────────────────

    def _start_assistant(self):
        """Start the full Assistant in a background daemon thread."""
        def _run():
            try:
                from core.assistant import Assistant
                self._assistant = Assistant(
                    use_wake_word=True,
                    input_mode="voice",
                )
                if config.SCREEN_VISION_ENABLED:
                    # Wire the assistant into the hotkey listener so vision
                    # requests go through the full pipeline (memory, tools, etc.)
                    if self._hotkey_listener:
                        self._hotkey_listener._assistant = self._assistant

                self._assistant.run()
            except Exception as e:
                log.error(f"Assistant thread crashed: {e}", exc_info=True)

        self._assistant_thread = threading.Thread(
            target=_run,
            name="AlexAssistant",
            daemon=True,
        )
        self._assistant_thread.start()
        log.info("🎤 Assistant thread started")

    def _start_hotkey(self):
        """Start the global hotkey listener."""
        if not config.SCREEN_VISION_ENABLED:
            log.info("Screen vision disabled — hotkey not registered")
            return
        try:
            from core.speaker import Speaker
            from core.listener import Listener
            from core.hotkey_listener import HotkeyListener

            self._hotkey_listener = HotkeyListener(
                speaker=Speaker(),
                listener=Listener(),
                assistant=None,  # will be set when assistant is ready
            )
            self._hotkey_listener.start()
        except Exception as e:
            log.error(f"HotkeyListener start failed: {e}")

    def _do_listen_cycle(self):
        """Run one voice interaction cycle (for the 'Listen now' menu item)."""
        if self._assistant:
            try:
                user_input = self._assistant.listener.listen()
                if user_input:
                    self._assistant.process_text_full(user_input)
            except Exception as e:
                log.error(f"Manual listen cycle failed: {e}")

    def _shutdown(self):
        """Gracefully stop the assistant and hotkey listener."""
        if self._hotkey_listener:
            self._hotkey_listener.stop()
        log.info("👋 Alex background service stopped")
