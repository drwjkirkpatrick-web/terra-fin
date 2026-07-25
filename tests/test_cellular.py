"""Tests for the cellular modem sensor driver.

NOTE: All tests run against the mock path — no serial hardware or pyserial
needed.  They verify the SensorBase contract shape, AT-command parsing
helpers, signal-band classification, mock read values, convenience API,
and cleanup.  Uses sys.path.insert(0, 'src') to import the core package
exactly as pyproject.toml's pythonpath setting would.

WHY: The cellular driver's classify_signal() bands drive upload decisions
(uploaded now vs buffered for later), so each band boundary must be
pinned and tested.  The AT-command parsers are tested with synthetic
response strings so they work on any machine.  The mock path exercises
the random-walk signal model from MockManager.
"""

import math
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.config import CellularConfig
from core.types import SensorReading
from sensors.cellular import (
    CellularSensor,
    rssi_to_dbm,
    classify_signal,
)


class TestCellularSensor:
    def setup_method(self):
        """Fresh sensor in mock mode for every test."""
        cfg = CellularConfig(mock_mode=True)
        self.sensor = CellularSensor(config=cfg)
        assert self.sensor.initialize() is True

    # -- class attributes / shape --------------------------------------

    def test_class_attributes(self):
        """Class attributes should match the SensorBase contract."""
        assert CellularSensor.name == "cellular"
        assert CellularSensor.bus_type == "serial"
        assert CellularSensor.metrics == ["rssi_dbm", "ber_pct"]
        assert "cellular" in CellularSensor.description.lower()

    def test_health_check_shape(self):
        """health_check() should report the configured sensor identity."""
        self.sensor.read()
        hc = self.sensor.health_check()
        assert hc["name"] == "cellular"
        assert hc["bus_type"] == "serial"
        assert hc["metrics"] == ["rssi_dbm", "ber_pct"]
        assert hc["initialized"] is True
        assert hc["mock_mode"] is True
        assert hc["healthy"] is True

    # -- mock read ------------------------------------------------------

    def test_mock_read_returns_reading(self):
        """A mock-mode read should return a SensorReading with rssi_dbm."""
        r = self.sensor.read()
        assert r is not None
        assert isinstance(r, SensorReading)
        assert r.sensor_name == "cellular"
        assert "rssi_dbm" in r.metrics
        assert "ber_pct" in r.metrics
        assert r.units["rssi_dbm"] == "dBm"
        assert r.units["ber_pct"] == "%"
        assert r.metadata["source"] == "mock"

    def test_mock_rssi_reasonable(self):
        """Mock RSSI should be in a plausible 4G range (-120 to -50 dBm)."""
        for _ in range(20):
            r = self.sensor.read()
            assert r is not None
            assert -120.0 <= r.metrics["rssi_dbm"] <= -50.0

    def test_mock_ber_nonnegative(self):
        """Mock BER must never be negative."""
        for _ in range(20):
            r = self.sensor.read()
            assert r is not None
            assert r.metrics["ber_pct"] >= 0.0

    def test_mock_metadata_fields(self):
        """Mock reading should carry all expected metadata fields."""
        r = self.sensor.read()
        assert r is not None
        assert r.metadata["sim_ready"] is True
        assert r.metadata["registration"] == "registered_home"
        assert r.metadata["operator"] == "Safaricom"
        assert r.metadata["network_tech"] == "4G"
        assert "signal_band" in r.metadata
        assert r.metadata["signal_band"] in ("weak", "fair", "strong")
        assert r.metadata["apn"] == "safaricom"

    def test_mock_signal_band_in_reading(self):
        """Each mock reading should carry its signal band in metadata."""
        r = self.sensor.read()
        assert r is not None
        assert r.metadata["signal_band"] in ("weak", "fair", "strong")

    # -- signal variation between reads --------------------------------

    def test_signal_variation_between_reads(self):
        """Successive mock reads should vary (random walk + jitter).

        NOTE: MockManager applies a random walk with ±3% jitter, so two
        reads should almost always differ slightly.  We sample a few
        times to avoid a rare coincidental tie.
        """
        values = []
        for _ in range(10):
            r = self.sensor.read()
            assert r is not None
            values.append(r.metrics["rssi_dbm"])
        assert len(set(values)) > 1, "random walk should produce varied RSSI"

    def test_read_twice(self):
        """Two consecutive reads should both succeed."""
        r1 = self.sensor.read()
        r2 = self.sensor.read()
        assert r1 is not None
        assert r2 is not None
        assert r1.sensor_name == "cellular"
        assert r2.sensor_name == "cellular"

    # -- rssi_to_dbm conversion ----------------------------------------

    def test_rssi_to_dbm_known_values(self):
        """RSSI index to dBm mapping per 3GPP TS 27.007."""
        assert rssi_to_dbm(0) == -113.0
        assert rssi_to_dbm(1) == -111.0
        assert rssi_to_dbm(15) == -83.0
        assert rssi_to_dbm(30) == -53.0
        assert rssi_to_dbm(31) == -51.0

    def test_rssi_to_dbm_unknown(self):
        """RSSI 99 (not known) should return NaN."""
        val = rssi_to_dbm(99)
        assert math.isnan(val)

    def test_rssi_to_dbm_out_of_range(self):
        """Out-of-range RSSI values should return NaN."""
        assert math.isnan(rssi_to_dbm(-1))
        assert math.isnan(rssi_to_dbm(32))
        assert math.isnan(rssi_to_dbm(100))

    # -- classify_signal -----------------------------------------------

    def test_classify_none_for_nan(self):
        """NaN RSSI should classify as 'none'."""
        assert classify_signal(float("nan"), -90, -70) == "none"

    def test_classify_weak(self):
        """Below warn threshold is 'weak'."""
        assert classify_signal(-100, -90, -70) == "weak"
        assert classify_signal(-91, -90, -70) == "weak"

    def test_classify_fair(self):
        """Between warn and good is 'fair'."""
        assert classify_signal(-90, -90, -70) == "fair"
        assert classify_signal(-80, -90, -70) == "fair"
        assert classify_signal(-71, -90, -70) == "fair"

    def test_classify_strong(self):
        """At or above good threshold is 'strong'."""
        assert classify_signal(-70, -90, -70) == "strong"
        assert classify_signal(-60, -90, -70) == "strong"
        assert classify_signal(-50, -90, -70) == "strong"

    # -- AT command parsers (with synthetic responses) -----------------

    def test_parse_csq_valid(self):
        """+CSQ parser should extract RSSI and BER."""
        resp = "\r\n+CSQ: 22,0\r\n\r\nOK\r\n"
        dbm, ber = CellularSensor._parse_csq(resp)
        assert dbm == rssi_to_dbm(22)  # -69 dBm
        assert ber == 0.0

    def test_parse_csq_with_ber(self):
        """+CSQ parser should handle nonzero BER."""
        resp = "\r\n+CSQ: 15,3\r\n\r\nOK\r\n"
        dbm, ber = CellularSensor._parse_csq(resp)
        assert dbm == -83.0
        assert ber == 3.0

    def test_parse_csq_unknown_rssi(self):
        """+CSQ with rssi=99 should give NaN dBm."""
        resp = "\r\n+CSQ: 99,99\r\n\r\nOK\r\n"
        dbm, ber = CellularSensor._parse_csq(resp)
        assert math.isnan(dbm)

    def test_parse_csq_malformed(self):
        """Malformed +CSQ response should return NaN/0."""
        dbm, ber = CellularSensor._parse_csq("garbage")
        assert math.isnan(dbm)
        assert ber == 0.0

    def test_parse_creg_registered(self):
        """+CREG parser should extract registration status."""
        resp = "\r\n+CREG: 0,1\r\n\r\nOK\r\n"
        assert CellularSensor._parse_creg(resp) == "registered_home"

    def test_parse_creg_roaming(self):
        """+CREG stat=5 is registered_roaming."""
        resp = "\r\n+CREG: 0,5\r\n\r\nOK\r\n"
        assert CellularSensor._parse_creg(resp) == "registered_roaming"

    def test_parse_creg_not_registered(self):
        """+CREG stat=0 is not_registered."""
        resp = "\r\n+CREG: 0,0\r\n\r\nOK\r\n"
        assert CellularSensor._parse_creg(resp) == "not_registered"

    def test_parse_creg_searching(self):
        """+CREG stat=2 is searching."""
        resp = "\r\n+CREG: 0,2\r\n\r\nOK\r\n"
        assert CellularSensor._parse_creg(resp) == "searching"

    def test_parse_creg_malformed(self):
        """Malformed +CREG should default to not_registered."""
        assert CellularSensor._parse_creg("garbage") == "not_registered"

    def test_parse_cops(self):
        """+COPS parser should extract operator name."""
        resp = '\r\n+COPS: 0,0,"Safaricom",7\r\n\r\nOK\r\n'
        assert CellularSensor._parse_cops(resp) == "Safaricom"

    def test_parse_cops_malformed(self):
        """Malformed +COPS should return 'unknown'."""
        assert CellularSensor._parse_cops("garbage") == "unknown"

    def test_parse_cnsmod_4g(self):
        """+CNSMOD parser should map act=7 to 4G."""
        resp = "\r\n+CNSMOD: 0,7\r\n\r\nOK\r\n"
        assert CellularSensor._parse_cnsmod(resp) == "4G"

    def test_parse_cnsmod_3g(self):
        """+CNSMOD parser should map act=2 to 3G."""
        resp = "\r\n+CNSMOD: 0,2\r\n\r\nOK\r\n"
        assert CellularSensor._parse_cnsmod(resp) == "3G"

    def test_parse_cnsmod_2g(self):
        """+CNSMOD parser should map act=0 to 2G."""
        resp = "\r\n+CNSMOD: 0,0\r\n\r\nOK\r\n"
        assert CellularSensor._parse_cnsmod(resp) == "2G"

    def test_parse_cnsmod_malformed(self):
        """Malformed +CNSMOD should return 'unknown'."""
        assert CellularSensor._parse_cnsmod("garbage") == "unknown"

    # -- convenience API ------------------------------------------------

    def test_get_signal_band(self):
        """get_signal_band() should return a valid band label."""
        band = self.sensor.get_signal_band()
        assert band in ("weak", "fair", "strong")

    def test_is_registered_true_mock(self):
        """Mock modem should be registered on home network."""
        assert self.sensor.is_registered() is True

    def test_is_sim_ready_true_mock(self):
        """Mock SIM should be ready."""
        assert self.sensor.is_sim_ready() is True

    # -- config thresholds ---------------------------------------------

    def test_custom_thresholds_classify_correctly(self):
        """Custom warn/good thresholds should shift band boundaries."""
        cfg = CellularConfig(
            mock_mode=True,
            signal_warn_dbm=-85.0,
            signal_good_dbm=-65.0,
        )
        s = CellularSensor(config=cfg)
        s.initialize()
        assert classify_signal(-86, cfg.signal_warn_dbm, cfg.signal_good_dbm) == "weak"
        assert classify_signal(-75, cfg.signal_warn_dbm, cfg.signal_good_dbm) == "fair"
        assert classify_signal(-64, cfg.signal_warn_dbm, cfg.signal_good_dbm) == "strong"

    def test_custom_apn_in_metadata(self):
        """Custom APN should appear in reading metadata."""
        cfg = CellularConfig(mock_mode=True, apn="airtel")
        s = CellularSensor(config=cfg)
        s.initialize()
        r = s.read()
        assert r is not None
        assert r.metadata["apn"] == "airtel"

    # -- cleanup --------------------------------------------------------

    def test_cleanup_does_not_raise(self):
        """cleanup() should be safe to call even with no hardware."""
        self.sensor.read()
        self.sensor.cleanup()  # must not raise
        # idempotent
        self.sensor.cleanup()

    def test_is_healthy_before_read_is_false(self):
        """A fresh sensor (before any read) is not healthy."""
        fresh = CellularSensor(config=CellularConfig(mock_mode=True))
        fresh.initialize()
        assert fresh.is_healthy is False