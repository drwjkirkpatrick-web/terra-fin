"""SHT40 temperature and humidity sensor for ESP32.

Uses ESP32 I2C (GPIO21=SDA, GPIO22=SCL).
MicroPython direct I2C register reads.
"""

import logging
import time
from core.sensor_base import SensorBase
from core.types import SensorReading, utc_now
from core.mock_manager import MockManager
from core.config import TempHumidityConfig

logger = logging.getLogger(__name__)

_SHT40_ADDR = 0x44
_SHT40_MEAS_HIGH = bytes([0xFD])

try:
    from machine import I2C, Pin
    _HAS_MACHINE = True
except ImportError:
    _HAS_MACHINE = False


def _crc8(data):
    crc = 0xFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = (crc << 1) ^ 0x31
            else:
                crc <<= 1
        crc &= 0xFF
    return crc


class TempHumiditySensor(SensorBase):
    name = "temp_humidity"
    metrics = ["temp_c", "humidity_pct"]
    bus_type = "i2c"
    description = "SHT40 on ESP32 I2C"

    def __init__(self, config=None, mock_mode=False):
        if config is None:
            config = TempHumidityConfig()
        super().__init__(config=config, mock_mode=mock_mode or config.mock_mode)
        self._mock = MockManager()
        self._i2c = None

    def _init_hardware(self):
        if not _HAS_MACHINE:
            return False
        try:
            scl = self._config.scl_pin if self._config else 22
            sda = self._config.sda_pin if self._config else 21
            self._i2c = I2C(self._config.i2c_id if self._config else 0,
                           scl=Pin(scl), sda=Pin(sda),
                           freq=self._config.i2c_freq if self._config else 100000)
            devices = self._i2c.scan()
            if _SHT40_ADDR not in devices:
                return False
            logger.info("[temp_humidity] SHT40 ready on I2C 0x%02X", _SHT40_ADDR)
            return True
        except Exception as e:
            logger.error("[temp_humidity] I2C init failed: %s", e)
            return False

    def _read_hardware(self):
        if self._i2c is None:
            return None
        try:
            self._i2c.writeto(_SHT40_ADDR, _SHT40_MEAS_HIGH)
            time.sleep_ms(10)
            data = self._i2c.readfrom(_SHT40_ADDR, 6)
            if len(data) != 6:
                return None
            if _crc8(data[0:2]) != data[2] or _crc8(data[3:5]) != data[5]:
                return None
            temp_raw = (data[0] << 8) | data[1]
            humidity_raw = (data[3] << 8) | data[4]
            temp_c = -45.0 + 175.0 * (temp_raw / 65535.0)
            humidity_pct = -6.0 + 125.0 * (humidity_raw / 65535.0)
            humidity_pct = max(0.0, min(100.0, humidity_pct))
            return SensorReading(
                sensor_name=self.name,
                timestamp=utc_now(),
                metrics={"temp_c": round(temp_c, 2), "humidity_pct": round(humidity_pct, 2)},
                units={"temp_c": "C", "humidity_pct": "%RH"},
                metadata={},
            )
        except Exception as e:
            logger.error("[temp_humidity] read failed: %s", e)
            return None

    def _read_mock(self):
        return SensorReading(
            sensor_name=self.name,
            timestamp=utc_now(),
            metrics={"temp_c": self._mock.temperature(), "humidity_pct": self._mock.humidity()},
            units={"temp_c": "C", "humidity_pct": "%RH"},
            metadata={"mock": True},
        )

    def cleanup(self):
        self._i2c = None
