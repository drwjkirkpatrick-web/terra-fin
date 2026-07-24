"""Tests for the HumidityComfort adaptation module.

NOTE: These tests cover all five humidity bands, the no-reading case, a
reading missing the humidity_pct metric, and the disabled-module path.
They use sys.path.insert(0, 'src') to import the core package exactly as
pyproject.toml's pythonpath setting would, matching the convention used
by every other test file in this project.

WHY: Humidity is the leading indicator for fungal disease and plant water
stress. Each band boundary must produce the correct advisory, confidence,
severity, and comfort_level label so the orchestrator and dashboard can
trust the output without re-validating it.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from adaptation.humidity_comfort import HumidityComfort
from core.types import SensorReading, utc_now


def _reading(humidity: float) -> SensorReading:
    """Helper: build a SensorReading with just humidity_pct."""
    return SensorReading(
        sensor_name="temp_humidity",
        timestamp=utc_now(),
        metrics={"humidity_pct": humidity},
        units={"humidity_pct": "%"},
    )


class TestHumidityComfort:
    """Tests for the HumidityComfort adaptation module."""

    def test_class_attributes(self):
        """Module exposes the required class-level metadata."""
        assert HumidityComfort.name == "humidity_comfort"
        assert HumidityComfort.category == "weather"
        assert "humidity" in HumidityComfort.description.lower()

    def test_very_humid_above_85(self):
        """humidity > 85 % → warning, confidence 0.7, very_humid label."""
        m = HumidityComfort()
        result = m.analyze(_reading(90.0), {})
        assert result.module_name == "humidity_comfort"
        assert result.category == "weather"
        assert "fungal disease" in result.advisory.lower()
        assert result.confidence == 0.7
        assert result.severity == "warning"
        assert result.data["humidity"] == 90.0
        assert result.data["comfort_level"] == "very_humid"

    def test_humid_70_to_85(self):
        """humidity 70–85 % → advisory, confidence 0.6, humid label."""
        m = HumidityComfort()
        result = m.analyze(_reading(78.0), {})
        assert "mildew" in result.advisory.lower()
        assert result.confidence == 0.6
        assert result.severity == "advisory"
        assert result.data["comfort_level"] == "humid"

    def test_comfortable_40_to_70(self):
        """humidity 40–70 % → info, confidence 0.8, comfortable label."""
        m = HumidityComfort()
        result = m.analyze(_reading(55.0), {})
        assert "comfortable" in result.advisory.lower()
        assert result.confidence == 0.8
        assert result.severity == "info"
        assert result.data["comfort_level"] == "comfortable"

    def test_dry_below_40(self):
        """humidity < 40 % (but >= 25) → advisory, confidence 0.7, dry label."""
        m = HumidityComfort()
        result = m.analyze(_reading(35.0), {})
        assert "dry air" in result.advisory.lower()
        assert result.confidence == 0.7
        assert result.severity == "advisory"
        assert result.data["comfort_level"] == "dry"

    def test_very_dry_below_25(self):
        """humidity < 25 % → warning, confidence 0.8, very_dry label."""
        m = HumidityComfort()
        result = m.analyze(_reading(20.0), {})
        assert "very dry" in result.advisory.lower()
        assert result.confidence == 0.8
        assert result.severity == "warning"
        assert result.data["comfort_level"] == "very_dry"

    def test_no_reading(self):
        """No reading at all → no-data advisory, confidence 0.0."""
        m = HumidityComfort()
        result = m.analyze(None, {})
        assert "no humidity data" in result.advisory.lower()
        assert result.confidence == 0.0
        assert result.data["humidity"] is None
        assert result.data["comfort_level"] == "no_data"

    def test_reading_missing_humidity_metric(self):
        """Reading present but humidity_pct absent → treated as no data."""
        m = HumidityComfort()
        reading = SensorReading(
            sensor_name="temp_humidity",
            timestamp=utc_now(),
            metrics={"temp_c": 24.0},
            units={"temp_c": "°C"},
        )
        result = m.analyze(reading, {})
        assert "no humidity data" in result.advisory.lower()
        assert result.confidence == 0.0
        assert result.data["humidity"] is None

    def test_disabled_module_returns_disabled(self):
        """When the module is disabled, process() short-circuits."""
        m = HumidityComfort()
        m.set_enabled(False)
        result = m.process(_reading(55.0), {})
        assert "disabled" in result.advisory.lower()
        assert result.confidence == 0.0