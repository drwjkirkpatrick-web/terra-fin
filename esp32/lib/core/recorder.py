"""JSON persistence for all sensor readings and events (ESP32/MicroPython).

NOTE: Replaces sqlite3 with JSON line files. Each record type has its own
.jsonl file. Thread-safe via _thread locks.

WHY: MicroPython has no sqlite3. JSON files are zero-config, inspectable
from a phone, and compress well for cellular upload.
"""

import logging
import os
import json
import time

try:
    import _thread as thread_mod
except ImportError:
    import threading as thread_mod

from .types import SensorReading, HarvestEntry, NightEvent, GPSPosition

logger = logging.getLogger(__name__)


def _make_lock():
    if hasattr(thread_mod, 'allocate_lock'):
        return thread_mod.allocate_lock()
    return thread_mod.Lock()


def _ensure_dir(path):
    """Ensure directory exists (MicroPython-compatible)."""
    try:
        os.mkdir(path)
    except OSError:
        pass


class Recorder:
    """JSONL-backed data recorder for the agricultural stick agent.

    Thread-safe. File per record type:
        sensor_readings.jsonl
        harvest_entries.jsonl
        night_events.jsonl
        gps_track.jsonl
    """

    def __init__(self, data_path="/flash/data/terra-fin"):
        self._data_path = data_path
        self._lock = _make_lock()
        self._initialized = False

    def init_db(self):
        """Initialize storage directory."""
        with self._lock:
            _ensure_dir(self._data_path)
            self._initialized = True

    def _path(self, name):
        return self._data_path + "/" + name + ".jsonl"

    def _append(self, name, record):
        """Append a JSON record to a .jsonl file."""
        path = self._path(name)
        with self._lock:
            try:
                f = open(path, "a")
                f.write(json.dumps(record) + "\n")
                f.close()
            except OSError as e:
                logger.error("Recorder write failed: %s", e)

    def _read_all(self, name, limit=None):
        """Read all records from a .jsonl file."""
        path = self._path(name)
        results = []
        with self._lock:
            try:
                f = open(path, "r")
                for line in f:
                    line = line.strip()
                    if line:
                        results.append(json.loads(line))
                f.close()
            except OSError:
                pass
        if limit is not None:
            results = results[-limit:]
        return results

    def record_sensor(self, reading):
        self._append("sensor_readings", reading.to_dict())

    def record_harvest(self, entry):
        self._append("harvest_entries", entry.to_dict())

    def record_night_event(self, event):
        self._append("night_events", event.to_dict())

    def record_gps(self, position):
        self._append("gps_track", position.to_dict())

    def get_sensor_history(self, sensor_name=None, limit=100):
        all_readings = self._read_all("sensor_readings", limit=limit * 3)
        if sensor_name:
            return [r for r in all_readings if r.get("sensor_name") == sensor_name][-limit:]
        return all_readings[-limit:]

    def get_harvests(self, crop=None, limit=100):
        all_harvests = self._read_all("harvest_entries", limit=limit * 3)
        if crop:
            return [h for h in all_harvests if h.get("crop") == crop][-limit:]
        return all_harvests[-limit:]

    def get_night_events(self, limit=100):
        return self._read_all("night_events", limit=limit)

    def get_gps_track(self, limit=500):
        return self._read_all("gps_track", limit=limit)

    def get_summary(self):
        return {
            "sensor_readings": len(self._read_all("sensor_readings")),
            "harvest_entries": len(self._read_all("harvest_entries")),
            "night_events": len(self._read_all("night_events")),
            "gps_track": len(self._read_all("gps_track")),
        }
