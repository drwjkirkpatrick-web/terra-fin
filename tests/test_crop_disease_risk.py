"""Tests for the CropDiseaseRisk adaptation module.

NOTE: These tests cover the high-risk (humid + warm), very-high-risk
(humid + prolonged leaf wetness), moderate-risk, low-risk, temperature-
out-of-range, no-reading, and missing-metric paths. They use
sys.path.insert(0, 'src') to import the core package exactly as
pyproject.toml's pythonpath setting would, matching the convention
used by every other test file in this project.

WHY: Fungal disease risk is the single most actionable crop-health
signal a smallholder can receive early. Each band boundary must produce
the correct advisory, confidence, severity, and disease_risk label so
the orchestrator and dashboard can trust the output without re-validating it.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from adaptation.crop_disease_risk import CropDiseaseRisk
from core.types import SensorReading, utc_now


def _reading(humidity: float, temp: float) -> SensorReading:
    """Helper: build a SensorReading with humidity_pct and temp_c."""
    return SensorReading(
        sensor_name="temp_humidity",
        timestamp=utc_now(),
        metrics={"humidity_pct": humidity, "temp_c": temp},
        units={"humidity_pct": "%", "temp_c": "°C"},
    )


class TestCropDiseaseRisk:
    """Tests for the CropDiseaseRisk adaptation module."""

    def test_class_attributes(self):
        """Module exposes the required class-level metadata."""
        assert CropDiseaseRisk.name == "crop_disease_risk"
        assert CropDiseaseRisk.category == "composite"
        assert "disease risk" in CropDiseaseRisk.description.lower()

    def test_high_risk_humid_and_warm(self):
        """humidity > 85 and temp 20–30 → high risk warning, confidence 0.6."""
        m = CropDiseaseRisk()
        result = m.analyze(_reading(90.0, 25.0), {})
        assert result.module_name == "crop_disease_risk"
        assert result.category == "composite"
        assert "fungal disease risk" in result.advisory.lower()
        assert "anthracnose" in result.advisory.lower()
        assert result.confidence == 0.6
        assert result.severity == "warning"
        assert result.data["humidity"] == 90.0
        assert result.data["temp"] == 25.0
        assert result.data["leaf_wetness_hours"] == 0
        assert result.data["disease_risk"] == "high"

    def test_very_high_risk_leaf_wetness(self):
        """humidity > 85 and leaf_wetness_hours > 6 → very high risk warning, 0.7."""
        m = CropDiseaseRisk()
        result = m.analyze(_reading(90.0, 18.0), {"leaf_wetness_hours": 8})
        assert "prolonged leaf wetness" in result.advisory.lower()
        assert "air circulation" in result.advisory.lower()
        assert result.confidence == 0.7
        assert result.severity == "warning"
        assert result.data["leaf_wetness_hours"] == 8
        assert result.data["disease_risk"] == "high"

    def test_moderate_risk(self):
        """humidity 70–85 and temp 20–30 → moderate risk advisory, confidence 0.5."""
        m = CropDiseaseRisk()
        result = m.analyze(_reading(78.0, 25.0), {})
        assert "moderate disease risk" in result.advisory.lower()
        assert "mildew" in result.advisory.lower()
        assert result.confidence == 0.5
        assert result.severity == "advisory"
        assert result.data["disease_risk"] == "moderate"

    def test_low_risk_dry(self):
        """humidity < 70 → low risk info, confidence 0.6."""
        m = CropDiseaseRisk()
        result = m.analyze(_reading(50.0, 25.0), {})
        assert "low fungal disease risk" in result.advisory.lower()
        assert result.confidence == 0.6
        assert result.severity == "info"
        assert result.data["disease_risk"] == "low"

    def test_temp_outside_optimal_range(self):
        """temp < 15 or temp > 35 → info, confidence 0.5."""
        m = CropDiseaseRisk()
        # Cold
        result_cold = m.analyze(_reading(90.0, 10.0), {})
        assert "temperature outside optimal range" in result_cold.advisory.lower()
        assert result_cold.confidence == 0.5
        assert result_cold.severity == "info"
        assert result_cold.data["disease_risk"] == "low"
        # Hot
        result_hot = m.analyze(_reading(90.0, 40.0), {})
        assert "temperature outside optimal range" in result_hot.advisory.lower()
        assert result_hot.confidence == 0.5
        assert result_hot.severity == "info"
        assert result_hot.data["disease_risk"] == "low"

    def test_no_reading(self):
        """No reading at all → no-data advisory, confidence 0.0."""
        m = CropDiseaseRisk()
        result = m.analyze(None, {"leaf_wetness_hours": 3})
        assert "no environmental data" in result.advisory.lower()
        assert result.confidence == 0.0
        assert result.data["humidity"] is None
        assert result.data["temp"] is None
        assert result.data["leaf_wetness_hours"] == 3
        assert result.data["disease_risk"] == "no_data"

    def test_reading_missing_metrics(self):
        """Reading present but temp_c or humidity_pct absent → treated as no data."""
        m = CropDiseaseRisk()
        reading = SensorReading(
            sensor_name="temp_humidity",
            timestamp=utc_now(),
            metrics={"temp_c": 24.0},  # missing humidity_pct
            units={"temp_c": "°C"},
        )
        result = m.analyze(reading, {})
        assert "no environmental data" in result.advisory.lower()
        assert result.confidence == 0.0
        assert result.data["disease_risk"] == "no_data"

    def test_disabled_module_returns_disabled(self):
        """When the module is disabled, process() short-circuits."""
        m = CropDiseaseRisk()
        m.set_enabled(False)
        result = m.process(_reading(90.0, 25.0), {})
        assert "disabled" in result.advisory.lower()
        assert result.confidence == 0.0