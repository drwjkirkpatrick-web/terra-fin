"""LDR light sensor driver for ESP32.

Reads LDR voltage divider via ESP32 ADC (GPIO34).
Returns approximate lux. Calibrate against known lux meter.
"""

import logging
from core.sensor_base import SensorBase
from core.types import SensorReading, utc_now
from core.mock_manager import MockManager
from core.config import LightConfig

logger = logging.getLogger(__name__)

_ADC_MAX_COUNTS = 4095
_ADC_VREF_V = 3.3
_LUX_SCALE = 50000.0

try:
    from machine import ADC, Pin
    _HAS_MACHINE = True
except ImportError:
    _HAS_MACHINE = False


class LightSensor(SensorBase):
    name = "light"
    metrics = ["light_lux"]
    bus_type = "adc"
    description = "LDR light sensor on ESP32 ADC"

    def __init__(self, config=None, mock_mode=False):
        if config is None:
            config = LightConfig()
        super().__init__(config=config, mock_mode=mock_mode or config.mock_mode)
        self._mock = MockManager()
        self._adc = None

    def _init_hardware(self):
        if not _HAS_MACHINE:
            return False
        try:
            pin = self._config.adc_pin if self._config else 34
            self._adc = ADC(Pin(pin))
            self._adc.atten(ADC.ATTN_11DB)
            self._adc.width(ADC.WIDTH_12BIT)
            logger.info("[light] ADC ready on GPIO%d", pin)
            return True
        except Exception as e:
            logger.error("[light] ADC init failed: %s", e)
            return False

    def _read_hardware(self):
        if self._adc is None:
            return None
        try:
            raw = self._adc.read()
            voltage = (raw / _ADC_MAX_COUNTS) * _ADC_VREF_V
            lux = (voltage / _ADC_VREF_V) * _LUX_SCALE
            lux = max(0.0, lux)
            return SensorReading(
                sensor_name=self.name,
                timestamp=utc_now(),
                metrics={"light_lux": round(lux, 1)},
                units={"light_lux": "lux"},
                metadata={"raw_adc": raw, "voltage_v": round(voltage, 3)},
            )
        except Exception as e:
            logger.error("[light] read failed: %s", e)
            return None

    def _read_mock(self):
        return SensorReading(
            sensor_name=self.name,
            timestamp=utc_now(),
            metrics={"light_lux": self._mock.light_lux()},
            units={"light_lux": "lux"},
            metadata={"mock": True},
        )

    def cleanup(self):
        self._adc = None
