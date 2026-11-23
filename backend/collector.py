#!/usr/bin/env python3
"""Linux / WSL2 real-time system telemetry collector reading directly from /proc and standard OS utilities."""

import os
import platform
import shutil
import socket
import subprocess
import time
from typing import Any, Dict, List

_PREV_CPU_TIMES = None
_PREV_NET_BYTES = None
_PREV_NET_TS = None


def _read_cpu_times() -> List[int]:
    try:
        with open("/proc/stat", "r", encoding="utf-8") as fh:
            first_line = fh.readline()
            parts = first_line.strip().split()[1:]
            return [int(x) for x in parts]
    except OSError:
        return []


def get_cpu_percent() -> float:
    global _PREV_CPU_TIMES
    current = _read_cpu_times()
    if not current or len(current) < 4:
        return 0.0
    if _PREV_CPU_TIMES is None:
        _PREV_CPU_TIMES = current
        time.sleep(0.08)
        current = _read_cpu_times()
    prev = _PREV_CPU_TIMES
    _PREV_CPU_TIMES = current

    idle_prev = prev[3] + (prev[4] if len(prev) > 4 else 0)
    idle_curr = current[3] + (current[4] if len(current) > 4 else 0)
    total_prev = sum(prev)
    total_curr = sum(current)

    total_diff = total_curr - total_prev
    idle_diff = idle_curr - idle_prev
    if total_diff <= 0:
        return 0.0
    return round(max(0.0, min(100.0, (1.0 - idle_diff / total_diff) * 100.0)), 1)


def get_memory_info() -> Dict[str, Any]:
    info: Dict[str, int] = {}
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as fh:
            for line in fh:
                if ":" in line:
                    k, v = line.split(":", 1)
                    parts = v.strip().split()
                    if parts and parts[0].isdigit():
                        info[k.strip()] = int(parts[0])
    except OSError:
        pass

    total_kb = info.get("MemTotal", 0)
    avail_kb = info.get("MemAvailable", info.get("MemFree", 0))
    used_kb = max(0, total_kb - avail_kb)
    swap_total_kb = info.get("SwapTotal", 0)
    swap_free_kb = info.get("SwapFree", 0)
    swap_used_kb = max(0, swap_total_kb - swap_free_kb)

    total_mb = round(total_kb / 1024)
    used_mb = round(used_kb / 1024)
    pct = round((used_kb / total_kb) * 100.0, 1) if total_kb > 0 else 0.0

    return {
        "total_mb": total_mb,
        "used_mb": used_mb,
        "available_mb": round(avail_kb / 1024),
        "percent": pct,
        "swap_total_mb": round(swap_total_kb / 1024),
        "swap_used_mb": round(swap_used_kb / 1024),
    }


def get_disk_info(mount_path: str = "/") -> Dict[str, Any]:
    try:
        usage = shutil.disk_usage(mount_path)
        total_gb = round(usage.total / (1024 ** 3), 2)
        used_gb = round(usage.used / (1024 ** 3), 2)
        free_gb = round(usage.free / (1024 ** 3), 2)
        pct = round((usage.used / usage.total) * 100.0, 1) if usage.total > 0 else 0.0
        return {
            "mount": mount_path,
            "total_gb": total_gb,
            "used_gb": used_gb,
            "free_gb": free_gb,
            "percent": pct,
        }
    except OSError:
        return {"mount": mount_path, "total_gb": 0.0, "used_gb": 0.0, "free_gb": 0.0, "percent": 0.0}


def get_network_info() -> Dict[str, Any]:
    global _PREV_NET_BYTES, _PREV_NET_TS
    rx_total = 0
    tx_total = 0
    interfaces: List[Dict[str, Any]] = []
    try:
        with open("/proc/net/dev", "r", encoding="utf-8") as fh:
            lines = fh.readlines()[2:]
            for line in lines:
                if ":" not in line:
                    continue
                iface, data = line.split(":", 1)
                iface = iface.strip()
                fields = data.split()
                if len(fields) >= 9:
                    rx_b = int(fields[0])
                    tx_b = int(fields[8])
                    if iface != "lo":
                        rx_total += rx_b
                        tx_total += tx_b
                    interfaces.append({
                        "interface": iface,
                        "rx_mb": round(rx_b / (1024 * 1024), 2),
                        "tx_mb": round(tx_b / (1024 * 1024), 2),
                    })
    except OSError:
        pass

    now = time.time()
    rx_rate_kbps = 0.0
    tx_rate_kbps = 0.0
    if _PREV_NET_BYTES is not None and _PREV_NET_TS is not None:
        dt = max(0.001, now - _PREV_NET_TS)
        rx_rate_kbps = round(max(0.0, (rx_total - _PREV_NET_BYTES[0]) / 1024.0 / dt), 1)
        tx_rate_kbps = round(max(0.0, (tx_total - _PREV_NET_BYTES[1]) / 1024.0 / dt), 1)

    _PREV_NET_BYTES = (rx_total, tx_total)
    _PREV_NET_TS = now

    return {
        "rx_total_mb": round(rx_total / (1024 * 1024), 2),
        "tx_total_mb": round(tx_total / (1024 * 1024), 2),
        "rx_rate_kbps": rx_rate_kbps,
        "tx_rate_kbps": tx_rate_kbps,
        "interfaces": interfaces,
    }


def get_top_processes(limit: int = 8) -> List[Dict[str, Any]]:
    processes: List[Dict[str, Any]] = []
    try:
        out = subprocess.check_output(
            ["ps", "-eo", "pid,user,%cpu,%mem,comm", "--sort=-%cpu"],
            text=True,
            timeout=2,
        )
        lines = out.strip().splitlines()[1 : limit + 1]
        for line in lines:
            parts = line.split(None, 4)
            if len(parts) == 5:
                processes.append({
                    "pid": int(parts[0]),
                    "user": parts[1],
                    "cpu": float(parts[2]),
                    "mem": float(parts[3]),
                    "command": parts[4],
                })
    except Exception:
        pass
    return processes


def get_host_summary() -> Dict[str, Any]:
    distro = "Linux (WSL2)"
    try:
        with open("/etc/os-release", "r", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("PRETTY_NAME="):
                    distro = line.split("=", 1)[1].strip().strip('"')
                    break
    except OSError:
        pass

    uptime_sec = 0
    try:
        with open("/proc/uptime", "r", encoding="utf-8") as fh:
            uptime_sec = int(float(fh.readline().split()[0]))
    except OSError:
        pass

    load_1, load_5, load_15 = (0.0, 0.0, 0.0)
    try:
        load_1, load_5, load_15 = [round(x, 2) for x in os.getloadavg()]
    except OSError:
        pass

    ip_addr = "127.0.0.1"
    try:
        out = subprocess.check_output(["hostname", "-I"], text=True, timeout=1).strip()
        if out:
            ip_addr = out.split()[0]
    except Exception:
        pass

    wsl_gateway = "172.17.80.1"
    try:
        out = subprocess.check_output(["ip", "route", "show", "default"], text=True, timeout=1).strip()
        parts = out.split()
        if "via" in parts:
            wsl_gateway = parts[parts.index("via") + 1]
    except Exception:
        pass

    return {
        "hostname": socket.gethostname(),
        "distro": distro,
        "kernel": platform.release(),
        "cpu_cores": os.cpu_count() or 1,
        "uptime_seconds": uptime_sec,
        "load_avg": [load_1, load_5, load_15],
        "wsl_ip": ip_addr,
        "windows_host_gateway": wsl_gateway,
    }


def collect_snapshot() -> Dict[str, Any]:
    host = get_host_summary()
    cpu_pct = get_cpu_percent()
    mem = get_memory_info()
    disk = get_disk_info("/")
    net = get_network_info()
    procs = get_top_processes(8)

    return {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "host": host,
        "cpu_percent": cpu_pct,
        "memory": mem,
        "disk": disk,
        "network": net,
        "processes": procs,
    }
