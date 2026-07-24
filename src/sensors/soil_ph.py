"""Soil pH sensor driver for the Agricultural Walking Stick Agent.

NOTE: This driver reads the pH probe attached to the stick tip through an
MCP3008 ADC. The probe outputs a voltage proportional to pH over the 0-14
range (0V = pH 0, 3.3V = pH 14, linear). In mock mode it pulls a realistic
value from MockManager and clamps to the configured [min_pH, max_pH] band.

WHY: The pH probe's raw voltage must be converted to pH units and then
classified (acidic / optimal / alkaline) so the agent can advise the farmer
on liming or acidification. Calibration is linear so the conversion is a
simple ratio; classification uses fixed agronomic thresholds that match
Kenyan highland staple crops (maize, beans).
"""

from __future__ import annotations

import logging

from core.sensor_base import SensorBase
from core.types import SensorReading, utc_now
from core.mock_manager import MockManager
from core.config import pHConfig

logger = logging.getLogger(__name__)

# Hardware imports — optional. On the Pi Zero these come from the
# Adafruit Blinka / CircuitPython stack (adafruit_mcp3xxx, busio, board,
# digitalio). When unavailable (e.g. dev laptop, CI) they fall back to None
# and the driver runs in mock mode.
try:
    import adafruit_mcp3xxx.mcp3008 as mcp3008  # noqa: F401
    import busio
    import board
    import digitalio
    _HARDWARE_OK = True
except ImportError:  # pragma: no cover - hardware libs absent off-device
    mcp3008 = None
    busio = None
    board = None
    digitalio = None
    _HARDWARE_OK = False


# Linear calibration constants.
#   0V  -> pH 0
#   3.3V -> pH 14
#   pH = voltage * (14.0 / 3.3)
_ADC_REF_VOLTAGE = 3.3
_PH_FULL_SCALE = 14.0
_ADC_RESOLUTION = 1023  # MCP3008 is 10-bit (0..1023)

# Agronomic classification thresholds.
ACIDIC_THRESHOLD = 5.5
ALKALINE_THRESHOLD = 7.5


class SoilPHSensor(SensorBase):
    """Soil pH probe driver reading via an MCP3008 ADC channel.

    NOTE: Follows the SensorBase contract — _init_hardware() sets up the ADC
    and SPI bus; _read_hardware() samples the configured ADC channel and
    converts the raw count to pH; _read_mock() generates realistic mock data.
    """

    name = "soil_ph"
    metrics = ["soil_pH"]
    bus_type = "adc"
    description = "Soil pH probe at stick tip"

    def __init__(self, config: pHConfig | None = None, mock_mode: bool | None = None) -> None:
        # Resolve config and mock mode. If mock_mode is explicitly passed it
        # wins; otherwise defer to the config's mock_mode flag.
        self._config = config if config is not None else pHConfig()
        if mock_mode is None:
            mock_mode = self._config.mock_mode
        super().__init__(mock_mode=mock_mode)
        self._mcp: object | None = None
        self._spi: object | None = None
        self._cs: object | None = None
        self._mock = MockManager()

    # ------------------------------------------------------------------ #
    # Hardware path
    # ------------------------------------------------------------------ #

    def _init_hardware(self) -> bool:
        """Set up the SPI bus and MCP3008 ADC. Return True if ready."""
        if not _HARDWARE_OK:
            logger.warning("[soil_ph] hardware libs unavailable, cannot init")
            return False
        try:
            self._spi = busio.SPI(clock=board.SCK, MISO=board.MISO, MOSI=board.MOSI)
            self._cs = digitalio.DigitalInOut(board.CE0)
            self._mcp = mcp3008.MCP3008(self._spi, self._cs)
            logger.info(
                "[soil_ph] MCP3008 initialised on ADC channel %d",
                self._config.adc_channel,
            )
            return True
        except Exception as e:  # pragma: no cover - hardware-specific
            logger.error("[soil_ph] MCP3008 init failed: %s", e)
            self._mcp = None
            return False

    def _read_hardware(self) -> SensorReading | None:
        """Sample the ADC channel and convert the raw count to pH."""
        if self._mcp is None:
            return None
        try:
            channel = getattr(mcp3008, f"P0{self._config.adc_channel}")
            raw = self._mcp.read(channel)
            voltage = (raw / _ADC_RESOLUTION) * _ADC_REF_VOLTAGE
            ph = voltage * (_PH_FULL_SCALE / _ADC_REF_VOLTAGE)
            ph = self._clamp_pH(ph)
            return SensorReading(
                sensor_name=self.name,
                timestamp=utc_now(),
                metrics={"soil_pH": ph},
                units={"soil_pH": "pH"},
                metadata={
                    "source": "hardware",
                    "raw_adc": int(raw),
                    "voltage": round(voltage, 4),
                    "classification": self.classify(ph),
                },
            )
        except Exception as e:  # pragma: no cover - hardware-specific
            logger.error("[soil_ph] hardware read failed: %s", e)
            return None

    # ------------------------------------------------------------------ #
    # Mock path
    # ------------------------------------------------------------------ #

    def _read_mock(self) -> SensorReading:
        """Generate a realistic mock pH reading from MockManager.

        NOTE: MockManager's baseline for soil_pH is 6.5 (Kenyan highland
        average). We add jitter=0.03 (±3%) and then clamp to the configured
        [min_pH, max_pH] band so the mock never reports absurd values.
        """
        ph = self._mock.get("soil_pH", jitter=0.03)
        ph = self._clamp_pH(ph)
        return SensorReading(
            sensor_name=self.name,
            timestamp=utc_now(),
            metrics={"soil_pH": ph},
            units={"soil_pH": "pH"},
            metadata={
                "source": "mock",
                "classification": self.classify(ph),
            },
        )

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _clamp_pH(self, ph: float) -> float:
        """Clamp a pH value to the configured [min_pH, max_pH] band."""
        return max(self._config.min_pH, min(self._config.max_pH, ph))

    @staticmethod
    def classify(ph: float) -> str:
        """Classify a pH value agronomically.

        NOTE: Thresholds match the most common Kenyan staple crops.
          - acidic : pH < 5.5   (liming needed)
          - optimal: 5.5 ≤ pH ≤ 7.5  (ideal nutrient availability)
          - alkaline: pH > 7.5  (acidification / sulphur needed)
        """
        if ph < ACIDIC_THRESHOLD:
            return "acidic"
        if ph > ALKALINE_THRESHOLD:
            return "alkaline"
        return "optimal"

    def cleanup(self) -> None:
        """Release SPI and GPIO resources held by the ADC."""
        try:
            if self._cs is not None and digitalio is not None:
                self._cs.deinit()
        except Exception:  # pragma: no cover - best-effort cleanup
            pass
        try:
            if self._spi is not None and busio is not None:
                self._spi.deinit()
        except Exception:  # pragma: no cover - best-effort cleanup
            pass
        self._mcp = None
        self._spi = None
        self._cs = None