"""Tests for the GPS sensor driver.

NOTE: All tests run against the mock path — no serial hardware or
pyserial/pynmea2 needed. They verify the SensorBase contract shape, the
random-walk movement, metadata contents, and the convenience API.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.config import GPSConfig
from core.types import GPSPosition, SensorReading
from sensors.gps import GPSSensor


class TestGPSSensor:
    def setup_method(self):
        """Fresh sensor in mock mode for every test."""
        cfg = GPSConfig(mock_mode=True)
        self.sensor = GPSSensor(config=cfg)
        assert self.sensor.initialize() is True

    # -- class attributes / shape --------------------------------------

    def test_class_attributes(self):
        assert GPSSensor.name == "gps"
        assert GPSSensor.bus_type == "serial"
        assert GPSSensor.metrics == ["lat", "lon", "altitude_m"]
        assert "GPS" in GPSSensor.description or "location" in GPSSensor.description

    def test_health_check_shape(self):
        hc = self.sensor.health_check()
        assert hc["name"] == "gps"
        assert hc["bus_type"] == "serial"
        assert hc["metrics"] == ["lat", "lon", "altitude_m"]
        assert hc["mock_mode"] is True

    # -- mock read -----------------------------------------------------

    def test_mock_read_returns_reading(self):
        r = self.sensor.read()
        assert r is not None
        assert isinstance(r, SensorReading)
        assert r.sensor_name == "gps"
        assert "lat" in r.metrics
        assert "lon" in r.metrics
        assert "altitude_m" in r.metrics

    def test_mock_read_has_gps_position_in_metadata(self):
        r = self.sensor.read()
        assert r is not None
        pos = r.metadata.get("position")
        assert isinstance(pos, GPSPosition)
        assert pos.lat != 0.0
        assert pos.lon != 0.0

    def test_mock_read_fix_quality_simulated(self):
        r = self.sensor.read()
        assert r is not None
        assert r.metadata.get("fix_quality") == "simulated"
        pos = r.metadata["position"]
        assert pos.fix_quality == "simulated"

    def test_mock_read_near_base_coords(self):
        """First fix should be near the Nairobi base coordinates."""
        r = self.sensor.read()
        assert r is not None
        pos = r.metadata["position"]
        assert abs(pos.lat - (-1.2864)) < 1.0
        assert abs(pos.lon - 36.8222) < 1.0

    # -- walk movement -------------------------------------------------

    def test_walk_pattern_moves(self):
        """Two reads should produce different lat/lon (random walk)."""
        r1 = self.sensor.read()
        r2 = self.sensor.read()
        assert r1 is not None and r2 is not None
        p1 = r1.metadata["position"]
        p2 = r2.metadata["position"]
        moved = (p1.lat != p2.lat) or (p1.lon != p2.lon)
        assert moved, "random walk should change lat or lon between reads"

    def test_read_twice_both_valid(self):
        r1 = self.sensor.read()
        r2 = self.sensor.read()
        assert r1 is not None
        assert r2 is not None
        assert r1.sensor_name == "gps"
        assert r2.sensor_name == "gps"

    # -- get_position convenience --------------------------------------

    def test_get_position_returns_gpsposition(self):
        pos = self.sensor.get_position()
        assert pos is not None
        assert isinstance(pos, GPSPosition)
        assert pos.fix_quality == "simulated"

    def test_get_position_after_health(self):
        self.sensor.get_position()
        assert self.sensor.is_healthy is True

    # -- cleanup -------------------------------------------------------

    def test_cleanup_no_serial(self):
        """cleanup() should not raise even with no serial port open."""
        self.sensor.cleanup()  # no exception
        # idempotent
        self.sensor.cleanup()

    def test_is_healthy_before_read_is_false(self):
        """A fresh sensor (before any read) is not healthy."""
        fresh = GPSSensor(config=GPSConfig(mock_mode=True))
        fresh.initialize()
        assert fresh.is_healthy is False