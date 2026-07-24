"""Tests for the ambient light sensor driver.

NOTE: These tests exercise the mock path only — no hardware is required.
They cover reading, all five classification thresholds, the is_night()
helper, diurnal variation from MockManager, health checks, cleanup, and
repeated reads. Uses sys.path.insert(0, 'src') to import the core package
exactly as pyproject.toml's pythonpath setting would.

WHY: The light driver's classify() bands drive night-mode entry and
agronomic light context, so each band boundary must be pinned and tested.
is_night() is the gate for the sentinel, so it must flip correctly at the
configured threshold. The diurnal test guards against regressions in
MockManager's day/night cycle for light_lux.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.config import LightConfig
from core.types import SensorReading
from sensors.light_sensor import LightSensor


class TestLightSensor:
    def setup_method(self):
        """Fresh sensor in mock mode for every test."""
        cfg = LightConfig(mock_mode=True)
        self.sensor = LightSensor(config=cfg, mock_mode=True)
        assert self.sensor.initialize() is True

    # -- class attributes / shape --------------------------------------

    def test_class_attributes(self):
        """Class attributes should match the SensorBase contract."""
        assert LightSensor.name == "light"
        assert LightSensor.bus_type == "adc"
        assert LightSensor.metrics == ["light_lux"]
        assert "light" in LightSensor.description.lower()
        assert "day/night" in LightSensor.description

    def test_health_check_shape(self):
        """health_check() should report the configured sensor identity."""
        self.sensor.read()
        hc = self.sensor.health_check()
        assert hc["name"] == "light"
        assert hc["bus_type"] == "adc"
        assert hc["metrics"] == ["light_lux"]
        assert hc["initialized"] is True
        assert hc["mock_mode"] is True
        assert hc["healthy"] is True

    # -- mock read ------------------------------------------------------

    def test_mock_read_returns_reading(self):
        """A mock-mode read should return a SensorReading with light_lux."""
        r = self.sensor.read()
        assert r is not None
        assert isinstance(r, SensorReading)
        assert r.sensor_name == "light"
        assert "light_lux" in r.metrics
        assert r.units["light_lux"] == "lx"
        assert r.metadata["source"] == "mock"

    def test_mock_value_nonnegative(self):
        """Mock lux must never be negative — illuminance is unsigned."""
        for _ in range(20):
            r = self.sensor.read()
            assert r is not None
            assert r.metrics["light_lux"] >= 0.0

    def test_classification_in_reading_metadata(self):
        """Each mock reading should carry its classification in metadata."""
        r = self.sensor.read()
        assert r is not None
        assert "classification" in r.metadata
        assert r.metadata["classification"] in (
            "night", "dawn_dusk", "overcast", "daylight", "bright",
        )

    # -- classify thresholds (all 5 categories) ------------------------

    def test_classify_night(self):
        """< 10 lux is night."""
        assert LightSensor(mock_mode=True).classify(0.0) == "night"
        assert LightSensor(mock_mode=True).classify(5.0) == "night"
        assert LightSensor(mock_mode=True).classify(9.99) == "night"

    def test_classify_dawn_dusk(self):
        """10 – 500 lux is dawn_dusk."""
        s = LightSensor(mock_mode=True)
        assert s.classify(10.0) == "dawn_dusk"
        assert s.classify(100.0) == "dawn_dusk"
        assert s.classify(499.99) == "dawn_dusk"

    def test_classify_overcast(self):
        """500 – 10 000 lux is overcast."""
        s = LightSensor(mock_mode=True)
        assert s.classify(500.0) == "overcast"
        assert s.classify(5000.0) == "overcast"
        assert s.classify(9999.99) == "overcast"

    def test_classify_daylight(self):
        """10 000 – 50 000 lux is daylight."""
        s = LightSensor(mock_mode=True)
        assert s.classify(10_000.0) == "daylight"
        assert s.classify(25_000.0) == "daylight"
        assert s.classify(49_999.99) == "daylight"

    def test_classify_bright(self):
        """> 50 000 lux is bright."""
        s = LightSensor(mock_mode=True)
        assert s.classify(50_000.0) == "bright"
        assert s.classify(80_000.0) == "bright"
        assert s.classify(100_000.0) == "bright"

    # -- is_night -------------------------------------------------------

    def test_is_night_true_below_threshold(self):
        """is_night() returns True when lux is below the night threshold."""
        cfg = LightConfig(night_lux_threshold=10.0, mock_mode=True)
        s = LightSensor(config=cfg, mock_mode=True)
        s.initialize()
        # Stub the read to force a sub-threshold value.
        s._read_mock = lambda: SensorReading(
            sensor_name="light",
            timestamp="",
            metrics={"light_lux": 5.0},
            units={"light_lux": "lx"},
            metadata={"source": "mock"},
        )
        assert s.is_night() is True

    def test_is_night_false_above_threshold(self):
        """is_night() returns False when lux is at/above the threshold."""
        cfg = LightConfig(night_lux_threshold=10.0, mock_mode=True)
        s = LightSensor(config=cfg, mock_mode=True)
        s.initialize()
        s._read_mock = lambda: SensorReading(
            sensor_name="light",
            timestamp="",
            metrics={"light_lux": 500.0},
            units={"light_lux": "lx"},
            metadata={"source": "mock"},
        )
        assert s.is_night() is False

    # -- diurnal variation ----------------------------------------------

    def test_diurnal_variation_between_reads(self):
        """Successive mock reads should vary (diurnal cycle + jitter).

        NOTE: MockManager applies a diurnal sine to light_lux plus ±5%
        jitter, so two reads should almost always differ. We sample a few
        times to avoid a rare coincidental tie at a cycle peak/trough.
        """
        values = []
        for _ in range(10):
            r = self.sensor.read()
            assert r is not None
            values.append(r.metrics["light_lux"])
        assert len(set(values)) > 1, "diurnal+jitter should produce varied lux"

    # -- read twice -----------------------------------------------------

    def test_read_twice(self):
        """Two consecutive reads should both succeed and be non-negative."""
        r1 = self.sensor.read()
        r2 = self.sensor.read()
        assert r1 is not None
        assert r2 is not None
        assert r1.sensor_name == "light"
        assert r2.sensor_name == "light"
        assert r1.metrics["light_lux"] >= 0.0
        assert r2.metrics["light_lux"] >= 0.0

    # -- cleanup --------------------------------------------------------

    def test_cleanup_does_not_raise(self):
        """cleanup() should be safe to call even with no hardware."""
        self.sensor.read()
        self.sensor.cleanup()  # must not raise
        # idempotent
        self.sensor.cleanup()