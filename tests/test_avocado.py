"""Tests for the avocado harvest tracking module.

NOTE: These tests exercise the AvocadoHarvest class with an in-memory SQLite
database — no hardware, no file I/O, no network. They cover log_harvest
round-trip, daily_summary (with and without entries), every branch of
quality_assessment, the GPS harvest_window planner, SQLite file persistence
across instances, and close() idempotency. Uses sys.path.insert(0, 'src')
to import the core.types and modules.avocado packages exactly as
pyproject.toml's pythonpath setting would.

WHY: The harvest tracker underpins the farmer's daily yield accounting and the
go/no-go harvest decision, so each behaviour — including empty-data and
partial-metric edge cases — must be pinned. The persistence round-trip guards
against the easy mistake of logging to a DB that can't later be queried back.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.types import HarvestEntry, SensorReading, GPSPosition
from modules.avocado import AvocadoHarvest


def _reading(moisture=None, ph=None):
    """Build a SensorReading with only the requested soil metrics present.

    NOTE: Omitted metrics are left out of the dict entirely (not set to None)
    so quality_assessment() sees genuinely missing keys — the partial-data
    path this module must handle gracefully.
    """
    metrics = {}
    units = {}
    if moisture is not None:
        metrics["soil_moisture_pct"] = moisture
        units["soil_moisture_pct"] = "%"
    if ph is not None:
        metrics["soil_pH"] = ph
        units["soil_pH"] = ""
    return SensorReading(
        sensor_name="soil",
        timestamp="2026-07-24T08:00:00Z",
        metrics=metrics,
        units=units,
    )


class TestAvocadoHarvest:
    # -- log_harvest ---------------------------------------------------

    def test_log_harvest_returns_entry(self):
        """log_harvest should return a populated HarvestEntry."""
        h = AvocadoHarvest()
        entry = h.log_harvest(
            count=12, weight_kg=3.5, location="Block A", tree_id="T1",
        )
        assert isinstance(entry, HarvestEntry)
        assert entry.crop == "avocado"
        assert entry.count == 12
        assert entry.weight_kg == 3.5
        assert entry.location == "Block A"
        assert entry.tree_id == "T1"
        assert entry.timestamp  # non-empty ISO string
        h.close()

    def test_log_harvest_defaults(self):
        """tree_id and notes should default sensibly."""
        h = AvocadoHarvest()
        entry = h.log_harvest(count=5, weight_kg=1.0, location="Block B")
        assert entry.tree_id is None
        assert entry.notes == ""
        h.close()

    # -- daily_summary -------------------------------------------------

    def test_daily_summary_with_entries(self):
        """daily_summary should aggregate count, weight, and unique trees."""
        h = AvocadoHarvest()
        # Force a known date so the LIKE filter matches.
        today = "2026-07-24"
        for e in [
            HarvestEntry("avocado", f"{today}T08:00:00Z", 10, 2.0, "A", "", "T1"),
            HarvestEntry("avocado", f"{today}T09:00:00Z", 20, 4.0, "A", "", "T2"),
            HarvestEntry("avocado", f"{today}T10:00:00Z",  5, 1.0, "A", "", "T1"),
        ]:
            h._conn.execute(
                "INSERT INTO harvest_entries "
                "(crop, timestamp, count, weight_kg, location, notes, tree_id) "
                "VALUES (?,?,?,?,?,?,?)",
                (e.crop, e.timestamp, e.count, e.weight_kg, e.location,
                 e.notes, e.tree_id),
            )
        h._conn.commit()
        s = h.daily_summary(date=today)
        assert s["total_count"] == 35
        assert s["total_weight_kg"] == 7.0
        assert s["trees_visited"] == 2  # T1 and T2
        # avg per tree = 35 / 2 = 17.5
        assert s["avg_per_tree"] == 17.5
        h.close()

    def test_daily_summary_empty(self):
        """daily_summary on a day with no entries should return zeros."""
        h = AvocadoHarvest()
        s = h.daily_summary(date="1999-01-01")
        assert s["total_count"] == 0
        assert s["total_weight_kg"] == 0.0
        assert s["avg_per_tree"] == 0.0
        assert s["trees_visited"] == 0
        h.close()

    # -- quality_assessment (all branches) -----------------------------

    def test_quality_optimal(self):
        """In-range moisture and pH → optimal."""
        h = AvocadoHarvest()
        r = _reading(moisture=50.0, ph=6.0)
        assert h.quality_assessment(r) == "optimal conditions for harvest"
        h.close()

    def test_quality_too_dry(self):
        """Moisture < 30 → irrigate."""
        h = AvocadoHarvest()
        r = _reading(moisture=20.0, ph=6.0)
        assert h.quality_assessment(r) == "soil too dry — irrigate before harvest"
        h.close()

    def test_quality_too_wet(self):
        """Moisture > 70 → wait for drainage."""
        h = AvocadoHarvest()
        r = _reading(moisture=85.0, ph=6.0)
        assert h.quality_assessment(r) == "soil too wet — wait for drainage"
        h.close()

    def test_quality_ph_too_low(self):
        """pH < 5.5 with OK moisture → amend acidic soil."""
        h = AvocadoHarvest()
        r = _reading(moisture=50.0, ph=5.0)
        assert h.quality_assessment(r) == "pH too low for avocado — amend soil"
        h.close()

    def test_quality_ph_too_high(self):
        """pH > 7.0 with OK moisture → amend alkaline soil."""
        h = AvocadoHarvest()
        r = _reading(moisture=50.0, ph=7.5)
        assert h.quality_assessment(r) == "pH too high for avocado — amend soil"
        h.close()

    def test_quality_missing_metrics(self):
        """Neither metric present → insufficient data."""
        h = AvocadoHarvest()
        r = _reading()
        assert h.quality_assessment(r) == "insufficient sensor data"
        h.close()

    # -- harvest_window (GPS) ------------------------------------------

    def test_harvest_window(self):
        """harvest_window should report area, point count, and a next-tree nudge."""
        h = AvocadoHarvest()
        pts = [
            GPSPosition(lat=-1.290, lon=36.820, timestamp="t1"),
            GPSPosition(lat=-1.280, lon=36.830, timestamp="t2"),
            GPSPosition(lat=-1.285, lon=36.825, timestamp="t3"),
        ]
        res = h.harvest_window(pts)
        assert res["points"] == 3
        assert res["area_km2"] > 0.0
        # Centroid of bounding box = (-1.285, 36.825); +0.001 offset.
        assert res["suggested_next_lat"] == round(-1.285 + 0.001, 6)
        assert res["suggested_next_lon"] == round(36.825 + 0.001, 6)
        h.close()

    # -- SQLite persistence round-trip ---------------------------------

    def test_persistence_round_trip(self):
        """Entries logged to a file DB should survive a new AvocadoHarvest instance."""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            h1 = AvocadoHarvest(db_path=path)
            e = h1.log_harvest(count=8, weight_kg=2.0, location="Block C", tree_id="T9")
            h1.close()
            # Reopen the same file and query today's summary.
            h2 = AvocadoHarvest(db_path=path)
            day = e.timestamp[:10]
            s = h2.daily_summary(date=day)
            assert s["total_count"] == 8
            assert s["total_weight_kg"] == 2.0
            assert s["trees_visited"] == 1
            h2.close()
        finally:
            os.remove(path)

    # -- close ---------------------------------------------------------

    def test_close_idempotent(self):
        """close() should be safe to call more than once."""
        h = AvocadoHarvest()
        h.log_harvest(count=1, weight_kg=0.3, location="X")
        h.close()
        h.close()  # must not raise