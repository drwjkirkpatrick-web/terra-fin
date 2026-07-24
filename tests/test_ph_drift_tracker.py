"""Tests for the PHDriftTracker adaptation module.

NOTE: These tests exercise every decision branch in PHDriftTracker.analyze —
acidifying drift (current pH well below the window average), alkalinizing
drift (current pH well above the window average), stable pH (current within
the +/-0.1 band of the average), the insufficient-readings cold-start path,
the no-reading path, the disabled-module path via process(), and the
data-dict contract. All tests feed mock SensorReadings in sequence so the
internal rolling window builds up deterministically.

WHY: pH drift advisories drive amendment recommendations — lime to raise pH,
sulphur to lower it — that cost the farmer money and take weeks to act. Each
branch must produce the exact advisory text, confidence, severity, and data
dict the spec requires so downstream consumers (CLI, dashboard, prompts) can
trust the result without re-checking the numbers.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.adaptation_base import AdaptationResult
from core.types import SensorReading, utc_now
from adaptation.ph_drift_tracker import PHDriftTracker


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _reading(ph: float) -> SensorReading:
    """Build a soil_ph SensorReading with the given pH value."""
    return SensorReading(
        sensor_name="soil_ph",
        timestamp=utc_now(),
        metrics={"soil_pH": ph},
        units={"soil_pH": "pH"},
    )


def _feed(module: PHDriftTracker, values: list[float]) -> AdaptationResult:
    """Feed a sequence of pH values to the module and return the last result."""
    result = AdaptationResult(
        module_name=module.name,
        category=module.category,
        timestamp=utc_now(),
        advisory="",
        confidence=0.0,
        data={},
    )
    for v in values:
        result = module.analyze(_reading(v), {})
    return result


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #

class TestPHDriftTrackerAttributes:
    def test_class_attributes(self):
        """Class attributes must match the AdaptationModule contract."""
        assert PHDriftTracker.name == "ph_drift_tracker"
        assert PHDriftTracker.category == "soil"
        assert "pH" in PHDriftTracker.description
        assert "acidification" in PHDriftTracker.description.lower() or \
               "alkalinization" in PHDriftTracker.description.lower()


class TestPHDriftTrackerAnalysis:
    def test_acidifying_drift(self):
        """A sequence trending downward → acidifying advisory, conf 0.7, warning."""
        m = PHDriftTracker()
        result = _feed(m, [6.5, 6.4, 6.3, 6.2, 6.1, 6.0])

        assert result.advisory == (
            "Soil pH is drifting acidic - consider lime application to raise pH."
        )
        assert result.confidence == 0.7
        assert result.severity == "warning"
        assert result.data["drift_direction"] == "acidifying"
        assert result.data["current_pH"] == 6.0
        # avg of [6.5,6.4,6.3,6.2,6.1,6.0] = 6.25; drift = 6.0 - 6.25 = -0.25
        assert result.data["avg_pH"] == 6.25
        assert result.data["drift_rate"] == -0.25

    def test_alkalinizing_drift(self):
        """A sequence trending upward → alkalinizing advisory, conf 0.7, warning."""
        m = PHDriftTracker()
        result = _feed(m, [6.0, 6.1, 6.2, 6.3, 6.4, 6.5])

        assert result.advisory == (
            "Soil pH is drifting alkaline - consider sulfur or acidifying amendments."
        )
        assert result.confidence == 0.7
        assert result.severity == "warning"
        assert result.data["drift_direction"] == "alkalinizing"
        assert result.data["current_pH"] == 6.5
        assert result.data["avg_pH"] == 6.25
        assert result.data["drift_rate"] == 0.25

    def test_stable_ph(self):
        """A flat sequence → stable advisory, conf 0.6, info."""
        m = PHDriftTracker()
        result = _feed(m, [6.5, 6.5, 6.5, 6.5, 6.5])

        assert result.advisory == "Soil pH stable at 6.5."
        assert result.confidence == 0.6
        assert result.severity == "info"
        assert result.data["drift_direction"] == "stable"
        assert result.data["current_pH"] == 6.5
        assert result.data["avg_pH"] == 6.5
        assert result.data["drift_rate"] == 0.0

    def test_insufficient_readings(self):
        """Fewer than 5 readings → baseline advisory, conf 0.2, info."""
        m = PHDriftTracker()
        result = _feed(m, [6.4, 6.5])  # only 2 readings

        assert result.advisory == (
            "Collecting pH baseline - need more readings for drift analysis."
        )
        assert result.confidence == 0.2
        assert result.severity == "info"
        assert result.data["drift_direction"] == "insufficient"
        assert result.data["current_pH"] == 6.5
        assert result.data["avg_pH"] == 6.45
        assert result.data["drift_rate"] == 0.0

    def test_no_reading(self):
        """No reading at all → no-data advisory, confidence 0.0."""
        m = PHDriftTracker()
        result = m.analyze(None, {})

        assert result.advisory == "No pH data for drift tracking."
        assert result.confidence == 0.0
        assert result.severity == "info"
        assert result.data["drift_direction"] == "no_data"
        assert result.data["current_pH"] is None

    def test_reading_missing_soil_ph_metric(self):
        """Reading present but missing soil_pH metric → no-data advisory."""
        m = PHDriftTracker()
        reading = SensorReading(
            sensor_name="soil_ph",
            timestamp=utc_now(),
            metrics={"temp_c": 21.0},  # no soil_pH
            units={"temp_c": "°C"},
        )
        result = m.analyze(reading, {})

        assert result.advisory == "No pH data for drift tracking."
        assert result.confidence == 0.0
        assert result.data["drift_direction"] == "no_data"


class TestPHDriftTrackerProcessAndData:
    def test_disabled_module(self):
        """A disabled module returns a 'Module disabled' advisory via process()."""
        m = PHDriftTracker()
        m.set_enabled(False)
        result = m.process(None, {})

        assert "disabled" in result.advisory.lower()
        assert result.confidence == 0.0

    def test_data_dict_contract(self):
        """The data dict must always contain current_pH, avg_pH, drift_rate,
        drift_direction — verified on a full acidifying run."""
        m = PHDriftTracker()
        result = _feed(m, [6.8, 6.6, 6.4, 6.2, 6.0, 5.8])

        assert "current_pH" in result.data
        assert "avg_pH" in result.data
        assert "drift_rate" in result.data
        assert "drift_direction" in result.data
        assert result.data["current_pH"] == 5.8
        assert result.data["drift_direction"] == "acidifying"