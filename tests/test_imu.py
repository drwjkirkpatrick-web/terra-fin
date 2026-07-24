"""Tests for the IMU (MPU-6050) sensor driver.

NOTE: These tests exercise the mock path only — no hardware is required.
They cover the SensorBase contract shape (class attributes, health check),
the 3-axis mock read (Z near gravity), the is_moving() threshold, every
branch of get_orientation() (upright / inverted / tilted / flat),
cleanup, and repeated reads. Uses sys.path.insert(0, 'src') to import
the core package exactly as pyproject.toml's pythonpath setting would.

WHY: The IMU's derived state (is_moving, get_orientation) drives
night-mode motion alerts and fall/drop detection, so the thresholds and
orientation logic must be pinned. The mock baselines pin Z near 9.81 so
a fresh mock stick reads "stationary" and "upright" by construction,
which lets us assert the contract holds without any hardware.
"""

import math
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.config import IMUConfig
from core.types import SensorReading
from sensors.imu import IMUSensor, _GRAVITY


class TestIMUSensor:
    def setup_method(self):
        """Fresh sensor in mock mode for every test."""
        cfg = IMUConfig(mock_mode=True)
        self.sensor = IMUSensor(config=cfg, mock_mode=True)
        assert self.sensor.initialize() is True

    # -- class attributes / shape --------------------------------------

    def test_class_attributes(self):
        """Class attrs must match the SensorBase contract for dashboard use."""
        assert IMUSensor.name == "imu"
        assert IMUSensor.bus_type == "i2c"
        assert IMUSensor.metrics == ["accel_x", "accel_y", "accel_z"]
        assert "MPU-6050" in IMUSensor.description

    def test_health_check_shape(self):
        """health_check() must report the configured sensor identity."""
        self.sensor.read()
        hc = self.sensor.health_check()
        assert hc["name"] == "imu"
        assert hc["bus_type"] == "i2c"
        assert hc["metrics"] == ["accel_x", "accel_y", "accel_z"]
        assert hc["initialized"] is True
        assert hc["mock_mode"] is True
        assert hc["healthy"] is True

    # -- mock read ------------------------------------------------------

    def test_mock_read_returns_reading(self):
        """A mock read returns a SensorReading with all 3 accel axes."""
        r = self.sensor.read()
        assert r is not None
        assert isinstance(r, SensorReading)
        assert r.sensor_name == "imu"
        assert "accel_x" in r.metrics
        assert "accel_y" in r.metrics
        assert "accel_z" in r.metrics
        assert r.units["accel_x"] == "m/s^2"
        assert r.metadata["source"] == "mock"

    def test_mock_z_near_gravity(self):
        """Mock Z must stay near 9.81 m/s^2 (stick held vertical).

        NOTE: This is the key contract for is_moving()/get_orientation() —
        a stationary mock stick must read near gravity on Z.
        """
        for _ in range(10):
            r = self.sensor.read()
            assert r is not None
            assert abs(r.metrics["accel_z"] - _GRAVITY) < 3.0, (
                f"Z {r.metrics['accel_z']} not near gravity {_GRAVITY}"
            )

    def test_read_twice(self):
        """Two consecutive reads should both succeed."""
        r1 = self.sensor.read()
        r2 = self.sensor.read()
        assert r1 is not None
        assert r2 is not None
        assert r1.sensor_name == "imu"
        assert r2.sensor_name == "imu"

    # -- is_moving threshold --------------------------------------------

    def test_is_moving_stationary(self):
        """A stationary stick (magnitude ≈ gravity) is not moving."""
        # Mock baselines: x,y ≈ 0, z ≈ 9.81 → magnitude ≈ gravity → not moving.
        assert self.sensor.is_moving() is False

    def test_is_moving_threshold_with_extreme_accel(self):
        """Above-threshold motion must register as moving.

        NOTE: We drive the helper directly with a crafted vector so the
        threshold math is tested independently of the mock's small jitter.
        """
        # Magnitude = sqrt(4^2 + 0^2 + 9.81^2) ≈ 10.60 → |10.60-9.81| ≈ 0.79 > 0.5
        moving = IMUSensor._compute_is_moving(4.0, 0.0, _GRAVITY, threshold=0.5)
        assert moving is True

    def test_is_moving_threshold_boundary(self):
        """Below-threshold motion must NOT register as moving."""
        # Magnitude = sqrt(0.2^2 + 0^2 + 9.81^2) ≈ 9.812 → residual ≈ 0.002 < 0.5
        moving = IMUSensor._compute_is_moving(0.2, 0.0, _GRAVITY, threshold=0.5)
        assert moving is False

    # -- get_orientation ------------------------------------------------

    def test_get_orientation_upright(self):
        """Mock stick is upright by default (Z dominates and is positive)."""
        assert self.sensor.get_orientation() == "upright"

    def test_get_orientation_inverted(self):
        """Z dominant and negative → inverted (stick upside down)."""
        assert IMUSensor._compute_orientation(0.0, 0.0, -_GRAVITY) == "inverted"

    def test_get_orientation_tilted(self):
        """X or Y dominating Z → tilted (stick off-vertical)."""
        # X >> Z → tilted
        assert IMUSensor._compute_orientation(_GRAVITY, 0.0, 1.0) == "tilted"
        # Y >> Z → tilted
        assert IMUSensor._compute_orientation(0.0, _GRAVITY, 1.0) == "tilted"

    def test_get_orientation_flat(self):
        """Neither axis dominates distinctly → flat (ambiguous / level).

        NOTE: When the largest axis ties with Z, neither 'upright' (requires
        strictly greater) nor 'tilted' (requires strictly greater) applies,
        so the driver reports 'flat'.
        """
        # All-equal magnitudes → az not strictly > ax/ay, ax/ay not strictly > az
        assert IMUSensor._compute_orientation(_GRAVITY, 0.0, _GRAVITY) == "flat"

    # -- cleanup --------------------------------------------------------

    def test_cleanup_does_not_raise(self):
        """cleanup() should be safe to call even with no hardware."""
        self.sensor.read()
        self.sensor.cleanup()  # must not raise
        # idempotent
        self.sensor.cleanup()

    def test_is_healthy_before_read_is_false(self):
        """A fresh sensor (before any read) is not healthy."""
        fresh = IMUSensor(config=IMUConfig(mock_mode=True), mock_mode=True)
        fresh.initialize()
        assert fresh.is_healthy is False