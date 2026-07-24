"""Tests for core config."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.config import (
    MainConfig, GPSConfig, SoilConfig, pHConfig,
    TempHumidityConfig, LightConfig, IMUConfig,
    NightModeConfig, DashboardConfig,
)


class TestDefaults:
    def test_main_config_defaults(self):
        c = MainConfig()
        assert c.device_name == "agri-stick-01"
        assert c.mode == "day"
        assert c.storage_path == "data/agri_stick.db"

    def test_sub_config_defaults(self):
        c = MainConfig()
        assert c.gps.port == "/dev/ttyACM0"
        assert c.gps.baud == 9600
        assert c.soil_moisture.dry_threshold == 30.0
        assert c.soil_ph.min_pH == 3.0
        assert c.temp_humidity.i2c_address == 0x44
        assert c.light.night_lux_threshold == 10.0
        assert c.imu.i2c_address == 0x68
        assert c.night_mode.enabled is True
        assert c.dashboard.port == 9195

    def test_all_mock_by_default(self):
        c = MainConfig()
        assert c.gps.mock_mode is True
        assert c.soil_moisture.mock_mode is True
        assert c.temp_humidity.mock_mode is True


class TestFromEnv:
    def test_top_level_env(self, monkeypatch):
        monkeypatch.setenv("AGRI_DEVICE_NAME", "stick-99")
        monkeypatch.setenv("AGRI_MODE", "night")
        c = MainConfig.from_env()
        assert c.device_name == "stick-99"
        assert c.mode == "night"

    def test_sub_config_env(self, monkeypatch):
        monkeypatch.setenv("AGRI_GPS_PORT", "/dev/ttyUSB0")
        monkeypatch.setenv("AGRI_GPS_BAUD", "4800")
        c = MainConfig.from_env()
        assert c.gps.port == "/dev/ttyUSB0"
        assert c.gps.baud == 4800

    def test_bool_env(self, monkeypatch):
        monkeypatch.setenv("AGRI_NIGHT_MODE_ENABLED", "false")
        c = MainConfig.from_env()
        assert c.night_mode.enabled is False

    def test_no_env_returns_defaults(self):
        c = MainConfig.from_env()
        assert c.device_name == "agri-stick-01"


class TestFromDict:
    def test_from_dict_partial(self):
        data = {"device_name": "test-stick", "gps": {"port": "/dev/ttyUSB1"}}
        c = MainConfig._from_dict(data)
        assert c.device_name == "test-stick"
        assert c.gps.port == "/dev/ttyUSB1"
        # Untouched sub-configs keep defaults
        assert c.soil_moisture.dry_threshold == 30.0


class TestToDict:
    def test_to_dict_has_all_fields(self):
        c = MainConfig()
        d = c.to_dict()
        assert "device_name" in d
        assert "gps" in d
        assert "soil_moisture" in d
        assert "night_mode" in d