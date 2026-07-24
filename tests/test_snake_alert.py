"""Tests for the SnakeAlert adaptation module.

NOTE: These tests cover every advisory band (warm+sparse, warm+cover, very
hot, cool, cold), the no-reading path, the default ground-cover fallback,
context soil-temperature override, the disabled-module path, and class-level
metadata.
They use sys.path.insert(0, 'src') to import the core package exactly as
pyproject.toml's pythonpath setting would, matching the convention used
by every other test file in this project.

WHY: Snakes are a safety hazard in the field. Each temperature/cover band
must produce the correct advisory, confidence, severity, and snake_risk
label so the orchestrator and dashboard can trust the output without
re-validating it.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from adaptation.snake_alert import SnakeAlert
from core.types import SensorReading, utc_now


def _reading(temp_c: float | None = None) -> SensorReading:
    """Helper: build a SensorReading, optionally carrying temp_c."""
    metrics = {}
    if temp_c is not None:
        metrics["temp_c"] = temp_c
    return SensorReading(
        sensor_name="temp_humidity",
        timestamp=utc_now(),
        metrics=metrics,
        units={"temp_c": "°C"} if temp_c is not None else {},
    )


class TestSnakeAlert:
    """Tests for the SnakeAlert adaptation module."""

    def test_class_attributes(self):
        """Module exposes the required class-level metadata."""
        assert SnakeAlert.name == "snake_alert"
        assert SnakeAlert.category == "animal"
        assert "snake" in SnakeAlert.description.lower()

    def test_warm_sparse_cover(self):
        """temp 25-35 with ground_cover < 40 → advisory, confidence 0.5, high risk."""
        m = SnakeAlert()
        result = m.analyze(_reading(temp_c=30), {"ground_cover_pct": 20})
        assert result.module_name == "snake_alert"
        assert result.category == "animal"
        assert "watch your step" in result.advisory.lower()
        assert result.confidence == 0.5
        assert result.severity == "advisory"
        assert result.data["temp"] == 30
        assert result.data["ground_cover"] == 20
        assert result.data["snake_risk"] == "high"

    def test_warm_adequate_cover(self):
        """temp 25-35 with ground_cover ≥ 40 → info, confidence 0.4, moderate risk."""
        m = SnakeAlert()
        result = m.analyze(_reading(temp_c=28), {"ground_cover_pct": 60})
        assert "moderate snake risk" in result.advisory.lower()
        assert result.confidence == 0.4
        assert result.severity == "info"
        assert result.data["snake_risk"] == "moderate"

    def test_very_hot(self):
        """temp > 35 → info, confidence 0.4, low risk (snakes seek shade)."""
        m = SnakeAlert()
        result = m.analyze(_reading(temp_c=40), {"ground_cover_pct": 20})
        assert "seek shade" in result.advisory.lower()
        assert result.confidence == 0.4
        assert result.severity == "info"
        assert result.data["snake_risk"] == "low"

    def test_cool_conditions(self):
        """temp 15-25 → info, confidence 0.5, low risk (reduced activity)."""
        m = SnakeAlert()
        result = m.analyze(_reading(temp_c=20), {"ground_cover_pct": 50})
        assert "cool conditions" in result.advisory.lower()
        assert result.confidence == 0.5
        assert result.severity == "info"
        assert result.data["snake_risk"] == "low"

    def test_too_cool(self):
        """temp < 15 → info, confidence 0.6, low risk (too cool for snakes)."""
        m = SnakeAlert()
        result = m.analyze(_reading(temp_c=10), {"ground_cover_pct": 50})
        assert "too cool" in result.advisory.lower()
        assert result.confidence == 0.6
        assert result.severity == "info"
        assert result.data["snake_risk"] == "low"

    def test_no_reading(self):
        """No reading (or reading without temp_c) → no-data result, confidence 0.0."""
        m = SnakeAlert()
        result = m.analyze(_reading(temp_c=None), {"ground_cover_pct": 30})
        assert "no temperature data" in result.advisory.lower()
        assert result.confidence == 0.0
        assert result.data["temp"] is None
        assert result.data["ground_cover"] == 30
        assert result.data["snake_risk"] == "low"

    def test_default_ground_cover(self):
        """Missing ground_cover_pct defaults to 50 (warm → moderate risk)."""
        m = SnakeAlert()
        result = m.analyze(_reading(temp_c=30), {})
        assert result.data["ground_cover"] == 50
        assert result.data["snake_risk"] == "moderate"
        assert result.severity == "info"

    def test_soil_temp_override(self):
        """context['soil_temp_c'] overrides the air temp for assessment."""
        m = SnakeAlert()
        # Air temp is warm (30 °C) but soil temp context says it's cold (10 °C).
        result = m.analyze(_reading(temp_c=30), {"soil_temp_c": 10, "ground_cover_pct": 20})
        assert "too cool" in result.advisory.lower()
        assert result.data["temp"] == 10
        assert result.data["snake_risk"] == "low"

    def test_disabled_module_returns_disabled(self):
        """When the module is disabled, process() short-circuits."""
        m = SnakeAlert()
        m.set_enabled(False)
        result = m.process(_reading(temp_c=30), {"ground_cover_pct": 20})
        assert "disabled" in result.advisory.lower()
        assert result.confidence == 0.0