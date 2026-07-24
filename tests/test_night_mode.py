"""Tests for night mode sentinel."""

import sys
import os
import time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.types import NightEvent, utc_now
from core.config import NightModeConfig, MainConfig
from core.event_bus import EventBus
from core.recorder import Recorder
from modules.night_mode import NightModeSentinel
from core.sensor_base import SensorBase
from core.types import SensorReading


class MockLightSensor(SensorBase):
    name = "light"
    metrics = ["light_lux"]
    bus_type = "adc"
    description = "mock light"

    def __init__(self, lux=5.0):
        self._lux = lux
        super().__init__(mock_mode=True)

    def _init_hardware(self):
        return False

    def _read_hardware(self):
        return None

    def _read_mock(self):
        return SensorReading(
            sensor_name="light", timestamp=utc_now(),
            metrics={"light_lux": self._lux}, units={"light_lux": "lux"},
        )


class MockIMU(SensorBase):
    name = "imu"
    metrics = ["accel_x", "accel_y", "accel_z"]
    bus_type = "i2c"
    description = "mock"

    def __init__(self, motion_delta=0.0):
        self._motion_delta = motion_delta
        super().__init__(mock_mode=True)

    def _init_hardware(self):
        return False

    def _read_hardware(self):
        return None

    def _read_mock(self):
        return SensorReading(
            sensor_name="imu", timestamp=utc_now(),
            metrics={"accel_x": self._motion_delta, "accel_y": 0.0, "accel_z": 9.81},
            units={"accel_x": "m/s2", "accel_y": "m/s2", "accel_z": "m/s2"},
        )


class MockGPS(SensorBase):
    name = "gps"
    metrics = ["lat", "lon", "altitude_m"]
    bus_type = "serial"
    description = "mock"

    def __init__(self):
        super().__init__(mock_mode=True)

    def _init_hardware(self):
        return False

    def _read_hardware(self):
        return None

    def _read_mock(self):
        return SensorReading(
            sensor_name="gps", timestamp=utc_now(),
            metrics={"lat": -1.0, "lon": 36.0, "altitude_m": 1800.0},
            units={"lat": "deg", "lon": "deg", "altitude_m": "m"},
            metadata={"fix_quality": "simulated"},
        )


class TestClassifyMotion:
    def test_none(self):
        assert NightModeSentinel.classify_motion(0.1) == "none"

    def test_small_animal(self):
        assert NightModeSentinel.classify_motion(0.5) == "small_animal"

    def test_human(self):
        assert NightModeSentinel.classify_motion(1.5) == "human"

    def test_large_animal(self):
        assert NightModeSentinel.classify_motion(5.0) == "large_animal"

    def test_boundary_none(self):
        assert NightModeSentinel.classify_motion(0.29) == "none"

    def test_boundary_small_animal(self):
        assert NightModeSentinel.classify_motion(0.3) == "small_animal"


class TestNightMode:
    def test_start_stop(self):
        cfg = NightModeConfig(poll_interval_s=0.1)
        bus = EventBus()
        rec = Recorder(":memory:")
        rec.init_db()
        sensors = {"light": MockLightSensor(lux=50000.0)}  # daytime
        nm = NightModeSentinel(cfg, sensors, bus, rec)
        nm.start()
        time.sleep(0.3)
        assert nm.is_active() is False  # daytime, not active
        nm.stop()

    def test_night_detection(self):
        cfg = NightModeConfig(poll_interval_s=0.1)
        bus = EventBus()
        rec = Recorder(":memory:")
        rec.init_db()
        sensors = {"light": MockLightSensor(lux=5.0)}  # night
        nm = NightModeSentinel(cfg, sensors, bus, rec)
        nm.start()
        time.sleep(0.3)
        assert nm.is_active() is True
        nm.stop()

    def test_motion_alert_emitted(self):
        cfg = NightModeConfig(poll_interval_s=0.1, motion_alert_threshold=0.3)
        bus = EventBus()
        rec = Recorder(":memory:")
        rec.init_db()
        alerts = []
        bus.subscribe("NIGHT_ALERT", lambda d: alerts.append(d))
        sensors = {
            "light": MockLightSensor(lux=5.0),
            "imu": MockIMU(motion_delta=5.0),  # above threshold
        }
        nm = NightModeSentinel(cfg, sensors, bus, rec)
        nm.start()
        time.sleep(0.5)
        nm.stop()
        assert len(alerts) > 0
        assert "motion" in alerts[0]["event_type"]

    def test_motion_recorded(self):
        cfg = NightModeConfig(poll_interval_s=0.1, motion_alert_threshold=0.3)
        bus = EventBus()
        rec = Recorder(":memory:")
        rec.init_db()
        sensors = {
            "light": MockLightSensor(lux=5.0),
            "imu": MockIMU(motion_delta=5.0),
        }
        nm = NightModeSentinel(cfg, sensors, bus, rec)
        nm.start()
        time.sleep(0.5)
        nm.stop()
        events = nm.get_events()
        assert len(events) > 0
        assert events[0].event_type == "motion"
        # Also recorded in database
        db_events = rec.query_night_events()
        assert len(db_events) > 0

    def test_gps_recorded(self):
        cfg = NightModeConfig(poll_interval_s=0.1)
        bus = EventBus()
        rec = Recorder(":memory:")
        rec.init_db()
        sensors = {
            "light": MockLightSensor(lux=5.0),
            "gps": MockGPS(),
        }
        nm = NightModeSentinel(cfg, sensors, bus, rec)
        nm.start()
        time.sleep(0.5)
        nm.stop()
        gps_points = rec.query_gps_track()
        assert len(gps_points) > 0

    def test_no_motion_no_alert(self):
        cfg = NightModeConfig(poll_interval_s=0.1, motion_alert_threshold=0.5)
        bus = EventBus()
        rec = Recorder(":memory:")
        rec.init_db()
        alerts = []
        bus.subscribe("NIGHT_ALERT", lambda d: alerts.append(d))
        sensors = {
            "light": MockLightSensor(lux=5.0),
            "imu": MockIMU(motion_delta=0.1),  # below threshold
        }
        nm = NightModeSentinel(cfg, sensors, bus, rec)
        nm.start()
        time.sleep(0.5)
        nm.stop()
        assert len(alerts) == 0

    def test_double_start_protection(self):
        cfg = NightModeConfig(poll_interval_s=1.0)
        bus = EventBus()
        rec = Recorder(":memory:")
        rec.init_db()
        sensors = {"light": MockLightSensor(lux=5.0)}
        nm = NightModeSentinel(cfg, sensors, bus, rec)
        nm.start()
        nm.start()  # should not start a second thread
        nm.stop()

    def test_stop_without_start(self):
        cfg = NightModeConfig()
        bus = EventBus()
        rec = Recorder(":memory:")
        rec.init_db()
        sensors = {}
        nm = NightModeSentinel(cfg, sensors, bus, rec)
        nm.stop()  # should not raise

    def test_get_events_empty(self):
        cfg = NightModeConfig()
        bus = EventBus()
        rec = Recorder(":memory:")
        rec.init_db()
        nm = NightModeSentinel(cfg, {}, bus, rec)
        assert nm.get_events() == []

    def test_recorder_closed_cleanly(self):
        cfg = NightModeConfig(poll_interval_s=0.1)
        bus = EventBus()
        rec = Recorder(":memory:")
        rec.init_db()
        sensors = {"light": MockLightSensor(lux=5.0)}
        nm = NightModeSentinel(cfg, sensors, bus, rec)
        nm.start()
        time.sleep(0.2)
        nm.stop()
        rec.close()  # should not raise