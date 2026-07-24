"""GPS sensor driver for the Terra-Fin Agent.

NOTE: Reads NMEA sentences from a serial GPS module (e.g. NEO-6M or similar)
using pyserial + pynmea2, and falls back to a MockManager-driven random walk
around Nairobi (-1.2864, 36.8222) when no hardware is present or mock_mode
is enabled.

WHY: Location data anchors harvest entries and night-mode events to a map.
The mock path produces a slow random walk so the rest of the agent (recorder,
night mode) can run on any machine without a physical GPS attached.
"""

from __future__ import annotations

import logging
from typing import Any

from core.config import GPSConfig
from core.mock_manager import MockManager
from core.sensor_base import SensorBase
from core.types import GPSPosition, SensorReading, utc_now

# Hardware deps are optional — tests/dev machines won't have them.
try:  # pragma: no cover - exercised only with real hardware
    import serial as pyserial  # noqa: F401
except ImportError:  # pragma: no cover
    pyserial = None

try:  # pragma: no cover
    import pynmea2  # noqa: F401
except ImportError:  # pragma: no cover
    pynmea2 = None

logger = logging.getLogger(__name__)

# Base coordinates for the simulated walk (Nairobi region, Kenyan highlands).
_BASE_LAT = -1.2864
_BASE_LON = 36.8222
_BASE_ALT = 1795.0


class GPSSensor(SensorBase):
    """GPS sensor reading NMEA sentences over a serial link.

    NOTE: Follows the SensorBase contract — _init_hardware / _read_hardware /
    _read_mock / cleanup. When mock_mode is True (the default from GPSConfig)
    hardware is never touched and a simulated walking pattern is produced.
    """

    name = "gps"
    metrics = ["lat", "lon", "altitude_m"]
    bus_type = "serial"
    description = "GPS module for location tracking"

    def __init__(self, config: GPSConfig | None = None) -> None:
        # Pull config (port, baud, mock_mode) from GPSConfig defaults unless one
        # is explicitly provided. SensorBase.__init__ needs the mock_mode flag.
        self.config = config or GPSConfig()
        super().__init__(mock_mode=self.config.mock_mode)
        self._serial: Any = None
        # Dedicated MockManager so the GPS walk state is independent of other
        # sensors' mock state.
        self._mock = MockManager()

    # ------------------------------------------------------------------
    # SensorBase implementation
    # ------------------------------------------------------------------

    def _init_hardware(self) -> bool:
        """Open the serial port. Returns True if the hardware is ready.

        NOTE: Returns False (without raising) if pyserial/pynmea2 are missing
        or the port cannot be opened — SensorBase then flips to mock mode.
        """
        if pyserial is None or pynmea2 is None:
            logger.warning(
                "[gps] pyserial/pynmea2 unavailable — cannot init hardware"
            )
            return False
        try:
            self._serial = pyserial.Serial(
                self.config.port, self.config.baud, timeout=1.0
            )
            logger.info(
                "[gps] opened %s @ %d baud", self.config.port, self.config.baud
            )
            return True
        except Exception as e:  # pragma: no cover - depends on real hardware
            logger.error("[gps] failed to open %s: %s", self.config.port, e)
            self._serial = None
            return False

    def _read_hardware(self) -> SensorReading | None:
        """Read one NMEA fix from the serial port.

        Reads lines until a GGA sentence (with fix) is found, then parses it
        with pynmea2 and extracts lat/lon/altitude.
        """
        if self._serial is None or pynmea2 is None:
            return None
        try:
            for _ in range(20):  # bounded scan so we don't block forever
                line = self._serial.readline()
                if not line:
                    continue
                line_str = line.decode("ascii", errors="ignore").strip()
                if not line_str or "$" not in line_str:
                    continue
                if not line_str.startswith("$"):
                    line_str = "$" + line_str
                msg = pynmea2.parse(line_str)
                if getattr(msg, "sentence_type", None) == "GGA":
                    # No fix yet — keep reading.
                    if getattr(msg, "gps_qual", 0) == 0:
                        continue
                    lat = float(msg.latitude)  # type: ignore[union-attr]
                    lon = float(msg.longitude)  # type: ignore[union-attr]
                    alt_val = getattr(msg, "altitude", None)
                    alt = float(alt_val) if alt_val else _BASE_ALT
                    pos = GPSPosition(
                        lat=lat,
                        lon=lon,
                        altitude_m=alt,
                        timestamp=utc_now(),
                        fix_quality=str(msg.gps_qual),
                    )
                    return self._build_reading(pos, source="hardware")
        except Exception as e:  # pragma: no cover
            logger.error("[gps] hardware read error: %s", e)
            return None
        return None

    def _read_mock(self) -> SensorReading:
        """Generate a simulated slow-walk GPS position.

        NOTE: Uses MockManager's random-walk for lat/lon so successive reads
        drift slightly around the Nairobi base coords — enough to exercise
        movement detection without teleporting across the map.
        """
        lat = self._mock.get("lat", jitter=0.0)
        lon = self._mock.get("lon", jitter=0.0)
        # Altitude is a static baseline here; MockManager already knows it.
        alt = self._mock.get("altitude_m", jitter=0.0)

        pos = GPSPosition(
            lat=lat,
            lon=lon,
            altitude_m=alt,
            timestamp=utc_now(),
            fix_quality="simulated",
        )
        return self._build_reading(pos, source="mock", fix_quality="simulated")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_reading(
        self,
        pos: GPSPosition,
        source: str,
        fix_quality: str | None = None,
    ) -> SensorReading:
        """Assemble a SensorReading carrying a GPSPosition in metadata."""
        metadata: dict[str, Any] = {
            "source": source,
            "position": pos,
        }
        if fix_quality is not None:
            metadata["fix_quality"] = fix_quality
        return SensorReading(
            sensor_name=self.name,
            timestamp=pos.timestamp or utc_now(),
            metrics={
                "lat": pos.lat,
                "lon": pos.lon,
                "altitude_m": pos.altitude_m if pos.altitude_m is not None else 0.0,
            },
            units={"lat": "deg", "lon": "deg", "altitude_m": "m"},
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Convenience API
    # ------------------------------------------------------------------

    def get_position(self) -> GPSPosition | None:
        """Read once and return the GPSPosition, or None on failure.

        NOTE: This is the primary call site for other modules (recorder,
        night mode) that want a fix without dealing with SensorReading.
        """
        reading = self.read()
        if reading is None:
            return None
        pos = reading.metadata.get("position")
        if isinstance(pos, GPSPosition):
            return pos
        return None

    def cleanup(self) -> None:
        """Close the serial port if it is open."""
        if self._serial is not None:
            try:
                self._serial.close()
            except Exception:  # pragma: no cover
                logger.warning("[gps] error closing serial port", exc_info=True)
            self._serial = None