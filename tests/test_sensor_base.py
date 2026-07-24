"""Tests for sensor base class."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.sensor_base import SensorBase
from core.types import SensorReading


class TestSensor(SensorBase):
    """Test sensor that always returns a known reading."""
    name = "test"
    metrics = ["value"]
    bus_type = "test"
    description = "test sensor"

    def _init_hardware(self) -> bool:
        return False  # always fail → mock mode

    def _read_hardware(self) -> SensorReading | None:
        return None

    def _read_mock(self) -> SensorReading:
        return SensorReading(
            sensor_name="test",
            timestamp="2026-01-01T00:00:00Z",
            metrics={"value": 42.0},
            units={"value": "units"},
            metadata={"source": "mock"},
        )


class FailingSensor(SensorBase):
    """Sensor that raises in _read_hardware."""
    name = "failing"
    metrics = ["x"]
    bus_type = "test"
    description = "failing sensor"

    def _init_hardware(self) -> bool:
        return False

    def _read_hardware(self) -> SensorReading | None:
        raise RuntimeError("hardware error")

    def _read_mock(self) -> SensorReading:
        return SensorReading(
            sensor_name="failing",
            timestamp="2026-01-01T00:00:00Z",
            metrics={"x": 0.0},
            units={"x": "u"},
        )


class TestSensorBase:
    def test_mock_mode(self):
        s = TestSensor(mock_mode=True)
        assert s.initialize() is True
        r = s.read()
        assert r is not None
        assert r.metrics["value"] == 42.0
        assert r.metadata["source"] == "mock"

    def test_hardware_fallback_to_mock(self):
        s = TestSensor(mock_mode=False)
        # _init_hardware returns False → falls back to mock
        assert s.initialize() is False
        assert s._mock_mode is True  # should be flipped to mock
        r = s.read()
        assert r is not None
        assert r.metrics["value"] == 42.0

    def test_read_exception_falls_back_to_mock(self):
        s = FailingSensor(mock_mode=True)
        s.initialize()
        r = s.read()
        # Even in mock mode, _read_mock is used
        assert r is not None
        assert r.metrics["x"] == 0.0

    def test_health_check(self):
        s = TestSensor(mock_mode=True)
        s.initialize()
        s.read()
        hc = s.health_check()
        assert hc["name"] == "test"
        assert hc["bus_type"] == "test"
        assert hc["metrics"] == ["value"]
        assert hc["initialized"] is True
        assert hc["mock_mode"] is True

    def test_is_healthy_after_read(self):
        s = TestSensor(mock_mode=True)
        s.initialize()
        assert s.is_healthy is False
        s.read()
        assert s.is_healthy is True

    def test_cleanup_default(self):
        s = TestSensor(mock_mode=True)
        s.cleanup()  # should not raise

    def test_read_twice(self):
        s = TestSensor(mock_mode=True)
        s.initialize()
        r1 = s.read()
        r2 = s.read()
        assert r1 is not None
        assert r2 is not None
        assert r1.metrics["value"] == 42.0
        assert r2.metrics["value"] == 42.0

    def test_default_mock_returns_zeros(self):
        """Default _read_mock returns zeros for all metrics."""
        class BareSensor(SensorBase):
            name = "bare"
            metrics = ["a", "b"]
            bus_type = "i2c"
            description = "bare"

            def _init_hardware(self) -> bool:
                return False

            def _read_hardware(self) -> SensorReading | None:
                return None

        s = BareSensor(mock_mode=True)
        s.initialize()
        r = s.read()
        assert r is not None
        assert r.metrics["a"] == 0.0
        assert r.metrics["b"] == 0.0