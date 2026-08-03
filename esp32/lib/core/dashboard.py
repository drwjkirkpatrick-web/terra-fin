"""Lightweight dashboard for Terra-Fin Agent (ESP32/MicroPython).

NOTE: Uses MicroPython socket or standard library http.server.
Serves a self-contained HTML page with no external assets.
"""

import json
import logging

try:
    import _thread as thread_mod
except ImportError:
    import threading as thread_mod

logger = logging.getLogger(__name__)


def _make_lock():
    if hasattr(thread_mod, 'allocate_lock'):
        return thread_mod.allocate_lock()
    return thread_mod.Lock()


class DashboardState:
    """Thread-safe shared state for the dashboard."""

    def __init__(self):
        self._lock = _make_lock()
        self._state = {
            "timestamp": "",
            "sensors": {},
            "cross_sensor": {},
        }
        self._history = {}
        self._harvests = {}
        self._night_events = []
        self._health = {}

    def update(self, summary):
        with self._lock:
            self._state = summary

    def update_history(self, sensor_name, readings):
        with self._lock:
            self._history[sensor_name] = readings

    def update_harvests(self, crop, entries):
        with self._lock:
            self._harvests[crop] = entries

    def update_night_events(self, events):
        with self._lock:
            self._night_events = events

    def update_health(self, health):
        with self._lock:
            self._health = health

    def get_state(self):
        with self._lock:
            return json.dumps(self._state)

    def get_history(self):
        with self._lock:
            return json.dumps(self._history)

    def get_harvests(self):
        with self._lock:
            return json.dumps(self._harvests)

    def get_night_events(self):
        with self._lock:
            return json.dumps(self._night_events)

    def get_health(self):
        with self._lock:
            return json.dumps(self._health)


HTML_PAGE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Terra-Fin Dashboard</title>
<style>
body { font-family: sans-serif; margin: 1em; background: #1a1a1a; color: #eee; }
h1 { color: #4CAF50; }
.card { background: #2a2a2a; border-radius: 8px; padding: 1em; margin: 0.5em 0; }
.metric { font-size: 1.2em; font-weight: bold; color: #FFC107; }
.ok { color: #4CAF50; }
.warn { color: #FF9800; }
.err { color: #F44336; }
pre { white-space: pre-wrap; }
</style>
</head>
<body>
<h1>Terra-Fin Dashboard</h1>
<div class="card">
  <p>Status: <span id="status">Loading...</span></p>
  <p>Timestamp: <span id="ts">-</span></p>
</div>
<div class="card">
  <h2>Sensors</h2>
  <pre id="sensors">Loading...</pre>
</div>
<div class="card">
  <h2>Adaptation Advisories</h2>
  <pre id="adapt">Loading...</pre>
</div>
<script>
async function refresh() {
  try {
    const r = await fetch('/api/state');
    const d = await r.json();
    document.getElementById('ts').textContent = d.timestamp || '-';
    document.getElementById('sensors').textContent = JSON.stringify(d.sensors || {}, null, 2);
    document.getElementById('status').textContent = 'Active';
    const a = await fetch('/api/adapt');
    const ad = await a.json();
    document.getElementById('adapt').textContent = JSON.stringify(ad, null, 2);
  } catch (e) {
    document.getElementById('status').textContent = 'Error: ' + e;
  }
}
refresh();
setInterval(refresh, 5000);
</script>
</body>
</html>
"""


class DashboardServer:
    """HTTP dashboard server for ESP32."""

    def __init__(self, state, host="0.0.0.0", port=80, engine=None):
        self._state = state
        self._host = host
        self._port = port
        self._engine = engine
        self._srv = None

    def start(self):
        try:
            import usocket as socket
            _upython = True
        except ImportError:
            import socket
            _upython = False

        self._srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._srv.bind((self._host, self._port))
        self._srv.listen(5)
        logger.info("Dashboard on http://%s:%d", self._host, self._port)

        if _upython:
            import _thread
            _thread.start_new_thread(self._serve_upython, ())
        else:
            import threading
            threading.Thread(target=self._serve_std, daemon=True).start()

    def _serve_upython(self):
        while True:
            try:
                conn, addr = self._srv.accept()
                self._handle_conn(conn)
            except Exception as e:
                logger.error("Dashboard accept error: %s", e)

    def _serve_std(self):
        while True:
            try:
                conn, addr = self._srv.accept()
                import threading
                threading.Thread(target=self._handle_conn, args=(conn,), daemon=True).start()
            except Exception as e:
                logger.error("Dashboard accept error: %s", e)

    def _handle_conn(self, conn):
        try:
            request = conn.recv(1024).decode('utf-8', 'ignore')
            lines = request.split('\r\n')
            first = lines[0] if lines else ''
            path = first.split(' ')[1] if len(first.split(' ')) > 1 else '/'

            if path == '/':
                body = HTML_PAGE.encode('utf-8')
                headers = b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: %d\r\n\r\n" % len(body)
                conn.send(headers + body)
            elif path == '/api/state':
                body = self._state.get_state().encode('utf-8')
                headers = b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: %d\r\n\r\n" % len(body)
                conn.send(headers + body)
            elif path == '/api/adapt':
                if self._engine:
                    advisories = self._engine.get_adaptation_advisories()
                    body = json.dumps(advisories).encode('utf-8')
                else:
                    body = b'[]'
                headers = b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: %d\r\n\r\n" % len(body)
                conn.send(headers + body)
            else:
                conn.send(b"HTTP/1.1 404 Not Found\r\n\r\n")
        except Exception as e:
            logger.error("Dashboard handler error: %s", e)
        finally:
            conn.close()

    def stop(self):
        if self._srv:
            self._srv.close()
            self._srv = None
