"""Tests for the engine."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import math
from core.engine import Engine
from core.config import MainConfig
from core.sensor_base import SensorBase
from core.types import SensorReading, utc_now


class MockSensor(SensorBase):
    """Configurable mock sensor for testing."""
    name = "mock"
    metrics = ["value"]
    bus_type = "test"
    description = "mock"

    def __init__(self, name="mock", metrics=None, values=None, mock_mode=True):
        self.name = name
        self.metrics = metrics or ["value"]
        self._values = values or [1.0, 2.0, 3.0]
        self._idx = 0
        super().__init__(mock_mode=mock_mode)

    def _init_hardware(self):
        return False

    def _read_hardware(self):
        return None

    def _read_mock(self):
        val = self._values[self._idx % len(self._values)]
        self._idx += 1
        return SensorReading(
            sensor_name=self.name,
            timestamp=utc_now(),
            metrics={m: val for m in self.metrics},
            units={m: "unit" for m in self.metrics},
            metadata={"source": "mock"},
        )


class MockLightSensor(SensorBase):
    name = "light"
    metrics = ["light_lux"]
    bus_type = "adc"
    description = "mock light"

    def __init__(self, lux=50000.0, mock_mode=True):
        self._lux = lux
        super().__init__(mock_mode=mock_mode)

    def _init_hardware(self):
        return False

    def _read_hardware(self):
        return None

    def _read_mock(self):
        return SensorReading(
            sensor_name="light", timestamp=utc_now(),
            metrics={"light_lux": self._lux}, units={"light_lux": "lux"},
            metadata={"source": "mock"},
        )


class MockIMUSensor(SensorBase):
    name = "imu"
    metrics = ["accel_x", "accel_y", "accel_z"]
    bus_type = "i2c"
    description = "mock imu"

    def __init__(self, moving=False, mock_mode=True):
        self._moving = moving
        super().__init__(mock_mode=mock_mode)

    def _init_hardware(self):
        return False

    def _read_hardware(self):
        return None

    def _read_mock(self):
        x = 5.0 if self._moving else 0.0
        return SensorReading(
            sensor_name="imu", timestamp=utc_now(),
            metrics={"accel_x": x, "accel_y": 0.0, "accel_z": 9.81},
            units={"accel_x": "m/s2", "accel_y": "m/s2", "accel_z": "m/s2"},
        )


class MockGPSSensor(SensorBase):
    name = "gps"
    metrics = ["lat", "lon", "altitude_m"]
    bus_type = "serial"
    description = "mock gps"

    def __init__(self, mock_mode=True):
        super().__init__(mock_mode=mock_mode)

    def _init_hardware(self):
        return False

    def _read_hardware(self):
        return None

    def _read_mock(self):
        return SensorReading(
            sensor_name="gps", timestamp=utc_now(),
            metrics={"lat": -1.2864, "lon": 36.8222, "altitude_m": 1795.0},
            units={"lat": "deg", "lon": "deg", "altitude_m": "m"},
        )


class TestEngine:
    def test_read_all(self):
        sensors = {"mock": MockSensor()}
        e = Engine(MainConfig(), sensors)
        results = e.read_all()
        assert "mock" in results
        assert results["mock"] is not None

    def test_get_summary(self):
        sensors = {
            "light": MockLightSensor(lux=50000.0),
            "imu": MockIMUSensor(moving=False),
            "gps": MockGPSSensor(),
        }
        e = Engine(MainConfig(), sensors)
        summary = e.get_summary()
        assert "timestamp" in summary
        assert "sensors" in summary
        assert "cross_sensor" in summary
        assert summary["cross_sensor"]["is_day"] is True
        assert summary["cross_sensor"]["is_moving"] is False
        assert summary["cross_sensor"]["lat"] == -1.2864

    def test_get_summary_night(self):
        sensors = {"light": MockLightSensor(lux=5.0)}
        e = Engine(MainConfig(), sensors)
        summary = e.get_summary()
        assert summary["cross_sensor"]["is_day"] is False

    def test_get_summary_moving(self):
        sensors = {"imu": MockIMUSensor(moving=True)}
        e = Engine(MainConfig(), sensors)
        summary = e.get_summary()
        assert summary["cross_sensor"]["is_moving"] is True

    def test_get_trends(self):
        sensors = {"mock": MockSensor()}
        e = Engine(MainConfig(), sensors)
        # Read a few times to build history
        e.read_all()
        e.read_all()
        e.read_all()
        trends = e.get_trends(window_minutes=60)
        assert "mock" in trends
        assert trends["mock"]["count"] == 3

    def test_get_baselines(self):
        sensors = {"mock": MockSensor(values=[10.0, 20.0, 30.0])}
        e = Engine(MainConfig(), sensors)
        e.read_all()
        e.read_all()
        e.read_all()
        e.update_baselines()
        baselines = e.get_baselines()
        assert "mock.value" in baselines

    def test_history_limit(self):
        sensors = {"mock": MockSensor()}
        e = Engine(MainConfig(), sensors)
        # Read many times
        for _ in range(400):
            e.read_all()
        # Should not exceed max history
        assert len(e._history["mock"]) <= 360

    def test_empty_sensors(self):
        e = Engine(MainConfig(), {})
        summary = e.get_summary()
        assert summary["sensors"] == {}

    def test_haversine(self):
        d = Engine._haversine(-1.2864, 36.8222, -1.2865, 36.8223)
        assert 0.0 < d < 0.1  # very close points

    def test_read_failure_handled(self):
        class FailSensor(SensorBase):
            name = "fail"
            metrics = ["x"]
            bus_type = "test"
            description = "fail"

            def _init_hardware(self):
                return False

            def _read_hardware(self):
                return None

            def _read_mock(self):
                raise RuntimeError("boom")

        sensors = {"fail": FailSensor(mock_mode=True)}
        e = Engine(MainConfig(), sensors)
        results = e.read_all()
        # Should not raise, should return None
        assert results["fail"] is None