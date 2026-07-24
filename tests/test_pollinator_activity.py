"""Tests for the PollinatorActivity adaptation module.

NOTE: These tests cover all pollinator condition bands (excellent, good, poor),
wind override, excessive heat, no-reading case, missing-metric case, and the
disabled-module path. They use sys.path.insert(0, 'src') to import the core
package exactly as pyproject.toml's pythonpath setting would, matching the
convention used by every other test file in this project.

WHY: Pollinator activity estimates inform pesticide scheduling and yield
expectations. Each condition band must produce the correct advisory,
confidence, severity, and pollination_outlook label so the orchestrator and
dashboard can trust the output without re-validating it.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from adaptation.pollinator_activity import PollinatorActivity
from core.types import SensorReading, utc_now


def _reading(temp_c: float, light_lux: float) -> SensorReading:
    """Helper: build a SensorReading with temp_c and light_lux."""
    return SensorReading(
        sensor_name="temp_humidity",
        timestamp=utc_now(),
        metrics={"temp_c": temp_c, "light_lux": light_lux},
        units={"temp_c": "°C", "light_lux": "lux"},
    )


class TestPollinatorActivityMetadata:
    """Tests for class-level metadata."""

    def test_class_attributes(self):
        """Module exposes the required class-level metadata."""
        assert PollinatorActivity.name == "pollinator_activity"
        assert PollinatorActivity.category == "animal"
        assert "pollinator" in PollinatorActivity.description.lower()


class TestPollinatorActivityExcellent:
    """Tests for the excellent pollination band."""

    def test_excellent_conditions(self):
        """temp 18–30 and light > 10000 → excellent, confidence 0.7, info."""
        m = PollinatorActivity()
        result = m.analyze(_reading(24.0, 15000.0), {})
        assert result.module_name == "pollinator_activity"
        assert result.category == "animal"
        assert "excellent" in result.advisory.lower()
        assert "bees and butterflies" in result.advisory.lower()
        assert result.confidence == 0.7
        assert result.severity == "info"
        assert result.data["temp"] == 24.0
        assert result.data["light"] == 15000.0
        assert result.data["wind_strong"] is False
        assert result.data["pollination_outlook"] == "excellent"

    def test_excellent_boundary_temp_18(self):
        """temp exactly 18, light > 10000 → excellent (lower temp boundary)."""
        m = PollinatorActivity()
        result = m.analyze(_reading(18.0, 12000.0), {})
        assert result.data["pollination_outlook"] == "excellent"
        assert result.confidence == 0.7

    def test_excellent_boundary_temp_30(self):
        """temp exactly 30, light > 10000 → excellent (upper temp boundary)."""
        m = PollinatorActivity()
        result = m.analyze(_reading(30.0, 12000.0), {})
        assert result.data["pollination_outlook"] == "excellent"
        assert result.confidence == 0.7


class TestPollinatorActivityGood:
    """Tests for the good pollination band."""

    def test_good_conditions(self):
        """temp 15–35 and light > 5000 (not excellent) → good, confidence 0.5."""
        m = PollinatorActivity()
        # temp=32, light=6000 — meets good but not excellent (temp > 30)
        result = m.analyze(_reading(32.0, 6000.0), {})
        assert "good pollination" in result.advisory.lower()
        assert result.confidence == 0.5
        assert result.severity == "info"
        assert result.data["pollination_outlook"] == "good"

    def test_good_boundary_temp_15(self):
        """temp exactly 15, light > 5000 → good (lower temp boundary)."""
        m = PollinatorActivity()
        result = m.analyze(_reading(15.0, 8000.0), {})
        assert result.data["pollination_outlook"] == "good"
        assert result.confidence == 0.5


class TestPollinatorActivityPoor:
    """Tests for the poor pollination band (cold/dark)."""

    def test_too_cold(self):
        """temp < 15 → poor, confidence 0.6, info."""
        m = PollinatorActivity()
        result = m.analyze(_reading(10.0, 20000.0), {})
        assert "too cold or dark" in result.advisory.lower()
        assert result.confidence == 0.6
        assert result.severity == "info"
        assert result.data["pollination_outlook"] == "poor"

    def test_too_dark(self):
        """light < 500 → poor, confidence 0.6, info."""
        m = PollinatorActivity()
        result = m.analyze(_reading(24.0, 300.0), {})
        assert "too cold or dark" in result.advisory.lower()
        assert result.confidence == 0.6
        assert result.data["pollination_outlook"] == "poor"


class TestPollinatorActivityWind:
    """Tests for the wind override band."""

    def test_wind_strong_overrides_excellent(self):
        """wind_strong=True overrides excellent conditions → advisory, 0.5."""
        m = PollinatorActivity()
        result = m.analyze(_reading(24.0, 15000.0), {"wind_strong": True})
        assert "wind reducing pollinator" in result.advisory.lower()
        assert "strong wind" in result.advisory.lower()
        assert result.confidence == 0.5
        assert result.severity == "advisory"
        assert result.data["wind_strong"] is True
        assert result.data["pollination_outlook"] == "poor"

    def test_wind_strong_default_false(self):
        """wind_strong not in context defaults to False."""
        m = PollinatorActivity()
        result = m.analyze(_reading(24.0, 15000.0), {})
        assert result.data["wind_strong"] is False


class TestPollinatorActivityHot:
    """Tests for the excessive-heat band."""

    def test_too_hot(self):
        """temp > 35 → advisory, confidence 0.6, advisory severity."""
        m = PollinatorActivity()
        result = m.analyze(_reading(40.0, 20000.0), {})
        assert "too hot for pollinators" in result.advisory.lower()
        assert result.confidence == 0.6
        assert result.severity == "advisory"
        assert result.data["pollination_outlook"] == "poor"


class TestPollinatorActivityNoData:
    """Tests for no-data paths."""

    def test_no_reading(self):
        """No reading at all → no-data advisory, confidence 0.0."""
        m = PollinatorActivity()
        result = m.analyze(None, {})
        assert "no data for pollinator" in result.advisory.lower()
        assert result.confidence == 0.0
        assert result.data["temp"] is None
        assert result.data["light"] is None
        assert result.data["pollination_outlook"] == "no_data"

    def test_reading_missing_metrics(self):
        """Reading present but temp_c/light_lux absent → no data."""
        m = PollinatorActivity()
        reading = SensorReading(
            sensor_name="temp_humidity",
            timestamp=utc_now(),
            metrics={"humidity_pct": 60.0},
            units={"humidity_pct": "%"},
        )
        result = m.analyze(reading, {})
        assert "no data for pollinator" in result.advisory.lower()
        assert result.confidence == 0.0
        assert result.data["pollination_outlook"] == "no_data"


class TestPollinatorActivityDisabled:
    """Tests for the disabled-module path."""

    def test_disabled_module_returns_disabled(self):
        """When the module is disabled, process() short-circuits."""
        m = PollinatorActivity()
        m.set_enabled(False)
        result = m.process(_reading(24.0, 15000.0), {})
        assert "disabled" in result.advisory.lower()
        assert result.confidence == 0.0
        assert result.data == {}