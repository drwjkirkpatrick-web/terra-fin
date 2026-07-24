"""Tests for the LivestockProximity adaptation module.

NOTE: These tests cover all four motion-pattern branches (large_animal, human,
small_animal, none), the missing-context path, the unrecognised-pattern guard,
the disabled-module path, and class-level metadata.
They use sys.path.insert(0, 'src') to import the core package exactly as
pyproject.toml's pythonpath setting would, matching the convention used
by every other test file in this project.

WHY: Livestock and wildlife proximity advisories drive safety and management
decisions at night. Each pattern must produce the correct advisory,
confidence, severity, and proximity_assessment so the orchestrator and
dashboard can trust the output without re-validating it.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from adaptation.livestock_proximity import LivestockProximity
from core.types import SensorReading, utc_now


def _reading() -> SensorReading:
    """Helper: build a minimal SensorReading (the module is context-driven)."""
    return SensorReading(
        sensor_name="placeholder",
        timestamp=utc_now(),
        metrics={},
        units={},
    )


class TestLivestockProximity:
    """Tests for the LivestockProximity adaptation module."""

    def test_class_attributes(self):
        """Module exposes the required class-level metadata."""
        assert LivestockProximity.name == "livestock_proximity"
        assert LivestockProximity.category == "animal"
        assert "livestock" in LivestockProximity.description.lower()

    def test_large_animal(self):
        """motion_pattern 'large_animal' → warning, confidence 0.5."""
        m = LivestockProximity()
        result = m.analyze(
            _reading(),
            {"motion_pattern": "large_animal", "night_motion_count": 3},
        )
        assert result.module_name == "livestock_proximity"
        assert result.category == "animal"
        assert "large animal" in result.advisory.lower()
        assert result.confidence == 0.5
        assert result.severity == "warning"
        assert result.data["pattern"] == "large_animal"
        assert result.data["motion_count"] == 3
        assert result.data["proximity_assessment"] == "Large animal in close proximity"

    def test_human(self):
        """motion_pattern 'human' → advisory, confidence 0.5."""
        m = LivestockProximity()
        result = m.analyze(
            _reading(),
            {"motion_pattern": "human", "night_motion_count": 1},
        )
        assert "human" in result.advisory.lower()
        assert result.confidence == 0.5
        assert result.severity == "advisory"
        assert result.data["pattern"] == "human"
        assert result.data["motion_count"] == 1
        assert result.data["proximity_assessment"] == "Human-sized presence nearby"

    def test_small_animal(self):
        """motion_pattern 'small_animal' → info, confidence 0.4."""
        m = LivestockProximity()
        result = m.analyze(
            _reading(),
            {"motion_pattern": "small_animal", "night_motion_count": 5},
        )
        assert "small animal" in result.advisory.lower()
        assert result.confidence == 0.4
        assert result.severity == "info"
        assert result.data["pattern"] == "small_animal"
        assert result.data["motion_count"] == 5
        assert result.data["proximity_assessment"] == "Small animal nearby"

    def test_none_pattern(self):
        """motion_pattern 'none' → info, confidence 0.5."""
        m = LivestockProximity()
        result = m.analyze(
            _reading(),
            {"motion_pattern": "none", "night_motion_count": 0},
        )
        assert "no significant motion" in result.advisory.lower()
        assert result.confidence == 0.5
        assert result.severity == "info"
        assert result.data["pattern"] == "none"
        assert result.data["motion_count"] == 0
        assert result.data["proximity_assessment"] == "No nearby motion"

    def test_missing_context_defaults_to_none(self):
        """Empty context → defaults to 'none' pattern, info, confidence 0.5."""
        m = LivestockProximity()
        result = m.analyze(_reading(), {})
        assert "no significant motion" in result.advisory.lower()
        assert result.confidence == 0.5
        assert result.severity == "info"
        assert result.data["pattern"] == "none"
        assert result.data["motion_count"] == 0
        assert result.data["proximity_assessment"] == "No nearby motion"

    def test_unrecognised_pattern_defaults_to_none(self):
        """An unknown motion_pattern falls back to 'none' (guard)."""
        m = LivestockProximity()
        result = m.analyze(
            _reading(),
            {"motion_pattern": "vehicle", "night_motion_count": 2},
        )
        assert "no significant motion" in result.advisory.lower()
        assert result.confidence == 0.5
        assert result.severity == "info"
        assert result.data["pattern"] == "none"
        assert result.data["motion_count"] == 2

    def test_none_reading_is_accepted(self):
        """The module is context-driven — reading=None is valid."""
        m = LivestockProximity()
        result = m.analyze(None, {"motion_pattern": "large_animal"})
        assert "large animal" in result.advisory.lower()
        assert result.severity == "warning"
        assert result.data["pattern"] == "large_animal"

    def test_disabled_module_returns_disabled(self):
        """When the module is disabled, process() short-circuits."""
        m = LivestockProximity()
        m.set_enabled(False)
        result = m.process(
            _reading(),
            {"motion_pattern": "large_animal", "night_motion_count": 4},
        )
        assert "disabled" in result.advisory.lower()
        assert result.confidence == 0.0