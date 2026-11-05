"""Windows 11 System Diagnostics & Telemetry Tools."""

import time

import psutil

from tools.registry import register_tool


@register_tool(
    name="get_system_diagnostics",
    description="Returns current hardware diagnostics including CPU utilization percentage, RAM usage, battery status, and available disk space."
)
def get_system_diagnostics() -> dict:
    """Collects system telemetry in real-time."""
    # CPU
    cpu_percent = psutil.cpu_percent(interval=0.1)
    cpu_count = psutil.cpu_count(logical=True)

    # Memory
    mem = psutil.virtual_memory()
    ram_used_gb = round(mem.used / (1024 ** 3), 2)
    ram_total_gb = round(mem.total / (1024 ** 3), 2)
    ram_percent = mem.percent

    # Disk
    disk = psutil.disk_usage("C:\\")
    disk_free_gb = round(disk.free / (1024 ** 3), 1)

    # Battery
    battery = psutil.sensors_battery()
    battery_info = "Desktop / No battery"
    if battery:
        charging = "charging" if battery.power_plugged else "on battery power"
        battery_info = f"{battery.percent}% ({charging})"

    # Boot time
    uptime_hours = round((time.time() - psutil.boot_time()) / 3600, 1)

    return {
        "cpu_usage_percent": f"{cpu_percent}%",
        "cpu_cores": cpu_count,
        "ram_usage": f"{ram_used_gb} GB / {ram_total_gb} GB ({ram_percent}%)",
        "disk_free_c_drive": f"{disk_free_gb} GB free",
        "battery_status": battery_info,
        "system_uptime_hours": uptime_hours
    }
