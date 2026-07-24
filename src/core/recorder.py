"""SQLite persistence for all sensor readings and events.

NOTE: Uses stdlib sqlite3 with parameterized queries (no SQL injection).
Supports :memory: mode for testing. Thread-safe via check_same_thread=False.

WHY: The recorder decouples data persistence from the sensors — any module
can record without knowing the database schema details.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any

from .types import SensorReading, HarvestEntry, NightEvent, GPSPosition

logger = logging.getLogger(__name__)


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sensor_readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sensor_name TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    metrics_json TEXT NOT NULL,
    units_json TEXT NOT NULL,
    metadata_json TEXT
);

CREATE TABLE IF NOT EXISTS harvest_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    crop TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    count INTEGER NOT NULL,
    weight_kg REAL NOT NULL,
    location TEXT NOT NULL,
    notes TEXT DEFAULT '',
    tree_id TEXT
);

CREATE TABLE IF NOT EXISTS night_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    description TEXT NOT NULL,
    location_json TEXT,
    severity TEXT DEFAULT 'info'
);

CREATE TABLE IF NOT EXISTS gps_track (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    altitude_m REAL,
    timestamp TEXT NOT NULL,
    fix_quality TEXT DEFAULT 'unknown'
);

CREATE INDEX IF NOT EXISTS idx_readings_sensor ON sensor_readings(sensor_name, timestamp);
CREATE INDEX IF NOT EXISTS idx_harvests_crop ON harvest_entries(crop, timestamp);
CREATE INDEX IF NOT EXISTS idx_night_events_time ON night_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_gps_track_time ON gps_track(timestamp);
"""


class Recorder:
    """SQLite-backed data recorder for the agricultural stick agent.

    Thread-safe (uses check_same_thread=False and a Lock).
    Supports both file-based and in-memory databases.
    """

    def __init__(self, db_path: str = "data/terra-fin.db") -> None:
        self._db_path = db_path
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None

    def init_db(self) -> None:
        """Initialize the database and create tables."""
        with self._lock:
            if self._db_path != ":memory:":
                os.makedirs(
                    os.path.dirname(self._db_path) or ".",
                    exist_ok=True,
                )

            self._conn = sqlite3.connect(
                self._db_path,
                check_same_thread=False,
            )
            self._conn.row_factory = sqlite3.Row
            self._conn.executescript(SCHEMA_SQL)
            self._conn.commit()

    def _ensure_connected(self) -> sqlite3.Connection:
        if self._conn is None:
            self.init_db()
        assert self._conn is not None
        return self._conn

    def record_reading(self, reading: SensorReading) -> int:
        """Record a sensor reading. Returns the row ID."""
        import json

        with self._lock:
            conn = self._ensure_connected()
            cursor = conn.execute(
                """INSERT INTO sensor_readings
                   (sensor_name, timestamp, metrics_json, units_json, metadata_json)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    reading.sensor_name,
                    reading.timestamp,
                    json.dumps(reading.metrics),
                    json.dumps(reading.units),
                    json.dumps(reading.metadata),
                ),
            )
            conn.commit()
            return cursor.lastrowid or 0

    def record_harvest(self, entry: HarvestEntry) -> int:
        """Record a harvest entry. Returns the row ID."""
        with self._lock:
            conn = self._ensure_connected()
            cursor = conn.execute(
                """INSERT INTO harvest_entries
                   (crop, timestamp, count, weight_kg, location, notes, tree_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    entry.crop,
                    entry.timestamp,
                    entry.count,
                    entry.weight_kg,
                    entry.location,
                    entry.notes,
                    entry.tree_id,
                ),
            )
            conn.commit()
            return cursor.lastrowid or 0

    def record_night_event(self, event: NightEvent) -> int:
        """Record a night mode event. Returns the row ID."""
        import json

        loc_json = None
        if event.location is not None:
            loc_json = json.dumps(event.location.to_dict())

        with self._lock:
            conn = self._ensure_connected()
            cursor = conn.execute(
                """INSERT INTO night_events
                   (event_type, timestamp, description, location_json, severity)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    event.event_type,
                    event.timestamp,
                    event.description,
                    loc_json,
                    event.severity,
                ),
            )
            conn.commit()
            return cursor.lastrowid or 0

    def record_gps(self, position: GPSPosition) -> int:
        """Record a GPS position. Returns the row ID."""
        with self._lock:
            conn = self._ensure_connected()
            cursor = conn.execute(
                """INSERT INTO gps_track
                   (lat, lon, altitude_m, timestamp, fix_quality)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    position.lat,
                    position.lon,
                    position.altitude_m,
                    position.timestamp,
                    position.fix_quality,
                ),
            )
            conn.commit()
            return cursor.lastrowid or 0

    def query_readings(
        self, sensor_name: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> list[dict]:
        """Query sensor readings with optional filters."""
        import json

        with self._lock:
            conn = self._ensure_connected()
            sql = "SELECT * FROM sensor_readings WHERE 1=1"
            params: list[Any] = []
            if sensor_name is not None:
                sql += " AND sensor_name = ?"
                params.append(sensor_name)
            if start_time is not None:
                sql += " AND timestamp >= ?"
                params.append(start_time)
            if end_time is not None:
                sql += " AND timestamp <= ?"
                params.append(end_time)
            sql += " ORDER BY timestamp DESC"
            rows = conn.execute(sql, params).fetchall()
            results = []
            for row in rows:
                d = dict(row)
                d["metrics"] = json.loads(d["metrics_json"])
                d["units"] = json.loads(d["units_json"])
                d["metadata"] = json.loads(d.get("metadata_json", "{}"))
                del d["metrics_json"]
                del d["units_json"]
                del d["metadata_json"]
                results.append(d)
            return results

    def query_harvests(self, crop: str | None = None, date: str | None = None) -> list[dict]:
        """Query harvest entries with optional filters."""
        with self._lock:
            conn = self._ensure_connected()
            sql = "SELECT * FROM harvest_entries WHERE 1=1"
            params: list[Any] = []
            if crop is not None:
                sql += " AND crop = ?"
                params.append(crop)
            if date is not None:
                sql += " AND timestamp LIKE ?"
                params.append(f"{date}%")
            sql += " ORDER BY timestamp DESC"
            rows = conn.execute(sql, params).fetchall()
            return [dict(row) for row in rows]

    def query_night_events(
        self, start_time: str | None = None, end_time: str | None = None
    ) -> list[dict]:
        """Query night mode events with optional time filters."""
        with self._lock:
            conn = self._ensure_connected()
            sql = "SELECT * FROM night_events WHERE 1=1"
            params: list[Any] = []
            if start_time is not None:
                sql += " AND timestamp >= ?"
                params.append(start_time)
            if end_time is not None:
                sql += " AND timestamp <= ?"
                params.append(end_time)
            sql += " ORDER BY timestamp DESC"
            rows = conn.execute(sql, params).fetchall()
            return [dict(row) for row in rows]

    def query_gps_track(
        self, start_time: str | None = None, end_time: str | None = None
    ) -> list[dict]:
        """Query GPS track points with optional time filters."""
        with self._lock:
            conn = self._ensure_connected()
            sql = "SELECT * FROM gps_track WHERE 1=1"
            params: list[Any] = []
            if start_time is not None:
                sql += " AND timestamp >= ?"
                params.append(start_time)
            if end_time is not None:
                sql += " AND timestamp <= ?"
                params.append(end_time)
            sql += " ORDER BY timestamp DESC"
            rows = conn.execute(sql, params).fetchall()
            return [dict(row) for row in rows]

    def close(self) -> None:
        """Close the database connection."""
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None