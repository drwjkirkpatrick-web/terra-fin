"""Cellular modem driver for ESP32.

Uses ESP32 UART for AT commands with SIM7600/SIM7000.
"""

import logging
import time
from core.sensor_base import SensorBase
from core.types import SensorReading, utc_now
from core.mock_manager import MockManager
from core.config import CellularConfig

logger = logging.getLogger(__name__)

try:
    from machine import UART, Pin
    _HAS_MACHINE = True
except ImportError:
    _HAS_MACHINE = False


class CellularSensor(SensorBase):
    name = "cellular"
    metrics = ["signal_dbm", "csq"]
    bus_type = "serial"
    description = "SIM7600 cellular modem on ESP32 UART"

    def __init__(self, config=None, mock_mode=False):
        if config is None:
            config = CellularConfig()
        super().__init__(config=config, mock_mode=mock_mode or config.mock_mode)
        self._mock = MockManager()
        self._uart = None

    def _init_hardware(self):
        if not _HAS_MACHINE:
            return False
        try:
            port = self._config.port if self._config else 1
            baud = self._config.baud if self._config else 115200
            self._uart = UART(port, baudrate=baud, tx=Pin(17), rx=Pin(16))
            self._uart.write(b'AT\r\n')
            time.sleep_ms(200)
            resp = self._uart.read()
            if resp and b'OK' in resp:
                logger.info("[cellular] Modem ready on UART%d", port)
                return True
            return False
        except Exception as e:
            logger.error("[cellular] UART init failed: %s", e)
            return False

    def _read_hardware(self):
        if self._uart is None:
            return None
        try:
            self._uart.write(b'AT+CSQ\r\n')
            time.sleep_ms(300)
            resp = self._uart.read()
            if not resp:
                return None
            text = resp.decode('ascii', 'ignore')
            for line in text.split("\n"):
                if '+CSQ:' in line:
                    parts = line.split(':')[1].split(',')
                    rssi = int(parts[0].strip())
                    if rssi == 99:
                        dbm = -120.0
                    else:
                        dbm = -113.0 + rssi * 2.0
                    return SensorReading(
                        sensor_name=self.name,
                        timestamp=utc_now(),
                        metrics={"signal_dbm": round(dbm, 1), "csq": rssi},
                        units={"signal_dbm": "dBm", "csq": "0-31"},
                        metadata={"network_status": "registered" if rssi != 99 else "unknown"},
                    )
            return None
        except Exception as e:
            logger.error("[cellular] read failed: %s", e)
            return None

    def _read_mock(self):
        return SensorReading(
            sensor_name=self.name,
            timestamp=utc_now(),
            metrics={"signal_dbm": self._mock.cellular_signal(), "csq": 15},
            units={"signal_dbm": "dBm", "csq": "0-31"},
            metadata={"mock": True, "network_status": "mock"},
        )

    def cleanup(self):
        if self._uart:
            self._uart.deinit()
        self._uart = None
