"""Ambient light sensor driver for the Terra-Fin Agent.

NOTE: This driver reads an LDR (light-dependent resistor) divider on an
MCP3008 ADC channel of a Raspberry Pi Zero. The LDR's resistance drops with
illumination, so the divider voltage rises with light. Raw 10-bit ADC
counts are converted to a voltage and then mapped to illuminance in lux on
a power-law curve that approximates a typical LDR response:
    lux = 100000 * (voltage / 3.3) ** 2.2
(0 V = 0 lux, 3.3 V ≈ 100 000 lux — bright direct sunlight). A logarithmic
mapping is used because an LDR's resistance spans many orders of magnitude
between starlight and noon sun, so a linear scale would crush the
day/night decision boundary into a tiny voltage sliver.

WHY: Day/night detection drives the stick's night-mode sentinel (motion
alerts, battery conservation, reduced polling). The driver therefore
exposes a cheap is_night() helper that reads the sensor and compares
against a configurable lux threshold, plus a classify() band that gives
finer-grained light states (night / dawn_dusk / overcast / daylight /
bright) for the dashboard and agronomic logging.

The driver follows the project SensorBase contract: a mock-safe path so
development and CI can run with no hardware, and a hardware path that
gracefully degrades to mock on any init or read failure. Mock values come
from MockManager, which already models a diurnal cycle for light_lux
(so mock readings naturally swing from near-zero at night to tens of
thousands of lux at midday).

Hardware wiring (Raspberry Pi Zero):
  MCP3008 CLK  -> GPIO11 (SCLK)
  MCP3008 DOUT -> GPIO9  (MISO)
  MCP3008 DIN  -> GPIO10 (MOSI)
  MCP3008 CS   -> GPIO8  (CE0)
  LDR divider  -> MCP3008 CH2 (adc_channel, configurable)
  Divider VCC  -> 3.3 V
  Divider GND  -> GND
"""

from __future__ import annotations

import logging

from core.sensor_base import SensorBase
from core.types import SensorReading, utc_now
from core.mock_manager import MockManager
from core.config import LightConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Hardware imports — optional. Wrapped so the module loads on any machine
# (CI, dev laptop) that lacks the CircuitPython / SPI stack. On the Pi Zero
# these come from the Adafruit Blinka / CircuitPython stack.
# ---------------------------------------------------------------------------
try:
    import adafruit_mcp3xxx  # type: ignore
    import adafruit_mcp3xxx.mcp3008 as mcp3008  # type: ignore # noqa: F401
    import busio  # type: ignore
    import board  # type: ignore
    import digitalio  # type: ignore
    _HARDWARE_OK = True
except ImportError:  # pragma: no cover - hardware libs absent off-device
    adafruit_mcp3xxx = None  # type: ignore
    mcp3008 = None  # type: ignore
    busio = None  # type: ignore
    board = None  # type: ignore
    digitalio = None  # type: ignore
    _HARDWARE_OK = False


# ---------------------------------------------------------------------------
# Calibration constants
# ---------------------------------------------------------------------------
_ADC_MAX_COUNTS = 1023          # MCP3008 is 10-bit (0..1023)
_ADC_VREF_V = 3.3               # Pi 3.3 V reference
_LUX_FULL_SCALE = 100_000.0     # 3.3 V ≈ 100 000 lux (bright direct sunlight)
_LUX_POWER = 2.2                # power-law exponent approximating LDR response

# Classification band boundaries (lux). These match the bands documented on
# classify(); see that method for the agronomic rationale.
_NIGHT_LUX = 10.0
_DAWN_DUSK_LUX = 500.0
_OVERCAST_LUX = 10_000.0
_DAYLIGHT_LUX = 50_000.0


class LightSensor(SensorBase):
    """Ambient light sensor reading an LDR divider via an MCP3008 ADC channel.

    NOTE: Follows the SensorBase contract — _init_hardware() sets up the SPI
    bus and ADC; _read_hardware() samples the configured channel, converts
    the raw count to a voltage, then to lux via the power-law calibration;
    _read_mock() pulls a diurnal-aware value from MockManager. is_night()
    and classify() give the agent fast day/night decisions.

    Class attributes follow the SensorBase contract so the framework can
    introspect every sensor uniformly (health checks, dashboards, recorder).
    """

    name: str = "light"
    metrics: list[str] = ["light_lux"]
    bus_type: str = "adc"
    description: str = "Ambient light sensor for day/night detection"

    def __init__(self, config: LightConfig | None = None, mock_mode: bool = False) -> None:
        """Create an ambient light sensor.

        Args:
            config: LightConfig with adc_channel, night_lux_threshold, and
                mock_mode. Defaults to a stock LightConfig (mock mode on) if
                omitted.
            mock_mode: Force mock mode regardless of the config flag. When
                True the sensor skips hardware init entirely.
        """
        self._config = config if config is not None else LightConfig()
        # An explicit mock_mode argument wins over the config flag so callers
        # can force mock mode in tests without editing the config.
        effective_mock = mock_mode or self._config.mock_mode
        super().__init__(mock_mode=effective_mock)
        # Each sensor keeps its own MockManager for independent random-walk
        # state — the MockManager docs explicitly recommend per-sensor use.
        self._mock = MockManager()
        # Hardware handles, populated by _init_hardware()
        self._spi = None
        self._cs = None
        self._mcp = None

    # ------------------------------------------------------------------ #
    # Hardware lifecycle
    # ------------------------------------------------------------------ #

    def _init_hardware(self) -> bool:
        """Set up the SPI bus and MCP3008 ADC. Return True if ready.

        Returns False (degrading to mock) when the CircuitPython stack is
        unavailable or the SPI bus cannot be opened.
        """
        if not _HARDWARE_OK:
            logger.warning(
                "[light] adafruit_mcp3xxx/board/busio not available — "
                "cannot init hardware"
            )
            return False
        try:
            self._spi = busio.SPI(clock=board.SCK, MISO=board.MISO, MOSI=board.MOSI)
            self._cs = digitalio.DigitalInOut(board.CE0)
            self._mcp = mcp3008.MCP3008(self._spi, self._cs)
            logger.info(
                "[light] MCP3008 ready on channel %d",
                self._config.adc_channel,
            )
            return True
        except Exception as e:  # pragma: no cover - depends on real hardware
            logger.error("[light] hardware init failed: %s", e)
            self._spi = None
            self._cs = None
            self._mcp = None
            return False

    def _read_hardware(self) -> SensorReading | None:
        """Read a raw ADC count, convert to lux, and build a SensorReading.

        Returns None on any hardware error so the base class falls back to
        mock mode automatically.
        """
        if self._mcp is None:
            return None
        try:
            raw = self._mcp.read(self._config.adc_channel)
            lux = self._counts_to_lux(raw)
            return SensorReading(
                sensor_name=self.name,
                timestamp=utc_now(),
                metrics={"light_lux": lux},
                units={"light_lux": "lx"},
                metadata={
                    "source": "hardware",
                    "adc_channel": self._config.adc_channel,
                    "raw_counts": raw,
                    "voltage": round(self._raw_to_voltage(raw), 4),
                    "classification": self.classify(lux),
                },
            )
        except Exception as e:  # pragma: no cover - depends on real hardware
            logger.error("[light] hardware read failed: %s", e)
            return None

    # ------------------------------------------------------------------ #
    # Mock path — realistic diurnal data via MockManager
    # ------------------------------------------------------------------ #

    def _read_mock(self) -> SensorReading:
        """Generate a realistic mock ambient light reading.

        NOTE: MockManager models a diurnal sine cycle for light_lux — it
        returns near-zero lux at local night (≈02:00) and a large daytime
        peak at ≈14:00 (Kenya EAT = UTC+3). We request jitter=0.05 (±5%)
        so successive reads vary slightly, then clamp to non-negative since
        lux is physically unsigned.
        """
        lux = self._mock.get("light_lux", jitter=0.05)
        lux = max(0.0, lux)  # illuminance cannot be negative
        return SensorReading(
            sensor_name=self.name,
            timestamp=utc_now(),
            metrics={"light_lux": lux},
            units={"light_lux": "lx"},
            metadata={
                "source": "mock",
                "adc_channel": self._config.adc_channel,
                "classification": self.classify(lux),
            },
        )

    # ------------------------------------------------------------------ #
    # Calibration + classification helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _raw_to_voltage(raw_counts: int) -> float:
        """Convert a 10-bit ADC count (0-1023) to voltage (0-3.3 V)."""
        return (raw_counts / _ADC_MAX_COUNTS) * _ADC_VREF_V

    @staticmethod
    def _counts_to_lux(raw_counts: int) -> float:
        """Convert a 10-bit ADC count to illuminance in lux.

        Power-law calibration approximating LDR response:
            lux = 100000 * (voltage / 3.3) ** 2.2
        0 V = 0 lux (dark), 3.3 V ≈ 100 000 lux (bright sun).
        """
        voltage = LightSensor._raw_to_voltage(raw_counts)
        ratio = voltage / _ADC_VREF_V
        lux = _LUX_FULL_SCALE * (ratio ** _LUX_POWER)
        return round(lux, 2)

    def classify(self, value: float) -> str:
        """Classify an illuminance value into a light-state band.

        Bands (lux):
            night     — < 10           (starlight/moonlight; sentinel mode)
            dawn_dusk — 10 – 500        (horizon glow, twilight transitions)
            overcast  — 500 – 10 000    (heavy cloud / shade, dim daytime)
            daylight  — 10 000 – 50 000 (normal indoor-to-outdoor daylight)
            bright    — > 50 000        (direct noon sun, clear sky)

        WHY: These bands give the agent coarse but agronomically meaningful
        light context — e.g. "overcast" tells the farmer that solar drying
        will be slow, while "bright" signals full-sun crops are productive.
        The night band boundary matches the default night_lux_threshold.
        """
        if value < _NIGHT_LUX:
            return "night"
        if value < _DAWN_DUSK_LUX:
            return "dawn_dusk"
        if value < _OVERCAST_LUX:
            return "overcast"
        if value < _DAYLIGHT_LUX:
            return "daylight"
        return "bright"

    def is_night(self) -> bool:
        """Return True if the current ambient light is below night threshold.

        Reads the sensor and checks whether light_lux < night_lux_threshold
        (default 10 lux). Used by the night-mode sentinel to decide whether
        to enter power-conserving motion-alert mode.

        Returns False if the sensor read fails (fail-safe: assume day).
        """
        reading = self.read()
        if reading is None:
            return False
        lux = reading.metrics.get("light_lux", 0.0)
        return lux < self._config.night_lux_threshold

    # ------------------------------------------------------------------ #
    # Cleanup
    # ------------------------------------------------------------------ #

    def cleanup(self) -> None:
        """Release SPI and GPIO resources if they were opened.

        In mock mode this is a safe no-op since no hardware was allocated.
        """
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