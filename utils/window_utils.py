"""
Window utilities for ALEX.
Brings background windows to the foreground after opening a URL or app.

Windows deliberately refuses SetForegroundWindow from a process that does not
own the current foreground window. The reliable way around it is
AttachThreadInput, which is what _force_foreground does; the old Alt-key trick
is kept only as a last resort because it injects a real Alt keystroke and can
pop menus in whatever happens to be focused.
"""

import time
import ctypes

from utils.logger import log

try:
    import pygetwindow
    _HAS_PYGETWINDOW = True
except ImportError:
    _HAS_PYGETWINDOW = False


# Window-title suffixes that identify a browser window. A page title alone is
# unreliable — a cold YouTube tab is titled "New Tab" for a second or two —
# so we can always fall back to "whatever browser window exists".
BROWSER_MARKERS = (
    "google chrome",
    "microsoft edge",
    "mozilla firefox",
    "brave",
    "opera",
    "vivaldi",
    "chromium",
)

SW_RESTORE = 9
ASFW_ANY = -1


def allow_foreground_for_any_process():
    """
    Let the process we're about to launch (the browser) steal focus.

    Without this, Windows' foreground lock means a browser launched by
    os.startfile opens its tab behind whatever the user is looking at.
    """
    try:
        ctypes.windll.user32.AllowSetForegroundWindow(ASFW_ANY)
    except Exception as e:
        log.debug(f"AllowSetForegroundWindow failed: {e}")


def _force_foreground(hwnd) -> bool:
    """Raise hwnd, working around the foreground lock. Returns True on success."""
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    try:
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)

        if user32.GetForegroundWindow() == hwnd:
            return True

        current = kernel32.GetCurrentThreadId()
        foreground = user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), None)
        target = user32.GetWindowThreadProcessId(hwnd, None)

        attached = []
        try:
            for thread in (foreground, target):
                if thread and thread != current and user32.AttachThreadInput(current, thread, True):
                    attached.append(thread)

            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
            user32.SetActiveWindow(hwnd)
        finally:
            for thread in attached:
                user32.AttachThreadInput(current, thread, False)

        if user32.GetForegroundWindow() == hwnd:
            return True

        # Last resort: the Alt-key trick. Injects a real keystroke, so it is
        # only used when the well-behaved path has already failed.
        VK_MENU, EXTENDED, KEYUP = 0x12, 0x0001, 0x0002
        user32.keybd_event(VK_MENU, 0, EXTENDED, 0)
        user32.keybd_event(VK_MENU, 0, EXTENDED | KEYUP, 0)
        user32.SetForegroundWindow(hwnd)
        return user32.GetForegroundWindow() == hwnd

    except Exception as e:
        log.debug(f"_force_foreground failed: {e}")
        return False


def _visible_windows():
    if not _HAS_PYGETWINDOW:
        return []
    try:
        return [w for w in pygetwindow.getAllWindows() if w.title and w.title.strip()]
    except Exception:
        return []


def focus_window(title_substring: str, timeout: float = 8.0) -> bool:
    """
    Wait for a window whose title contains the substring, then raise it.

    Returns True if a matching window was found and raised.
    """
    if not _HAS_PYGETWINDOW:
        log.debug("pygetwindow not installed — skipping focus_window")
        return False

    needle = title_substring.lower()
    deadline = time.time() + timeout

    while time.time() < deadline:
        for win in _visible_windows():
            if needle in win.title.lower():
                log.info(f"🪟 Bringing window to front: '{win.title}'")
                if _force_foreground(win._hWnd):
                    return True
                try:
                    win.activate()
                    return True
                except Exception:
                    return False
        time.sleep(0.25)

    log.debug(f"No window matching '{title_substring}' within {timeout}s")
    return False


def focus_browser(expected_title: str | None = None, timeout: float = 10.0) -> bool:
    """
    Bring the browser forward after opening a URL.

    Tries the page title first (most precise), then falls back to any browser
    window. The fallback is what makes this work for slow pages: YouTube's tab
    is titled "New Tab" for the first second or two, which is exactly when the
    old title-only match gave up and left the tab hidden behind ALEX.
    """
    if not _HAS_PYGETWINDOW:
        return False

    needle = expected_title.lower() if expected_title else None
    deadline = time.time() + timeout
    browser_window = None

    while time.time() < deadline:
        windows = _visible_windows()

        if needle:
            for win in windows:
                if needle in win.title.lower():
                    log.info(f"🪟 Focusing browser on '{win.title}'")
                    return _force_foreground(win._hWnd) or _safe_activate(win)

        # Remember a browser window in case the title never resolves
        if browser_window is None:
            for win in windows:
                if any(marker in win.title.lower() for marker in BROWSER_MARKERS):
                    browser_window = win
                    break

        if not needle and browser_window is not None:
            break

        time.sleep(0.25)

    if browser_window is not None:
        log.info(f"🪟 Focusing browser window '{browser_window.title}' (page title never matched)")
        return _force_foreground(browser_window._hWnd) or _safe_activate(browser_window)

    log.warning("Could not find a browser window to focus")
    return False


def _safe_activate(win) -> bool:
    try:
        win.activate()
        return True
    except Exception:
        return False
