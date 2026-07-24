"""Lightweight dashboard for the agricultural walking stick agent.

NOTE: Uses stdlib http.server as fallback (FastAPI optional).
Serves a self-contained HTML page with no external assets.

WHY: A farmer may connect to the Pi Zero's WiFi and check the dashboard
from a phone. Keep it minimal and fast for slow connections.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger(__name__)


class DashboardState:
    """Thread-safe shared state for the dashboard."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._state: dict[str, Any] = {
            "timestamp": "",
            "sensors": {},
            "cross_sensor": {},
        }
        self._history: dict[str, list[dict]] = {}
        self._harvests: dict[str, list[dict]] = {}
        self._night_events: list[dict] = []
        self._health: dict[str, Any] = {}

    def update(self, summary: dict) -> None:
        with self._lock:
            self._state = summary

    def update_history(self, sensor_name: str, readings: list[dict]) -> None:
        with self._lock:
            self._history[sensor_name] = readings

    def update_harvests(self, crop: str, entries: list[dict]) -> None:
        with self._lock:
            self._harvests[crop] = entries

    def update_night_events(self, events: list[dict]) -> None:
        with self._lock:
            self._night_events = events

    def update_health(self, health: dict) -> None:
        with self._lock:
            self._health = health

    def get_state(self) -> str:
        with self._lock:
            return json.dumps(self._state)

    def get_history(self, sensor_name: str) -> str:
        with self._lock:
            return json.dumps(self._history.get(sensor_name, []))

    def get_harvests(self, crop: str) -> str:
        with self._lock:
            return json.dumps(self._harvests.get(crop, []))

    def get_night_events(self) -> str:
        with self._lock:
            return json.dumps(self._night_events)

    def get_health(self) -> str:
        with self._lock:
            return json.dumps(self._health)


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TerraFin Dashboard</title>
<style>
body{font-family:sans-serif;background:#1a1a2e;color:#e0e0e0;margin:0;padding:20px}
h1{color:#0f3460;border-bottom:2px solid #e94560;padding-bottom:10px}
.card{background:#16213e;border-radius:8px;padding:15px;margin:10px 0}
.card h2{color:#e94560;margin-top:0;font-size:1.1em}
.metric{display:flex;justify-content:space-between;padding:4px 0}
.metric .label{color:#8a8a8a}
.metric .value{color:#0f3460;font-weight:bold;color:#53d8a0}
.status-ok{color:#53d8a0}
.status-warn{color:#e94560}
#refresh-info{color:#666;font-size:0.8em;margin-top:5px}
</style>
</head>
<body>
<h1>🌾 TerraFin Dashboard</h1>
<div id="content">Loading...</div>
<div id="refresh-info">Auto-refresh every 5s</div>
<script>
// SECURITY NOTE: innerHTML is used with same-origin JSON data only — no untrusted input.
async function refresh(){
  try{
    const s=await fetch('/api/state').then(r=>r.json());
    let html='';
    if(s.cross_sensor&&s.cross_sensor.is_day!==undefined){
      html+='<div class="card"><h2>Mode</h2><div class="metric"><span class="label">Day/Night</span><span class="value">'+(s.cross_sensor.is_day?'Day':'Night')+'</span></div></div>';
    }
    if(s.sensors){
      for(const[name,data]of Object.entries(s.sensors)){
        html+='<div class="card"><h2>'+name+'</h2>';
        for(const[m,v]of Object.entries(data.metrics||{})){
          html+='<div class="metric"><span class="label">'+m+'</span><span class="value">'+(typeof v==='number'?v.toFixed(2):v)+'</span></div>';
        }
        const status=data.healthy?'<span class="status-ok">OK</span>':'<span class="status-warn">WARNING</span>';
        html+='<div class="metric"><span class="label">Health</span>'+status+'</div>';
        html+='</div>';
      }
    }
    if(!html)html='<p>No sensor data available</p>';
    document.getElementById('content').innerHTML=html;
  }catch(e){
    document.getElementById('content').innerHTML='<p>Error loading data: '+e+'</p>';
  }
}
refresh();
setInterval(refresh,5000);
</script>
</body>
</html>"""


class DashboardHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the dashboard."""

    state: DashboardState | None = None  # set by DashboardService

    def log_message(self, format, *args):
        pass  # suppress default logging

    def do_GET(self):
        if self.state is None:
            self.send_error(500, "Dashboard not initialized")
            return

        path = urlparse(self.path).path

        if path == "/" or path == "/index.html":
            self._send_html(DASHBOARD_HTML)
        elif path == "/api/state":
            self._send_json(self.state.get_state())
        elif path.startswith("/api/history/"):
            sensor_name = path.split("/")[-1]
            self._send_json(self.state.get_history(sensor_name))
        elif path.startswith("/api/harvest/"):
            crop = path.split("/")[-1]
            self._send_json(self.state.get_harvests(crop))
        elif path == "/api/night/events":
            self._send_json(self.state.get_night_events())
        elif path == "/api/health":
            self._send_json(self.state.get_health())
        else:
            self.send_error(404, "Not found")

    def _send_html(self, html: str):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(html.encode())

    def _send_json(self, data: str):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(data.encode())


class DashboardService:
    """Dashboard server using stdlib http.server.

    NOTE: FastAPI is optional — this implementation uses only stdlib
    so it works on a bare Pi Zero without extra packages.
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 9195) -> None:
        self._host = host
        self._port = port
        self.state = DashboardState()
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        DashboardHandler.state = self.state
        self._server = HTTPServer((self._host, self._port), DashboardHandler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        logger.info("Dashboard started on %s:%d", self._host, self._port)

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None

    def update_state(self, summary: dict) -> None:
        self.state.update(summary)

    def update_health(self, health: dict) -> None:
        self.state.update_health(health)

    @property
    def url(self) -> str:
        return f"http://{self._host}:{self._port}"