"""Local greens harvest tracking module for the Agricultural Walking Stick Agent.

NOTE: This module tracks harvests of Kenyan leafy greens — sukuma wiki (kale),
spinach, and managu (African nightshade). It persists entries to SQLite with a
crop_type column so daily summaries can break down harvests by greens variety.

WHY: Greens are a staple smallholder crop in Kenya and are harvested repeatedly
from the same plot (cut-and-come-again). Tracking per-variety yield helps farmers
decide which greens perform best on their soil and when to re-sow.

NOTE: This module deliberately does NOT import from core.config — all thresholds
are kept local to keep the module self-contained and mock-safe for testing.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any

from core.types import HarvestEntry, SensorReading, GPSPosition, utc_now


# ---------------------------------------------------------------------------
# Greens quality thresholds (local to this module)
# ---------------------------------------------------------------------------

# Soil moisture range for healthy greens, in percent.
SOIL_MOISTURE_MIN = 50.0
SOIL_MOISTURE_MAX = 80.0

# Soil pH range for healthy greens.
SOIL_PH_MIN = 6.0
SOIL_PH_MAX = 7.0

# Leaf condition temperature range, in degrees Celsius.
LEAF_TEMP_MIN = 15.0
LEAF_TEMP_MAX = 25.0
LEAF_HUMIDITY_MIN = 50.0   # humidity threshold for "good" leaves
WILT_TEMP = 28.0           # above this, leaves wilt
WILT_HUMIDITY = 30.0       # below this humidity, leaves wilt
FROST_TEMP = 5.0           # below this, frost risk


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS harvest_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    crop TEXT NOT NULL,
    crop_type TEXT NOT NULL DEFAULT 'kale',
    timestamp TEXT NOT NULL,
    count INTEGER NOT NULL,
    weight_kg REAL NOT NULL,
    location TEXT NOT NULL,
    notes TEXT DEFAULT '',
    tree_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_greens_crop_type ON harvest_entries(crop_type, timestamp);
"""


class GreensHarvest:
    """SQLite-backed harvest tracker for local Kenyan leafy greens.

    NOTE: Uses stdlib sqlite3 with parameterized queries (no SQL injection).
    Supports ``:memory:`` mode for testing and uses check_same_thread=False.

    WHY: Each greens variety (kale, spinach, managu) has different yield
    characteristics. Storing a ``crop_type`` column alongside the shared
    ``crop='greens'`` contract lets us break down daily summaries by variety
    while remaining compatible with the generic recorder schema.
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    # ------------------------------------------------------------------
    # Database setup
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        """Create the harvest_entries table if it does not exist."""
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA_SQL)
        self._conn.commit()

    def _ensure_connected(self) -> sqlite3.Connection:
        if self._conn is None:
            self._init_db()
        assert self._conn is not None
        return self._conn

    # ------------------------------------------------------------------
    # Harvest logging
    # ------------------------------------------------------------------

    def log_harvest(
        self,
        count: int,
        weight_kg: float,
        location: str,
        crop_type: str = "kale",
        tree_id: str | None = None,
        notes: str = "",
    ) -> HarvestEntry:
        """Log a single greens harvest entry.

        NOTE: The ``crop`` field of the returned HarvestEntry is set to the
        crop_type value (e.g. 'kale', 'spinach', 'managu') for simplicity.
        The crop_type is also stored in its own column for querying.
        """
        conn = self._ensure_connected()
        ts = utc_now()
        # Set crop field to crop_type value per task spec.
        entry = HarvestEntry(
            crop=crop_type,
            timestamp=ts,
            count=count,
            weight_kg=weight_kg,
            location=location,
            notes=notes,
            tree_id=tree_id,
        )
        conn.execute(
            """INSERT INTO harvest_entries
               (crop, crop_type, timestamp, count, weight_kg, location, notes, tree_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (entry.crop, crop_type, ts, count, weight_kg, location, notes, tree_id),
        )
        conn.commit()
        return entry

    # ------------------------------------------------------------------
    # Daily summary
    # ------------------------------------------------------------------

    def daily_summary(self, date: str | None = None) -> dict[str, Any]:
        """Return total count, total weight, and breakdown by crop_type.

        Args:
            date: Optional ISO date string ``YYYY-MM-DD``. If None, uses today's
                UTC date.

        Returns:
            dict with keys: ``date``, ``total_count``, ``total_weight_kg``,
            ``breakdown`` (dict of crop_type -> {count, weight_kg, entries}).
        """
        conn = self._ensure_connected()
        if date is None:
            date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        sql = (
            "SELECT crop_type, COUNT(*) as entries, "
            "SUM(count) as total_count, SUM(weight_kg) as total_weight "
            "FROM harvest_entries WHERE timestamp LIKE ? "
            "GROUP BY crop_type ORDER BY crop_type"
        )
        rows = conn.execute(sql, (f"{date}%",)).fetchall()

        breakdown: dict[str, dict[str, Any]] = {}
        total_count = 0
        total_weight = 0.0
        for row in rows:
            ct = row["crop_type"]
            c = row["total_count"] or 0
            w = row["total_weight"] or 0.0
            breakdown[ct] = {"count": c, "weight_kg": w, "entries": row["entries"]}
            total_count += c
            total_weight += w

        return {
            "date": date,
            "total_count": total_count,
            "total_weight_kg": total_weight,
            "breakdown": breakdown,
        }

    # ------------------------------------------------------------------
    # Quality assessment
    # ------------------------------------------------------------------

    def quality_assessment(self, reading: SensorReading) -> str:
        """Assess soil conditions for greens based on a sensor reading.

        NOTE: Checks moisture (percent) and pH from the reading's metrics dict.
        Returns a human-readable assessment string.
        """
        metrics = reading.metrics or {}
        moisture = metrics.get("soil_moisture_pct")
        ph = metrics.get("soil_ph")

        if moisture is None or ph is None:
            return "insufficient sensor data"

        if moisture < SOIL_MOISTURE_MIN:
            return "soil too dry for greens"
        if moisture > SOIL_MOISTURE_MAX:
            return "soil too wet for greens"
        if ph < SOIL_PH_MIN or ph > SOIL_PH_MAX:
            return "pH outside greens range (6.0-7.0)"
        return "optimal conditions for greens"

    # ------------------------------------------------------------------
    # Leaf condition
    # ------------------------------------------------------------------

    def leaf_condition(self, temp_c: float, humidity_pct: float) -> str:
        """Assess leaf condition from ambient temperature and humidity.

        Returns one of: ``good``, ``wilt_risk``, ``frost_risk``, ``fair``.
        """
        if temp_c < FROST_TEMP:
            return "frost_risk"
        if temp_c > WILT_TEMP or humidity_pct < WILT_HUMIDITY:
            return "wilt_risk"
        if LEAF_TEMP_MIN <= temp_c <= LEAF_TEMP_MAX and humidity_pct >= LEAF_HUMIDITY_MIN:
            return "good"
        return "fair"

    # ------------------------------------------------------------------
    # Harvest window (GPS-based)
    # ------------------------------------------------------------------

    def harvest_window(self, gps_positions: list[GPSPosition]) -> dict[str, Any]:
        """Summarize the harvest window from a list of GPS positions.

        NOTE: Returns start/end times, point count, and a simple bounding box.
        WHY: Farmers walk their plots during harvest — the GPS track captures
        the area covered and the duration of the harvest session.
        """
        if not gps_positions:
            return {
                "start_time": None,
                "end_time": None,
                "point_count": 0,
                "bbox": None,
            }

        timestamps = [p.timestamp for p in gps_positions if p.timestamp]
        start_time = min(timestamps) if timestamps else None
        end_time = max(timestamps) if timestamps else None

        lats = [p.lat for p in gps_positions]
        lons = [p.lon for p in gps_positions]
        bbox = {
            "min_lat": min(lats),
            "max_lat": max(lats),
            "min_lon": min(lons),
            "max_lon": max(lons),
        }

        return {
            "start_time": start_time,
            "end_time": end_time,
            "point_count": len(gps_positions),
            "bbox": bbox,
        }

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None