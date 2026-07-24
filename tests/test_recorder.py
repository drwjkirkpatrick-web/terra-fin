"""Tests for the SQLite recorder."""

import sys
import os
import threading
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.recorder import Recorder
from core.types import SensorReading, HarvestEntry, NightEvent, GPSPosition, utc_now


class TestRecorderInit:
    def test_init_memory(self):
        r = Recorder(":memory:")
        r.init_db()
        assert r._conn is not None
        r.close()

    def test_init_file(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        r = Recorder(db_path)
        r.init_db()
        assert os.path.exists(db_path)
        r.close()

    def test_init_creates_dir(self, tmp_path):
        db_path = str(tmp_path / "subdir" / "test.db")
        r = Recorder(db_path)
        r.init_db()
        assert os.path.exists(db_path)
        r.close()


class TestRecordReading:
    def test_record_and_query(self):
        r = Recorder(":memory:")
        r.init_db()
        reading = SensorReading(
            sensor_name="soil_moisture",
            timestamp=utc_now(),
            metrics={"soil_moisture_pct": 45.0},
            units={"soil_moisture_pct": "percent"},
            metadata={"source": "mock"},
        )
        row_id = r.record_reading(reading)
        assert row_id > 0
        results = r.query_readings(sensor_name="soil_moisture")
        assert len(results) == 1
        assert results[0]["metrics"]["soil_moisture_pct"] == 45.0
        r.close()

    def test_query_by_sensor_name(self):
        r = Recorder(":memory:")
        r.init_db()
        for name in ["soil_moisture", "temp_humidity", "soil_moisture"]:
            r.record_reading(SensorReading(
                sensor_name=name, timestamp=utc_now(),
                metrics={"v": 1.0}, units={"v": "u"},
            ))
        sm = r.query_readings(sensor_name="soil_moisture")
        assert len(sm) == 2
        r.close()

    def test_query_by_time(self):
        r = Recorder(":memory:")
        r.init_db()
        r.record_reading(SensorReading(
            sensor_name="s", timestamp="2026-01-01T10:00:00Z",
            metrics={"v": 1.0}, units={},
        ))
        r.record_reading(SensorReading(
            sensor_name="s", timestamp="2026-01-02T10:00:00Z",
            metrics={"v": 2.0}, units={},
        ))
        after = r.query_readings(start_time="2026-01-01T12:00:00Z")
        assert len(after) == 1
        assert after[0]["metrics"]["v"] == 2.0
        r.close()


class TestRecordHarvest:
    def test_record_and_query(self):
        r = Recorder(":memory:")
        r.init_db()
        entry = HarvestEntry(
            crop="avocado", timestamp=utc_now(),
            count=10, weight_kg=2.5, location="tree-01",
        )
        row_id = r.record_harvest(entry)
        assert row_id > 0
        results = r.query_harvests(crop="avocado")
        assert len(results) == 1
        assert results[0]["count"] == 10
        r.close()

    def test_query_by_date(self):
        r = Recorder(":memory:")
        r.init_db()
        r.record_harvest(HarvestEntry(
            crop="orange", timestamp="2026-07-24T10:00:00Z",
            count=5, weight_kg=1.0, location="grove-1",
        ))
        r.record_harvest(HarvestEntry(
            crop="orange", timestamp="2026-07-25T10:00:00Z",
            count=8, weight_kg=2.0, location="grove-2",
        ))
        day1 = r.query_harvests(crop="orange", date="2026-07-24")
        assert len(day1) == 1
        assert day1[0]["count"] == 5
        r.close()


class TestRecordNightEvent:
    def test_record_and_query(self):
        r = Recorder(":memory:")
        r.init_db()
        ev = NightEvent(
            event_type="motion", timestamp=utc_now(),
            description="Movement detected",
        )
        row_id = r.record_night_event(ev)
        assert row_id > 0
        results = r.query_night_events()
        assert len(results) == 1
        assert results[0]["event_type"] == "motion"
        r.close()

    def test_record_with_location(self):
        r = Recorder(":memory:")
        r.init_db()
        loc = GPSPosition(lat=-1.0, lon=36.0)
        ev = NightEvent(
            event_type="motion", timestamp=utc_now(),
            description="Movement", location=loc, severity="warning",
        )
        r.record_night_event(ev)
        results = r.query_night_events()
        assert len(results) == 1
        assert results[0]["location_json"] is not None
        r.close()


class TestRecordGPS:
    def test_record_and_query(self):
        r = Recorder(":memory:")
        r.init_db()
        pos = GPSPosition(lat=-1.2864, lon=36.8222, altitude_m=1795.0,
                        timestamp=utc_now(), fix_quality="gps")
        row_id = r.record_gps(pos)
        assert row_id > 0
        results = r.query_gps_track()
        assert len(results) == 1
        assert abs(results[0]["lat"] - (-1.2864)) < 0.001
        r.close()


class TestThreadSafety:
    def test_concurrent_writes(self):
        r = Recorder(":memory:")
        r.init_db()
        errors = []

        def writer():
            try:
                for i in range(50):
                    r.record_reading(SensorReading(
                        sensor_name="s", timestamp=utc_now(),
                        metrics={"v": float(i)}, units={},
                    ))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        all_readings = r.query_readings()
        assert len(all_readings) == 200
        r.close()


class TestParameterizedQueries:
    def test_no_sql_injection(self):
        r = Recorder(":memory:")
        r.init_db()
        # Attempt injection via sensor_name — should be safe with parameterized queries
        r.record_reading(SensorReading(
            sensor_name="normal", timestamp=utc_now(),
            metrics={"v": 1.0}, units={},
        ))
        results = r.query_readings(sensor_name="'; DROP TABLE sensor_readings; --")
        assert len(results) == 0
        # Table should still exist
        all_results = r.query_readings()
        assert len(all_results) == 1
        r.close()