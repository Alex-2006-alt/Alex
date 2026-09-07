"""
ALEX — System Monitor
Real-time monitoring of CPU, RAM, disk, network, and custom conditions.
Integrates with TaskManager to run monitors as background tasks.
"""

import time
import psutil
from typing import Callable

from utils.logger import log


class SystemMonitor:
    """
    Monitors system resources and triggers alerts on threshold breaches.
    Works with TaskManager for background execution.
    """

    def __init__(self, alert_callback: Callable[[str], None] | None = None):
        """
        Args:
            alert_callback: Called with alert message when a threshold is exceeded.
                            Signature: (message: str)
        """
        self._alert_callback = alert_callback
        self._task_manager = None

    def set_task_manager(self, task_manager):
        self._task_manager = task_manager

    def _alert(self, message: str):
        log.warning(f"🚨 MONITOR ALERT: {message}")
        if self._alert_callback:
            self._alert_callback(message)

    # ─── SNAPSHOT ────────────────────────────────────────────────────────────

    def get_snapshot(self) -> dict:
        """Get current system resource snapshot."""
        cpu = psutil.cpu_percent(interval=0.5)
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        net = psutil.net_io_counters()

        snapshot = {
            "cpu_percent": cpu,
            "cpu_cores": psutil.cpu_count(),
            "ram_total_gb": round(ram.total / 1e9, 2),
            "ram_used_gb": round(ram.used / 1e9, 2),
            "ram_percent": ram.percent,
            "disk_total_gb": round(disk.total / 1e9, 2),
            "disk_used_gb": round(disk.used / 1e9, 2),
            "disk_percent": disk.percent,
            "net_sent_mb": round(net.bytes_sent / 1e6, 2),
            "net_recv_mb": round(net.bytes_recv / 1e6, 2),
            "timestamp": time.time(),
        }
        return snapshot

    def get_summary_text(self) -> str:
        """Get human-readable system status."""
        s = self.get_snapshot()
        return (
            f"CPU: {s['cpu_percent']}% | "
            f"RAM: {s['ram_used_gb']:.1f}/{s['ram_total_gb']:.1f} GB ({s['ram_percent']}%) | "
            f"Disk: {s['disk_used_gb']:.1f}/{s['disk_total_gb']:.1f} GB ({s['disk_percent']}%)"
        )

    # ─── MONITORS ────────────────────────────────────────────────────────────

    def watch_cpu(
        self,
        threshold: float = 80.0,
        interval_seconds: float = 60.0,
        action_callback: Callable | None = None,
    ) -> str | None:
        """
        Start monitoring CPU usage. Alert when it exceeds threshold.

        Returns: task_id (or None if TaskManager not set)
        """
        if not self._task_manager:
            log.warning("TaskManager not set — cannot start CPU monitor as background task")
            return None

        def _check_cpu():
            cpu = psutil.cpu_percent(interval=1)
            if cpu >= threshold:
                msg = f"CPU usage is at {cpu:.1f}% (threshold: {threshold}%)"
                self._alert(msg)
                if action_callback:
                    try:
                        action_callback(cpu)
                    except Exception as e:
                        log.error(f"CPU alert callback failed: {e}")

        task_id = self._task_manager.schedule(
            _check_cpu,
            name=f"CPU Monitor (>{threshold}%)",
            interval_seconds=interval_seconds,
        )
        log.info(f"📊 CPU monitor started: threshold={threshold}%, every {interval_seconds}s")
        return task_id

    def watch_ram(
        self,
        threshold: float = 85.0,
        interval_seconds: float = 60.0,
    ) -> str | None:
        """Monitor RAM usage. Alert when it exceeds threshold."""
        if not self._task_manager:
            return None

        def _check_ram():
            ram = psutil.virtual_memory()
            if ram.percent >= threshold:
                used = round(ram.used / 1e9, 1)
                total = round(ram.total / 1e9, 1)
                msg = f"RAM usage is at {ram.percent:.1f}% ({used}/{total} GB)"
                self._alert(msg)

        return self._task_manager.schedule(
            _check_ram,
            name=f"RAM Monitor (>{threshold}%)",
            interval_seconds=interval_seconds,
        )

    def watch_disk(
        self,
        path: str = "/",
        threshold: float = 90.0,
        interval_seconds: float = 300.0,
    ) -> str | None:
        """Monitor disk usage. Alert when it exceeds threshold."""
        if not self._task_manager:
            return None

        def _check_disk():
            disk = psutil.disk_usage(path)
            if disk.percent >= threshold:
                used = round(disk.used / 1e9, 1)
                total = round(disk.total / 1e9, 1)
                msg = f"Disk usage is at {disk.percent:.1f}% ({used}/{total} GB) on {path}"
                self._alert(msg)

        return self._task_manager.schedule(
            _check_disk,
            name=f"Disk Monitor (>{threshold}%)",
            interval_seconds=interval_seconds,
        )

    def watch_process(
        self,
        process_name: str,
        alert_if: str = "dies",  # "dies" or "appears"
        interval_seconds: float = 30.0,
    ) -> str | None:
        """Monitor if a process starts or stops."""
        if not self._task_manager:
            return None

        def _process_is_running() -> bool:
            return any(
                process_name.lower() in p.name().lower()
                for p in psutil.process_iter(["name"])
            )

        last_state = _process_is_running()

        def _check_process():
            nonlocal last_state
            current_state = _process_is_running()
            if alert_if == "dies" and last_state and not current_state:
                self._alert(f"Process '{process_name}' has stopped!")
            elif alert_if == "appears" and not last_state and current_state:
                self._alert(f"Process '{process_name}' has started!")
            last_state = current_state

        return self._task_manager.schedule(
            _check_process,
            name=f"Process Monitor: {process_name}",
            interval_seconds=interval_seconds,
        )

    def watch_website(
        self,
        url: str,
        alert_if_down: bool = True,
        interval_seconds: float = 60.0,
    ) -> str | None:
        """Periodically check if a website is up or down."""
        if not self._task_manager:
            return None

        import requests

        last_was_up = True

        def _check_website():
            nonlocal last_was_up
            try:
                resp = requests.get(url, timeout=10)
                is_up = resp.status_code < 500
            except Exception:
                is_up = False

            if alert_if_down and last_was_up and not is_up:
                self._alert(f"Website is DOWN: {url}")
            elif not alert_if_down and not last_was_up and is_up:
                self._alert(f"Website is back UP: {url}")

            last_was_up = is_up

        return self._task_manager.schedule(
            _check_website,
            name=f"Website Monitor: {url}",
            interval_seconds=interval_seconds,
        )

    def watch_file_change(
        self,
        path: str,
        interval_seconds: float = 10.0,
    ) -> str | None:
        """Alert when a file or directory changes."""
        if not self._task_manager:
            return None

        import os
        try:
            last_mtime = os.path.getmtime(path)
        except FileNotFoundError:
            last_mtime = 0

        def _check_file():
            nonlocal last_mtime
            try:
                mtime = os.path.getmtime(path)
                if mtime != last_mtime:
                    self._alert(f"File changed: {path}")
                    last_mtime = mtime
            except FileNotFoundError:
                self._alert(f"File deleted: {path}")

        return self._task_manager.schedule(
            _check_file,
            name=f"File Monitor: {path}",
            interval_seconds=interval_seconds,
        )
