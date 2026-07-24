"""Tests for the soil pH sensor driver.

NOTE: These tests exercise the mock path only — no hardware is required.
They cover reading, classification thresholds, health checks, cleanup and
repeated reads. Uses sys.path.insert(0, 'src') to import the core package
exactly as pyproject.toml's pythonpath setting would.

WHY: The pH driver's classify() thresholds drive agronomic advice, so they
must be pinned and tested at the boundaries. Clamping must also be verified
so the mock never reports values outside the configured band.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.config import pHConfig
from sensors.soil_ph import SoilPHSensor


class TestSoilPHSensor:
    def test_mock_read_returns_reading(self):
        """A mock-mode read should return a SensorReading with soil_pH."""
        s = SoilPHSensor(mock_mode=True)
        assert s.initialize() is True
        r = s.read()
        assert r is not None
        assert r.sensor_name == "soil_ph"
        assert "soil_pH" in r.metrics
        assert r.units["soil_pH"] == "pH"
        assert r.metadata["source"] == "mock"

    def test_mock_value_within_configured_band(self):
        """Mock pH must always be clamped to [min_pH, max_pH]."""
        cfg = pHConfig(min_pH=3.0, max_pH=10.0)
        s = SoilPHSensor(config=cfg, mock_mode=True)
        s.initialize()
        for _ in range(20):
            r = s.read()
            assert r is not None
            assert cfg.min_pH <= r.metrics["soil_pH"] <= cfg.max_pH

    def test_classify_acidic(self):
        """pH < 5.5 is acidic."""
        assert SoilPHSensor.classify(4.5) == "acidic"
        assert SoilPHSensor.classify(5.49) == "acidic"

    def test_classify_optimal(self):
        """5.5 ≤ pH ≤ 7.5 is optimal (boundaries inclusive)."""
        assert SoilPHSensor.classify(5.5) == "optimal"
        assert SoilPHSensor.classify(6.5) == "optimal"
        assert SoilPHSensor.classify(7.5) == "optimal"

    def test_classify_alkaline(self):
        """pH > 7.5 is alkaline."""
        assert SoilPHSensor.classify(7.51) == "alkaline"
        assert SoilPHSensor.classify(9.0) == "alkaline"

    def test_classification_in_reading_metadata(self):
        """Each mock reading should carry its classification in metadata."""
        s = SoilPHSensor(mock_mode=True)
        s.initialize()
        r = s.read()
        assert r is not None
        assert "classification" in r.metadata
        assert r.metadata["classification"] in ("acidic", "optimal", "alkaline")

    def test_health_check(self):
        """health_check() should report the configured sensor identity."""
        s = SoilPHSensor(mock_mode=True)
        s.initialize()
        s.read()
        hc = s.health_check()
        assert hc["name"] == "soil_ph"
        assert hc["bus_type"] == "adc"
        assert hc["metrics"] == ["soil_pH"]
        assert hc["initialized"] is True
        assert hc["mock_mode"] is True
        assert hc["healthy"] is True

    def test_cleanup_does_not_raise(self):
        """cleanup() should be safe to call even with no hardware."""
        s = SoilPHSensor(mock_mode=True)
        s.initialize()
        s.read()
        s.cleanup()  # must not raise

    def test_read_twice(self):
        """Two consecutive reads should both succeed and stay in band."""
        s = SoilPHSensor(mock_mode=True)
        s.initialize()
        r1 = s.read()
        r2 = s.read()
        assert r1 is not None
        assert r2 is not None
        assert 3.0 <= r1.metrics["soil_pH"] <= 10.0
        assert 3.0 <= r2.metrics["soil_pH"] <= 10.0

    def test_clamping_enforced_on_extreme_config(self):
        """Even with a tiny band, mock reads must stay inside it."""
        cfg = pHConfig(min_pH=6.0, max_pH=6.1, mock_mode=True)
        s = SoilPHSensor(config=cfg, mock_mode=True)
        s.initialize()
        r = s.read()
        assert r is not None
        assert 6.0 <= r.metrics["soil_pH"] <= 6.1