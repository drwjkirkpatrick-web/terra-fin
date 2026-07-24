"""IMU (MPU-6050) sensor driver for the Agricultural Walking Stick Agent.

NOTE: This driver reads 3-axis acceleration from an MPU-6050 inertial
measurement unit over the I2C bus of a Raspberry Pi Zero. The MPU-6050
exposes a 3-axis accelerometer + 3-axis gyroscope; this driver uses only
the accelerometer to detect stick motion (is_moving) and coarse
orientation (upright / inverted / tilted / flat), which the night-mode
sentinel and the fall/stumble detection logic consume.

WHY: A walking stick needs to know whether it is moving (to gate
harvest logging and night-mode alerts) and whether it is upright
(to detect a fall or a dropped stick). The MPU-6050 is the cheapest,
best-supported 6-DoF IMU for the Pi Zero, with two community drivers:
Adafruit's CircuitPython `adafruit_mpu6050` and the lighter `mpu6050`
package. We try the Adafruit stack first (it pairs with busio/board)
and fall back to the plain `mpu6050` package, so the driver works
regardless of which one is installed.

The driver follows the project SensorBase contract: a mock-safe path so
development and CI can run with no hardware, and a hardware path that
gracefully degrades to mock on any init or read failure. In mock mode
the Z axis stays near 9.81 m/s^2 (gravity) so is_moving() correctly
reports "stationary" and get_orientation() reports "upright" by
default, exactly like a real stick held vertically.

Hardware wiring (Raspberry Pi Zero):
  MPU-6050 VCC -> 3.3 V
  MPU-6050 GND -> GND
  MPU-6050 SDA -> GPIO2 (I2C SDA)
  MPU-6050 SCL -> GPIO3 (I2C SCL)
  MPU-6050 AD0 -> GND (address 0x68; tie to VCC for 0x69)
"""

from __future__ import annotations

import logging
import math
from typing import Any

from core.sensor_base import SensorBase
from core.types import SensorReading, utc_now
from core.mock_manager import MockManager
from core.config import IMUConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Hardware imports — optional. Wrapped so the module loads on any machine
# (CI, dev laptop) that lacks the CircuitPython / I2C stack. We try the
# Adafruit CircuitPython driver first, then the standalone `mpu6050` package.
# ---------------------------------------------------------------------------
try:
    import board  # type: ignore
    import busio  # type: ignore
    import adafruit_mpu6050  # type: ignore
except ImportError:  # pragma: no cover - hardware lib absent on dev machines
    board = None  # type: ignore
    busio = None  # type: ignore
    adafruit_mpu6050 = None  # type: ignore

try:  # alternate driver: https://pypi.org/project/mpu6050/
    from mpu6050 import mpu6050 as MPU6050Device  # type: ignore
except ImportError:  # pragma: no cover - hardware lib absent on dev machines
    MPU6050Device = None  # type: ignore


# Standard gravitational acceleration (m/s^2), used by is_moving().
_GRAVITY = 9.81


class IMUSensor(SensorBase):
    """Driver for an MPU-6050 6-DoF IMU on the I2C bus.

    Class attributes follow the SensorBase contract so the framework can
    introspect every sensor uniformly (health checks, dashboards, recorder).

    NOTE: Follows the SensorBase contract — _init_hardware() sets up the
    I2C bus and MPU-6050; _read_hardware() samples the 3-axis accelerometer;
    _read_mock() generates realistic mock data with the Z axis pinned near
    gravity. Two convenience methods — is_moving() and get_orientation() —
    derive higher-level state from a fresh accelerometer sample.
    """

    name: str = "imu"
    metrics: list[str] = ["accel_x", "accel_y", "accel_z"]
    bus_type: str = "i2c"
    description: str = (
        "IMU sensor (MPU-6050) for motion and orientation detection"
    )

    def __init__(
        self,
        config: IMUConfig | None = None,
        mock_mode: bool = False,
    ) -> None:
        """Create an IMU sensor.

        Args:
            config: IMUConfig with i2c_address and mock_mode. Defaults to a
                stock IMUConfig (mock_mode on, address 0x68) if omitted.
            mock_mode: Force mock mode on (True) or defer to the config's
                mock_mode flag (False, the default). When False and the
                config has mock_mode=True, the config wins; when True it
                always wins. Either way, a hardware-init failure degrades
                to mock via SensorBase.initialize().
        """
        self._config = config if config is not None else IMUConfig()
        # An explicit mock_mode=True always wins; otherwise defer to config.
        effective_mock = mock_mode or self._config.mock_mode
        super().__init__(mock_mode=effective_mock)
        # Each sensor keeps its own MockManager for independent random-walk
        # state — the MockManager docs explicitly recommend per-sensor use.
        self._mock = MockManager()
        # Hardware handles, populated by _init_hardware().
        self._i2c: Any = None
        self._mpu: Any = None
        # Which driver library is active: "adafruit" or "mpu6050".
        self._driver: str | None = None

    # ------------------------------------------------------------------
    # Hardware lifecycle
    # ------------------------------------------------------------------

    def _init_hardware(self) -> bool:
        """Set up the I2C bus and MPU-6050. Return True on success.

        Tries the Adafruit CircuitPython stack (board + busio +
        adafruit_mpu6050) first; if unavailable, falls back to the
        standalone `mpu6050` package. Returns False (degrading to mock)
        when neither stack is present or the I2C bus cannot be opened.
        """
        # --- Adafruit CircuitPython path --------------------------------
        if adafruit_mpu6050 is not None and board is not None and busio is not None:
            try:
                self._i2c = busio.I2C(board.SCL, board.SDA)
                self._mpu = adafruit_mpu6050.MPU6050(
                    self._i2c, address=self._config.i2c_address
                )
                self._driver = "adafruit"
                logger.info(
                    "[imu] MPU-6050 ready on I2C 0x%02X (adafruit driver)",
                    self._config.i2c_address,
                )
                return True
            except Exception as e:  # pragma: no cover - depends on real hardware
                logger.error("[imu] adafruit MPU-6050 init failed: %s", e)
                self._i2c = None
                self._mpu = None
                self._driver = None
                # Fall through to the alternate driver as a second attempt.

        # --- Standalone mpu6050 package path ----------------------------
        if MPU6050Device is not None:
            try:
                self._mpu = MPU6050Device(self._config.i2c_address)
                self._driver = "mpu6050"
                logger.info(
                    "[imu] MPU-6050 ready on I2C 0x%02X (mpu6050 driver)",
                    self._config.i2c_address,
                )
                return True
            except Exception as e:  # pragma: no cover - depends on real hardware
                logger.error("[imu] mpu6050 init failed: %s", e)
                self._mpu = None
                self._driver = None

        logger.warning(
            "[imu] no MPU-6050 driver available — cannot init hardware"
        )
        return False

    def _read_hardware(self) -> SensorReading | None:
        """Read 3-axis acceleration (m/s^2) from the MPU-6050.

        Returns None on any hardware error so the base class falls back to
        mock mode automatically.
        """
        if self._mpu is None or self._driver is None:
            return None
        try:
            if self._driver == "adafruit":
                x, y, z = self._mpu.acceleration
            else:  # standalone mpu6050 package
                data = self._mpu.get_accel_data()
                x, y, z = data["x"], data["y"], data["z"]
            return self._build_reading(
                x, y, z, source="hardware"
            )
        except Exception as e:  # pragma: no cover - depends on real hardware
            logger.error("[imu] hardware read failed: %s", e)
            return None

    # ------------------------------------------------------------------
    # Mock path — realistic data via MockManager
    # ------------------------------------------------------------------

    def _read_mock(self) -> SensorReading:
        """Generate a realistic mock accelerometer reading.

        NOTE: Uses MockManager's random-walk around the physical baselines:
        accel_x and accel_y drift near 0 (stick held vertical), while
        accel_z stays near 9.81 m/s^2 (gravity pulling along the stick's
        long axis). The small jitter (0.1 on x/y, 0.02 on z) mimics real
        sensor noise without ever leaving the "stationary / upright" band,
        so is_moving() and get_orientation() behave like a real held stick.
        """
        x = self._mock.get("accel_x", jitter=0.1)
        y = self._mock.get("accel_y", jitter=0.1)
        z = self._mock.get("accel_z", jitter=0.02)
        return self._build_reading(x, y, z, source="mock")

    # ------------------------------------------------------------------
    # Reading assembly
    # ------------------------------------------------------------------

    def _build_reading(
        self, x: float, y: float, z: float, source: str
    ) -> SensorReading:
        """Assemble a SensorReading with accelerometer metrics + derived state.

        Embeds the computed orientation and motion flag in metadata so a
        single reading is self-describing (matches the pattern used by the
        soil moisture driver, which carries its classification in metadata).
        """
        return SensorReading(
            sensor_name=self.name,
            timestamp=utc_now(),
            metrics={"accel_x": round(x, 4), "accel_y": round(y, 4),
                     "accel_z": round(z, 4)},
            units={"accel_x": "m/s^2", "accel_y": "m/s^2", "accel_z": "m/s^2"},
            metadata={
                "source": source,
                "i2c_address": self._config.i2c_address,
                "orientation": self._compute_orientation(x, y, z),
                "is_moving": self._compute_is_moving(x, y, z),
            },
        )

    # ------------------------------------------------------------------
    # Derived state — pure helpers + public API
    # ------------------------------------------------------------------

    @staticmethod
    def _accel_magnitude(x: float, y: float, z: float) -> float:
        """Euclidean magnitude of the acceleration vector."""
        return math.sqrt(x * x + y * y + z * z)

    @staticmethod
    def _compute_is_moving(
        x: float, y: float, z: float, threshold: float = 0.5
    ) -> bool:
        """Return True when |accel_magnitude - gravity| exceeds threshold.

        A stationary stick measures only gravity (magnitude ≈ 9.81), so the
        residual is ~0. Any extra motion pushes the magnitude away from
        gravity and trips the threshold.
        """
        magnitude = IMUSensor._accel_magnitude(x, y, z)
        return abs(magnitude - _GRAVITY) > threshold

    @staticmethod
    def _compute_orientation(x: float, y: float, z: float) -> str:
        """Coarse stick orientation from the accelerometer axes.

            'upright'  — Z dominates and is positive (stick vertical, tip up)
            'inverted' — Z dominates and is negative (stick upside down)
            'tilted'   — X or Y dominates over Z (stick off-vertical)
            'flat'     — none of the above (e.g. lying level / ambiguous)
        """
        ax, ay, az = abs(x), abs(y), abs(z)
        if az > ax and az > ay:
            if z > 0:
                return "upright"
            if z < 0:
                return "inverted"
        if ax > az or ay > az:
            return "tilted"
        return "flat"

    def is_moving(self, threshold: float = 0.5) -> bool:
        """Read a fresh sample and return whether the stick is moving.

        NOTE: Pulls a live accelerometer reading (hardware or mock) and
        checks the magnitude deviation from gravity. Returns False if no
        reading could be obtained.
        """
        reading = self.read()
        if reading is None:
            return False
        m = reading.metrics
        return self._compute_is_moving(
            m["accel_x"], m["accel_y"], m["accel_z"], threshold
        )

    def get_orientation(self) -> str:
        """Read a fresh sample and return the coarse stick orientation.

        Returns 'flat' if no reading could be obtained.
        """
        reading = self.read()
        if reading is None:
            return "flat"
        m = reading.metrics
        return self._compute_orientation(
            m["accel_x"], m["accel_y"], m["accel_z"]
        )

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def cleanup(self) -> None:
        """Release I2C resources if they were opened.

        In mock mode this is a safe no-op since no hardware was allocated.
        """
        self._mpu = None
        self._i2c = None
        self._driver = None