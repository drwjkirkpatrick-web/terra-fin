"""Tests for the WindEstimator adaptation module."""

import sys
import os
import math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.adaptation_base import AdaptationResult
from core.types import SensorReading, utc_now
from adaptation.wind_estimator import WindEstimator


def _imu_reading(accel_x: float, accel_y: float) -> SensorReading:
    """Build a minimal IMU-style SensorReading."""
    return SensorReading(
        sensor_name="imu",
        timestamp=utc_now(),
        metrics={"accel_x": accel_x, "accel_y": accel_y},
        units={"accel_x": "m/s^2", "accel_y": "m/s^2"},
        metadata={},
    )


class TestWindEstimatorMetadata:
    def test_class_attrs(self):
        m = WindEstimator()
        assert m.name == "wind_estimator"
        assert m.category == "weather"
        assert "stick sway" in m.description.lower()


class TestWindEstimatorStrong:
    def test_strong_sway(self):
        m = WindEstimator()
        # accel_x=2, accel_y=2 => sway = sqrt(8) ≈ 2.83... bump to exceed 3.0
        reading = _imu_reading(2.5, 2.0)  # sqrt(6.25+4)=sqrt(10.25)≈3.2
        result = m.process(reading, {})
        assert result.advisory.startswith("Strong wind detected")
        assert result.confidence == 0.6
        assert result.severity == "warning"
        assert result.data["wind_estimate"] == "strong"
        assert result.data["sway_magnitude"] > 3.0

    def test_strong_boundary(self):
        # Just above threshold
        m = WindEstimator()
        reading = _imu_reading(3.1, 0.0)  # sway = 3.1
        result = m.process(reading, {})
        assert result.data["wind_estimate"] == "strong"
        assert result.severity == "warning"


class TestWindEstimatorModerate:
    def test_moderate_sway(self):
        m = WindEstimator()
        reading = _imu_reading(1.5, 0.0)  # sway = 1.5
        result = m.process(reading, {})
        assert "Moderate wind" in result.advisory
        assert result.confidence == 0.5
        assert result.severity == "info"
        assert result.data["wind_estimate"] == "moderate"
        assert 1.0 <= result.data["sway_magnitude"] <= 3.0

    def test_moderate_boundary_low(self):
        m = WindEstimator()
        reading = _imu_reading(1.0, 0.0)  # sway = 1.0 exactly
        result = m.process(reading, {})
        assert result.data["wind_estimate"] == "moderate"


class TestWindEstimatorCalm:
    def test_calm_sway(self):
        m = WindEstimator()
        reading = _imu_reading(0.3, 0.4)  # sway = 0.5
        result = m.process(reading, {})
        assert "Calm conditions" in result.advisory
        assert result.confidence == 0.4
        assert result.severity == "info"
        assert result.data["wind_estimate"] == "calm"
        assert result.data["sway_magnitude"] < 1.0


class TestWindEstimatorNoData:
    def test_none_reading(self):
        m = WindEstimator()
        result = m.process(None, {})
        assert "No motion data" in result.advisory
        assert result.confidence == 0.0
        assert result.severity == "info"
        assert result.data == {}

    def test_missing_accel(self):
        m = WindEstimator()
        reading = SensorReading(
            sensor_name="imu",
            timestamp=utc_now(),
            metrics={"temp": 20.0},  # no accel_x/accel_y
            units={},
        )
        result = m.process(reading, {})
        assert "No motion data" in result.advisory
        assert result.confidence == 0.0


class TestWindEstimatorDisabled:
    def test_disabled_returns_disabled_advisory(self):
        m = WindEstimator()
        m.set_enabled(False)
        reading = _imu_reading(5.0, 5.0)  # would normally be strong wind
        result = m.process(reading, {})
        assert "disabled" in result.advisory.lower()
        assert result.confidence == 0.0
        assert result.data == {}


class TestWindEstimatorSwayMagnitude:
    def test_sway_magnitude_is_pythagorean(self):
        m = WindEstimator()
        reading = _imu_reading(3.0, 4.0)  # classic 3-4-5
        result = m.process(reading, {})
        assert math.isclose(result.data["sway_magnitude"], 5.0, rel_tol=1e-9)