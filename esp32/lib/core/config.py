"""Configuration system for Terra-Fin Agent (ESP32/MicroPython).

NOTE: Simple class-based config with no pathlib, no complex dataclasses.
All defaults work in mock mode.
"""

import os
import json


class SensorConfig:
    """Base config for any sensor."""
    def __init__(self, enabled=True, poll_interval_s=5.0, mock_mode=True):
        self.enabled = enabled
        self.poll_interval_s = poll_interval_s
        self.mock_mode = mock_mode


class GPSConfig(SensorConfig):
    def __init__(self, enabled=True, poll_interval_s=5.0, mock_mode=True, port=2, baud=9600):
        super().__init__(enabled, poll_interval_s, mock_mode)
        self.port = port
        self.baud = baud


class SoilConfig(SensorConfig):
    def __init__(self, enabled=True, poll_interval_s=5.0, mock_mode=True, adc_pin=32, dry_threshold=30.0, wet_threshold=70.0, probe_depth_cm=15.0):
        super().__init__(enabled, poll_interval_s, mock_mode)
        self.adc_pin = adc_pin
        self.dry_threshold = dry_threshold
        self.wet_threshold = wet_threshold
        self.probe_depth_cm = probe_depth_cm


class pHConfig(SensorConfig):
    def __init__(self, enabled=True, poll_interval_s=5.0, mock_mode=True, adc_pin=33, min_pH=3.0, max_pH=10.0):
        super().__init__(enabled, poll_interval_s, mock_mode)
        self.adc_pin = adc_pin
        self.min_pH = min_pH
        self.max_pH = max_pH


class TempHumidityConfig(SensorConfig):
    def __init__(self, enabled=True, poll_interval_s=5.0, mock_mode=True, i2c_id=0, scl_pin=22, sda_pin=21, i2c_freq=100000):
        super().__init__(enabled, poll_interval_s, mock_mode)
        self.i2c_id = i2c_id
        self.scl_pin = scl_pin
        self.sda_pin = sda_pin
        self.i2c_freq = i2c_freq


class LightConfig(SensorConfig):
    def __init__(self, enabled=True, poll_interval_s=5.0, mock_mode=True, adc_pin=34, night_lux_threshold=10.0):
        super().__init__(enabled, poll_interval_s, mock_mode)
        self.adc_pin = adc_pin
        self.night_lux_threshold = night_lux_threshold


class IMUConfig(SensorConfig):
    def __init__(self, enabled=True, poll_interval_s=5.0, mock_mode=True, i2c_id=0, scl_pin=22, sda_pin=21, i2c_freq=100000, i2c_address=0x68):
        super().__init__(enabled, poll_interval_s, mock_mode)
        self.i2c_id = i2c_id
        self.scl_pin = scl_pin
        self.sda_pin = sda_pin
        self.i2c_freq = i2c_freq
        self.i2c_address = i2c_address


class CellularConfig(SensorConfig):
    def __init__(self, enabled=True, poll_interval_s=30.0, mock_mode=True, port=1, baud=115200, apn="safaricom", model="SIM7600G-H", signal_warn_dbm=-90.0, signal_good_dbm=-70.0, upload_enabled=False, upload_interval_s=3600.0):
        super().__init__(enabled, poll_interval_s, mock_mode)
        self.port = port
        self.baud = baud
        self.apn = apn
        self.model = model
        self.signal_warn_dbm = signal_warn_dbm
        self.signal_good_dbm = signal_good_dbm
        self.upload_enabled = upload_enabled
        self.upload_interval_s = upload_interval_s


class NightModeConfig:
    def __init__(self, enabled=True, poll_interval_s=30.0, motion_alert_threshold=0.5, log_only=True):
        self.enabled = enabled
        self.poll_interval_s = poll_interval_s
        self.motion_alert_threshold = motion_alert_threshold
        self.log_only = log_only


class DashboardConfig:
    def __init__(self, enabled=True, port=8080, refresh_interval_s=5.0):
        self.enabled = enabled
        self.port = port
        self.refresh_interval_s = refresh_interval_s


class UploadConfig:
    def __init__(self, enabled=False, endpoint="", api_key=""):
        self.enabled = enabled
        self.endpoint = endpoint
        self.api_key = api_key


class MainConfig:
    def __init__(self):
        self.device_name = "terra-fin-esp32-01"
        self.storage_path = "/flash/data/terra-fin"
        self.soil_moisture = SoilConfig()
        self.soil_ph = pHConfig()
        self.gps = GPSConfig()
        self.temp_humidity = TempHumidityConfig()
        self.light = LightConfig()
        self.imu = IMUConfig()
        self.cellular = CellularConfig()
        self.night_mode = NightModeConfig()
        self.dashboard = DashboardConfig()
        self.upload = UploadConfig()
        self.mock_mode = True
        self.log_level = "INFO"

    def to_dict(self):
        return {
            "device_name": self.device_name,
            "storage_path": self.storage_path,
            "mock_mode": self.mock_mode,
            "log_level": self.log_level,
            "soil_moisture": {"enabled": self.soil_moisture.enabled, "poll_interval_s": self.soil_moisture.poll_interval_s, "mock_mode": self.soil_moisture.mock_mode, "adc_pin": self.soil_moisture.adc_pin},
            "soil_ph": {"enabled": self.soil_ph.enabled, "poll_interval_s": self.soil_ph.poll_interval_s, "mock_mode": self.soil_ph.mock_mode, "adc_pin": self.soil_ph.adc_pin},
            "gps": {"enabled": self.gps.enabled, "poll_interval_s": self.gps.poll_interval_s, "mock_mode": self.gps.mock_mode, "port": self.gps.port, "baud": self.gps.baud},
            "temp_humidity": {"enabled": self.temp_humidity.enabled, "poll_interval_s": self.temp_humidity.poll_interval_s, "mock_mode": self.temp_humidity.mock_mode, "i2c_id": self.temp_humidity.i2c_id, "scl_pin": self.temp_humidity.scl_pin, "sda_pin": self.temp_humidity.sda_pin},
            "light": {"enabled": self.light.enabled, "poll_interval_s": self.light.poll_interval_s, "mock_mode": self.light.mock_mode, "adc_pin": self.light.adc_pin},
            "imu": {"enabled": self.imu.enabled, "poll_interval_s": self.imu.poll_interval_s, "mock_mode": self.imu.mock_mode, "i2c_id": self.imu.i2c_id, "scl_pin": self.imu.scl_pin, "sda_pin": self.imu.sda_pin, "i2c_address": self.imu.i2c_address},
            "cellular": {"enabled": self.cellular.enabled, "poll_interval_s": self.cellular.poll_interval_s, "mock_mode": self.cellular.mock_mode, "port": self.cellular.port, "baud": self.cellular.baud, "apn": self.cellular.apn, "upload_enabled": self.cellular.upload_enabled},
            "night_mode": {"enabled": self.night_mode.enabled, "poll_interval_s": self.night_mode.poll_interval_s, "motion_alert_threshold": self.night_mode.motion_alert_threshold, "log_only": self.night_mode.log_only},
            "dashboard": {"enabled": self.dashboard.enabled, "port": self.dashboard.port},
            "upload": {"enabled": self.upload.enabled, "endpoint": self.upload.endpoint},
        }

    @classmethod
    def from_dict(cls, data):
        cfg = cls()
        cfg.device_name = data.get("device_name", cfg.device_name)
        cfg.storage_path = data.get("storage_path", cfg.storage_path)
        cfg.mock_mode = data.get("mock_mode", cfg.mock_mode)
        cfg.log_level = data.get("log_level", cfg.log_level)
        if "soil_moisture" in data:
            s = data["soil_moisture"]
            cfg.soil_moisture.enabled = s.get("enabled", True)
            cfg.soil_moisture.adc_pin = s.get("adc_pin", 32)
        if "soil_ph" in data:
            s = data["soil_ph"]
            cfg.soil_ph.enabled = s.get("enabled", True)
            cfg.soil_ph.adc_pin = s.get("adc_pin", 33)
        if "gps" in data:
            s = data["gps"]
            cfg.gps.enabled = s.get("enabled", True)
            cfg.gps.port = s.get("port", 2)
            cfg.gps.baud = s.get("baud", 9600)
        if "temp_humidity" in data:
            s = data["temp_humidity"]
            cfg.temp_humidity.enabled = s.get("enabled", True)
            cfg.temp_humidity.scl_pin = s.get("scl_pin", 22)
            cfg.temp_humidity.sda_pin = s.get("sda_pin", 21)
        if "light" in data:
            s = data["light"]
            cfg.light.enabled = s.get("enabled", True)
            cfg.light.adc_pin = s.get("adc_pin", 34)
        if "imu" in data:
            s = data["imu"]
            cfg.imu.enabled = s.get("enabled", True)
            cfg.imu.i2c_address = s.get("i2c_address", 0x68)
        if "cellular" in data:
            s = data["cellular"]
            cfg.cellular.enabled = s.get("enabled", True)
            cfg.cellular.apn = s.get("apn", "safaricom")
            cfg.cellular.upload_enabled = s.get("upload_enabled", False)
        if "night_mode" in data:
            s = data["night_mode"]
            cfg.night_mode.enabled = s.get("enabled", True)
        if "dashboard" in data:
            s = data["dashboard"]
            cfg.dashboard.enabled = s.get("enabled", True)
            cfg.dashboard.port = s.get("port", 8080)
        if "upload" in data:
            s = data["upload"]
            cfg.upload.enabled = s.get("enabled", False)
        return cfg

    def save(self, path):
        with open(path, "w") as f:
            json.dump(self.to_dict(), f)

    @classmethod
    def load(cls, path):
        with open(path) as f:
            return cls.from_dict(json.load(f))
