"""
Listens for Windows power events (sleep/wake) and runs the ALEX greeting.
Designed to run silently in the background.
"""

import os
import sys
import time
import subprocess
import win32api
import win32con
import win32gui

# Power broadcast constants
WM_POWERBROADCAST = 0x021B
PBT_APMRESUMESUSPEND = 0x0007

# Project root
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MAIN_SCRIPT = os.path.join(PROJECT_ROOT, "main.py")

class SleepWakeListener:
    def __init__(self):
        # Register a window class
        message_map = {
            WM_POWERBROADCAST: self.on_power_broadcast
        }
        
        wc = win32gui.WNDCLASS()
        wc.lpfnWndProc = message_map
        wc.lpszClassName = "AlexSleepWakeListener"
        wc.hInstance = win32api.GetModuleHandle(None)
        
        try:
            self.class_atom = win32gui.RegisterClass(wc)
        except Exception:
            # Already registered
            pass

        # Create a hidden window to receive messages
        self.hwnd = win32gui.CreateWindow(
            wc.lpszClassName,
            "Alex Sleep/Wake Listener",
            0,
            0, 0, 0, 0,
            0, 0, wc.hInstance, None
        )

    def on_power_broadcast(self, hwnd, msg, wparam, lparam):
        if wparam == PBT_APMRESUMESUSPEND:
            print("System woke from sleep! Triggering greeting...")
            self.trigger_greeting()
        return True

    def trigger_greeting(self):
        """Launch the greeting in a separate process."""
        python_exe = sys.executable
        if python_exe.lower().endswith("python.exe"):
            python_exe = python_exe.replace("python.exe", "pythonw.exe")
            
        try:
            subprocess.Popen(
                [python_exe, MAIN_SCRIPT, "--greet"],
                cwd=PROJECT_ROOT,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
        except Exception as e:
            print(f"Failed to launch greeting: {e}")

    def run(self):
        print("Listening for Windows sleep/wake events...")
        # We also trigger a greeting right away when this script starts 
        # (e.g. at PC boot/logon)
        self.trigger_greeting()
        
        # Message loop
        win32gui.PumpMessages()


if __name__ == "__main__":
    listener = SleepWakeListener()
    listener.run()
