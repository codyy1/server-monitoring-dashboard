#!/usr/bin/env python3
"""User-Facing Server Monitoring Dashboard REST API & Web Server."""

import json
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from collector import collect_snapshot
from db import VMDatabaseBridge

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(PROJECT_ROOT, "frontend")
DB_BRIDGE = VMDatabaseBridge()


class MonitorRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        pass

    def _send_json(self, payload: dict, status: int = 200) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _serve_static(self, rel_path: str) -> None:
        if rel_path in ("", "/"):
            rel_path = "index.html"
        clean_path = os.path.normpath(rel_path.lstrip("/"))
        full_path = os.path.join(FRONTEND_DIR, clean_path)

        if not full_path.startswith(FRONTEND_DIR) or not os.path.isfile(full_path):
            self._send_json({"error": "Not found"}, status=404)
            return

        ctype, _ = mimetypes.guess_type(full_path)
        if not ctype:
            ctype = "application/octet-stream"

        with open(full_path, "rb") as fh:
            content = fh.read()

        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        route = parsed.path

        if route == "/api/dashboard":
            snap = collect_snapshot()
            db_status = DB_BRIDGE.get_status()
            state = DB_BRIDGE.get_dashboard_state(snap)
            history = DB_BRIDGE.get_recent_snapshots(limit=20)
            self._send_json(
                {
                    "metrics": snap,
                    "database": db_status,
                    "servers": state["servers"],
                    "services": state["services"],
                    "rules": state["rules"],
                    "alerts": state["alerts"],
                    "snapshots": history,
                }
            )
            return

        if route == "/api/metrics":
            snap = collect_snapshot()
            db_status = DB_BRIDGE.get_status()
            self._send_json({"metrics": snap, "database": db_status})
            return

        if route == "/api/history":
            qs = parse_qs(parsed.query)
            limit = int(qs.get("limit", ["20"])[0])
            rows = DB_BRIDGE.get_recent_snapshots(limit=min(50, max(1, limit)))
            self._send_json({"snapshots": rows, "database": DB_BRIDGE.get_status()})
            return

        if route == "/api/db/status":
            self._send_json({"database": DB_BRIDGE.get_status()})
            return

        self._serve_static(route)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        route = parsed.path
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            data = {}

        if route == "/api/snapshots/record":
            snap = collect_snapshot()
            saved = DB_BRIDGE.record_snapshot(snap)
            self._send_json({"recorded": saved, "database": DB_BRIDGE.get_status()}, status=201)
            return

        if route == "/api/servers":
            res = DB_BRIDGE.add_server(data)
            self._send_json({"result": res}, status=201)
            return

        if route == "/api/servers/delete":
            res = DB_BRIDGE.delete_server(int(data.get("id", 0)))
            self._send_json({"result": res})
            return

        if route == "/api/services":
            res = DB_BRIDGE.add_service(data)
            self._send_json({"result": res}, status=201)
            return

        if route == "/api/services/delete":
            res = DB_BRIDGE.delete_service(int(data.get("id", 0)))
            self._send_json({"result": res})
            return

        if route == "/api/alerts/rules":
            res = DB_BRIDGE.update_rules(data)
            self._send_json({"result": res})
            return

        if route == "/api/alerts/test":
            res = DB_BRIDGE.create_alert(data)
            self._send_json({"result": res}, status=201)
            return

        if route == "/api/alerts/ack":
            res = DB_BRIDGE.ack_alert(int(data.get("id", 0)))
            self._send_json({"result": res})
            return

        if route == "/api/db/config":
            DB_BRIDGE.update_config(
                host=data.get("host"),
                port=data.get("port"),
                user=data.get("user"),
                password=data.get("password"),
                database=data.get("database"),
            )
            self._send_json({"database": DB_BRIDGE.get_status()})
            return

        self._send_json({"error": "Unknown endpoint"}, status=404)


def main() -> None:
    host = os.environ.get("APP_HOST", "0.0.0.0")
    port = int(os.environ.get("APP_PORT", "8080"))
    initial_snap = collect_snapshot()
    DB_BRIDGE.record_snapshot(initial_snap)
    server = ThreadingHTTPServer((host, port), MonitorRequestHandler)
    print(f"Server Monitoring Dashboard listening on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
