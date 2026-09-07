"""
Window utilities for ALEX.
Handles bringing background windows to the foreground.
"""

import time
import ctypes
import pygetwindow

from utils.logger import log

def focus_window(title_substring: str, timeout: float = 5.0) -> bool:
    """
    Wait for a window whose title contains the substring, then raise it.
    Uses pygetwindow, falling back to ctypes SetForegroundWindow if needed.
    """
    start = time.time()
    
    while time.time() - start < timeout:
        windows = pygetwindow.getAllWindows()
        for win in windows:
            if title_substring.lower() in win.title.lower():
                log.info(f"Bringing window to front: '{win.title}'")
                
                # Attempt 1: pygetwindow's activate
                try:
                    win.activate()
                except Exception as e:
                    log.debug(f"win.activate() failed: {e}")
                
                # Attempt 2: ctypes fallback (more robust when caller is not foreground)
                try:
                    user32 = ctypes.windll.user32
                    # Check if window is minimized
                    if user32.IsIconic(win._hWnd):
                        user32.ShowWindow(win._hWnd, 9) # SW_RESTORE
                    
                    user32.SetForegroundWindow(win._hWnd)
                except Exception as e:
                    log.debug(f"SetForegroundWindow failed: {e}")
                
                return True
                
        time.sleep(0.5)
        
    log.warning(f"Timeout: could not find a window matching '{title_substring}'")
    return False
