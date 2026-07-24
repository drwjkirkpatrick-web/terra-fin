"""Tests for the RodentActivity adaptation module.

NOTE: These tests cover all four motion-count bands (high, moderate, low,
none), the harvest-season note, the no-context path, the non-integer motion
count edge case, the disabled-module path, and class-level metadata.
They use sys.path.insert(0, 'src') to import the core package exactly as
pyproject.toml's pythonpath setting would, matching the convention used
by every other test file in this project.

WHY: Rodents are a major cause of stored-harvest loss and equipment damage
in orchards. Each motion-count band must produce the correct advisory,
confidence, severity, and activity_level label so the orchestrator and
dashboard can trust the output without re-validating it. The harvest-season
note must fire only during September–November when motion_count > 3.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from adaptation.rodent_activity import RodentActivity
from core.types import SensorReading, utc_now


def _reading() -> SensorReading:
    """Helper: build a minimal SensorReading (the module is context-driven)."""
    return SensorReading(
        sensor_name="placeholder",
        timestamp=utc_now(),
        metrics={},
        units={},
    )


class TestRodentActivity:
    """Tests for the RodentActivity adaptation module."""

    def test_class_attributes(self):
        """Module exposes the required class-level metadata."""
        assert RodentActivity.name == "rodent_activity"
        assert RodentActivity.category == "animal"
        assert "rodent" in RodentActivity.description.lower()

    def test_high_activity(self):
        """motion_count > 10 → warning, confidence 0.5, activity_level 'high'."""
        m = RodentActivity()
        result = m.analyze(_reading(), {"night_motion_count": 15, "month": 6})
        assert result.module_name == "rodent_activity"
        assert result.category == "animal"
        assert "high rodent activity" in result.advisory.lower()
        assert result.confidence == 0.5
        assert result.severity == "warning"
        assert result.data["motion_count"] == 15
        assert result.data["month"] == 6
        assert result.data["activity_level"] == "high"

    def test_moderate_activity(self):
        """motion_count 5-10 → advisory, confidence 0.4, activity_level 'moderate'."""
        m = RodentActivity()
        result = m.analyze(_reading(), {"night_motion_count": 7, "month": 3})
        assert "moderate rodent activity" in result.advisory.lower()
        assert result.confidence == 0.4
        assert result.severity == "advisory"
        assert result.data["activity_level"] == "moderate"

    def test_low_activity(self):
        """motion_count 1-4 → info, confidence 0.4, activity_level 'low'."""
        m = RodentActivity()
        result = m.analyze(_reading(), {"night_motion_count": 3, "month": 4})
        assert "low rodent activity" in result.advisory.lower()
        assert result.confidence == 0.4
        assert result.severity == "info"
        assert result.data["activity_level"] == "low"

    def test_no_activity(self):
        """motion_count 0 → info, confidence 0.5, activity_level 'none'."""
        m = RodentActivity()
        result = m.analyze(_reading(), {"night_motion_count": 0, "month": 1})
        assert "no rodent activity" in result.advisory.lower()
        assert result.confidence == 0.5
        assert result.severity == "info"
        assert result.data["activity_level"] == "none"

    def test_harvest_season_note(self):
        """month in [9,10,11] with motion_count > 3 appends harvest-season note."""
        m = RodentActivity()
        result = m.analyze(_reading(), {"night_motion_count": 5, "month": 10})
        assert "harvest season" in result.advisory.lower()
        assert result.data["month"] == 10

    def test_no_harvest_note_outside_season(self):
        """month not in [9,10,11] does not append harvest-season note."""
        m = RodentActivity()
        result = m.analyze(_reading(), {"night_motion_count": 15, "month": 6})
        assert "harvest season" not in result.advisory.lower()

    def test_no_context(self):
        """Empty context → insufficient data, confidence 0.0."""
        m = RodentActivity()
        result = m.analyze(_reading(), {})
        assert "no motion data" in result.advisory.lower()
        assert result.confidence == 0.0
        assert result.data["motion_count"] is None
        assert result.data["month"] is None
        assert result.data["activity_level"] == "no_data"

    def test_non_integer_motion_count(self):
        """Non-integer motion_count → insufficient data (guard against bad input)."""
        m = RodentActivity()
        result = m.analyze(_reading(), {"night_motion_count": "many", "month": 6})
        assert "no motion data" in result.advisory.lower()
        assert result.confidence == 0.0

    def test_disabled_module_returns_disabled(self):
        """When the module is disabled, process() short-circuits."""
        m = RodentActivity()
        m.set_enabled(False)
        result = m.process(_reading(), {"night_motion_count": 15, "month": 6})
        assert "disabled" in result.advisory.lower()
        assert result.confidence == 0.0