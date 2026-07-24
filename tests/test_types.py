"""Tests for core types."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.types import (
    SensorReading, GPSPosition, HarvestEntry, NightEvent,
    DeviceMode, utc_now, parse_iso,
)


class TestDeviceMode:
    def test_values(self):
        assert DeviceMode.DAY.value == "day"
        assert DeviceMode.NIGHT.value == "night"
        assert DeviceMode.STANDBY.value == "standby"

    def test_from_value(self):
        assert DeviceMode("day") is DeviceMode.DAY
        assert DeviceMode("night") is DeviceMode.NIGHT


class TestSensorReading:
    def test_create(self):
        r = SensorReading(
            sensor_name="test",
            timestamp="2026-01-01T00:00:00Z",
            metrics={"temp": 25.0},
            units={"temp": "celsius"},
        )
        assert r.sensor_name == "test"
        assert r.metrics["temp"] == 25.0

    def test_to_dict(self):
        r = SensorReading("s", "ts", {"m": 1.0}, {"m": "unit"})
        d = r.to_dict()
        assert d["sensor_name"] == "s"
        assert d["metrics"]["m"] == 1.0

    def test_from_dict(self):
        d = {"sensor_name": "s", "timestamp": "ts", "metrics": {"m": 1.0},
             "units": {"m": "u"}, "metadata": {"k": "v"}}
        r = SensorReading.from_dict(d)
        assert r.sensor_name == "s"
        assert r.metrics["m"] == 1.0
        assert r.metadata["k"] == "v"

    def test_from_dict_ignores_extra(self):
        d = {"sensor_name": "s", "timestamp": "ts", "metrics": {},
             "units": {}, "extra_field": True}
        r = SensorReading.from_dict(d)
        assert r.sensor_name == "s"
        assert not hasattr(r, "extra_field")

    def test_default_metadata(self):
        r = SensorReading("s", "ts", {}, {})
        assert r.metadata == {}


class TestGPSPosition:
    def test_create(self):
        g = GPSPosition(lat=-1.0, lon=36.0)
        assert g.lat == -1.0
        assert g.lon == 36.0
        assert g.altitude_m is None
        assert g.fix_quality == "unknown"

    def test_round_trip(self):
        g = GPSPosition(lat=-1.5, lon=36.8, altitude_m=1800.0,
                        timestamp="2026-01-01T00:00:00Z", fix_quality="gps")
        d = g.to_dict()
        g2 = GPSPosition.from_dict(d)
        assert g2.lat == -1.5
        assert g2.lon == 36.8
        assert g2.altitude_m == 1800.0
        assert g2.fix_quality == "gps"


class TestHarvestEntry:
    def test_create(self):
        e = HarvestEntry(
            crop="avocado", timestamp="2026-01-01T00:00:00Z",
            count=10, weight_kg=2.5, location="tree-01",
        )
        assert e.crop == "avocado"
        assert e.count == 10
        assert e.weight_kg == 2.5
        assert e.notes == ""
        assert e.tree_id is None

    def test_round_trip(self):
        e = HarvestEntry(
            crop="orange", timestamp="2026-01-01T00:00:00Z",
            count=50, weight_kg=15.0, location="grove-2",
            notes="sweet", tree_id="T-42",
        )
        d = e.to_dict()
        e2 = HarvestEntry.from_dict(d)
        assert e2.crop == "orange"
        assert e2.tree_id == "T-42"
        assert e2.notes == "sweet"


class TestNightEvent:
    def test_create(self):
        ev = NightEvent(
            event_type="motion", timestamp="2026-01-01T00:00:00Z",
            description="Movement detected",
        )
        assert ev.event_type == "motion"
        assert ev.severity == "info"
        assert ev.location is None

    def test_with_location(self):
        loc = GPSPosition(lat=-1.0, lon=36.0)
        ev = NightEvent(
            event_type="motion", timestamp="2026-01-01T00:00:00Z",
            description="Movement", location=loc, severity="warning",
        )
        d = ev.to_dict()
        assert d["location"]["lat"] == -1.0
        ev2 = NightEvent.from_dict(d)
        assert ev2.location is not None
        assert ev2.location.lat == -1.0
        assert ev2.severity == "warning"


class TestHelpers:
    def test_utc_now(self):
        ts = utc_now()
        assert "T" in ts
        assert ts.endswith("Z")

    def test_parse_iso(self):
        dt = parse_iso("2026-07-24T12:00:00Z")
        assert dt.year == 2026
        assert dt.month == 7
        assert dt.day == 24