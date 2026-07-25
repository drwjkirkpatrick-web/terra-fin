"""Cellular modem sensor driver for the Terra-Fin Agent.

NOTE: This driver talks to a SIMCom LTE Cat-1 modem (SIM7600G-H by default)
over a USB serial link using AT commands.  It reports signal strength
(RSSI in dBm), bit error rate (BER %), network registration status,
operator name, and network technology (2G/3G/4G).  The shark-fin antenna
atop the walking stick houses the cellular primary antenna plus an
optional GNSS patch antenna — see hardware/shark_fin_antenna.md for the
physical design.

WHY: A cellular link lets the agent upload harvest logs, night-mode
alerts, and telemetry from the field without relying on the farmer's
phone or a WiFi hotspot.  Signal quality also factors into adaptation
advisories — if the link is weak the agent can buffer data and defer
uploads until the farmer returns to better coverage.

The driver follows the project SensorBase contract: a mock-safe path
so development and CI can run with no hardware, and a hardware path
that gracefully degrades to mock on any init or read failure.  Mock
values come from MockManager, which models a gentle random walk for
cellular_rssi_dbm and cellular_ber_pct.

Hardware wiring (Raspberry Pi Zero 2 W):
  SIM7600 USB  -> Pi Zero micro-USB via OTG cable
  Appears as   -> /dev/ttyUSB2 (data port); also /dev/ttyUSB0, /dev/ttyUSB1
  Power        -> 3.7V LiPo or 5V USB (modem draws ~500 mA peaks during TX)
  Antenna      -> Primary cellular antenna in shark-fin enclosure (U.FL → SMA → fin)
  GNSS (opt)   -> GNSS patch antenna also in shark-fin fin (U.FL pigtail)
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from core.config import CellularConfig
from core.mock_manager import MockManager
from core.sensor_base import SensorBase
from core.types import SensorReading, utc_now

# Hardware deps are optional — tests/dev machines won't have them.
try:  # pragma: no cover - exercised only with real hardware
    import serial as pyserial  # noqa: F401
except ImportError:  # pragma: no cover
    pyserial = None

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# AT command constants
# --------------------------------------------------------------------------- #

# Signal quality report: +CSQ: <rssi>,<ber>
# rssi: 0-31 (31 = -51 dBm or better), 99 = not known; map to dBm:
#   dBm = -113 + 2*rssi  (for rssi 0-30), rssi=31 ≈ -51 dBm, rssi=99 = unknown
# ber: 0-7 (%), 99 = not known
_AT_CSQ = "AT+CSQ"

# Network registration: +CREG: <stat>[,<lac>,<ci>,<act>]
# stat: 0=not registered, 1=registered home, 2=searching, 3=denied,
#       4=unknown, 5=registered roaming
_AT_CREG = "AT+CREG?"

# Operator name: +COPS: <mode>,<format>,<oper>
_AT_COPS = "AT+COPS?"

# Network technology query (SIM7600): +CNSMOD: <mode>,<act>
# act: 0=2G, 2=3G, 7=4G LTE, others vary by module
_AT_CNSMOD = "AT+CNSMOD?"

# SIM card status: +CPIN: <code>  (READY = OK)
_AT_CPIN = "AT+CPIN?"

# RSSI 0-31 to dBm mapping (3GPP TS 27.007 §8.4)
_RSSI_DBM_MAP = {
    0: -113, 1: -111, 2: -109, 3: -107, 4: -105, 5: -103,
    6: -101, 7: -99, 8: -97, 9: -95, 10: -93, 11: -91,
    12: -89, 13: -87, 14: -85, 15: -83, 16: -81, 17: -79,
    18: -77, 19: -75, 20: -73, 21: -71, 22: -69, 23: -67,
    24: -65, 25: -63, 26: -61, 27: -59, 28: -57, 29: -55,
    30: -53, 31: -51,
}

# Network technology labels by access technology code
_NET_TECH_LABELS: dict[int, str] = {
    0: "2G",   # GSM
    1: "2G",   # GSM COMPACT
    2: "3G",   # UTRAN
    3: "3G",   # GSM EDGE
    4: "3G",   # UTRAN HSDPA
    5: "3G",   # UTRAN HSUPA
    6: "3G",   # UTRAN HSPA
    7: "4G",   # E-UTRAN (LTE)
    8: "4G",   # E-UTRAN Cat-M1
    9: "4G",   # E-UTRAN NB-IoT
}

# CREG status code labels
_CREG_LABELS: dict[int, str] = {
    0: "not_registered",
    1: "registered_home",
    2: "searching",
    3: "denied",
    4: "unknown",
    5: "registered_roaming",
}


def rssi_to_dbm(rssi: int) -> float:
    """Convert 3GPP CSQ RSSI index (0-31, 99) to dBm.

    Per 3GPP TS 27.007 §8.4:
        rssi 0  → -113 dBm
        rssi n  → -113 + 2*n dBm  (for 0 ≤ n ≤ 30)
        rssi 31 → ≥ -51 dBm (saturates at -51)
        rssi 99 → not known / not detectable

    Returns NaN for unknown (99) so downstream code can detect it.
    """
    if rssi == 99:
        return float("nan")
    if rssi < 0 or rssi > 31:
        return float("nan")
    return float(_RSSI_DBM_MAP.get(rssi, -113 + 2 * rssi))


def classify_signal(dbm: float, warn: float, good: float) -> str:
    """Classify signal strength into bands.

    Bands (configurable via CellularConfig thresholds):
        none    — NaN / not measurable
        weak    — below warn threshold (default < -90 dBm)
        fair    — between warn and good (default -90 to -70 dBm)
        strong  — at or above good threshold (default ≥ -70 dBm)

    WHY: The agent uses this band to decide whether to attempt an upload
    now (strong/fair) or buffer and defer (weak/none).
    """
    if dbm != dbm:  # NaN check
        return "none"
    if dbm < warn:
        return "weak"
    if dbm < good:
        return "fair"
    return "strong"


class CellularSensor(SensorBase):
    """Cellular modem sensor reading AT commands over a serial link.

    NOTE: Follows the SensorBase contract — _init_hardware / _read_hardware /
    _read_mock / cleanup.  When mock_mode is True (the default from
    CellularConfig) hardware is never touched and a simulated signal
    pattern is produced.

    The driver polls four AT commands on each read:
        AT+CPIN?   — SIM card ready?
        AT+CSQ     — signal quality (RSSI + BER)
        AT+CREG?   — network registration status
        AT+COPS?   — operator name
        AT+CNSMOD? — network technology (2G/3G/4G)

    Each is independently parseable and individually tolerant of failure
    — if one command times out we log a warning and substitute defaults
    rather than discarding the entire reading.
    """

    name: str = "cellular"
    metrics: list[str] = ["rssi_dbm", "ber_pct"]
    bus_type: str = "serial"
    description: str = (
        "Cellular modem for telemetry upload and signal quality monitoring"
    )

    def __init__(self, config: CellularConfig | None = None) -> None:
        self.config = config or CellularConfig()
        super().__init__(mock_mode=self.config.mock_mode)
        self._serial: Any = None
        self._mock = MockManager()
        # Cached operator name — doesn't change often, so we only
        # re-query every ~10 reads to save serial bandwidth.
        self._operator_cache: str = ""
        self._operator_cache_count: int = 0
        self._net_tech_cache: str = "4G"
        self._net_tech_cache_count: int = 0

    # ------------------------------------------------------------------ #
    # SensorBase implementation
    # ------------------------------------------------------------------ #

    def _init_hardware(self) -> bool:
        """Open the serial port to the modem.  Returns True if ready.

        NOTE: Returns False (without raising) if pyserial is missing or
        the port cannot be opened — SensorBase then flips to mock mode.
        """
        if pyserial is None:
            logger.warning(
                "[cellular] pyserial unavailable — cannot init hardware"
            )
            return False
        try:
            self._serial = pyserial.Serial(
                self.config.port, self.config.baud, timeout=2.0
            )
            # Send a basic AT command to verify the modem is alive.
            self._serial.write(b"AT\r\n")
            time.sleep(0.1)
            resp = self._serial.read(256)
            if resp and b"OK" in resp:
                logger.info(
                    "[cellular] opened %s @ %d baud — modem responding",
                    self.config.port, self.config.baud,
                )
                return True
            logger.warning(
                "[cellular] modem on %s did not respond to AT — falling back",
                self.config.port,
            )
            self._serial.close()
            self._serial = None
            return False
        except Exception as e:  # pragma: no cover - depends on real hardware
            logger.error("[cellular] failed to open %s: %s", self.config.port, e)
            self._serial = None
            return False

    def _read_hardware(self) -> SensorReading | None:
        """Poll the modem via AT commands and assemble a SensorReading.

        Each AT command is sent and its response parsed independently.
        If the serial port is unavailable or all commands fail, returns
        None so SensorBase falls back to mock mode.
        """
        if self._serial is None:
            return None
        try:
            rssi_dbm = float("nan")
            ber_pct = 0.0
            reg_status = "not_registered"
            operator = "unknown"
            net_tech = "unknown"
            sim_ready = False

            # 1. SIM card status
            resp = self._send_at(_AT_CPIN)
            if resp and "READY" in resp:
                sim_ready = True

            # 2. Signal quality
            resp = self._send_at(_AT_CSQ)
            if resp:
                rssi_dbm, ber_pct = self._parse_csq(resp)

            # 3. Network registration
            resp = self._send_at(_AT_CREG)
            if resp:
                reg_status = self._parse_creg(resp)

            # 4. Operator name (cached — re-query every 10 reads)
            self._operator_cache_count += 1
            if self._operator_cache and self._operator_cache_count < 10:
                operator = self._operator_cache
            else:
                resp = self._send_at(_AT_COPS)
                if resp:
                    operator = self._parse_cops(resp)
                    self._operator_cache = operator
                    self._operator_cache_count = 0

            # 5. Network technology (cached — re-query every 10 reads)
            self._net_tech_cache_count += 1
            if self._net_tech_cache and self._net_tech_cache_count < 10:
                net_tech = self._net_tech_cache
            else:
                resp = self._send_at(_AT_CNSMOD)
                if resp:
                    net_tech = self._parse_cnsmod(resp)
                    self._net_tech_cache = net_tech
                    self._net_tech_cache_count = 0

            signal_band = classify_signal(
                rssi_dbm,
                self.config.signal_warn_dbm,
                self.config.signal_good_dbm,
            )

            return SensorReading(
                sensor_name=self.name,
                timestamp=utc_now(),
                metrics={
                    "rssi_dbm": rssi_dbm if rssi_dbm == rssi_dbm else 0.0,
                    "ber_pct": ber_pct,
                },
                units={"rssi_dbm": "dBm", "ber_pct": "%"},
                metadata={
                    "source": "hardware",
                    "port": self.config.port,
                    "model": self.config.model,
                    "sim_ready": sim_ready,
                    "registration": reg_status,
                    "operator": operator,
                    "network_tech": net_tech,
                    "signal_band": signal_band,
                    "apn": self.config.apn,
                },
            )
        except Exception as e:  # pragma: no cover
            logger.error("[cellular] hardware read error: %s", e)
            return None

    def _read_mock(self) -> SensorReading:
        """Generate a simulated cellular signal reading.

        NOTE: Uses MockManager's random-walk for rssi and ber so successive
        reads drift slightly — enough to exercise signal-band classification
        without teleporting across bands every poll.  The mock simulates
        a registered, SIM-ready 4G connection on Safaricom by default.
        """
        rssi = self._mock.get("cellular_rssi_dbm", jitter=0.03)
        ber = self._mock.get("cellular_ber_pct", jitter=0.05)
        ber = max(0.0, ber)  # BER cannot be negative

        signal_band = classify_signal(
            rssi,
            self.config.signal_warn_dbm,
            self.config.signal_good_dbm,
        )

        return SensorReading(
            sensor_name=self.name,
            timestamp=utc_now(),
            metrics={
                "rssi_dbm": round(rssi, 1),
                "ber_pct": round(ber, 2),
            },
            units={"rssi_dbm": "dBm", "ber_pct": "%"},
            metadata={
                "source": "mock",
                "port": self.config.port,
                "model": self.config.model,
                "sim_ready": True,
                "registration": "registered_home",
                "operator": "Safaricom",
                "network_tech": "4G",
                "signal_band": signal_band,
                "apn": self.config.apn,
            },
        )

    # ------------------------------------------------------------------ #
    # AT command helpers (hardware-only)
    # ------------------------------------------------------------------ #

    def _send_at(self, cmd: str) -> str | None:
        """Send an AT command and return the response as a string.

        NOTE: Reads until the 'OK' or 'ERROR' terminator, or until the
        read timeout expires.  Returns None on timeout or error.
        """
        if self._serial is None:
            return None
        try:
            self._serial.write((cmd + "\r\n").encode("ascii"))
            time.sleep(0.05)
            # Read in a loop until we see OK/ERROR or timeout
            chunks: list[bytes] = []
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                chunk = self._serial.read(256)
                if chunk:
                    chunks.append(chunk)
                    text = b"".join(chunks).decode("ascii", errors="ignore")
                    if "OK" in text or "ERROR" in text:
                        return text
            if chunks:
                return b"".join(chunks).decode("ascii", errors="ignore")
            return None
        except Exception as e:  # pragma: no cover
            logger.warning("[cellular] AT command '%s' failed: %s", cmd, e)
            return None

    @staticmethod
    def _parse_csq(resp: str) -> tuple[float, float]:
        """Parse +CSQ response into (rssi_dbm, ber_pct).

        Expected format: +CSQ: <rssi>,<ber>
        """
        match = re.search(r"\+CSQ:\s*(\d+),(\d+)", resp)
        if not match:
            return float("nan"), 0.0
        rssi_idx = int(match.group(1))
        ber_idx = int(match.group(2))
        dbm = rssi_to_dbm(rssi_idx)
        # BER index 0-7 maps to 0-7%, 99 = unknown → 0.0
        ber_pct = float(ber_idx) if 0 <= ber_idx <= 7 else 0.0
        return dbm, ber_pct

    @staticmethod
    def _parse_creg(resp: str) -> str:
        """Parse +CREG response into a registration status label.

        Expected: +CREG: <n>,<stat>[,<lac>,<ci>,<act>]
        """
        match = re.search(r"\+CREG:\s*\d+,(\d+)", resp)
        if not match:
            return "not_registered"
        stat = int(match.group(1))
        return _CREG_LABELS.get(stat, "unknown")

    @staticmethod
    def _parse_cops(resp: str) -> str:
        """Parse +COPS response to extract operator name.

        Expected: +COPS: <mode>,<format>,<oper>[,<act>]
        """
        match = re.search(r"\+COPS:\s*[\d,]+,\"([^\"]+)\"", resp)
        if not match:
            return "unknown"
        return match.group(1)

    @staticmethod
    def _parse_cnsmod(resp: str) -> str:
        """Parse +CNSMOD response to extract network technology.

        Expected: +CNSMOD: <n>,<act>
        """
        match = re.search(r"\+CNSMOD:\s*\d+,(\d+)", resp)
        if not match:
            return "unknown"
        act = int(match.group(1))
        return _NET_TECH_LABELS.get(act, "unknown")

    # ------------------------------------------------------------------ #
    # Convenience API
    # ------------------------------------------------------------------ #

    def get_signal_band(self) -> str:
        """Read once and return the signal band label.

        NOTE: This is the primary call site for adaptation modules that
        want to decide whether to upload or buffer data.
        """
        reading = self.read()
        if reading is None:
            return "none"
        return reading.metadata.get("signal_band", "none")

    def is_registered(self) -> bool:
        """Return True if the modem is registered on a network.

        Reads the sensor and checks whether registration status is
        'registered_home' or 'registered_roaming'.
        """
        reading = self.read()
        if reading is None:
            return False
        reg = reading.metadata.get("registration", "not_registered")
        return reg in ("registered_home", "registered_roaming")

    def is_sim_ready(self) -> bool:
        """Return True if the SIM card is ready."""
        reading = self.read()
        if reading is None:
            return False
        return reading.metadata.get("sim_ready", False)

    # ------------------------------------------------------------------ #
    # Cleanup
    # ------------------------------------------------------------------ #

    def cleanup(self) -> None:
        """Close the serial port if it is open."""
        if self._serial is not None:
            try:
                self._serial.close()
            except Exception:  # pragma: no cover
                logger.warning(
                    "[cellular] error closing serial port", exc_info=True
                )
            self._serial = None