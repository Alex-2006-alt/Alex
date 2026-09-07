"""
ALEX — System Information Utilities
Get PC stats: CPU, memory, disk, battery, network, etc.
"""

import platform
import socket
from datetime import datetime

import psutil

from utils.logger import log


def get_system_summary() -> dict:
    """Get a comprehensive system summary."""
    info = {
        "hostname": socket.gethostname(),
        "os": f"{platform.system()} {platform.release()}",
        "os_version": platform.version(),
        "architecture": platform.machine(),
        "processor": platform.processor(),
        "cpu_cores_physical": psutil.cpu_count(logical=False),
        "cpu_cores_logical": psutil.cpu_count(logical=True),
        "cpu_usage_percent": psutil.cpu_percent(interval=0.5),
        "ram_total_gb": round(psutil.virtual_memory().total / (1024**3), 1),
        "ram_used_gb": round(psutil.virtual_memory().used / (1024**3), 1),
        "ram_usage_percent": psutil.virtual_memory().percent,
        "boot_time": datetime.fromtimestamp(psutil.boot_time()).strftime("%Y-%m-%d %H:%M:%S"),
    }

    # Battery info (if available)
    battery = psutil.sensors_battery()
    if battery:
        info["battery_percent"] = battery.percent
        info["battery_plugged"] = battery.power_plugged
        if battery.secsleft > 0:
            info["battery_time_left"] = f"{battery.secsleft // 3600}h {(battery.secsleft % 3600) // 60}m"

    # Disk usage for all partitions
    info["disks"] = []
    for partition in psutil.disk_partitions():
        try:
            usage = psutil.disk_usage(partition.mountpoint)
            info["disks"].append({
                "drive": partition.mountpoint,
                "total_gb": round(usage.total / (1024**3), 1),
                "used_gb": round(usage.used / (1024**3), 1),
                "free_gb": round(usage.free / (1024**3), 1),
                "usage_percent": usage.percent,
            })
        except PermissionError:
            pass

    return info


def get_cpu_usage() -> float:
    """Get current CPU usage percentage."""
    return psutil.cpu_percent(interval=0.5)


def get_memory_usage() -> dict:
    """Get RAM usage details."""
    mem = psutil.virtual_memory()
    return {
        "total_gb": round(mem.total / (1024**3), 1),
        "used_gb": round(mem.used / (1024**3), 1),
        "available_gb": round(mem.available / (1024**3), 1),
        "percent": mem.percent,
    }


def get_running_processes(top_n: int = 10) -> list[dict]:
    """Get top N processes by CPU usage."""
    processes = []
    for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
        try:
            processes.append(proc.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    # Sort by CPU usage, descending
    processes.sort(key=lambda p: p.get("cpu_percent", 0) or 0, reverse=True)
    return processes[:top_n]


def get_network_info() -> dict:
    """Get network connection info."""
    addrs = psutil.net_if_addrs()
    stats = psutil.net_if_stats()

    interfaces = {}
    for name, addr_list in addrs.items():
        if name in stats and stats[name].isup:
            for addr in addr_list:
                if addr.family == socket.AF_INET:
                    interfaces[name] = {
                        "ip": addr.address,
                        "netmask": addr.netmask,
                        "speed_mbps": stats[name].speed,
                    }
    return interfaces


def format_system_info_for_speech(info: dict) -> str:
    """Format system info into a speakable string."""
    parts = [
        f"Your PC is running {info['os']}.",
        f"CPU usage is at {info['cpu_usage_percent']}%.",
        f"You're using {info['ram_used_gb']} out of {info['ram_total_gb']} GB of RAM, "
        f"that's {info['ram_usage_percent']}%.",
    ]

    if "battery_percent" in info:
        plug_status = "plugged in" if info["battery_plugged"] else "on battery"
        parts.append(f"Battery is at {info['battery_percent']}%, {plug_status}.")

    return " ".join(parts)
