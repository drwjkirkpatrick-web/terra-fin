"""GPS module driver for ESP32.

Uses ESP32 UART to read NMEA sentences. Parses $GPGGA for lat/lon/alt.
"""

import logging
from core.sensor_base import SensorBase
from core.types import SensorReading, utc_now
from core.mock_manager import MockManager
from core.config import GPSConfig

logger = logging.getLogger(__name__)

try:
    from machine import UART, Pin
    _HAS_MACHINE = True
except ImportError:
    _HAS_MACHINE = False


def _parse_gpgga(line):
    if not line.startswith('$GPGGA'):
        return None
    parts = line.split(',')
    if len(parts) < 10:
        return None
    try:
        if parts[2] == '' or parts[4] == '':
            return None
        lat_deg = float(parts[2][:2])
        lat_min = float(parts[2][2:])
        lat = lat_deg + lat_min / 60.0
        if parts[3] == 'S':
            lat = -lat
        lon_deg = float(parts[4][:3])
        lon_min = float(parts[4][3:])
        lon = lon_deg + lon_min / 60.0
        if parts[5] == 'W':
            lon = -lon
        alt = float(parts[9]) if parts[9] else 0.0
        return (lat, lon, alt)
    except (ValueError, IndexError):
        return None


class GPSSensor(SensorBase):
    name = "gps"
    metrics = ["lat", "lon", "altitude_m"]
    bus_type = "serial"
    description = "GPS on ESP32 UART"

    def __init__(self, config=None, mock_mode=False):
        if config is None:
            config = GPSConfig()
        super().__init__(config=config, mock_mode=mock_mode or config.mock_mode)
        self._mock = MockManager()
        self._uart = None

    def _init_hardware(self):
        if not _HAS_MACHINE:
            return False
        try:
            port = self._config.port if self._config else 2
            baud = self._config.baud if self._config else 9600
            self._uart = UART(port, baudrate=baud, tx=Pin(17), rx=Pin(16))
            logger.info("[gps] UART%d ready at %d baud", port, baud)
            return True
        except Exception as e:
            logger.error("[gps] UART init failed: %s", e)
            return False

    def _read_hardware(self):
        if self._uart is None:
            return None
        try:
            if self._uart.any():
                raw = self._uart.read()
                if raw:
                    text = raw.decode('ascii', 'ignore')
                    for line in reversed(text.split("\n")):
                        line = line.strip()
                        result = _parse_gpgga(line)
                        if result:
                            lat, lon, alt = result
                            return SensorReading(
                                sensor_name=self.name,
                                timestamp=utc_now(),
                                metrics={"lat": round(lat, 6), "lon": round(lon, 6), "altitude_m": round(alt, 1)},
                                units={"lat": "deg", "lon": "deg", "altitude_m": "m"},
                                metadata={"fix_quality": "GPS"},
                            )
            return None
        except Exception as e:
            logger.error("[gps] read failed: %s", e)
            return None

    def _read_mock(self):
        return SensorReading(
            sensor_name=self.name,
            timestamp=utc_now(),
            metrics={"lat": self._mock.gps_lat(), "lon": self._mock.gps_lon(), "altitude_m": 1800.0},
            units={"lat": "deg", "lon": "deg", "altitude_m": "m"},
            metadata={"mock": True, "fix_quality": "mock"},
        )

    def cleanup(self):
        if self._uart:
            self._uart.deinit()
        self._uart = None
