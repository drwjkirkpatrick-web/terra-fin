"""Tests for the orange / citrus harvest tracking module.

NOTE: These tests run entirely against SQLite (:memory:) and synthetic
SensorReading objects — no hardware or filesystem is required. They cover
harvest logging, the daily summary (populated and empty), the citrus-specific
soil quality assessment across several soil conditions, the approximate Brix
estimate (with and without required metrics), GPS harvest-window math, SQLite
persistence across instances, and cleanup.

WHY: Citrus thresholds differ from avocado, so the assessment logic and Brix
formula need their own coverage to guard against regressions when the shared
harvest interface is refactored.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.types import HarvestEntry, SensorReading, GPSPosition, utc_now
from modules.orange import OrangeHarvest


def _reading(metrics: dict, sensor_name: str = "soil_combo") -> SensorReading:
    """Build a synthetic SensorReading with the given metrics."""
    return SensorReading(
        sensor_name=sensor_name,
        timestamp=utc_now(),
        metrics=metrics,
        units={},
    )


class TestLogHarvest:
    def test_log_harvest_returns_entry(self):
        """log_harvest must return a HarvestEntry with crop='orange'."""
        h = OrangeHarvest()
        entry = h.log_harvest(count=12, weight_kg=3.4, location="grove-A")
        assert isinstance(entry, HarvestEntry)
        assert entry.crop == "orange"
        assert entry.count == 12
        assert entry.weight_kg == 3.4
        assert entry.location == "grove-A"
        assert entry.notes == ""
        assert entry.tree_id is None
        assert entry.timestamp  # non-empty ISO string
        h.close()

    def test_log_harvest_with_tree_id_and_notes(self):
        """Optional tree_id and notes round-trip into the returned entry."""
        h = OrangeHarvest()
        entry = h.log_harvest(
            count=5, weight_kg=1.2, location="grove-B",
            tree_id="T-42", notes="grade-A",
        )
        assert entry.tree_id == "T-42"
        assert entry.notes == "grade-A"
        h.close()


class TestDailySummary:
    def test_daily_summary_with_entries(self):
        """Summary aggregates count, weight, distinct trees, and avg/tree."""
        h = OrangeHarvest()
        # Three entries across two trees on the same day.
        h.log_harvest(count=10, weight_kg=2.0, location="g1", tree_id="T1")
        h.log_harvest(count=8, weight_kg=1.6, location="g1", tree_id="T1")
        h.log_harvest(count=6, weight_kg=1.0, location="g1", tree_id="T2")

        summary = h.daily_summary()
        assert summary["total_count"] == 24
        assert abs(summary["total_weight_kg"] - 4.6) < 1e-6
        assert summary["trees_visited"] == 2
        assert abs(summary["avg_per_tree"] - 12.0) < 1e-6
        assert summary["date"] == utc_now()[:10]
        h.close()

    def test_daily_summary_empty(self):
        """An empty day yields zeros and no division error."""
        h = OrangeHarvest()
        summary = h.daily_summary(date="2026-01-01")
        assert summary["total_count"] == 0
        assert summary["total_weight_kg"] == 0.0
        assert summary["trees_visited"] == 0
        assert summary["avg_per_tree"] == 0.0
        h.close()


class TestQualityAssessment:
    def test_optimal_conditions(self):
        """Moisture 40-70 % and pH 5.5-6.5 -> optimal."""
        h = OrangeHarvest()
        r = _reading({"soil_moisture_pct": 55.0, "soil_pH": 6.0})
        assert h.quality_assessment(r) == "optimal conditions for citrus harvest"
        h.close()

    def test_moisture_too_low(self):
        h = OrangeHarvest()
        r = _reading({"soil_moisture_pct": 30.0, "soil_pH": 6.0})
        assert h.quality_assessment(r) == "moisture too low for citrus"
        h.close()

    def test_moisture_too_high(self):
        h = OrangeHarvest()
        r = _reading({"soil_moisture_pct": 80.0, "soil_pH": 6.0})
        assert h.quality_assessment(r) == "moisture too high for citrus"
        h.close()

    def test_ph_out_of_range(self):
        """Moisture OK but pH outside 5.5-6.5 -> pH message."""
        h = OrangeHarvest()
        r_low = _reading({"soil_moisture_pct": 55.0, "soil_pH": 4.5})
        assert h.quality_assessment(r_low) == "pH outside citrus range (5.5-6.5)"
        r_high = _reading({"soil_moisture_pct": 55.0, "soil_pH": 7.5})
        assert h.quality_assessment(r_high) == "pH outside citrus range (5.5-6.5)"
        h.close()

    def test_insufficient_sensor_data(self):
        """Missing moisture or pH -> insufficient data."""
        h = OrangeHarvest()
        assert h.quality_assessment(_reading({"soil_pH": 6.0})) == \
            "insufficient sensor data"
        assert h.quality_assessment(_reading({"soil_moisture_pct": 50.0})) == \
            "insufficient sensor data"
        assert h.quality_assessment(_reading({})) == "insufficient sensor data"
        h.close()


class TestBrixEstimate:
    def test_brix_with_temp_and_moisture(self):
        """Brix is computed from temp_c and soil_moisture_pct."""
        h = OrangeHarvest()
        # temp_c=25, moisture=50 -> 12.0 + (25-20)*0.2 - (100-50)*0.01
        #                       = 12.0 + 1.0 - 0.5 = 12.5
        r = _reading({"temp_c": 25.0, "soil_moisture_pct": 50.0})
        brix = h.brix_estimate(r)
        assert brix is not None
        assert abs(brix - 12.5) < 1e-6
        h.close()

    def test_brix_missing_data_returns_none(self):
        """Missing temp or moisture -> None."""
        h = OrangeHarvest()
        assert h.brix_estimate(_reading({"soil_moisture_pct": 50.0})) is None
        assert h.brix_estimate(_reading({"temp_c": 25.0})) is None
        assert h.brix_estimate(_reading({})) is None
        h.close()


class TestHarvestWindow:
    def test_harvest_window_bbox(self):
        """GPS fixes produce a bounding box and span."""
        h = OrangeHarvest()
        positions = [
            GPSPosition(lat=-1.0, lon=36.0),
            GPSPosition(lat=-1.5, lon=36.5),
            GPSPosition(lat=-1.2, lon=36.2),
        ]
        w = h.harvest_window(positions)
        assert w["stops"] == 3
        assert w["bbox"]["min_lat"] == -1.5
        assert w["bbox"]["max_lat"] == -1.0
        assert w["bbox"]["min_lon"] == 36.0
        assert w["bbox"]["max_lon"] == 36.5
        assert abs(w["lat_span"] - 0.5) < 1e-6
        assert abs(w["lon_span"] - 0.5) < 1e-6
        h.close()

    def test_harvest_window_empty(self):
        """No fixes -> bbox None, zero spans."""
        h = OrangeHarvest()
        w = h.harvest_window([])
        assert w["stops"] == 0
        assert w["bbox"] is None
        assert w["lat_span"] == 0.0
        assert w["lon_span"] == 0.0
        h.close()


class TestPersistence:
    def test_sqlite_persistence_across_instances(self):
        """Data written by one instance is visible to a later one on disk."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "orange.db")
            h1 = OrangeHarvest(db_path=db)
            h1.log_harvest(count=20, weight_kg=5.0, location="grove-P", tree_id="X")
            h1.close()

            h2 = OrangeHarvest(db_path=db)
            summary = h2.daily_summary()
            assert summary["total_count"] == 20
            assert abs(summary["total_weight_kg"] - 5.0) < 1e-6
            assert summary["trees_visited"] == 1
            h2.close()


class TestClose:
    def test_close_is_idempotent(self):
        """Calling close() multiple times must not raise."""
        h = OrangeHarvest()
        h.close()
        h.close()  # second close is a no-op

    def test_close_then_log_reopens(self):
        """After close, a log_harvest re-initializes the DB via _ensure_connected."""
        h = OrangeHarvest()
        h.close()
        entry = h.log_harvest(count=1, weight_kg=0.2, location="g")
        assert entry.count == 1
        h.close()