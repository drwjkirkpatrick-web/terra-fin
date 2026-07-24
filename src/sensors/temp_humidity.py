"""Temperature and humidity sensor (SHT40) driver for the Terra-Fin Walking Stick.

NOTE: This driver reads a Sensirion SHT40 digital temperature and humidity
sensor over I2C on a Raspberry Pi Zero. The SHT40 is a small, low-power
calibrated sensor returning temperature (°C) and relative humidity (%). It
replaces the larger SHT3x series at the same default address (0x44) with
better accuracy specs. We use the Adafruit CircuitPython adafruit_sht4x
library, which is the community-standard driver for the Pi.

WHY: Ambient air temperature and humidity contextualise the other agronomic
readings — soil moisture, soil pH, and light — so the agent can reason about
evapotranspiration, plant stress, and disease risk. A diurnal cycle already
exists in MockManager for both temp_c and humidity_pct, so mock data mirrors
real-world day/night variation out of the box.

The driver follows the project SensorBase contract: a mock-safe path so
development and CI can run with no hardware, and a hardware path that
gracefully degrades to mock on any init or read failure.

Hardware wiring (Raspberry Pi Zero):
  SHT40 SDA -> GPIO2  (I2C SDA, physical pin 3)
  SHT40 SCL -> GPIO3  (I2C SCL, physical pin 5)
  SHT40 VCC -> 3.3 V
  SHT40 GND -> GND
  SHT40 ADDR -> GND (default address 0x44)
"""

from __future__ import annotations

import logging

from core.sensor_base import SensorBase
from core.types import SensorReading, utc_now
from core.mock_manager import MockManager
from core.config import TempHumidityConfig

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Hardware imports — optional. Wrapped so the module loads on any machine
# (CI, dev laptop) that lacks the CircuitPython / Blinka stack. When the libs
# are absent they fall back to None and the driver runs in mock mode.
# --------------------------------------------------------------------------- #
try:
    import adafruit_sht4x  # type: ignore
    import busio  # type: ignore
    import board  # type: ignore
    _HARDWARE_OK = True
except ImportError:  # pragma: no cover - hardware libs absent off-device
    adafruit_sht4x = None  # type: ignore
    busio = None  # type: ignore
    board = None  # type: ignore
    _HARDWARE_OK = False


# Temperature classification thresholds (degrees Celsius).
COLD_THRESHOLD = 15.0
HOT_THRESHOLD = 28.0

# Humidity classification thresholds (percent relative humidity).
DRY_THRESHOLD = 40.0
HUMID_THRESHOLD = 70.0


class TempHumiditySensor(SensorBase):
    """Driver for a Sensirion SHT40 temperature/humidity sensor over I2C.

    Class attributes follow the SensorBase contract so the framework can
    introspect every sensor uniformly (health checks, dashboards, recorder).
    """

    name: str = "temp_humidity"
    metrics: list[str] = ["temp_c", "humidity_pct"]
    bus_type: str = "i2c"
    description: str = "Temperature and humidity sensor (SHT40)"

    def __init__(
        self,
        config: TempHumidityConfig | None = None,
        mock_mode: bool | None = None,
    ) -> None:
        """Create a temperature/humidity sensor.

        Args:
            config: TempHumidityConfig with i2c_address and mock_mode.
                Defaults to a stock TempHumidityConfig (mock mode on) if None.
            mock_mode: If given, overrides the config's mock_mode flag. When
                None (default) the config's value is used.
        """
        self._config = config if config is not None else TempHumidityConfig()
        if mock_mode is None:
            mock_mode = self._config.mock_mode
        super().__init__(mock_mode=mock_mode)
        # Each sensor keeps its own MockManager for independent random-walk
        # state — the MockManager docs explicitly recommend per-sensor use.
        self._mock = MockManager()
        # Hardware handles, populated by _init_hardware()
        self._i2c = None
        self._sht = None

    # ------------------------------------------------------------------ #
    # Hardware lifecycle
    # ------------------------------------------------------------------ #

    def _init_hardware(self) -> bool:
        """Set up the I2C bus and SHT40 sensor. Return True on success.

        Returns False (degrading to mock) when the CircuitPython stack is
        unavailable or the I2C bus / sensor cannot be opened.
        """
        if not _HARDWARE_OK:
            logger.warning(
                "[temp_humidity] adafruit_sht4x/board/busio not available — "
                "cannot init hardware"
            )
            return False
        try:
            self._i2c = busio.I2C(board.SCL, board.SDA)
            self._sht = adafruit_sht4x.SHT4x(self._i2c)
            # Default to high-precision, no heater — best for field readings
            self._sht.mode = adafruit_sht4x.Mode.NOHEAT_HIGHPRECISION
            logger.info(
                "[temp_humidity] SHT40 ready at I2C address 0x%02x",
                self._config.i2c_address,
            )
            return True
        except Exception as e:  # pragma: no cover - depends on real hardware
            logger.error("[temp_humidity] hardware init failed: %s", e)
            self._i2c = None
            self._sht = None
            return False

    def _read_hardware(self) -> SensorReading | None:
        """Read temperature (°C) and relative humidity (%) from the SHT40.

        Returns None on any hardware error so the base class falls back to
        mock mode automatically.
        """
        if self._sht is None:
            return None
        try:
            temp_c = self._sht.temperature
            humidity_pct = self._sht.relative_humidity
            return SensorReading(
                sensor_name=self.name,
                timestamp=utc_now(),
                metrics={
                    "temp_c": round(temp_c, 2),
                    "humidity_pct": round(humidity_pct, 2),
                },
                units={"temp_c": "°C", "humidity_pct": "%"},
                metadata={
                    "source": "hardware",
                    "i2c_address": self._config.i2c_address,
                    "temp_classification": classify_temp(temp_c),
                    "humidity_classification": classify_humidity(humidity_pct),
                },
            )
        except Exception as e:  # pragma: no cover - depends on real hardware
            logger.error("[temp_humidity] hardware read failed: %s", e)
            return None

    # ------------------------------------------------------------------ #
    # Mock path — realistic data via MockManager
    # ------------------------------------------------------------------ #

    def _read_mock(self) -> SensorReading:
        """Generate a realistic mock temperature and humidity reading.

        NOTE: MockManager already has a diurnal cycle (sine wave around a
        baseline) for both temp_c (24 °C ± 6 °C) and humidity_pct
        (60 % ± 15 %), so mock values vary naturally through the day. We add
        jitter=0.05 (±5 %) on top for realistic sensor noise.
        """
        temp_c = self._mock.get("temp_c", jitter=0.05)
        humidity_pct = self._mock.get("humidity_pct", jitter=0.05)
        return SensorReading(
            sensor_name=self.name,
            timestamp=utc_now(),
            metrics={
                "temp_c": round(temp_c, 2),
                "humidity_pct": round(humidity_pct, 2),
            },
            units={"temp_c": "°C", "humidity_pct": "%"},
            metadata={
                "source": "mock",
                "temp_classification": classify_temp(temp_c),
                "humidity_classification": classify_humidity(humidity_pct),
            },
        )

    # ------------------------------------------------------------------ #
    # Cleanup
    # ------------------------------------------------------------------ #

    def cleanup(self) -> None:
        """Release I2C bus resources if they were opened.

        In mock mode this is a safe no-op since no hardware was allocated.
        """
        try:
            if self._i2c is not None and busio is not None:
                self._i2c.deinit()
        except Exception:  # pragma: no cover - best-effort cleanup
            pass
        self._sht = None
        self._i2c = None


# --------------------------------------------------------------------------- #
# Classification helpers — module-level functions
# --------------------------------------------------------------------------- #

def classify_temp(value: float) -> str:
    """Classify a temperature in °C into a band.

    NOTE: Thresholds are chosen for highland-tropical agronomy.
      - cold : value < 15 °C
      - mild : 15 ≤ value ≤ 28 °C
      - hot  : value > 28 °C
    """
    if value < COLD_THRESHOLD:
        return "cold"
    if value > HOT_THRESHOLD:
        return "hot"
    return "mild"


def classify_humidity(value: float) -> str:
    """Classify a relative humidity percentage into a band.

    NOTE: Bands map to comfort and disease-risk levels.
      - dry         : value < 40 %
      - comfortable : 40 ≤ value ≤ 70 %
      - humid       : value > 70 %
    """
    if value < DRY_THRESHOLD:
        return "dry"
    if value > HUMID_THRESHOLD:
        return "humid"
    return "comfortable"