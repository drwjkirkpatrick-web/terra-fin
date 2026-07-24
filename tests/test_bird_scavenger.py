"""Tests for the BirdScavengerMonitor adaptation module.

NOTE: These tests cover all four time-of-day windows (dawn, dusk, midday,
night), the no-ripening path, the no-context path, the non-integer-hour edge
case, the disabled-module path, and class-level metadata.
They use sys.path.insert(0, 'src') to import the core package exactly as
pyproject.toml's pythonpath setting would, matching the convention used
by every other test file in this project.

WHY: Birds are a major cause of fruit loss at dawn and dusk. Each time window
must produce the correct advisory, confidence, severity, and bird_activity
label so the orchestrator and dashboard can trust the output without
re-validating it.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from adaptation.bird_scavenger import BirdScavengerMonitor
from core.types import SensorReading, utc_now


def _reading() -> SensorReading:
    """Helper: build a minimal SensorReading (the module is context-driven)."""
    return SensorReading(
        sensor_name="placeholder",
        timestamp=utc_now(),
        metrics={},
        units={},
    )


class TestBirdScavengerMonitor:
    """Tests for the BirdScavengerMonitor adaptation module."""

    def test_class_attributes(self):
        """Module exposes the required class-level metadata."""
        assert BirdScavengerMonitor.name == "bird_scavenger"
        assert BirdScavengerMonitor.category == "animal"
        assert "bird" in BirdScavengerMonitor.description.lower()

    def test_dawn_ripening(self):
        """hour in [6,7,8,9] with crop_ripening → warning, confidence 0.6, high_dawn."""
        m = BirdScavengerMonitor()
        result = m.analyze(_reading(), {"hour": 7, "crop_ripening": True})
        assert result.module_name == "bird_scavenger"
        assert result.category == "animal"
        assert "dawn" in result.advisory.lower()
        assert result.confidence == 0.6
        assert result.severity == "warning"
        assert result.data["hour"] == 7
        assert result.data["crop_ripening"] is True
        assert result.data["bird_activity"] == "high_dawn"

    def test_dusk_ripening(self):
        """hour in [16,17,18] with crop_ripening → warning, confidence 0.6, high_dusk."""
        m = BirdScavengerMonitor()
        result = m.analyze(_reading(), {"hour": 17, "crop_ripening": True})
        assert "dusk" in result.advisory.lower()
        assert result.confidence == 0.6
        assert result.severity == "warning"
        assert result.data["bird_activity"] == "high_dusk"

    def test_midday_ripening(self):
        """hour in [10,11,12,13,14,15] with crop_ripening → info, confidence 0.5, low_midday."""
        m = BirdScavengerMonitor()
        result = m.analyze(_reading(), {"hour": 12, "crop_ripening": True})
        assert "midday" in result.advisory.lower()
        assert result.confidence == 0.5
        assert result.severity == "info"
        assert result.data["bird_activity"] == "low_midday"

    def test_night_ripening(self):
        """hour in [19,20,21,22,23,0,1,2,3,4,5] with crop_ripening → info, confidence 0.6, roosting."""
        m = BirdScavengerMonitor()
        result = m.analyze(_reading(), {"hour": 22, "crop_ripening": True})
        assert "roosting" in result.advisory.lower()
        assert result.confidence == 0.6
        assert result.severity == "info"
        assert result.data["bird_activity"] == "roosting"

    def test_not_ripening(self):
        """crop_ripening False → minimal pressure advisory, info, confidence 0.5."""
        m = BirdScavengerMonitor()
        result = m.analyze(_reading(), {"hour": 7, "crop_ripening": False})
        assert "no ripe crops" in result.advisory.lower()
        assert result.confidence == 0.5
        assert result.severity == "info"
        assert result.data["crop_ripening"] is False
        assert result.data["bird_activity"] == "high_dawn"

    def test_no_context(self):
        """Empty context → insufficient data, confidence 0.0."""
        m = BirdScavengerMonitor()
        result = m.analyze(_reading(), {})
        assert "insufficient data" in result.advisory.lower()
        assert result.confidence == 0.0
        assert result.data["hour"] is None
        assert result.data["crop_ripening"] is None
        assert result.data["bird_activity"] is None

    def test_non_integer_hour(self):
        """Non-integer hour → insufficient data (guard against bad input)."""
        m = BirdScavengerMonitor()
        result = m.analyze(_reading(), {"hour": "seven", "crop_ripening": True})
        assert "insufficient data" in result.advisory.lower()
        assert result.confidence == 0.0

    def test_disabled_module_returns_disabled(self):
        """When the module is disabled, process() short-circuits."""
        m = BirdScavengerMonitor()
        m.set_enabled(False)
        result = m.process(_reading(), {"hour": 7, "crop_ripening": True})
        assert "disabled" in result.advisory.lower()
        assert result.confidence == 0.0