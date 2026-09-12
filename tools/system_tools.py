"""
ALEX — System Tools
Process management, app launching, system control, volume, clipboard.
"""

import os
import subprocess
import platform
import psutil

from core.tool_registry import tool, ToolResult, SafetyLevel
from utils.logger import log
import config


@tool(
    name="app_open",
    description="Open (launch) an application by name",
    parameters={
        "name": {"type": "string", "description": "Application name (e.g., 'chrome', 'notepad', 'vscode')", "required": True},
    },
    category="system",
)
def app_open(params: dict) -> ToolResult:
    name = params.get("name", "").lower().strip()
    if not name:
        return ToolResult(success=False, error="No app name provided")

    # Check registry
    app_path = str(config.DEFAULT_APP_REGISTRY.get(name, name))

    import threading
    from utils.window_utils import focus_window, allow_foreground_for_any_process

    def post_launch():
        # Map common command names to actual window title substrings
        window_title_map = {
            "vscode": "visual studio code",
            "vs code": "visual studio code",
            "chrome": "google chrome",
            "edge": "microsoft edge",
        }
        search_name = str(window_title_map.get(name, name))
        
        # Wait up to 5s for the window to appear and bring it to foreground
        focus_window(search_name, timeout=5.0)
        
        import sys
        # Launch companion widget
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        companion_script = os.path.join(project_root, "gui", "companion.py")
        
        python_exe = sys.executable
        if python_exe.lower().endswith("python.exe"):
            python_exe = python_exe.replace("python.exe", "pythonw.exe")
            
        try:
            # We don't need CREATE_NO_WINDOW when using pythonw.exe, and it can sometimes hide GUI windows
            subprocess.Popen([python_exe, companion_script, "--app", name])
        except Exception as e:
            log.error(f"Failed to launch companion widget: {e}")

    try:
        allow_foreground_for_any_process()
        os.startfile(app_path)
        log.info(f"🚀 Opened app: {name}")
        threading.Thread(target=post_launch, daemon=True).start()
        return ToolResult(success=True, message=f"Opening {name}...")
    except Exception:
        try:
            allow_foreground_for_any_process()
            subprocess.Popen(app_path, shell=True)
            threading.Thread(target=post_launch, daemon=True).start()
            return ToolResult(success=True, message=f"Launched {name}")
        except Exception as e:
            return ToolResult(success=False, error=f"Could not open '{name}': {e}")


@tool(
    name="app_close",
    description="Close/terminate a running application by name",
    parameters={
        "name": {"type": "string", "description": "Application/process name to close", "required": True},
    },
    category="system",
    safety=SafetyLevel.WARN,
)
def app_close(params: dict) -> ToolResult:
    name = params.get("name", "").lower().strip()
    if not name:
        return ToolResult(success=False, error="No app name provided")

    killed = []
    for proc in psutil.process_iter(["name", "pid"]):
        proc_name = proc.info["name"].lower()
        if name in proc_name or proc_name.startswith(name):
            try:
                proc.terminate()
                killed.append(proc.info["name"])
            except Exception:
                pass

    if killed:
        log.info(f"🛑 Closed: {', '.join(killed)}")
        return ToolResult(success=True, message=f"Closed: {', '.join(set(killed))}", data={"killed": killed})
    return ToolResult(success=False, error=f"No running process found matching '{name}'")


def _process_kill_summary(params: dict) -> str:
    name = params.get("name")
    pid = params.get("pid")
    if name:
        return f"Force kill the '{name}' process"
    elif pid:
        return f"Force kill process ID {pid}"
    return "Force kill a process"

@tool(
    name="process_kill",
    description="Force kill a process by name or PID",
    parameters={
        "name": {"type": "string", "description": "Process name", "required": False},
        "pid": {"type": "integer", "description": "Process ID (PID)", "required": False},
    },
    category="system",
    safety=SafetyLevel.CONFIRM,
    confirm_summary=_process_kill_summary,
)
def process_kill(params: dict) -> ToolResult:
    name = params.get("name", "").lower()
    pid = params.get("pid")

    killed = []
    for proc in psutil.process_iter(["name", "pid"]):
        if pid and proc.pid == int(pid):
            try:
                proc.kill()
                killed.append(f"PID {proc.pid}")
            except Exception:
                pass
        elif name and name in proc.info["name"].lower():
            try:
                proc.kill()
                killed.append(proc.info["name"])
            except Exception:
                pass

    if killed:
        return ToolResult(success=True, message=f"Force killed: {', '.join(set(killed))}")
    return ToolResult(success=False, error="No matching process found to kill")


@tool(
    name="process_list",
    description="List currently running processes with CPU and memory usage",
    parameters={
        "filter": {"type": "string", "description": "Filter processes by name (optional)", "required": False},
        "sort_by": {"type": "string", "description": "'cpu' or 'memory' (default: cpu)", "required": False},
        "limit": {"type": "integer", "description": "Max processes to return (default: 20)", "required": False},
    },
    category="system",
)
def process_list(params: dict) -> ToolResult:
    filter_name = params.get("filter", "").lower()
    sort_by = params.get("sort_by", "cpu")
    limit = int(params.get("limit", 20))

    procs = []
    for proc in psutil.process_iter(["name", "pid", "cpu_percent", "memory_percent"]):
        try:
            if filter_name and filter_name not in proc.info["name"].lower():
                continue
            procs.append({
                "name": proc.info["name"],
                "pid": proc.info["pid"],
                "cpu": round(proc.info["cpu_percent"] or 0, 1),
                "memory": round(proc.info["memory_percent"] or 0, 1),
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    key = "cpu" if sort_by == "cpu" else "memory"
    procs.sort(key=lambda x: x[key], reverse=True)
    procs = procs[:limit]

    lines = [f"Top {len(procs)} processes by {sort_by}:"]
    for p in procs:
        lines.append(f"  {p['name']} (PID {p['pid']}): CPU {p['cpu']}%, RAM {p['memory']}%")

    return ToolResult(success=True, message="\n".join(lines), data={"processes": procs})


@tool(
    name="system_volume",
    description="Control system volume: set level, mute, unmute, raise, or lower",
    parameters={
        "action": {"type": "string", "description": "'up', 'down', 'mute', 'unmute', or 'set'", "required": True},
        "amount": {"type": "integer", "description": "Volume change amount or target level 0-100 (default: 10)", "required": False},
    },
    category="system",
)
def system_volume(params: dict) -> ToolResult:
    action = params.get("action", "up").lower()
    amount = int(params.get("amount", 10))

    try:
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        from comtypes import CLSCTX_ALL
        import ctypes

        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)  # type: ignore
        volume = ctypes.cast(interface, ctypes.POINTER(IAudioEndpointVolume))

        current = int(volume.GetMasterVolumeLevelScalar() * 100)  # type: ignore

        if action == "mute":
            volume.SetMute(1, None)  # type: ignore
            return ToolResult(success=True, message="Volume muted")
        elif action == "unmute":
            volume.SetMute(0, None)  # type: ignore
            return ToolResult(success=True, message="Volume unmuted")
        elif action == "up":
            new_level = min(100, current + amount)
            volume.SetMasterVolumeLevelScalar(new_level / 100.0, None)  # type: ignore
            return ToolResult(success=True, message=f"Volume increased to {new_level}%")
        elif action == "down":
            new_level = max(0, current - amount)
            volume.SetMasterVolumeLevelScalar(new_level / 100.0, None)  # type: ignore
            return ToolResult(success=True, message=f"Volume decreased to {new_level}%")
        elif action == "set":
            volume.SetMasterVolumeLevelScalar(amount / 100.0, None)  # type: ignore
            return ToolResult(success=True, message=f"Volume set to {amount}%")

        return ToolResult(success=False, error=f"Unknown volume action: {action}")
    except Exception as e:
        log.error(f"Volume control error: {e}")
        return ToolResult(success=False, error=f"Volume control failed: {e}")


def _system_power_summary(params: dict) -> str:
    action = params.get("action", "lock").lower()
    delay = int(params.get("delay_seconds", getattr(config, "SHUTDOWN_GRACE_SECONDS", 30)))
    if action == "shutdown":
        return f"shut down this PC in {delay} seconds"
    elif action == "restart":
        return f"restart this PC in {delay} seconds"
    elif action == "sleep":
        return "put this PC to sleep"
    return f"{action} this PC"

@tool(
    name="system_power",
    description="Shutdown, restart, sleep, or lock the computer",
    parameters={
        "action": {"type": "string", "description": "'shutdown', 'restart', 'sleep', or 'lock'", "required": True},
        "delay_seconds": {"type": "integer", "description": "Delay in seconds (default: 30 for shutdown)", "required": False},
    },
    category="system",
    safety=SafetyLevel.CONFIRM,
    confirm_summary=_system_power_summary,
)
def system_power(params: dict) -> ToolResult:
    action = params.get("action", "lock").lower()
    
    # Use grace period for shutdown/restart if delay not explicitly set
    if "delay_seconds" not in params and action in ["shutdown", "restart"]:
        delay = getattr(config, "SHUTDOWN_GRACE_SECONDS", 30)
    else:
        delay = int(params.get("delay_seconds", 0))

    try:
        if action == "shutdown":
            os.system(f"shutdown /s /t {delay}")
            return ToolResult(success=True, message=f"Shutting down in {delay} seconds — say 'cancel shutdown' to stop me.")
        elif action == "restart":
            os.system(f"shutdown /r /t {delay}")
            return ToolResult(success=True, message=f"Restarting in {delay} seconds — say 'cancel shutdown' to stop me.")
        elif action == "sleep":
            subprocess.Popen("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
            return ToolResult(success=True, message="Going to sleep (Note: if hibernation is enabled in Windows, this will hibernate instead).")
        elif action == "lock":
            os.system("rundll32.exe user32.dll,LockWorkStation")
            return ToolResult(success=True, message="Workstation locked")
        else:
            return ToolResult(success=False, error=f"Unknown power action: {action}")
    except Exception as e:
        return ToolResult(success=False, error=f"Power action failed: {e}")


@tool(
    name="screenshot_capture",
    description="Take a screenshot of the entire screen or a selected region",
    parameters={
        "region": {"type": "string", "description": "'full' (default) or 'select' for region picker", "required": False},
        "save_path": {"type": "string", "description": "Optional path to save the screenshot", "required": False},
    },
    category="system",
)
def screenshot_capture(params: dict) -> ToolResult:
    import pyautogui
    from datetime import datetime

    region = params.get("region", "full")
    save_path = params.get("save_path", "")

    if not save_path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        save_dir = os.path.join(os.path.expanduser("~"), "Desktop")
        save_path = os.path.join(save_dir, f"screenshot_{ts}.png")

    try:
        if region == "select":
            import pyautogui
            screenshot = pyautogui.screenshot()
        else:
            screenshot = pyautogui.screenshot()

        screenshot.save(save_path)
        log.info(f"📸 Screenshot saved: {save_path}")
        return ToolResult(
            success=True,
            message=f"Screenshot saved to {save_path}",
            data={"path": save_path},
            artifacts=[save_path],
        )
    except Exception as e:
        return ToolResult(success=False, error=f"Screenshot failed: {e}")


@tool(
    name="keyboard_type",
    description="Type text at the current cursor position (simulates keyboard input)",
    parameters={
        "text": {"type": "string", "description": "Text to type", "required": True},
        "interval": {"type": "number", "description": "Delay between keystrokes in seconds (default: 0.05)", "required": False},
    },
    category="system",
)
def keyboard_type(params: dict) -> ToolResult:
    import pyautogui
    text = params.get("text", "")
    interval = float(params.get("interval", 0.05))
    if not text:
        return ToolResult(success=False, error="No text provided")
    try:
        pyautogui.write(text, interval=interval)
        return ToolResult(success=True, message=f"Typed: {text[:50]}")
    except Exception as e:
        return ToolResult(success=False, error=f"Type failed: {e}")


@tool(
    name="keyboard_press",
    description="Press a keyboard key or key combination (e.g., ctrl+c, alt+tab, enter)",
    parameters={
        "keys": {"type": "string", "description": "Key or combo like 'ctrl+c', 'alt+tab', 'enter', 'win'", "required": True},
    },
    category="system",
)
def keyboard_press(params: dict) -> ToolResult:
    import pyautogui
    keys = params.get("keys", "")
    if not keys:
        return ToolResult(success=False, error="No keys provided")
    try:
        key_list = [k.strip() for k in keys.split("+")]
        if len(key_list) == 1:
            pyautogui.press(key_list[0])
        else:
            pyautogui.hotkey(*key_list)
        return ToolResult(success=True, message=f"Pressed: {keys}")
    except Exception as e:
        return ToolResult(success=False, error=f"Key press failed: {e}")


@tool(
    name="clipboard_op",
    description="Read from or write to the system clipboard",
    parameters={
        "action": {"type": "string", "description": "'copy' (write to clipboard) or 'paste' (read from clipboard)", "required": True},
        "text": {"type": "string", "description": "Text to copy to clipboard (required for 'copy' action)", "required": False},
    },
    category="system",
)
def clipboard_op(params: dict) -> ToolResult:
    import pyperclip
    action = params.get("action", "paste")
    text = params.get("text", "")

    try:
        if action == "copy":
            pyperclip.copy(text)
            return ToolResult(success=True, message=f"Copied to clipboard: {text[:50]}", data={"text": text})
        elif action == "paste":
            content = pyperclip.paste()
            return ToolResult(success=True, message=f"Clipboard content: {content[:200]}", data={"text": content})
        else:
            return ToolResult(success=False, error=f"Unknown clipboard action: {action}")
    except Exception as e:
        return ToolResult(success=False, error=f"Clipboard error: {e}")


@tool(
    name="media_play",
    description="Control media playback: play, pause, next track, previous track",
    parameters={
        "action": {"type": "string", "description": "'play', 'pause', 'next', 'previous', 'stop'", "required": True},
    },
    category="system",
)
def media_play(params: dict) -> ToolResult:
    import pyautogui
    action = params.get("action", "play").lower()

    key_map = {
        "play": "playpause",
        "pause": "playpause",
        "next": "nexttrack",
        "previous": "prevtrack",
        "stop": "stop",
    }

    key = key_map.get(action)
    if not key:
        return ToolResult(success=False, error=f"Unknown media action: {action}")

    try:
        pyautogui.press(key)
        return ToolResult(success=True, message=f"Media: {action}")
    except Exception as e:
        return ToolResult(success=False, error=f"Media control failed: {e}")
