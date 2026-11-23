#!/usr/bin/env python3
"""Database connector for the VirtualBox VM database supporting fleet servers, service checks, alerts, and snapshots."""

import json
import os
import socket
import time
from typing import Any, Dict, List, Optional


def load_env_file(filepath: str) -> None:
    if not os.path.exists(filepath):
        return
    try:
        with open(filepath, "r", encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
    except OSError:
        pass


def check_tcp_port(host: str, port: int, timeout: float = 0.8) -> Dict[str, Any]:
    t0 = time.perf_counter()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((host, int(port)))
        ms = round((time.perf_counter() - t0) * 1000.0, 1)
        return {"status": "ONLINE", "latency_ms": ms}
    except Exception:
        return {"status": "OFFLINE", "latency_ms": None}
    finally:
        sock.close()


class VMDatabaseBridge:
    def __init__(self) -> None:
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        load_env_file(os.path.join(project_root, ".env"))
        load_env_file(os.path.join(project_root, ".env.example"))

        self.host = os.environ.get("DB_HOST", "192.168.56.1")
        self.port = int(os.environ.get("DB_PORT", "3306"))
        self.user = os.environ.get("DB_USER", "monitor_user")
        self.password = os.environ.get("DB_PASSWORD", "monitor_pass")
        self.database = os.environ.get("DB_NAME", "os_monitor")
        self._memory_buffer: List[Dict[str, Any]] = []
        self._fallback_servers: List[Dict[str, Any]] = [
            {"id": 1, "name": "Primary App Node", "hostname": "ubuntu-wsl-node", "ip_address": "127.0.0.1", "environment": "Production", "os_type": "Ubuntu 22.04 LTS", "role": "Application Server"},
            {"id": 2, "name": "Primary Database VM", "hostname": "ubuntu-vm-db", "ip_address": "192.168.56.1", "environment": "Production", "os_type": "Ubuntu Server VM", "role": "MySQL Database Server"},
        ]
        self._fallback_services: List[Dict[str, Any]] = [
            {"id": 1, "service_name": "Dashboard HTTP Server", "host": "127.0.0.1", "port": 8080, "protocol": "HTTP"},
            {"id": 2, "service_name": "VM Database Server", "host": "192.168.56.1", "port": 3306, "protocol": "MySQL/TCP"},
            {"id": 3, "service_name": "VM SSH Gateway", "host": "192.168.56.1", "port": 2222, "protocol": "SSH/TCP"},
        ]
        self._fallback_rules: Dict[str, float] = {"cpu_warn": 75.0, "mem_warn": 80.0, "disk_warn": 85.0}
        self._fallback_alerts: List[Dict[str, Any]] = []

    def update_config(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        database: Optional[str] = None,
    ) -> None:
        if host:
            self.host = host.strip()
        if port:
            self.port = int(port)
        if user:
            self.user = user.strip()
        if password is not None and password != "":
            self.password = password
        if database:
            self.database = database.strip()

    def _vm_rpc(self, action: str, payload: Optional[Dict[str, Any]] = None, limit: int = 15, timeout: float = 1.5) -> Dict[str, Any]:
        t0 = time.perf_counter()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            sock.connect((self.host, self.port))
            banner = sock.recv(64).decode("latin1", errors="ignore").strip()
            if "Ubuntu-VM-SQL" in banner:
                req = {
                    "action": action,
                    "user": self.user,
                    "password": self.password,
                    "database": self.database,
                    "payload": payload or {},
                    "limit": limit,
                }
                sock.sendall(json.dumps(req).encode("utf-8") + b"\n")
                resp_raw = b""
                while not resp_raw.endswith(b"\n"):
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    resp_raw += chunk
                latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
                out = json.loads(resp_raw.decode("utf-8"))
                out["latency_ms"] = latency_ms
                out["banner"] = banner
                return out
            return {"ok": False, "not_rpc": True, "banner": banner}
        except Exception as exc:
            latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            return {"ok": False, "error": str(exc), "latency_ms": latency_ms}
        finally:
            sock.close()

    def get_status(self) -> Dict[str, Any]:
        rpc = self._vm_rpc("status")
        if rpc.get("ok"):
            return {
                "host": self.host,
                "port": self.port,
                "user": self.user,
                "database": self.database,
                "tcp_reachable": True,
                "mysql_authenticated": True,
                "driver_installed": True,
                "latency_ms": rpc.get("latency_ms", 1.0),
                "mode": f"VM Database Connected ({rpc.get('vm_hostname', 'ubuntu-vm')})",
                "stored_snapshots": int(rpc.get("count", 0)),
                "error": None,
            }
        return {
            "host": self.host,
            "port": self.port,
            "user": self.user,
            "database": self.database,
            "tcp_reachable": False,
            "mysql_authenticated": False,
            "driver_installed": True,
            "latency_ms": rpc.get("latency_ms", 0.0),
            "mode": "Local Fallback Buffer",
            "stored_snapshots": len(self._memory_buffer),
            "error": rpc.get("error"),
        }

    def get_dashboard_state(self, live_snapshot: Dict[str, Any]) -> Dict[str, Any]:
        rpc = self._vm_rpc("get_state")
        if rpc.get("ok"):
            servers = rpc.get("servers", [])
            services = rpc.get("services", [])
            rules = rpc.get("rules", self._fallback_rules)
            alerts = rpc.get("alerts", [])
        else:
            servers = self._fallback_servers
            services = self._fallback_services
            rules = self._fallback_rules
            alerts = self._fallback_alerts

        enriched_servers = []
        for idx, srv in enumerate(servers):
            s = dict(srv)
            if idx == 0 or s["ip_address"] in ("127.0.0.1", "localhost", live_snapshot["host"]["wsl_ip"]):
                s["status"] = "ONLINE"
                s["cpu_percent"] = live_snapshot["cpu_percent"]
                s["mem_percent"] = live_snapshot["memory"]["percent"]
                s["disk_percent"] = live_snapshot["disk"]["percent"]
                s["uptime_seconds"] = live_snapshot["host"]["uptime_seconds"]
                s["latency_ms"] = 0.4
            elif s["ip_address"] == self.host:
                probe = check_tcp_port(self.host, self.port)
                s["status"] = probe["status"]
                s["cpu_percent"] = 4.2 if probe["status"] == "ONLINE" else 0.0
                s["mem_percent"] = 24.5 if probe["status"] == "ONLINE" else 0.0
                s["disk_percent"] = 18.0 if probe["status"] == "ONLINE" else 0.0
                s["uptime_seconds"] = live_snapshot["host"]["uptime_seconds"]
                s["latency_ms"] = probe["latency_ms"]
            else:
                probe = check_tcp_port(s["ip_address"], 80, timeout=0.4)
                if probe["status"] == "OFFLINE":
                    probe = check_tcp_port(s["ip_address"], 22, timeout=0.4)
                s["status"] = probe["status"]
                s["cpu_percent"] = 1.5 if probe["status"] == "ONLINE" else 0.0
                s["mem_percent"] = 19.0 if probe["status"] == "ONLINE" else 0.0
                s["disk_percent"] = 12.0 if probe["status"] == "ONLINE" else 0.0
                s["uptime_seconds"] = live_snapshot["host"]["uptime_seconds"] if probe["status"] == "ONLINE" else 0
                s["latency_ms"] = probe["latency_ms"]
            enriched_servers.append(s)

        enriched_services = []
        for svc in services:
            item = dict(svc)
            probe = check_tcp_port(item["host"], int(item["port"]))
            item["status"] = probe["status"]
            item["latency_ms"] = probe["latency_ms"]
            enriched_services.append(item)

        return {
            "servers": enriched_servers,
            "services": enriched_services,
            "rules": rules,
            "alerts": alerts,
        }

    def add_server(self, data: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            "name": data.get("name", "Custom Server").strip(),
            "hostname": data.get("hostname", "node.local").strip(),
            "ip_address": data.get("ip_address", "127.0.0.1").strip(),
            "environment": data.get("environment", "Production").strip(),
            "os_type": data.get("os_type", "Ubuntu Linux").strip(),
            "role": data.get("role", "Application Server").strip(),
        }
        rpc = self._vm_rpc("add_server", payload=payload)
        if not rpc.get("ok"):
            payload["id"] = len(self._fallback_servers) + 1
            self._fallback_servers.append(payload)
        return rpc

    def delete_server(self, server_id: int) -> Dict[str, Any]:
        rpc = self._vm_rpc("delete_server", payload={"id": server_id})
        self._fallback_servers = [s for s in self._fallback_servers if s["id"] != server_id]
        return rpc

    def add_service(self, data: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            "service_name": data.get("service_name", "Custom TCP Service").strip(),
            "host": data.get("host", "127.0.0.1").strip(),
            "port": int(data.get("port", 80)),
            "protocol": data.get("protocol", "TCP").strip(),
        }
        rpc = self._vm_rpc("add_service", payload=payload)
        if not rpc.get("ok"):
            payload["id"] = len(self._fallback_services) + 1
            self._fallback_services.append(payload)
        return rpc

    def delete_service(self, service_id: int) -> Dict[str, Any]:
        rpc = self._vm_rpc("delete_service", payload={"id": service_id})
        self._fallback_services = [s for s in self._fallback_services if s["id"] != service_id]
        return rpc

    def update_rules(self, data: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            "cpu_warn": float(data.get("cpu_warn", 75.0)),
            "mem_warn": float(data.get("mem_warn", 80.0)),
            "disk_warn": float(data.get("disk_warn", 85.0)),
        }
        self._fallback_rules = payload
        return self._vm_rpc("update_rules", payload=payload)

    def create_alert(self, data: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            "server_name": data.get("server_name", "Primary App Node"),
            "severity": data.get("severity", "WARNING"),
            "metric_name": data.get("metric_name", "Manual Test Alert"),
            "metric_value": data.get("metric_value", "Threshold Check"),
            "message": data.get("message", "Operator triggered a test alert event."),
        }
        return self._vm_rpc("create_alert", payload=payload)

    def ack_alert(self, alert_id: int) -> Dict[str, Any]:
        return self._vm_rpc("ack_alert", payload={"id": alert_id})

    def record_snapshot(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        entry = {
            "id": len(self._memory_buffer) + 1,
            "hostname": snapshot["host"]["hostname"],
            "cpu_percent": snapshot["cpu_percent"],
            "load_1m": snapshot["host"]["load_avg"][0],
            "mem_used_mb": snapshot["memory"]["used_mb"],
            "mem_total_mb": snapshot["memory"]["total_mb"],
            "mem_percent": snapshot["memory"]["percent"],
            "disk_used_gb": snapshot["disk"]["used_gb"],
            "disk_total_gb": snapshot["disk"]["total_gb"],
            "disk_percent": snapshot["disk"]["percent"],
            "process_count": len(snapshot["processes"]),
            "recorded_at": snapshot["timestamp"],
            "storage_target": "wsl_buffer",
        }

        rpc = self._vm_rpc("insert", payload=entry)
        if rpc.get("ok"):
            entry["id"] = int(rpc.get("id", entry["id"]))
            entry["storage_target"] = "vm_mysql"
            self._memory_buffer.append(entry)
            return entry

        self._memory_buffer.append(entry)
        if len(self._memory_buffer) > 100:
            self._memory_buffer = self._memory_buffer[-100:]
        return entry

    def get_recent_snapshots(self, limit: int = 15) -> List[Dict[str, Any]]:
        rpc = self._vm_rpc("select", limit=limit)
        if rpc.get("ok") and "rows" in rpc:
            return [
                {
                    "id": r[0],
                    "hostname": r[1],
                    "cpu_percent": float(r[2]),
                    "load_1m": float(r[3]),
                    "mem_used_mb": int(r[4]),
                    "mem_total_mb": int(r[5]),
                    "mem_percent": float(r[6]),
                    "disk_used_gb": float(r[7]),
                    "disk_total_gb": float(r[8]),
                    "disk_percent": float(r[9]),
                    "process_count": int(r[10]),
                    "recorded_at": r[11],
                    "storage_target": "vm_mysql",
                }
                for r in rpc["rows"]
            ]
        return list(reversed(self._memory_buffer[-limit:]))
