"""Configuration system for the Terra-Fin Agent.

NOTE: All sub-configs use sensible defaults that work in mock mode.
Hardware-specific fields (ports, addresses, channels) are only used when
the corresponding sensor's _init_hardware() succeeds.

WHY: A single config tree prevents drift between modules — every module
reads from the same MainConfig, never inventing its own env vars.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, fields, asdict
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Sensor sub-configs
# ---------------------------------------------------------------------------

@dataclass
class SensorConfig:
    """Base config for any sensor."""
    enabled: bool = True
    poll_interval_s: float = 5.0
    mock_mode: bool = True


@dataclass
class GPSConfig(SensorConfig):
    port: str = "/dev/ttyACM0"
    baud: int = 9600


@dataclass
class SoilConfig(SensorConfig):
    adc_channel: int = 0
    dry_threshold: float = 30.0
    wet_threshold: float = 70.0
    probe_depth_cm: float = 15.0


@dataclass
class pHConfig(SensorConfig):
    adc_channel: int = 1
    min_pH: float = 3.0
    max_pH: float = 10.0


@dataclass
class TempHumidityConfig(SensorConfig):
    i2c_address: int = 0x44  # SHT40 default


@dataclass
class LightConfig(SensorConfig):
    adc_channel: int = 2
    night_lux_threshold: float = 10.0


@dataclass
class IMUConfig(SensorConfig):
    i2c_address: int = 0x68  # MPU-6050


# ---------------------------------------------------------------------------
# Feature configs
# ---------------------------------------------------------------------------

@dataclass
class NightModeConfig:
    enabled: bool = True
    poll_interval_s: float = 30.0
    motion_alert_threshold: float = 0.5
    log_only: bool = True


@dataclass
class DashboardConfig:
    port: int = 9195
    host: str = "0.0.0.0"


# ---------------------------------------------------------------------------
# Main config
# ---------------------------------------------------------------------------

@dataclass
class MainConfig:
    device_name: str = "terra-fin-01"
    mode: str = "day"
    storage_path: str = "data/terra-fin.db"

    gps: GPSConfig = field(default_factory=GPSConfig)
    soil_moisture: SoilConfig = field(default_factory=SoilConfig)
    soil_ph: pHConfig = field(default_factory=pHConfig)
    temp_humidity: TempHumidityConfig = field(default_factory=TempHumidityConfig)
    light: LightConfig = field(default_factory=LightConfig)
    imu: IMUConfig = field(default_factory=IMUConfig)
    night_mode: NightModeConfig = field(default_factory=NightModeConfig)
    dashboard: DashboardConfig = field(default_factory=DashboardConfig)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_yaml(cls, path: str) -> "MainConfig":
        """Load config from a YAML file."""
        import yaml  # optional dependency
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls._from_dict(data)

    @classmethod
    def from_env(cls) -> "MainConfig":
        """Load config from environment variables with AGRI_ prefix.

        Example: AGRI_DEVICE_NAME=stick-02, AGRI_GPS_PORT=/dev/ttyUSB0
        """
        kwargs: dict[str, Any] = {}
        # Top-level fields
        for f in fields(cls):
            env_key = f"AGRI_{f.name.upper()}"
            env_val = os.environ.get(env_key)
            if env_val is not None:
                if f.name in ("gps", "soil_moisture", "soil_ph", "temp_humidity",
                              "light", "imu", "night_mode", "dashboard"):
                    continue  # sub-configs handled below
                if f.type is bool or f.type == "bool":
                    kwargs[f.name] = env_val.lower() in ("true", "1", "yes")
                elif f.type is int or f.type == "int":
                    kwargs[f.name] = int(env_val)
                elif f.type is float or f.type == "float":
                    kwargs[f.name] = float(env_val)
                else:
                    kwargs[f.name] = env_val

        # Sub-config fields via AGRI_GPS_PORT, AGRI_SOIL_MOISTURE_ADC_CHANNEL, etc.
        sub_configs = {
            "gps": GPSConfig,
            "soil_moisture": SoilConfig,
            "soil_ph": pHConfig,
            "temp_humidity": TempHumidityConfig,
            "light": LightConfig,
            "imu": IMUConfig,
            "night_mode": NightModeConfig,
            "dashboard": DashboardConfig,
        }
        for sub_name, sub_cls in sub_configs.items():
            sub_kwargs: dict[str, Any] = {}
            prefix = f"AGRI_{sub_name.upper()}_"
            for sf in fields(sub_cls):
                env_key = f"{prefix}{sf.name.upper()}"
                env_val = os.environ.get(env_key)
                if env_val is not None:
                    if sf.type is bool or sf.type == "bool":
                        sub_kwargs[sf.name] = env_val.lower() in ("true", "1", "yes")
                    elif sf.type is int or sf.type == "int":
                        sub_kwargs[sf.name] = int(env_val)
                    elif sf.type is float or sf.type == "float":
                        sub_kwargs[sf.name] = float(env_val)
                    else:
                        sub_kwargs[sf.name] = env_val
            if sub_kwargs:
                # Merge with defaults
                default_instance = sub_cls()
                merged = asdict(default_instance)
                merged.update(sub_kwargs)
                kwargs[sub_name] = sub_cls(**merged)

        return cls(**kwargs)

    @classmethod
    def _from_dict(cls, data: dict) -> "MainConfig":
        """Build MainConfig from a plain dict, handling nested sub-configs."""
        kwargs: dict[str, Any] = {}
        sub_configs = {
            "gps": GPSConfig,
            "soil_moisture": SoilConfig,
            "soil_ph": pHConfig,
            "temp_humidity": TempHumidityConfig,
            "light": LightConfig,
            "imu": IMUConfig,
            "night_mode": NightModeConfig,
            "dashboard": DashboardConfig,
        }
        for f in fields(cls):
            if f.name in sub_configs:
                sub_data = data.get(f.name, {})
                if isinstance(sub_data, dict):
                    sub_cls = sub_configs[f.name]
                    defaults = asdict(sub_cls())
                    defaults.update(sub_data)
                    kwargs[f.name] = sub_cls(**defaults)
            elif f.name in data:
                kwargs[f.name] = data[f.name]
        return cls(**kwargs)