"""Tests for the EvapotranspirationEstimator adaptation module.

NOTE: These tests cover all four ET classification bands (high, moderate,
low, minimal), the no-reading case, a reading missing required metrics,
and the disabled-module path. They use sys.path.insert(0, 'src') to import
the core and adaptation packages exactly as pyproject.toml's pythonpath
setting would, matching the convention used by every other test file in
this project.

WHY: ET estimation drives irrigation scheduling advisories. Each band
boundary must produce the correct advisory, confidence, severity, and
classification label so the orchestrator and dashboard can trust the
output without re-validating it. The ET values used in these tests were
chosen to fall clearly within each band while exercising the full
temperature/humidity formula.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from adaptation.et_estimator import EvapotranspirationEstimator
from core.types import SensorReading, utc_now


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reading(temp_c: float, humidity_pct: float) -> SensorReading:
    """Build a SensorReading with temp_c and humidity_pct metrics."""
    return SensorReading(
        sensor_name="temp_humidity",
        timestamp=utc_now(),
        metrics={"temp_c": temp_c, "humidity_pct": humidity_pct},
        units={"temp_c": "°C", "humidity_pct": "%"},
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestEvapotranspirationEstimator:
    """Tests for the EvapotranspirationEstimator adaptation module."""

    def test_class_attributes(self):
        """Module exposes the required class-level metadata."""
        assert EvapotranspirationEstimator.name == "et_estimator"
        assert EvapotranspirationEstimator.category == "weather"
        assert "evapotranspiration" in EvapotranspirationEstimator.description.lower()

    def test_high_et_hot_and_dry(self):
        """Hot + dry conditions → ET > 5 mm/day → warning, confidence 0.5.

        temp=50°C, humidity=10%:
            ET = (50-10) * 0.15 * (1 - 0.10) = 40 * 0.15 * 0.90 = 5.4 mm/day
        """
        m = EvapotranspirationEstimator()
        result = m.analyze(_reading(50.0, 10.0), {})
        assert result.module_name == "et_estimator"
        assert result.category == "weather"
        assert result.data["et_mm_day"] == 5.4
        assert "high evapotranspiration" in result.advisory.lower()
        assert "irrigate today" in result.advisory.lower()
        assert result.confidence == 0.5
        assert result.severity == "warning"
        assert result.data["classification"] == "high"
        assert result.data["temp"] == 50.0
        assert result.data["humidity"] == 10.0

    def test_moderate_et(self):
        """Warm + somewhat dry → ET 2–5 mm/day → advisory, confidence 0.5.

        temp=30°C, humidity=20%:
            ET = (30-10) * 0.15 * (1 - 0.20) = 20 * 0.15 * 0.80 = 2.4 mm/day
        """
        m = EvapotranspirationEstimator()
        result = m.analyze(_reading(30.0, 20.0), {})
        assert result.data["et_mm_day"] == 2.4
        assert "moderate water loss" in result.advisory.lower()
        assert "1-2 days" in result.advisory.lower()
        assert result.confidence == 0.5
        assert result.severity == "advisory"
        assert result.data["classification"] == "moderate"

    def test_low_et(self):
        """Mild temp + moderate humidity → ET 0.5–2 mm/day → info, confidence 0.4.

        temp=20°C, humidity=50%:
            ET = (20-10) * 0.15 * (1 - 0.50) = 10 * 0.15 * 0.50 = 0.75 mm/day
        """
        m = EvapotranspirationEstimator()
        result = m.analyze(_reading(20.0, 50.0), {})
        assert result.data["et_mm_day"] == 0.75
        assert "low water loss" in result.advisory.lower()
        assert "normal" in result.advisory.lower()
        assert result.confidence == 0.4
        assert result.severity == "info"
        assert result.data["classification"] == "low"

    def test_minimal_et_cool_and_humid(self):
        """Cool + humid → ET < 0.5 mm/day → info, confidence 0.4.

        temp=12°C, humidity=90%:
            ET = (12-10) * 0.15 * (1 - 0.90) = 2 * 0.15 * 0.10 = 0.03 mm/day
        """
        m = EvapotranspirationEstimator()
        result = m.analyze(_reading(12.0, 90.0), {})
        assert result.data["et_mm_day"] == 0.03
        assert "minimal water loss" in result.advisory.lower()
        assert "no immediate irrigation" in result.advisory.lower()
        assert result.confidence == 0.4
        assert result.severity == "info"
        assert result.data["classification"] == "minimal"

    def test_cold_temp_clamps_to_zero(self):
        """Below 10°C the (temp - 10) term goes negative; clamp to 0 → minimal.

        temp=5°C, humidity=50%:
            ET = max(0, (5-10) * 0.15 * 0.50) = max(0, -0.375) = 0.0 mm/day
        """
        m = EvapotranspirationEstimator()
        result = m.analyze(_reading(5.0, 50.0), {})
        assert result.data["et_mm_day"] == 0.0
        assert result.data["classification"] == "minimal"
        assert result.severity == "info"

    def test_no_reading(self):
        """No reading at all → no-data advisory, confidence 0.0."""
        m = EvapotranspirationEstimator()
        result = m.analyze(None, {})
        assert "no data" in result.advisory.lower()
        assert result.confidence == 0.0
        assert result.data["et_mm_day"] is None
        assert result.data["classification"] == "no_data"

    def test_reading_missing_metrics(self):
        """Reading present but temp_c or humidity_pct absent → treated as no data."""
        m = EvapotranspirationEstimator()
        reading = SensorReading(
            sensor_name="temp_humidity",
            timestamp=utc_now(),
            metrics={"temp_c": 25.0},  # humidity_pct missing
            units={"temp_c": "°C"},
        )
        result = m.analyze(reading, {})
        assert "no data" in result.advisory.lower()
        assert result.confidence == 0.0
        assert result.data["et_mm_day"] is None
        assert result.data["classification"] == "no_data"

    def test_disabled_module_returns_disabled(self):
        """When the module is disabled, process() short-circuits."""
        m = EvapotranspirationEstimator()
        m.set_enabled(False)
        result = m.process(_reading(50.0, 10.0), {})
        assert "disabled" in result.advisory.lower()
        assert result.confidence == 0.0