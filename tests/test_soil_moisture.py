"""Tests for the capacitive soil moisture sensor driver.

NOTE: These tests run entirely in mock mode — no SPI/ADC hardware is
required. They verify the SensorBase contract, mock-data shape, ADC
calibration math, classification thresholds, and cleanup behavior.

WHY: A soil moisture driver is one of the core agricultural inputs; it
must remain correct and mock-testable on any machine without the
CircuitPython stack installed.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.config import SoilConfig
from core.mock_manager import MockManager
from core.types import SensorReading
from sensors.soil_moisture import SoilMoistureSensor


class TestSoilMoistureSensor:
    """End-to-end mock-mode tests for SoilMoistureSensor."""

    def test_mock_read_returns_valid_reading(self):
        """A mock-mode read must produce a fully-populated SensorReading."""
        s = SoilMoistureSensor(SoilConfig(mock_mode=True))
        assert s.initialize() is True

        r = s.read()
        assert r is not None
        assert isinstance(r, SensorReading)
        assert r.sensor_name == "soil_moisture"
        assert "soil_moisture_pct" in r.metrics
        assert r.units["soil_moisture_pct"] == "%"
        assert r.metadata["source"] == "mock"
        assert r.metadata["classification"] in ("dry", "moist", "wet")
        # Mock baseline is ~45 % → value should be in a sane band
        assert 0.0 <= r.metrics["soil_moisture_pct"] <= 100.0

    def test_mock_uses_mock_manager(self):
        """Mock path should delegate to MockManager's soil_moisture_pct."""
        s = SoilMoistureSensor(SoilConfig(mock_mode=True))
        s.initialize()

        # Seed a fixed MockManager and confirm its value flows through.
        s._mock = MockManager(seed=7)
        expected = s._mock.get("soil_moisture_pct", jitter=0.05)
        # The next read() will advance the walk once more, so just verify
        # the reading is drawn from the MockManager's ballpark (±15 %).
        r = s.read()
        assert r is not None
        assert abs(r.metrics["soil_moisture_pct"] - expected) < 15.0

    def test_timestamp_is_iso8601_utc(self):
        """Every reading must carry an ISO 8601 UTC timestamp."""
        s = SoilMoistureSensor(SoilConfig(mock_mode=True))
        s.initialize()

        r = s.read()
        assert r is not None
        assert r.timestamp.endswith("Z")
        assert "T" in r.timestamp
        assert len(r.timestamp) >= len("2026-01-01T00:00:00Z")

    def test_classify_dry(self):
        """Below dry_threshold (default 30 %) → 'dry'."""
        s = SoilMoistureSensor(SoilConfig(mock_mode=True))
        assert s.classify(10.0) == "dry"
        assert s.classify(0.0) == "dry"
        assert s.classify(29.9) == "dry"

    def test_classify_moist(self):
        """Between dry_threshold and wet_threshold (30–70 %) → 'moist'."""
        s = SoilMoistureSensor(SoilConfig(mock_mode=True))
        assert s.classify(30.0) == "moist"
        assert s.classify(50.0) == "moist"
        assert s.classify(70.0) == "moist"

    def test_classify_wet(self):
        """Above wet_threshold (default 70 %) → 'wet'."""
        s = SoilMoistureSensor(SoilConfig(mock_mode=True))
        assert s.classify(70.1) == "wet"
        assert s.classify(85.0) == "wet"
        assert s.classify(100.0) == "wet"

    def test_classify_respects_custom_thresholds(self):
        """Thresholds come from SoilConfig and should be honoured."""
        cfg = SoilConfig(mock_mode=True, dry_threshold=20.0, wet_threshold=60.0)
        s = SoilMoistureSensor(cfg)
        assert s.classify(19.9) == "dry"
        assert s.classify(20.0) == "moist"
        assert s.classify(60.0) == "moist"
        assert s.classify(60.1) == "wet"

    def test_health_check_shape(self):
        """health_check() must expose the SensorBase contract fields."""
        s = SoilMoistureSensor(SoilConfig(mock_mode=True))
        s.initialize()
        s.read()

        hc = s.health_check()
        assert hc["name"] == "soil_moisture"
        assert hc["bus_type"] == "adc"
        assert hc["metrics"] == ["soil_moisture_pct"]
        assert "description" in hc
        assert hc["initialized"] is True
        assert hc["healthy"] is True
        assert hc["mock_mode"] is True

    def test_cleanup_noop_in_mock(self):
        """cleanup() in mock mode must be a safe no-op and not raise."""
        s = SoilMoistureSensor(SoilConfig(mock_mode=True))
        s.initialize()
        s.read()
        s.cleanup()  # should not raise
        # Reading after cleanup still works (mock path needs no hardware)
        s.initialize()
        r = s.read()
        assert r is not None

    def test_read_twice_consistency(self):
        """Two successive mock reads must both be valid and within range."""
        s = SoilMoistureSensor(SoilConfig(mock_mode=True))
        s.initialize()

        r1 = s.read()
        r2 = s.read()
        assert r1 is not None
        assert r2 is not None
        assert r1.sensor_name == r2.sensor_name == "soil_moisture"
        for r in (r1, r2):
            assert 0.0 <= r.metrics["soil_moisture_pct"] <= 100.0
            assert r.units["soil_moisture_pct"] == "%"
            assert r.metadata["source"] == "mock"

    def test_counts_to_moisture_calibration(self):
        """ADC counts → percent must be linear: 0 counts = 0 %, 1023 ≈ 100 %."""
        assert SoilMoistureSensor._counts_to_moisture(0) == 0.0
        assert SoilMoistureSensor._counts_to_moisture(1023) == 100.0
        # Mid-range: 512 counts ≈ 50 % (rounds to 50.0 within 0.5)
        mid = SoilMoistureSensor._counts_to_moisture(512)
        assert 49.0 <= mid <= 51.0

    def test_classify_threshold_boundary_in_reading(self):
        """A mock reading's metadata classification must match classify()."""
        s = SoilMoistureSensor(SoilConfig(mock_mode=True))
        s.initialize()

        r = s.read()
        assert r is not None
        pct = r.metrics["soil_moisture_pct"]
        expected = s.classify(pct)
        assert r.metadata["classification"] == expected