"""
Install desktop / Start Menu / terminal launchers for A.L.E.X.

    python scripts/install_launcher.py              # desktop + Start Menu shortcuts
    python scripts/install_launcher.py --path       # also make `alex` work in any terminal
    python scripts/install_launcher.py --all        # everything
    python scripts/install_launcher.py --uninstall  # remove everything it created

Nothing here needs administrator rights: shortcuts go in your own profile and
the PATH entry is the per-user one, not the system one.
"""

import argparse
import os
import sys
import winreg
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LAUNCHER = PROJECT_ROOT / "alex.bat"
SHORTCUT_NAME = "A.L.E.X.lnk"


def _folder(name: str) -> Path:
    """Resolve a Windows shell folder, honouring OneDrive redirection."""
    import ctypes.wintypes

    guids = {
        "desktop": "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}",
        "programs": "{A77F5D77-2E2B-44C3-A6A2-ABA601054A51}",
    }
    buf = ctypes.c_wchar_p()
    ctypes.windll.shell32.SHGetKnownFolderPath(
        ctypes.byref(_guid(guids[name])), 0, None, ctypes.byref(buf)
    )
    return Path(buf.value)


def _guid(text):
    import ctypes

    class GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", ctypes.c_ulong),
            ("Data2", ctypes.c_ushort),
            ("Data3", ctypes.c_ushort),
            ("Data4", ctypes.c_ubyte * 8),
        ]

    guid = GUID()
    ctypes.windll.ole32.CLSIDFromString(ctypes.c_wchar_p(text), ctypes.byref(guid))
    return guid


def make_shortcut(target_dir: Path) -> Path:
    """Create (or replace) the A.L.E.X shortcut in target_dir."""
    from win32com.client import Dispatch

    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / SHORTCUT_NAME

    shell = Dispatch("WScript.Shell")
    link = shell.CreateShortCut(str(path))
    link.TargetPath = str(LAUNCHER)
    link.WorkingDirectory = str(PROJECT_ROOT)
    link.Description = "A.L.E.X — Advanced Linguistic Executive System"
    # Python's own icon, so the shortcut isn't a blank page
    link.IconLocation = f"{sys.executable},0"
    link.save()
    return path


def add_to_path() -> bool:
    """Add the project root to the per-user PATH. Returns True if changed."""
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0,
                        winreg.KEY_READ | winreg.KEY_WRITE) as key:
        try:
            current, _ = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            current = ""

        entries = [p for p in current.split(os.pathsep) if p.strip()]
        if any(Path(p) == PROJECT_ROOT for p in entries if p):
            return False

        entries.append(str(PROJECT_ROOT))
        winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, os.pathsep.join(entries))

    _broadcast_env_change()
    return True


def remove_from_path() -> bool:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0,
                        winreg.KEY_READ | winreg.KEY_WRITE) as key:
        try:
            current, _ = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            return False

        entries = [p for p in current.split(os.pathsep) if p.strip()]
        kept = [p for p in entries if Path(p) != PROJECT_ROOT]
        if len(kept) == len(entries):
            return False

        winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, os.pathsep.join(kept))

    _broadcast_env_change()
    return True


def _broadcast_env_change():
    """Tell running apps the environment changed, so new terminals pick it up."""
    import ctypes

    HWND_BROADCAST, WM_SETTINGCHANGE, SMTO_ABORTIFHUNG = 0xFFFF, 0x1A, 0x0002
    ctypes.windll.user32.SendMessageTimeoutW(
        HWND_BROADCAST, WM_SETTINGCHANGE, 0, ctypes.c_wchar_p("Environment"),
        SMTO_ABORTIFHUNG, 5000, None,
    )


def main():
    parser = argparse.ArgumentParser(description="Install A.L.E.X launchers")
    parser.add_argument("--path", action="store_true",
                        help="add the project to your user PATH so `alex` works in any terminal")
    parser.add_argument("--all", action="store_true", help="shortcuts + PATH")
    parser.add_argument("--uninstall", action="store_true", help="remove everything")
    args = parser.parse_args()

    if not LAUNCHER.exists():
        sys.exit(f"Launcher not found: {LAUNCHER}")

    print(f"\n  A.L.E.X launcher installer")
    print(f"  Project: {PROJECT_ROOT}\n")

    if args.uninstall:
        for folder in ("desktop", "programs"):
            target = _folder(folder) / SHORTCUT_NAME
            if target.exists():
                target.unlink()
                print(f"  removed  {target}")
        print("  removed from PATH" if remove_from_path() else "  PATH was not modified")
        print("\n  Uninstalled. The project folder itself is untouched.\n")
        return

    desktop = make_shortcut(_folder("desktop"))
    print(f"  created  {desktop}")

    programs = make_shortcut(_folder("programs"))
    print(f"  created  {programs}")

    if args.path or args.all:
        if add_to_path():
            print(f"  added    {PROJECT_ROOT} to your user PATH")
            print("           (open a NEW terminal for this to take effect)")
        else:
            print("  PATH     already contains the project folder")

    print("\n  Done. You can now start ALEX by:")
    print("    • double-clicking A.L.E.X on your Desktop")
    print("    • searching \"ALEX\" in the Start Menu")
    if args.path or args.all:
        print("    • typing  alex  in any new terminal")
    print()


if __name__ == "__main__":
    main()
