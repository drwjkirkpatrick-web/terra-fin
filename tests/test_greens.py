"""Tests for the local greens harvest tracking module.

NOTE: Tests cover all crop types (kale, spinach, managu), daily summaries with
breakdown, quality assessment, leaf condition, SQLite persistence, and close.

WHY: Greens are cut-and-come-again crops — verifying per-variety yield
breakdown and soil-condition assessment is essential for smallholder planning.
"""

import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.types import HarvestEntry, SensorReading, GPSPosition, utc_now
from modules.greens import GreensHarvest


class TestLogHarvest:
    def test_log_kale_harvest(self):
        gh = GreensHarvest()
        entry = gh.log_harvest(count=20, weight_kg=1.5, location="plot-A",
                               crop_type="kale")
        assert entry.crop == "kale"
        assert entry.count == 20
        assert entry.weight_kg == 1.5
        assert entry.location == "plot-A"
        gh.close()

    def test_log_spinach_harvest(self):
        gh = GreensHarvest()
        entry = gh.log_harvest(count=15, weight_kg=0.8, location="plot-B",
                               crop_type="spinach", notes="second cut")
        assert entry.crop == "spinach"
        assert entry.notes == "second cut"
        gh.close()

    def test_log_managu_harvest(self):
        gh = GreensHarvest()
        entry = gh.log_harvest(count=10, weight_kg=0.5, location="plot-C",
                               crop_type="managu", tree_id="bed-3")
        assert entry.crop == "managu"
        assert entry.tree_id == "bed-3"
        gh.close()

    def test_log_harvest_returns_harvest_entry(self):
        gh = GreensHarvest()
        entry = gh.log_harvest(count=5, weight_kg=0.3, location="plot-D")
        assert isinstance(entry, HarvestEntry)
        assert entry.crop == "kale"  # default crop_type
        gh.close()


class TestDailySummary:
    def test_daily_summary_with_breakdown(self):
        gh = GreensHarvest()
        date = "2026-07-24"
        # Log multiple crop types on the same date.
        gh.log_harvest(count=20, weight_kg=1.5, location="plot-A",
                       crop_type="kale")
        # Override timestamps by inserting directly to simulate same date.
        conn = gh._ensure_connected()
        conn.execute(
            "UPDATE harvest_entries SET timestamp = ? WHERE crop_type = 'kale'",
            (f"{date}T08:00:00Z",),
        )
        gh.log_harvest(count=15, weight_kg=0.8, location="plot-B",
                       crop_type="spinach")
        conn.execute(
            "UPDATE harvest_entries SET timestamp = ? WHERE crop_type = 'spinach'",
            (f"{date}T09:00:00Z",),
        )
        gh.log_harvest(count=10, weight_kg=0.5, location="plot-C",
                       crop_type="managu")
        conn.execute(
            "UPDATE harvest_entries SET timestamp = ? WHERE crop_type = 'managu'",
            (f"{date}T10:00:00Z",),
        )
        conn.commit()

        summary = gh.daily_summary(date=date)
        assert summary["total_count"] == 45
        assert abs(summary["total_weight_kg"] - 2.8) < 0.01
        assert "kale" in summary["breakdown"]
        assert "spinach" in summary["breakdown"]
        assert "managu" in summary["breakdown"]
        assert summary["breakdown"]["kale"]["count"] == 20
        assert summary["breakdown"]["spinach"]["count"] == 15
        assert summary["breakdown"]["managu"]["count"] == 10
        gh.close()

    def test_daily_summary_empty(self):
        gh = GreensHarvest()
        summary = gh.daily_summary(date="2026-07-24")
        assert summary["total_count"] == 0
        assert summary["total_weight_kg"] == 0.0
        assert summary["breakdown"] == {}
        gh.close()


class TestQualityAssessment:
    def test_optimal_conditions(self):
        gh = GreensHarvest()
        reading = SensorReading(
            sensor_name="soil", timestamp=utc_now(),
            metrics={"soil_moisture_pct": 65.0, "soil_ph": 6.5},
            units={"soil_moisture_pct": "percent", "soil_ph": "pH"},
        )
        assert gh.quality_assessment(reading) == "optimal conditions for greens"
        gh.close()

    def test_soil_too_dry(self):
        gh = GreensHarvest()
        reading = SensorReading(
            sensor_name="soil", timestamp=utc_now(),
            metrics={"soil_moisture_pct": 30.0, "soil_ph": 6.5},
            units={},
        )
        assert gh.quality_assessment(reading) == "soil too dry for greens"
        gh.close()

    def test_soil_too_wet(self):
        gh = GreensHarvest()
        reading = SensorReading(
            sensor_name="soil", timestamp=utc_now(),
            metrics={"soil_moisture_pct": 90.0, "soil_ph": 6.5},
            units={},
        )
        assert gh.quality_assessment(reading) == "soil too wet for greens"
        gh.close()

    def test_ph_out_of_range(self):
        gh = GreensHarvest()
        reading = SensorReading(
            sensor_name="soil", timestamp=utc_now(),
            metrics={"soil_moisture_pct": 65.0, "soil_ph": 5.5},
            units={},
        )
        assert gh.quality_assessment(reading) == "pH outside greens range (6.0-7.0)"
        gh.close()

    def test_insufficient_data(self):
        gh = GreensHarvest()
        reading = SensorReading(
            sensor_name="soil", timestamp=utc_now(),
            metrics={"soil_moisture_pct": 65.0},
            units={},
        )
        assert gh.quality_assessment(reading) == "insufficient sensor data"
        gh.close()


class TestLeafCondition:
    def test_good(self):
        gh = GreensHarvest()
        assert gh.leaf_condition(temp_c=20, humidity_pct=60) == "good"
        gh.close()

    def test_wilt_risk_hot(self):
        gh = GreensHarvest()
        assert gh.leaf_condition(temp_c=30, humidity_pct=60) == "wilt_risk"
        gh.close()

    def test_wilt_risk_dry(self):
        gh = GreensHarvest()
        assert gh.leaf_condition(temp_c=20, humidity_pct=20) == "wilt_risk"
        gh.close()

    def test_frost_risk(self):
        gh = GreensHarvest()
        assert gh.leaf_condition(temp_c=2, humidity_pct=60) == "frost_risk"
        gh.close()

    def test_fair(self):
        gh = GreensHarvest()
        # Temp in range but humidity below good threshold (but above wilt)
        assert gh.leaf_condition(temp_c=20, humidity_pct=40) == "fair"
        gh.close()


class TestPersistenceAndClose:
    def test_sqlite_persistence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "greens.db")
            gh = GreensHarvest(db_path)
            gh.log_harvest(count=12, weight_kg=1.0, location="plot-X",
                           crop_type="kale")
            gh.close()
            # Reopen and verify persistence.
            gh2 = GreensHarvest(db_path)
            rows = gh2._ensure_connected().execute(
                "SELECT * FROM harvest_entries"
            ).fetchall()
            assert len(rows) == 1
            assert rows[0]["crop_type"] == "kale"
            assert rows[0]["count"] == 12
            gh2.close()

    def test_close_sets_conn_none(self):
        gh = GreensHarvest()
        gh.close()
        assert gh._conn is None

    def test_close_idempotent(self):
        gh = GreensHarvest()
        gh.close()
        gh.close()  # should not raise