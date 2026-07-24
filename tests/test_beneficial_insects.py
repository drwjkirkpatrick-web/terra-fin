"""Tests for the BeneficialInsectIndex adaptation module.

NOTE: These tests cover all four habitat-quality bands (excellent, moderate,
low, pesticide-reduced), the extreme-heat addendum, the no-data case, and the
disabled-module path.
They use sys.path.insert(0, 'src') to import packages exactly as
pyproject.toml's pythonpath setting would, matching the convention used by
every other test file in this project.

WHY: Beneficial insects are the backbone of natural pest control. Each
habitat band must produce the correct advisory, confidence, severity, and
habitat_quality label so the orchestrator and dashboard can act without
re-validating the output.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from adaptation.beneficial_insects import BeneficialInsectIndex
from core.types import SensorReading, utc_now


def _reading(temp: float | None = None) -> SensorReading | None:
    """Helper: build a SensorReading with temp_c, or None if temp is None."""
    if temp is None:
        return None
    return SensorReading(
        sensor_name="temp_humidity",
        timestamp=utc_now(),
        metrics={"temp_c": temp, "humidity_pct": 60.0},
        units={"temp_c": "°C", "humidity_pct": "%"},
    )


class TestBeneficialInsectIndex:
    """Tests for the BeneficialInsectIndex adaptation module."""

    def test_class_attributes(self):
        """Module exposes the required class-level metadata."""
        assert BeneficialInsectIndex.name == "beneficial_insects"
        assert BeneficialInsectIndex.category == "insect"
        assert "beneficial" in BeneficialInsectIndex.description.lower()

    def test_excellent_habitat(self):
        """flowering > 5, no pesticide → info, confidence 0.7, excellent."""
        m = BeneficialInsectIndex()
        result = m.analyze(_reading(25.0), {"flowering_plants": 8, "pesticide_used_recently": False})
        assert result.module_name == "beneficial_insects"
        assert result.category == "insect"
        assert "excellent" in result.advisory.lower()
        assert "ladybugs" in result.advisory.lower()
        assert result.confidence == 0.7
        assert result.severity == "info"
        assert result.data["flowering_count"] == 8
        assert result.data["pesticide_recent"] is False
        assert result.data["habitat_quality"] == "excellent"
        assert result.data["temp"] == 25.0

    def test_moderate_habitat(self):
        """flowering 2-5, no pesticide → info, confidence 0.5, moderate."""
        m = BeneficialInsectIndex()
        result = m.analyze(None, {"flowering_plants": 3, "pesticide_used_recently": False})
        assert "moderate" in result.advisory.lower()
        assert "companion" in result.advisory.lower()
        assert result.confidence == 0.5
        assert result.severity == "info"
        assert result.data["flowering_count"] == 3
        assert result.data["habitat_quality"] == "moderate"
        assert result.data["temp"] is None

    def test_pesticide_warning(self):
        """pesticide_used_recently → warning, confidence 0.6, reduced.
        Takes priority regardless of flowering count."""
        m = BeneficialInsectIndex()
        result = m.analyze(None, {"flowering_plants": 10, "pesticide_used_recently": True})
        assert "pesticide" in result.advisory.lower()
        assert "recovery" in result.advisory.lower()
        assert result.confidence == 0.6
        assert result.severity == "warning"
        assert result.data["pesticide_recent"] is True
        assert result.data["habitat_quality"] == "reduced"

    def test_low_flowering(self):
        """flowering < 2, no pesticide → advisory, confidence 0.5, low."""
        m = BeneficialInsectIndex()
        result = m.analyze(None, {"flowering_plants": 1, "pesticide_used_recently": False})
        assert "low flowering" in result.advisory.lower()
        assert "marigolds" in result.advisory.lower()
        assert result.confidence == 0.5
        assert result.severity == "advisory"
        assert result.data["flowering_count"] == 1
        assert result.data["habitat_quality"] == "low"

    def test_extreme_heat_addendum(self):
        """temp > 35 °C with reading → extreme-heat sentence appended."""
        m = BeneficialInsectIndex()
        result = m.analyze(_reading(38.0), {"flowering_plants": 7, "pesticide_used_recently": False})
        assert "extreme heat" in result.advisory.lower()
        assert result.data["temp"] == 38.0
        # The base advisory should still be present.
        assert "excellent" in result.advisory.lower()

    def test_no_data(self):
        """No flowering_plants key in context → insufficient data, confidence 0.0."""
        m = BeneficialInsectIndex()
        result = m.analyze(None, {})
        assert "insufficient" in result.advisory.lower()
        assert result.confidence == 0.0
        assert result.data["flowering_count"] is None
        assert result.data["habitat_quality"] == "no_data"
        assert result.data["temp"] is None

    def test_no_data_still_extracts_temp(self):
        """No flowering_plants but a reading is present → temp still in data."""
        m = BeneficialInsectIndex()
        result = m.analyze(_reading(30.0), {})
        assert "insufficient" in result.advisory.lower()
        assert result.confidence == 0.0
        assert result.data["temp"] == 30.0

    def test_disabled_module_returns_disabled(self):
        """When the module is disabled, process() short-circuits."""
        m = BeneficialInsectIndex()
        m.set_enabled(False)
        result = m.process(_reading(25.0), {"flowering_plants": 6})
        assert "disabled" in result.advisory.lower()
        assert result.confidence == 0.0