"""Local greens harvest tracking module for the Terra-Fin Agent.

NOTE: This module tracks harvests of Kenyan leafy greens — sukuma wiki (kale),
spinach, and managu (African nightshade). It persists entries to a JSON file
with a crop_type field so daily summaries can break down harvests by greens
variety.

WHY: Greens are a staple smallholder crop in Kenya and are harvested repeatedly
from the same plot (cut-and-come-again). Tracking per-variety yield helps farmers
decide which greens perform best on their soil and when to re-sow.

NOTE: This module deliberately does NOT import from core.config — all thresholds
are kept local to keep the module self-contained and mock-safe for testing.
"""

import json
import logging

try:
    import _thread as thread_mod
except ImportError:
    import threading as thread_mod


def _make_lock():
    if hasattr(thread_mod, "allocate_lock"):
        return thread_mod.allocate_lock()
    return thread_mod.Lock()


from core.types import HarvestEntry, SensorReading, GPSPosition, utc_now

logger = logging.getLogger(__name__)


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


class GreensHarvest:
    """JSON-backed harvest tracker for local Kenyan leafy greens.

    NOTE: Persists entries as a list of dicts in a JSON file (no SQL injection
    surface). Supports in-memory mode (``db_path=None``) for testing and uses
    an internal lock for basic thread safety.

    WHY: Each greens variety (kale, spinach, managu) has different yield
    characteristics. Storing a ``crop_type`` field alongside the shared
    ``crop='greens'`` contract lets us break down daily summaries by variety
    while remaining compatible with the generic recorder schema.
    """

    def __init__(self, db_path=None):
        self._db_path = db_path
        self._lock = _make_lock()
        self._entries = []
        if db_path:
            self._load()

    # ------------------------------------------------------------------
    # JSON persistence
    # ------------------------------------------------------------------

    def _load(self):
        """Load harvest entries from the JSON file, if it exists.

        On any read/parse error the entry list is reset to empty so the tracker
        remains usable (and a subsequent save recreates the file).
        """
        try:
            with open(self._db_path) as f:
                self._entries = json.load(f)
        except (OSError, ValueError):
            self._entries = []

    def _save(self):
        """Persist the in-memory entry list to the JSON file.

        A no-op when running in-memory (``db_path is None``). Save failures are
        logged but never raised so a bad filesystem does not take down a
        harvest-session in progress.
        """
        if self._db_path:
            try:
                with open(self._db_path, "w") as f:
                    json.dump(self._entries, f)
            except OSError as e:
                logger.error("Save failed: %s", e)

    # ------------------------------------------------------------------
    # Harvest logging
    # ------------------------------------------------------------------

    def log_harvest(
        self,
        count: int,
        weight_kg: float,
        location: str,
        crop_type: str = "kale",
        tree_id=None,
        notes: str = "",
    ) -> HarvestEntry:
        """Log a single greens harvest entry.

        NOTE: The ``crop`` field of the returned HarvestEntry is set to the
        crop_type value (e.g. 'kale', 'spinach', 'managu') for simplicity.
        The crop_type is also stored as its own field for querying.
        """
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
        record = {
            "crop": entry.crop,
            "crop_type": crop_type,
            "timestamp": ts,
            "count": count,
            "weight_kg": weight_kg,
            "location": location,
            "notes": notes,
            "tree_id": tree_id,
        }
        with self._lock:
            self._entries.append(record)
            self._save()
        return entry

    # ------------------------------------------------------------------
    # Daily summary
    # ------------------------------------------------------------------

    def daily_summary(self, date=None) -> dict:
        """Return total count, total weight, and breakdown by crop_type.

        Args:
            date: Optional ISO date string ``YYYY-MM-DD``. If None, uses today's
                UTC date.

        Returns:
            dict with keys: ``date``, ``total_count``, ``total_weight_kg``,
            ``breakdown`` (dict of crop_type -> {count, weight_kg, entries}).
        """
        if date is None:
            date = utc_now()[:10]  # "YYYY-MM-DD"

        with self._lock:
            entries = [
                e for e in self._entries
                if e.get("timestamp", "").startswith(date)
            ]

        breakdown = {}
        total_count = 0
        total_weight = 0.0
        for e in entries:
            ct = e.get("crop_type", "kale")
            c = e.get("count", 0)
            w = e.get("weight_kg", 0.0)
            if ct not in breakdown:
                breakdown[ct] = {"count": 0, "weight_kg": 0.0, "entries": 0}
            breakdown[ct]["count"] += c
            breakdown[ct]["weight_kg"] += w
            breakdown[ct]["entries"] += 1
            total_count += c
            total_weight += w

        # Match the original ``ORDER BY crop_type`` ordering.
        ordered = {}
        for k in sorted(breakdown):
            ordered[k] = breakdown[k]
        breakdown = ordered

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

    def harvest_window(self, gps_positions) -> dict:
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
        """Close the tracker.

        NOTE: JSON persistence saves eagerly on every ``log_harvest`` call, so
        there is no buffered state to flush here. This method is kept for
        interface compatibility and is safe to call multiple times.
        """
        pass