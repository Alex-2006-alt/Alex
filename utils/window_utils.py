"""
Window utilities for ALEX.
Handles bringing background windows to the foreground.
"""

import time
import ctypes
import ctypes.wintypes

from utils.logger import log

try:
    import pygetwindow
    _HAS_PYGETWINDOW = True
except ImportError:
    _HAS_PYGETWINDOW = False


def focus_window(title_substring: str, timeout: float = 5.0) -> bool:
    """
    Wait for a window whose title contains the substring, then raise it.

    Uses the ``Alt-key`` trick so that ``SetForegroundWindow`` succeeds even
    when the caller (Flask server thread) is not the current foreground
    application — without this trick, Windows silently ignores the call.
    """
    if not _HAS_PYGETWINDOW:
        log.debug("pygetwindow not installed — skipping focus_window")
        return False

    user32 = ctypes.windll.user32
    start = time.time()

    while time.time() - start < timeout:
        try:
            windows = pygetwindow.getAllWindows()
        except Exception:
            time.sleep(0.5)
            continue

        for win in windows:
            if not win.title:
                continue
            if title_substring.lower() in win.title.lower():
                hwnd = win._hWnd
                log.info(f"Bringing window to front: '{win.title}'")

                try:
                    # Restore if minimized
                    if user32.IsIconic(hwnd):
                        user32.ShowWindow(hwnd, 9)  # SW_RESTORE

                    # --- Alt-key trick ---
                    # Press and release Alt so Windows thinks we are in an
                    # "active keyboard sequence" and allows the
                    # SetForegroundWindow call to succeed.
                    VK_MENU = 0x12
                    KEYEVENTF_EXTENDEDKEY = 0x0001
                    KEYEVENTF_KEYUP = 0x0002
                    user32.keybd_event(VK_MENU, 0, KEYEVENTF_EXTENDEDKEY, 0)
                    user32.keybd_event(VK_MENU, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)

                    user32.SetForegroundWindow(hwnd)
                except Exception as e:
                    log.debug(f"SetForegroundWindow failed: {e}")

                    # Last resort: pygetwindow's activate
                    try:
                        win.activate()
                    except Exception:
                        pass

                return True

        time.sleep(0.5)

    log.warning(f"Timeout: could not find a window matching '{title_substring}'")
    return False
