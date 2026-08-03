"""Capacitive soil moisture sensor driver for ESP32.

Reads capacitive probe via ESP32 ADC (GPIO32). Uses 12-bit ADC.
Raw counts converted to voltage, then linearly calibrated to 0-100% moisture.
"""

import logging
from core.sensor_base import SensorBase
from core.types import SensorReading, utc_now
from core.mock_manager import MockManager
from core.config import SoilConfig

logger = logging.getLogger(__name__)

_ADC_MAX_COUNTS = 4095
_ADC_VREF_V = 3.3

try:
    from machine import ADC, Pin
    _HAS_MACHINE = True
except ImportError:
    _HAS_MACHINE = False


class SoilMoistureSensor(SensorBase):
    name = "soil_moisture"
    metrics = ["soil_moisture_pct"]
    bus_type = "adc"
    description = "Capacitive soil moisture probe on ESP32 ADC"

    def __init__(self, config=None, mock_mode=False):
        if config is None:
            config = SoilConfig()
        super().__init__(config=config, mock_mode=mock_mode or config.mock_mode)
        self._mock = MockManager()
        self._adc = None

    def _init_hardware(self):
        if not _HAS_MACHINE:
            return False
        try:
            pin = self._config.adc_pin if self._config else 32
            self._adc = ADC(Pin(pin))
            self._adc.atten(ADC.ATTN_11DB)
            self._adc.width(ADC.WIDTH_12BIT)
            logger.info("[soil_moisture] ADC ready on GPIO%d", pin)
            return True
        except Exception as e:
            logger.error("[soil_moisture] ADC init failed: %s", e)
            return False

    def _read_hardware(self):
        if self._adc is None:
            return None
        try:
            raw = self._adc.read()
            voltage = (raw / _ADC_MAX_COUNTS) * _ADC_VREF_V
            moisture = (voltage / _ADC_VREF_V) * 100.0
            moisture = max(0.0, min(100.0, moisture))
            return SensorReading(
                sensor_name=self.name,
                timestamp=utc_now(),
                metrics={"soil_moisture_pct": round(moisture, 1)},
                units={"soil_moisture_pct": "%"},
                metadata={"raw_adc": raw, "voltage_v": round(voltage, 3)},
            )
        except Exception as e:
            logger.error("[soil_moisture] read failed: %s", e)
            return None

    def _read_mock(self):
        return SensorReading(
            sensor_name=self.name,
            timestamp=utc_now(),
            metrics={"soil_moisture_pct": self._mock.soil_moisture()},
            units={"soil_moisture_pct": "%"},
            metadata={"mock": True},
        )

    def cleanup(self):
        self._adc = None
