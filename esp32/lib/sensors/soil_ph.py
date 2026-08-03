"""Soil pH probe driver for ESP32.

Reads pH probe via ESP32 ADC (GPIO33). Calibrate in field for accuracy.
"""

import logging
from core.sensor_base import SensorBase
from core.types import SensorReading, utc_now
from core.mock_manager import MockManager
from core.config import pHConfig

logger = logging.getLogger(__name__)

_ADC_MAX_COUNTS = 4095
_ADC_VREF_V = 3.3
_PH_VOLTAGE_SLOPE = 14.0 / 3.0

try:
    from machine import ADC, Pin
    _HAS_MACHINE = True
except ImportError:
    _HAS_MACHINE = False


class SoilPHSensor(SensorBase):
    name = "soil_ph"
    metrics = ["soil_pH"]
    bus_type = "adc"
    description = "Soil pH probe on ESP32 ADC"

    def __init__(self, config=None, mock_mode=False):
        if config is None:
            config = pHConfig()
        super().__init__(config=config, mock_mode=mock_mode or config.mock_mode)
        self._mock = MockManager()
        self._adc = None

    def _init_hardware(self):
        if not _HAS_MACHINE:
            return False
        try:
            pin = self._config.adc_pin if self._config else 33
            self._adc = ADC(Pin(pin))
            self._adc.atten(ADC.ATTN_11DB)
            self._adc.width(ADC.WIDTH_12BIT)
            logger.info("[soil_ph] ADC ready on GPIO%d", pin)
            return True
        except Exception as e:
            logger.error("[soil_ph] ADC init failed: %s", e)
            return False

    def _read_hardware(self):
        if self._adc is None:
            return None
        try:
            raw = self._adc.read()
            voltage = (raw / _ADC_MAX_COUNTS) * _ADC_VREF_V
            ph = voltage * _PH_VOLTAGE_SLOPE
            ph = max(0.0, min(14.0, ph))
            return SensorReading(
                sensor_name=self.name,
                timestamp=utc_now(),
                metrics={"soil_pH": round(ph, 2)},
                units={"soil_pH": "pH"},
                metadata={"raw_adc": raw, "voltage_v": round(voltage, 3)},
            )
        except Exception as e:
            logger.error("[soil_ph] read failed: %s", e)
            return None

    def _read_mock(self):
        return SensorReading(
            sensor_name=self.name,
            timestamp=utc_now(),
            metrics={"soil_pH": self._mock.soil_ph()},
            units={"soil_pH": "pH"},
            metadata={"mock": True},
        )

    def cleanup(self):
        self._adc = None
