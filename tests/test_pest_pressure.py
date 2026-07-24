"""Tests for the PestPressure adaptation module.

NOTE: These tests cover all five pest-pressure bands (fruit flies, aphids,
thrips, moderate, cool/low), the no-reading case, a reading missing the
required metrics, the seasonal month context, and the disabled-module path.
They use sys.path.insert(0, 'src') to import the adaptation package exactly as
pyproject.toml's pythonpath setting would, matching the convention used by
every other test file in this project.

WHY: Pest pressure is the main yield-loss driver in Kenyan orchards. Each
band boundary must produce the correct advisory, confidence, severity, and
pest_risks list so the orchestrator and dashboard can trust the output
without re-validating it.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from adaptation.pest_pressure import PestPressure
from core.types import SensorReading, utc_now


def _reading(temp: float, humidity: float) -> SensorReading:
    """Helper: build a SensorReading with temp_c and humidity_pct."""
    return SensorReading(
        sensor_name="temp_humidity",
        timestamp=utc_now(),
        metrics={"temp_c": temp, "humidity_pct": humidity},
        units={"temp_c": "°C", "humidity_pct": "%"},
    )


class TestPestPressure:
    """Tests for the PestPressure adaptation module."""

    def test_class_attributes(self):
        """Module exposes the required class-level metadata."""
        assert PestPressure.name == "pest_pressure"
        assert PestPressure.category == "insect"
        assert "pest" in PestPressure.description.lower()

    def test_fruit_fly_warm_humid(self):
        """temp 25-35 and humidity > 60 → fruit fly warning, confidence 0.6."""
        m = PestPressure()
        result = m.analyze(_reading(28.0, 65.0), {})
        assert result.module_name == "pest_pressure"
        assert result.category == "insect"
        assert "fruit fly" in result.advisory.lower()
        assert result.confidence == 0.6
        assert result.severity == "warning"
        assert result.data["temp"] == 28.0
        assert result.data["humidity"] == 65.0
        assert "fruit_flies" in result.data["pest_risks"]

    def test_aphid_pressure_moderate_humid(self):
        """temp 20-30 and humidity > 70 → aphid advisory, confidence 0.5."""
        m = PestPressure()
        result = m.analyze(_reading(22.0, 75.0), {})
        assert "aphid" in result.advisory.lower()
        assert result.confidence == 0.5
        assert result.severity == "advisory"
        assert "aphids" in result.data["pest_risks"]

    def test_thrips_hot_dry(self):
        """temp > 30 and humidity < 40 → thrips advisory, confidence 0.5."""
        m = PestPressure()
        result = m.analyze(_reading(32.0, 30.0), {})
        assert "thrips" in result.advisory.lower()
        assert result.confidence == 0.5
        assert result.severity == "advisory"
        assert "thrips" in result.data["pest_risks"]

    def test_moderate_pressure(self):
        """temp 15-25 and humidity 40-70 → moderate info, confidence 0.4."""
        m = PestPressure()
        result = m.analyze(_reading(20.0, 55.0), {})
        assert "moderate pest pressure" in result.advisory.lower()
        assert result.confidence == 0.4
        assert result.severity == "info"
        assert result.data["pest_risks"] == []

    def test_low_pressure_cool(self):
        """temp < 15 → low pest pressure info, confidence 0.5."""
        m = PestPressure()
        result = m.analyze(_reading(10.0, 60.0), {})
        assert "low pest pressure" in result.advisory.lower()
        assert result.confidence == 0.5
        assert result.severity == "info"
        assert result.data["pest_risks"] == []

    def test_no_reading(self):
        """No reading at all → no-data advisory, confidence 0.0."""
        m = PestPressure()
        result = m.analyze(None, {})
        assert "no environmental data" in result.advisory.lower()
        assert result.confidence == 0.0
        assert result.data["temp"] is None
        assert result.data["humidity"] is None
        assert result.data["pest_risks"] == []

    def test_reading_missing_metrics(self):
        """Reading present but temp_c/humidity_pct absent → treated as no data."""
        m = PestPressure()
        reading = SensorReading(
            sensor_name="temp_humidity",
            timestamp=utc_now(),
            metrics={"humidity_pct": 70.0},  # temp_c missing
            units={"humidity_pct": "%"},
        )
        result = m.analyze(reading, {})
        assert "no environmental data" in result.advisory.lower()
        assert result.confidence == 0.0
        assert result.data["temp"] is None

    def test_month_context_default_and_provided(self):
        """month defaults to 1 and is reflected in data; provided month passes through."""
        m = PestPressure()
        # Default month when context omits it.
        result = m.analyze(_reading(28.0, 65.0), {})
        assert result.data["month"] == 1
        # Explicit month is carried through.
        result2 = m.analyze(_reading(28.0, 65.0), {"month": 7})
        assert result2.data["month"] == 7

    def test_disabled_module_returns_disabled(self):
        """When the module is disabled, process() short-circuits."""
        m = PestPressure()
        m.set_enabled(False)
        result = m.process(_reading(28.0, 65.0), {})
        assert "disabled" in result.advisory.lower()
        assert result.confidence == 0.0