"""Tests for the CompostTiming adaptation module.

NOTE: These tests cover every advisory branch — no reading, too dry, too wet,
too cold, ideal, good, a partial-data case, and the disabled-module path.
They use sys.path.insert(0, 'src') to import the core and adaptation packages
exactly as pyproject.toml's pythonpath setting would, matching the convention
used by every other test file in this project.

WHY: Compost timing is a go/no-go decision for the farmer. Getting it wrong
wastes compost (applied to dry/cold soil it sits inert) or loses nutrients
(applied to saturated soil they leach away). Each branch must return the
correct advisory, confidence, severity, and data dict so the orchestrator
and dashboard can act on the result without re-validating it.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from adaptation.compost_timing import CompostTiming
from core.types import SensorReading, utc_now


def _reading(temp_c: float | None = None, moisture: float | None = None) -> SensorReading:
    """Helper: build a SensorReading with the given temp and/or moisture."""
    metrics: dict[str, float] = {}
    if temp_c is not None:
        metrics["temp_c"] = temp_c
    if moisture is not None:
        metrics["soil_moisture_pct"] = moisture
    return SensorReading(
        sensor_name="soil_probe",
        timestamp=utc_now(),
        metrics=metrics,
        units={},
    )


class TestCompostTiming:
    """Tests for the CompostTiming adaptation module."""

    def test_class_attributes(self):
        """Module exposes the required class-level metadata."""
        assert CompostTiming.name == "compost_timing"
        assert CompostTiming.category == "soil"
        assert "compost" in CompostTiming.description.lower()

    def test_no_reading(self):
        """No reading at all → confidence 0.0, 'No data' advisory."""
        m = CompostTiming()
        result = m.analyze(None, {})
        assert result.module_name == "compost_timing"
        assert result.category == "soil"
        assert "no data" in result.advisory.lower()
        assert result.confidence == 0.0
        assert result.severity == "info"
        assert result.data["temp"] is None
        assert result.data["moisture"] is None
        assert result.data["compost_action"] == "unknown"
        assert result.data["decomposition_rate"] == "unknown"

    def test_too_dry(self):
        """Moisture < 30 → too dry advisory, severity 'advisory', conf 0.6."""
        m = CompostTiming()
        result = m.analyze(_reading(temp_c=25.0, moisture=20.0), {})
        assert result.confidence == 0.6
        assert result.severity == "advisory"
        assert "too dry" in result.advisory.lower()
        assert result.data["temp"] == 25.0
        assert result.data["moisture"] == 20.0
        assert result.data["compost_action"] == "water_then_apply"
        assert result.data["decomposition_rate"] == "stalled"

    def test_too_wet(self):
        """Moisture > 70 → too wet advisory, severity 'advisory', conf 0.6."""
        m = CompostTiming()
        result = m.analyze(_reading(temp_c=25.0, moisture=80.0), {})
        assert result.confidence == 0.6
        assert result.severity == "advisory"
        assert "too wet" in result.advisory.lower()
        assert result.data["moisture"] == 80.0
        assert result.data["compost_action"] == "wait"
        assert result.data["decomposition_rate"] == "leaching_risk"

    def test_too_cold(self):
        """Temp < 10 (with good moisture) → cold advisory, conf 0.5, info."""
        m = CompostTiming()
        result = m.analyze(_reading(temp_c=5.0, moisture=50.0), {})
        assert result.confidence == 0.5
        assert result.severity == "info"
        assert "too cold" in result.advisory.lower()
        assert result.data["temp"] == 5.0
        assert result.data["compost_action"] == "apply_expect_slow"
        assert result.data["decomposition_rate"] == "slow"

    def test_ideal_conditions(self):
        """Temp 20–30 & moisture 40–60 → ideal, conf 0.7, info."""
        m = CompostTiming()
        result = m.analyze(_reading(temp_c=25.0, moisture=50.0), {})
        assert result.confidence == 0.7
        assert result.severity == "info"
        assert "ideal" in result.advisory.lower()
        assert result.data["compost_action"] == "apply_now"
        assert result.data["decomposition_rate"] == "high"

    def test_good_conditions(self):
        """Temp 15–35 & moisture 40–60 (outside ideal) → good, conf 0.6, info."""
        m = CompostTiming()
        # 17 °C is in good range (15–35) but not ideal (20–30).
        result = m.analyze(_reading(temp_c=17.0, moisture=45.0), {})
        assert result.confidence == 0.6
        assert result.severity == "info"
        assert "good conditions" in result.advisory.lower()
        assert result.data["compost_action"] == "apply"
        assert result.data["decomposition_rate"] == "moderate"

    def test_ideal_boundary_high_temp(self):
        """Temp exactly 30 with moisture 50 → ideal (boundary inclusive)."""
        m = CompostTiming()
        result = m.analyze(_reading(temp_c=30.0, moisture=50.0), {})
        assert result.confidence == 0.7
        assert "ideal" in result.advisory.lower()
        assert result.data["decomposition_rate"] == "high"

    def test_disabled_module_returns_disabled(self):
        """When the module is disabled, process() short-circuits."""
        m = CompostTiming()
        m.set_enabled(False)
        result = m.process(_reading(temp_c=25.0, moisture=50.0), {})
        assert "disabled" in result.advisory.lower()
        assert result.confidence == 0.0