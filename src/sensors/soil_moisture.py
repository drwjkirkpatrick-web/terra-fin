"""Capacitive soil moisture sensor driver for the TerraFin Walking Stick.

NOTE: This driver reads a capacitive soil moisture probe via an MCP3008 ADC
on the SPI bus of a Raspberry Pi Zero. The probe is wired to a single ADC
channel; raw 10-bit counts are converted to a voltage and then linearly
calibrated to a 0-100 % moisture reading (0 V = dry, 3.3 V = wet).

WHY: Capacitive probes resist corrosion far better than resistive probes
because no exposed metal is in direct current contact with the soil. They
need an ADC, so we lean on the adafruit_mcp3xxx stack which is the
community-standard CircuitPython driver for the MCP3008 on the Pi.

The driver follows the project SensorBase contract: a mock-safe path so
development and CI can run with no hardware, and a hardware path that
gracefully degrades to mock on any init or read failure.

Hardware wiring (Raspberry Pi Zero):
  MCP3008 CLK  -> GPIO11 (SCLK)
  MCP3008 DOUT -> GPIO9  (MISO)
  MCP3008 DIN  -> GPIO10 (MOSI)
  MCP3008 CS   -> GPIO8  (CE0)
  Probe VCC    -> 3.3 V
  Probe GND    -> GND
  Probe AOUT   -> MCP3008 CH0 (adc_channel, configurable)
"""

from __future__ import annotations

import logging
from typing import Any

from core.sensor_base import SensorBase
from core.types import SensorReading, utc_now
from core.mock_manager import MockManager
from core.config import SoilConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Hardware imports — optional. Wrapped so the module loads on any machine
# (CI, dev laptop) that lacks the CircuitPython / SPI stack.
# ---------------------------------------------------------------------------
try:
    import board  # type: ignore
    import busio  # type: ignore
    import digitalio  # type: ignore
    import adafruit_mcp3xxx  # type: ignore
    from adafruit_mcp3xxx import mcp3008  # type: ignore
except ImportError:  # pragma: no cover - hardware lib absent on dev machines
    board = None  # type: ignore
    busio = None  # type: ignore
    digitalio = None  # type: ignore
    adafruit_mcp3xxx = None  # type: ignore
    mcp3008 = None  # type: ignore


# Calibration constants
_ADC_MAX_COUNTS = 1023          # MCP3008 is 10-bit
_ADC_VREF_V = 3.3               # Pi 3.3 V reference
# Soil moisture classification bands (percent)
_DRY_PCT = 30.0
_WET_PCT = 70.0


class SoilMoistureSensor(SensorBase):
    """Driver for a capacitive soil moisture probe on an MCP3008 ADC.

    Class attributes follow the SensorBase contract so the framework can
    introspect every sensor uniformly (health checks, dashboards, recorder).
    """

    name: str = "soil_moisture"
    metrics: list[str] = ["soil_moisture_pct"]
    bus_type: str = "adc"
    description: str = (
        "Capacitive soil moisture probe read via MCP3008 ADC channel"
    )

    def __init__(self, config: SoilConfig | None = None) -> None:
        """Create a soil moisture sensor.

        Args:
            config: SoilConfig with adc_channel, thresholds, and mock_mode.
                Defaults to a stock SoilConfig (mock mode on) if omitted.
        """
        self._config = config if config is not None else SoilConfig()
        super().__init__(mock_mode=self._config.mock_mode)
        # Each sensor keeps its own MockManager for independent random-walk
        # state — the MockManager docs explicitly recommend per-sensor use.
        self._mock = MockManager()
        # Hardware handles, populated by _init_hardware()
        self._spi = None
        self._cs = None
        self._mcp = None

    # ------------------------------------------------------------------
    # Hardware lifecycle
    # ------------------------------------------------------------------

    def _init_hardware(self) -> bool:
        """Set up SPI bus and MCP3008 ADC. Return True on success.

        Returns False (degrading to mock) when the CircuitPython stack is
        unavailable or the SPI bus cannot be opened.
        """
        if (
            adafruit_mcp3xxx is None
            or board is None
            or busio is None
            or digitalio is None
            or mcp3008 is None
        ):
            logger.warning(
                "[soil_moisture] adafruit_mcp3xxx/board/busio not available — "
                "cannot init hardware"
            )
            return False
        try:
            self._spi = busio.SPI(board.SCK, MISO=board.MISO, MOSI=board.MOSI)
            self._cs = digitalio.DigitalInOut(board.D5)
            self._mcp = mcp3008.MCP3008(self._spi, self._cs)
            logger.info(
                "[soil_moisture] MCP3008 ready on channel %d",
                self._config.adc_channel,
            )
            return True
        except Exception as e:  # pragma: no cover - depends on real hardware
            logger.error("[soil_moisture] hardware init failed: %s", e)
            self._spi = None
            self._cs = None
            self._mcp = None
            return False

    def _read_hardware(self) -> SensorReading | None:
        """Read a raw ADC count, convert to moisture percent, build reading.

        Returns None on any hardware error so the base class falls back to
        mock mode automatically.
        """
        if self._mcp is None:
            return None
        try:
            raw = self._mcp.read(self._config.adc_channel)
            moisture_pct = self._counts_to_moisture(raw)
            reading = SensorReading(
                sensor_name=self.name,
                timestamp=utc_now(),
                metrics={"soil_moisture_pct": moisture_pct},
                units={"soil_moisture_pct": "%"},
                metadata={
                    "source": "hardware",
                    "adc_channel": self._config.adc_channel,
                    "raw_counts": raw,
                    "probe_depth_cm": self._config.probe_depth_cm,
                    "classification": self.classify(moisture_pct),
                },
            )
            return reading
        except Exception as e:  # pragma: no cover - depends on real hardware
            logger.error("[soil_moisture] hardware read failed: %s", e)
            return None

    # ------------------------------------------------------------------
    # Mock path — realistic data via MockManager
    # ------------------------------------------------------------------

    def _read_mock(self) -> SensorReading:
        """Generate a realistic mock soil moisture reading.

        NOTE: Uses MockManager's random-walk around the 45 % baseline so
        successive mock readings drift naturally, mimicking real soil that
        doesn't jump instantaneously.
        """
        moisture_pct = self._mock.get("soil_moisture_pct", jitter=0.05)
        # Clamp into a physically sane 0-100 range
        moisture_pct = max(0.0, min(100.0, moisture_pct))
        return SensorReading(
            sensor_name=self.name,
            timestamp=utc_now(),
            metrics={"soil_moisture_pct": moisture_pct},
            units={"soil_moisture_pct": "%"},
            metadata={
                "source": "mock",
                "adc_channel": self._config.adc_channel,
                "probe_depth_cm": self._config.probe_depth_cm,
                "classification": self.classify(moisture_pct),
            },
        )

    # ------------------------------------------------------------------
    # Calibration + classification helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _counts_to_moisture(raw_counts: int) -> float:
        """Convert a 10-bit ADC count (0-1023) to moisture percent.

        Linear calibration: 0 V = 0 % (dry), 3.3 V = 100 % (wet).
        """
        voltage = (raw_counts / _ADC_MAX_COUNTS) * _ADC_VREF_V
        moisture_pct = (voltage / _ADC_VREF_V) * 100.0
        return round(moisture_pct, 2)

    def classify(self, moisture_pct: float) -> str:
        """Classify a moisture percentage into a soil state band.

        Bands (configurable thresholds, defaults below):
            dry   — below dry_threshold  (< 30 %)
            moist — between dry and wet   (30–70 %)
            wet   — above wet_threshold   (> 70 %)
        """
        if moisture_pct < self._config.dry_threshold:
            return "dry"
        if moisture_pct > self._config.wet_threshold:
            return "wet"
        return "moist"

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def cleanup(self) -> None:
        """Release SPI and GPIO resources if they were opened.

        In mock mode this is a safe no-op since no hardware was allocated.
        """
        self._mcp = None
        self._spi = None
        self._cs = None