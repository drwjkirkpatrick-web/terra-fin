"""Avocado harvest tracking module for the Terra-Fin Agent.

NOTE: This module provides the AvocadoHarvest class — a self-contained JSON-file
tracker for avocado harvest entries. It logs each harvest (count, weight,
location, optional tree_id and notes), produces a daily summary, assesses soil
quality from a SensorReading, and suggests the next harvest point from a recent
GPS track. It deliberately keeps its OWN JSON persistence file so it can be
used standalone (e.g. on a phone or laptop) without pulling in the full
Recorder/core.config stack.

WHY: Avocado is a high-value crop for Kenyan smallholders, and harvest records
drive three operational decisions: (1) daily yield accounting — how many fruit
and kilograms came off the orchard today, and the per-tree average so the
farmer can spot underperforming trees; (2) a go/no-go quality check based on
soil moisture and pH at harvest time, because avocados are sensitive to water
stress (too dry → small fruit and drop, too wet → root-rot risk) and to soil
acidity (optimal pH 5.5–7.0); (3) a harvest-window planner that turns the
farmer's recent GPS walk into a coverage area and nudges the next tree
location, so the harvest proceeds systematically across the orchard rather
than re-visiting the same rows.

All methods are mock-safe — no hardware or sensor dependency is required to
construct or call any method. Persistence uses json.dump/load on a plain list
of dicts; no user-supplied string is ever evaluated as code.
"""

import json
import logging
import math

try:
    import _thread as thread_mod
except ImportError:
    import threading as thread_mod

from core.types import HarvestEntry, SensorReading, GPSPosition, utc_now

logger = logging.getLogger(__name__)


def _make_lock():
    return thread_mod.allocate_lock()


# ---------------------------------------------------------------------------
# Soil-quality thresholds for avocado (Persea americana).
# Sourced from agronomic guidance for smallholder avocado production.
# ---------------------------------------------------------------------------
_MOISTURE_LOW_PCT = 30.0      # below this → irrigate before harvest
_MOISTURE_HIGH_PCT = 70.0     # above this → wait for drainage
_PH_LOW = 5.5                # below this → soil too acidic, amend
_PH_HIGH = 7.0               # above this → soil too alkaline, amend

# Small offset (degrees) added to the track centroid to suggest the next tree.
# ~0.001° ≈ 111 m — a sensible spacing nudge for the next tree in a walk.
_NEXT_TREE_OFFSET = 0.001

# Mean Earth-related constants for converting degree deltas to kilometres.
_KM_PER_DEG_LAT = 111.32


class AvocadoHarvest:
    """Track avocado harvest entries via JSON file persistence and provide
    harvest guidance.

    NOTE: The class owns its JSON store (a list of dicts serialised to a .json
    file) and loads/saves under a lock. It does NOT import or depend on
    core.config — only core.types — so it can be unit-tested in isolation and
    embedded in lightweight frontends.

    WHY: Giving the harvest tracker its own persistence file (rather than
    sharing the Recorder) keeps the module decoupled and lets a farmer's phone
    app log harvests without the full sensor/recorder stack.
    """

    def __init__(self, db_path=None):
        """Create the tracker and initialise its JSON store.

        Args:
            db_path: JSON file path for persistent storage across sessions.
                When None (default) entries are kept in memory only and never
                written to disk — useful for tests and ephemeral use.
        """
        self._db_path = db_path
        self._lock = _make_lock()
        self._entries = []
        if db_path:
            self._load()

    # ------------------------------------------------------------------ #
    # Persistence
    # ------------------------------------------------------------------ #

    def _load(self):
        """Load entries from the JSON file, if it exists.

        NOTE: On any read error (missing file, corrupt JSON) the entry list is
        reset to empty so the tracker starts cleanly rather than crashing.
        """
        try:
            with open(self._db_path) as f:
                self._entries = json.load(f)
        except (OSError, ValueError):
            self._entries = []

    def _save(self):
        """Persist entries to the JSON file.

        NOTE: When no db_path is set this is a no-op (in-memory mode). Write
        errors are logged but never raised so a failed flash write does not
        crash the harvest logger.
        """
        if self._db_path:
            try:
                with open(self._db_path, 'w') as f:
                    json.dump(self._entries, f)
            except OSError as e:
                logger.error('Save failed: %s', e)

    # ------------------------------------------------------------------ #
    # Logging
    # ------------------------------------------------------------------ #

    def log_harvest(self, count, weight_kg, location, tree_id=None, notes=""):
        """Create and persist an avocado harvest entry, returning it.

        Args:
            count: Number of avocados harvested.
            weight_kg: Total weight in kilograms.
            location: Human-readable location label (e.g. "Block A, row 3").
            tree_id: Optional tree identifier. When provided it is used for
                per-tree averaging in daily_summary().
            notes: Optional free-text notes.

        Returns:
            The persisted HarvestEntry (crop='avocado', timestamp=utc_now()).

        NOTE: The entry dict is built from the HarvestEntry fields and
        appended to the in-memory list, then persisted via _save(). User
        text (location/notes/tree_id) is stored as plain JSON values — no
        evaluation or interpolation, so it is injection-safe by construction.
        """
        entry = HarvestEntry(
            crop="avocado",
            timestamp=utc_now(),
            count=count,
            weight_kg=weight_kg,
            location=location,
            notes=notes,
            tree_id=tree_id,
        )
        with self._lock:
            self._entries.append({
                "crop": entry.crop,
                "timestamp": entry.timestamp,
                "count": entry.count,
                "weight_kg": entry.weight_kg,
                "location": entry.location,
                "notes": entry.notes,
                "tree_id": entry.tree_id,
            })
            self._save()
        logger.info(
            "[avocado] logged %d fruit (%.2f kg) at %s tree=%s",
            count, weight_kg, location, tree_id,
        )
        return entry

    # ------------------------------------------------------------------ #
    # Daily summary
    # ------------------------------------------------------------------ #

    def daily_summary(self, date=None):
        """Summarise today's (or a given day's) avocado harvest.

        Args:
            date: Optional date prefix in 'YYYY-MM-DD' form. When None, the
                current UTC date (derived from utc_now()) is used.

        Returns:
            dict with keys:
              - total_count (int): sum of all counts for the day
              - total_weight_kg (float): sum of all weights for the day
              - avg_per_tree (float): mean count per unique tree_id
                  (0.0 when no tree_ids were recorded)
              - trees_visited (int): number of distinct tree_ids

        NOTE: Date filtering uses a timestamp startswith('{date}') check,
        matching the ISO 8601 'Z' timestamp format produced by utc_now()
        (e.g. '2026-07-24T12:34:56Z').
        """
        if date is None:
            date = utc_now()[:10]  # 'YYYY-MM-DD' from the full ISO timestamp

        total_count = 0
        total_weight = 0.0
        trees = set()
        for row in self._entries:
            if row.get("crop") != "avocado":
                continue
            if not row.get("timestamp", "").startswith(date):
                continue
            total_count += row["count"]
            total_weight += row["weight_kg"]
            if row["tree_id"] is not None:
                trees.add(row["tree_id"])

        avg_per_tree = (total_count / len(trees)) if trees else 0.0
        return {
            "total_count": total_count,
            "total_weight_kg": round(total_weight, 4),
            "avg_per_tree": round(avg_per_tree, 4),
            "trees_visited": len(trees),
        }

    # ------------------------------------------------------------------ #
    # Soil-quality assessment
    # ------------------------------------------------------------------ #

    def quality_assessment(self, reading):
        """Assess soil conditions for avocado harvest from a SensorReading.

        Args:
            reading: A SensorReading whose metrics dict may contain
                'soil_moisture_pct' and/or 'soil_pH'.

        Returns:
            One of:
              - 'optimal conditions for harvest'
              - 'soil too dry — irrigate before harvest'
              - 'soil too wet — wait for drainage'
              - 'pH too low for avocado — amend soil'
              - 'pH too high for avocado — amend soil'
              - 'insufficient sensor data'  (neither metric present)

        NOTE: Moisture is checked before pH so the most immediately actionable
        condition (water availability) is reported first when both are out of
        range. Partial data is handled gracefully — if only one metric is
        present, only that metric is assessed; if all present metrics are in
        range, 'optimal' is returned.
        """
        metrics = reading.metrics
        moisture = metrics.get("soil_moisture_pct")
        ph = metrics.get("soil_pH")

        if moisture is None and ph is None:
            return "insufficient sensor data"

        # Moisture checks take priority — water availability is the most
        # immediate harvest-affecting factor.
        if moisture is not None:
            if moisture < _MOISTURE_LOW_PCT:
                return "soil too dry — irrigate before harvest"
            if moisture > _MOISTURE_HIGH_PCT:
                return "soil too wet — wait for drainage"

        # pH checks next.
        if ph is not None:
            if ph < _PH_LOW:
                return "pH too low for avocado — amend soil"
            if ph > _PH_HIGH:
                return "pH too high for avocado — amend soil"

        # Every present metric fell within its optimal band.
        return "optimal conditions for harvest"

    # ------------------------------------------------------------------ #
    # Harvest-window planner (GPS)
    # ------------------------------------------------------------------ #

    def harvest_window(self, gps_positions):
        """Analyse a recent GPS track and suggest the next harvest point.

        Args:
            gps_positions: Recent GPS fixes from the farmer's walk.

        Returns:
            dict with keys:
              - area_km2 (float): bounding-box area in square kilometres
                  (0.0 when fewer than 2 distinct points)
              - points (int): number of GPS positions supplied
              - suggested_next_lat (float): nudge latitude for the next tree
              - suggested_next_lon (float): nudge longitude for the next tree

        NOTE: The area is the axis-aligned bounding box in km². Longitude
        degrees are scaled by cos(latitude) because longitudinal degree
        spacing shrinks toward the poles. The suggested next point is the
        bounding-box centroid plus a small offset (_NEXT_TREE_OFFSET) so the
        farmer moves systematically rather than re-harvesting the centre.

        WHY: Walking an orchard row-by-row without a plan causes missed or
        double-harvested trees. A centroid+offset nudge biases the next stop
        just beyond the already-covered area, encouraging forward progress.
        """
        points = len(gps_positions)

        if points == 0:
            return {
                "area_km2": 0.0,
                "points": 0,
                "suggested_next_lat": 0.0,
                "suggested_next_lon": 0.0,
            }

        lats = [p.lat for p in gps_positions]
        lons = [p.lon for p in gps_positions]
        min_lat, max_lat = min(lats), max(lats)
        min_lon, max_lon = min(lons), max(lons)
        center_lat = (min_lat + max_lat) / 2.0
        center_lon = (min_lon + max_lon) / 2.0

        lat_delta_km = (max_lat - min_lat) * _KM_PER_DEG_LAT
        lon_delta_km = (max_lon - min_lon) * _KM_PER_DEG_LAT * math.cos(
            math.radians(center_lat)
        )
        area_km2 = lat_delta_km * lon_delta_km

        return {
            "area_km2": round(area_km2, 6),
            "points": points,
            "suggested_next_lat": round(center_lat + _NEXT_TREE_OFFSET, 6),
            "suggested_next_lon": round(center_lon + _NEXT_TREE_OFFSET, 6),
        }

    # ------------------------------------------------------------------ #
    # Cleanup
    # ------------------------------------------------------------------ #

    def close(self):
        """Flush and close the JSON store.

        Safe to call multiple times — subsequent calls are a no-op once the
        store is already closed. A final _save() ensures any buffered entries
        are persisted before teardown.
        """
        with self._lock:
            self._save()
            self._db_path = None