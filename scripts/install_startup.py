"""
ALEX — Windows Startup Registration
=====================================
Registers alex_service.pyw to run silently at Windows login.

Two methods (tried in order, most reliable first):
  1. Task Scheduler  — most reliable, survives UAC, shows in taskschd.msc
  2. Registry Run key — simpler, no admin required, but UAC can block it

Usage:
    python scripts/install_startup.py           # install
    python scripts/install_startup.py --remove  # uninstall
    python scripts/install_startup.py --status  # check if installed
"""

import sys
import os
import subprocess
import argparse
from pathlib import Path

# ─── Paths ────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SERVICE_SCRIPT = PROJECT_ROOT / "alex_service.pyw"

TASK_NAME = "AlexBackgroundService"
REG_KEY   = r"Software\Microsoft\Windows\CurrentVersion\Run"
REG_VALUE = "AlexAssistant"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _pythonw_exe() -> str:
    """Return the pythonw.exe path (no-console Python executable)."""
    exe = sys.executable
    if exe.lower().endswith("python.exe"):
        candidate = exe.replace("python.exe", "pythonw.exe")
        if Path(candidate).exists():
            return candidate
    return exe  # already pythonw, or running from venv


def _build_command() -> str:
    pythonw = _pythonw_exe()
    return f'"{pythonw}" "{SERVICE_SCRIPT}"'


# ─── Task Scheduler ───────────────────────────────────────────────────────────

def install_task_scheduler() -> bool:
    """Create a Task Scheduler task that runs Alex at user logon."""
    cmd = _build_command()
    xml = f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>ALEX Personal AI Assistant — Background Service</Description>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{_pythonw_exe()}</Command>
      <Arguments>"{SERVICE_SCRIPT}"</Arguments>
      <WorkingDirectory>{PROJECT_ROOT}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>"""

    # Write XML to a temp file
    import tempfile
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".xml", delete=False, encoding="utf-16"
    ) as f:
        f.write(xml)
        xml_path = f.name

    try:
        result = subprocess.run(
            ["schtasks", "/Create", "/TN", TASK_NAME,
             "/XML", xml_path, "/F"],
            capture_output=True, text=True
        )
        return result.returncode == 0
    finally:
        os.unlink(xml_path)


def remove_task_scheduler() -> bool:
    result = subprocess.run(
        ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"],
        capture_output=True, text=True
    )
    return result.returncode == 0


def status_task_scheduler() -> bool:
    result = subprocess.run(
        ["schtasks", "/Query", "/TN", TASK_NAME],
        capture_output=True, text=True
    )
    return result.returncode == 0


# ─── Registry Run key ─────────────────────────────────────────────────────────

def install_registry() -> bool:
    """Add Alex to HKCU\...\Run (no admin required)."""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, REG_KEY,
            0, winreg.KEY_SET_VALUE
        )
        winreg.SetValueEx(key, REG_VALUE, 0, winreg.REG_SZ, _build_command())
        winreg.CloseKey(key)
        return True
    except Exception as e:
        print(f"Registry install failed: {e}")
        return False


def remove_registry() -> bool:
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, REG_KEY,
            0, winreg.KEY_SET_VALUE
        )
        winreg.DeleteValue(key, REG_VALUE)
        winreg.CloseKey(key)
        return True
    except Exception as e:
        print(f"Registry remove failed: {e}")
        return False


def status_registry() -> bool:
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY)
        val, _ = winreg.QueryValueEx(key, REG_VALUE)
        winreg.CloseKey(key)
        return bool(val)
    except Exception:
        return False


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Register or remove Alex from Windows startup"
    )
    parser.add_argument("--remove", action="store_true", help="Remove from startup")
    parser.add_argument("--status", action="store_true", help="Check registration status")
    args = parser.parse_args()

    if args.status:
        ts = status_task_scheduler()
        reg = status_registry()
        print(f"Task Scheduler : {'✅ installed' if ts else '❌ not found'}")
        print(f"Registry Run   : {'✅ installed' if reg else '❌ not found'}")
        return

    if args.remove:
        ts_ok  = remove_task_scheduler()
        reg_ok = remove_registry()
        print(f"Task Scheduler : {'✅ removed' if ts_ok else '⚠️  not found'}")
        print(f"Registry Run   : {'✅ removed' if reg_ok else '⚠️  not found'}")
        print("\nAlex will no longer start at login.")
        return

    # ── Install ──────────────────────────────────────────────────────────────
    print(f"Installing {TASK_NAME} startup task...")

    ts_ok = install_task_scheduler()
    if ts_ok:
        print("✅ Task Scheduler task created — Alex will start silently at login.")
    else:
        print("⚠️  Task Scheduler failed (may need admin). Trying registry...")
        reg_ok = install_registry()
        if reg_ok:
            print("✅ Registry Run key set — Alex will start at login.")
        else:
            print("❌ Both methods failed. See errors above.")
            sys.exit(1)

    print(f"\nCommand: {_build_command()}")
    print("To remove:  python scripts/install_startup.py --remove")


if __name__ == "__main__":
    main()
