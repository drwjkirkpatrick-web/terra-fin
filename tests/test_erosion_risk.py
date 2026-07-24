"""Tests for the ErosionRisk adaptation module.

NOTE: These tests exercise every decision branch in the erosion-risk
assessment without any hardware. They feed synthetic context dicts with
controlled ``rain_estimate_mm`` and ``slope_percent`` values so the advisory,
confidence, severity, and risk_level are deterministic.

WHY: Erosion directly drives long-term farmland productivity — a missed
high-risk warning on sloped ground can lose an entire topsoil layer in one
storm, while a false alarm wastes labour on contour barriers that were not
needed. The rain and slope thresholds must be pinned at their boundaries so
the farmer is warned at the right moment.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.types import SensorReading, utc_now
from adaptation.erosion_risk import ErosionRisk


def _ctx(rain: float | None, slope: float = 0.0) -> dict:
    """Helper: build a context dict with rainfall and slope.

    Pass ``rain=None`` to omit the ``rain_estimate_mm`` key entirely,
    simulating a no-data scenario.
    """
    ctx: dict = {"slope_percent": float(slope)}
    if rain is not None:
        ctx["rain_estimate_mm"] = float(rain)
    return ctx


class TestErosionRisk:
    """Tests covering all advisory branches, no-data, and edge cases."""

    # ------------------------------------------------------------------ #
    # Advisory branch tests
    # ------------------------------------------------------------------ #

    def test_high_erosion_risk(self):
        """rain > 20 mm and slope > 10 % → warning, confidence 0.7, high."""
        m = ErosionRisk()
        result = m.process(None, _ctx(rain=25.0, slope=15.0))
        assert result.severity == "warning"
        assert result.confidence == 0.7
        assert "high erosion risk" in result.advisory.lower()
        assert result.data["risk_level"] == "high"
        assert result.data["rain_mm"] == 25.0
        assert result.data["slope_percent"] == 15.0

    def test_moderate_erosion_risk(self):
        """rain 10–20 mm and slope > 10 % → advisory, confidence 0.5, moderate."""
        m = ErosionRisk()
        result = m.process(None, _ctx(rain=15.0, slope=12.0))
        assert result.severity == "advisory"
        assert result.confidence == 0.5
        assert "moderate erosion risk" in result.advisory.lower()
        assert result.data["risk_level"] == "moderate"

    def test_heavy_rain_flat_ground(self):
        """rain > 20 mm and slope < 5 % → info, confidence 0.5, low risk."""
        m = ErosionRisk()
        result = m.process(None, _ctx(rain=30.0, slope=2.0))
        assert result.severity == "info"
        assert result.confidence == 0.5
        assert "heavy rain on flat ground" in result.advisory.lower()
        assert "check drainage" in result.advisory.lower()
        assert result.data["risk_level"] == "low"

    def test_low_rain(self):
        """rain < 10 mm → info, confidence 0.6, minimal risk."""
        m = ErosionRisk()
        result = m.process(None, _ctx(rain=5.0, slope=15.0))
        assert result.severity == "info"
        assert result.confidence == 0.6
        assert "low rain" in result.advisory.lower()
        assert result.data["risk_level"] == "minimal"

    # ------------------------------------------------------------------ #
    # No-data test
    # ------------------------------------------------------------------ #

    def test_no_rain_data(self):
        """Missing rain_estimate_mm key → zero-confidence no-data advisory."""
        m = ErosionRisk()
        result = m.process(None, _ctx(rain=None, slope=10.0))
        assert result.confidence == 0.0
        assert result.severity == "info"
        assert "no rainfall data" in result.advisory.lower()
        assert result.data["risk_level"] == "unknown"
        assert result.data["rain_mm"] is None

    # ------------------------------------------------------------------ #
    # Boundary tests
    # ------------------------------------------------------------------ #

    def test_boundary_heavy_rain_exactly_20(self):
        """rain == 20 mm falls in the 10–20 band (moderate), not heavy."""
        m = ErosionRisk()
        # 20 mm on a steep slope → moderate, not high.
        result = m.process(None, _ctx(rain=20.0, slope=15.0))
        assert result.severity == "advisory"
        assert result.data["risk_level"] == "moderate"

    def test_boundary_light_rain_exactly_10(self):
        """rain == 10 mm falls in the 10–20 band (moderate), not low."""
        m = ErosionRisk()
        # 10 mm on a steep slope → moderate, not low.
        result = m.process(None, _ctx(rain=10.0, slope=15.0))
        assert result.severity == "advisory"
        assert result.data["risk_level"] == "moderate"

    # ------------------------------------------------------------------ #
    # Data-dict and identity tests
    # ------------------------------------------------------------------ #

    def test_data_dict_shape(self):
        """Result data must contain rain_mm, slope_percent, and risk_level."""
        m = ErosionRisk()
        result = m.process(None, _ctx(rain=25.0, slope=12.0))
        assert "rain_mm" in result.data
        assert "slope_percent" in result.data
        assert "risk_level" in result.data

    def test_module_identity(self):
        """Module exposes the correct name, category, and description."""
        m = ErosionRisk()
        assert m.name == "erosion_risk"
        assert m.category == "soil"
        assert "erosion" in m.description.lower()

    def test_health_check_after_processing(self):
        """health_check() should reflect processed results."""
        m = ErosionRisk()
        m.process(None, _ctx(rain=25.0, slope=15.0))
        hc = m.health_check()
        assert hc["name"] == "erosion_risk"
        assert hc["category"] == "soil"
        assert hc["enabled"] is True
        assert hc["history_count"] == 1
        assert hc["has_result"] is True