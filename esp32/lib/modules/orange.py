"""Orange / citrus harvest tracking module for the Terra-Fin Walking Stick.

NOTE: This module mirrors the AvocadoHarvest interface but is tuned for orange
and citrus crops. It provides JSON-file-backed harvest logging, a daily
summary, a citrus-specific soil quality assessment, a rough Brix (sugar
content) estimate, and a harvest-window helper driven by GPS positions.

WHY: Citrus harvest decisions depend on different thresholds than avocado —
moisture 40-70 %, pH 5.5-6.5 — and Brix is the key ripeness indicator for
oranges. Keeping crop-specific logic in its own module (rather than overloading
a generic harvester) keeps each crop's heuristics readable, testable, and
independently evolvable.

The class is mock-safe: it never touches hardware directly and operates purely
on the SensorReading data contract, so tests can feed in synthetic readings.
On MicroPython the module persists entries as a list of dicts in a .json file
(when a db_path is given) or keeps them in memory (when db_path is None) so the
class is trivially testable with no filesystem cleanup.
"""


try:
    import _thread as thread_mod
except ImportError:
    import threading as thread_mod

def _make_lock():
    if hasattr(thread_mod, "allocate_lock"):
        return thread_mod.allocate_lock()
    return thread_mod.Lock()

import json
import logging
import os

from core.types import HarvestEntry, SensorReading, GPSPosition, utc_now

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Citrus-specific thresholds
# ---------------------------------------------------------------------------
# NOTE: These are the soil condition bands used by quality_assessment(). They
# are module-level constants so tests and other modules can reference them and
# so the thresholds are easy to tune for a different citrus variety.
_CITRUS_MOISTURE_LOW = 40.0   # % — below this is "too dry" for citrus
_CITRUS_MOISTURE_HIGH = 70.0  # % — above this is "too wet" for citrus
_CITRUS_PH_LOW = 5.5
_CITRUS_PH_HIGH = 6.5

# Metric key names used across the project's sensors (see soil_moisture.py,
# soil_ph.py, temp_humidity.py). Centralized here so a rename is one edit.
_MOISTURE_KEY = "soil_moisture_pct"
_PH_KEY = "soil_pH"
_TEMP_KEY = "temp_c"


class OrangeHarvest:
    """JSON-file-backed harvest tracker for oranges and citrus.

    The class owns its own JSON store (separate from the core Recorder) so a
    single crop module can be used standalone in tests or scripts without
    pulling in the full recording stack. Access to the in-memory entry list is
    guarded by an internal lock for basic thread safety, matching the
    convention in ``core.recorder.Recorder``.

    Parameters
    ----------
    db_path:
        Path to the JSON file used for persistence. When ``None`` (default) the
        class keeps entries in memory only, so it is trivially testable with no
        filesystem cleanup. When a path is given, entries are loaded on init
        and saved after every mutation.
    """

    def __init__(self, db_path=None):
        self._db_path = db_path
        self._lock = _make_lock()
        self._entries = []
        if db_path:
            self._load()

    # ------------------------------------------------------------------
    # Persistence lifecycle
    # ------------------------------------------------------------------

    def _load(self):
        """Load entries from the JSON file into ``self._entries``.

        Creates the parent directory for file-backed stores (mirroring the old
        SQLite init). A missing or corrupt file is treated as an empty store so
        the class is robust to a fresh filesystem on the ESP32.
        """
        try:
            parent = os.path.dirname(self._db_path) or "."
            os.makedirs(parent, exist_ok=True)
        except OSError:
            # Parent may already exist or be unwritable; _load still tries to read.
            pass
        try:
            with open(self._db_path) as f:
                data = json.load(f)
            if isinstance(data, list):
                self._entries = data
            else:
                self._entries = []
        except (OSError, ValueError):
            # Missing file or malformed JSON — start with an empty store.
            self._entries = []

    def _save(self):
        """Persist ``self._entries`` to the JSON file, if a path was given.

        Failures are logged but never raised so a transient flash write error
        does not crash a harvest-logging call on the stick.
        """
        if not self._db_path:
            return
        try:
            with open(self._db_path, "w") as f:
                json.dump(self._entries, f)
        except OSError as e:
            logger.error("Save failed: %s", e)

    # ------------------------------------------------------------------
    # Harvest logging
    # ------------------------------------------------------------------

    def log_harvest(self, count, weight_kg, location, tree_id=None, notes=""):
        """Record a single orange harvest entry and return it.

        Parameters
        ----------
        count:
            Number of oranges (or pieces of citrus) harvested.
        weight_kg:
            Total weight of this harvest entry, in kilograms.
        location:
            Human-readable location label (grove name, block, etc.).
        tree_id:
            Optional identifier of the specific tree. Used by
            ``daily_summary`` to compute per-tree averages.
        notes:
            Free-text notes (quality grade, picker, etc.).

        Returns
        -------
        HarvestEntry
            The persisted entry with ``crop='orange'`` and a UTC timestamp.
        """
        entry = HarvestEntry(
            crop="orange",
            timestamp=utc_now(),
            count=count,
            weight_kg=weight_kg,
            location=location,
            notes=notes,
            tree_id=tree_id,
        )
        with self._lock:
            self._entries.append(entry.to_dict())
            self._save()
        logger.info(
            "[orange] logged harvest: %d oranges, %.2f kg @ %s",
            count,
            weight_kg,
            location,
        )
        return entry

    # ------------------------------------------------------------------
    # Daily summary
    # ------------------------------------------------------------------

    def daily_summary(self, date=None):
        """Aggregate orange harvests for a single day.

        Parameters
        ----------
        date:
            ``YYYY-MM-DD`` string. If ``None``, defaults to today's UTC date.

        Returns
        -------
        dict
            ``{
              "date": str,
              "total_count": int,
              "total_weight_kg": float,
              "avg_per_tree": float,
              "trees_visited": int,
            }``

        ``avg_per_tree`` is ``0.0`` when no trees (with a ``tree_id``) were
        visited, to avoid a divide-by-zero. ``trees_visited`` counts distinct
        non-null ``tree_id`` values.
        """
        if date is None:
            date = utc_now()[:10]  # "YYYY-MM-DD"

        prefix = date
        total_count = 0
        total_weight = 0.0
        trees = set()
        with self._lock:
            for row in self._entries:
                if row.get("crop") != "orange":
                    continue
                ts = row.get("timestamp", "")
                if not ts.startswith(prefix):
                    continue
                total_count += row.get("count", 0)
                total_weight += row.get("weight_kg", 0.0)
                tid = row.get("tree_id")
                if tid is not None:
                    trees.add(tid)

        avg_per_tree = (total_count / len(trees)) if trees else 0.0

        return {
            "date": date,
            "total_count": total_count,
            "total_weight_kg": round(total_weight, 4),
            "avg_per_tree": round(avg_per_tree, 4),
            "trees_visited": len(trees),
        }

    # ------------------------------------------------------------------
    # Quality assessment
    # ------------------------------------------------------------------

    def quality_assessment(self, reading):
        """Assess soil conditions for a citrus harvest decision.

        Uses the project's standard metric keys:
          * ``soil_moisture_pct`` (percent)
          * ``soil_pH``

        Decision order (first match wins):
          1. Missing moisture or pH  -> ``"insufficient sensor data"``
          2. Moisture < 40 %          -> ``"moisture too low for citrus"``
          3. Moisture > 70 %          -> ``"moisture too high for citrus"``
          4. pH < 5.5 or pH > 6.5     -> ``"pH outside citrus range (5.5-6.5)"``
          5. Otherwise               -> ``"optimal conditions for citrus harvest"``

        NOTE: Moisture is checked before pH so that a gross moisture problem is
        reported first; the pH branch is only reached when moisture is already
        in the acceptable band.
        """
        metrics = reading.metrics
        moisture = metrics.get(_MOISTURE_KEY)
        ph = metrics.get(_PH_KEY)

        if moisture is None or ph is None:
            return "insufficient sensor data"

        if moisture < _CITRUS_MOISTURE_LOW:
            return "moisture too low for citrus"
        if moisture > _CITRUS_MOISTURE_HIGH:
            return "moisture too high for citrus"
        if ph < _CITRUS_PH_LOW or ph > _CITRUS_PH_HIGH:
            return "pH outside citrus range (5.5-6.5)"

        return "optimal conditions for citrus harvest"

    # ------------------------------------------------------------------
    # Brix estimate (approximate)
    # ------------------------------------------------------------------

    def brix_estimate(self, reading):
        """Roughly estimate the Brix (sugar content) of citrus from a sensor reading.

        .. warning::
            **APPROXIMATE PLACEHOLDER FORMULA.** This is NOT a calibrated
            model. It is a heuristic stand-in so the agent has a number to
            reason about until a real refractometer-based calibration (or a
            trained regression on historical harvest + sensor data) is
            available. Treat the output as a qualitative indicator only.

        The placeholder formula is::

            base_brix = 12.0 + (temp_c - 20) * 0.2 - (100 - moisture_pct) * 0.01

        - ``temp_c``    : air/soil temperature in °C (metric key ``temp_c``)
        - ``moisture_pct`` : soil moisture in % (metric key ``soil_moisture_pct``)
        - ``12.0``      : a typical mid-season orange Brix baseline
        - Warmer temps nudge the estimate up; drier soil nudges it down very
          slightly.

        Returns
        -------
        float or None
            The estimated Brix, or ``None`` if either ``temp_c`` or
            ``soil_moisture_pct`` is absent from ``reading.metrics``.
        """
        metrics = reading.metrics
        temp_c = metrics.get(_TEMP_KEY)
        moisture_pct = metrics.get(_MOISTURE_KEY)

        if temp_c is None or moisture_pct is None:
            return None

        base_brix = 12.0 + (temp_c - 20) * 0.2 - (100 - moisture_pct) * 0.01
        return round(base_brix, 2)

    # ------------------------------------------------------------------
    # Harvest window (GPS-based)
    # ------------------------------------------------------------------

    def harvest_window(self, gps_positions):
        """Summarize the spatial spread of a harvest session from GPS fixes.

        Given a list of GPS positions captured during a harvest session,
        return a dict describing the bounding box, number of stops, and
        estimated area covered. Mirrors the AvocadoHarvest interface so any
        UI or reporting code can treat crop modules interchangeably.

        Returns
        -------
        dict
            ``{
              "stops": int,
              "bbox": {"min_lat", "max_lat", "min_lon", "max_lon"} or None,
              "lat_span": float,
              "lon_span": float,
            }``

        For an empty list, ``bbox`` is ``None`` and spans are ``0.0``.
        """
        if not gps_positions:
            return {
                "stops": 0,
                "bbox": None,
                "lat_span": 0.0,
                "lon_span": 0.0,
            }

        lats = [p.lat for p in gps_positions]
        lons = [p.lon for p in gps_positions]
        min_lat, max_lat = min(lats), max(lats)
        min_lon, max_lon = min(lons), max(lons)

        return {
            "stops": len(gps_positions),
            "bbox": {
                "min_lat": min_lat,
                "max_lat": max_lat,
                "min_lon": min_lon,
                "max_lon": max_lon,
            },
            "lat_span": round(max_lat - min_lat, 6),
            "lon_span": round(max_lon - min_lon, 6),
        }

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close(self):
        """Flush any pending entries and release the store. Safe to call multiple times.

        For an in-memory store this is a no-op; for a file-backed store it
        performs one final save so buffered writes are not lost.
        """
        with self._lock:
            self._save()