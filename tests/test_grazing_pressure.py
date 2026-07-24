"""Tests for the GrazingPressure adaptation module.

NOTE: These tests cover all four pressure bands (heavy with sparse cover,
moderate with thinning cover, light-to-moderate, minimal), the no-context
path, the non-numeric-input edge case, the disabled-module path, and
class-level metadata.
They use sys.path.insert(0, 'src') to import the core package exactly as
pyproject.toml's pythonpath setting would, matching the convention used
by every other test file in this project.

WHY: Grazing pressure advisories drive rotation decisions. Each band must
produce the correct advisory, confidence, severity, and pressure_level so
the orchestrator and dashboard can trust the output without re-validating it.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from adaptation.grazing_pressure import GrazingPressure
from core.types import SensorReading, utc_now


def _reading() -> SensorReading:
    """Helper: build a minimal SensorReading (the module is context-driven)."""
    return SensorReading(
        sensor_name="placeholder",
        timestamp=utc_now(),
        metrics={},
        units={},
    )


class TestGrazingPressure:
    """Tests for the GrazingPressure adaptation module."""

    def test_class_attributes(self):
        """Module exposes the required class-level metadata."""
        assert GrazingPressure.name == "grazing_pressure"
        assert GrazingPressure.category == "animal"
        assert "grazing" in GrazingPressure.description.lower()

    def test_heavy_grazing_sparse_cover(self):
        """track_density > 0.7 and ground_cover < 30 → warning, confidence 0.6, heavy."""
        m = GrazingPressure()
        result = m.analyze(_reading(), {"gps_track_density": 0.85, "ground_cover_pct": 20})
        assert result.module_name == "grazing_pressure"
        assert result.category == "animal"
        assert "heavy grazing" in result.advisory.lower()
        assert result.confidence == 0.6
        assert result.severity == "warning"
        assert result.data["track_density"] == 0.85
        assert result.data["ground_cover"] == 20.0
        assert result.data["pressure_level"] == "heavy"

    def test_heavy_grazing_thinning_cover(self):
        """track_density > 0.7 and ground_cover 30-60 → advisory, confidence 0.5, moderate."""
        m = GrazingPressure()
        result = m.analyze(_reading(), {"gps_track_density": 0.8, "ground_cover_pct": 45})
        assert "moderate grazing" in result.advisory.lower()
        assert result.confidence == 0.5
        assert result.severity == "advisory"
        assert result.data["pressure_level"] == "moderate"

    def test_heavy_grazing_healthy_cover(self):
        """track_density > 0.7 but ground_cover > 60 still → advisory/moderate (cover holding)."""
        m = GrazingPressure()
        result = m.analyze(_reading(), {"gps_track_density": 0.75, "ground_cover_pct": 75})
        assert result.confidence == 0.5
        assert result.severity == "advisory"
        assert result.data["pressure_level"] == "moderate"

    def test_light_to_moderate(self):
        """track_density in [0.3, 0.7] → info, confidence 0.4, light."""
        m = GrazingPressure()
        result = m.analyze(_reading(), {"gps_track_density": 0.5, "ground_cover_pct": 60})
        assert "light to moderate" in result.advisory.lower()
        assert result.confidence == 0.4
        assert result.severity == "info"
        assert result.data["pressure_level"] == "light"

    def test_minimal_pressure(self):
        """track_density < 0.3 → info, confidence 0.5, minimal."""
        m = GrazingPressure()
        result = m.analyze(_reading(), {"gps_track_density": 0.1, "ground_cover_pct": 90})
        assert "minimal grazing pressure" in result.advisory.lower()
        assert result.confidence == 0.5
        assert result.severity == "info"
        assert result.data["pressure_level"] == "minimal"

    def test_no_context(self):
        """Empty context → no grazing data, confidence 0.0, unknown."""
        m = GrazingPressure()
        result = m.analyze(_reading(), {})
        assert "no grazing data" in result.advisory.lower()
        assert result.confidence == 0.0
        assert result.data["track_density"] is None
        assert result.data["ground_cover"] is None
        assert result.data["pressure_level"] == "unknown"

    def test_non_numeric_input(self):
        """Non-numeric context values → no data result (guard against bad input)."""
        m = GrazingPressure()
        result = m.analyze(
            _reading(),
            {"gps_track_density": "high", "ground_cover_pct": "patchy"},
        )
        assert "no grazing data" in result.advisory.lower()
        assert result.confidence == 0.0
        assert result.data["pressure_level"] == "unknown"

    def test_disabled_module_returns_disabled(self):
        """When the module is disabled, process() short-circuits."""
        m = GrazingPressure()
        m.set_enabled(False)
        result = m.process(_reading(), {"gps_track_density": 0.9, "ground_cover_pct": 10})
        assert "disabled" in result.advisory.lower()
        assert result.confidence == 0.0