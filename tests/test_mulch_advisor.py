"""Tests for the MulchAdvisor adaptation module.

NOTE: These tests exercise every mulch-advisory branch — low moisture, the
temperature-coupled mid-moisture band, high erosion risk (which overrides
moisture), the adequate and wet bands, and the no-data paths — using
synthetic SensorReading objects so behaviour is deterministic without
hardware.

WHY: Mulching decisions interact with moisture, temperature, and erosion
risk simultaneously. A wrong advisory can either leave bare soil exposed to
erosion or trap moisture against fungal disease. Pinning each branch at its
threshold ensures the grower is told to mulch at the right time and told to
*wait* when the soil is already saturated.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.types import SensorReading, utc_now
from adaptation.mulch_advisor import MulchAdvisor


def _reading(moisture: float) -> SensorReading:
    """Helper: build a SensorReading with a single soil_moisture_pct metric."""
    return SensorReading(
        sensor_name="soil_moisture",
        timestamp=utc_now(),
        metrics={"soil_moisture_pct": float(moisture)},
        units={"soil_moisture_pct": "%"},
    )


class TestMulchAdvisor:
    """Tests covering all advisory branches, priority overrides, and edge cases."""

    # ------------------------------------------------------------------
    # Advisory branch tests
    # ------------------------------------------------------------------

    def test_low_moisture_apply_now(self):
        """Moisture below 30 % → advisory, confidence 0.7, 'apply mulch now'."""
        m = MulchAdvisor()
        result = m.process(_reading(20.0), {})
        assert result.severity == "advisory"
        assert result.confidence == 0.7
        assert "apply mulch now" in result.advisory.lower()
        assert result.data["mulch_priority"] == "high"

    def test_mid_moisture_hot_soil(self):
        """Moisture 30–50 % with soil temp > 30 °C → advisory to reduce evaporation."""
        m = MulchAdvisor()
        result = m.process(_reading(40.0), {"soil_temp_c": 35.0})
        assert result.severity == "advisory"
        assert result.confidence == 0.6
        assert "reduce evaporation" in result.advisory.lower()
        assert result.data["mulch_priority"] == "medium"

    def test_mid_moisture_cool_soil(self):
        """Moisture 30–50 % with soil temp ≤ 30 °C → falls through to 'not urgent'."""
        m = MulchAdvisor()
        result = m.process(_reading(40.0), {"soil_temp_c": 25.0})
        # 40 % is ≤ 50 % but temp is not > 30, so the 30–70 % band applies.
        assert result.severity == "info"
        assert result.confidence == 0.4
        assert "not urgent" in result.advisory.lower()
        assert result.data["mulch_priority"] == "low"

    def test_erosion_risk_high_overrides_moisture(self):
        """High erosion risk → warning, regardless of adequate moisture."""
        m = MulchAdvisor()
        result = m.process(_reading(60.0), {"erosion_risk": "high"})
        assert result.severity == "warning"
        assert result.confidence == 0.7
        assert "erosion risk" in result.advisory.lower()
        assert result.data["mulch_priority"] == "high"

    def test_erosion_risk_high_overrides_wet_soil(self):
        """High erosion risk takes priority even when soil is wet (>70 %)."""
        m = MulchAdvisor()
        result = m.process(_reading(80.0), {"erosion_risk": "high"})
        assert result.severity == "warning"
        assert "erosion risk" in result.advisory.lower()

    def test_adequate_moisture_not_urgent(self):
        """Moisture 50–70 % → info, confidence 0.4, 'not urgent'."""
        m = MulchAdvisor()
        result = m.process(_reading(60.0), {})
        assert result.severity == "info"
        assert result.confidence == 0.4
        assert "not urgent" in result.advisory.lower()
        assert result.data["mulch_priority"] == "low"

    def test_wet_soil_delay_mulching(self):
        """Moisture above 70 % → info, confidence 0.5, 'delay mulching'."""
        m = MulchAdvisor()
        result = m.process(_reading(80.0), {})
        assert result.severity == "info"
        assert result.confidence == 0.5
        assert "delay mulching" in result.advisory.lower()
        assert result.data["mulch_priority"] == "low"

    # ------------------------------------------------------------------
    # No-data tests
    # ------------------------------------------------------------------

    def test_no_reading(self):
        """Passing None → zero-confidence info with no-data advisory."""
        m = MulchAdvisor()
        result = m.process(None, {})
        assert result.confidence == 0.0
        assert result.severity == "info"
        assert "no soil data" in result.advisory.lower()
        assert result.data["moisture"] is None
        assert result.data["mulch_priority"] == "unknown"

    def test_missing_metric_treated_as_no_data(self):
        """A reading without soil_moisture_pct → treated as no data."""
        m = MulchAdvisor()
        reading = SensorReading("soil_moisture", utc_now(), {}, {})
        result = m.process(reading, {})
        assert result.confidence == 0.0
        assert "no soil data" in result.advisory.lower()

    # ------------------------------------------------------------------
    # Data-dict and identity tests
    # ------------------------------------------------------------------

    def test_data_dict_shape(self):
        """Result data must contain moisture, soil_temp, erosion_risk, mulch_priority."""
        m = MulchAdvisor()
        result = m.process(
            _reading(45.0),
            {"soil_temp_c": 32.0, "erosion_risk": "moderate"},
        )
        assert "moisture" in result.data
        assert "soil_temp" in result.data
        assert "erosion_risk" in result.data
        assert "mulch_priority" in result.data
        assert result.data["moisture"] == 45.0
        assert result.data["soil_temp"] == 32.0
        assert result.data["erosion_risk"] == "moderate"

    def test_module_identity(self):
        """Module exposes the correct name, category, and description."""
        m = MulchAdvisor()
        assert m.name == "mulch_advisor"
        assert m.category == "soil"
        assert "mulch" in m.description.lower()

    def test_health_check_after_processing(self):
        """health_check() should reflect processed results."""
        m = MulchAdvisor()
        m.process(_reading(20.0), {})
        hc = m.health_check()
        assert hc["name"] == "mulch_advisor"
        assert hc["category"] == "soil"
        assert hc["enabled"] is True
        assert hc["history_count"] == 1
        assert hc["has_result"] is True