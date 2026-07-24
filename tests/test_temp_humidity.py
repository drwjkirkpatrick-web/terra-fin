"""Tests for the SHT40 temperature/humidity sensor driver.

NOTE: These tests exercise the mock path only — no hardware is required.
They cover reading both metrics, temperature and humidity classification
thresholds, health checks, diurnal variation, cleanup, and repeated reads.
Uses sys.path.insert(0, 'src') to import the core package exactly as
pyproject.toml's pythonpath setting would.

WHY: Temperature and humidity contextualise every other agronomic reading,
so the mock path must return both metrics and the classification thresholds
must be pinned at their boundaries. Diurnal variation must stay within
physically valid ranges so the agent never acts on absurd mock data.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sensors.temp_humidity import (
    TempHumiditySensor,
    classify_temp,
    classify_humidity,
)


class TestTempHumiditySensor:
    def test_mock_read_returns_both_metrics(self):
        """A mock-mode read should return temp_c and humidity_pct together."""
        s = TempHumiditySensor(mock_mode=True)
        assert s.initialize() is True
        r = s.read()
        assert r is not None
        assert r.sensor_name == "temp_humidity"
        assert "temp_c" in r.metrics
        assert "humidity_pct" in r.metrics
        assert r.units["temp_c"] == "°C"
        assert r.units["humidity_pct"] == "%"
        assert r.metadata["source"] == "mock"

    def test_mock_value_valid_ranges(self):
        """Mock temp/humidity must always stay in physically valid ranges."""
        s = TempHumiditySensor(mock_mode=True)
        s.initialize()
        for _ in range(20):
            r = s.read()
            assert r is not None
            # SHT40 physical range: -40 to +125 °C, 0-100 % RH
            assert -40.0 <= r.metrics["temp_c"] <= 125.0
            assert 0.0 <= r.metrics["humidity_pct"] <= 100.0

    def test_classification_in_reading_metadata(self):
        """Each mock reading should carry temp + humidity classifications."""
        s = TempHumiditySensor(mock_mode=True)
        s.initialize()
        r = s.read()
        assert r is not None
        assert "temp_classification" in r.metadata
        assert r.metadata["temp_classification"] in ("cold", "mild", "hot")
        assert "humidity_classification" in r.metadata
        assert r.metadata["humidity_classification"] in (
            "dry", "comfortable", "humid",
        )

    def test_classify_temp_cold(self):
        """temp < 15 °C is cold."""
        assert classify_temp(14.9) == "cold"
        assert classify_temp(0.0) == "cold"
        assert classify_temp(-10.0) == "cold"

    def test_classify_temp_mild(self):
        """15 ≤ temp ≤ 28 °C is mild (boundaries inclusive)."""
        assert classify_temp(15.0) == "mild"
        assert classify_temp(20.0) == "mild"
        assert classify_temp(28.0) == "mild"

    def test_classify_temp_hot(self):
        """temp > 28 °C is hot."""
        assert classify_temp(28.1) == "hot"
        assert classify_temp(35.0) == "hot"
        assert classify_temp(50.0) == "hot"

    def test_classify_humidity_dry(self):
        """humidity < 40 % is dry."""
        assert classify_humidity(39.9) == "dry"
        assert classify_humidity(20.0) == "dry"
        assert classify_humidity(0.0) == "dry"

    def test_classify_humidity_comfortable(self):
        """40 ≤ humidity ≤ 70 % is comfortable (boundaries inclusive)."""
        assert classify_humidity(40.0) == "comfortable"
        assert classify_humidity(55.0) == "comfortable"
        assert classify_humidity(70.0) == "comfortable"

    def test_classify_humidity_humid(self):
        """humidity > 70 % is humid."""
        assert classify_humidity(70.1) == "humid"
        assert classify_humidity(85.0) == "humid"
        assert classify_humidity(100.0) == "humid"

    def test_health_check(self):
        """health_check() should report the configured sensor identity."""
        s = TempHumiditySensor(mock_mode=True)
        s.initialize()
        s.read()
        hc = s.health_check()
        assert hc["name"] == "temp_humidity"
        assert hc["bus_type"] == "i2c"
        assert hc["metrics"] == ["temp_c", "humidity_pct"]
        assert hc["description"] == "Temperature and humidity sensor (SHT40)"
        assert hc["initialized"] is True
        assert hc["mock_mode"] is True
        assert hc["healthy"] is True

    def test_diurnal_variation(self):
        """Multiple reads across calls should stay in valid range and vary."""
        s = TempHumiditySensor(mock_mode=True)
        s.initialize()
        temps = []
        humids = []
        for _ in range(10):
            r = s.read()
            assert r is not None
            temps.append(r.metrics["temp_c"])
            humids.append(r.metrics["humidity_pct"])
        # All within valid physical range
        assert all(-40.0 <= t <= 125.0 for t in temps)
        assert all(0.0 <= h <= 100.0 for h in humids)
        # With jitter, values should not all be identical
        assert len(set(temps)) > 1 or len(set(humids)) > 1

    def test_cleanup_does_not_raise(self):
        """cleanup() should be safe to call even with no hardware."""
        s = TempHumiditySensor(mock_mode=True)
        s.initialize()
        s.read()
        s.cleanup()  # must not raise

    def test_read_twice(self):
        """Two consecutive reads should both succeed and stay valid."""
        s = TempHumiditySensor(mock_mode=True)
        s.initialize()
        r1 = s.read()
        r2 = s.read()
        assert r1 is not None
        assert r2 is not None
        assert -40.0 <= r1.metrics["temp_c"] <= 125.0
        assert 0.0 <= r1.metrics["humidity_pct"] <= 100.0
        assert -40.0 <= r2.metrics["temp_c"] <= 125.0
        assert 0.0 <= r2.metrics["humidity_pct"] <= 100.0