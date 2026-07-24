"""Tests for the FrostAlert adaptation module.

NOTE: These tests cover all four temperature bands (imminent, risk-night,
cool, safe), the no-reading case, a reading missing the temp_c metric, the
hour-based early-morning risk path, and the disabled-module path.
They use sys.path.insert(0, 'src') to import the core package exactly as
pyproject.toml's pythonpath setting would, matching the convention used
by every other test file in this project.

WHY: Frost is the most destructive weather event for many crops.  Each band
boundary must produce the correct advisory, confidence, severity, and
frost_risk label so the orchestrator and dashboard can trust the output
without re-validating it.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from adaptation.frost_alert import FrostAlert
from core.types import SensorReading, utc_now


def _reading(temp: float, humidity: float = 60.0) -> SensorReading:
    """Helper: build a SensorReading with temp_c (and optional humidity_pct)."""
    return SensorReading(
        sensor_name="temp_humidity",
        timestamp=utc_now(),
        metrics={"temp_c": temp, "humidity_pct": humidity},
        units={"temp_c": "°C", "humidity_pct": "%"},
    )


class TestFrostAlert:
    """Tests for the FrostAlert adaptation module."""

    def test_class_attributes(self):
        """Module exposes the required class-level metadata."""
        assert FrostAlert.name == "frost_alert"
        assert FrostAlert.category == "weather"
        assert "frost" in FrostAlert.description.lower()

    def test_frost_imminent_below_2c(self):
        """temp < 2 °C → critical, confidence 0.9, frost_risk imminent."""
        m = FrostAlert()
        result = m.analyze(_reading(1.0), {"is_night": True})
        assert result.module_name == "frost_alert"
        assert result.category == "weather"
        assert "immediate" in result.advisory.lower()
        assert result.confidence == 0.9
        assert result.severity == "critical"
        assert result.data["temp"] == 1.0
        assert result.data["frost_risk"] == "imminent"

    def test_frost_risk_night_2_to_5c(self):
        """temp 2-5 °C at night → warning, confidence 0.7, frost_risk risk."""
        m = FrostAlert()
        result = m.analyze(_reading(3.0), {"is_night": True})
        assert "risk" in result.advisory.lower()
        assert result.confidence == 0.7
        assert result.severity == "warning"
        assert result.data["frost_risk"] == "risk"
        assert result.data["is_night"] is True

    def test_frost_risk_early_morning_hour(self):
        """temp 2-5 °C with hour in 0-6 → warning (hour-based night detection)."""
        m = FrostAlert()
        result = m.analyze(_reading(4.0), {"hour": 3})
        assert "risk" in result.advisory.lower()
        assert result.severity == "warning"
        assert result.data["frost_risk"] == "risk"
        assert result.data["is_night"] is True

    def test_cool_5_to_10c(self):
        """temp 5-10 °C → info, confidence 0.6, frost_risk none."""
        m = FrostAlert()
        result = m.analyze(_reading(7.0), {})
        assert "cool" in result.advisory.lower()
        assert result.confidence == 0.6
        assert result.severity == "info"
        assert result.data["frost_risk"] == "none"

    def test_safe_above_10c(self):
        """temp > 10 °C → info, confidence 0.8, frost_risk none."""
        m = FrostAlert()
        result = m.analyze(_reading(15.0), {})
        assert "no frost risk" in result.advisory.lower()
        assert result.confidence == 0.8
        assert result.severity == "info"
        assert result.data["frost_risk"] == "none"
        assert result.data["temp"] == 15.0

    def test_no_reading(self):
        """No reading at all → no-data advisory, confidence 0.0."""
        m = FrostAlert()
        result = m.analyze(None, {})
        assert "no temperature data" in result.advisory.lower()
        assert result.confidence == 0.0
        assert result.data["temp"] is None
        assert result.data["frost_risk"] == "none"

    def test_reading_missing_temp_metric(self):
        """Reading present but temp_c absent → treated as no data."""
        m = FrostAlert()
        reading = SensorReading(
            sensor_name="temp_humidity",
            timestamp=utc_now(),
            metrics={"humidity_pct": 70.0},
            units={"humidity_pct": "%"},
        )
        result = m.analyze(reading, {})
        assert "no temperature data" in result.advisory.lower()
        assert result.confidence == 0.0
        assert result.data["temp"] is None

    def test_2_to_5c_daytime_no_risk(self):
        """temp 2-5 °C during daytime (no night context) → cool, not risk."""
        m = FrostAlert()
        result = m.analyze(_reading(4.0), {"is_night": False})
        # Without night context, 2-5°C falls into the cool band, not risk.
        assert "cool" in result.advisory.lower()
        assert result.severity == "info"
        assert result.data["frost_risk"] == "none"

    def test_disabled_module_returns_disabled(self):
        """When the module is disabled, process() short-circuits."""
        m = FrostAlert()
        m.set_enabled(False)
        result = m.process(_reading(1.0), {"is_night": True})
        assert "disabled" in result.advisory.lower()
        assert result.confidence == 0.0