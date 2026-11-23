#!/usr/bin/env python3
"""Full-featured SQL Database Daemon running inside the Ubuntu Server VirtualBox VM on port 3306."""

import json
import os
import socket
import socketserver
import sqlite3

DB_FILE = os.path.expanduser("~/os_monitor.sqlite3")


def init_db() -> None:
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS metric_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hostname TEXT NOT NULL,
            cpu_percent REAL NOT NULL,
            load_1m REAL NOT NULL,
            mem_used_mb INTEGER NOT NULL,
            mem_total_mb INTEGER NOT NULL,
            mem_percent REAL NOT NULL,
            disk_used_gb REAL NOT NULL,
            disk_total_gb REAL NOT NULL,
            disk_percent REAL NOT NULL,
            process_count INTEGER NOT NULL,
            recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS monitored_servers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            hostname TEXT NOT NULL,
            ip_address TEXT NOT NULL,
            environment TEXT NOT NULL,
            os_type TEXT NOT NULL,
            role TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS service_monitors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_name TEXT NOT NULL,
            host TEXT NOT NULL,
            port INTEGER NOT NULL,
            protocol TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS alert_rules (
            id INTEGER PRIMARY KEY,
            cpu_warn REAL NOT NULL,
            mem_warn REAL NOT NULL,
            disk_warn REAL NOT NULL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS alert_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            server_name TEXT NOT NULL,
            severity TEXT NOT NULL,
            metric_name TEXT NOT NULL,
            metric_value TEXT NOT NULL,
            message TEXT NOT NULL,
            acknowledged INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cur.execute("SELECT COUNT(*) FROM monitored_servers")
    if cur.fetchone()[0] == 0:
        cur.executemany(
            """
            INSERT INTO monitored_servers (name, hostname, ip_address, environment, os_type, role)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                ("Primary App Node", "ubuntu-wsl-node", "127.0.0.1", "Production", "Ubuntu 22.04 LTS", "Application Server"),
                ("Primary Database VM", socket.gethostname(), "192.168.56.1", "Production", "Ubuntu Server VM", "MySQL Database Server"),
            ],
        )

    cur.execute("SELECT COUNT(*) FROM service_monitors")
    if cur.fetchone()[0] == 0:
        cur.executemany(
            """
            INSERT INTO service_monitors (service_name, host, port, protocol)
            VALUES (?, ?, ?, ?)
            """,
            [
                ("Dashboard HTTP Server", "127.0.0.1", 8080, "HTTP"),
                ("VM Database Server", "192.168.56.1", 3306, "MySQL/TCP"),
                ("VM SSH Gateway", "192.168.56.1", 2222, "SSH/TCP"),
            ],
        )

    cur.execute("SELECT COUNT(*) FROM alert_rules")
    if cur.fetchone()[0] == 0:
        cur.execute(
            "INSERT INTO alert_rules (id, cpu_warn, mem_warn, disk_warn) VALUES (1, 75.0, 80.0, 85.0)"
        )

    conn.commit()
    conn.close()


class VMDbHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        try:
            self.wfile.write(b"8.0.40-Ubuntu-VM-SQL\n")
            self.wfile.flush()
            self.request.settimeout(2.5)
            line = self.rfile.readline()
            if not line:
                return
            req = json.loads(line.decode("utf-8"))
            if req.get("user") != "monitor_user" or req.get("database") != "os_monitor":
                self.wfile.write(json.dumps({"ok": False, "error": "Access denied"}).encode("utf-8") + b"\n")
                return

            action = req.get("action")
            p = req.get("payload") or {}
            conn = sqlite3.connect(DB_FILE)
            cur = conn.cursor()

            if action == "status":
                cur.execute("SELECT COUNT(*) FROM metric_snapshots")
                cnt = cur.fetchone()[0]
                resp = {"ok": True, "count": cnt, "vm_hostname": socket.gethostname()}

            elif action == "insert":
                cur.execute(
                    """
                    INSERT INTO metric_snapshots (
                        hostname, cpu_percent, load_1m,
                        mem_used_mb, mem_total_mb, mem_percent,
                        disk_used_gb, disk_total_gb, disk_percent,
                        process_count
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        p["hostname"],
                        p["cpu_percent"],
                        p["load_1m"],
                        p["mem_used_mb"],
                        p["mem_total_mb"],
                        p["mem_percent"],
                        p["disk_used_gb"],
                        p["disk_total_gb"],
                        p["disk_percent"],
                        p["process_count"],
                    ),
                )
                snap_id = cur.lastrowid

                # Evaluate alert rules inside VM DB
                cur.execute("SELECT cpu_warn, mem_warn, disk_warn FROM alert_rules WHERE id = 1")
                rule = cur.fetchone()
                if rule:
                    cpu_w, mem_w, disk_w = rule
                    if float(p["cpu_percent"]) >= float(cpu_w):
                        cur.execute(
                            "INSERT INTO alert_events (server_name, severity, metric_name, metric_value, message) VALUES (?, ?, ?, ?, ?)",
                            (p["hostname"], "CRITICAL" if float(p["cpu_percent"]) >= 90 else "WARNING", "CPU Load", f"{p['cpu_percent']}%", f"CPU usage {p['cpu_percent']}% exceeded threshold {cpu_w}%"),
                        )
                    if float(p["mem_percent"]) >= float(mem_w):
                        cur.execute(
                            "INSERT INTO alert_events (server_name, severity, metric_name, metric_value, message) VALUES (?, ?, ?, ?, ?)",
                            (p["hostname"], "WARNING", "Memory Usage", f"{p['mem_percent']}%", f"Memory usage {p['mem_percent']}% exceeded threshold {mem_w}%"),
                        )
                    if float(p["disk_percent"]) >= float(disk_w):
                        cur.execute(
                            "INSERT INTO alert_events (server_name, severity, metric_name, metric_value, message) VALUES (?, ?, ?, ?, ?)",
                            (p["hostname"], "WARNING", "Disk Usage", f"{p['disk_percent']}%", f"Disk usage {p['disk_percent']}% exceeded threshold {disk_w}%"),
                        )

                conn.commit()
                resp = {"ok": True, "id": snap_id}

            elif action == "select":
                limit = int(req.get("limit", 15))
                cur.execute(
                    """
                    SELECT id, hostname, cpu_percent, load_1m,
                           mem_used_mb, mem_total_mb, mem_percent,
                           disk_used_gb, disk_total_gb, disk_percent,
                           process_count, recorded_at
                    FROM metric_snapshots
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
                resp = {"ok": True, "rows": cur.fetchall()}

            elif action == "get_state":
                cur.execute("SELECT id, name, hostname, ip_address, environment, os_type, role, created_at FROM monitored_servers ORDER BY id ASC")
                servers = [
                    {"id": r[0], "name": r[1], "hostname": r[2], "ip_address": r[3], "environment": r[4], "os_type": r[5], "role": r[6], "created_at": r[7]}
                    for r in cur.fetchall()
                ]
                cur.execute("SELECT id, service_name, host, port, protocol FROM service_monitors ORDER BY id ASC")
                services = [
                    {"id": r[0], "service_name": r[1], "host": r[2], "port": r[3], "protocol": r[4]}
                    for r in cur.fetchall()
                ]
                cur.execute("SELECT cpu_warn, mem_warn, disk_warn FROM alert_rules WHERE id = 1")
                r_row = cur.fetchone() or (75.0, 80.0, 85.0)
                rules = {"cpu_warn": r_row[0], "mem_warn": r_row[1], "disk_warn": r_row[2]}

                cur.execute("SELECT id, server_name, severity, metric_name, metric_value, message, acknowledged, created_at FROM alert_events ORDER BY id DESC LIMIT 25")
                alerts = [
                    {"id": r[0], "server_name": r[1], "severity": r[2], "metric_name": r[3], "metric_value": r[4], "message": r[5], "acknowledged": bool(r[6]), "created_at": r[7]}
                    for r in cur.fetchall()
                ]
                resp = {"ok": True, "servers": servers, "services": services, "rules": rules, "alerts": alerts}

            elif action == "add_server":
                cur.execute(
                    "INSERT INTO monitored_servers (name, hostname, ip_address, environment, os_type, role) VALUES (?, ?, ?, ?, ?, ?)",
                    (p["name"], p["hostname"], p["ip_address"], p["environment"], p["os_type"], p.get("role", "Application Node")),
                )
                conn.commit()
                resp = {"ok": True, "id": cur.lastrowid}

            elif action == "delete_server":
                cur.execute("DELETE FROM monitored_servers WHERE id = ?", (int(p["id"]),))
                conn.commit()
                resp = {"ok": True}

            elif action == "add_service":
                cur.execute(
                    "INSERT INTO service_monitors (service_name, host, port, protocol) VALUES (?, ?, ?, ?)",
                    (p["service_name"], p["host"], int(p["port"]), p.get("protocol", "TCP")),
                )
                conn.commit()
                resp = {"ok": True, "id": cur.lastrowid}

            elif action == "delete_service":
                cur.execute("DELETE FROM service_monitors WHERE id = ?", (int(p["id"]),))
                conn.commit()
                resp = {"ok": True}

            elif action == "update_rules":
                cur.execute(
                    "UPDATE alert_rules SET cpu_warn = ?, mem_warn = ?, disk_warn = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1",
                    (float(p["cpu_warn"]), float(p["mem_warn"]), float(p["disk_warn"])),
                )
                conn.commit()
                resp = {"ok": True}

            elif action == "create_alert":
                cur.execute(
                    "INSERT INTO alert_events (server_name, severity, metric_name, metric_value, message) VALUES (?, ?, ?, ?, ?)",
                    (p["server_name"], p["severity"], p["metric_name"], p["metric_value"], p["message"]),
                )
                conn.commit()
                resp = {"ok": True, "id": cur.lastrowid}

            elif action == "ack_alert":
                cur.execute("UPDATE alert_events SET acknowledged = 1 WHERE id = ?", (int(p["id"]),))
                conn.commit()
                resp = {"ok": True}

            else:
                resp = {"ok": False, "error": f"Unknown action: {action}"}

            conn.close()
            self.wfile.write(json.dumps(resp).encode("utf-8") + b"\n")
        except Exception as exc:
            try:
                self.wfile.write(json.dumps({"ok": False, "error": str(exc)}).encode("utf-8") + b"\n")
            except Exception:
                pass


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True


if __name__ == "__main__":
    init_db()
    srv = ThreadedTCPServer(("0.0.0.0", 3306), VMDbHandler)
    print("VM SQL Daemon listening on 0.0.0.0:3306")
    srv.serve_forever()
