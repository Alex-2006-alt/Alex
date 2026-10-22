"""
ALEX Background Service Entry Point
------------------------------------
Run with pythonw.exe (no console window):

    pythonw.exe alex_service.pyw          # background tray mode
    pythonw.exe alex_service.pyw --tray   # explicit tray mode (same)

This file intentionally has a .pyw extension so Windows runs it with
pythonw.exe when double-clicked or launched by the startup task.
"""

import sys
import os

# Ensure the project root is on the path (same as main.py)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ─── Redirect stdout/stderr to the log file when there is no console ─────────
# pythonw.exe gives us no stdout, which causes crashes in libraries that print.
# Route everything to the ALEX log file so errors are still captured.

from pathlib import Path
_log_dir = Path(__file__).parent / "data" / "logs"
_log_dir.mkdir(parents=True, exist_ok=True)

import datetime as _dt
_log_file = str(_log_dir / f"alex_service_{_dt.date.today()}.log")

# Only redirect if we have no real console (pythonw path)
if sys.stdout is None or not hasattr(sys.stdout, "fileno"):
    _fh = open(_log_file, "a", encoding="utf-8", buffering=1)
    sys.stdout = _fh
    sys.stderr = _fh

# ─── Launch ───────────────────────────────────────────────────────────────────

from utils.logger import log
import config

log.info("=" * 55)
log.info(f"  {config.ASSISTANT_NAME} — Background Service starting")
log.info("=" * 55)

try:
    from core.tray_app import TrayApp
    TrayApp().run()
except Exception as e:
    log.critical(f"TrayApp crashed: {e}", exc_info=True)
    sys.exit(1)
