# system_info_utils.py
import psutil
import socket
import subprocess
import wmi
import os
import time                 
from pathlib import Path      
import datetime 
import pyautogui             
import pygetwindow as gw     


def get_power_status():
    """Check if the system is on battery or plugged in."""
    battery = psutil.sensors_battery()
    if not battery:
        return "Power source unknown"
    if battery.power_plugged:
        return f"Plugged in ({battery.percent}%)"
    return f"On battery ({battery.percent}%)"

def get_network_status():
    """Check internet and Wi-Fi connection."""
    try:
        # Ping Google to test connectivity
        socket.create_connection(("8.8.8.8", 53), timeout=2)
        connected = True
    except OSError:
        connected = False

    # Detect active network adapters
    addrs = psutil.net_if_addrs()
    wifi = [name for name in addrs.keys() if "Wi-Fi" in name or "WLAN" in name]

    if not connected:
        return "No internet connection"
    elif wifi:
        return f"Connected to Wi-Fi "
    else:
        return "Connected via Ethernet or unknown network"

def get_vpn_status():
    """Detect if VPN connection is active (rudimentary check)."""
    interfaces = psutil.net_if_addrs()
    vpn_keywords = ["TAP", "VPN", "WireGuard", "OpenVPN"]
    active_vpn = [name for name in interfaces if any(k.lower() in name.lower() for k in vpn_keywords)]
    return "VPN Active" if active_vpn else "No VPN detected"

def get_performance():
    """Return CPU, GPU, and Memory usage."""
    cpu = psutil.cpu_percent(interval=1)
    mem = psutil.virtual_memory().percent

    # Try WMI for GPU info
    gpu_info = "Unavailable"
    try:
        w = wmi.WMI()
        gpus = w.Win32_VideoController()
        if gpus:
            gpu_load = []
            for gpu in gpus:
                gpu_load.append(gpu.Name)
            gpu_info = ", ".join(gpu_load)
    except Exception:
        pass

    return f"CPU: {cpu}%, Memory: {mem}%, GPU: {gpu_info}"

def get_disk_usage():
    """Return disk usage for main drive."""
    usage = psutil.disk_usage('/')
    return f"Disk Usage: {usage.percent}% ({usage.used // (1024**3)}GB used / {usage.total // (1024**3)}GB total)"

def get_time():
    return {"ok": True, "out": datetime.datetime.now().strftime("The current time is %I:%M:%S %p")}

def get_date():
    return {"ok": True, "out": datetime.date.today().strftime("Today's date is %B %d, %Y")}

def get_battery():
    try:
        b = psutil.sensors_battery()
        if not b:
            return {"ok": True, "out": "No battery info available."}
        plugged = "charging" if b.power_plugged else "not charging"
        return {"ok": True, "out": f"Battery at {b.percent}% and {plugged}."}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def get_system_info():
    try:
        cpu = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory().percent
        boot = datetime.datetime.fromtimestamp(psutil.boot_time()).strftime("%Y-%m-%d %H:%M:%S")
        return {"ok": True, "out": f"CPU: {cpu}%, Memory: {mem}%, Boot: {boot}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}



